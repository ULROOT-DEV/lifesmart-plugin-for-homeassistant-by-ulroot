"""Integration constants, without credentials or installation-specific values."""

DOMAIN = "lifesmart_ulroot"
NAME = "LifeSmart by ULROOT"
VERSION = "0.3.2"
ACTIVATION_EMAIL = "ss.kim@ulroot.com"
PLATFORMS = [
    "sensor",
    "binary_sensor",
    "switch",
    "light",
    "cover",
    "climate",
    "fan",
    "siren",
    "scene",
    "remote",
]
DEFAULT_CLOUD_URL = "https://api.us.ilifesmart.com/app/"
DEFAULT_LOCAL_PORT = 8008
REQUEST_TIMEOUT = 10
MAX_RESPONSE = 4 * 1024 * 1024
POLL_CLOUD = 60
POLL_LOCAL = 30
POLL_PUSH = 300
