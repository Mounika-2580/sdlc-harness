"""Anthropic (Claude) provider using the native Messages API.

The `anthropic` package is imported lazily so the harness has no hard dependency on
it unless this provider is actually selected.
"""

from __future__ import annotations

from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    """Cloud provider for Claude models via the Anthropic Messages API."""

    def generate(self, system: str, prompt: str) -> str:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "The 'anthropic' package is required for the anthropic provider. "
                "Install it with: pip install anthropic  (or pip install -e \".[anthropic]\")"
            ) from exc

        if not self.api_key:
            raise RuntimeError("LLM_API_KEY is required for the anthropic provider.")

        client = anthropic.Anthropic(api_key=self.api_key)
        resp = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = getattr(resp, "usage", None)
        if usage is not None:
            self.last_usage = {
                "input_tokens": getattr(usage, "input_tokens", None),
                "output_tokens": getattr(usage, "output_tokens", None),
            }
        return "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
