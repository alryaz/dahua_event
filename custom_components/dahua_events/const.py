"""Constants for dahua_events component."""
from typing import List

DOMAIN = 'dahua_events'
DATA_CONFIGS = DOMAIN + '_configs'

URL_EVENT_MANAGER = "/cgi-bin/eventManager.cgi?action="
URL_MAGIC_BOX = "/cgi-bin/magicBox.cgi?action="
URL_CONFIG_MANAGER = "/cgi-bin/configManager.cgi?action=getConfig&name="

URL_TEMPLATE = URL_EVENT_MANAGER + "attach&channel={channel}&codes=%5B{events}%5D"
URL_TITLES = URL_CONFIG_MANAGER + "ChannelTitle"
URL_SERIAL = URL_MAGIC_BOX + "getSerialNo"
URL_SOFTWARE = URL_MAGIC_BOX + "getSoftwareVersion"
URL_NETWORKS = URL_CONFIG_MANAGER + "Network"

CONF_NUMBER_OFFSET = "number_offset"
CONF_CHANNELS = "channels"
CONF_EVENTS = "events"
CONF_NUMBER = "number"
CONF_ALARM_CHANNEL = "alarm_channel"

AUTH_METHOD_BASIC = "basic"
AUTH_METHOD_DIGEST = "digest"

AUTH_METHODS: List[str] = [AUTH_METHOD_BASIC, AUTH_METHOD_DIGEST]

DEFAULT_NAME = "Dahua Device {host}:{port}"
DEFAULT_SSL = False
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_PORT = 80
DEFAULT_AUTHENTICATION = AUTH_METHOD_BASIC
DEFAULT_EVENTS = ['VideoMotion', 'CrossLineDetection', 'AlarmLocal', 'VideoLoss', 'VideoBlind']
DEFAULT_ALARM_CHANNEL = 1
DEFAULT_NUMBER_OFFSET = 1
#DEFAULT_EVENTS = ['All']

ATTR_CHANNEL_NAME_FORMAT = "channel_{channel}_name"
ATTR_CHANNEL_TRIGGERED_FORMAT = "channel_{channel}_triggered"
ATTR_CHANNEL_LAST_EVENT_FORMAT = "channel_{channel}_last_event"
ATTR_SW_VERSION = "software_version"
ATTR_WEB_VERSION = "web_version"

PROP_EVENT = "event"
PROP_ACTION = "action"
PROP_CHANNEL = "channel"
PROP_NAME = "name"
PROP_INDEX = "index"

EVENT_RECEIVED_NAME = "dahua_event_received"
