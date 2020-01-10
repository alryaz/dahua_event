"""
Attach event listener to Dahua devices
Borrowed code from https://github.com/johnnyletrois/dahua-watch

Author: Akram
"""
import threading, logging, os, socket, time

import asyncio
import voluptuous as vol
from datetime import timedelta
import pycurl
import requests_async

import homeassistant.util.dt as dt_util
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP,
    CONF_NAME,
    CONF_PROTOCOL,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_AUTHENTICATION,
)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

DOMAIN = 'dahua_event'

URL_TEMPLATE = "{protocol}://{host}:{port}/cgi-bin/eventManager.cgi?action=attach&channel=1&codes=%5B{events}%5D"

CONF_CHANNELS = "channels"
CONF_EVENTS = "events"
CONF_NUMBER = "number"

AUTH_METHOD_BASIC = "basic"
AUTH_METHOD_DIGEST = "digest"

DEFAULT_PROTOCOL = "http"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_PORT = 80
DEFAULT_AUTHENTICATION = AUTH_METHOD_DIGEST
DEFAULT_EVENTS = ['VideoMotion', 'CrossLineDetection', 'AlarmLocal', 'VideoLoss', 'VideoBlind']

CHANNEL_SCHEMA = vol.Schema({
    vol.Required(CONF_NUMBER): int,
    vol.Optional(CONF_NAME): cv.string,
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN:
        vol.All(cv.ensure_list, [vol.Schema({
            vol.Optional(CONF_NAME): cv.string,
            vol.Optional(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): cv.string,
            vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): cv.string,
            vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): cv.string,
            vol.Optional(CONF_AUTHENTICATION, default=DEFAULT_AUTHENTICATION): vol.In([
                AUTH_METHOD_BASIC,
                AUTH_METHOD_DIGEST
            ]),
            vol.Required(CONF_HOST): cv.string,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Optional(CONF_CHANNELS, default=1): vol.All(cv.ensure_list, [vol.Any(
                CHANNEL_SCHEMA,
                lambda x: CHANNEL_SCHEMA({
                    CONF_NUMBER: x,
                    CONF_NAME: f'Channel {x}'
                }) if isinstance(x, int) else vol.Invalid('')
            )]),
            vol.Optional(CONF_EVENTS, default=DEFAULT_EVENTS): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional(CONF_SCAN_INTERVAL, default=timedelta): cv.time_period,
        })])
}, extra=vol.ALLOW_EXTRA)


def setup(hass, config):
    """Set up Dahua event listener."""
    config = config.get(DOMAIN)

    dahua_event = DahuaEventThread(
        hass,
        config
    )

    def _start_dahua_event(_event):
        dahua_event.start()

    def _stop_dahua_event(_event):
        dahua_event.stopped.set()

    hass.bus.listen_once(
        EVENT_HOMEASSISTANT_START,
        _start_dahua_event
    )
    hass.bus.listen_once(
        EVENT_HOMEASSISTANT_STOP,
        _stop_dahua_event
    )

    return True


class DahuaDevice:
    def __init__(self, hass, name, url, channels):
        self.hass = hass
        self.Name = name
        self.Url = url
        self.Channels = channels
        self.CurlObj = None
        self.Connected = None
        self.reconnect = None

    def on_connect(self):
        _LOGGER.debug("[{0}] on_connect()".format(self.Name))
        self.Connected = True

    def on_disconnect(self, reason):
        _LOGGER.debug("[{0}] on_disconnect({1})".format(self.Name, reason))
        self.Connected = False

    def on_receive(self, data):
        data = data.decode("utf-8", errors="ignore")
        _LOGGER.debug("[{0}]: {1}".format(self.Name, data))

        for line in data.split("\r\n"):
            if line == "HTTP/1.1 200 OK":
                self.on_connect()

            if not line.startswith("Code="):
                continue

            alarm = dict()
            alarm["name"] = self.Name
            for KeyValue in line.split(';'):
                key, value = KeyValue.split('=')
                alarm[key] = value

            if alarm["index"] in self.Channels:
                alarm["channel"] = self.Channels[alarm["index"]]

            self.hass.bus.fire("dahua_event_received", alarm)


