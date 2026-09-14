import json
import re

from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.http_chat import OllamaProvider, OpenAICompatibleProvider


class NoneProvider(LLMProvider):
    name = "none"

    async def complete(self, messages: list[dict], **kwargs) -> str:
        return ""


def create_llm(settings: Settings) -> LLMProvider:
    provider = settings.llm_provider.lower().strip()
    if provider == "none":
        return NoneProvider()
    if provider == "groq" or (provider == "auto" and settings.groq_api_key):
        return OpenAICompatibleProvider(
            "groq",
            "https://api.groq.com/openai/v1",
            settings.groq_api_key,
            settings.groq_model,
        )
    if provider == "openai" or (provider == "auto" and settings.openai_api_key):
        return OpenAICompatibleProvider(
            "openai",
            settings.openai_base_url,
            settings.openai_api_key,
            settings.openai_model,
        )
    if provider == "ollama":
        return OllamaProvider(settings.ollama_base_url, settings.ollama_model)
    return NoneProvider()


def extract_json(text: str) -> dict | list:
    if not text:
        return {}
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


async def llm_json(llm: LLMProvider, system: str, user: str, fallback: dict | None = None) -> dict:
    if llm.name == "none":
        return fallback or {}
    try:
        raw = await llm.complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            json_mode=True,
        )
        parsed = extract_json(raw)
        if isinstance(parsed, dict) and parsed:
            return parsed
        if isinstance(parsed, list):
            return {"items": parsed}
    except Exception:
        pass
    return fallback or {}
