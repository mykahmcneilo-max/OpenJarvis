"""Tests for IMessageConnector — local macOS Messages database connector.

All tests use a temporary SQLite database that mimics the real chat.db schema.
No actual macOS Messages database is required.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List

import pytest

from openjarvis.connectors._stubs import Document
from openjarvis.core.registry import ConnectorRegistry

# ---------------------------------------------------------------------------
# Helper: create a fake chat.db
# ---------------------------------------------------------------------------


def _create_fake_chat_db(db_path: Path) -> None:
    """Populate a SQLite file with the iMessage chat.db schema and sample rows."""
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        "CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT NOT NULL);"
        "CREATE TABLE chat ("
        "  ROWID INTEGER PRIMARY KEY,"
        "  chat_identifier TEXT NOT NULL,"
        "  display_name TEXT"
        ");"
        "CREATE TABLE message ("
        "  ROWID INTEGER PRIMARY KEY,"
        "  text TEXT,"
        "  handle_id INTEGER,"
        "  date INTEGER,"
        "  is_from_me INTEGER DEFAULT 0,"
        "  cache_roomnames TEXT"
        ");"
        "CREATE TABLE chat_message_join ("
        "  chat_id INTEGER,"
        "  message_id INTEGER"
        ");"
        "INSERT INTO handle VALUES (1, '+15550100');"
        "INSERT INTO handle VALUES (2, 'alice@icloud.com');"
        "INSERT INTO chat VALUES (1, '+15550100', 'Alice');"
        "INSERT INTO chat VALUES (2, 'chat123', 'Team Group');"
        "INSERT INTO message VALUES ("
        "  1, 'Hey, are we meeting tomorrow?',"
        "  1, 700000000000000000, 0, NULL"
        ");"
        "INSERT INTO message VALUES ("
        "  2, 'Yes at 3pm!', 1, 700000060000000000, 1, NULL"
        ");"
        "INSERT INTO message VALUES ("
        "  3, 'Group message about project',"
        "  2, 700000120000000000, 0, 'chat123'"
        ");"
        "INSERT INTO chat_message_join VALUES (1, 1);"
        "INSERT INTO chat_message_join VALUES (1, 2);"
        "INSERT INTO chat_message_join VALUES (2, 3);"
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_db(tmp_path: Path) -> Path:
    """Return path to a populated fake chat.db."""
    db_path = tmp_path / "chat.db"
    _create_fake_chat_db(db_path)
    return db_path


@pytest.fixture()
def connector(fake_db: Path):
    """IMessageConnector pointing at the fake DB."""
    from openjarvis.connectors.imessage import IMessageConnector  # noqa: PLC0415

    return IMessageConnector(db_path=str(fake_db))


# ---------------------------------------------------------------------------
# Test 1 — is_connected returns True when db_path exists
# ---------------------------------------------------------------------------


def test_is_connected(connector) -> None:
    """is_connected() returns True when chat.db exists at the configured path."""
    assert connector.is_connected() is True


# ---------------------------------------------------------------------------
# Test 2 — is_connected returns False for a missing file
# ---------------------------------------------------------------------------


def test_not_connected_missing_db() -> None:
    """is_connected() returns False when the database file does not exist."""
    from openjarvis.connectors.imessage import IMessageConnector  # noqa: PLC0415

    conn = IMessageConnector(db_path="/nonexistent/path/chat.db")
    assert conn.is_connected() is False


# ---------------------------------------------------------------------------
# Test 3 — sync yields all 3 messages with correct source and doc_type
# ---------------------------------------------------------------------------


def test_sync_yields_messages(connector) -> None:
    """sync() yields one Document per non-NULL message (3 total)."""
    docs: List[Document] = list(connector.sync())
    assert len(docs) == 3
    for doc in docs:
        assert doc.source == "imessage"
        assert doc.doc_type == "message"


# ---------------------------------------------------------------------------
# Test 4 — sync_message_content checks specific text is present
# ---------------------------------------------------------------------------


def test_sync_message_content(connector) -> None:
    """sync() surfaces the exact message text in each Document's content."""
    docs: List[Document] = list(connector.sync())
    contents = {d.content for d in docs}
    assert "Hey, are we meeting tomorrow?" in contents
    assert "Yes at 3pm!" in contents
    assert "Group message about project" in contents


# ---------------------------------------------------------------------------
# Test 5 — sync sets author to handle identifier for received messages
# ---------------------------------------------------------------------------


