"""Abstract LLM provider interface.

Every provider exposes `generate(system, prompt) -> str`, so the rest of the harness
never depends on which provider is active. After each call a provider populates
`last_usage` (input_tokens / output_tokens) when the backend reports them, which the
run logger records.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Base class for all LLM backends (cloud API or local)."""

    def __init__(self, model: str, api_key: str, base_url: str,
                 max_tokens: int, temperature: float, timeout: int) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.last_usage: dict = {}

    @abstractmethod
    def generate(self, system: str, prompt: str) -> str:
        """Send a system + user prompt to the model and return its text reply."""
        raise NotImplementedError

    @property
    def label(self) -> str:
        return f"{type(self).__name__}({self.model})"
