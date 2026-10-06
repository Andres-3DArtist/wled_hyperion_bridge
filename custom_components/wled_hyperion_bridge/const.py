"""Constants for WLED Hyperion Bridge."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "wled_hyperion_bridge"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_DEVICES = "devices"
CONF_AREA_ID = "area_id"
CONF_BRIDGE_NAME = "bridge_name"
CONF_DEVICE_NAME = "device_name"
CONF_ACTION = "action"
CONF_REMOVE_IDS = "remove_ids"

CONF_HYPERION = "hyperion"
CONF_HYPERION_HOST = "host"
CONF_HYPERION_PORT = "port"
CONF_HYPERION_TOKEN = "token"
CONF_HYPERION_ALL_INSTANCES = "all_instances"
CONF_HYPERION_INSTANCE = "instance"

DEFAULT_PORT = 80
DEFAULT_HYPERION_PORT = 19444
DEFAULT_HYPERION_INSTANCE = 0
MAX_HYPERION_INSTANCE = 254
DEFAULT_NAME = "Hyperion Bridge"

PLATFORMS = ("switch",)
SCAN_INTERVAL = timedelta(seconds=30)

STORAGE_VERSION = 1
STORAGE_KEY_TEMPLATE = f"{DOMAIN}.{{entry_id}}"

LIVE_OVERRIDE_OFF = 0
LIVE_OVERRIDE_UNTIL_REBOOT = 2

RESTORABLE_STATE_KEYS = {
    "on",
    "bri",
    "transition",
    "ps",
    "pl",
    "nl",
    "mainseg",
    "seg",
}

RESTORABLE_SEGMENT_KEYS = {
    "id",
    "start",
    "stop",
    "startY",
    "stopY",
    "grp",
    "spc",
    "of",
    "on",
    "bri",
    "col",
    "fx",
    "sx",
    "ix",
    "c1",
    "c2",
    "c3",
    "o1",
    "o2",
    "o3",
    "pal",
    "sel",
    "rev",
    "rY",
    "mi",
    "mY",
    "tp",
    "cct",
}
