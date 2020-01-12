"""Dahua device specification for Dahua package"""
__all__ = [
    'Device',
    'EventsListener'
]

import logging
import re
import threading
import urllib.request
from urllib.error import URLError, HTTPError
from base64 import b64encode
from datetime import datetime
from typing import Optional, List, Any, Dict, Callable
from urllib.parse import urlencode, quote as urlquote
from socket import timeout as socket_timeout_exception

import asyncio
from homeassistant.util import aiohttp

from .channel import Channel
from .const import CGI_CONFIG, CGI_MAGIC, CGI_EVENTS
from .helpers import gather_dict, str_value_to_type, dict_from_dotted_str
from .exceptions import UnauthorizedException, ProtocolException

_LOGGER = logging.getLogger(__name__)


class Device:
    def __init__(self,
                 host: str, port: int,
                 username: str, password: str,
                 use_ssl=False,
                 use_digest_auth=False,
                 channel_number_offset=1) -> None:
        super().__init__()

        # Device-specific config
        self.stream_port = 554
        self.channel_number_offset = channel_number_offset
        self.use_ssl = use_ssl
        self.host = host
        self.port = port
        self.__username = username
        self.__password = password
        self.__auth_basic = 'Basic ' + b64encode(f'{username}:{password}'.encode()).decode('utf-8')
        # @TODO: currently unused
        self.use_digest_auth = use_digest_auth
        self.__auth_digest = None
        if use_digest_auth:
            raise Exception('Digest authentication is not currently supported')

        # Internal properties
        self._device_info = {}

        self._channels = {}

        self._callbacks = set()

    def __repr__(self) -> str:
        return f'<Dahua:Device({self.host}:{self.port})>'

    @property
    def device_info(self):
        if self._device_info is None:
            self._device_info = self.get_info()
        return self._device_info

    def generate_url(self, path, protocol=None, add_credentials=False, **kwargs):
        prefix = (protocol or 'https' if self.use_ssl else 'http') + '://'
        if add_credentials:
            prefix += urlquote(self.__username, safe='') + ':' + urlquote(self.__password, safe='')
        base_url = prefix + self.host + ':' + str(self.port) + path

        return base_url + '?' + urlencode(kwargs, safe=',') if kwargs else base_url

    def generate_request(self, url, headers=None, *args, **kwargs):
        auth_headers = {'Authorization': self.__auth_basic}
        if headers:
            auth_headers.update(headers)

        return urllib.request.Request(
            url=url,
            headers=auth_headers,
            *args,
            **kwargs
        )

    def get_url_stream(self, channel, stream_type=0,
                       start_time: datetime = None,
                       end_time: datetime = None,
                       add_credentials=False):
        args = {
            'channel': channel,
            'subtype': stream_type,
        }

        if start_time and end_time:
            arg_format = '%Y_%m_%d_%H_%M_%S'
            args.update({
                'starttime': start_time.strftime(arg_format),
                'endtime': end_time.strftime(arg_format),
            })
            action = 'playback'
        else:
            action = 'realmonitor'

        return self.generate_url(
            path='/cam/' + action,
            protocol='rtsp',
            add_credentials=add_credentials,
            **args
        )

    def command(self, script, **kwargs) -> Optional[str]:
        request_url = self.generate_url(script, **kwargs)
        req = self.generate_request(request_url)

        error_code = None

        try:
            _LOGGER.debug('Making request to `%s`' % request_url)
            with urllib.request.urlopen(req) as response:
                data = response.read()
                _LOGGER.debug('Finished request to `%s`' % request_url)
                return data.decode('utf-8').replace('\r\n', '\n').strip()
        except HTTPError as e:
            if e.code == 401:
                raise UnauthorizedException(self, req)
            raise ProtocolException(self, req, e.code, e.reason)
        except OSError as e:
            _LOGGER.error('Low-level exception `%s` occured while performing command: %s' % (type(e), str(e)))
            return None

    def command_get_config(self, **kwargs) -> Optional[str]:
        return self.command(CGI_CONFIG, action='getConfig', **kwargs)

    def command_magic(self, **kwargs) -> Optional[str]:
        return self.command(CGI_MAGIC, **kwargs)

    def channel_index_to_number(self, index: int) -> int:
        # this is a helper method to use throughout the code
        return index + self.channel_number_offset

    def get_info_channel_titles(self) -> Optional[Dict[int, str]]:
        data = self.command_get_config(name='ChannelTitle')
        if not data:
            return None
        res = re.findall(r'table\.ChannelTitle\[(\d+)\]\.Name=(\w+)', data)
        return {self.channel_index_to_number(int(match[0])): match[1] for match in res} if res else None

    def _single_data_split(self, data):
        if not data:
            return None
        parts = data.split('=')
        try:
            return parts[1]
        except IndexError:
            return None

    def get_info_serial(self) -> Optional[str]:
        data = self.command_magic(action='getSerialNo')
        return self._single_data_split(data)

    def get_info_type(self):
        data = self.command_magic(action='getDeviceType')
        return self._single_data_split(data)

    # noinspection PyTypeChecker
    def get_info_software(self) -> Optional[Dict[str, str]]:
        data = self.command_magic(action='getSoftwareVersion')
        return dict([line.split('=', 1) for line in data.splitlines()]) if data else None

    def get_info_network(self) -> Optional[Dict[str, Any]]:
        data = self.command_get_config(name='Network')
        if not data:
            return None
        res = dict_from_dotted_str(data)
        return res.get('table', {}).get('Network') if res else None

    def _update_channels(self):
        for number, title in self._device_info['channel_titles'].items():
            if self._channels.get(number):
                self._channels[number].name = title
            else:
                self._channels[number] = Channel(self, number, title)

    def get_info(self) -> Optional[Dict[str, Any]]:
        new_info = {}
        for method_name in dir(self):
            if method_name.startswith('get_info_'):
                result = getattr(self, method_name)()
                if result is None:
                    return None

                new_info[method_name[9:]] = result

        self._device_info = new_info
        if 'channel_titles' in self._device_info:
            self._update_channels()

        return new_info

    async def async_get_info(self):
        """ Placeholder method for async """
        loop = asyncio.get_event_loop()

        params = []
        tasks = []
        for method_name in dir(self):
            if method_name.startswith('async_get_info_'):
                param = method_name[15:]
                coro = getattr(self, method_name)()
            elif method_name.startswith('get_info_'):
                param = method_name[9:]
                if param in tasks:
                    continue
                coro = loop.run_in_executor(None, getattr(self, method_name))
            else:
                continue

            params.append(param)
            tasks.append(asyncio.ensure_future(coro))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result

        new_info = dict(zip(params, results))
        self._device_info = new_info
        if 'channel_titles' in new_info:
            self._update_channels()

        return new_info

    def get_channel(self, number: int) -> Optional[Channel]:
        return self._channels.get(number)

    def __getitem__(self, number: int) -> Optional[Channel]:
        return self.get_channel(number)

    @property
    def channels(self):
        return self._channels

    def create_listener(self, *args, **kwargs):
        return EventsListener(self, *args, **kwargs)


