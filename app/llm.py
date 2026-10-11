"""Thin wrapper around an OpenAI-compatible chat-completions endpoint.

Responsibilities:
  * stream the response (keeps long reasoning calls alive)
  * strip reasoning / code fences and pull out the JSON object
  * validate against a Pydantic schema, and on failure do ONE repair retry
    that shows the model its own error
  * fall back along config.fallback_chain() on transport errors / timeouts
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Type, TypeVar

import httpx
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from . import config

log = logging.getLogger("llm")
T = TypeVar("T", bound=BaseModel)

# read timeout = max silence between streamed chunks (the deep model can queue ~3 min
# before its first token); the total wall-clock budget per call is enforced in chat().
_clients: dict[tuple, OpenAI] = {}


def _client_for(model: str) -> OpenAI:
    key = config.api_key_for(model)
    _, silence = config.timeouts_for(model)
    if (key, silence) not in _clients:
        _clients[(key, silence)] = OpenAI(
            base_url=config.API_BASE_URL, api_key=key, max_retries=1,
            timeout=httpx.Timeout(connect=20, read=silence, write=30, pool=30))
    return _clients[(key, silence)]


class LLMError(RuntimeError):
    pass


def chat(system: str, user: str, model: str, max_tokens: int = 4096,
         temperature: float = config.LLM_TEMPERATURE) -> tuple[str, dict]:
    """Return (content, meta). Streams the response to keep long calls alive."""
    t0 = time.time()
    deadline, _ = config.timeouts_for(model)
    stream = _client_for(model).chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature, top_p=1, max_tokens=max_tokens, stream=True,
    )
    content, reasoning = [], []
    for chunk in stream:
        if time.time() - t0 > deadline:
            stream.close()
            raise LLMError(f"{model} exceeded {deadline}s")
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta
        if delta.content:
            content.append(delta.content)
        rc = getattr(delta, "reasoning_content", None)
        if rc:
            reasoning.append(rc)
    text = "".join(content)
    if not text.strip():
        raise LLMError(f"{model} returned an empty response")
    return text, {"model": config.label_for(model), "seconds": round(time.time() - t0, 1),
                  "reasoning_chars": len("".join(reasoning))}


def extract_json(text: str) -> dict:
    """Pull the first top-level JSON object out of a model response."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in response")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unterminated JSON object")


def _is_rate_limit(e: Exception) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in ("resourceexhausted", "request limit", "rate limit", "429", "too many"))


def chat_with_retry(system: str, user: str, model: str, max_tokens: int) -> tuple[str, dict]:
    """Retry the SAME model with backoff on rate limits / empty streams (shared free-tier workers)."""
    delays = [4, 12, 30] if model != config.QUALITY_MODEL else [10]
    for i in range(len(delays) + 1):
        try:
            return chat(system, user, model, max_tokens=max_tokens)
        except Exception as e:  # noqa: BLE001
            retryable = (_is_rate_limit(e) or "empty response" in str(e) or "exceeded" in str(e)
                         or "timed out" in str(e).lower())
            if not retryable or i == len(delays):
                raise
            log.warning("retrying %s in %ss: %s", model, delays[i], e)
            time.sleep(delays[i])
    raise LLMError("unreachable")


def structured(system: str, user: str, schema: Type[T], model: str,
               max_tokens: int = 6000) -> tuple[T, dict]:
    """Call the LLM and return a validated `schema` instance.

    * rate limits / empty streams: retried on the same model with backoff
    * invalid JSON / schema: one repair retry showing the model its own error
    * persistent transport errors: next model in config.fallback_chain()
    """
    meta: dict = {"attempts": 0, "repaired": False, "fallback": False}
    models = config.fallback_chain(model)  # e.g. Model_2 -> Model_1 -> backup
    last_err: Exception | None = None

    for m in models:
        prompt = user
        for attempt in range(2):
            meta["attempts"] += 1
            try:
                raw, call_meta = chat_with_retry(system, prompt, m, max_tokens)
                meta.update(call_meta)
            except Exception as e:  # transport / API error -> try next model
                last_err = e
                log.warning("LLM call failed on %s: %s", m, e)
                meta["fallback"] = True
                break
            try:
                return schema.model_validate(extract_json(raw)), meta
            except (ValueError, ValidationError, json.JSONDecodeError) as e:
                last_err = e
                meta["repaired"] = True
                prompt = (f"{user}\n\n---\nYour previous answer was invalid:\n{str(e)[:1500]}\n"
                          f"Previous answer (truncated):\n{raw[:3000]}\n\n"
                          "Return ONLY a corrected JSON object that matches the schema exactly.")
    raise LLMError(f"Structured call failed: {last_err}")
