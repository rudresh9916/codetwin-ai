"""Pluggable LLM providers (Anthropic Claude, OpenAI-compatible, Ollama) using only the standard library.

Every provider supports blocking `complete()` and incremental `stream()`.
When no provider is configured the app keeps working in deterministic "offline" mode.
"""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Iterator

from ..config import load_settings


class LLMError(RuntimeError):
    pass


def _ssl_ctx():
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _post(url: str, headers: dict, body: dict, timeout: int = 120, stream: bool = False):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json", **headers}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx() if url.startswith("https") else None)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        raise LLMError(f"{e.code} from provider: {detail}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"Cannot reach provider: {e.reason}") from e
    if stream:
        return resp
    with resp:
        return json.loads(resp.read().decode())


def _sse_lines(resp) -> Iterator[str]:
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if line.startswith("data:"):
                yield line[5:].strip()


class Provider:
    name = "none"
    model = ""

    def available(self) -> bool:
        return False

    def complete(self, system: str, messages: list[dict], max_tokens: int = 1500, temperature: float = 0.2) -> str:
        return "".join(self.stream(system, messages, max_tokens, temperature))

    def stream(self, system: str, messages: list[dict], max_tokens: int = 1500, temperature: float = 0.2) -> Iterator[str]:
        raise LLMError("No LLM provider configured")


DEFAULT_ANTHROPIC_MODEL = "claude-opus-5-5"
# Current Claude models think adaptively and that thinking shares the max_tokens budget, so callers' small
# answer-length caps get headroom. Sampling params (temperature) are rejected by these models and never sent.
_ANTHROPIC_MIN_TOKENS = 16000
# Models without the `effort` control (incl. dated IDs such as claude-sonnet-4-20250514).
_LEGACY_ANTHROPIC = ("claude-3", "claude-haiku", "claude-sonnet-4-5", "claude-sonnet-4-0", "claude-sonnet-4-2",
                     "claude-opus-4-0", "claude-opus-4-1", "claude-opus-4-2")
_FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")


class Anthropic(Provider):
    """Claude via the official `anthropic` SDK (streaming, adaptive thinking, effort, server-side refusal fallback)."""
    name = "anthropic"

    def __init__(self, key: str, model: str, base: str = "https://api.anthropic.com", effort: str = "medium"):
        self.key, self.model, self.effort = key, model, effort or "medium"
        self.base = (base or "https://api.anthropic.com").rstrip("/")

    def available(self):
        return bool(self.key)

    def _client(self):
        import anthropic
        return anthropic.Anthropic(api_key=self.key, base_url=self.base)

    def _params(self, system, messages, max_tokens):
        params = {"model": self.model, "system": system, "messages": messages}
        if self.model.startswith(_LEGACY_ANTHROPIC):
            params["max_tokens"] = max(max_tokens, 1024)
            return params
        params["max_tokens"] = max(max_tokens, _ANTHROPIC_MIN_TOKENS)
        params["output_config"] = {"effort": self.effort}
        if self.model in _FALLBACK_MODELS and self.base == "https://api.anthropic.com":
            # If a safety classifier declines, the API re-runs the request on Anthropic's recommended fallback model.
            params["betas"] = ["server-side-fallback-2026-07-01"]
            params["fallbacks"] = "default"
        return params

    def stream(self, system, messages, max_tokens=1500, temperature=0.2):
        import anthropic
        try:
            with self._client().beta.messages.stream(**self._params(system, messages, max_tokens)) as s:
                yield from s.text_stream
                final = s.get_final_message()
        except anthropic.AuthenticationError as e:
            raise LLMError("Anthropic rejected the API key (401). Check it in Settings.") from e
        except anthropic.NotFoundError as e:
            raise LLMError(f"Model '{self.model}' was not found for this API key (404).") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Rate limited by Anthropic (429). Try again shortly.") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"{e.status_code} from Anthropic: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"Cannot reach Anthropic: {e}") from e
        if final.stop_reason == "refusal":
            raise LLMError("Claude declined this request.")
        if final.stop_reason == "max_tokens":
            yield "\n\n…(answer truncated at the token limit)"


