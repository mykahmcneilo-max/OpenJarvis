"""Subscription CLIs, xAI Grok, and honest provider status."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from openjarvis.core.types import Message, Role
from openjarvis.server import cloud_router


def test_provider_detection():
    assert cloud_router.get_provider("claude-code") == "claude_cli"
    assert cloud_router.get_provider("claude-code:opus") == "claude_cli"
    assert cloud_router.get_provider("codex-cli") == "codex_cli"
    assert cloud_router.get_provider("grok-4") == "xai"
    assert cloud_router.get_provider("claude-sonnet-4-5") == "anthropic"
    assert cloud_router.get_provider("qwen3.5:9b") is None


def test_free_only_blocks_metered_but_allows_subscription(tmp_path: Path):
    (tmp_path / "free-cloud-only").write_text("")
    msgs = [Message(role=Role.USER, content="hi")]

    async def collect(model):
        return [t async for t in cloud_router.stream_cloud(model, msgs)]

    async def fake_cli(provider, model, messages):
        yield f"{provider} ok"

    with (
        patch.object(cloud_router, "get_config_dir", return_value=tmp_path),
        patch.object(cloud_router, "_stream_cli", fake_cli),
    ):
        assert asyncio.run(collect("claude-code")) == ["claude_cli ok"]
        with pytest.raises(ValueError, match="Free-only mode"):
            asyncio.run(collect("grok-4"))


def test_provider_status_is_honest_without_keys(tmp_path: Path):
    (tmp_path / "free-cloud-only").write_text("")
    with (
        patch.object(cloud_router, "get_config_dir", return_value=tmp_path),
        patch.object(
            cloud_router, "_load_keys", return_value={"XAI_API_KEY": "SECRET123"}
        ),
        patch.object(cloud_router, "_cli_path", return_value=None),
    ):
        rows = {r["id"]: r for r in cloud_router.provider_status()}
    assert rows["claude_cli"]["billing"] == "subscription"
    assert rows["claude_cli"]["usable"] is False
    assert rows["claude_cli"]["detail"] == "Not installed"
    assert rows["openai"]["detail"].startswith("Needs OPENAI_API_KEY")
    assert rows["xai"]["authorized"] is True and rows["xai"]["usable"] is False
    assert "free-only" in rows["xai"]["detail"]
    assert "SECRET123" not in str(rows)


def test_cli_prompt_flattening_keeps_context():
    system, prompt = cloud_router._flatten_for_cli(
        [
            Message(role=Role.SYSTEM, content="Be chill."),
            Message(role=Role.USER, content="hey"),
            Message(role=Role.ASSISTANT, content="sup"),
            Message(role=Role.USER, content="summarize that"),
        ]
    )
    assert system == "Be chill."
    assert "User: hey" in prompt and prompt.rstrip().endswith("User: summarize that")
