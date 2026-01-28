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
from .conversation import (
    HAAgentConversationAgent,
    async_register_agent,
    async_set_default_agent,
    async_unregister_agent,
)
from .const import (
    CONF_ANTHROPIC_KEY,
    CONF_BASE_URL,
    CONF_GEMINI_KEY,
    CONF_INSTRUCTION,
    CONF_LLM_KEY,
    CONF_MODEL_FAST,
    CONF_MODEL_REASONING,
    CONF_OPENAI_KEY,
    CONF_SET_DEFAULT_AGENT,
    CONF_STT_MODEL,
    CONF_TTS_MODEL,
    DEFAULT_BASE_URL,
    DEFAULT_INSTRUCTION,
    DOMAIN,
    PANEL_COMPONENT_NAME,
    PANEL_FRONTEND_URL,
    PANEL_ICON,
    PANEL_MODULE_URL,
    PANEL_TITLE,
)
from .storage import HAAgentStorage

PANEL_FILE_PATH = Path(__file__).parent / "panel" / "home-assistant-agent-panel.js"
PANEL_STATIC_URL = "/home_assistant_agent_panel/home-assistant-agent-panel.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(
        DOMAIN,
        {
            "entries": {},
            "panel_registered": False,
            "views_registered": False,
            "storage": HAAgentStorage(hass),
        },
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.setdefault(
        DOMAIN,
        {
            "entries": {},
            "panel_registered": False,
            "views_registered": False,
            "storage": HAAgentStorage(hass),
        },
    )

    session = aiohttp_client.async_get_clientsession(hass)
    storage: HAAgentStorage = domain_data["storage"]
    if not await storage.async_entry_exists(entry.entry_id):
        seed: dict[str, Any] = {"instruction": DEFAULT_INSTRUCTION}
        base_url = entry.data.get(CONF_BASE_URL)
        if base_url and base_url != DEFAULT_BASE_URL:
            seed["base_url"] = base_url
        llm_key = entry.options.get(CONF_LLM_KEY)
        if llm_key:
            seed["openai_key"] = llm_key
        await storage.async_set_entry(entry.entry_id, seed)
    settings = await storage.async_get_entry(entry.entry_id)
    client = HAAgentApi(settings.get("base_url", DEFAULT_BASE_URL), session)
    agent = HAAgentConversationAgent(hass, entry.entry_id)
    domain_data["entries"][entry.entry_id] = {
        "client": client,
        "entry": entry,
        "agent": agent,
        "settings": settings,
    }
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    await async_register_agent(hass, entry, agent)

    if entry.options.get(CONF_SET_DEFAULT_AGENT):
        await async_set_default_agent(hass, agent)

    if not domain_data["panel_registered"]:
        await _async_register_panel(hass)
        domain_data["panel_registered"] = True

    if not domain_data["views_registered"]:
        _register_views(hass)
        domain_data["views_registered"] = True

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.get(DOMAIN, {})
    entry_data = domain_data.get("entries", {}).pop(entry.entry_id, None)
    if entry_data and entry_data.get("agent"):
        await async_unregister_agent(hass, entry, entry_data["agent"])

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
    storage: HAAgentStorage = domain_data.get("storage")
    if storage:
        settings = await storage.async_get_entry(entry.entry_id)
        entry_data["settings"] = settings
        entry_data["client"].set_base_url(settings.get("base_url", DEFAULT_BASE_URL))
    if entry.options.get(CONF_SET_DEFAULT_AGENT):
        await async_set_default_agent(hass, entry_data["agent"])


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
    hass.http.register_view(HAAgentSettingsView())
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


async def _update_settings(
    hass: HomeAssistant, entry: ConfigEntry, updates: dict[str, Any]
) -> dict[str, Any]:
    domain_data = hass.data.get(DOMAIN, {})
    storage: HAAgentStorage = domain_data.get("storage")
    if not storage:
        return {}
    settings = await storage.async_set_entry(entry.entry_id, updates)
    entry_data = domain_data.get("entries", {}).get(entry.entry_id)
    if entry_data:
        entry_data["settings"] = settings
        if "base_url" in updates:
            entry_data["client"].set_base_url(settings.get("base_url", DEFAULT_BASE_URL))
    return settings


def _provider_for_model(model: str) -> str | None:
    if model.startswith("gpt-"):
        return "openai"
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith("gemini-"):
        return "gemini"
    return None


