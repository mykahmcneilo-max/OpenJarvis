"""Outlook / Microsoft 365 connector — reads email via IMAP.

Thin subclass of GmailIMAPConnector that defaults to the Outlook IMAP host
and relabels documents with source='outlook'.

Two ways to authenticate:

* **Microsoft sign-in (OAuth, recommended).** Required for personal
  Outlook.com / Hotmail accounts: Microsoft turned off basic auth (app
  passwords) for their IMAP on 2024-09-16. Register a public-client app
  (personal accounts, "Allow public client flows" on, delegated
  ``IMAP.AccessAsUser.All``), then call :meth:`connect_with_device_code`.
  IMAP then authenticates with XOAUTH2 and refreshes tokens automatically.
* **App password.** Still works for some Microsoft 365 work accounts.
"""

from __future__ import annotations

import base64
import imaplib
import json
import time
from datetime import datetime
from typing import Any, Callable, Dict, Iterator, Optional

from openjarvis.connectors._stubs import Document
from openjarvis.connectors.gmail_imap import (
    _UIDVALIDITY_ATTRIBUTE,
    GmailIMAPConnector,
    _read_uidvalidity,
)
from openjarvis.connectors.oauth import load_tokens, save_tokens
from openjarvis.core.config import DEFAULT_CONFIG_DIR
from openjarvis.core.registry import ConnectorRegistry

_DEFAULT_CREDENTIALS_PATH = str(DEFAULT_CONFIG_DIR / "connectors" / "outlook.json")

_AUTHORITY = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0"
_IMAP_SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All"
_OAUTH_SCOPES = f"{_IMAP_SCOPE} offline_access openid email profile"
_OAUTH_PLACEHOLDER = "<oauth>"
_REFRESH_MARGIN_SECONDS = 120


