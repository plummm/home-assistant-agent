"""Config flow for Home Assistant Agent."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import CONF_BASE_URL, CONF_LLM_KEY, DEFAULT_BASE_URL, DOMAIN


class HAAgentConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Home Assistant Agent."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is None:
            data_schema = vol.Schema(
                {vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str}
            )
            return self.async_show_form(step_id="user", data_schema=data_schema)

        return self.async_create_entry(title="Home Assistant Agent", data=user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HAAgentOptionsFlow(config_entry)


class HAAgentOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Home Assistant Agent."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is None:
            data_schema = vol.Schema(
                {
                    vol.Optional(
                        CONF_LLM_KEY,
                        default=self._config_entry.options.get(CONF_LLM_KEY, ""),
                    ): str
                }
            )
            return self.async_show_form(step_id="init", data_schema=data_schema)

        return self.async_create_entry(title="", data=user_input)