async def _validate_models(
    client: HAAgentApi,
    models: list[str],
    keys: dict[str, str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for model in models:
        provider = _provider_for_model(model)
        if not provider:
            results.append(
                {"model": model, "ok": False, "error": "Unknown model provider"}
            )
            continue
        api_key = keys.get(provider, "")
        if not api_key:
            results.append(
                {
                    "model": model,
                    "ok": False,
                    "error": f"Missing API key for {provider}",
                }
            )
            continue
        try:
            await client.async_chat(
                "ping",
                use_llm=True,
                api_key=api_key,
                model=model,
                default_reply="ok",
            )
            results.append({"model": model, "ok": True})
        except Exception as err:  # noqa: BLE001
            results.append({"model": model, "ok": False, "error": str(err)})
    return results


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
    """Store an LLM API key in HA storage."""

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
        settings = await _update_settings(hass, entry, {"openai_key": llm_key})
        return self.json(
            {"status": "ok", "openai_key_present": bool(settings.get("openai_key"))}
        )


class HAAgentSettingsView(HomeAssistantView):
    """Get or update stored settings without reloading the entry."""

    url = "/api/home_assistant_agent/settings"
    name = "api:home_assistant_agent:settings"
    requires_auth = True

    async def get(self, request):
        hass: HomeAssistant = request.app["hass"]
        entry_id = request.query.get("entry_id")
        entry, _client = _get_entry_and_client(hass, entry_id)
        if not entry:
            return self.json({"error": "No config entry found"}, status_code=400)
        entry_data = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry.entry_id, {})
        settings = entry_data.get("settings", {})
        return self.json(
            {
                "base_url": settings.get("base_url", DEFAULT_BASE_URL),
                "openai_key_present": bool(settings.get("openai_key")),
                "anthropic_key_present": bool(settings.get("anthropic_key")),
                "gemini_key_present": bool(settings.get("gemini_key")),
                "model_reasoning": settings.get("model_reasoning", ""),
                "model_fast": settings.get("model_fast", ""),
                "tts_model": settings.get("tts_model", ""),
                "stt_model": settings.get("stt_model", ""),
                "instruction": settings.get("instruction", DEFAULT_INSTRUCTION),
            }
        )

    async def post(self, request):
        hass: HomeAssistant = request.app["hass"]
        payload = await request.json()
        entry_id = payload.get("entry_id")
        entry, _client = _get_entry_and_client(hass, entry_id)
        if not entry:
            return self.json({"error": "No config entry found"}, status_code=400)
        updates: dict[str, Any] = {}
        if "base_url" in payload:
            updates["base_url"] = payload.get("base_url")
        if "openai_key" in payload:
            updates["openai_key"] = payload.get("openai_key")
        if "anthropic_key" in payload:
            updates["anthropic_key"] = payload.get("anthropic_key")
        if "gemini_key" in payload:
            updates["gemini_key"] = payload.get("gemini_key")
        if "model_reasoning" in payload:
            updates["model_reasoning"] = payload.get("model_reasoning")
        if "model_fast" in payload:
            updates["model_fast"] = payload.get("model_fast")
        if "tts_model" in payload:
            updates["tts_model"] = payload.get("tts_model")
        if "stt_model" in payload:
            updates["stt_model"] = payload.get("stt_model")
        if "instruction" in payload:
            updates["instruction"] = payload.get("instruction")
        settings = await _update_settings(hass, entry, updates)
        validation_results = None
        if payload.get("validate"):
            entry_data = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry.entry_id, {})
            client: HAAgentApi | None = entry_data.get("client") if entry_data else None
            if client:
                models: list[str] = []
                for name in ("model_reasoning", "model_fast"):
                    model = settings.get(name)
                    if model:
                        models.append(model)
                keys = {
                    "openai": settings.get("openai_key", ""),
                    "anthropic": settings.get("anthropic_key", ""),
                    "gemini": settings.get("gemini_key", ""),
                }
                validation_results = await _validate_models(client, models, keys)
        return self.json(
            {
                "status": "ok",
                "base_url": settings.get("base_url", DEFAULT_BASE_URL),
                "openai_key_present": bool(settings.get("openai_key")),
                "anthropic_key_present": bool(settings.get("anthropic_key")),
                "gemini_key_present": bool(settings.get("gemini_key")),
                "model_reasoning": settings.get("model_reasoning", ""),
                "model_fast": settings.get("model_fast", ""),
                "tts_model": settings.get("tts_model", ""),
                "stt_model": settings.get("stt_model", ""),
                "instruction": settings.get("instruction", DEFAULT_INSTRUCTION),
                "validation": validation_results,
            }
        )


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

        entry_data = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry.entry_id, {})
        settings = entry_data.get("settings", {})
        model = payload.get("model") or settings.get("model_reasoning") or settings.get("model_fast")
        provider = _provider_for_model(model) if model else None
        llm_key = payload.get("llm_key")
        if not llm_key:
            if provider == "openai":
                llm_key = settings.get("openai_key")
            elif provider == "anthropic":
                llm_key = settings.get("anthropic_key")
            elif provider == "gemini":
                llm_key = settings.get("gemini_key")
        if payload.get("llm_key") is not None:
            await _update_settings(hass, entry, {"openai_key": payload.get("llm_key", "")})

        entities = payload.get("entities") or _build_entity_payload(hass)
        result = await client.async_entity_suggest(
            entities=entities,
            use_llm=payload.get("use_llm"),
            api_key=llm_key,
            model=model,
        )
        return self.json(result)
