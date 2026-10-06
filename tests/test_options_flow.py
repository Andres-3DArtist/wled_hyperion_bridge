"""Regression tests for the options flow HA compatibility.

On HA 2025.12+, OptionsFlow.config_entry is a read-only property that HA
injects. Passing the entry to the constructor (or assigning
self.config_entry) raises AttributeError and the Configure dialog fails
with 500. These tests lock in the supported construction contract.
"""

from __future__ import annotations

import pytest

from custom_components.wled_hyperion_bridge.config_flow import (
    WLEDHyperionBridgeConfigFlow,
    WLEDHyperionBridgeOptionsFlow,
)


class FakeEntry:
    """Minimal config entry double."""

    def __init__(self):
        self.data: dict = {}
        self.options: dict = {}
        self.entry_id = "test-entry"
        self.title = "Test Bridge"


def test_options_flow_defines_no_custom_init() -> None:
    """The flow must rely on HA's injected config_entry property."""
    assert "__init__" not in WLEDHyperionBridgeOptionsFlow.__dict__


def test_options_flow_constructs_without_arguments() -> None:
    """Direct construction takes no entry (as HA instantiates it)."""
    flow = WLEDHyperionBridgeOptionsFlow()

    with pytest.raises(ValueError):
        _ = flow.config_entry


def test_async_get_options_flow_ignores_entry_argument() -> None:
    """The factory must not forward the entry to the constructor."""
    flow = WLEDHyperionBridgeConfigFlow.async_get_options_flow(FakeEntry())  # type: ignore[arg-type]

    assert isinstance(flow, WLEDHyperionBridgeOptionsFlow)


def test_injected_config_entry_is_exposed() -> None:
    """Once HA injects the entry, steps can read it via the property."""
    entry = FakeEntry()
    flow = WLEDHyperionBridgeOptionsFlow()
    flow._config_entry = entry  # what the HA flow manager does internally

    assert flow.config_entry is entry
