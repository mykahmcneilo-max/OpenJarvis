"""Test ChannelBridge routes to DeepResearchAgent."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_handle_chat_uses_deep_research_agent() -> None:
    """When a DeepResearch agent is configured, route through it."""
    from openjarvis.server.channel_bridge import ChannelBridge
    from openjarvis.server.session_store import SessionStore

    mock_agent = MagicMock()
    mock_agent.run.return_value = MagicMock(content="Found 3 results about Spain.")

    bridge = ChannelBridge(
        channels={},
        session_store=SessionStore(db_path=":memory:"),
        bus=MagicMock(),
        deep_research_agent=mock_agent,
    )

    result = bridge.handle_incoming(
        sender_id="+15551234567",
        content="When was my last trip to Spain?",
        channel_type="twilio",
    )

    assert "Spain" in result
    mock_agent.run.assert_called_once()


def test_handle_chat_falls_back_to_system() -> None:
    """When no DeepResearch agent, fall back to system.ask()."""
    from openjarvis.server.channel_bridge import ChannelBridge
    from openjarvis.server.session_store import SessionStore

    mock_system = MagicMock()
    mock_system.ask.return_value = {"content": "Generic response"}

    bridge = ChannelBridge(
        channels={},
        session_store=SessionStore(db_path=":memory:"),
        bus=MagicMock(),
        system=mock_system,
    )

    result = bridge.handle_incoming(
        sender_id="+15551234567",
        content="Hello",
        channel_type="twilio",
    )

    assert result == "Generic response"
    mock_system.ask.assert_called_once()


def test_deep_research_receives_conversation_history() -> None:
    """Follow-up texts must reach the agent with prior turns and text rules."""
    from openjarvis.server.channel_bridge import ChannelBridge
    from openjarvis.server.session_store import SessionStore

    mock_agent = MagicMock()
    mock_agent.run.return_value = MagicMock(content="ok")
    bridge = ChannelBridge(
        channels={},
        session_store=SessionStore(db_path=":memory:"),
        bus=MagicMock(),
        deep_research_agent=mock_agent,
    )

    bridge.handle_incoming(
        sender_id="+15551234567",
        content="What happened this week?",
        channel_type="sendblue",
    )
    bridge.handle_incoming(
        sender_id="+15551234567",
        content="Yes put it all together",
        channel_type="sendblue",
    )

    prompt = mock_agent.run.call_args_list[-1].args[0]
    assert "What happened this week?" in prompt
    assert "Current message: Yes put it all together" in prompt
    assert "Do not ask clarifying questions" in prompt


def test_phone_dashboard_shows_exchanges_without_sender_id():
    from openjarvis.server.session_store import SessionStore

    store = SessionStore(":memory:")
    store.get_or_create("+15551234567", "sendblue")
    store.append_message("+15551234567", "sendblue", "user", "Apple connection test")
    store.append_message("+15551234567", "sendblue", "assistant", "Connected.")
    conversations = store.recent_conversations()
    assert len(conversations) == 1
    assert conversations[0]["messages"][1]["content"] == "Connected."
    assert "+15551234567" not in str(conversations)
    assert conversations[0]["updated_at"].endswith("Z")


def _bridge(agent, manager=None):
    from openjarvis.server.channel_bridge import ChannelBridge
    from openjarvis.server.session_store import SessionStore

    return ChannelBridge(
        channels={},
        session_store=SessionStore(db_path=":memory:"),
        bus=MagicMock(),
        agent_manager=manager,
        deep_research_agent=agent,
    )


def test_photo_without_vision_model_is_answered_honestly():
    from unittest.mock import patch

    agent = MagicMock()
    agent._model = "text-only:7b"
    with patch(
        "openjarvis.agents.name_router.model_supports_vision", return_value=False
    ):
        out = _bridge(agent).respond("+1555", "what is this", "sendblue", images=["a"])
    assert "can't see images" in out["content"]
    agent.run.assert_not_called()


def test_photo_is_passed_to_vision_model():
    from unittest.mock import patch

    agent = MagicMock()
    agent._model = "qwen3.5:9b"
    agent.run.return_value = MagicMock(content="A red circle.")
    with patch(
        "openjarvis.agents.name_router.model_supports_vision", return_value=True
    ):
        out = _bridge(agent).respond("+1555", "", "sendblue", images=["a"])
    assert out == {"content": "A red circle.", "agent": "Jarvis", "model": "qwen3.5:9b"}
    assert agent.run.call_args.kwargs["images"] == ["a"]


def test_named_agent_routing_from_phone():
    from unittest.mock import patch

    manager = MagicMock()
    manager.list_agents.return_value = [{"id": "t", "name": "Tony", "config": {}}]
    agent = MagicMock()
    agent._model = "qwen3.5:9b"
    reply = {"content": "Reviewed.", "agent": "Tony", "model": "qwen3.5:9b", "note": ""}
    with patch(
        "openjarvis.agents.name_router.run_named_agent", return_value=reply
    ) as run:
        out = _bridge(agent, manager).respond(
            "+1555", "Hey Tony, review this project", "sendblue"
        )
    assert out["agent"] == "Tony" and out["content"] == "Reviewed."
    assert run.call_args.args[0].message == "review this project"
    agent.run.assert_not_called()
