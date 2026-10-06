"""Async Hyperion JSON API (TCP) client.

Talks to Hyperion's JSON server (default port 19444, plain TCP with
newline-delimited JSON objects) to read and control the LEDDEVICE component
per instance.

Session model, verified against the Hyperion JSON-RPC docs:
- Optional login first: {"command": "authorize", "subcommand": "login",
  "token": ...}. Without a token the server answers "No Authorization" to
  protected commands when API authentication is enabled.
- Commands run against the connection's current instance (instance 0 by
  default), so switch first: {"command": "instance", "subcommand":
  "switchTo", "instance": N} in the SAME session.
- Read state: {"command": "serverinfo"} -> info.components is a list of
  {"name": ..., "enabled": ...}; info.instance lists running instances.
- Write: {"command": "componentstate", "instance": [N],
  "componentstate": {"component": "LEDDEVICE", "state": true}}.
  An empty instance array applies to all instances.

Callers must read before writing: re-enabling LEDDEVICE while it is already
on resets Hyperion's LED stream (hyperion.ng#967) and WLED goes dark.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from dataclasses import dataclass
from typing import Any

from .const import (
    CONF_HYPERION_ALL_INSTANCES,
    CONF_HYPERION_HOST,
    CONF_HYPERION_INSTANCE,
    CONF_HYPERION_PORT,
    CONF_HYPERION_TOKEN,
    DEFAULT_HYPERION_INSTANCE,
    DEFAULT_HYPERION_PORT,
    MAX_HYPERION_INSTANCE,
)
from .devices import validate_host, validate_port

_LOGGER = logging.getLogger(__name__)

LEDDEVICE_COMPONENT = "LEDDEVICE"


class HyperionAPIError(Exception):
    """Base Hyperion API error."""


class HyperionConnectionError(HyperionAPIError):
    """Raised when Hyperion cannot be reached."""


class HyperionAuthError(HyperionAPIError):
    """Raised when Hyperion rejects the call (bad/missing token)."""


class HyperionInstanceError(HyperionAPIError):
    """Raised when a Hyperion instance does not exist or is not running."""


class HyperionResponseError(HyperionAPIError):
    """Raised when Hyperion answers with success=false or garbage."""


def normalize_hyperion_config(data: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize an optional per-bridge Hyperion config.

    Returns None when no host is given (bridge stays WLED-only).
    ``instances`` is a list of instance indices; an empty list means all
    instances, matching the Hyperion API convention.
    """
    host = str(data.get(CONF_HYPERION_HOST) or "").strip()
    if not host:
        return None
    validate_host(host)
    port = validate_port(data.get(CONF_HYPERION_PORT, DEFAULT_HYPERION_PORT))
    token = str(data.get(CONF_HYPERION_TOKEN) or "").strip() or None
    all_instances = bool(data.get(CONF_HYPERION_ALL_INSTANCES, False))
    try:
        instance = int(data.get(CONF_HYPERION_INSTANCE, DEFAULT_HYPERION_INSTANCE))  # type: ignore[arg-type]
    except (TypeError, ValueError) as err:
        raise ValueError("invalid_instance") from err
    if not 0 <= instance <= MAX_HYPERION_INSTANCE:
        raise ValueError("invalid_instance")
    return {
        CONF_HYPERION_HOST: host,
        CONF_HYPERION_PORT: port,
        CONF_HYPERION_TOKEN: token,
        CONF_HYPERION_ALL_INSTANCES: all_instances,
        CONF_HYPERION_INSTANCE: instance,
        "instances": [] if all_instances else [instance],
    }


@dataclass(slots=True)
class HyperionClient:
    """Small async client for Hyperion's TCP JSON API."""

    host: str
    port: int = DEFAULT_HYPERION_PORT
    token: str | None = None
    request_timeout: float = 10.0

    async def async_read_led_state(
        self, instances: list[int]
    ) -> dict[int, bool]:
        """Return LEDDEVICE enabled state per target instance."""
        async with _HyperionSession(self) as session:
            targets = await session.async_resolve_targets(instances)
            states: dict[int, bool] = {}
            for target in targets:
                await session.async_switch_to(target)
                states[target] = await session.async_led_enabled()
            return states

    async def async_ensure_led_enabled(
        self, instances: list[int]
    ) -> tuple[dict[int, bool], list[int]]:
        """Enable LEDDEVICE output on targets that have it off.

        Returns the LED states per target and the instances that were
        changed, so callers can update state without opening a second
        session. Never writes to instances that already report LEDDEVICE on.
        """
        async with _HyperionSession(self) as session:
            targets = await session.async_resolve_targets(instances)
            states: dict[int, bool] = {}
            changed: list[int] = []
            for target in targets:
                await session.async_switch_to(target)
                enabled = await session.async_led_enabled()
                states[target] = enabled
                if enabled:
                    continue
                await session.async_set_led_enabled(target, True)
                states[target] = True
                changed.append(target)
            return states, changed


