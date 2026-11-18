"""jarvis-auto failover engine: best first, hand-off, tools for every model."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from openjarvis.core.types import Message, Role, ToolCall
from openjarvis.engine.failover import (
    AUTO_MODEL,
    FailoverEngine,
    parse_cli_tool_calls,
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "knowledge_search",
            "description": "Search the user's data",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


def test_new_rotation_keeps_vision_route_and_local_fallback():
    vision = "openrouter/nvidia/nemotron-3.5-super-vl:free"
    engine, _ = _engine(
        ["codex-cli:gpt-6.2-astra", vision],
        usable={"codex_cli": True, "openrouter": True},
    )
    assert engine.candidates(needs_vision=True) == [vision, "qwen3.5:9b"]


def _resp(status: int, body: dict) -> httpx.Response:
    return httpx.Response(
        status, json=body, request=httpx.Request("POST", "https://x/chat")
    )


def _ok(content="hi", tool_calls=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return _resp(200, {"choices": [{"message": msg, "finish_reason": "stop"}]})


class _Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def _engine(chain, http=None, run_cli=None, usable=None, inner=None, clock=None):
    inner = inner or MagicMock()
    inner.generate.return_value = {"content": "local answer"}
    eng = FailoverEngine(
        inner,
        "qwen3.5:9b",
        chain=lambda: chain,
        usable=lambda: usable
        or {"claude_cli": True, "groq": True, "google": True, "xai": False},
        http=http or MagicMock(),
        run_cli=run_cli or MagicMock(return_value="cli answer"),
        clock=clock or _Clock(),
    )
    return eng, inner


@pytest.fixture(autouse=True)
def _keys(monkeypatch):
    from openjarvis.server import cloud_router

    monkeypatch.setattr(
        cloud_router,
        "_load_keys",
        lambda: {"GROQ_API_KEY": "k", "GEMINI_API_KEY": "g"},
    )


def test_best_model_answers_first():
    eng, inner = _engine(["claude-code:opus", "groq/openai/gpt-oss-120b"])
    out = eng.generate([Message(role=Role.USER, content="yo")], model=AUTO_MODEL)
    assert out["content"] == "cli answer" and out["model"] == "claude-code:opus"
    assert eng.last_model == "claude-code:opus"
    inner.generate.assert_not_called()


def test_out_of_credits_moves_down_and_cools_off():
    http = MagicMock()
    http.post.return_value = _ok("groq answer")
    cli = MagicMock(side_effect=ValueError("claude_cli failed: usage limit reached"))
    clock = _Clock()
    eng, _ = _engine(
        ["claude-code:opus", "grok-4", "groq/openai/gpt-oss-120b"],
        http=http,
        run_cli=cli,
        clock=clock,
    )
    msgs = [Message(role=Role.USER, content="yo")]
    out = eng.generate(msgs, model=AUTO_MODEL)
    assert out["model"] == "groq/openai/gpt-oss-120b"  # grok skipped: not usable
    eng.generate(msgs, model=AUTO_MODEL)
    assert cli.call_count == 1  # cooling off after a quota error
    clock.t += 31 * 60
    eng.generate(msgs, model=AUTO_MODEL)
    assert cli.call_count == 2  # retried once the cooldown passed


def test_rate_limit_status_falls_through_to_local():
    http = MagicMock()
    http.post.return_value = _resp(429, {"error": "slow down"})
    eng, inner = _engine(["groq/openai/gpt-oss-120b"], http=http)
    out = eng.generate(
        [Message(role=Role.USER, content="yo")], model=AUTO_MODEL, tools=TOOLS
    )
    assert out["model"] == "qwen3.5:9b" and out["content"] == "local answer"
    assert inner.generate.call_args.kwargs["tools"] == TOOLS


def test_full_conversation_and_tools_hand_off_to_next_model():
    http = MagicMock()
    http.post.return_value = _ok(
        "",
        tool_calls=[
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "knowledge_search", "arguments": "{}"},
            }
        ],
    )
    eng, _ = _engine(["groq/openai/gpt-oss-120b"], http=http)
    history = [
        Message(role=Role.SYSTEM, content="You're Jarvis."),
        Message(role=Role.USER, content="what did I say yesterday?"),
        Message(
            role=Role.ASSISTANT,
            content="",
            tool_calls=[ToolCall(id="a", name="knowledge_search", arguments="{}")],
        ),
        Message(role=Role.TOOL, content="nothing", tool_call_id="a", name="ks"),
    ]
    out = eng.generate(history, model=AUTO_MODEL, tools=TOOLS)
    sent = http.post.call_args.kwargs["json"]
    assert [m["role"] for m in sent["messages"]] == [
        "system",
        "user",
        "assistant",
        "tool",
    ]
    assert sent["model"] == "openai/gpt-oss-120b" and sent["tools"] == TOOLS
    assert out["tool_calls"][0]["name"] == "knowledge_search"


def test_cli_models_get_tools_through_a_json_protocol():
    cli = MagicMock(
        return_value='```json\n{"tool_calls": [{"name": "knowledge_search", '
        '"arguments": {"query": "x"}}]}\n```'
    )
    eng, _ = _engine(["claude-code:opus"], run_cli=cli)
    out = eng.generate(
        [
            Message(role=Role.SYSTEM, content="persona"),
            Message(role=Role.USER, content="find x"),
        ],
        model=AUTO_MODEL,
        tools=TOOLS,
    )
    (call,) = out["tool_calls"]
    assert call["name"] == "knowledge_search"
    assert json.loads(call["arguments"]) == {"query": "x"}
    system = cli.call_args.args[2]
    assert system.startswith("persona") and "knowledge_search" in system


def test_photos_skip_models_that_cant_see():
    http = MagicMock()
    http.post.return_value = _ok("a dog")
    eng, _ = _engine(["claude-code:opus", "groq/x", "gemini-2.5-pro"], http=http)
    msg = Message(role=Role.USER, content="what's this?")
    msg.images = ["/9j/abc"]
    out = eng.generate([msg], model=AUTO_MODEL)
    assert out["model"] == "gemini-2.5-pro"
    part = http.post.call_args.kwargs["json"]["messages"][0]["content"][1]
    assert part["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_other_models_pass_straight_through():
    eng, inner = _engine(["groq/x"])
    eng.generate([Message(role=Role.USER, content="yo")], model="qwen3.5:9b")
    assert inner.generate.call_args.kwargs["model"] == "qwen3.5:9b"
    assert eng.list_models()[0] == AUTO_MODEL


def test_parse_cli_tool_calls_finds_json_after_a_sentence():
    text = (
        "Weather tool failed; fall back to web_search.\n\n"
        '{"tool_calls": [{"name": "web_search", "arguments": {"query": "x"}}]}'
    )
    (call,) = parse_cli_tool_calls(text)
    assert call["name"] == "web_search"


def test_parse_cli_tool_calls_ignores_plain_answers():
    assert parse_cli_tool_calls("Sure, it's sunny.") is None
    assert parse_cli_tool_calls('{"answer": 1}') is None
