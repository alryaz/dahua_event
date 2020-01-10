"""
Attach event listener to Dahua devices
Borrowed code from https://github.com/johnnyletrois/dahua-watch

Author: Akram
"""
import re
import threading, logging, os, socket, time

import asyncio
from typing import Union, Optional

import voluptuous as vol
from datetime import timedelta
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
import requests
import http.client
from base64 import b64encode

import homeassistant.util.dt as dt_util
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP,
    CONF_NAME,
    CONF_SSL,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_AUTHENTICATION,
)

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'dahua_event'

URL_TEMPLATE = "/cgi-bin/eventManager.cgi?action=attach&channel={channel}&codes=%5B{events}%5D"
URL_TITLES = "/cgi-bin/configManager.cgi?action=getConfig&name=ChannelTitle"

CONF_CHANNELS = "channels"
CONF_EVENTS = "events"
CONF_NUMBER = "number"

AUTH_METHOD_BASIC = "basic"
AUTH_METHOD_DIGEST = "digest"

DEFAULT_SSL = False
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"
DEFAULT_PORT = 80
DEFAULT_AUTHENTICATION = AUTH_METHOD_DIGEST
DEFAULT_EVENTS = ['VideoMotion', 'CrossLineDetection', 'AlarmLocal', 'VideoLoss', 'VideoBlind']
#DEFAULT_EVENTS = ['All']

CHANNEL_SCHEMA = vol.Schema({
    vol.Required(CONF_NUMBER): int,
    vol.Optional(CONF_NAME): cv.string,
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN:
        vol.All(cv.ensure_list, [vol.Schema({
            vol.Optional(CONF_NAME): cv.string,
            vol.Optional(CONF_SSL, default=DEFAULT_SSL): cv.boolean,
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


def create_threads(hass, config):
    threads = [
        DahuaDevice(
            hass=hass,
            name=device_cfg.get(CONF_NAME),
            host=device_cfg.get(CONF_HOST),
            port=device_cfg.get(CONF_PORT),
            username=device_cfg.get(CONF_USERNAME),
            password=device_cfg.get(CONF_PASSWORD),
            channels=device_cfg.get(CONF_CHANNELS),
            monitored_events=device_cfg.get(CONF_EVENTS),
            use_ssl=device_cfg.get(CONF_SSL),
            auth_method=device_cfg.get(CONF_AUTHENTICATION),
            #channel=channel[CONF_NUMBER]
        )
        for device_cfg in config #for channel in device_cfg.get(CONF_CHANNELS)
    ]

    #for device in threads:
    #    print(device.name, device.get_titles())

    def _start_dahua_event(*_):
        for thread in threads:
            thread.start()

    def _stop_dahua_event(*_):
        for thread in threads:
            thread.stopped.set()

    return _start_dahua_event, _stop_dahua_event


def setup(hass, config):
    """Set up Dahua event listener."""

    conf = config.get(DOMAIN)

    _start_dahua_event, _stop_dahua_event = create_threads(hass, conf)

    hass.bus.listen_once(
        EVENT_HOMEASSISTANT_START,
        _start_dahua_event
    )
    hass.bus.listen_once(
        EVENT_HOMEASSISTANT_STOP,
        _stop_dahua_event
    )

    return True


class DahuaDevice(threading.Thread):
    def __init__(self,
                 hass, name,
                 host, port,
                 username, password,
                 channels,
                 monitored_events=None, use_ssl=DEFAULT_SSL,
                 auth_method=AUTH_METHOD_BASIC, channel=1):
        super().__init__()

        if monitored_events is None:
            monitored_events = DEFAULT_EVENTS

        self.hass = hass

        self.name = name
        self.channel = channel
        self.channels = channels
        self.monitored_events = monitored_events

        self.use_ssl = use_ssl
        self.host = host
        self.port = port

        self.__username = username
        self.__password = password
        self.auth_method = auth_method

        self.stopped = threading.Event()

    def on_connect(self):
        _LOGGER.debug("[{0}] on_connect()".format(self.name))

    def on_disconnect(self, reason):
        _LOGGER.debug("[{0}] on_disconnect({1})".format(self.name, reason))

    def on_receive(self, data):
        data = data.decode("utf-8", errors="ignore")
        _LOGGER.debug("[{0}]: {1}".format(self.name, data))

        for line in data.split("\r\n"):
            if line == "HTTP/1.1 200 OK":
                self.on_connect()

            if not line.startswith("Code="):
                continue

            alarm = dict()
            alarm["name"] = self.name
            for KeyValue in line.split(';'):
                key, value = KeyValue.split('=')
                alarm[key] = value

            if alarm["index"] in self.channels:
                alarm["channel"] = self.channels[alarm["index"]]

            self.hass.bus.fire("dahua_event_received", alarm)

    @property
    def authenticator(self) -> Union[HTTPDigestAuth, HTTPBasicAuth]:
        return (HTTPDigestAuth(self.__username, self.__password)
                if self.auth_method == AUTH_METHOD_DIGEST
                else HTTPBasicAuth(self.__username, self.__password))

    def create_request_via_requests(self, event_url):
        protocol = 'https' if self.use_ssl else 'http'
        event_url = f'{protocol}://{self.host}:{self.port}{event_url}'

        resp = requests.get(
            url=event_url,
            auth=self.authenticator,
            timeout=30,
            stream=True
        )
        return resp

    def create_request_via_httplib(self, event_url):
        if self.use_ssl:
            conn = http.client.HTTPSConnection(
                host=self.host,
                port=self.port,
                timeout=30
            )
        else:
            conn = http.client.HTTPConnection(
                host=self.host,
                port=self.port,
                timeout=30
            )

        conn.set_debuglevel(1)
        conn.connect()
        conn.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        conn.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
        conn.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 15)

        pair = f'{self.__username}:{self.__password}'.encode()
        conn.request("GET", event_url, None, {
            'Authorization': 'Basic ' + b64encode(pair).decode('utf-8')
        })
        try:
            resp = conn.getresponse()
            return resp
        except socket.timeout:
            _LOGGER.debug('Socket timeout')
            return None

    def get_titles(self):
        if self.use_httplib:
            resp = self.create_request_via_httplib(URL_TITLES)
            data = resp.read().decode('utf-8')
        else:
            data = self.create_request_via_requests(URL_TITLES)

        if not data:
            return None

        res = re.findall(r'table\.ChannelTitle\[(\d+)\]\.Name=([^\r\n]+)', data)

        if not res:
            return None

        return {} if not res else {
            int(match[0]): match[1]
            for match in res
        }

    def run(self):
        """Fetch events"""
        while not self.stopped.isSet():
            # Sleeps to ease load on processor

            event_url = URL_TEMPLATE.format(channel=self.channel, events=','.join(self.monitored_events))

            resp = self.create_request_via_httplib(event_url)

            boundary_prefix_length = len('-- myboundary\r\nContent-Type: text/plain\r\nContent-Length:')
            while True:
                prefix = resp.read(boundary_prefix_length)
                _LOGGER.debug('Reading prefix length: %d, content: %s' % (boundary_prefix_length, prefix))
                content_length = bytes()
                while True:
                    read_char = resp.read(1)
                    if read_char == b'\r':
                        break
                    content_length += read_char
                content_length = int(content_length.decode('utf-8'))
                resp.read(1)  # dump b'\n'
                content = resp.read(content_length)
                _LOGGER.debug('Read content: %s' % content)
                self.on_receive(content.decode('utf-8'))
                resp.read(4)  # dump b'\r\n\r\n'