class EventsListener(threading.Thread):
    def __init__(self,
                 device: Device,
                 monitored_events: List[str] = None,
                 alarm_channel: int = 1):
        super().__init__()

        self._callbacks = set()
        self.stopped = threading.Event()
        if not monitored_events:
            monitored_events = ['All']
        self._monitored_events = monitored_events
        self._device = device
        self._alarm_channel = alarm_channel

    @property
    def device(self) -> Device:
        return self._device

    @property
    def monitored_events(self) -> List[str]:
        return self._monitored_events

    @property
    def subscribe_url(self) -> str:
        return self._device.generate_url(
            path=CGI_EVENTS,
            action='attach',
            channel=self._alarm_channel,
            codes='[' + (','.join(self._monitored_events)) + ']',
        )

    def add_event_callback(self, callback: Callable[[Device, Dict[str, Any]], Any]) -> None:
        if not callable(callback):
            raise TypeError
        self._callbacks.add(callback)

    def remove_event_callback(self, callback: Callable[[Device, Dict[str, Any]], Any]) -> None:
        if not callable(callback):
            raise TypeError
        self._callbacks.remove(callback)

    async def listen_events_async(self) -> None:
        '''Async events listener (NOT FINISHED!)'''
        # @TODO: finish async event listener should the performance be better
        raise NotImplementedError

        async with aiohttp.request(
                url=self.subscribe_url,
                method='GET',
                auth=aiohttp.BasicAuth(self.__username, self.__password),
                timeout=aiohttp.ClientTimeout(sock_connect=2)
        ) as resp:
            try:
                async for data in resp.content.iter_any():
                    line = data.decode('utf-8')
            except asyncio.TimeoutError:
                _LOGGER.debug('Socket closed because of timeout')

    def listen_events_sync(self) -> bool:
        events_url = self.subscribe_url
        req = self._device.generate_request(events_url)

        try:
            _LOGGER.debug('Started listening `%s` for events...' % events_url)
            with urllib.request.urlopen(req, timeout=30) as response:
                buffer = b''
                last_char = b''
                while True:
                    this_char = response.read(1)
                    if last_char == b'\r' and this_char == b'\n':
                        line = buffer[:-1].decode('utf-8')
                        if line.startswith('Code'):
                            split_parts = [part.split('=', 1) for part in line.split(';')]
                            parts = {
                                part[0].lower(): str_value_to_type(part[1])
                                for part in split_parts
                            }

                            if 'index' in parts:
                                parts['channel'] = self.device.get_channel(
                                    self.device.channel_index_to_number(parts['index'])
                                )

                            for callback in self._callbacks:
                                callback(self, parts)

                        buffer = b''
                    else:
                        buffer += this_char

                    last_char = this_char
        except URLError as e:
            _LOGGER.error('HTTP error occured while listening for %s:%d: %s' % (self._device.host,
                                                                                self._device.port,
                                                                                e.reason))
            return False
        except socket_timeout_exception:
            _LOGGER.debug('Socket timeout during event listening, assumed as graceful')
            return True
        except OSError as e:
            _LOGGER.error('Low-level error `%s` while listening for %s:%d: %s' % (type(e),
                                                                                  self._device.host,
                                                                                  self._device.port,
                                                                                  str(e)))
            return False
        except Exception as e:
            _LOGGER.debug('Exception `%s` during event listening, assumed as graceful: %s' % (type(e), str(e)))
            return True  # in all other cases, listening failed gracefully

    def run(self):
        """Fetch events"""
        while not self.stopped.isSet():
            # Sleeps to ease load on processor

            status = self.listen_events_sync()
            if not status:
                _LOGGER.critical('Events listener failed with unrecovable error (see above)')
                self.stopped.set()

            # loop = asyncio.get_event_loop()
            # future = asyncio.ensure_future(self.listen_events())
            # loop.run_until_complete(future)