def test_sync_sets_author(connector) -> None:
    """Received messages use the handle identifier; sent messages use 'me'."""
    docs: List[Document] = list(connector.sync())

    # Message 1 is received from handle +15550100
    msg1 = next(d for d in docs if d.doc_id == "imessage:1")
    assert msg1.author == "+15550100"

    # Message 2 is sent by me
    msg2 = next(d for d in docs if d.doc_id == "imessage:2")
    assert msg2.author == "me"

    # Message 3 is received from handle alice@icloud.com
    msg3 = next(d for d in docs if d.doc_id == "imessage:3")
    assert msg3.author == "alice@icloud.com"


# ---------------------------------------------------------------------------
# Test 6 — disconnect sets connected flag to False
# ---------------------------------------------------------------------------


def test_disconnect(connector) -> None:
    """disconnect() marks the connector as disconnected."""
    # Initially the DB file exists, so is_connected is True
    assert connector.is_connected() is True
    connector.disconnect()
    # _connected flag is cleared; is_connected still checks file existence
    assert connector._connected is False


# ---------------------------------------------------------------------------
# Test 7 — mcp_tools returns exactly 2 tool specs
# ---------------------------------------------------------------------------


def test_mcp_tools(connector) -> None:
    """mcp_tools() returns exactly 2 tools with the expected names."""
    tools = connector.mcp_tools()
    names = {t.name for t in tools}
    assert len(tools) == 2
    assert "imessage_search_messages" in names
    assert "imessage_get_conversation" in names


# ---------------------------------------------------------------------------
# Test 8 — ConnectorRegistry contains "imessage" after import
# ---------------------------------------------------------------------------


def test_registry() -> None:
    """IMessageConnector is registered and retrievable via ConnectorRegistry."""
    from openjarvis.connectors.imessage import IMessageConnector  # noqa: PLC0415

    ConnectorRegistry.register_value("imessage", IMessageConnector)
    assert ConnectorRegistry.contains("imessage")
    cls = ConnectorRegistry.get("imessage")
    assert cls.connector_id == "imessage"


def test_contact_names_and_raw_handles(fake_db):
    from openjarvis.connectors.imessage import IMessageConnector

    docs = list(
        IMessageConnector(
            str(fake_db),
            handle_names={
                "+1 (555) 0100": "Jarvis",
                "ALICE@ICLOUD.COM": "Alice Smith",
            },
        ).sync()
    )
    assert docs[0].author == "Jarvis"
    assert docs[0].participants == ["Jarvis"]
    assert docs[0].participants_raw == ["+15550100"]
    assert docs[1].author == "me"
    assert docs[2].author == "Alice Smith"
    assert docs[2].title == "Team Group"


def test_us_phone_normalization():
    from openjarvis.connectors.imessage import normalize_handle

    assert normalize_handle("+1 (202) 555-0100") == normalize_handle("2025550100")
    assert normalize_handle(" USER@EXAMPLE.COM ") == "user@example.com"
    assert normalize_handle("+44 20 1234 5678") == "442012345678"


def test_resync_updates_names_without_changing_message(fake_db, tmp_path):
    from openjarvis.connectors.imessage import IMessageConnector
    from openjarvis.connectors.pipeline import IngestionPipeline
    from openjarvis.connectors.store import KnowledgeStore

    store = KnowledgeStore(str(tmp_path / "knowledge.db"))
    pipeline = IngestionPipeline(store)
    assert pipeline.ingest(list(IMessageConnector(str(fake_db)).sync())) == 3
    named = list(
        IMessageConnector(
            str(fake_db),
            handle_names={
                "+15550100": "Jarvis",
            },
        ).sync()
    )
    assert pipeline.ingest(named) == 2
    rows = store._conn.execute(
        "SELECT author, participants_raw FROM knowledge_chunks WHERE doc_id = ?",
        ("imessage:1",),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "Jarvis"
    assert rows[0][1] == '["+15550100"]'
    assert pipeline.ingest(named) == 0


def test_group_members_and_direct_chat_title(fake_db):
    from openjarvis.connectors.imessage import IMessageConnector

    with sqlite3.connect(fake_db) as db:
        db.executescript(
            "CREATE TABLE chat_handle_join (chat_id INTEGER, handle_id INTEGER);"
            "INSERT INTO chat_handle_join VALUES (2, 1), (2, 2);"
            "UPDATE chat SET display_name = NULL WHERE ROWID = 1;"
        )
    docs = list(
        IMessageConnector(
            str(fake_db),
            handle_names={
                "+15550100": "Jarvis",
                "alice@icloud.com": "Alice",
            },
        ).sync()
    )
    assert docs[0].title == "Jarvis"
    assert docs[2].title == "Team Group"
    assert docs[2].participants == ["Jarvis", "Alice"]
    assert docs[2].participants_raw == ["+15550100", "alice@icloud.com"]
