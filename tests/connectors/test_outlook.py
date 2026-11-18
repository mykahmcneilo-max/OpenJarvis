"""Tests for OutlookConnector — thin subclass of GmailIMAPConnector."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from openjarvis.connectors.oauth import load_tokens
from openjarvis.connectors.outlook import OutlookConnector
from openjarvis.core.registry import ConnectorRegistry


def test_outlook_registered() -> None:
    ConnectorRegistry.register_value("outlook", OutlookConnector)
    assert ConnectorRegistry.contains("outlook")
    cls = ConnectorRegistry.get("outlook")
    assert cls.connector_id == "outlook"
    assert cls.display_name == "Outlook / Microsoft 365"


def test_outlook_uses_correct_imap_host() -> None:
    conn = OutlookConnector()
    assert conn._imap_host == "outlook.office365.com"


def test_outlook_auth_url() -> None:
    conn = OutlookConnector()
    assert "microsoft.com" in conn.auth_url()


def test_outlook_handle_callback(tmp_path: Path) -> None:
    creds_path = str(tmp_path / "outlook.json")
    conn = OutlookConnector(credentials_path=creds_path)
    mock_imap = MagicMock()
    mock_imap.login.return_value = ("OK", [])
    mock_imap.select.return_value = ("OK", [])
    mock_imap.response.return_value = ("UIDVALIDITY", [b"777"])
    with patch.object(conn, "_make_imap_client", return_value=mock_imap):
        conn.handle_callback("user@outlook.com:mypassword123")
    tokens = load_tokens(creds_path)
    assert tokens is not None
    assert tokens["email"] == "user@outlook.com"
    assert tokens["password"] == "mypassword123"
    assert tokens["validated"] is True


def test_outlook_is_connected(tmp_path: Path) -> None:
    creds_path = str(tmp_path / "outlook.json")
    conn = OutlookConnector(credentials_path=creds_path)
    assert conn.is_connected() is False
    mock_imap = MagicMock()
    mock_imap.login.return_value = ("OK", [])
    mock_imap.select.return_value = ("OK", [])
    mock_imap.response.return_value = ("UIDVALIDITY", [b"777"])
    with patch.object(conn, "_make_imap_client", return_value=mock_imap):
        conn.handle_callback("user@outlook.com:pass")
    assert conn.is_connected() is True


def test_outlook_sync_source_is_outlook(tmp_path: Path) -> None:
    creds_path = str(tmp_path / "outlook.json")
    conn = OutlookConnector(credentials_path=creds_path)

    mock_imap = MagicMock()
    mock_imap.login.return_value = ("OK", [])
    mock_imap.select.return_value = ("OK", [])
    mock_imap.response.return_value = ("UIDVALIDITY", [b"777"])

    raw_email = (
        b"From: sender@test.com\r\n"
        b"To: user@outlook.com\r\n"
        b"Subject: Test Email\r\n"
        b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\n"
        b"Message-ID: <test123@test.com>\r\n"
        b"\r\n"
        b"Hello from Outlook test"
    )
    mock_imap.uid.side_effect = [
        ("OK", [b"1"]),
        ("OK", [(b"1", raw_email)]),
    ]
    mock_imap.logout.return_value = ("OK", [])

    with patch.object(conn, "_make_imap_client", return_value=mock_imap):
        conn.handle_callback("user@outlook.com:pass")
        docs = list(conn.sync())

    assert len(docs) == 1
    assert docs[0].source == "outlook"
    assert docs[0].doc_id.startswith("outlook:")
    assert docs[0].title == "Test Email"
    assert mock_imap.uid.call_args_list[0].args == ("SEARCH", None, "ALL")
    assert mock_imap.uid.call_args_list[1].args == ("FETCH", b"1", "(RFC822)")


def _fake_jwt(claims: dict) -> str:
    import base64
    import json

    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"x.{body}.y"


def _ok_imap() -> MagicMock:
    imap = MagicMock()
    imap.authenticate.return_value = ("OK", [])
    imap.select.return_value = ("OK", [])
    imap.response.return_value = ("UIDVALIDITY", [b"777"])
    return imap


def test_outlook_device_code_sign_in_uses_xoauth2(tmp_path: Path) -> None:
    creds_path = str(tmp_path / "outlook.json")
    responses = iter(
        [
            {"device_code": "dc", "interval": 1, "expires_in": 60, "message": "go"},
            {"error": "authorization_pending"},
            {
                "access_token": "AT1",
                "refresh_token": "RT1",
                "expires_in": 3600,
                "id_token": _fake_jwt({"preferred_username": "me@outlook.com"}),
            },
        ]
    )
    calls = []

    def post(url, data):
        calls.append((url, data))
        return next(responses)

    shown = []
    conn = OutlookConnector(credentials_path=creds_path, http_post=post)
    imap = _ok_imap()
    with patch.object(conn, "_make_imap_client", return_value=imap):
        email = conn.connect_with_device_code(
            "client-123", show=shown.append, sleep=lambda _s: None
        )

    assert email == "me@outlook.com"
    assert shown == ["go"]
    assert "IMAP.AccessAsUser.All" in calls[0][1]["scope"]
    mech, auth_cb = imap.authenticate.call_args.args
    assert mech == "XOAUTH2"
    assert auth_cb(b"") == b"user=me@outlook.com\x01auth=Bearer AT1\x01\x01"
    tokens = load_tokens(creds_path)
    assert tokens["auth"] == "oauth" and tokens["validated"] is True
    assert "password" not in tokens
    assert conn.is_connected() is True


def test_outlook_refreshes_expired_token(tmp_path: Path) -> None:
    from openjarvis.connectors.oauth import save_tokens

    creds_path = str(tmp_path / "outlook.json")
    save_tokens(
        creds_path,
        {
            "auth": "oauth",
            "email": "me@outlook.com",
            "client_id": "client-123",
            "tenant": "common",
            "access_token": "OLD",
            "refresh_token": "RT1",
            "expires_at": 0,
            "validated": True,
        },
    )
    posted = []

    def post(url, data):
        posted.append(data)
        return {"access_token": "NEW", "refresh_token": "RT2", "expires_in": 3600}

    conn = OutlookConnector(credentials_path=creds_path, http_post=post)
    imap = _ok_imap()
    with patch.object(conn, "_make_imap_client", return_value=imap):
        conn._close_imap(conn._open_imap())

    assert posted[0]["grant_type"] == "refresh_token"
    assert posted[0]["refresh_token"] == "RT1"
    assert imap.authenticate.call_args.args[1](b"").endswith(b"Bearer NEW\x01\x01")
    assert load_tokens(creds_path)["refresh_token"] == "RT2"
