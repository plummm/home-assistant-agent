"""Conversation agent for Home Assistant Agent."""

from __future__ import annotations

from typing import Any

from homeassistant.components import conversation
from homeassistant.components.conversation import (
    AbstractConversationAgent,
    ConversationInput,
    ConversationResult,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.intent import IntentResponse

from .const import DOMAIN


def _provider_for_model(model: str | None) -> str | None:
    if not model:
        return None
    if model.startswith("gpt-"):
        return "openai"
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith("gemini-"):
        return "gemini"
    return None


class HAAgentConversationAgent(AbstractConversationAgent):
    """Conversation agent that proxies to ha_agent_core."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self._entry_id = entry_id

    @property
    def agent_id(self) -> str:
        return self._entry_id

    @property
    def name(self) -> str:
        return "Home Assistant Agent"

    @property
    def attribution(self) -> str:
        return "Powered by ha_agent_core"

    async def async_process(
        self, conversation_input: ConversationInput
    ) -> ConversationResult:
        entry_data = (
            self.hass.data.get(DOMAIN, {})
            .get("entries", {})
            .get(self._entry_id, {})
        )
        client = entry_data.get("client")
        settings = entry_data.get("settings", {})
        model = settings.get("model_reasoning") or settings.get("model_fast")
        provider = _provider_for_model(model)
        llm_key = None
        if provider == "openai":
            llm_key = settings.get("openai_key")
        elif provider == "anthropic":
            llm_key = settings.get("anthropic_key")
        elif provider == "gemini":
            llm_key = settings.get("gemini_key")

        response_text = "Sorry, I couldn't reach the agent."
        conversation_id = conversation_input.conversation_id
        if client:
            result: dict[str, Any] = await client.async_chat(
                conversation_input.text,
                conversation_id=conversation_id,
                use_llm=True,
                api_key=llm_key,
                model=model,
            )
            response_text = result.get("response", response_text)
            conversation_id = result.get("conversation_id", conversation_id)

        intent_response = IntentResponse(language=conversation_input.language)
        intent_response.async_set_speech(response_text)
        return ConversationResult(
            response=intent_response, conversation_id=conversation_id
        )


async def async_register_agent(
    hass: HomeAssistant, agent: AbstractConversationAgent
) -> None:
    if hasattr(conversation, "async_set_agent"):
        try:
            await conversation.async_set_agent(hass, agent)
        except TypeError:
            await conversation.async_set_agent(hass, agent.agent_id, agent)


async def async_unregister_agent(
    hass: HomeAssistant, agent: AbstractConversationAgent
) -> None:
    if hasattr(conversation, "async_unset_agent"):
        try:
            await conversation.async_unset_agent(hass, agent)
        except TypeError:
            await conversation.async_unset_agent(hass, agent.agent_id)


async def async_set_default_agent(
    hass: HomeAssistant, agent: AbstractConversationAgent
) -> None:
    if hasattr(conversation, "async_set_default_agent"):
        try:
            await conversation.async_set_default_agent(hass, agent)
        except TypeError:
            await conversation.async_set_default_agent(hass, agent.agent_id)
        return

    if hasattr(conversation, "async_set_default_agent_id"):
        await conversation.async_set_default_agent_id(hass, agent.agent_id)
