"""Native Ollama provider for fully local, no-key runs.

Uses the numeric loopback address (127.0.0.1) and disables environment proxies so a
corporate proxy never intercepts a localhost call.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import LLMProvider


class OllamaProvider(LLMProvider):
    """Local provider talking to an Ollama server's /api/chat endpoint."""

    def generate(self, system: str, prompt: str) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": self.temperature},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Could not reach Ollama at {url}: {getattr(exc, 'reason', exc)}. "
                "Is 'ollama serve' running and the model pulled?"
            ) from exc

        self.last_usage = {
            "input_tokens": body.get("prompt_eval_count"),
            "output_tokens": body.get("eval_count"),
        }
        return body["message"]["content"]
