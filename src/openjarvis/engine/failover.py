"""Best-first model failover engine ("jarvis-auto").

Wraps the server's local engine. Requests for ``jarvis-auto`` walk the ranked
model chain (``cloud_router.model_chain()``), best first, and move down the
list when a model is unusable, out of credits, rate limited or failing. The
local model is always last, so a reply always comes.

Every call gets the full message list, so when the chain switches models
mid-conversation (or mid tool loop) the next model picks up the whole
conversation: history, tool calls and tool results. The persona lives in the
system prompt the agents build, so every model answers as the same Jarvis.

Subscription CLIs (Claude Code / Codex) can't take OpenAI ``tools``; they get
a small JSON tool-call protocol in the prompt instead, so agents keep their
tools whichever model answers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from typing import Any, Callable, Dict, List, Optional

import httpx

from openjarvis.core.types import Message
from openjarvis.engine._base import (
    EngineConnectionError,
    InferenceEngine,
    messages_to_dicts,
)
from openjarvis.engine._stubs import StreamChunk

logger = logging.getLogger(__name__)

AUTO_MODEL = "jarvis-auto"

# Native (non OpenAI-compat table) providers reachable over an
# OpenAI-compatible chat endpoint: provider -> (base URL, key names).
_NATIVE_APIS: Dict[str, tuple[str, tuple[str, ...]]] = {
    "google": (
        "https://generativelanguage.googleapis.com/v1beta/openai",
        ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    ),
    "xai": ("https://api.x.ai/v1", ("XAI_API_KEY",)),
    "openai": ("https://api.openai.com/v1", ("OPENAI_API_KEY",)),
    "anthropic": ("https://api.anthropic.com/v1", ("ANTHROPIC_API_KEY",)),
    "openrouter": ("https://openrouter.ai/api/v1", ("OPENROUTER_API_KEY",)),
}

# Chain models known to accept images over these APIs.
_VISION_PREFIXES = (
    "gemini-",
    "grok-4",
    "gpt-4",
    "gpt-5",
    "claude-",
    "github/openai/gpt-4",
    "mistral/pixtral",
)

# How long to skip a model after it fails, by failure kind (seconds).
_COOLDOWN = {"quota": 30 * 60, "auth": 6 * 3600, "other": 2 * 60}
_QUOTA_WORDS = re.compile(
    r"quota|credit|rate.?limit|usage limit|insufficient|exhausted|too many|"
    r"billing|limit reached|resource_exhausted",
    re.IGNORECASE,
)

_TOOL_PROTOCOL = """\
## Tools

You can call these tools to look things up or act. To call tools, reply with
ONLY a JSON object and nothing else, exactly like:
{{"tool_calls": [{{"name": "<tool name>", "arguments": {{...}}}}]}}
You'll get the results back, then you can call more tools or answer.
When you're ready to answer the user, reply with plain text (no JSON).

