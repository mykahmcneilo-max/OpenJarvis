"""Integration tests for the SendBlue webhook endpoint.

Tests the /webhooks/sendblue route, health check endpoint, and the
full flow from incoming webhook -> bridge -> agent -> send response.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi", reason="openjarvis[server] not installed")

from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from openjarvis.core.registry import ChannelRegistry  # noqa: E402


@pytest.fixture(autouse=True)
def _register_sendblue():
    if not ChannelRegistry.contains("sendblue"):
        from openjarvis.channels.sendblue import SendBlueChannel

        ChannelRegistry.register_value("sendblue", SendBlueChannel)


@pytest.fixture
def mock_bridge():
    bridge = MagicMock()
    bridge.handle_incoming.return_value = "Here are your results..."
    return bridge


@pytest.fixture
def sendblue_channel():
    from openjarvis.channels.sendblue import SendBlueChannel

    ch = SendBlueChannel(
        api_key_id="test_key",
        api_secret_key="test_secret",
        from_number="+15551234567",
        # Webhooks now fail closed without a secret, so configure one and have
        # the test client send the matching header by default.
        webhook_secret="testsecret",
    )
    ch.connect()
    return ch


@pytest.fixture
def webhook_app(mock_bridge, sendblue_channel):
    from openjarvis.server.webhook_routes import create_webhook_router

    app = FastAPI()
    router = create_webhook_router(
        bridge=mock_bridge,
        sendblue_channel=sendblue_channel,
    )
    app.include_router(router)
    return app


@pytest.fixture
def client(webhook_app):
    # Send the webhook secret by default so message-handling tests reach the
    # bridge; fail-closed behavior is covered separately below.
    return TestClient(webhook_app, headers={"x-sendblue-secret": "testsecret"})


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------


class TestSendBlueWebhook:
    def test_incoming_message_returns_200(self, client):
        resp = client.post(
            "/webhooks/sendblue",
            json={
                "from_number": "+19127130720",
                "to_number": "+15551234567",
                "content": "Hello Jarvis",
                "message_handle": "msg-001",
                "is_outbound": False,
                "status": "RECEIVED",
                "service": "iMessage",
            },
        )
        assert resp.status_code == 200

    def test_outbound_status_callback_ignored(self, client, mock_bridge):
        resp = client.post(
            "/webhooks/sendblue",
            json={
                "from_number": "+15551234567",
                "content": "Sent message",
                "is_outbound": True,
            },
        )
        assert resp.status_code == 200
        mock_bridge.handle_incoming.assert_not_called()

    def test_empty_content_ignored(self, client, mock_bridge):
        resp = client.post(
            "/webhooks/sendblue",
            json={
                "from_number": "+19127130720",
                "content": "",
                "is_outbound": False,
            },
        )
        assert resp.status_code == 200
        mock_bridge.handle_incoming.assert_not_called()

    def test_missing_from_number_ignored(self, client, mock_bridge):
        resp = client.post(
            "/webhooks/sendblue",
            json={
                "content": "Hello",
                "is_outbound": False,
            },
        )
        assert resp.status_code == 200
        mock_bridge.handle_incoming.assert_not_called()

    def test_webhook_secret_validation(self, mock_bridge):
        """When a webhook secret is set, reject requests without it."""
        from openjarvis.channels.sendblue import SendBlueChannel
        from openjarvis.server.webhook_routes import create_webhook_router

        ch = SendBlueChannel(
            api_key_id="k",
            api_secret_key="s",
            from_number="+1555",
            webhook_secret="mysecret",
        )
        ch.connect()

        app = FastAPI()
        router = create_webhook_router(bridge=mock_bridge, sendblue_channel=ch)
        app.include_router(router)
        c = TestClient(app)

        # Without secret header -> rejected
        resp = c.post(
            "/webhooks/sendblue",
            json={
                "from_number": "+19127130720",
                "content": "Hello",
                "is_outbound": False,
            },
        )
        assert resp.status_code == 403

        # With correct secret -> accepted
        resp = c.post(
            "/webhooks/sendblue",
            json={
                "from_number": "+19127130720",
                "content": "Hello",
                "is_outbound": False,
                "message_handle": "msg-002",
            },
            headers={"x-sendblue-secret": "mysecret"},
        )
        assert resp.status_code == 200

        # SendBlue's own header name -> accepted; wrong value -> rejected
        msg = {"from_number": "+19127130720", "content": "Hi", "is_outbound": False}
        resp = c.post(
            "/webhooks/sendblue",
            json={**msg, "message_handle": "msg-003"},
            headers={"sb-signing-secret": "mysecret"},
        )
        assert resp.status_code == 200
        resp = c.post(
            "/webhooks/sendblue",
            json=msg,
            headers={"sb-signing-secret": "wrong"},
        )
        assert resp.status_code == 403

    def test_no_bridge_returns_200(self, sendblue_channel):
        """When no bridge exists, webhook should not crash."""
        from openjarvis.server.webhook_routes import create_webhook_router

        app = FastAPI()
        router = create_webhook_router(bridge=None, sendblue_channel=sendblue_channel)
        app.include_router(router)
        c = TestClient(app, headers={"x-sendblue-secret": "testsecret"})

        resp = c.post(
            "/webhooks/sendblue",
            json={
                "from_number": "+19127130720",
                "content": "Hello",
                "is_outbound": False,
            },
        )
        assert resp.status_code == 200

    def test_no_secret_configured_is_rejected(self, mock_bridge):
        """Fail closed: a channel without a webhook_secret rejects all posts."""
        from openjarvis.channels.sendblue import SendBlueChannel
        from openjarvis.server.webhook_routes import create_webhook_router

        ch = SendBlueChannel(api_key_id="k", api_secret_key="s", from_number="+1555")
        ch.connect()
        app = FastAPI()
        router = create_webhook_router(bridge=mock_bridge, sendblue_channel=ch)
        app.include_router(router)
        c = TestClient(app)

        resp = c.post(
            "/webhooks/sendblue",
            json={"from_number": "+19127130720", "content": "Hi", "is_outbound": False},
        )
        assert resp.status_code == 403
        mock_bridge.handle_incoming.assert_not_called()


# ---------------------------------------------------------------------------
# Health endpoint (requires agent_manager_routes)
# ---------------------------------------------------------------------------


class TestSendBlueHealth:
    @pytest.fixture
    def health_app(self, sendblue_channel):
        app = FastAPI()
        app.state.sendblue_channel = sendblue_channel
        app.state.channel_bridge = MagicMock()
        app.state.channel_bridge._channels = {"sendblue": sendblue_channel}

        from openjarvis.server.agent_manager_routes import (
            create_agent_manager_router,
        )

        mgr = MagicMock()
        mgr.list_agents.return_value = []
        routers = create_agent_manager_router(mgr)
        sendblue_router = routers[4]  # 5th element is sendblue_router
        app.include_router(sendblue_router)
        return app

    def test_health_ready(self, health_app):
        c = TestClient(health_app)
        resp = c.get("/v1/channels/sendblue/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["channel_connected"] is True
        assert data["bridge_wired"] is True
        assert data["ready"] is True

    def test_health_not_ready(self):
        app = FastAPI()
        # No sendblue_channel or bridge on state

        from openjarvis.server.agent_manager_routes import (
            create_agent_manager_router,
        )

        mgr = MagicMock()
        mgr.list_agents.return_value = []
        routers = create_agent_manager_router(mgr)
        sendblue_router = routers[4]
        app.include_router(sendblue_router)

        c = TestClient(app)
        resp = c.get("/v1/channels/sendblue/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is False


def test_webhook_accepts_secret_of_any_configured_binding(mock_bridge):
    """After a restart the primary channel may be a different binding than the
    one whose secret SendBlue sends; any configured binding must verify."""
    from openjarvis.channels.sendblue import SendBlueChannel
    from openjarvis.server.webhook_routes import create_webhook_router

    primary = SendBlueChannel(
        api_key_id="k", api_secret_key="s", from_number="+1555", webhook_secret="A"
    )
    other = SendBlueChannel(
        api_key_id="k", api_secret_key="s", from_number="+1555", webhook_secret="B"
    )
    app = FastAPI()
    app.state.sendblue_channel = primary
    app.state.sendblue_channels = [primary, other]
    app.include_router(create_webhook_router(bridge=mock_bridge))
    c = TestClient(app)
    msg = {"from_number": "+19127130720", "content": "hi", "is_outbound": False}

    assert (
        c.post(
            "/webhooks/sendblue", json=msg, headers={"sb-signing-secret": "B"}
        ).status_code
        == 200
    )
    assert (
        c.post(
            "/webhooks/sendblue", json=msg, headers={"sb-signing-secret": "C"}
        ).status_code
        == 403
    )


def test_photo_webhook_saves_media_logs_and_tracks_delivery(tmp_path, monkeypatch):
    """A photo-only text is processed: media saved by id (no URL kept), the
    reply is sent with a handle, and delivery status is recorded."""
    import time

    from openjarvis.server import webhook_routes
    from openjarvis.server.session_store import SessionStore
    from openjarvis.server.webhook_routes import create_webhook_router

    monkeypatch.setattr(webhook_routes, "_media_dir", lambda: tmp_path)
    monkeypatch.setattr(webhook_routes, "_CAPTION_WAIT_SECONDS", 0.1)
    monkeypatch.setattr(
        webhook_routes,
        "_track_delivery",
        lambda ch, st, row, handle: st.update_delivery(row, "DELIVERED"),
    )
    channel = MagicMock()
    channel.webhook_secret = "S"
    channel.fetch_media.return_value = (b"\x89PNGdata", "image/png")
    channel.send_message.return_value = {
        "ok": True,
        "handle": "h9",
        "status": "QUEUED",
        "error": "",
    }
    store = SessionStore(db_path=":memory:")
    bridge = MagicMock()
    bridge._session_store = store
    bridge.respond.return_value = {
        "content": "Nice dog.",
        "agent": "Jarvis",
        "model": "qwen3.5:9b",
    }
    app = FastAPI()
    app.state.sendblue_channel = channel
    app.include_router(create_webhook_router(bridge=bridge))
    c = TestClient(app, headers={"sb-signing-secret": "S"})
    photo = {
        "from_number": "+1555",
        "content": "",
        "media_url": "https://cdn.example/p.png",
        "message_handle": "in1",
    }
    assert c.post("/webhooks/sendblue", json=photo).status_code == 200

    def delivered():
        convs = store.logged_conversations()
        return convs and convs[0]["messages"][-1]["delivery_status"] == "DELIVERED"

    for _ in range(60):
        if delivered():
            break
        time.sleep(0.05)
    assert bridge.respond.call_args.kwargs["images"]
    (conv,) = store.logged_conversations()
    user, reply = conv["messages"]
    assert user["attachments"][0]["type"] == "image/png"
    assert "cdn.example" not in str(conv)
    assert reply["delivery_status"] == "DELIVERED"
    assert reply["model"] == "qwen3.5:9b"
    assert len(list(tmp_path.iterdir())) == 1

    # SendBlue retrying the same message handle is ignored.
    c.post("/webhooks/sendblue", json={**photo, "content": "again"})
    time.sleep(0.2)
    assert bridge.respond.call_count == 1


def test_photo_then_caption_gets_one_reply_that_sees_the_photo(tmp_path, monkeypatch):
    """iMessage sends a photo and its caption as two webhooks; they must be
    answered together, once, with the photo attached to the caption."""
    import time

    from openjarvis.server import webhook_routes
    from openjarvis.server.webhook_routes import create_webhook_router

    monkeypatch.setattr(webhook_routes, "_media_dir", lambda: tmp_path)
    monkeypatch.setattr(webhook_routes, "_CAPTION_WAIT_SECONDS", 5)
    channel = MagicMock()
    channel.webhook_secret = "S"
    channel.fetch_media.return_value = (bytes([0x89]) + b"PNGdata", "image/png")
    channel.send_message.return_value = {"ok": True, "handle": "", "error": ""}
    bridge = MagicMock()
    bridge._session_store = None
    bridge.respond.return_value = {"content": "GTA ends tmrw", "agent": "Jarvis"}
    app = FastAPI()
    app.state.sendblue_channel = channel
    app.include_router(create_webhook_router(bridge=bridge))
    c = TestClient(app, headers={"sb-signing-secret": "S"})
    import threading

    # TestClient blocks until background work ends, so send the photo from a
    # thread and the caption while the photo is still waiting for it.
    photo = threading.Thread(
        target=c.post,
        args=("/webhooks/sendblue",),
        kwargs={
            "json": {
                "from_number": "+1555",
                "content": "",
                "media_url": "https://x/p.png",
            }
        },
    )
    photo.start()
    time.sleep(1)
    c.post("/webhooks/sendblue", json={"from_number": "+1555", "content": "Read that"})
    photo.join()
    for _ in range(100):
        if channel.send_message.call_count:
            break
        time.sleep(0.05)
    time.sleep(0.3)
    assert bridge.respond.call_count == 1
    assert bridge.respond.call_args.args[1] == "Read that"
    assert len(bridge.respond.call_args.kwargs["images"]) == 1
    assert channel.send_message.call_count == 1
