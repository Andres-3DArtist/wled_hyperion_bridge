"""Tests for the Hyperion TCP JSON API client."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from custom_components.wled_hyperion_bridge.hyperion import (
    HyperionAuthError,
    HyperionClient,
    HyperionConnectionError,
    HyperionInstanceError,
    normalize_hyperion_config,
)


class FakeHyperionServer:
    """Minimal Hyperion JSON-server double (newline-delimited JSON)."""

    def __init__(
        self,
        led: dict[int, bool] | None = None,
        require_auth: bool = False,
        token: str = "test-token",
    ) -> None:
        """Configure per-instance LEDDEVICE state and auth."""
        self.led: dict[int, bool] = dict(led if led is not None else {0: True})
        self.require_auth = require_auth
        self.token = token
        self.requests: list[dict[str, Any]] = []
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> int:
        """Start listening on 127.0.0.1 and return the port."""

        async def handle(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            authed = False
            current = 0
            try:
                while True:
                    line = await reader.readline()
                    if not line:
                        return
                    try:
                        request = json.loads(line.decode("utf-8"))
                    except ValueError:
                        continue
                    if not isinstance(request, dict):
                        continue
                    self.requests.append(request)
                    tan = request.get("tan", 0)
                    command = request.get("command")

                    if command == "authorize" and request.get("subcommand") == "login":
                        if request.get("token") == self.token:
                            authed = True
                            response = {
                                "command": "authorize-login",
                                "success": True,
                                "tan": tan,
                            }
                        else:
                            response = {
                                "command": "authorize-login",
                                "success": False,
                                "error": "Invalid token",
                                "tan": tan,
                            }
                    elif self.require_auth and not authed:
                        response = {
                            "command": command,
                            "success": False,
                            "error": "No Authorization",
                            "tan": tan,
                        }
                    elif (
                        command == "instance"
                        and request.get("subcommand") == "switchTo"
                    ):
                        instance = request.get("instance")
                        if instance in self.led:
                            current = instance
                            response = {
                                "command": "instance-switchTo",
                                "success": True,
                                "info": {"instance": instance},
                                "tan": tan,
                            }
                        else:
                            response = {
                                "command": "instance-switchTo",
                                "success": False,
                                "error": f"Hyperion instance [{instance}] does not exist.",
                                "tan": tan,
                            }
                    elif command == "serverinfo":
                        response = {
                            "command": "serverinfo",
                            "success": True,
                            "tan": tan,
                            "info": {
                                "components": [
                                    {
                                        "name": "LEDDEVICE",
                                        "enabled": self.led.get(current, False),
                                    }
                                ],
                                "instance": [
                                    {
                                        "instance": idx,
                                        "friendly_name": f"Instance {idx}",
                                        "running": True,
                                    }
                                    for idx in sorted(self.led)
                                ],
                            },
                        }
                    elif command == "componentstate":
                        state = request.get("componentstate", {})
                        for idx in request.get("instance", [current]):
                            if idx in self.led:
                                self.led[idx] = bool(state.get("state"))
                        response = {
                            "command": "componentstate",
                            "success": True,
                            "tan": tan,
                        }
                    else:
                        response = {
                            "command": command,
                            "success": False,
                            "error": "unknown command",
                            "tan": tan,
                        }
                    writer.write((json.dumps(response) + "\n").encode())
                    await writer.drain()
            finally:
                writer.close()

        self._server = await asyncio.start_server(handle, "127.0.0.1", 0)
        sock = self._server.sockets[0]
        return sock.getsockname()[1]

    async def stop(self) -> None:
        """Stop the server."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()


@pytest.fixture
async def hyperion_server():
    """Yield a running fake Hyperion with LEDDEVICE on."""
    server = FakeHyperionServer(led={0: True})
    port = await server.start()
    yield server, port
    await server.stop()


def _client(server_and_port, **kwargs) -> HyperionClient:
    _, port = server_and_port
    return HyperionClient(host="127.0.0.1", port=port, **kwargs)


async def test_read_led_state(hyperion_server) -> None:
    """Client reads LEDDEVICE state for one instance."""
    state = await _client(hyperion_server).async_read_led_state([0])

    assert state == {0: True}


