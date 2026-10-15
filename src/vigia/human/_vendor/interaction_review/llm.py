"""Wrapper over the LLM with two backends: Anthropic (cloud) and Ollama (local).

Isolates the LLM dependency: the rest of the code works with dicts/pydantic and
does not know which backend is behind it. It is selected with the LLM_BACKEND
environment variable ('anthropic' by default, or 'ollama'). The models are
selected with GEN_MODEL / JUDGE_MODEL.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

# --- Defaults per backend ---
DEFAULT_GEN_MODEL = "claude-haiku-4-5-20251001"     # Anthropic: cheap generator (dated snapshot)
# NOTE (reproducibility): the judge default is a FLOATING alias, not a dated snapshot, so the
# provider may re-point it and quietly shift "the reproducible number". The run config records
# this alias; for a frozen run pin it via JUDGE_MODEL=claude-sonnet-4-6-<date>.
DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"           # Anthropic: judge (different model from gen)
DEFAULT_OLLAMA_GEN = "qwen2.5:14b"                  # Local: generator (what is evaluated)
DEFAULT_OLLAMA_JUDGE = "qwen2.5:14b"                # Local: fits entirely in 16 GB and judges well.
# Note: qwen2.5:32b would be the ideal judge by capability, but does NOT fit in 16 GB of
# VRAM (weighs ~24 GB) and spills over to shared memory -> extremely slow, unusable when iterating.
# gemma3:12b fits but is too weak for the matching. qwen2.5:14b is the only one
# that fits AND judges well (verified). Compromise: gen = judge = qwen2.5:14b; independence
# is mitigated with the anchoring to the golden, and an independent re-judgment remains
# available (e.g. phi4:14b, another family that also fits).

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_NUM_CTX = 16384  # the dossier + guidelines catalog does not fit in 2k


class LLMNotConfigured(RuntimeError):
    """No LLM backend available (no API key, or Ollama does not respond)."""


def backend() -> str:
    return os.environ.get("LLM_BACKEND", "anthropic").lower()


def _is_ollama() -> bool:
    return backend() in ("ollama", "local")


def gen_model() -> str:
    default = DEFAULT_OLLAMA_GEN if _is_ollama() else DEFAULT_GEN_MODEL
    return os.environ.get("GEN_MODEL", default)


def judge_model() -> str:
    default = DEFAULT_OLLAMA_JUDGE if _is_ollama() else DEFAULT_JUDGE_MODEL
    return os.environ.get("JUDGE_MODEL", default)


# --------------------------------------------------------------------------- #
# Anthropic backend (cloud): forced tool-use.
# --------------------------------------------------------------------------- #
def _anthropic_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise LLMNotConfigured(
            "Missing ANTHROPIC_API_KEY. Export it or use LLM_BACKEND=ollama for local."
        )
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise LLMNotConfigured("The 'anthropic' package is not installed.") from e
    return anthropic.Anthropic()


def _call_anthropic(model, system, user, tool, temperature, max_tokens) -> dict[str, Any]:
    client = _anthropic_client()
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return dict(block.input)
    # A truncated response has no tool_use block; say so instead of a generic error.
    if getattr(resp, "stop_reason", None) == "max_tokens":
        raise RuntimeError(
            f"The model hit max_tokens ({max_tokens}) before completing the tool call. "
            "Raise max_tokens or reduce the dossier / guideline batch size."
        )
    raise RuntimeError("The model did not return a tool_use block.")


# --------------------------------------------------------------------------- #
# Ollama backend (local): structured output via `format` (JSON-schema).
# --------------------------------------------------------------------------- #
def _num_ctx() -> int:
    """OLLAMA_NUM_CTX as int, falling back to the default if unset or malformed."""
    raw = os.environ.get("OLLAMA_NUM_CTX")
    if not raw:
        return DEFAULT_NUM_CTX
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_NUM_CTX


def ollama_payload(model, system, user, schema, temperature) -> dict[str, Any]:
    """Builds the body of /api/chat (pure function, testable without network)."""
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "format": schema,  # decoding constrained to the JSON-schema
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": _num_ctx(),
        },
    }


def _call_ollama(model, system, user, tool, temperature) -> dict[str, Any]:
    import httpx

    base = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL).rstrip("/")
    payload = ollama_payload(model, system, user, tool["input_schema"], temperature)
    timeout = float(os.environ.get("LLM_TIMEOUT", "900"))  # 15 min; when local is slow, some slack helps
    try:
        resp = httpx.post(f"{base}/api/chat", json=payload, timeout=timeout)
        resp.raise_for_status()
    except httpx.ConnectError as e:
        raise LLMNotConfigured(
            f"Ollama does not respond at {base}. Install Ollama and/or start the service "
            f"(`ollama serve`), and pull the model (`ollama pull {model}`)."
        ) from e
    except httpx.HTTPStatusError as e:
        # A 404 means the model is not pulled: a configuration error, not a transient
        # failure. Raise LLMNotConfigured so call_structured does NOT retry it 3x.
        if e.response.status_code == 404:
            raise LLMNotConfigured(
                f"Ollama at {base} does not have model {model!r} (404). Pull it: `ollama pull {model}`."
            ) from e
        raise  # other HTTP errors (e.g. transient 5xx): let the retry loop handle them
    content = resp.json()["message"]["content"]
    return json.loads(content)


# --------------------------------------------------------------------------- #
# Single interface.
# --------------------------------------------------------------------------- #
def call_structured(
    *,
    model: str,
    system: str,
    user: str,
    tool: dict[str, Any],
    temperature: float,
    max_tokens: int = 8000,
    retries: int = 3,
) -> dict[str, Any]:
    """Calls the LLM (per LLM_BACKEND) and returns a dict conforming to the schema of `tool`."""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            if _is_ollama():
                return _call_ollama(model, system, user, tool, temperature)
            return _call_anthropic(model, system, user, tool, temperature, max_tokens)
        except LLMNotConfigured:
            raise  # configuration error: no point in retrying
        except Exception as e:  # noqa: BLE001 - controlled retry on transient failures
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"LLM call failed after {retries} attempts: {last_err}")
