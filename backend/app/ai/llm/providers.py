"""LLM provider implementations.

* ``openai_compatible`` — any server implementing the OpenAI Chat Completions API (OpenAI, Azure
  OpenAI-compatible gateways, OpenRouter, Together, Groq, vLLM, Ollama, LM Studio …). Plain HTTP.
* ``anthropic`` — Claude via the official Anthropic SDK, with prompt caching on the system prompt.
* ``fake`` — deterministic scripted responses for tests.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from app.ai.llm.base import LLMError, LLMNotConfigured, LLMProvider, LLMRequest, LLMResponse


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(self, base_url: str, api_key: str):
        if not base_url:
            raise LLMNotConfigured("LLM base URL is not configured")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def complete(self, req: LLMRequest) -> LLMResponse:
        body: dict[str, Any] = {
            "model": req.model,
            "messages": [{"role": "system", "content": req.system}, {"role": "user", "content": req.user}],
            "max_tokens": req.max_tokens,
        }
        if req.temperature is not None:
            body["temperature"] = req.temperature
        if req.json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=req.timeout)
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            raise LLMError(f"LLM network error: {e}", retryable=True) from e
        if r.status_code == 400 and req.json_mode and "response_format" in r.text:
            # Some compatible servers don't support JSON mode — retry without it.
            return self.complete(LLMRequest(**{**req.__dict__, "json_mode": False}))
        if r.status_code in (401, 403):
            raise LLMError("LLM provider rejected the API key", retryable=False)
        if r.status_code == 429 or r.status_code >= 500:
            raise LLMError(f"LLM provider HTTP {r.status_code}", retryable=True)
        if r.status_code != 200:
            raise LLMError(f"LLM provider HTTP {r.status_code}: {r.text[:300]}", retryable=False)
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage") or {}
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        return LLMResponse(
            text=(choice.get("message") or {}).get("content") or "",
            model=data.get("model", req.model),
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
            cached_tokens=int(cached),
            stop_reason=choice.get("finish_reason"),
        )


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, base_url: str | None = None):
        import anthropic

        if not api_key:
            raise LLMNotConfigured("Anthropic API key is not configured")
        kw: dict[str, Any] = {"api_key": api_key, "max_retries": 0}  # retries handled by the runtime
        if base_url and "anthropic.com" not in base_url and "openai.com" not in base_url:
            kw["base_url"] = base_url
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(**kw)

    def complete(self, req: LLMRequest) -> LLMResponse:
        a = self._anthropic
        params: dict[str, Any] = {
            "model": req.model,
            "max_tokens": max(req.max_tokens, 4000),  # leave room for adaptive thinking
            # Stable agent instructions first → cacheable prefix.
            "system": [{"type": "text", "text": req.system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": req.user}],
        }
        if req.effort:
            params["output_config"] = {"effort": req.effort}
        try:
            msg = self.client.with_options(timeout=req.timeout).messages.create(**params)
        except a.AuthenticationError as e:
            raise LLMError("Anthropic rejected the API key", retryable=False) from e
        except a.PermissionDeniedError as e:
            raise LLMError("Anthropic API key lacks permission", retryable=False) from e
        except a.NotFoundError as e:
            raise LLMError(f"Unknown Anthropic model '{req.model}'", retryable=False) from e
        except a.BadRequestError as e:
            raise LLMError(f"Anthropic bad request: {e.message}", retryable=False) from e
        except a.RateLimitError as e:
            raise LLMError("Anthropic rate limit", retryable=True) from e
        except a.APIStatusError as e:
            raise LLMError(f"Anthropic HTTP {e.status_code}", retryable=e.status_code >= 500) from e
        except a.APIConnectionError as e:
            raise LLMError("Anthropic connection error", retryable=True) from e
        if msg.stop_reason == "refusal":
            raise LLMError("Model declined the request (refusal)", retryable=False)
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        u = msg.usage
        return LLMResponse(
            text=text, model=msg.model,
            input_tokens=int(u.input_tokens or 0) + int(getattr(u, "cache_creation_input_tokens", 0) or 0),
            output_tokens=int(u.output_tokens or 0),
            cached_tokens=int(getattr(u, "cache_read_input_tokens", 0) or 0),
            stop_reason=msg.stop_reason,
        )


class FakeProvider(LLMProvider):
    """Test double. ``handler(req) -> dict | str`` produces the response body."""

    name = "fake"

    def __init__(self, handler: Callable[[LLMRequest], Any]):
        self.handler = handler
        self.calls: list[LLMRequest] = []

    def complete(self, req: LLMRequest) -> LLMResponse:
        self.calls.append(req)
        out = self.handler(req)
        if isinstance(out, Exception):
            raise out
        text = out if isinstance(out, str) else json.dumps(out)
        return LLMResponse(text=text, model=req.model, input_tokens=len(req.system + req.user) // 4,
                           output_tokens=len(text) // 4)


_override: LLMProvider | None = None


def set_provider_override(p: LLMProvider | None) -> None:
    """Tests use this to inject a FakeProvider."""
    global _override
    _override = p


def build_provider(cfg: dict[str, Any]) -> LLMProvider:
    if _override is not None:
        return _override
    kind = cfg.get("provider", "none")
    if kind == "openai_compatible":
        return OpenAICompatibleProvider(cfg.get("base_url", ""), cfg.get("api_key", ""))
    if kind == "anthropic":
        return AnthropicProvider(cfg.get("api_key", ""), cfg.get("base_url"))
    raise LLMNotConfigured("No LLM provider configured")


def llm_available(cfg: dict[str, Any]) -> bool:
    if _override is not None:
        return True
    kind = cfg.get("provider", "none")
    if kind == "anthropic":
        return bool(cfg.get("api_key"))
    if kind == "openai_compatible":
        return bool(cfg.get("base_url"))  # local servers (Ollama, vLLM) may need no key
    return False
