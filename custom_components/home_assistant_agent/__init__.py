"""Home Assistant Agent integration setup."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.components import panel_custom
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .api import HAAgentApi
from .const import (
    CONF_BASE_URL,
    CONF_LLM_KEY,
    DEFAULT_BASE_URL,
    DOMAIN,
    PANEL_COMPONENT_NAME,
    PANEL_FRONTEND_URL,
    PANEL_ICON,
    PANEL_MODULE_URL,
    PANEL_TITLE,
)

PANEL_FILE_PATH = Path(__file__).parent / "panel" / "home-assistant-agent-panel.js"
PANEL_STATIC_URL = "/home_assistant_agent_panel/home-assistant-agent-panel.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(
        DOMAIN,
        {"entries": {}, "panel_registered": False, "views_registered": False},
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.setdefault(
        DOMAIN,
        {"entries": {}, "panel_registered": False, "views_registered": False},
    )

    session = aiohttp_client.async_get_clientsession(hass)
    client = HAAgentApi(entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL), session)
    domain_data["entries"][entry.entry_id] = {"client": client}
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    if not domain_data["panel_registered"]:
        await _async_register_panel(hass)
        domain_data["panel_registered"] = True

    if not domain_data["views_registered"]:
        _register_views(hass)
        domain_data["views_registered"] = True

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.get(DOMAIN, {})
    domain_data.get("entries", {}).pop(entry.entry_id, None)

    if not hass.config_entries.async_entries(DOMAIN):
        if domain_data.get("panel_registered"):
            await _async_unregister_panel(hass)
            domain_data["panel_registered"] = False
    return True


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    entry_data = domain_data.get("entries", {}).get(entry.entry_id)
    if not entry_data:
        return
    client: HAAgentApi = entry_data["client"]
    client.set_base_url(entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL))


async def _async_register_panel(hass: HomeAssistant) -> None:
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_STATIC_URL, str(PANEL_FILE_PATH), False)]
    )
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_COMPONENT_NAME,
        frontend_url_path=PANEL_FRONTEND_URL,
        module_url=PANEL_MODULE_URL,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        config={},
        require_admin=False,
    )


async def _async_unregister_panel(hass: HomeAssistant) -> None:
    remove_fn = getattr(panel_custom, "async_remove_panel", None)
    if remove_fn is None:
        remove_fn = getattr(panel_custom, "async_unregister_panel", None)
    if remove_fn is not None:
        await remove_fn(hass, PANEL_FRONTEND_URL)


def _register_views(hass: HomeAssistant) -> None:
    hass.http.register_view(HAAgentEntitiesView())
    hass.http.register_view(HAAgentLLMKeyView())
    hass.http.register_view(HAAgentSuggestView())


def _get_entry_and_client(
    hass: HomeAssistant, entry_id: str | None
) -> tuple[ConfigEntry | None, HAAgentApi | None]:
    entries = hass.config_entries.async_entries(DOMAIN)
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
    else:
        entry = entries[0] if entries else None
    if not entry:
        return None, None
    entry_data = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry.entry_id)
    if not entry_data:
        return entry, None
    return entry, entry_data["client"]


def _update_llm_key(hass: HomeAssistant, entry: ConfigEntry, llm_key: str) -> None:
    hass.config_entries.async_update_entry(
        entry,
        options={**entry.options, CONF_LLM_KEY: llm_key},
    )


def _build_entity_payload(hass: HomeAssistant) -> list[dict[str, Any]]:
    entity_reg = er.async_get(hass)
    device_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)
    entities: list[dict[str, Any]] = []

    for entry in entity_reg.entities.values():
        device = device_reg.devices.get(entry.device_id) if entry.device_id else None
        area_id = entry.area_id or (device.area_id if device else None)
        area = area_reg.areas.get(area_id) if area_id else None
        state = hass.states.get(entry.entity_id)
        name = (
            entry.name
            or entry.original_name
            or (state.attributes.get("friendly_name") if state else None)
            or entry.entity_id
        )
        device_class = getattr(entry, "device_class", None) or (
            state.attributes.get("device_class") if state else None
        )
        unit = getattr(entry, "unit_of_measurement", None) or (
            state.attributes.get("unit_of_measurement") if state else None
        )

        entities.append(
            {
                "entity_id": entry.entity_id,
                "name": name,
                "device_class": device_class,
                "unit": unit,
                "area": area.name if area else None,
                "device": device.name_by_user or device.name if device else None,
            }
        )

    return entities


class HAAgentEntitiesView(HomeAssistantView):
    """Return registry data shaped for /entity/suggest."""

    url = "/api/home_assistant_agent/entities"
    name = "api:home_assistant_agent:entities"
    requires_auth = True

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        entities = _build_entity_payload(hass)
        return self.json({"entities": entities})


class HAAgentLLMKeyView(HomeAssistantView):
    """Store an LLM API key in config entry options."""

    url = "/api/home_assistant_agent/llm_key"
    name = "api:home_assistant_agent:llm_key"
    requires_auth = True

    async def post(self, request):
        hass: HomeAssistant = request.app["hass"]
        payload = await request.json()
        llm_key = payload.get("llm_key", "")
        entry_id = payload.get("entry_id")
        entry, _client = _get_entry_and_client(hass, entry_id)
        if not entry:
            return self.json({"error": "No config entry found"}, status_code=400)
        _update_llm_key(hass, entry, llm_key)
        return self.json({"status": "ok"})


class HAAgentSuggestView(HomeAssistantView):
    """Proxy /entity/suggest to ha_agent_core."""

    url = "/api/home_assistant_agent/suggest"
    name = "api:home_assistant_agent:suggest"
    requires_auth = True

    async def post(self, request):
        hass: HomeAssistant = request.app["hass"]
        payload = await request.json()
        entry_id = payload.get("entry_id")
        entry, client = _get_entry_and_client(hass, entry_id)
        if not entry or not client:
            return self.json({"error": "No config entry found"}, status_code=400)

        llm_key = payload.get("llm_key") or entry.options.get(CONF_LLM_KEY)
        if payload.get("llm_key") is not None:
            _update_llm_key(hass, entry, payload.get("llm_key", ""))

        entities = payload.get("entities") or _build_entity_payload(hass)
        result = await client.async_entity_suggest(
            entities=entities,
            use_llm=payload.get("use_llm"),
            api_key=llm_key,
            model=payload.get("model"),
        )
        return self.json(result)
