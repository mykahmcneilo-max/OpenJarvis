"""Tests for the durable channel message log."""

from __future__ import annotations

from openjarvis.server.session_store import SessionStore


def test_log_and_list_conversation_without_exposing_number():
    s = SessionStore(db_path=":memory:")
    s.log_message(
        "+15551234567", "sendblue", "user", "hi", attachments=[{"id": "x.jpg"}]
    )
    row = s.log_message(
        "+15551234567",
        "sendblue",
        "assistant",
        "yo",
        agent="Jarvis",
        model="qwen3.5:9b",
        delivery_status="QUEUED",
        message_handle="h1",
    )
    s.update_delivery(row, "DELIVERED")
    (conv,) = s.logged_conversations("sendblue")
    assert "5551234567" not in conv["id"]
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["messages"][0]["attachments"] == [{"id": "x.jpg"}]
    assert conv["messages"][1]["delivery_status"] == "DELIVERED"
    assert conv["messages"][1]["model"] == "qwen3.5:9b"


def test_backfill_copies_rolling_history_once():
    s = SessionStore(db_path=":memory:")
    s.get_or_create("+1555", "sendblue")
    s.append_message("+1555", "sendblue", "user", "old q")
    s.append_message("+1555", "sendblue", "assistant", "old a")
    assert s.backfill_logged_messages("sendblue") == 2
    assert s.backfill_logged_messages("sendblue") == 0
    (conv,) = s.logged_conversations("sendblue")
    assert [m["content"] for m in conv["messages"]] == ["old q", "old a"]