class _HyperionSession:
    """One short-lived TCP session: login, switch, read, maybe write."""

    def __init__(self, client: HyperionClient) -> None:
        """Hold the client; connect on __aenter__."""
        self._client = client
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._tan = itertools.count(1)

    async def __aenter__(self) -> _HyperionSession:
        """Open the TCP connection and log in when a token is set."""
        host = self._client.host.strip()
        try:
            async with asyncio.timeout(self._client.request_timeout):
                self._reader, self._writer = await asyncio.open_connection(
                    host, int(self._client.port)
                )
        except (OSError, asyncio.TimeoutError) as err:
            raise HyperionConnectionError(
                f"Could not connect to Hyperion at {host}:{self._client.port}"
            ) from err
        if self._client.token:
            await self.async_login()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        """Close the TCP connection."""
        writer, self._writer = self._writer, None
        self._reader = None
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except (OSError, asyncio.TimeoutError):
                pass

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send one request and wait for the matching (tan) response."""
        assert self._reader is not None and self._writer is not None
        payload = {**payload, "tan": next(self._tan)}
        raw = (json.dumps(payload) + "\n").encode("utf-8")
        try:
            async with asyncio.timeout(self._client.request_timeout):
                self._writer.write(raw)
                await self._writer.drain()
                while True:
                    line = await self._reader.readline()
                    if not line:
                        raise HyperionResponseError(
                            "Hyperion closed the connection"
                        )
                    try:
                        response = json.loads(line.decode("utf-8"))
                    except ValueError:
                        continue  # skip non-JSON noise, keep waiting
                    if not isinstance(response, dict):
                        continue
                    if response.get("tan") != payload["tan"]:
                        continue  # async push for another call, ignore
                    return response
        except (OSError, asyncio.TimeoutError) as err:
            raise HyperionConnectionError(
                f"Lost connection to Hyperion at {self._client.host}"
            ) from err

    @staticmethod
    def _check(response: dict[str, Any], action: str) -> dict[str, Any]:
        """Raise typed errors for success=false responses."""
        if response.get("success"):
            return response
        error = str(response.get("error") or "unknown Hyperion error")
        if "uthoriz" in error.lower():
            raise HyperionAuthError(
                "Hyperion requires API authentication: set a token "
                f"({error})"
            )
        raise HyperionResponseError(f"Hyperion failed to {action}: {error}")

    async def async_login(self) -> None:
        """Log in with the configured API token."""
        response = await self._request(
            {
                "command": "authorize",
                "subcommand": "login",
                "token": self._client.token,
            }
        )
        if not response.get("success"):
            raise HyperionAuthError(
                "Hyperion rejected the API token: "
                f"{response.get('error') or 'login failed'}"
            )

    async def async_switch_to(self, instance: int) -> None:
        """Switch the session to one Hyperion instance."""
        response = await self._request(
            {"command": "instance", "subcommand": "switchTo", "instance": instance}
        )
        if not response.get("success"):
            error = str(response.get("error") or "switch failed")
            if "uthoriz" in error.lower():
                raise HyperionAuthError(
                    "Hyperion requires API authentication: set a token "
                    f"({error})"
                )
            raise HyperionInstanceError(
                f"Cannot use Hyperion instance {instance}: {error}"
            )

    async def async_serverinfo(self) -> dict[str, Any]:
        """Return the serverinfo info dict for the current instance."""
        response = self._check(await self._request({"command": "serverinfo"}), "read state")
        info = response.get("info")
        if not isinstance(info, dict):
            raise HyperionResponseError("Hyperion serverinfo had no info object")
        return info

    async def async_led_enabled(self) -> bool:
        """Return LEDDEVICE enabled state for the current instance."""
        info = await self.async_serverinfo()
        components = info.get("components")
        if not isinstance(components, list):
            raise HyperionResponseError("Hyperion serverinfo had no components list")
        for component in components:
            if isinstance(component, dict) and component.get("name") == LEDDEVICE_COMPONENT:
                return bool(component.get("enabled"))
        raise HyperionResponseError("Hyperion did not report a LEDDEVICE component")

    async def async_running_instances(self) -> list[int]:
        """Return indices of running Hyperion instances."""
        info = await self.async_serverinfo()
        instances = info.get("instance")
        if not isinstance(instances, list):
            return [DEFAULT_HYPERION_INSTANCE]
        running = [
            int(item["instance"])
            for item in instances
            if isinstance(item, dict)
            and item.get("running")
            and isinstance(item.get("instance"), int)
        ]
        return running or [DEFAULT_HYPERION_INSTANCE]

    async def async_resolve_targets(self, instances: list[int]) -> list[int]:
        """Map [] (all) to running instances; validate explicit ones."""
        if instances:
            return list(instances)
        targets = await self.async_running_instances()
        _LOGGER.debug("Hyperion all-instances resolved to %s", targets)
        return targets

    async def async_set_led_enabled(self, instance: int, enabled: bool) -> None:
        """Set LEDDEVICE state for one instance."""
        response = await self._request(
            {
                "command": "componentstate",
                "instance": [instance],
                "componentstate": {"component": LEDDEVICE_COMPONENT, "state": enabled},
            }
        )
        self._check(response, f"set LEDDEVICE to {enabled}")
