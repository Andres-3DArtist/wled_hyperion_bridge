"""WLED state snapshot helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .const import RESTORABLE_SEGMENT_KEYS, RESTORABLE_STATE_KEYS


def build_restorable_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    """Build a compact state object safe to POST back to /json/state."""
    snapshot: dict[str, Any] = {}

    for key in RESTORABLE_STATE_KEYS:
        if key not in state:
            continue
        if key == "seg" and isinstance(state[key], list):
            snapshot[key] = [_clean_segment(segment) for segment in state[key]]
            continue
        snapshot[key] = deepcopy(state[key])

    return snapshot


def _clean_segment(segment: Any) -> Any:
    """Keep documented mutable segment state fields."""
    if not isinstance(segment, dict):
        return deepcopy(segment)
    return {
        key: deepcopy(value)
        for key, value in segment.items()
        if key in RESTORABLE_SEGMENT_KEYS
    }
