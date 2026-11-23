"""Constants of the Orgaia integration."""

from __future__ import annotations

DOMAIN = "orgaia"
NAME = "Orgaia"
VERSION = "0.12.0"

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
# Options: the person in whose name a voice assistant (which knows no user) puts articles on a shopping list.
CONF_VOICE_PERSON = "voice_person"
# Options: the lists that become to-do lists (none chosen: all), whether people get devices of their own,
# and how many days ticked-off tasks stay in the to-do lists.
CONF_LISTS = "lists"
CONF_PERSON_DEVICES = "person_devices"
CONF_COMPLETED_DAYS = "completed_days"
# Options: whether the ready-made dashboard of the group stands in the sidebar. New setups offer it;
# groups connected before are asked in the settings, so that nothing appears by itself after an update.
CONF_DASHBOARD = "dashboard"

# Fired on the event bus for automations; also offered as device triggers on the group's device.
EVENT_ORGAIA = "orgaia_event"

# Where Home Assistant serves the Orgaia card to dashboards.
CARD_URL = "/orgaia/orgaia-card.js"
