"""Route "Hey Tony, ..." style messages to a configured agent by name.

Used by the phone (iMessage) bridge and the desktop chat endpoint so both
behave the same:

* Only a message that *starts* by addressing an agent is routed
  ("Hey Tony, ...", "Tony, ...", "@Tony ...", "yo tony ..."). Names in the
  middle of a sentence are left alone.
* Names come from each agent's ``name`` plus optional ``config.aliases``.
* Two agents sharing a name is reported, never guessed.
* The agent answers with its own instructions (identity) on its own model;
  if that model can't call tools, the default model runs it and the reply
  says so.
* Chat-invoked agents get read-only tools only, so a text message can't
  make an agent run shell commands or write files.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Tools a chat-invoked agent may use: search/read/reason only.
SAFE_CHAT_TOOLS = (
    "knowledge_search",
    "knowledge_sql",
    "scan_chunks",
    "think",
    "web_search",
    "calculator",
    "memory_retrieve",
    "memory_search",
    "calendar_upcoming",
    "calendar_search",
    "retrieval",
)

_GREETING = r"(?:(?:hey|hi|hello|yo|ok(?:ay)?|ask)\s+)?"


@dataclass
class AgentMention:
    """Outcome of resolving an addressed agent name."""

    agent: Optional[Dict[str, Any]] = None
    message: str = ""
    name: str = ""
    error: str = ""
    candidates: List[str] = field(default_factory=list)

    @property
    def routed(self) -> bool:
        return self.agent is not None


def _names(agent: Dict[str, Any]) -> List[str]:
    config = agent.get("config") or {}
    names = [agent.get("name", "")] + list(config.get("aliases") or [])
    return [n.strip() for n in names if isinstance(n, str) and n.strip()]


def resolve_mention(text: str, agents: List[Dict[str, Any]]) -> AgentMention:
    """Return which agent (if any) *text* is addressed to."""
    stripped = text.strip()
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for agent in agents:
        if agent.get("status") == "archived":
            continue
        for name in _names(agent):
            by_name.setdefault(name.lower(), []).append(agent)

    # Longest names first so "Tony Stark" wins over "Tony".
    for name in sorted(by_name, key=len, reverse=True):
        pattern = re.compile(
            rf"^\s*{_GREETING}@?{re.escape(name)}\b\s*[,:!\-—]?\s*",
            re.IGNORECASE,
        )
        match = pattern.match(stripped)
        if not match:
            continue
        # "Hey Tony" alone, or followed by punctuation/a request.
        rest = stripped[match.end() :].strip()
        greeted = bool(
            re.match(r"^\s*(hey|hi|hello|yo|ok|okay|ask)\s", stripped, re.IGNORECASE)
        )
        punctuated = bool(re.search(r"[,:!\-—]\s*$", stripped[: match.end()]))
        if not (greeted or punctuated or stripped.startswith("@") or not rest):
            continue
        matches = {a.get("id"): a for a in by_name[name]}
        if len(matches) > 1:
            return AgentMention(
                name=name,
                message=rest,
                error=(
                    f"You have {len(matches)} agents named {name.title()}. "
                    "Rename one (or give it an alias) so I know who you mean."
                ),
                candidates=[str(i) for i in matches],
            )
        return AgentMention(agent=next(iter(matches.values())), message=rest, name=name)
    return AgentMention(message=stripped)


def model_capabilities(engine: Any, model: str) -> Optional[List[str]]:
    """Ollama's capability list for *model* (None when it can't be read)."""
    try:
        import httpx

        host = getattr(engine, "_host", "") or "http://localhost:11434"
        resp = httpx.post(f"{host}/api/show", json={"model": model}, timeout=10)
        caps = resp.json().get("capabilities")
        return [str(c) for c in caps] if isinstance(caps, list) else None
    except Exception:
        return None


def model_supports_tools(engine: Any, model: str) -> bool:
    """Best-effort check via Ollama's capabilities (True if unknown)."""
    caps = model_capabilities(engine, model)
    return True if caps is None else "tools" in caps


def model_supports_vision(engine: Any, model: str) -> bool:
    """True only when the model is known to accept images."""
    if model == "jarvis-auto":  # failover picks a vision model for images
        return True
    caps = model_capabilities(engine, model)
    return bool(caps) and "vision" in caps


def run_named_agent(
    mention: AgentMention,
    *,
    engine: Any,
    default_model: str,
    context: str = "",
    images: Optional[List[str]] = None,
    bus: Any = None,
    supports_tools: Callable[[Any, str], bool] = model_supports_tools,
) -> Dict[str, str]:
    """Run the addressed agent once; returns ``{content, agent, model, note}``."""
    import openjarvis.tools  # noqa: F401  (register tools)
    from openjarvis.agents.orchestrator import OrchestratorAgent
    from openjarvis.core.registry import ToolRegistry
    from openjarvis.core.types import Message, Role
    from openjarvis.prompt.persona import persona_block
    from openjarvis.tools._stubs import BaseTool

    agent = mention.agent or {}
    config = agent.get("config") or {}
    name = agent.get("name", mention.name.title())
    wanted = config.get("model") or default_model
    model, note = wanted, ""
    if not supports_tools(engine, wanted):
        model = default_model
        note = f"({name}'s model {wanted} can't use tools, so {model} ran this.)"

    allowed = set(config.get("tools") or SAFE_CHAT_TOOLS) & set(SAFE_CHAT_TOOLS)
    # Knowledge tools need the store/engine wiring the research agent uses.
    from openjarvis.agents.tool_resolver import build_deep_research_tools

    tools: List[Any] = [
        t
        for t in build_deep_research_tools(engine, model)
        if getattr(getattr(t, "spec", None), "name", "") in allowed
    ]
    have = {t.spec.name for t in tools}
    for tool_name in sorted(allowed - have):
        if not ToolRegistry.contains(tool_name):
            continue
        registered = ToolRegistry.get(tool_name)
        try:
            tools.append(registered() if isinstance(registered, type) else registered)
        except Exception:
            continue
    tools = [t for t in tools if isinstance(t, BaseTool)]

    identity = config.get("system_prompt") or config.get("instruction") or ""
    system_prompt = (
        f"You are {name}, one of the user's agents. You're answering them "
        f"directly in chat because they addressed you by name.\n\n{identity}"
        f"{persona_block()}\n\nAnswer the request in chat. Don't claim you ran "
        "tools or sent anything unless you actually did."
    )
    request = mention.message or "Introduce yourself in one sentence."
    if context:
        request = f"Conversation so far:\n{context}\n\nRequest for you: {request}"

    runner = OrchestratorAgent(
        engine=engine,
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        bus=bus,
        max_turns=int(config.get("max_turns") or 8),
        agent_id=f"chat:{agent.get('id', name)}",
    )
    if images:
        # Attach photos to the request turn for vision-capable models.
        original = runner._build_messages

        def _with_images(*args: Any, **kwargs: Any) -> List[Message]:
            msgs = original(*args, **kwargs)
            for msg in reversed(msgs):
                if msg.role == Role.USER:
                    msg.images = list(images)
                    break
            return msgs

        runner._build_messages = _with_images  # type: ignore[method-assign]
    result = runner.run(request)
    content = (result.content or "").strip() or f"{name} came back empty-handed."
    return {"content": content, "agent": name, "model": model, "note": note}


__all__ = [
    "AgentMention",
    "SAFE_CHAT_TOOLS",
    "model_capabilities",
    "model_supports_tools",
    "model_supports_vision",
    "resolve_mention",
    "run_named_agent",
]