def _jwt_claims(token: str) -> Dict[str, Any]:
    """Decode a JWT payload without verifying it (identity hint only)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def xoauth2_string(email_address: str, access_token: str) -> bytes:
    """Build the SASL XOAUTH2 initial response for IMAP."""
    return f"user={email_address}\x01auth=Bearer {access_token}\x01\x01".encode()


@ConnectorRegistry.register("outlook")
class OutlookConnector(GmailIMAPConnector):
    """Outlook connector using IMAP + Microsoft OAuth (or an app password)."""

    connector_id = "outlook"
    display_name = "Outlook / Microsoft 365"
    _default_imap_host = "outlook.office365.com"

    def __init__(
        self,
        email_address: str = "",
        app_password: str = "",
        credentials_path: str = "",
        *,
        max_messages: Optional[int] = None,
        http_post: Optional[Callable[..., Any]] = None,
    ) -> None:
        super().__init__(
            email_address,
            app_password,
            credentials_path or _DEFAULT_CREDENTIALS_PATH,
            max_messages=max_messages,
        )
        self._http_post = http_post

    # -- OAuth helpers ---------------------------------------------------------

    def _post(self, url: str, data: Dict[str, str]) -> Dict[str, Any]:
        if self._http_post is not None:
            return self._http_post(url, data)
        import httpx

        resp = httpx.post(url, data=data, timeout=30)
        return resp.json()

    def _oauth_tokens(self) -> Dict[str, Any]:
        tokens = load_tokens(self._credentials_path) or {}
        return tokens if tokens.get("auth") == "oauth" else {}

    def _save_oauth(self, tokens: Dict[str, Any], result: Dict[str, Any]) -> None:
        tokens["access_token"] = result["access_token"]
        if result.get("refresh_token"):
            tokens["refresh_token"] = result["refresh_token"]
        tokens["expires_at"] = time.time() + int(result.get("expires_in", 3600))
        save_tokens(self._credentials_path, tokens)

    def _access_token(self) -> str:
        """Return a valid access token, refreshing it when close to expiry."""
        tokens = self._oauth_tokens()
        if not tokens:
            raise imaplib.IMAP4.error("Outlook is not signed in")
        if tokens.get("access_token") and (
            float(tokens.get("expires_at", 0)) - time.time() > _REFRESH_MARGIN_SECONDS
        ):
            return str(tokens["access_token"])
        result = self._post(
            _AUTHORITY.format(tenant=tokens.get("tenant", "common")) + "/token",
            {
                "grant_type": "refresh_token",
                "client_id": str(tokens["client_id"]),
                "refresh_token": str(tokens.get("refresh_token", "")),
                "scope": _OAUTH_SCOPES,
            },
        )
        if "access_token" not in result:
            raise imaplib.IMAP4.error(
                f"Outlook token refresh failed: {result.get('error', 'unknown')}"
            )
        self._save_oauth(tokens, result)
        return str(result["access_token"])

    def connect_with_device_code(
        self,
        client_id: str,
        *,
        tenant: str = "common",
        show: Callable[[str], None] = print,
        sleep: Callable[[float], None] = time.sleep,
    ) -> str:
        """Sign in with Microsoft's device-code flow; returns the email address.

        *show* receives Microsoft's instruction text (URL + one-time code).
        """
        base = _AUTHORITY.format(tenant=tenant)
        start = self._post(
            base + "/devicecode", {"client_id": client_id, "scope": _OAUTH_SCOPES}
        )
        if "device_code" not in start:
            raise RuntimeError(
                "Microsoft rejected the sign-in request: "
                f"{start.get('error_description') or start.get('error')}"
            )
        show(start.get("message") or f"Go to {start['verification_uri']}")

        interval = int(start.get("interval", 5))
        deadline = time.time() + int(start.get("expires_in", 900))
        while time.time() < deadline:
            sleep(interval)
            result = self._post(
                base + "/token",
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": client_id,
                    "device_code": start["device_code"],
                },
            )
            error = result.get("error")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            if error:
                raise RuntimeError(
                    f"Sign-in failed: {result.get('error_description') or error}"
                )
            claims = _jwt_claims(result.get("id_token", ""))
            email_address = str(
                claims.get("email") or claims.get("preferred_username") or ""
            )
            if not email_address:
                raise RuntimeError("Sign-in returned no email address")
            tokens: Dict[str, Any] = {
                "auth": "oauth",
                "email": email_address,
                "client_id": client_id,
                "tenant": tenant,
                "imap_host": self._default_imap_host,
                "imap_port": 993,
                "imap_security": "tls",
            }
            self._save_oauth(tokens, result)
            # Prove IMAP works before marking the connection valid.
            self._close_imap(self._open_imap())
            tokens = self._oauth_tokens()
            tokens["validated"] = True
            save_tokens(self._credentials_path, tokens)
            self._credentials_validated = True
            return email_address
        raise RuntimeError("Sign-in timed out; run it again")

    # -- IMAP overrides ----------------------------------------------------------

    def _resolve_connection(self) -> tuple[str, str, str, int, str, bool]:
        email_address, password, host, port, security, validated = (
            super()._resolve_connection()
        )
        if not password and self._oauth_tokens():
            password = _OAUTH_PLACEHOLDER
        return email_address, password, host, port, security, validated

    def _open_authenticated_imap(
        self,
        email_address: str,
        password: str,
        host: str,
        port: int,
        security: str,
    ) -> imaplib.IMAP4:
        if password != _OAUTH_PLACEHOLDER:
            return super()._open_authenticated_imap(
                email_address, password, host, port, security
            )
        auth = xoauth2_string(email_address, self._access_token())
        imap = self._make_imap_client(host, port, security)
        try:
            status, _ = imap.authenticate("XOAUTH2", lambda _challenge: auth)
            if status != "OK":
                raise imaplib.IMAP4.error("Outlook XOAUTH2 login rejected")
            status, _ = imap.select("INBOX", readonly=True)
            if status != "OK":
                raise imaplib.IMAP4.error("Unable to select INBOX read-only")
            setattr(imap, _UIDVALIDITY_ATTRIBUTE, _read_uidvalidity(imap))
            return imap
        except Exception:
            self._close_imap(imap)
            raise

    def auth_url(self) -> str:
        return "https://microsoft.com/devicelogin"

    def sync(
        self,
        *,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
    ) -> Iterator[Document]:
        for doc in super().sync(since=since, cursor=cursor):
            doc.source = "outlook"
            doc.doc_id = doc.doc_id.replace("gmail:", "outlook:", 1)
            doc.url = "https://outlook.live.com/mail/0/inbox"
            yield doc
