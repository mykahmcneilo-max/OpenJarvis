"""ChannelBridge — unified orchestrator for multi-channel messaging."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from openjarvis.channels._stubs import BaseChannel, ChannelStatus
from openjarvis.core.events import EventBus, EventType
from openjarvis.server.session_store import SessionStore

logger = logging.getLogger(__name__)

_DEFAULT_MAX_LENGTH = 4000
_SMS_MAX_LENGTH = 1600

_HELP_TEXT = """\
Available commands:
/agents — list running agents
/agent <id> status — agent state and current task
/agent <id> <message> — send a message to an agent
/agent <id> pause — pause an agent
/agent <id> resume — resume an agent
/notify <channel> — set where to receive notifications
/sessions — list your active sessions
/more — get the rest of a truncated response
/help — show this message\
"""

# Prior messages passed to the research agent as conversation context
_HISTORY_TURNS = 8

_TEXT_REPLY_RULES = (
    "You are replying by text message. Today is {today}. Search the user's "
    "data and answer directly with what you find. Do not ask clarifying "
    "questions or end your reply with questions: if the request is broad, "
    "choose the most reasonable reading (e.g. 'this week' = the current "
    "calendar week) and summarize. Keep it short. Use the previous "
    "conversation to understand follow-ups."
)


def _research_prompt(query: str) -> str:
    """Prefix a channel query with texting rules and today's date."""
    today = time.strftime("%A, %B %d, %Y")
    return f"{_TEXT_REPLY_RULES.format(today=today)}\n\n{query}"


# Events the bridge subscribes to for notifications
_NOTIFICATION_EVENTS = [
    EventType.AGENT_TICK_END,
    EventType.AGENT_TICK_ERROR,
    EventType.AGENT_BUDGET_EXCEEDED,
    EventType.SCHEDULER_TASK_END,
]


