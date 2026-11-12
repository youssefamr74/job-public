"""The AI providers the user can choose from. Model ids are never hardcoded: they're listed live."""

from dataclasses import dataclass

KIND_OPENAI = "openai_compatible"
KIND_ANTHROPIC = "anthropic"


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    kind: str
    default_base_url: str
    needs_api_key: bool
    supports_batch: bool
    supports_pdf: bool


PROVIDERS: dict[str, Provider] = {
    p.id: p for p in (
        Provider("anthropic", "Anthropic", KIND_ANTHROPIC, "https://api.anthropic.com/v1", True, True, True),
        Provider("openai", "OpenAI", KIND_OPENAI, "https://api.openai.com/v1", True, True, False),
        Provider("gemini", "Google Gemini", KIND_OPENAI, "https://generativelanguage.googleapis.com/v1beta/openai", True, False, False),
        Provider("openrouter", "OpenRouter", KIND_OPENAI, "https://openrouter.ai/api/v1", True, False, False),
        Provider("ollama", "Ollama (local)", KIND_OPENAI, "http://localhost:11434/v1", False, False, False),
    )
}
