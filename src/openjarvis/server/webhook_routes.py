"""Webhook endpoints for receiving messages from external platforms."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Request, Response
from starlette.responses import PlainTextResponse

logger = logging.getLogger(__name__)

# Seconds before a single "still on it" note is texted for a slow reply.
_SLOW_REPLY_SECONDS = 90
# iMessage sends a photo and its caption as two webhooks. A photo with no
# text waits this long for the caption so the pair gets ONE reply.
_CAPTION_WAIT_SECONDS = 6.0
_FINAL_DELIVERY = {"DELIVERED", "ERROR", "DECLINED"}


def _media_dir():
    from openjarvis.core.paths import get_config_dir

    path = get_config_dir() / "media" / "sendblue"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_inbound_media(channel, url: str) -> tuple[list[str], list[dict]]:
    """Download one inbound photo; returns (base64 images, attachment records).

    Files are stored under ~/.openjarvis/media/sendblue with a random name;
    only that id is kept in history (never the SendBlue media URL).
    """
    import base64
    import uuid

    from openjarvis.channels.sendblue import ALLOWED_MEDIA_TYPES

    data, ctype = channel.fetch_media(url)
    media_id = uuid.uuid4().hex + ALLOWED_MEDIA_TYPES[ctype]
    (_media_dir() / media_id).write_bytes(data)
    record = {"id": media_id, "type": ctype, "size": len(data), "kind": "image"}
    return [base64.b64encode(data).decode("ascii")], [record]


def _track_delivery(channel, store, row_id: int, handle: str) -> None:
    """Poll SendBlue until the reply is DELIVERED/ERROR (max ~2 minutes)."""
    import time

    status = ""
    for delay in (2, 3, 5, 10, 15, 30, 60):
        time.sleep(delay)
        status = channel.delivery_status(handle) or status
        if status:
            store.update_delivery(row_id, status)
        if status in _FINAL_DELIVERY:
            break
    if status not in _FINAL_DELIVERY:
        logger.warning("SendBlue delivery unconfirmed after 2 min (last: %s)", status)


def _log_task_exception(task: asyncio.Task) -> None:
    """Log exceptions from background message handling tasks."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "Background message handling failed: %s",
            exc,
            exc_info=exc,
        )


def _validate_twilio_signature(
    auth_token: str,
    url: str,
    params: dict,
    signature: str,
) -> bool:
    """Validate Twilio webhook signature using the SDK.

    Fails closed: returns ``False`` if the SDK is not installed or
    if no auth_token is configured.
    """
    if not auth_token:
        logger.error("Twilio auth token not configured — rejecting webhook")
        return False
    try:
        from twilio.request_validator import RequestValidator

        validator = RequestValidator(auth_token)
        return validator.validate(url, params, signature)
    except ImportError:
        logger.error(
            "twilio SDK not installed — rejecting webhook. "
            "Install it: pip install twilio"
        )
        return False


