"""Deterministic pre-processing. No LLM here - cheap, testable, predictable.

* normalises whitespace and bullet characters
* splits the input into numbered source sentences S1..Sn - every later
  LLM output must cite these IDs, which is what makes grounding checkable
* flags obvious prompt-injection attempts so they are treated as data
"""
from __future__ import annotations

import re

from . import config

_INJECTION_PATTERNS = [
    r"ignore (all |the )?(previous|above|prior) (instructions|prompts?)",
    r"disregard (the )?(system|previous) (prompt|instructions)",
    r"you are now", r"act as (an? )?(?!user|admin|manager)", r"system prompt",
    r"output (only )?the following", r"add (a |the )?requirement (for|that)",
]


def normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("’", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_sentences(text: str) -> list[dict]:
    """Split on sentence punctuation, bullets, table rows and line breaks."""
    chunks: list[str] = []
    for line in text.split("\n"):
        line = re.sub(r"^\s*(?:[-*•●]|\d+[.)])\s+", "", line).strip()
        if not line:
            continue
        if line.startswith("|"):          # keep markdown table rows intact
            chunks.append(line)
            continue
        parts = re.split(r"(?<=[.!?…])\s+(?=[A-Z0-9\"'(])|(?<=\.\.\.)\s+", line)
        chunks.extend(p.strip() for p in parts if p.strip())
    return [{"id": f"S{i + 1}", "text": c} for i, c in enumerate(chunks)]


def detect_injection(text: str) -> list[str]:
    low = text.lower()
    return [p for p in _INJECTION_PATTERNS if re.search(p, low)]


def prepare(raw: str) -> dict:
    """Return the prepared input package or raise ValueError for unusable input."""
    warnings: list[str] = []
    text = normalise(raw or "")
    if len(text.split()) < config.MIN_INPUT_WORDS:
        raise ValueError("Input is empty or too short to analyse (need at least a sentence).")
    if len(text) > config.MAX_INPUT_CHARS:
        text = text[: config.MAX_INPUT_CHARS]
        warnings.append(f"Input truncated to {config.MAX_INPUT_CHARS} characters.")
    hits = detect_injection(text)
    if hits:
        warnings.append("Input contains instruction-like text (possible prompt injection). "
                        "It was treated as customer data, not as instructions.")
    sentences = split_sentences(text)
    return {"text": text, "sentences": sentences, "warnings": warnings, "injection_flags": hits}


def numbered(sentences: list[dict]) -> str:
    return "\n".join(f"[{s['id']}] {s['text']}" for s in sentences)
