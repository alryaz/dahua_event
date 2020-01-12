"""
Attach event listener to Dahua devices
Borrowed code from https://github.com/johnnyletrois/dahua-watch

Author: Akram
"""
import collections
import re
import threading, logging

import asyncio
from typing import Optional, Dict, Any, Union

import voluptuous as vol
from datetime import timedelta

from homeassistant import config_entries
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import HomeAssistantType

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import device_registry as dr
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
    CONF_AUTHENTICATION
)

from .const import *

from custom_components.dahua_events.dahua import (
    Device as DahuaDevice,
    EventsListener as DahuaEventsListener
)

_LOGGER = logging.getLogger(__name__)

CHANNEL_SCHEMA = vol.Schema({
    vol.Required(CONF_NUMBER): int,
    vol.Optional(CONF_NAME): cv.string,
})

ENTRY_SCHEMA = vol.Schema({
    vol.Optional(CONF_NAME): cv.string,
    vol.Required(CONF_HOST): cv.string,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    vol.Optional(CONF_SSL, default=DEFAULT_SSL): cv.boolean,
    vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME): cv.string,
    vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD): cv.string,
    vol.Optional(CONF_NUMBER_OFFSET, default=DEFAULT_NUMBER_OFFSET): int,
    vol.Optional(CONF_AUTHENTICATION, default=DEFAULT_AUTHENTICATION): vol.In(AUTH_METHODS),
    vol.Optional(CONF_ALARM_CHANNEL, default=DEFAULT_ALARM_CHANNEL): int,
    vol.Optional(CONF_CHANNELS): vol.All(cv.ensure_list, [vol.Any(
        CHANNEL_SCHEMA,
        lambda x: CHANNEL_SCHEMA({CONF_NUMBER: x}) if isinstance(x, int) else vol.Invalid('')
    )]),
    vol.Optional(CONF_EVENTS, default=DEFAULT_EVENTS): vol.All(cv.ensure_list, [cv.string]),
    #vol.Optional(CONF_SCAN_INTERVAL, default=timedelta): cv.time_period,
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN:
        vol.All(cv.ensure_list, [ENTRY_SCHEMA])
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    conf = config.get(DOMAIN, [])

    _LOGGER.debug('Current config status: %s', conf)

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    if DATA_CONFIGS not in hass.data:
        hass.data[DATA_CONFIGS] = {}

    # User has not configured any listeners
    if conf:
        configured_hosts = set(
            (entry.data[CONF_HOST], entry.data[CONF_PORT])
            for entry in hass.config_entries.async_entries(DOMAIN)
        )

        for device_cfg in conf:
            host, port = device_cfg[CONF_HOST], device_cfg[CONF_PORT]

            hass.data[DATA_CONFIGS][(host, port)] = device_cfg

            if (host, port) in configured_hosts:
                _LOGGER.debug('Entry %s:%d already configured' % (host, port))
                continue

            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": config_entries.SOURCE_IMPORT},
                    data=device_cfg,
                )
            )

    _LOGGER.debug('Component setup complete, devices created: %d' % len(conf))

    return True


def create_device(hass, device_cfg):
    return DahuaDevice(
        host=device_cfg.get(CONF_HOST),
        port=device_cfg.get(CONF_PORT),
        username=device_cfg.get(CONF_USERNAME),
        password=device_cfg.get(CONF_PASSWORD),
        channel_number_offset=device_cfg.get(CONF_NUMBER_OFFSET),
        use_ssl=device_cfg.get(CONF_SSL),
        use_digest_auth=(device_cfg.get(CONF_AUTHENTICATION) == 'digest')
    )


def create_listener(hass, device, device_cfg):
    return DahuaEventsListener(
        device=device,
        monitored_events=device_cfg.get(CONF_EVENTS),
        alarm_channel=device_cfg.get(CONF_ALARM_CHANNEL)
    )


async def async_setup_entry(
    hass: HomeAssistantType, entry: config_entries.ConfigEntry
):
    """Set up a bridge from a config entry."""

    host = entry.data.get(CONF_HOST)
    port = entry.data.get(CONF_PORT)
    name = entry.data.get(CONF_NAME, DEFAULT_NAME.format(host=host, port=port))

    device = create_device(hass, entry.data)

    device_info = await device.async_get_info()

    if device_info is None:
        return False

    device_registry = await dr.async_get_registry(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={
            (dr.CONNECTION_NETWORK_MAC, network['PhysicalAddress'])
            for network in device_info['network'].values()
            if isinstance(network, dict)
        },
        identifiers={(DOMAIN, device_info['serial'])},
        manufacturer="Signify",
        name=name,
        model=device_info['type'],
        sw_version=device_info['software'].get('version'),
    )

    events = entry.data.get(CONF_EVENTS)
    channels = entry.data.get(CONF_CHANNELS)
    if channels:
        listen_channels = [c.number for c in entry.data.get(CONF_CHANNELS)]
    else:
        listen_channels = True

    def listener_callback(device, event_data):
        if not events or event_data['code'] in events:
            hass_event_data = {'code': event_data['code']}

            _LOGGER.debug('Event received: %s' % event_data)

            if 'action' in event_data:
                hass_event_data['action'] = event_data['action']

            if 'channel' in event_data:
                channel_number = event_data['channel'].number
                if not (listen_channels is True or channel_number in listen_channels):
                    _LOGGER.debug('Skipping channel %d (listening for: %s)' % (
                        channel_number,
                        'all' if listen_channels is True
                        else listen_channels
                    ))
                    return

                hass_event_data['channel_number'] = channel_number
                hass_event_data['channel_name'] = event_data['channel'].name

            _LOGGER.debug('Delegating to HA: %s', hass_event_data)

            hass.bus.fire(
                'dahua_event_received',
                hass_event_data
            )

    listener = create_listener(hass, device, entry.data)
    listener.add_event_callback(listener_callback)

    hass.data[DOMAIN][(host, port)] = (device, listener)

    # start listening thread
    listener.start()

    '''hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(
            entry,
            'sensor'
        )
    )'''

    return True


async def async_unload_entry(hass: HomeAssistantType, entry: config_entries.ConfigEntry):
    """Unload a config entry."""

    host = entry.data.get(CONF_HOST)
    port = entry.data.get(CONF_PORT)

    device, listener = hass.data[DOMAIN].pop((host, port))  # type: DahuaDevice, DahuaEventsListener

    listener.stopped.set()


