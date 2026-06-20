"""Tests for WLED state snapshot helpers."""

from custom_components.wled_hyperion_bridge.snapshot import build_restorable_snapshot


def test_build_restorable_snapshot_keeps_expected_wled_fields() -> None:
    """Snapshot includes brightness, preset, segment colors, effects, and palette."""
    state = {
        "on": True,
        "bri": 128,
        "ps": 7,
        "lor": 0,
        "live": True,
        "mainseg": 0,
        "seg": [
            {
                "id": 0,
                "start": 0,
                "stop": 60,
                "len": 60,
                "col": [[255, 0, 0], [0, 0, 0], [0, 0, 255]],
                "fx": 42,
                "sx": 90,
                "ix": 120,
                "pal": 3,
                "sel": True,
            }
        ],
    }

    snapshot = build_restorable_snapshot(state)

    assert snapshot["on"] is True
    assert snapshot["bri"] == 128
    assert snapshot["ps"] == 7
    assert snapshot["mainseg"] == 0
    assert snapshot["seg"][0]["col"] == [[255, 0, 0], [0, 0, 0], [0, 0, 255]]
    assert snapshot["seg"][0]["fx"] == 42
    assert snapshot["seg"][0]["pal"] == 3
    assert "lor" not in snapshot
    assert "live" not in snapshot
    assert "len" not in snapshot["seg"][0]


def test_build_restorable_snapshot_deep_copies_state() -> None:
    """Snapshot should not mutate when source state changes later."""
    state = {
        "bri": 10,
        "seg": [{"id": 0, "col": [[1, 2, 3]], "fx": 0, "pal": 0}],
    }

    snapshot = build_restorable_snapshot(state)
    state["seg"][0]["col"][0][0] = 255

    assert snapshot["seg"][0]["col"][0][0] == 1