class DahuaEventThread(threading.Thread):
    """Connects to device and subscribes to events"""
    Devices = []
    NumActivePlayers = 0

    CurlMultiObj = pycurl.CurlMulti()
    NumCurlObjs = 0

    def __init__(self, hass, config):
        """Construct a thread listening for events."""
        self.hass = hass

        for device_cfg in config:
            url = URL_TEMPLATE.format(
                protocol=device_cfg.get(CONF_PROTOCOL),
                host=device_cfg.get(CONF_HOST),
                port=device_cfg.get(CONF_PORT),
                events=','.join(device_cfg.get(CONF_EVENTS))
            )
            channels = device_cfg.get(CONF_CHANNELS)
            channels_dict = {}
            if channels is not None:
                for channel in channels:
                    channels_dict[channel.get("number")] = channel.get("name")

            device = DahuaDevice(hass, device_cfg.get(CONF_NAME), url, channels_dict)
            self.Devices.append(device)

            curl_obj = pycurl.Curl()
            device.CurlObj = curl_obj

            curl_obj.setopt(pycurl.URL, url)
            curl_obj.setopt(pycurl.CONNECTTIMEOUT, 30)
            curl_obj.setopt(pycurl.TCP_KEEPALIVE, 1)
            curl_obj.setopt(pycurl.TCP_KEEPIDLE, 30)
            curl_obj.setopt(pycurl.TCP_KEEPINTVL, 15)
            curl_obj.setopt(pycurl.HTTPAUTH, pycurl.HTTPAUTH_DIGEST)
            curl_obj.setopt(pycurl.USERPWD, "%s:%s" % (device_cfg.get(CONF_USERNAME), device_cfg.get(CONF_PASSWORD)))
            curl_obj.setopt(pycurl.WRITEFUNCTION, device.on_receive)

            self.CurlMultiObj.add_handle(curl_obj)
            self.NumCurlObjs += 1

            _LOGGER.debug("Added Dahua device at: %s", url)

        threading.Thread.__init__(self)
        self.stopped = threading.Event()

    def run(self):
        """Fetch events"""
        while 1:
            ret, num_handles = self.CurlMultiObj.perform()
            if ret != pycurl.E_CALL_MULTI_PERFORM:
                break

        ret = self.CurlMultiObj.select(1.0)
        while not self.stopped.isSet():
            # Sleeps to ease load on processor
            time.sleep(.05)
            ret, num_handles = self.CurlMultiObj.perform()

            if num_handles != self.NumCurlObjs:
                _, success, error = self.CurlMultiObj.info_read()

                for CurlObj in success:
                    dahua_device = next(filter(lambda x: x.CurlObj == CurlObj, self.Devices))
                    if dahua_device.reconnect:
                        continue

                    dahua_device.on_disconnect("success")
                    dahua_device.reconnect = time.time() + 5

                for CurlObj, ErrorNo, ErrorStr in error:
                    dahua_device = next(filter(lambda x: x.CurlObj == CurlObj, self.Devices))
                    if dahua_device.reconnect:
                        continue

                    dahua_device.on_disconnect("{0} ({1})".format(ErrorStr, ErrorNo))
                    dahua_device.reconnect = time.time() + 5

                for dahua_device in self.Devices:
                    if dahua_device.reconnect and dahua_device.reconnect < time.time():
                        self.CurlMultiObj.remove_handle(dahua_device.CurlObj)
                        self.CurlMultiObj.add_handle(dahua_device.CurlObj)
                        dahua_device.reconnect = None
            # if ret != pycurl.E_CALL_MULTI_PERFORM: break
