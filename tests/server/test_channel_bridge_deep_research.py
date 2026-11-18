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
