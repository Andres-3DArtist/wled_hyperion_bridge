"""Tests for the bridge coordinator sync logic."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.wled_hyperion_bridge.api import WLEDConnectionError
from custom_components.wled_hyperion_bridge.coordinator import (
    WLEDHyperionBridgeCoordinator,
)


class FakeClient:
    """Minimal WLED client double."""

    def __init__(self, state: dict[str, Any] | Exception):
        self._state = state
        self.get_calls = 0
        self.posts: list[dict[str, Any]] = []
        self.fail_on_post = False

    async def async_get_state(self) -> dict[str, Any]:
        self.get_calls += 1
        if isinstance(self._state, Exception):
            raise self._state
        return dict(self._state)

    async def async_set_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.posts.append(dict(payload))
        if self.fail_on_post:
            raise WLEDConnectionError("boom")
        if isinstance(self._state, dict):
            self._state = {**self._state, **payload}
        return {"success": True}


class FakeStore:
    """In-memory Store double."""

    def __init__(self, initial: Any = None):
        self.data = initial

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data

    async def async_remove(self):
        self.data = None


class FakeHyperion:
    """Minimal Hyperion client double."""

    def __init__(
        self,
        led: dict[int, bool] | None = None,
        error: Exception | None = None,
    ):
        """Configure LEDDEVICE state or a failure to raise."""
        self.led = dict(led if led is not None else {0: True})
        self.error = error
        self.ensure_calls: list[list[int]] = []
        self.read_calls: list[list[int]] = []

    async def async_read_led_state(self, instances: list[int]) -> dict[int, bool]:
        self.read_calls.append(list(instances))
        if self.error is not None:
            raise self.error
        targets = instances or sorted(self.led)
        return {idx: self.led[idx] for idx in targets}

    async def async_ensure_led_enabled(
        self, instances: list[int]
    ) -> tuple[dict[int, bool], list[int]]:
        self.ensure_calls.append(list(instances))
        if self.error is not None:
            raise self.error
        targets = instances or sorted(self.led)
        states = {idx: self.led.get(idx, False) for idx in targets}
        changed = [idx for idx in targets if not states[idx]]
        for idx in changed:
            self.led[idx] = True
            states[idx] = True
        return states, changed


def _devices() -> list[dict[str, Any]]:
    return [
        {"id": "a:80", "name": "A", "host": "a", "port": 80},
        {"id": "b:80", "name": "B", "host": "b", "port": 80},
    ]


def _coordinator(clients, store=None, devices=None, hyperion=None, hyperion_config=None):
    return WLEDHyperionBridgeCoordinator(
        hass=object(),
        clients=clients,
        devices=devices if devices is not None else _devices(),
        store=store if store is not None else FakeStore(),
        name="Test",
        update_interval=None,
        hyperion=hyperion,
        hyperion_config=hyperion_config,
    )


def _hyperion_config(instances=None):
    return {
        "host": "hyperion",
        "port": 19444,
        "token": None,
        "all_instances": False,
        "instance": 0,
        "instances": [0] if instances is None else instances,
    }


async def test_enable_saves_snapshot_and_posts_lor_zero() -> None:
    clients = [
        FakeClient({"on": True, "bri": 100, "lor": 2, "live": False, "ps": 3}),
        FakeClient({"on": True, "bri": 50, "lor": 2, "live": False}),
    ]
    store = FakeStore()
    coord = _coordinator(clients, store=store)

    await coord.async_set_sync_enabled(True)

    assert coord.sync_enabled is True
    assert set(coord.saved_snapshots) == {"a:80", "b:80"}
    assert coord.saved_snapshots["a:80"]["bri"] == 100
    assert "lor" not in coord.saved_snapshots["a:80"]
    assert "live" not in coord.saved_snapshots["a:80"]
    assert clients[0].posts == [{"lor": 0}]
    assert store.data["sync_enabled"] is True


async def test_double_enable_does_not_overwrite_snapshot() -> None:
    clients = [FakeClient({"on": True, "bri": 100, "lor": 2})]
    coord = _coordinator(
        clients, devices=[{"id": "a:80", "name": "A", "host": "a", "port": 80}]
    )

    await coord.async_set_sync_enabled(True)
    clients[0]._state = {"on": False, "bri": 1, "lor": 0, "live": True}
    saved_before = dict(coord.saved_snapshots["a:80"])
    gets_after_first = clients[0].get_calls
    await coord.async_set_sync_enabled(True)

    # Second enable must not re-read into a new snapshot: only the post-heal
    # plus the trailing refresh should hit the device (2 calls... refresh=1,
    # no re-read). Snapshot content is unchanged.
    assert coord.saved_snapshots["a:80"] == saved_before
    assert coord.saved_snapshots["a:80"]["bri"] == 100
    assert clients[0].posts == [{"lor": 0}, {"lor": 0}]
    assert clients[0].get_calls == gets_after_first + 1


async def test_disable_restores_snapshot() -> None:
    clients = [
        FakeClient({"on": True, "bri": 100, "lor": 2}),
        FakeClient({"on": True, "bri": 50, "lor": 2}),
    ]
    coord = _coordinator(clients)

    await coord.async_set_sync_enabled(True)
    # Simulate live WLED state during sync; restore must use the snapshot.
    clients[0]._state = {"on": True, "bri": 5, "lor": 0, "live": True}
    await coord.async_set_sync_enabled(False)

    assert coord.sync_enabled is False
    assert coord.saved_snapshots == {}
    assert clients[0].posts[1] == {"lor": 2, "live": False}
    assert clients[0].posts[2] == {"bri": 100, "on": True}
    assert clients[1].posts[2] == {"bri": 50, "on": True}


async def test_disable_without_snapshot_only_exits_live() -> None:
    clients = [FakeClient({"lor": 0, "live": True})]
    coord = _coordinator(
        clients, devices=[{"id": "a:80", "name": "A", "host": "a", "port": 80}]
    )

    await coord.async_set_sync_enabled(False)

    assert clients[0].posts == [{"lor": 2, "live": False}]


async def test_poll_partial_failure_keeps_bridge_available() -> None:
    clients = [
        FakeClient({"lor": 0, "bri": 10}),
        FakeClient(WLEDConnectionError("down")),
    ]
    coord = _coordinator(clients)

    data = await coord._async_update_data()

    assert set(data) == {"a:80"}
    assert "b:80" in coord.unreachable
    assert "down" in coord.unreachable["b:80"]
    # Sync state is owned by snapshots; a plain poll must not flip the switch.
    assert coord.sync_enabled is False


async def test_poll_all_fail_raises() -> None:
    from homeassistant.helpers.update_coordinator import UpdateFailed

    clients = [
        FakeClient(WLEDConnectionError("down")),
        FakeClient(WLEDConnectionError("down")),
    ]
    coord = _coordinator(clients)

    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


async def test_enable_read_failure_raises_and_keeps_sync_off() -> None:
    from homeassistant.exceptions import HomeAssistantError

    clients = [FakeClient(WLEDConnectionError("down"))]
    coord = _coordinator(
        clients, devices=[{"id": "a:80", "name": "A", "host": "a", "port": 80}]
    )

    with pytest.raises(HomeAssistantError):
        await coord.async_set_sync_enabled(True)

    assert coord.sync_enabled is False
    assert coord.saved_snapshots == {}


async def test_concurrent_toggle_is_serialized() -> None:
    import asyncio

    clients = [FakeClient({"on": True, "bri": 100, "lor": 2})]
    coord = _coordinator(
        clients, devices=[{"id": "a:80", "name": "A", "host": "a", "port": 80}]
    )

    await asyncio.gather(
        coord.async_set_sync_enabled(True),
        coord.async_set_sync_enabled(True),
    )

    # One snapshot read plus one trailing refresh per toggle.
    assert clients[0].get_calls == 3
    assert coord.sync_enabled is True
    assert coord.saved_snapshots["a:80"]["bri"] == 100


async def test_enable_ensures_hyperion_output() -> None:
    """Bridge ON enables Hyperion LED output for its instances."""
    clients = [FakeClient({"on": True, "bri": 100, "lor": 2})]
    hyperion = FakeHyperion(led={0: False})
    coord = _coordinator(
        clients,
        devices=[{"id": "a:80", "name": "A", "host": "a", "port": 80}],
        hyperion=hyperion,
        hyperion_config=_hyperion_config(),
    )

    await coord.async_set_sync_enabled(True)

    assert coord.sync_enabled is True
    assert hyperion.ensure_calls == [[0]]
    assert hyperion.led == {0: True}
    assert coord.hyperion_state["reachable"] is True
    assert coord.hyperion_state["led"] == {0: True}
    # Single Hyperion session: only the trailing refresh re-reads.
    assert len(hyperion.read_calls) == 1
    assert getattr(coord, "listener_updates", 0) >= 1


async def test_enable_fails_when_hyperion_down() -> None:
    """A dead Hyperion fails the toggle loudly instead of silent darkness."""
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.wled_hyperion_bridge.hyperion import (
        HyperionConnectionError,
    )

    clients = [FakeClient({"on": True, "bri": 100, "lor": 2})]
    hyperion = FakeHyperion(error=HyperionConnectionError("down"))
    coord = _coordinator(
        clients,
        devices=[{"id": "a:80", "name": "A", "host": "a", "port": 80}],
        hyperion=hyperion,
        hyperion_config=_hyperion_config(),
    )

    with pytest.raises(HomeAssistantError, match="Hyperion"):
        await coord.async_set_sync_enabled(True)

    assert coord.sync_enabled is False
    assert coord.hyperion_state["reachable"] is False
    # WLED side was already applied before Hyperion failed.
    assert clients[0].posts == [{"lor": 0}]
    assert getattr(coord, "listener_updates", 0) >= 2


async def test_poll_tracks_hyperion_but_survives_it() -> None:
    """Hyperion poll updates state; its failure never fails the refresh."""
    from custom_components.wled_hyperion_bridge.hyperion import (
        HyperionConnectionError,
    )

    clients = [FakeClient({"lor": 0, "bri": 10})]
    hyperion = FakeHyperion(led={0: True})
    coord = _coordinator(
        clients,
        devices=[{"id": "a:80", "name": "A", "host": "a", "port": 80}],
        hyperion=hyperion,
        hyperion_config=_hyperion_config(),
    )

    await coord._async_update_data()
    assert coord.hyperion_state["reachable"] is True
    assert coord.hyperion_state["led"] == {0: True}

    hyperion.error = HyperionConnectionError("down")
    await coord._async_update_data()
    assert coord.hyperion_state["reachable"] is False
