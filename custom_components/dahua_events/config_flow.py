"""Config flow for the Dahua Events component."""
import logging
from collections import OrderedDict
from http.client import HTTPException

from requests.exceptions import ConnectTimeout, HTTPError
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD, CONF_USERNAME,
    CONF_AUTHENTICATION, CONF_SSL, CONF_PORT, CONF_NAME)

from . import create_device, ENTRY_SCHEMA
from .const import DOMAIN, DEFAULT_SSL, AUTH_METHODS, DEFAULT_AUTHENTICATION, \
    DEFAULT_NUMBER_OFFSET, DEFAULT_PASSWORD, DEFAULT_USERNAME, CONF_NUMBER_OFFSET, \
    CONF_CHANNELS, CONF_ALARM_CHANNEL, DEFAULT_ALARM_CHANNEL, DEFAULT_PORT, \
    DEFAULT_EVENTS, CONF_EVENTS, CONF_NUMBER, DEFAULT_NAME  # pylint: disable=unused-import
from .dahua.exceptions import UnauthorizedException, ProtocolException

CONF_POLLING = "polling"

_LOGGER = logging.getLogger(__name__)


class DahuaEventsFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Abode."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):
        """Initialize."""
        self.data_schema = OrderedDict()
        self.data_schema[vol.Required(CONF_HOST)] = str
        self.data_schema[vol.Optional(CONF_PORT, default=DEFAULT_PORT)] = int
        self.data_schema[vol.Optional(CONF_SSL, default=DEFAULT_SSL)] = bool
        self.data_schema[vol.Optional(CONF_USERNAME, default=DEFAULT_USERNAME)] = str
        self.data_schema[vol.Optional(CONF_PASSWORD, default=DEFAULT_PASSWORD)] = str
        self.data_schema[vol.Optional(CONF_NUMBER_OFFSET, default=DEFAULT_NUMBER_OFFSET)] = int
        self.data_schema[vol.Optional(CONF_AUTHENTICATION, default=DEFAULT_AUTHENTICATION)] = vol.In(AUTH_METHODS)
        self.data_schema[vol.Optional(CONF_ALARM_CHANNEL, default=DEFAULT_ALARM_CHANNEL)] = int
        self.data_schema[vol.Optional(CONF_CHANNELS)] = str
        self.data_schema[vol.Optional(CONF_EVENTS, default=','.join(DEFAULT_EVENTS))] = str

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""

        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if not user_input:
            return self._show_form()

        try:
            if CONF_CHANNELS in user_input:
                channels = user_input.get(CONF_CHANNELS)
                if channels:
                    converted = []
                    for channel in channels.split(','):
                        parts = channel.split(':', maxsplit=1)
                        new_channel = {CONF_NUMBER: int(parts[0])}
                        if len(parts) > 1:
                            new_channel[CONF_NAME] = parts[1].trim()

                        converted.append(new_channel)
                    user_input[CONF_CHANNELS] = converted
                else:
                    del user_input[CONF_CHANNELS]

            device = create_device(self.hass, user_input)
            device_info = await device.async_get_info()

            user_input[CONF_NAME] = DEFAULT_NAME.format(
                host=user_input[CONF_HOST],
                port=user_input[CONF_PORT]
            )

            save_data = ENTRY_SCHEMA(user_input)

        except ValueError as e:
            _LOGGER.error("Invalid input for channels")
            return self._show_form({"base": "invalid_channels"})
        except UnauthorizedException as e:
            _LOGGER.error("Unable to authenticate with Dahua device: %s", str(e))
            return self._show_form({"base": "invalid_credentials"})
        except ProtocolException as e:
            _LOGGER.error("Unable to connect to Dahua device: %s", str(e))
            return self._show_form({"base": "connection_error"})

        return self.async_create_entry(
            title=user_input[CONF_NAME],
            data=save_data,
        )

    @callback
    def _show_form(self, errors=None):
        """Show the form to the user."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(self.data_schema),
            errors=errors if errors else {},
        )

    async def async_step_import(self, import_config):
        """Import a config entry from configuration.yaml."""
        if self._async_current_entries():
            _LOGGER.warning("Only one configuration of abode is allowed.")
            return self.async_abort(reason="single_instance_allowed")

        return await self.async_step_user(import_config)