async def test_ensure_enables_only_when_off() -> None:
    """Client writes componentstate only for instances that are off."""
    server = FakeHyperionServer(led={0: True, 1: False})
    port = await server.start()
    try:
        states, changed = await HyperionClient(host="127.0.0.1", port=port).async_ensure_led_enabled([0, 1])
    finally:
        await server.stop()

    assert states == {0: True, 1: True}
    assert changed == [1]
    writes = [r for r in server.requests if r.get("command") == "componentstate"]
    assert len(writes) == 1
    assert writes[0]["instance"] == [1]
    assert writes[0]["componentstate"] == {"component": "LEDDEVICE", "state": True}
    assert server.led == {0: True, 1: True}


async def test_ensure_writes_nothing_when_already_on(hyperion_server) -> None:
    """No write happens when LEDDEVICE is already on (stream reset bug)."""
    server, _ = hyperion_server

    states, changed = await _client(hyperion_server).async_ensure_led_enabled([0])

    assert states == {0: True}
    assert changed == []
    assert [r for r in server.requests if r.get("command") == "componentstate"] == []


async def test_login_with_token() -> None:
    """Client logs in before reading when a token is configured."""
    server = FakeHyperionServer(led={0: False}, require_auth=True)
    port = await server.start()
    try:
        state = await HyperionClient(
            host="127.0.0.1", port=port, token="test-token"
        ).async_read_led_state([0])
    finally:
        await server.stop()

    assert state == {0: False}
    logins = [
        r
        for r in server.requests
        if r.get("command") == "authorize" and r.get("subcommand") == "login"
    ]
    assert len(logins) == 1
    assert logins[0]["token"] == "test-token"


async def test_auth_required_without_token() -> None:
    """Missing token surfaces as an auth error, not a generic failure."""
    server = FakeHyperionServer(led={0: True}, require_auth=True)
    port = await server.start()
    try:
        with pytest.raises(HyperionAuthError):
            await HyperionClient(host="127.0.0.1", port=port).async_read_led_state([0])
    finally:
        await server.stop()


async def test_wrong_token_rejected() -> None:
    """A bad token raises an auth error."""
    server = FakeHyperionServer(led={0: True}, require_auth=True)
    port = await server.start()
    try:
        with pytest.raises(HyperionAuthError):
            await HyperionClient(
                host="127.0.0.1", port=port, token="wrong"
            ).async_read_led_state([0])
    finally:
        await server.stop()


async def test_connection_refused() -> None:
    """Unreachable Hyperion raises a connection error."""
    with pytest.raises(HyperionConnectionError):
        await HyperionClient(host="127.0.0.1", port=1).async_read_led_state([0])


async def test_unknown_instance(hyperion_server) -> None:
    """switchTo on a missing instance raises an instance error."""
    with pytest.raises(HyperionInstanceError):
        await _client(hyperion_server).async_read_led_state([9])


async def test_all_instances_resolves_running() -> None:
    """Empty target list reads every running instance."""
    server = FakeHyperionServer(led={0: True, 1: False})
    port = await server.start()
    try:
        state = await HyperionClient(host="127.0.0.1", port=port).async_read_led_state([])
    finally:
        await server.stop()

    assert state == {0: True, 1: False}


def test_normalize_empty_host_is_none() -> None:
    """Empty host means a WLED-only bridge."""
    assert normalize_hyperion_config({"host": "  ", "port": 19444}) is None


def test_normalize_all_instances() -> None:
    """All-instances flag maps to an empty target list."""
    config = normalize_hyperion_config(
        {"host": "hyperion.local", "port": 19444, "all_instances": True, "instance": 0}
    )

    assert config is not None
    assert config["instances"] == []
    assert config["token"] is None


def test_normalize_rejects_bad_values() -> None:
    """Bad host, port and instance raise ValueError."""
    with pytest.raises(ValueError):
        normalize_hyperion_config({"host": "http://x", "port": 19444})
    with pytest.raises(ValueError):
        normalize_hyperion_config({"host": "hyperion", "port": 0})
    with pytest.raises(ValueError):
        normalize_hyperion_config({"host": "hyperion", "port": 19444, "instance": 300})
