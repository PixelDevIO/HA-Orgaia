"""Constants of the Orgaia integration."""

from __future__ import annotations

DOMAIN = "orgaia"
NAME = "Orgaia"
VERSION = "0.5.0"

CONF_LINK = "link"
CONF_NAME = "name"
CONF_SEED = "seed"
CONF_SERVER = "server"
CONF_SPACE = "space"
CONF_DEVICE = "device"
CONF_NODE = "node"
CONF_JOIN = "join"

DEFAULT_MEMBER_NAME = "Home Assistant"
STORAGE_VERSION = 1

# How long the setup waits for an admin to confirm in the app, and how often it asks.
JOIN_WAIT_SECONDS = 600
JOIN_POLL_SECONDS = 2

# Completed to-dos stay in the list for this long, so shopping lists do not fill up with old ticks.
COMPLETED_DAYS = 14
# Attributes list at most this many titles.
MAX_TITLES = 20

# Options: Orgaia person id -> Home Assistant person entity.
CONF_PERSONS = "persons"

# Fired on the event bus for automations; also offered as device triggers on the group's device.
EVENT_ORGAIA = "orgaia_event"
