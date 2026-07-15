"""Central configuration for the generalized SDLC harness.

Everything tunable lives here. The harness is **zero-config by default**: if you don't
set LLM_PROVIDER, it auto-detects an available AI (a known API key in your environment,
or a local Ollama server). You only ever *have* to configure something if no AI can be
found at all.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Populate os.environ from a .env file without overriding real env vars."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


for _candidate in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
    _load_dotenv(_candidate)


_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "ollama": "http://127.0.0.1:11434",
    "anthropic": "",
}
_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "ollama": "llama3.2",
    "anthropic": "claude-opus-4-8",
}


@dataclass
class LLMConfig:
    """Resolved LLM settings. Fields left blank are filled with provider defaults."""

    provider: str = ""
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    max_tokens: int = 4096
    temperature: float = 0.2
    timeout: int = 180
    autodetected: bool = False

    def __post_init__(self) -> None:
        self.provider = (self.provider or "ollama").lower()
        self.model = self.model or _DEFAULT_MODELS.get(self.provider, "")
        self.base_url = self.base_url or _DEFAULT_BASE_URLS.get(self.provider, "")


def _reachable(host: str, port: int, timeout: float = 0.4) -> bool:
    """Cheaply check whether a local service (e.g. Ollama) is listening."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _autodetect() -> tuple[str, str, str]:
    """Guess (provider, api_key, base_url) from the environment. Zero-config path.

    Priority: an explicit cloud key already in the environment, then a running local
    Ollama, then Ollama as the fallback default (errors clearly if not running).
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", os.environ["ANTHROPIC_API_KEY"], ""
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", os.environ["OPENAI_API_KEY"], ""
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openai", os.environ["OPENROUTER_API_KEY"], "https://openrouter.ai/api/v1"
    # Local, no key.
    return "ollama", "", ""


def _key_from_env(provider: str) -> str:
    if provider == "anthropic":
        return os.environ.get("ANTHROPIC_API_KEY", "")
    if provider == "openai":
        return os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
    return ""


def load_llm_config() -> LLMConfig:
    """Build config from env, auto-detecting the provider when not set explicitly."""
    provider = os.environ.get("LLM_PROVIDER", "").lower()
    api_key = os.environ.get("LLM_API_KEY", "")
    base_url = os.environ.get("LLM_BASE_URL", "")
    autodetected = False

    if not provider:
        provider, det_key, det_base = _autodetect()
        api_key = api_key or det_key
        base_url = base_url or det_base
        autodetected = True
    elif not api_key:
        api_key = _key_from_env(provider)

    return LLMConfig(
        provider=provider,
        model=os.environ.get("LLM_MODEL", ""),
        api_key=api_key,
        base_url=base_url,
        max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "4096")),
        temperature=float(os.environ.get("LLM_TEMPERATURE", "0.2")),
        timeout=int(os.environ.get("LLM_TIMEOUT", "180")),
        autodetected=autodetected,
    )


def ollama_running() -> bool:
    """True if a local Ollama server appears to be listening (for a friendly hint)."""
    return _reachable("127.0.0.1", 11434)


# --- Artifacts & limits -------------------------------------------------------

ARTIFACT_DIR = "docs/sdlc"
LOG_FILE = ".harness-log.jsonl"
STATE_FILE = ".sdlc-state.json"
BACKUP_DIR = ".backups"

TEST_COMMAND_TIMEOUT = int(os.environ.get("TEST_TIMEOUT", "300"))
REPAIR_ATTEMPTS = int(os.environ.get("REPAIR_ATTEMPTS", "2"))
JSON_RETRY_ATTEMPTS = int(os.environ.get("JSON_RETRY_ATTEMPTS", "1"))
MAX_DOC_CHARS = int(os.environ.get("MAX_DOC_CHARS", "8000"))


# --- Project detection (data-driven; add ecosystems by editing this map) ------

DETECTION_MAP: dict[str, str] = {
    "package.json": "Node.js / JavaScript / TypeScript",
    "requirements.txt": "Python",
    "pyproject.toml": "Python",
    "setup.py": "Python",
    "Pipfile": "Python",
    "pom.xml": "Java / Maven",
    "build.gradle": "Java / Kotlin / Gradle",
    "build.gradle.kts": "Kotlin / Gradle",
    "go.mod": "Go",
    "Cargo.toml": "Rust",
    "composer.json": "PHP",
    "Gemfile": "Ruby",
    "pubspec.yaml": "Dart / Flutter",
    "*.csproj": ".NET / C#",
    "*.sln": ".NET",
    "CMakeLists.txt": "C / C++",
    "mix.exs": "Elixir",
    "Package.swift": "Swift",
}

SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".go", ".rs", ".php",
    ".rb", ".dart", ".cs", ".cpp", ".c", ".h", ".swift", ".ex", ".exs", ".scala",
}

IGNORE_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    "target", "bin", "obj", ".idea", ".vscode", ".next", "vendor", ".dart_tool",
}
