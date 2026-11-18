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


def test_compat_providers_and_auto_are_detected():
    assert cloud_router.get_provider("groq/llama-3.3-70b-versatile") == "groq"
    assert cloud_router.get_provider("kimi/kimi-k2-0905-preview") == "moonshot"
    assert cloud_router.get_provider("deepseek-api/deepseek-chat") == "deepseek"
    assert cloud_router.get_provider("github/openai/gpt-4.1") == "github"
    assert cloud_router.get_provider("jarvis-auto") == "auto"
    # Plain OpenRouter-style ids still go to OpenRouter.
    assert cloud_router.get_provider("deepseek/deepseek-r1") == "openrouter"


def test_free_tier_confirmation_unblocks_only_that_provider(tmp_path: Path):
    (tmp_path / "free-cloud-only").write_text("")
    (tmp_path / "free-tier-providers.txt").write_text("groq\n# comment\n")
    keys = {"GROQ_API_KEY": "k1", "MISTRAL_API_KEY": "k2"}
    with (
        patch.object(cloud_router, "get_config_dir", return_value=tmp_path),
        patch.object(cloud_router, "_load_keys", return_value=keys),
        patch.object(cloud_router, "_cli_path", return_value=None),
    ):
        rows = {r["id"]: r for r in cloud_router.provider_status()}
    assert rows["groq"]["usable"] and "free tier" in rows["groq"]["detail"]
    assert not rows["mistral"]["usable"] and rows["mistral"]["blocked_by_free_only"]


def test_auto_falls_through_failing_models_to_next(tmp_path: Path):
    (tmp_path / "model-chain.txt").write_text("claude-code\ngroq/m\ncodex-cli\n")
    msgs = [Message(role=Role.USER, content="hi")]
    calls = []

    async def fake_cli(provider, model, messages):
        calls.append(model)
        if provider == "claude_cli":
            raise ValueError("usage limit reached")
        yield "codex answer"

    usable = {"claude_cli": True, "codex_cli": True, "groq": False}

    async def run():
        return [t async for t in cloud_router.stream_cloud("jarvis-auto", msgs)]

    with (
        patch.object(cloud_router, "get_config_dir", return_value=tmp_path),
        patch.object(cloud_router, "_stream_cli", fake_cli),
        patch.object(cloud_router, "_usable_models", return_value=usable),
    ):
        out = asyncio.run(run())
    assert out == ["codex answer"]
    assert calls == ["claude-code", "codex-cli"]  # groq skipped: not usable
    assert cloud_router.LAST_AUTO_MODEL["model"] == "codex-cli"


def test_auto_ends_on_local_model_when_nothing_works(tmp_path: Path):
    (tmp_path / "model-chain.txt").write_text("claude-code\n")
    msgs = [Message(role=Role.USER, content="hi")]

    async def broken_cli(provider, model, messages):
        raise ValueError("down")
        yield  # pragma: no cover

    async def local(model, messages, temperature, max_tokens):
        yield f"local {model}"

    async def run():
        return [t async for t in cloud_router.stream_cloud("jarvis-auto", msgs)]

    with (
        patch.object(cloud_router, "get_config_dir", return_value=tmp_path),
        patch.object(cloud_router, "_stream_cli", broken_cli),
        patch.object(cloud_router, "_usable_models", return_value={"claude_cli": True}),
        patch.object(cloud_router, "stream_local", local),
    ):
        assert asyncio.run(run()) == ["local qwen3.5:9b"]
