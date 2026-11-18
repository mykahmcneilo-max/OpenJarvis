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


def user_text() -> str:
    """USER.md (who the user is), or "" when missing/unreadable."""
    try:
        from openjarvis.core.config import load_config

        path = Path(load_config().memory_files.user_path).expanduser()
    except Exception:
        from openjarvis.core.paths import get_config_dir

        path = get_config_dir() / "USER.md"
    try:
        return path.read_text(encoding="utf-8").strip()[:_MAX_CHARS]
    except OSError:
        return ""


def persona_block() -> str:
    """SOUL.md + USER.md as system-prompt sections ("" when not configured)."""
    out = ""
    soul = soul_text()
    if soul:
        out += f"\n\n## Voice and personality\n\n{soul}"
    user = user_text()
    if user:
        out += f"\n\n## Who you're talking to\n\n{user}"
    return out
