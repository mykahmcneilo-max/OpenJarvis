"""Tests for the shared SOUL.md persona block."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openjarvis.prompt import persona


def _cfg(path: Path):
    return SimpleNamespace(memory_files=SimpleNamespace(soul_path=str(path)))


def test_persona_block_reads_soul(tmp_path: Path) -> None:
    soul = tmp_path / "SOUL.md"
    soul.write_text("Be chill.", encoding="utf-8")
    with patch("openjarvis.core.config.load_config", return_value=_cfg(soul)):
        block = persona.persona_block()
    assert "Voice and personality" in block and "Be chill." in block


def test_persona_block_empty_without_soul(tmp_path: Path) -> None:
    with patch(
        "openjarvis.core.config.load_config", return_value=_cfg(tmp_path / "none.md")
    ):
        assert persona.persona_block() == ""
