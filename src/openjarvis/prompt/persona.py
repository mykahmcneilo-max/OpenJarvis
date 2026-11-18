"""Shared Jarvis persona (SOUL.md) for agents that build their own prompts.

Most agents get SOUL.md through :class:`SystemPromptBuilder`. Agents that
assemble a specialized system prompt (e.g. DeepResearch, which answers
iMessage) call :func:`persona_block` so the voice stays the same across
desktop chat, phone, agents, and provider switches.
"""

from __future__ import annotations

from pathlib import Path

_MAX_CHARS = 4000


def soul_text() -> str:
    """Return the configured SOUL.md text, or "" if missing/unreadable."""
    try:
        from openjarvis.core.config import load_config

        path = Path(load_config().memory_files.soul_path).expanduser()
    except Exception:
        from openjarvis.core.paths import get_config_dir

        path = get_config_dir() / "SOUL.md"
    try:
        return path.read_text(encoding="utf-8").strip()[:_MAX_CHARS]
    except OSError:
        return ""


def persona_block() -> str:
    """SOUL.md formatted as a system-prompt section ("" when not configured)."""
    soul = soul_text()
    return f"\n\n## Voice and personality\n\n{soul}" if soul else ""