def _format_for_sms(text: str) -> str:
    """Strip markdown/LaTeX formatting for clean iMessage/SMS display."""
    import re

    # Remove markdown headers (## Header -> Header)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    # Remove inline code backticks
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove LaTeX
    text = re.sub(r"\$\$[\s\S]*?\$\$", "", text)
    text = re.sub(r"\$[^$]+\$", "", text)
    # Remove markdown links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove image syntax ![alt](url)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    # Convert markdown bullet lists to plain bullets
    text = re.sub(r"^[\s]*[-*]\s+", "- ", text, flags=re.MULTILINE)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def create_webhook_router(
    bridge: Any,
    twilio_auth_token: str = "",
    bluebubbles_password: str = "",
    whatsapp_verify_token: str = "",
    whatsapp_app_secret: str = "",
    sendblue_channel: Any = None,
) -> APIRouter:
    """Create a FastAPI router with webhook endpoints.

    Args:
        bridge: ChannelBridge instance for routing messages.
        twilio_auth_token: Twilio auth token for signatures.
        bluebubbles_password: BlueBubbles server password.
        whatsapp_verify_token: WhatsApp verification token.
        whatsapp_app_secret: WhatsApp app secret for HMAC.
        sendblue_channel: SendBlueChannel instance for reply-back.
    """
    router = APIRouter(prefix="/webhooks", tags=["webhooks"])

    # ----------------------------------------------------------
    # Twilio SMS
    # ----------------------------------------------------------

    @router.post("/twilio")
    async def twilio_incoming(request: Request) -> Response:
        form = await request.form()
        params = dict(form)
        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)

        # Fail closed: an unconfigured token means we cannot verify the sender,
        # so reject rather than trust unsigned input.
        if not twilio_auth_token:
            logger.error("Twilio webhook rejected: TWILIO_AUTH_TOKEN not configured.")
            return Response("Webhook signature verification not configured", 403)
        if not _validate_twilio_signature(twilio_auth_token, url, params, signature):
            return Response("Invalid signature", status_code=403)

        from_number = params.get("From", "")
        body = params.get("Body", "")

        if not from_number or not body:
            return Response(
                content="<Response></Response>",
                media_type="application/xml",
            )

        # Use bridge or app.state.channel_bridge
        active_bridge = bridge or getattr(
            request.app.state,
            "channel_bridge",
            None,
        )

        def _handle_twilio() -> None:

            # Send ack via Twilio API
            try:
                from twilio.rest import Client

                # Get creds from app state bindings
                mgr = getattr(
                    request.app.state,
                    "agent_manager",
                    None,
                )
                twilio_client = None
                twilio_from = ""
                if mgr:
                    for agent in mgr.list_agents():
                        aid = agent.get("id", "")
                        for b in mgr.list_channel_bindings(aid):
                            if b.get("channel_type") == "twilio":
                                cfg = b.get("config", {})
                                sid = cfg.get("account_sid", "")
                                tok = cfg.get("auth_token", "")
                                twilio_from = cfg.get(
                                    "phone_number",
                                    "",
                                )
                                if sid and tok:
                                    twilio_client = Client(
                                        sid,
                                        tok,
                                    )
                                break

                if twilio_client and twilio_from:
                    twilio_client.messages.create(
                        body=("Message received! Working on it now..."),
                        from_=twilio_from,
                        to=from_number,
                    )
            except Exception as _e:
                logger.warning("Twilio ack failed: %s", _e)

            # Process via bridge or agent directly
            response = ""
            if active_bridge:
                response = active_bridge.handle_incoming(
                    from_number,
                    body,
                    "twilio",
                    max_length=1600,
                )
            else:
                # Direct agent fallback
                try:
                    from openjarvis.agents.deep_research import (
                        DeepResearchAgent,
                    )
                    from openjarvis.server.agent_manager_routes import (
                        _build_deep_research_tools,
                    )

                    engine = getattr(
                        request.app.state,
                        "engine",
                        None,
                    )
                    if engine:
                        tools = _build_deep_research_tools(
                            engine=engine,
                            model="",
                        )
                        agent = DeepResearchAgent(
                            engine=engine,
                            model=getattr(
                                engine,
                                "_model",
                                "",
                            ),
                            tools=tools,
                            bus=getattr(request.app.state, "bus", None),
                            capability_policy=getattr(
                                request.app.state, "capability_policy", None
                            ),
                            rate_limiter=getattr(
                                request.app.state, "rate_limiter", None
                            ),
                            agent_id="server:webhook:twilio",
                            max_turns=5,
                        )
                        result = agent.run(body)
                        response = result.content or ""
                except Exception as _exc:
                    response = f"Error: {_exc}"

            # Send response via Twilio
            if response and twilio_client and twilio_from:
                try:
                    clean = _format_for_sms(response)
                    # Twilio SMS limit is 1600 chars
                    if len(clean) > 1500:
                        clean = clean[:1500] + "\n\n(truncated)"
                    twilio_client.messages.create(
                        body=clean,
                        from_=twilio_from,
                        to=from_number,
                    )
                except Exception as _e:
                    logger.warning(
                        "Twilio reply failed: %s",
                        _e,
                    )

        task = asyncio.create_task(
            asyncio.to_thread(_handle_twilio),
        )
        task.add_done_callback(_log_task_exception)

        return Response(
            content="<Response></Response>",
            media_type="application/xml",
        )

    # ----------------------------------------------------------
    # BlueBubbles (iMessage)
    # ----------------------------------------------------------

    @router.post("/bluebubbles")
    async def bluebubbles_incoming(
        request: Request,
    ) -> Response:
        auth = request.headers.get("Authorization", "")
        # Fail closed when no password is configured.
        if not bluebubbles_password:
            logger.error("BlueBubbles webhook rejected: password not configured.")
            return Response("Webhook authentication not configured", 403)
        if not hmac.compare_digest(auth, bluebubbles_password):
            return Response("Invalid password", status_code=403)

        payload = await request.json()
        msg_type = payload.get("type", "")
        if msg_type != "new-message":
            return Response("OK", status_code=200)

        data = payload.get("data", {})
        handle = data.get("handle", {})
        sender = handle.get("address", "")
        text = data.get("text", "")

        task = asyncio.create_task(
            asyncio.to_thread(
                bridge.handle_incoming,
                sender,
                text,
                "bluebubbles",
            )
        )
        task.add_done_callback(_log_task_exception)

        return Response("OK", status_code=200)

    # ----------------------------------------------------------
    # WhatsApp Cloud API
    # ----------------------------------------------------------

    @router.get("/whatsapp")
    async def whatsapp_verify(request: Request) -> Response:
        mode = request.query_params.get("hub.mode", "")
        token = request.query_params.get("hub.verify_token", "")
        challenge = request.query_params.get("hub.challenge", "")

        # Fail closed: never echo the challenge if no verify token is set,
        # otherwise an empty token would match an empty query value.
        if not whatsapp_verify_token:
            return Response("Forbidden", status_code=403)
        if mode == "subscribe" and hmac.compare_digest(token, whatsapp_verify_token):
            return PlainTextResponse(challenge)
        return Response("Forbidden", status_code=403)

    @router.post("/whatsapp")
    async def whatsapp_incoming(
        request: Request,
    ) -> Response:
        body_bytes = await request.body()

        # Fail closed: reject when no app secret is configured to verify HMAC.
        if not whatsapp_app_secret:
            logger.error("WhatsApp webhook rejected: app secret not configured.")
            return Response("Webhook signature verification not configured", 403)
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = (
            "sha256="
            + hmac.new(
                whatsapp_app_secret.encode(),
                body_bytes,
                hashlib.sha256,
            ).hexdigest()
        )
        if not hmac.compare_digest(signature, expected):
            return Response("Invalid signature", status_code=403)

        payload = json.loads(body_bytes)
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    if message.get("type") != "text":
                        continue
                    sender = message.get("from", "")
                    text = message.get("text", {}).get("body", "")

                    task = asyncio.create_task(
                        asyncio.to_thread(
                            bridge.handle_incoming,
                            sender,
                            text,
                            "whatsapp",
                        )
                    )
                    task.add_done_callback(_log_task_exception)

        return Response("OK", status_code=200)

    # ----------------------------------------------------------
    # SendBlue (iMessage / SMS)
    # ----------------------------------------------------------

    @router.post("/sendblue")
    async def sendblue_incoming(request: Request) -> Response:
        payload = await request.json()

        # Every configured SendBlue binding is a candidate: the account's
        # webhook carries one of their secrets, and after a restart the
        # "primary" channel may belong to a different binding.
        primary = sendblue_channel or getattr(
            request.app.state, "sendblue_channel", None
        )
        candidates = [primary, *getattr(request.app.state, "sendblue_channels", [])]
        candidates = [c for c in candidates if c and getattr(c, "webhook_secret", "")]

        # Fail closed: require a configured channel + webhook secret to verify
        # the sender before processing any inbound message.
        if not candidates:
            logger.error("SendBlue webhook rejected: webhook_secret not configured.")
            return Response("Webhook secret not configured", status_code=403)
        # SendBlue sends the registered secret as ``sb-signing-secret``;
        # ``x-sendblue-secret`` is kept for existing setups/tests.
        header_secret = request.headers.get(
            "sb-signing-secret", ""
        ) or request.headers.get("x-sendblue-secret", "")
        sb = next(
            (
                c
                for c in candidates
                if hmac.compare_digest(header_secret, c.webhook_secret)
            ),
            None,
        )
        if sb is None:
            logger.warning("SendBlue webhook rejected: secret matched no binding")
            return Response("Invalid secret", status_code=403)

        # Ignore outbound status callbacks
        if payload.get("is_outbound", False):
            return Response("OK", status_code=200)

        from_number = payload.get("from_number", "")
        content = payload.get("content", "") or ""
        media_url = payload.get("media_url", "") or ""

        # A photo with no text is still a message.
        if not from_number or not (content.strip() or media_url):
            return Response("OK", status_code=200)

        # SendBlue retries webhooks; process each message handle once.
        handle_in = str(payload.get("message_handle") or "")
        seen = getattr(request.app.state, "_sendblue_seen", None)
        if seen is None:
            from collections import OrderedDict

            seen = request.app.state._sendblue_seen = OrderedDict()
        if handle_in:
            if handle_in in seen:
                return Response("OK", status_code=200)
            seen[handle_in] = True
            while len(seen) > 500:
                seen.popitem(last=False)

        # Capture sb for the closure
        reply_channel = sb
        # Also check for a dynamically-created bridge on app.state
        active_bridge = bridge or getattr(request.app.state, "channel_bridge", None)

        if not active_bridge:
            logger.warning("No channel bridge — cannot process SendBlue msg")
            return Response("OK", status_code=200)

        # Message queue tracking (per-sender)
        _sendblue_queues = getattr(request.app.state, "_sendblue_queues", None)
        if _sendblue_queues is None:
            import threading as _th

            _sendblue_queues = {}
            _sendblue_queues["_lock"] = _th.Lock()
            _sendblue_queues["_photos"] = {}  # sender -> photo awaiting caption
            request.app.state._sendblue_queues = _sendblue_queues

        # Pair a photo with the caption that follows it (one reply, and the
        # caption's answer can see the photo). Done here, in arrival order,
        # not in the worker threads, which can start in either order.
        import threading as _pair_th

        photos = _sendblue_queues["_photos"]
        my_photo = caption_for = None
        with _sendblue_queues["_lock"]:
            if media_url and not content.strip():
                my_photo = photos[from_number] = {
                    "images": [],
                    "ready": _pair_th.Event(),
                    "claimed": _pair_th.Event(),
                }
            elif content.strip():
                caption_for = photos.pop(from_number, None)
                if caption_for is not None:
                    caption_for["claimed"].set()

        def _handle_and_reply() -> None:
            import threading

            lock = _sendblue_queues["_lock"]

            # Track queue depth for this sender
            with lock:
                q = _sendblue_queues.setdefault(from_number, {"pending": 0})
                q["pending"] += 1

            # No "Message received!" acks: answer directly. Only if a reply
            # is genuinely slow, send ONE casual heads-up.
            done_event = threading.Event()

            def _send_reminders() -> None:
                if not done_event.wait(_SLOW_REPLY_SECONDS) and reply_channel:
                    reply_channel.send(from_number, "still on it, one sec")

            reminder = threading.Thread(target=_send_reminders, daemon=True)
            reminder.start()

            store = getattr(active_bridge, "_session_store", None)

            images: list[str] = []
            attachments: list[dict] = []
            media_note = ""
            try:
                if media_url:
                    try:
                        images, attachments = _save_inbound_media(
                            reply_channel, media_url
                        )
                    except Exception as exc:  # never log the media URL itself
                        logger.warning("SendBlue attachment rejected: %s", exc)
                        media_note = f"[photo could not be loaded: {exc}]"
            finally:
                if my_photo is not None:
                    my_photo["images"] = images
                    my_photo["ready"].set()
            if caption_for is not None:
                caption_for["ready"].wait(60)
                images = caption_for["images"] + images
            if store is not None:
                store.log_message(
                    from_number,
                    "sendblue",
                    "user",
                    (content + (f"\n{media_note}" if media_note else "")).strip(),
                    attachments=attachments,
                )

            try:
                if my_photo is not None and not media_note:
                    my_photo["claimed"].wait(_CAPTION_WAIT_SECONDS)
                    with lock:
                        if photos.get(from_number) is my_photo:
                            photos.pop(from_number)
                        if my_photo["claimed"].is_set():
                            return  # the caption's reply covers the photo
                if media_note and not content.strip():
                    why = media_note[1:-1].split(": ", 1)[-1]
                    reply = {
                        "content": "Your photo didn't come through on my end "
                        f"({why}). Try sending it again?",
                        "agent": "Jarvis",
                        "model": "",
                    }
                elif hasattr(active_bridge, "respond"):
                    reply = active_bridge.respond(
                        from_number, content, "sendblue", images=images
                    )
                else:
                    reply = {
                        "content": active_bridge.handle_incoming(
                            from_number, content, "sendblue"
                        ),
                        "agent": "Jarvis",
                        "model": "",
                    }
            finally:
                done_event.set()
                with lock:
                    q["pending"] = max(0, q["pending"] - 1)

            response = reply.get("content", "")
            if not (response and reply_channel):
                return
            text = _format_for_sms(response)
            sent = (
                reply_channel.send_message(from_number, text)
                if hasattr(reply_channel, "send_message")
                else {"ok": reply_channel.send(from_number, text), "handle": ""}
            )
            row_id = None
            if store is not None:
                row_id = store.log_message(
                    from_number,
                    "sendblue",
                    "assistant",
                    response,
                    agent=reply.get("agent", "Jarvis"),
                    model=reply.get("model", ""),
                    delivery_status=sent.get(
                        "status", "SENT" if sent.get("ok") else "ERROR"
                    ),
                    delivery_error=sent.get("error", ""),
                    message_handle=sent.get("handle", ""),
                )
            if not sent.get("ok"):
                logger.error("SendBlue reply not sent: %s", sent.get("error", ""))
                return
            # Confirm delivery: accepted by the API is not delivered.
            if store is not None and row_id and sent.get("handle"):
                _track_delivery(reply_channel, store, row_id, sent["handle"])

        task = asyncio.create_task(asyncio.to_thread(_handle_and_reply))
        task.add_done_callback(_log_task_exception)

        return Response("OK", status_code=200)

    return router