Available tools (JSON Schema parameters):
{tools}"""

_MAX_TOOL_RESULT_CHARS = 6000


def _classify(exc: Exception) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", 0)
    if status in (401, 403):
        return "auth"
    if status in (402, 429) or _QUOTA_WORDS.search(str(exc)):
        return "quota"
    return "other"


def _guess_mime(b64: str) -> str:
    for prefix, mime in (
        ("/9j/", "image/jpeg"),
        ("iVBOR", "image/png"),
        ("R0lGOD", "image/gif"),
        ("UklGR", "image/webp"),
    ):
        if b64.startswith(prefix):
            return mime
    return "image/jpeg"


def _openai_messages(messages: Sequence[Message]) -> List[Dict[str, Any]]:
    """OpenAI chat format; Ollama-style ``images`` become ``image_url`` parts."""
    out = []
    for d in messages_to_dicts(messages):
        images = d.pop("images", None)
        if images:
            parts: List[Dict[str, Any]] = []
            if d.get("content"):
                parts.append({"type": "text", "text": d["content"]})
            for img in images:
                url = img if img.startswith("data:") else (
                    f"data:{_guess_mime(img)};base64,{img}"
                )
                parts.append({"type": "image_url", "image_url": {"url": url}})
            d["content"] = parts
        if d.get("content") is None:
            d["content"] = ""
        out.append(d)
    return out


def _has_images(messages: Sequence[Message]) -> bool:
    return any(getattr(m, "images", None) for m in messages)


def _tool_specs(tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    specs = []
    for t in tools or []:
        fn = t.get("function", t)
        specs.append(
            {
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "parameters": fn.get("parameters", {}),
            }
        )
    return specs


def _cli_transcript(messages: Sequence[Message]) -> tuple[str, str]:
    """(system, transcript) including tool calls and results."""
    system = "\n\n".join(
        m.content for m in messages if m.role.value == "system" and m.content
    )
    lines: List[str] = []
    for m in messages:
        role = m.role.value
        if role == "user":
            lines.append(f"User: {m.content}")
        elif role == "assistant":
            if m.content:
                lines.append(f"Assistant: {m.content}")
            for tc in m.tool_calls or []:
                lines.append(
                    f"Assistant called tool {tc.name} with {tc.arguments}"
                )
        elif role == "tool":
            result = (m.content or "")[:_MAX_TOOL_RESULT_CHARS]
            lines.append(f"Tool result ({m.name or 'tool'}): {result}")
    if len(lines) == 1 and lines[0].startswith("User: "):
        return system, lines[0][len("User: ") :]
    return system, (
        "Conversation so far (continue it; reply only as the assistant):\n\n"
        + "\n\n".join(lines)
    )


def parse_cli_tool_calls(text: str) -> Optional[List[Dict[str, Any]]]:
    """Tool calls from a CLI reply that follows the JSON protocol, else None."""
    # Models sometimes add a sentence or a code fence around the JSON, so
    # find the tool_calls object anywhere in the reply.
    start = text.find('{"tool_calls"')
    if start < 0:
        match = re.search(r'\{\s*"tool_calls"\s*:', text)
        if not match:
            return None
        start = match.start()
    try:
        data, _end = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return None
    calls = data.get("tool_calls") if isinstance(data, dict) else None
    if not isinstance(calls, list) or not calls:
        return None
    out = []
    for call in calls:
        if not isinstance(call, dict) or not call.get("name"):
            return None
        args = call.get("arguments", {})
        out.append(
            {
                "id": f"call_{uuid.uuid4().hex[:12]}",
                "name": str(call["name"]),
                "arguments": args if isinstance(args, str) else json.dumps(args),
            }
        )
    return out


class FailoverEngine(InferenceEngine):
    """``jarvis-auto``: best available model first, local model last."""

    engine_id = "failover"

    def __init__(
        self,
        inner: InferenceEngine,
        local_model: str,
        *,
        chain: Optional[Callable[[], List[str]]] = None,
        usable: Optional[Callable[[], Dict[str, bool]]] = None,
        http: Optional[httpx.Client] = None,
        run_cli: Optional[Callable[[str, str, str, str], str]] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        from openjarvis.server import cloud_router

        self._inner = inner
        self._local_model = local_model
        self._chain = chain or cloud_router.model_chain
        self._usable = usable or cloud_router._usable_models
        self._http = http or httpx.Client(timeout=180.0)
        self._run_cli = run_cli or cloud_router.run_cli_sync
        self._clock = clock
        self._cooling: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.last_model = ""
        self.is_cloud = False
        self._model = AUTO_MODEL  # what agents built from this engine serve

    # -- passthrough ---------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        # _host etc. for capability checks against the local engine.
        if name.startswith("__") or name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)

    def list_models(self) -> List[str]:
        try:
            models = list(self._inner.list_models())
        except Exception:
            models = []
        return [AUTO_MODEL, *[m for m in models if m != AUTO_MODEL]]

    def health(self) -> bool:
        return True

    def can_serve(self, model: str) -> bool:
        return model == AUTO_MODEL or self._inner.can_serve(model)

    def close(self) -> None:
        self._inner.close()

    def prepare(self, model: str) -> None:
        self._inner.prepare(self._local_model if model == AUTO_MODEL else model)

    # -- chain ---------------------------------------------------------------

    def candidates(self, *, needs_vision: bool = False) -> List[str]:
        """Usable chain models right now, best first (local appended last)."""
        from openjarvis.server import cloud_router
        from openjarvis.server.cloud_router import get_provider

        try:
            usable = self._usable()
        except Exception:
            usable = {}
        now = self._clock()
        out = []
        for model in self._chain():
            provider = get_provider(model)
            if provider is None or not usable.get(provider, False):
                continue
            if self._cooling.get(model, 0) > now:
                continue
            if needs_vision and (
                provider in cloud_router.SUBSCRIPTION_PROVIDERS
                or not model.startswith(_VISION_PREFIXES)
            ):
                continue
            out.append(model)
        out.append(self._local_model)
        return out

    def _cool(self, model: str, exc: Exception) -> None:
        kind = _classify(exc)
        with self._lock:
            self._cooling[model] = self._clock() + _COOLDOWN[kind]
        logger.warning(
            "jarvis-auto: %s failed (%s: %s); moving down the list",
            model,
            kind,
            str(exc)[:200],
        )

    def generate(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if model != AUTO_MODEL:
            return self._inner.generate(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        tools = kwargs.get("tools")
        last_exc: Optional[Exception] = None
        for candidate in self.candidates(needs_vision=_has_images(messages)):
            try:
                if candidate == self._local_model:
                    result = self._inner.generate(
                        messages,
                        model=candidate,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        **kwargs,
                    )
                else:
                    result = self._generate_cloud(
                        candidate, messages, temperature, max_tokens, tools
                    )
            except Exception as exc:
                last_exc = exc
                if candidate != self._local_model:
                    self._cool(candidate, exc)
                continue
            if not (result.get("content") or "").strip() and not result.get(
                "tool_calls"
            ):
                last_exc = ValueError(f"{candidate} returned an empty reply")
                if candidate != self._local_model:
                    self._cool(candidate, last_exc)
                continue
            result["model"] = candidate
            self._record(candidate)
            return result
        raise EngineConnectionError(f"jarvis-auto: every model failed ({last_exc})")

    def _record(self, model: str) -> None:
        self.last_model = model
        try:
            from openjarvis.server.cloud_router import LAST_AUTO_MODEL

            LAST_AUTO_MODEL["model"] = model
        except Exception:
            pass

    def _generate_cloud(
        self,
        model: str,
        messages: Sequence[Message],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        from openjarvis.server import cloud_router

        provider = cloud_router.get_provider(model)
        if provider in cloud_router.SUBSCRIPTION_PROVIDERS:
            return self._generate_cli(provider, model, messages, tools)
        if provider in cloud_router.OPENAI_COMPAT:
            prefix, base, key_name, _label = cloud_router.OPENAI_COMPAT[provider]
            api_model, key_names = model[len(prefix) :], (key_name,)
        elif provider in _NATIVE_APIS:
            base, key_names = _NATIVE_APIS[provider]
            api_model = (
                cloud_router._openrouter_model_id(model)
                if provider == "openrouter"
                else model
            )
        else:
            raise ValueError(f"jarvis-auto can't call provider {provider!r}")
        keys = cloud_router._load_keys()
        api_key = next((keys[k] for k in key_names if keys.get(k)), "")
        if not api_key:
            raise ValueError(f"no key for {provider}")
        payload: Dict[str, Any] = {
            "model": api_model,
            "messages": _openai_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        resp = self._http.post(
            f"{base.rstrip('/')}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        result: Dict[str, Any] = {
            "content": msg.get("content") or "",
            "usage": data.get("usage") or {},
            "finish_reason": choice.get("finish_reason") or "stop",
        }
        calls = msg.get("tool_calls") or []
        if calls:
            result["tool_calls"] = [
                {
                    "id": c.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                    "name": (c.get("function") or {}).get("name", ""),
                    "arguments": (c.get("function") or {}).get("arguments") or "{}",
                }
                for c in calls
            ]
        return result

    def _generate_cli(
        self,
        provider: str,
        model: str,
        messages: Sequence[Message],
        tools: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        system, prompt = _cli_transcript(messages)
        specs = _tool_specs(tools)
        if specs:
            protocol = _TOOL_PROTOCOL.format(tools=json.dumps(specs, indent=1))
            system = f"{system}\n\n{protocol}" if system else protocol
        text = self._run_cli(provider, model, system, prompt)
        calls = parse_cli_tool_calls(text) if specs else None
        if calls:
            return {"content": "", "tool_calls": calls, "finish_reason": "tool_calls"}
        return {"content": text, "finish_reason": "stop", "usage": {}}

    # -- streaming -----------------------------------------------------------

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        if model != AUTO_MODEL:
            async for token in self._inner.stream(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            ):
                yield token
            return
        result = await asyncio.to_thread(
            self.generate,
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        if result.get("content"):
            yield result["content"]

    async def stream_full(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        if model != AUTO_MODEL:
            async for chunk in self._inner.stream_full(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            ):
                yield chunk
            return
        result = await asyncio.to_thread(
            self.generate,
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        if result.get("content"):
            yield StreamChunk(content=result["content"])
        calls = result.get("tool_calls") or []
        if calls:
            yield StreamChunk(
                tool_calls=[
                    {
                        "index": i,
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": c["arguments"]},
                    }
                    for i, c in enumerate(calls)
                ]
            )
        yield StreamChunk(
            finish_reason="tool_calls" if calls else "stop",
            usage=result.get("usage") or None,
        )


__all__ = ["AUTO_MODEL", "FailoverEngine", "parse_cli_tool_calls"]
