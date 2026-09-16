"""Constants for the KampKlar integration."""

from datetime import timedelta

DOMAIN = "kampklar"

CONF_PERSONS = "persons"
CONF_PERSON_ID = "person_id"
CONF_PERSON_NAME = "name"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_START_AT_MEETING_TIME = "start_at_meeting_time"
DEFAULT_START_AT_MEETING_TIME = False

# Activity type IDs (typeId in the DBU feed)
ACTIVITY_TYPE_TRAINING = 1
ACTIVITY_TYPE_MATCH = 2
ACTIVITY_TYPE_TOURNAMENT = 4
ACTIVITY_TYPE_PRACTICE_MATCH = 5
ACTIVITY_TYPE_DBU_TOURNAMENT = 7

# Sign-up status IDs, from the app's SignUpStatusKind enum.
# The live feed uses null for "not answered", 1 Frameldt, 2 Tilmeldt.
SIGNUP_NOT_RESPONDED = 0  # Undefined; real "not answered" is null
SIGNUP_SIGNED_OFF = 1  # Unsubscribed / Frameldt
SIGNUP_SIGNED_UP = 2  # Subscribed / Tilmeldt
SIGNUP_AVAILABLE = 3  # Til raadighed
SIGNUP_SELECTED = 4  # Udtaget
SIGNUP_SELECTED_CONFIRMED = 5  # Udtaget, bekraeftet
SIGNUP_SELECTED_NOT_CONFIRMED = 6  # Udtaget, ikke bekraeftet
SIGNUP_TEAM_SIGN_ON = 7  # Holdtilmelding

SIGNUP_STATUS_NAMES = {
    1: "Frameldt",
    2: "Tilmeldt",
    3: "Til raadighed",
    4: "Udtaget",
    5: "Udtaget (bekraeftet)",
    6: "Udtaget (ikke bekraeftet)",
    7: "Holdtilmelding",
}

# "Udtaget" = the child has been selected/called up for a match.
UDTAGET_STATUS_IDS = frozenset({4, 5, 6})

DEFAULT_SCAN_INTERVAL = 300  # seconds
MIN_SCAN_INTERVAL = 60
MAX_SCAN_INTERVAL = 3600

# Live match handling
LIVE_SCAN_INTERVAL = timedelta(seconds=60)
MATCH_WINDOW_BEFORE = timedelta(hours=2)
MATCH_WINDOW_AFTER = timedelta(hours=3)

# Match venue lookups (Match/GetMatch), cached per match and stored across restarts
VENUE_STORE_VERSION = 1
VENUE_MAX_AGE = timedelta(days=7)
VENUE_RETRY_MIN = timedelta(minutes=15)  # first retry after a failed lookup, doubling per failure
VENUE_RETRY_MAX = timedelta(hours=24)
VENUE_LOOKUP_TIMEOUT = 10  # seconds for one lookup; the shared HA session has no timeout of its own
VENUE_LOOKUPS_PER_REFRESH = 10  # run together, nearest matches first; the rest wait for the next refresh

# Service names
SERVICE_SIGN_UP = "tilmeld"
SERVICE_SIGN_OFF = "afmeld"
ATTR_ACTIVITY_ID = "activity_id"


def is_udtaget(status_id: int | None) -> bool:
    """Return True when the sign-up status means the person is selected for a match."""
    return status_id in UDTAGET_STATUS_IDS
