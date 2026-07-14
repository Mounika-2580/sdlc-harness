"""Central configuration for the generalized SDLC harness.

Everything tunable lives here: which LLM provider to use, the manifest->ecosystem
detection map, artifact locations, and safety/robustness limits. Nothing in this file
is tied to a specific programming language or a specific project.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
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


# Load a .env from the current working directory or the repo root, if present.
for _candidate in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
    _load_dotenv(_candidate)


# Per-provider default endpoints/models; every value is overridable by env vars so the
# same code path serves cloud APIs and local models.
_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "ollama": "http://127.0.0.1:11434",
    "anthropic": "",  # SDK manages the endpoint
}

_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "ollama": "llama3.2",
    "anthropic": "claude-opus-4-8",
}


@dataclass
class LLMConfig:
    """Resolved LLM settings. Provider is chosen purely from config/env."""

    provider: str = field(default_factory=lambda: os.environ.get("LLM_PROVIDER", "ollama").lower())
    model: str = ""
    api_key: str = field(default_factory=lambda: os.environ.get("LLM_API_KEY", ""))
    base_url: str = ""
    max_tokens: int = field(default_factory=lambda: int(os.environ.get("LLM_MAX_TOKENS", "4096")))
    temperature: float = field(default_factory=lambda: float(os.environ.get("LLM_TEMPERATURE", "0.2")))
    timeout: int = field(default_factory=lambda: int(os.environ.get("LLM_TIMEOUT", "180")))

    def __post_init__(self) -> None:
        self.model = self.model or os.environ.get("LLM_MODEL", "") or _DEFAULT_MODELS.get(self.provider, "")
        self.base_url = (
            self.base_url
            or os.environ.get("LLM_BASE_URL", "")
            or _DEFAULT_BASE_URLS.get(self.provider, "")
        )


def load_llm_config() -> LLMConfig:
    """Build the LLM configuration from environment variables."""
    return LLMConfig()


# --- Artifacts & limits -------------------------------------------------------

ARTIFACT_DIR = "docs/sdlc"          # relative to the target project folder
LOG_FILE = ".harness-log.jsonl"     # per-call LLM log, inside ARTIFACT_DIR
STATE_FILE = ".sdlc-state.json"     # resume state, inside ARTIFACT_DIR
BACKUP_DIR = ".backups"             # overwritten-file snapshots, inside ARTIFACT_DIR

# Max seconds a test/build command may run before the harness kills it.
TEST_COMMAND_TIMEOUT = int(os.environ.get("TEST_TIMEOUT", "300"))

# How many times to auto-repair failing tests (feed the error back and retry).
REPAIR_ATTEMPTS = int(os.environ.get("REPAIR_ATTEMPTS", "2"))

# How many times to re-ask the model for valid JSON when parsing fails.
JSON_RETRY_ATTEMPTS = int(os.environ.get("JSON_RETRY_ATTEMPTS", "1"))

# Cap for each prior-stage document injected into a prompt (protects the model's
# context window on large brownfield repos). Truncation is announced in the prompt.
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
