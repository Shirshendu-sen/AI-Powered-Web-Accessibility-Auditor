"""Provider-agnostic AI resolver — shared by Phase 4 (alt-text, vision) and
Phase 5 (ARIA/semantic, text).

Selection is env-driven per Section 3.1 of the guide:
    AI_PROVIDER = "gemini"      -> Google Gemini via google-genai SDK
    AI_PROVIDER = "openrouter"  -> OpenRouter's OpenAI-compatible endpoint via httpx

Any other value (including missing) raises a configuration error at import
time so the pipeline fails fast rather than silently defaulting.

Neither fixer imports a provider SDK directly — they call `generate_vision`
and `generate_text` here. Swapping providers is a config change.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")


class AIProviderError(RuntimeError):
    """Raised when the provider layer can't fulfil a request in a way the
    caller must handle differently from a normal failure — misconfigured
    key, provider auth rejection, transient rate-limit / quota exhaustion.
    """

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind  # one of: config, auth, rate_limit, timeout, upstream


VALID_PROVIDERS = ("gemini", "openrouter")

AI_PROVIDER = os.environ.get("AI_PROVIDER", "").strip().lower()
if AI_PROVIDER not in VALID_PROVIDERS:
    raise AIProviderError(
        f"AI_PROVIDER must be one of {VALID_PROVIDERS!r}; got "
        f"{AI_PROVIDER!r}. Set it in apps/backend/.env.",
        kind="config",
    )


# ---------------------------------------------------------------------------
# Gemini branch
# ---------------------------------------------------------------------------

_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"
_GEMINI_REQUEST_TIMEOUT = float(os.environ.get("AI_REQUEST_TIMEOUT_S", "30"))

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise AIProviderError(
            "GEMINI_API_KEY is not set but AI_PROVIDER=gemini.",
            kind="config",
        )
    from google import genai  # local import so tests can monkeypatch cleanly
    _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _translate_gemini_error(exc: Exception) -> AIProviderError:
    msg = str(exc)
    lowered = msg.lower()
    if any(s in lowered for s in ("rate limit", "quota", "429", "resource_exhausted")):
        return AIProviderError(f"Gemini rate limit / quota exhausted: {msg}", kind="rate_limit")
    if any(s in lowered for s in ("401", "403", "permission", "unauthorized", "invalid api key", "api key not valid")):
        return AIProviderError(f"Gemini auth failure: {msg}", kind="auth")
    if "timeout" in lowered or "timed out" in lowered:
        return AIProviderError(f"Gemini request timed out: {msg}", kind="timeout")
    return AIProviderError(f"Gemini upstream error: {msg}", kind="upstream")


def _gemini_vision(image_bytes: bytes, mime_type: str, prompt: str) -> str:
    client = _get_gemini_client()
    try:
        from google.genai import types
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
        )
    except AIProviderError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _translate_gemini_error(exc) from exc
    text = getattr(response, "text", None)
    if not text:
        raise AIProviderError("Gemini returned an empty response.", kind="upstream")
    return text.strip()


def _gemini_text(prompt: str) -> str:
    client = _get_gemini_client()
    try:
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
        )
    except AIProviderError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _translate_gemini_error(exc) from exc
    text = getattr(response, "text", None)
    if not text:
        raise AIProviderError("Gemini returned an empty response.", kind="upstream")
    return text.strip()


# ---------------------------------------------------------------------------
# OpenRouter branch (OpenAI-compatible over httpx — no extra SDK)
# ---------------------------------------------------------------------------

_OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def _openrouter_headers() -> dict[str, str]:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise AIProviderError(
            "OPENROUTER_API_KEY is not set but AI_PROVIDER=openrouter.",
            kind="config",
        )
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "https://localhost"),
        "X-Title": os.environ.get("OPENROUTER_APP_TITLE", "AccessibilityAuditor"),
    }


def _openrouter_model() -> str:
    model = os.environ.get("OPENROUTER_MODEL", "").strip()
    if not model:
        raise AIProviderError(
            "OPENROUTER_MODEL is not set but AI_PROVIDER=openrouter.",
            kind="config",
        )
    return model


def _openrouter_post(payload: dict[str, Any]) -> str:
    try:
        resp = httpx.post(
            _OPENROUTER_ENDPOINT,
            headers=_openrouter_headers(),
            json=payload,
            timeout=_GEMINI_REQUEST_TIMEOUT,
        )
    except httpx.TimeoutException as exc:
        raise AIProviderError(f"OpenRouter request timed out: {exc}", kind="timeout") from exc
    except httpx.HTTPError as exc:
        raise AIProviderError(f"OpenRouter upstream error: {exc}", kind="upstream") from exc

    if resp.status_code == 401 or resp.status_code == 403:
        raise AIProviderError(f"OpenRouter auth failure: {resp.status_code} {resp.text}", kind="auth")
    if resp.status_code == 429:
        raise AIProviderError(f"OpenRouter rate limit / quota: {resp.text}", kind="rate_limit")
    if resp.status_code >= 400:
        raise AIProviderError(f"OpenRouter upstream error: {resp.status_code} {resp.text}", kind="upstream")

    try:
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError) as exc:
        raise AIProviderError(f"OpenRouter returned unexpected shape: {resp.text}", kind="upstream") from exc


def _openrouter_vision(image_bytes: bytes, mime_type: str, prompt: str) -> str:
    import base64
    b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": _openrouter_model(),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                    },
                ],
            },
        ],
    }
    return _openrouter_post(payload)


def _openrouter_text(prompt: str) -> str:
    payload = {
        "model": _openrouter_model(),
        "messages": [{"role": "user", "content": prompt}],
    }
    return _openrouter_post(payload)


# ---------------------------------------------------------------------------
# Public dispatch — the only functions the fixers should call.
# ---------------------------------------------------------------------------


def generate_vision(image_bytes: bytes, mime_type: str, prompt: str) -> str:
    """Vision-capable completion. Raises AIProviderError on failure."""
    if AI_PROVIDER == "gemini":
        return _gemini_vision(image_bytes, mime_type, prompt)
    return _openrouter_vision(image_bytes, mime_type, prompt)


def generate_text(prompt: str) -> str:
    """Text-only completion. Raises AIProviderError on failure."""
    if AI_PROVIDER == "gemini":
        return _gemini_text(prompt)
    return _openrouter_text(prompt)


def get_active_provider() -> str:
    return AI_PROVIDER


def get_active_model() -> Optional[str]:
    if AI_PROVIDER == "gemini":
        return _GEMINI_MODEL
    try:
        return _openrouter_model()
    except AIProviderError:
        return None
