"""Status sensor entity for Dahua Devices"""
from datetime import timedelta
from typing import Optional, Dict, Any, Union, TYPE_CHECKING
from homeassistant.helpers.entity import Entity
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    STATE_UNKNOWN,
    STATE_OK,
    STATE_OFF,
    CONF_NAME)

from custom_components.dahua_events.const import (
    DOMAIN,
    ATTR_CHANNEL_NAME_FORMAT,
    CONF_NUMBER,
    ATTR_SW_VERSION, ATTR_WEB_VERSION, ATTR_CHANNEL_TRIGGERED_FORMAT, ATTR_CHANNEL_LAST_EVENT_FORMAT)

if TYPE_CHECKING:
    from . import DahuaDevice


async def async_setup_entry(hass, config_entry, async_add_devices):
    """Setup sensor platform."""

    index = (config_entry.get(CONF_HOST), config_entry.get(CONF_PORT))
    device = hass.data[DOMAIN][index]  # type: Optional[DahuaDevice]
    async_add_devices([DahuaSensor(device)])


class DahuaSensor(Entity):
    def __init__(self, data_source: DahuaDevice):
        self._data_source = data_source

    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state.

        False if entity pushes its state to HA.
        """
        return False

    @property
    def unique_id(self) -> Optional[str]:
        """Return a unique ID."""
        return self._data_source.serial

    @property
    def name(self) -> Optional[str]:
        """Return the name of the entity."""
        return self._data_source.name

    @property
    def state(self) -> Union[None, str, int, float]:
        """Return the state of the entity."""
        return STATE_OK if self._data_source.connected else STATE_UNKNOWN

    @property
    def device_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return device specific state attributes.
        """
        attrs = {
            ATTR_SW_VERSION: self._data_source.sw_version,
            ATTR_WEB_VERSION: self._data_source.web_version
        }
        for ch in self._data_source.channels:
            channel_number = ch.get(CONF_NUMBER)
            channel_index = channel_number - self._data_source.number_offset

            attrs[ATTR_CHANNEL_NAME_FORMAT.format(channel_number)] = \
                ch.get(CONF_NAME, self._data_source.channel_titles.get(channel_index))

            (triggered_at, event_name) = self._data_source.channel_triggers.get(channel_index, (None, None))
            attrs[ATTR_CHANNEL_TRIGGERED_FORMAT.format(ch.get(CONF_NUMBER))] = triggered_at
            attrs[ATTR_CHANNEL_LAST_EVENT_FORMAT.format(ch.get(CONF_NUMBER))] = event_name

        return attrs

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        """Return device specific attributes.

        Implemented by platform classes.
        """
        return None

    @property
    def icon(self) -> Optional[str]:
        """Return the icon to use in the frontend, if any."""
        return 'mdi:cctv'

    @property
    def assumed_state(self) -> bool:
        """Return True if unable to access real state of the entity."""
        return STATE_OFF

    @property
    def context_recent_time(self) -> timedelta:
        """Time that a context is considered recent."""
        return timedelta(seconds=1)

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return True

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass.

        To be extended by integrations.
        """

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass.

        To be extended by integrations.
        """
