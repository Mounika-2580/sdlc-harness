"""Secrets / PII guardrail.

Scans text (typically LLM-generated file content) for things that must never be
written into a project: API keys, private keys, credentials, and obvious PII. The
orchestrator blocks any file whose content trips a HIGH-severity rule unless the
user explicitly overrides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (label, severity, compiled pattern). Severity "high" blocks by default.
_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("AWS access key id", "high", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Private key block", "high", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("OpenAI-style key", "high", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("Anthropic key", "high", re.compile(r"\bsk-ant-[A-Za-z0-9-]{20,}\b")),
    ("Slack token", "high", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", "high", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("GitHub token", "high", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("Hardcoded password/secret assignment", "high",
     re.compile(r"(?i)(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"][^'\"]{6,}['\"]")),
    ("Possible SSN (US)", "medium", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("Credit-card-like number", "medium", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
]

# Common placeholders that should NOT be treated as real secrets.
_PLACEHOLDERS = re.compile(
    r"(?i)(your[_-]?key|example|placeholder|xxx+|<[^>]+>|changeme|dummy|sk-ant-\.\.\.|sk-\.\.\.)"
)


@dataclass
class Finding:
    label: str
    severity: str
    snippet: str


def scan(text: str) -> list[Finding]:
    """Return guardrail findings for a blob of text."""
    findings: list[Finding] = []
    for label, severity, pattern in _RULES:
        for match in pattern.finditer(text):
            hit = match.group(0)
            if _PLACEHOLDERS.search(hit):
                continue
            findings.append(Finding(label=label, severity=severity, snippet=_mask(hit)))
    return findings


def _mask(value: str) -> str:
    """Never echo a full secret back; keep only the ends."""
    value = value.replace("\n", " ").strip()
    if len(value) <= 12:
        return value[:2] + "***"
    return f"{value[:4]}...{value[-4:]}"


def has_blocking(findings: list[Finding]) -> bool:
    return any(f.severity == "high" for f in findings)
