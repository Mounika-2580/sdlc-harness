"""OpenAI-compatible provider.

Because the endpoint is a configurable base_url, this single implementation serves
OpenAI, OpenRouter, Together, vLLM, LM Studio, and any other OpenAI-compatible
server - cloud OR local. That is what makes the harness work with "api and local".
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    """Chat-completions provider for any OpenAI-compatible endpoint."""

    def generate(self, system: str, prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI-compatible request failed ({exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc

        usage = body.get("usage") or {}
        self.last_usage = {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
        }
        return body["choices"][0]["message"]["content"]
