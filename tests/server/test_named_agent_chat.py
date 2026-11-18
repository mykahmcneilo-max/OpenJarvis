"""Desktop chat routes "Hey Tony, ..." to the named agent."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.server.routes import router  # noqa: E402


def _client():
    app = FastAPI()
    app.include_router(router)
    app.state.engine = MagicMock()
    app.state.model = "qwen3.5:9b"
    manager = MagicMock()
    manager.list_agents.return_value = [{"id": "t", "name": "Tony", "config": {}}]
    app.state.agent_manager = manager
    return TestClient(app)


REPLY = {"content": "Project looks solid.", "agent": "Tony", "model": "qwen3.5:9b"}


def test_named_agent_answers_non_streaming():
    with patch(
        "openjarvis.agents.name_router.run_named_agent",
        return_value={**REPLY, "note": ""},
    ) as run:
        resp = _client().post(
            "/v1/chat/completions",
            json={
                "model": "qwen3.5:9b",
                "messages": [
                    {"role": "user", "content": "earlier"},
                    {"role": "user", "content": "Hey Tony, review this project"},
                ],
            },
        )
    body = resp.json()
    assert body["openjarvis"] == {"agent": "Tony", "model": "qwen3.5:9b"}
    assert body["choices"][0]["message"]["content"] == "Project looks solid."
    assert run.call_args.args[0].message == "review this project"
    assert "earlier" in run.call_args.kwargs["context"]


def test_named_agent_answers_streaming():
    with patch(
        "openjarvis.agents.name_router.run_named_agent",
        return_value={**REPLY, "note": ""},
    ):
        resp = _client().post(
            "/v1/chat/completions",
            json={
                "model": "qwen3.5:9b",
                "stream": True,
                "messages": [{"role": "user", "content": "Tony, review this"}],
            },
        )
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: {")
    ]
    assert events[0]["choices"][0]["delta"]["content"] == "Project looks solid."
    assert events[0]["openjarvis"]["agent"] == "Tony"
    assert resp.text.rstrip().endswith("data: [DONE]")


def test_duplicate_agent_names_get_a_clear_answer():
    client = _client()
    client.app.state.agent_manager.list_agents.return_value = [
        {"id": "a", "name": "Tony", "config": {}},
        {"id": "b", "name": "Tony", "config": {}},
    ]
    resp = client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "Hey Tony, go"}]},
    )
    assert "2 agents named Tony" in resp.json()["choices"][0]["message"]["content"]