class ChannelBridge:
    """Orchestrates incoming messages across multiple channel adapters.

    Provides backward-compatible ``send()``/``status()``/``list_channels()``
    so it can replace the old single-channel bridge in ``app.state``.
    """

    def __init__(
        self,
        channels: Dict[str, BaseChannel],
        session_store: SessionStore,
        bus: EventBus,
        system: Any = None,
        agent_manager: Any = None,
        deep_research_agent: Any = None,
    ) -> None:
        self._channels = channels
        self._session_store = session_store
        self._bus = bus
        self._system = system
        self._agent_manager = agent_manager
        self._deep_research_agent = deep_research_agent
        self._notification_timestamps: Dict[str, float] = {}
        self._subscribe_notifications()

    # --------------------------------------------------------------
    # Backward-compatible BaseChannel interface
    # --------------------------------------------------------------

    def connect(self) -> None:
        for ch in self._channels.values():
            ch.connect()

    def disconnect(self) -> None:
        for ch in self._channels.values():
            ch.disconnect()

    def list_channels(self) -> List[str]:
        result: List[str] = []
        for ch in self._channels.values():
            result.extend(ch.list_channels())
        return result

    def status(self) -> ChannelStatus:
        statuses = [ch.status() for ch in self._channels.values()]
        if not statuses:
            return ChannelStatus.DISCONNECTED
        if any(s == ChannelStatus.CONNECTED for s in statuses):
            return ChannelStatus.CONNECTED
        if all(s == ChannelStatus.ERROR for s in statuses):
            return ChannelStatus.ERROR
        return ChannelStatus.DISCONNECTED

    def send(
        self,
        channel: str,
        content: str,
        *,
        conversation_id: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> bool:
        for ch in self._channels.values():
            if channel in ch.list_channels():
                return ch.send(
                    channel,
                    content,
                    conversation_id=conversation_id,
                    metadata=metadata,
                )
        logger.warning("No adapter found for channel %s", channel)
        return False

    # --------------------------------------------------------------
    # Incoming message handling
    # --------------------------------------------------------------

    def handle_incoming(
        self,
        sender_id: str,
        content: str,
        channel_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        max_length: int = _DEFAULT_MAX_LENGTH,
    ) -> str:
        return self.respond(sender_id, content, channel_type, max_length=max_length)[
            "content"
        ]

    def respond(
        self,
        sender_id: str,
        content: str,
        channel_type: str,
        *,
        images: Optional[List[str]] = None,
        max_length: int = _DEFAULT_MAX_LENGTH,
    ) -> Dict[str, str]:
        """Answer one incoming message.

        Returns ``{"content", "agent", "model"}`` so callers can show who
        actually answered. *images* are base64 photos from the message.
        """
        self._session_store.get_or_create(sender_id, channel_type)

        # Command routing
        stripped = content.strip()
        if stripped.startswith("/") and not images:
            result = self._handle_command(sender_id, stripped, channel_type)
            if result is not None:
                return {"content": result, "agent": "Jarvis", "model": ""}

        # Regular chat (optionally addressed to a named agent)
        return self._handle_chat(
            sender_id, stripped, channel_type, max_length, images=images or []
        )

    # --------------------------------------------------------------
    # Command parsing
    # --------------------------------------------------------------

    def _handle_command(
        self,
        sender_id: str,
        content: str,
        channel_type: str,
    ) -> Optional[str]:
        parts = content.split(None, 2)
        cmd = parts[0].lower()

        if cmd == "/help":
            return _HELP_TEXT

        if cmd == "/more":
            return self._handle_more(sender_id, channel_type)

        if cmd == "/notify" and len(parts) >= 2:
            pref = parts[1]
            self._session_store.set_notification_preference(
                sender_id, channel_type, pref
            )
            return f"Notifications will be sent to {pref}."

        if cmd == "/sessions":
            return self._handle_sessions(sender_id)

        if cmd == "/agents":
            return self._handle_agents_list()

        if cmd == "/agent" and len(parts) >= 2:
            agent_id = parts[1]
            rest = parts[2] if len(parts) > 2 else "status"
            return self._handle_agent_command(agent_id, rest)

        # Unknown command — fall through to chat
        return None

    def _handle_more(self, sender_id: str, channel_type: str) -> str:
        session = self._session_store.get_or_create(sender_id, channel_type)
        pending = session.get("pending_response")
        if pending:
            self._session_store.clear_pending_response(sender_id, channel_type)
            return pending
        return "No pending response."

    def _handle_agents_list(self) -> str:
        if not self._agent_manager:
            return "No agent manager configured."
        agents = self._agent_manager.list_agents()
        if not agents:
            return "No agents currently running."
        lines = []
        for a in agents:
            name = a.get("name", a.get("agent_id", "unknown"))
            status = a.get("status", "unknown")
            lines.append(f"  {name} — {status}")
        return "Running agents:\n" + "\n".join(lines)

    def _handle_agent_command(self, agent_id: str, action: str) -> str:
        if not self._agent_manager:
            return "No agent manager configured."
        action_lower = action.strip().lower()
        if action_lower == "status":
            state = self._agent_manager.get_agent(agent_id)
            if state is None:
                return f"Agent '{agent_id}' not found."
            name = state.get("name", agent_id)
            status = state.get("status", "unknown")
            return f"Agent '{name}': {status}"
        if action_lower == "pause":
            self._agent_manager.pause_agent(agent_id)
            return f"Agent '{agent_id}' paused."
        if action_lower == "resume":
            self._agent_manager.resume_agent(agent_id)
            return f"Agent '{agent_id}' resumed."
        # Treat as a message to the agent
        result = self._agent_manager.send_message(agent_id, action)
        return str(result) if result else f"Message sent to agent '{agent_id}'."

    # --------------------------------------------------------------
    # Chat handling
    # --------------------------------------------------------------

    def _handle_sessions(self, sender_id: str) -> str:
        targets = self._session_store.get_notification_targets()
        user_sessions = [t for t in targets if t["sender_id"] == sender_id]
        if not user_sessions:
            return "No active sessions with notification preferences."
        lines = []
        for s in user_sessions:
            lines.append(
                f"  {s['channel_type']} -> "
                f"notifications: {s['preferred_notification_channel']}"
            )
        return "Your sessions:\n" + "\n".join(lines)

    def _handle_chat(
        self,
        sender_id: str,
        content: str,
        channel_type: str,
        max_length: int,
        images: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        images = images or []
        history_text = content or ("[sent a photo]" if images else "")
        if images and content:
            history_text = f"{content} [with photo]"
        self._session_store.append_message(
            sender_id, channel_type, "user", history_text
        )

        # Build context from conversation history
        session = self._session_store.get_or_create(sender_id, channel_type)
        history = session.get("conversation_history", [])
        context_lines = []
        # exclude the message we just appended; keep the last few turns only
        for msg in history[:-1][-_HISTORY_TURNS:]:
            context_lines.append(f"{msg['role']}: {msg['content']}")
        context_str = "\n".join(context_lines)

        def _done(text: str, agent: str = "Jarvis", model: str = "") -> Dict[str, str]:
            formatted = self._format_response(sender_id, channel_type, text, max_length)
            self._session_store.append_message(
                sender_id, channel_type, "assistant", text
            )
            return {"content": formatted, "agent": agent, "model": model}

        engine = getattr(self._deep_research_agent, "_engine", None)
        default_model = getattr(self._deep_research_agent, "_model", "") or ""

        # "Hey Tony, ..." -> the named agent answers (identity + its model).
        if self._agent_manager is not None and engine is not None:
            from openjarvis.agents.name_router import resolve_mention, run_named_agent

            try:
                mention = resolve_mention(content, self._agent_manager.list_agents())
            except Exception:
                logger.exception("Agent name resolution failed")
                mention = None
            if mention is not None and mention.error:
                return _done(mention.error)
            if mention is not None and mention.routed:
                try:
                    out = run_named_agent(
                        mention,
                        engine=engine,
                        default_model=default_model,
                        context=context_str,
                        images=images,
                        bus=self._bus,
                    )
                except Exception as exc:
                    logger.exception("Named agent run failed")
                    return _done(
                        f"{mention.agent.get('name', 'That agent')} hit an error: "
                        f"{type(exc).__name__}. Try again or ask me directly."
                    )
                text = f"{out['content']}\n\n{out['note']}".strip()
                return _done(text, agent=out["agent"], model=out["model"])

        if images:
            from openjarvis.agents.name_router import model_supports_vision

            if engine is None or not model_supports_vision(engine, default_model):
                return _done(
                    "Got your photo, but the model I'm running on "
                    f"({default_model or 'unknown'}) can't see images, so I "
                    "can't tell you what's in it. Switch to a vision model and "
                    "send it again.",
                    model=default_model,
                )

        query = content or "What's in this photo?"
        if images:
            # Small models otherwise claim they "can't see images" even while
            # describing the attached photo correctly.
            query = (
                f"{query}\n\n(The user attached {len(images)} photo"
                f"{'s' if len(images) > 1 else ''} to this message. It's included "
                "and you can see it: look at it and answer about it directly. "
                "Don't say you can't see images.)"
            )
        if context_str:
            query = f"Previous conversation:\n{context_str}\n\nCurrent message: {query}"

        # Try DeepResearchAgent first
        if self._deep_research_agent is not None:
            try:
                result = self._deep_research_agent.run(
                    _research_prompt(query), images=images
                )
                response_text = result.content or "No results found."
            except Exception as exc:
                logger.error("DeepResearch agent failed: %s", exc)
                response_text = (
                    "Something broke on my end answering that "
                    f"({type(exc).__name__}). Try me again in a sec."
                )
            return _done(response_text, model=default_model)
        if self._system is not None:
            try:
                result = self._system.ask(query)
                return _done(result.get("content", str(result)))
            except Exception:
                logger.exception("Error in JarvisSystem.ask()")
        return _done("Sorry, I couldn't process that right now. Try again in a moment.")

    def _format_response(
        self,
        sender_id: str,
        channel_type: str,
        response: str,
        max_length: int,
    ) -> str:
        if len(response) <= max_length:
            return response
        # Truncate and store full response for /more retrieval
        truncation_notice = "\n\n... (reply /more for full response)"
        cut_at = max_length - len(truncation_notice)
        truncated = response[:cut_at] + truncation_notice
        self._session_store.set_pending_response(sender_id, channel_type, response)
        return truncated

    # --------------------------------------------------------------
    # Notifications
    # --------------------------------------------------------------

    def _subscribe_notifications(self) -> None:
        for event_type in _NOTIFICATION_EVENTS:
            self._bus.subscribe(event_type, self._on_notification_event)

    def _on_notification_event(self, event) -> None:  # noqa: ANN001
        event_key = str(event.event_type)
        now = time.time()

        # Rate limit: max 1 per event type per 5 minutes
        last = self._notification_timestamps.get(event_key, 0)
        if now - last < 300:
            return
        self._notification_timestamps[event_key] = now

        message = self._format_notification(event)
        if not message:
            return

        targets = self._session_store.get_notification_targets()
        for target in targets:
            pref_channel = target["preferred_notification_channel"]
            sender_id = target["sender_id"]
            self._send_notification(pref_channel, sender_id, message)

    def _format_notification(  # noqa: ANN201
        self,
        event,  # noqa: ANN001
    ) -> Optional[str]:
        data = event.data or {}
        name = data.get("agent_name", data.get("name", "unknown"))

        if event.event_type == EventType.AGENT_TICK_END:
            summary = data.get("summary", data.get("result", ""))
            return f"Agent '{name}' finished: {summary}" if summary else None
        if event.event_type == EventType.AGENT_TICK_ERROR:
            error = data.get("error", "unknown error")
            return f"Agent '{name}' error: {error}"
        if event.event_type == EventType.AGENT_BUDGET_EXCEEDED:
            return f"Agent '{name}' hit budget limit."
        if event.event_type == EventType.SCHEDULER_TASK_END:
            if data.get("success", True):
                return f"Scheduled task '{name}' completed."
            error = data.get("error", "unknown error")
            return f"Scheduled task '{name}' failed: {error}"
        return None

    def _send_notification(
        self,
        channel_type: str,
        sender_id: str,
        message: str,
    ) -> None:
        ch = self._channels.get(channel_type)
        if ch is None:
            logger.warning(
                "No adapter for notification channel %s",
                channel_type,
            )
            return
        try:
            ch.send(sender_id, message)
        except Exception:
            logger.exception("Failed to send notification to %s", channel_type)