class OpenAI(Provider):
    name = "openai"

    def __init__(self, key: str, model: str, base: str):
        self.key, self.model, self.base = key, model, base.rstrip("/")

    def available(self):
        return bool(self.key)

    def _body(self, system, messages, max_tokens, temperature, stream):
        return {"model": self.model, "messages": [{"role": "system", "content": system}] + messages, "max_tokens": max_tokens,
                "temperature": temperature, "stream": stream}

    def complete(self, system, messages, max_tokens=1500, temperature=0.2):
        r = _post(f"{self.base}/chat/completions", {"authorization": f"Bearer {self.key}"},
                  self._body(system, messages, max_tokens, temperature, False))
        return r["choices"][0]["message"]["content"] or ""

    def stream(self, system, messages, max_tokens=1500, temperature=0.2):
        resp = _post(f"{self.base}/chat/completions", {"authorization": f"Bearer {self.key}"},
                     self._body(system, messages, max_tokens, temperature, True), stream=True)
        for data in _sse_lines(resp):
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"].get("content")
            except Exception:
                continue
            if delta:
                yield delta

    def embed(self, texts: list[str]) -> list[list[float]]:
        r = _post(f"{self.base}/embeddings", {"authorization": f"Bearer {self.key}"}, {"model": "text-embedding-3-small", "input": texts})
        return [d["embedding"] for d in r["data"]]


class Ollama(Provider):
    name = "ollama"

    def __init__(self, url: str, model: str, embed_model: str = "nomic-embed-text"):
        self.url, self.model, self.embed_model = url.rstrip("/"), model, embed_model

    def available(self):
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    def stream(self, system, messages, max_tokens=1500, temperature=0.2):
        req = urllib.request.Request(f"{self.url}/api/chat", method="POST", headers={"content-type": "application/json"},
                                     data=json.dumps({"model": self.model, "stream": True,
                                                      "messages": [{"role": "system", "content": system}] + messages,
                                                      "options": {"temperature": temperature, "num_predict": max_tokens}}).encode())
        try:
            resp = urllib.request.urlopen(req, timeout=300)
        except Exception as e:
            raise LLMError(f"Ollama error: {e}") from e
        with resp:
            for raw in resp:
                try:
                    ev = json.loads(raw.decode())
                except Exception:
                    continue
                txt = ev.get("message", {}).get("content")
                if txt:
                    yield txt
                if ev.get("done"):
                    break

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            r = _post(f"{self.url}/api/embeddings", {}, {"model": self.embed_model, "prompt": t}, timeout=60)
            out.append(r["embedding"])
        return out


def get_provider(settings: dict | None = None) -> Provider:
    s = settings or load_settings()
    p = s.get("provider", "anthropic")
    claude = lambda: Anthropic(s["anthropic_api_key"], s.get("anthropic_model") or DEFAULT_ANTHROPIC_MODEL, s.get("anthropic_base_url"),
                               s.get("anthropic_effort"))
    if p == "anthropic" and s.get("anthropic_api_key"):
        return claude()
    if p == "openai" and s.get("openai_api_key"):
        return OpenAI(s["openai_api_key"], s.get("openai_model") or "gpt-4o-mini", s.get("openai_base_url") or "https://api.openai.com/v1")
    if p == "ollama":
        return Ollama(s.get("ollama_url") or "http://localhost:11434", s.get("ollama_model") or "llama3.1", s.get("ollama_embed_model"))
    # fall back to whichever key exists
    if s.get("anthropic_api_key") and p != "none":
        return claude()
    if s.get("openai_api_key") and p != "none":
        return OpenAI(s["openai_api_key"], s.get("openai_model") or "gpt-4o-mini", s.get("openai_base_url") or "https://api.openai.com/v1")
    return Provider()


def ai_status() -> dict:
    p = get_provider()
    ok = p.available() if p.name != "ollama" else p.available()
    return {"provider": p.name, "model": p.model, "available": ok}
