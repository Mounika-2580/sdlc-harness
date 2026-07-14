"""LLM provider factory.

`get_provider()` maps the resolved config's provider name to a concrete
implementation. Add a new backend by dropping a module here and registering it in
_PROVIDERS - nothing else in the harness changes.
"""

from __future__ import annotations

from ..config import LLMConfig
from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,      # any OpenAI-compatible endpoint, cloud or local
    "ollama": OllamaProvider,      # native local
}


def get_provider(cfg: LLMConfig) -> LLMProvider:
    """Instantiate the provider named by cfg.provider."""
    cls = _PROVIDERS.get(cfg.provider)
    if cls is None:
        valid = ", ".join(sorted(_PROVIDERS))
        raise ValueError(f"Unknown LLM_PROVIDER '{cfg.provider}'. Valid: {valid}")
    return cls(
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
        timeout=cfg.timeout,
    )
