"""Tests for routing "Hey Tony, ..." messages to named agents."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from openjarvis.agents.name_router import resolve_mention, run_named_agent

AGENTS = [
    {"id": "a1", "name": "Tony", "config": {"aliases": ["T-Bone"]}},
    {"id": "a2", "name": "Pepper", "config": {}},
]


def test_greeting_routes_to_agent_and_strips_name():
    m = resolve_mention("Hey Tony, I want you to review this project.", AGENTS)
    assert m.routed and m.agent["id"] == "a1"
    assert m.message == "I want you to review this project."


def test_other_address_forms_and_aliases():
    assert resolve_mention("tony: summarize my inbox", AGENTS).agent["id"] == "a1"
    assert resolve_mention("@Pepper what's up", AGENTS).agent["id"] == "a2"
    assert resolve_mention("yo t-bone, help", AGENTS).agent["id"] == "a1"
    assert resolve_mention("Hey Tony", AGENTS).agent["id"] == "a1"


def test_name_mid_sentence_is_not_routed():
    assert not resolve_mention("Did Tony text me today?", AGENTS).routed
    assert not resolve_mention("Tony Stark movies ranked", AGENTS).routed


def test_duplicate_names_are_reported_not_guessed():
    agents = AGENTS + [{"id": "a3", "name": "tony", "config": {}}]
    m = resolve_mention("Hey Tony, do it", agents)
    assert not m.routed and "2 agents named Tony" in m.error


def test_run_named_agent_uses_identity_safe_tools_and_reports_model_fallback():
    captured = {}

    class FakeAgent:
        def __init__(self, **kw):
            captured.update(kw)

        def _build_messages(self, *a, **k):
            return []

        def run(self, text):
            captured["input"] = text
            return MagicMock(content="On it: here's the review.")

    agent = {
        "id": "a1",
        "name": "Tony",
        "config": {
            "model": "deepseek-r1:7b",
            "system_prompt": "You are an Inbox Triager.",
            "tools": ["shell_exec", "knowledge_search", "file_write"],
        },
    }
    mention = resolve_mention("Hey Tony, review this", [agent])
    with (
        patch("openjarvis.agents.orchestrator.OrchestratorAgent", FakeAgent),
        patch(
            "openjarvis.agents.tool_resolver.build_deep_research_tools",
            return_value=[],
        ),
    ):
        out = run_named_agent(
            mention,
            engine=MagicMock(),
            default_model="qwen3.5:9b",
            supports_tools=lambda e, m: m != "deepseek-r1:7b",
        )
    assert out["agent"] == "Tony" and out["model"] == "qwen3.5:9b"
    assert "deepseek-r1:7b can't use tools" in out["note"]
    assert "Inbox Triager" in captured["system_prompt"]
    names = {getattr(getattr(t, "spec", None), "name", "") for t in captured["tools"]}
    assert "shell_exec" not in names and "file_write" not in names
    assert captured["input"].endswith("review this")
