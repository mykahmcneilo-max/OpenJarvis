"""SendBlue channel — iMessage/SMS API adapter.

Sends and receives iMessages (blue bubbles!) and SMS via the SendBlue API.
The agent gets a dedicated phone number; users text that number to interact.

API reference: https://docs.sendblue.com/api-v2/
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from openjarvis.channels._stubs import (
    BaseChannel,
    ChannelHandler,
    ChannelMessage,
    ChannelStatus,
)
from openjarvis.core.events import EventBus, EventType
from openjarvis.core.registry import ChannelRegistry

logger = logging.getLogger(__name__)

_API_BASE = "https://api.sendblue.co"


def _status_value(data: Any) -> str:
    """Extract a status string; /api/status nests it ({"status": {"status": ...}})."""
    for _ in range(3):
        if isinstance(data, dict):
            data = data.get("status") or data.get("data") or ""
        else:
            break
    return str(data or "").upper() if isinstance(data, str) else ""


# Inbound photo limits (iMessage photos are typically well under 10 MB).
MAX_MEDIA_BYTES = 15 * 1024 * 1024
ALLOWED_MEDIA_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}


@ChannelRegistry.register("sendblue")
class SendBlueChannel(BaseChannel):
    """SendBlue iMessage/SMS channel adapter.

    Parameters
    ----------
    api_key_id:
        SendBlue API key ID.  Falls back to ``SENDBLUE_API_KEY_ID`` env var.
    api_secret_key:
        SendBlue API secret key.  Falls back to ``SENDBLUE_API_SECRET_KEY``
        env var.
    from_number:
        The SendBlue phone number to send from (E.164 format).
        Falls back to ``SENDBLUE_FROM_NUMBER`` env var.
    webhook_secret:
        Optional secret for verifying incoming webhook requests.
    bus:
        Optional event bus for publishing channel events.
    """

    channel_id = "sendblue"

    def __init__(
        self,
        *,
        api_key_id: str = "",
        api_secret_key: str = "",
        from_number: str = "",
        webhook_secret: str = "",
        bus: Optional[EventBus] = None,
    ) -> None:
        self._api_key_id = api_key_id or os.environ.get("SENDBLUE_API_KEY_ID", "")
        self._api_secret_key = api_secret_key or os.environ.get(
            "SENDBLUE_API_SECRET_KEY", ""
        )
        self._from_number = from_number or os.environ.get("SENDBLUE_FROM_NUMBER", "")
        self._webhook_secret = webhook_secret
        self._bus = bus
        self._handlers: List[ChannelHandler] = []
        self._status = ChannelStatus.DISCONNECTED

    @classmethod
    def from_binding_config(
        cls, config: Dict[str, Any], *, bus: Optional[EventBus] = None
    ) -> "SendBlueChannel":
        """Build a channel from a stored binding config.

        Accepts both key styles in use: ``api_key_id``/``api_secret_key``/
        ``from_number`` (server API) and ``api_key``/``api_secret``/
        ``phone_number`` (desktop app setup wizard).
        """
        number = str(config.get("from_number") or config.get("phone_number") or "")
        number = number.strip()
        if number.isdigit():
            number = "+" + number
        return cls(
            api_key_id=config.get("api_key_id") or config.get("api_key") or "",
            api_secret_key=(
                config.get("api_secret_key") or config.get("api_secret") or ""
            ),
            from_number=number,
            webhook_secret=config.get("webhook_secret", ""),
            bus=bus,
        )

    # -- connection lifecycle ---------------------------------------------------

    def connect(self) -> None:
        """Validate credentials and mark as connected."""
        if not self._api_key_id or not self._api_secret_key:
            logger.warning("No SendBlue API credentials configured")
            self._status = ChannelStatus.ERROR
            return
        self._status = ChannelStatus.CONNECTED

    def disconnect(self) -> None:
        """Mark as disconnected."""
        self._status = ChannelStatus.DISCONNECTED

    # -- send / receive --------------------------------------------------------

    def send(
        self,
        channel: str,
        content: str,
        *,
        conversation_id: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> bool:
        """Send an iMessage/SMS via SendBlue.

        Parameters
        ----------
        channel:
            Recipient phone number in E.164 format (e.g. "+15551234567").
        content:
            Message text to send.
        """
        if not self._api_key_id or not self._api_secret_key:
            logger.warning("Cannot send: no SendBlue credentials configured")
            return False

        try:
            import httpx

            payload: Dict[str, Any] = {
                "number": channel,
                "content": content,
            }
            if self._from_number:
                payload["from_number"] = self._from_number

            resp = httpx.post(
                f"{_API_BASE}/api/send-message",
                headers={
                    "sb-api-key-id": self._api_key_id,
                    "sb-api-secret-key": self._api_secret_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30.0,
            )
            if resp.status_code < 300:
                self._publish_sent(channel, content, conversation_id)
                return True
            logger.warning(
                "SendBlue API returned status %d: %s",
                resp.status_code,
                resp.text[:200],
            )
            return False
        except Exception:
            logger.debug("SendBlue send failed", exc_info=True)
            return False

    def _headers(self) -> Dict[str, str]:
        return {
            "sb-api-key-id": self._api_key_id,
            "sb-api-secret-key": self._api_secret_key,
            "Content-Type": "application/json",
        }

    def send_message(self, number: str, content: str) -> Dict[str, Any]:
        """Send and return ``{"ok", "handle", "status", "error"}``.

        Unlike :meth:`send`, the result carries SendBlue's message handle so
        delivery can be confirmed later with :meth:`delivery_status`.
        """
        if not self._api_key_id or not self._api_secret_key:
            return {
                "ok": False,
                "handle": "",
                "status": "ERROR",
                "error": "no credentials",
            }
        payload: Dict[str, Any] = {"number": number, "content": content}
        if self._from_number:
            payload["from_number"] = self._from_number
        try:
            import httpx

            resp = httpx.post(
                f"{_API_BASE}/api/send-message",
                headers=self._headers(),
                json=payload,
                timeout=30.0,
            )
            data = resp.json() if resp.content else {}
        except Exception as exc:  # network failure
            return {
                "ok": False,
                "handle": "",
                "status": "ERROR",
                "error": type(exc).__name__,
            }
        ok = resp.status_code < 300 and data.get("status") != "ERROR"
        if ok:
            self._publish_sent(number, content, "")
        return {
            "ok": ok,
            "handle": str(data.get("message_handle") or ""),
            "status": str(data.get("status") or ("QUEUED" if ok else "ERROR")),
            "error": "" if ok else str(data.get("error_message") or resp.status_code),
        }

    def delivery_status(self, handle: str) -> str:
        """Return SendBlue's current status for *handle* ("" if unknown)."""
        if not handle:
            return ""
        try:
            import httpx

            resp = httpx.get(
                f"{_API_BASE}/api/status",
                headers=self._headers(),
                params={"handle": handle},
                timeout=15.0,
            )
            if resp.status_code >= 300:
                return ""
            return _status_value(resp.json())
        except Exception:
            return ""

    def fetch_media(self, url: str) -> tuple[bytes, str]:
        """Download an inbound attachment; returns ``(data, content_type)``.

        Only https image downloads up to :data:`MAX_MEDIA_BYTES` are
        accepted. The URL is never logged (it is a bearer-style link).
        """
        from urllib.parse import urlparse

        import httpx

        if urlparse(url).scheme != "https":
            raise ValueError("attachment URL must be https")
        with httpx.stream("GET", url, timeout=30.0, follow_redirects=True) as resp:
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype not in ALLOWED_MEDIA_TYPES:
                raise ValueError(f"unsupported attachment type {ctype or 'unknown'}")
            data = bytearray()
            for chunk in resp.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_MEDIA_BYTES:
                    raise ValueError("attachment too large")
        return bytes(data), ctype

    def handle_webhook(self, payload: Dict[str, Any]) -> None:
        """Process an incoming webhook payload from SendBlue.

        Expected fields: from_number, content, to_number, message_handle,
        is_outbound, status, service.
        """
        if payload.get("is_outbound", False):
            return  # Ignore outbound status callbacks

        from_number = payload.get("from_number", "")
        content = payload.get("content", "")
        message_handle = payload.get("message_handle", "")

        if not from_number or not content:
            return

        msg = ChannelMessage(
            channel="sendblue",
            sender=from_number,
            content=content,
            message_id=message_handle,
        )

        for handler in self._handlers:
            try:
                handler(msg)
            except Exception:
                logger.exception("Handler failed for SendBlue message")

        if self._bus is not None:
            self._bus.publish(
                EventType.CHANNEL_MESSAGE_RECEIVED,
                {
                    "channel": "sendblue",
                    "sender": from_number,
                    "content": content,
                    "message_id": message_handle,
                    "service": payload.get("service", ""),
                },
            )

    def status(self) -> ChannelStatus:
        """Return the current connection status."""
        return self._status

    def list_channels(self) -> List[str]:
        """Return available channel identifiers."""
        return ["sendblue"]

    def on_message(self, handler: ChannelHandler) -> None:
        """Register a callback for incoming messages."""
        self._handlers.append(handler)

    # -- properties ------------------------------------------------------------

    @property
    def from_number(self) -> str:
        """The SendBlue phone number this channel sends from."""
        return self._from_number

    @property
    def api_key_id(self) -> str:
        return self._api_key_id

    @property
    def api_secret_key(self) -> str:
        return self._api_secret_key

    @property
    def webhook_secret(self) -> str:
        return self._webhook_secret

    # -- internal helpers -------------------------------------------------------

    def _publish_sent(self, channel: str, content: str, conversation_id: str) -> None:
        """Publish a CHANNEL_MESSAGE_SENT event on the bus."""
        if self._bus is not None:
            self._bus.publish(
                EventType.CHANNEL_MESSAGE_SENT,
                {
                    "channel": "sendblue",
                    "recipient": channel,
                    "content": content,
                    "conversation_id": conversation_id,
                },
            )


__all__ = ["SendBlueChannel"]
