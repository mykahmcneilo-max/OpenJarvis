"""Add an event to the user's Google Calendar ("add this to my schedule").

Uses the Google Calendar connection the user already authorized (full
``calendar`` scope). It can only create events: nothing here edits or
deletes, so a phone message can't wipe the user's schedule.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Dict

import httpx

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

_API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def _credentials_path() -> str:
    from openjarvis.core.config import DEFAULT_CONFIG_DIR

    return str(DEFAULT_CONFIG_DIR / "connectors" / "gcalendar.json")


def _insert(token: str, body: Dict[str, Any]) -> Dict[str, Any]:
    resp = httpx.post(
        _API,
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


def _parse(value: str) -> datetime | date:
    value = value.strip()
    if len(value) == 10:
        return date.fromisoformat(value)
    parsed = datetime.fromisoformat(value)
    # Times without an offset are the user's local time.
    return parsed if parsed.tzinfo else parsed.astimezone()


def build_event(params: Dict[str, Any]) -> Dict[str, Any]:
    """Google Calendar event body from the tool arguments."""
    title = str(params.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")
    start = _parse(str(params.get("start") or ""))
    end_raw = str(params.get("end") or "").strip()
    body: Dict[str, Any] = {"summary": title[:300]}
    for key in ("location", "description"):
        text = str(params.get(key) or "").strip()
        if text:
            body[key] = text[:4000]

    if isinstance(start, datetime):
        end = _parse(end_raw) if end_raw else start + timedelta(hours=1)
        if not isinstance(end, datetime):
            raise ValueError("end must be a date-time when start is a date-time")
        if end.tzinfo is None:
            end = end.astimezone()
        while end <= start:  # "8pm-1am" ends the next day
            end += timedelta(days=1)
        body["start"] = {"dateTime": start.isoformat()}
        body["end"] = {"dateTime": end.isoformat()}
    else:
        end_day = _parse(end_raw) if end_raw else start
        if isinstance(end_day, datetime):
            end_day = end_day.date()
        # All-day end dates are exclusive in Google Calendar.
        body["start"] = {"date": start.isoformat()}
        body["end"] = {"date": (max(end_day, start) + timedelta(days=1)).isoformat()}
    return body


@ToolRegistry.register("calendar_add")
class CalendarAddTool(BaseTool):
    """Create one event on the user's Google Calendar."""

    tool_id = "calendar_add"
    is_local = False

    def __init__(self, insert: Any = None) -> None:
        self._insert = insert

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="calendar_add",
            description=(
                "Add an event to the user's Google Calendar. Use when they ask "
                "to add/put/schedule something, including from a photo of a "
                "flyer or screenshot: pull out the title, date, time, place "
                "and key details. Resolve relative dates ('sat', 'tmrw') "
                "against today. Creates one event; can't edit or delete."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event name."},
                    "start": {
                        "type": "string",
                        "description": (
                            "Local start, ISO: '2026-11-21T20:00' or "
                            "'2026-11-21' for an all-day event."
                        ),
                    },
                    "end": {
                        "type": "string",
                        "description": (
                            "Local end, same format. Optional (1 hour for "
                            "timed events). An end before the start rolls "
                            "into the next day."
                        ),
                    },
                    "location": {"type": "string", "description": "Address/venue."},
                    "description": {
                        "type": "string",
                        "description": (
                            "Important details: price, dress code, RSVP or "
                            "ticket link, who's hosting, what to bring."
                        ),
                    },
                },
                "required": ["title", "start"],
            },
            category="calendar",
            latency_estimate=1.5,
            timeout_seconds=30.0,
            required_capabilities=["network:fetch"],
        )

    def execute(self, **params: Any) -> ToolResult:
        try:
            body = build_event(params)
        except ValueError as exc:
            return self._fail(f"Couldn't add it: {exc}")
        try:
            if self._insert is not None:
                event = self._insert(body)
            else:
                from openjarvis.connectors.google_auth import call_with_refresh

                event = call_with_refresh(_insert, _credentials_path(), body)
        except FileNotFoundError:
            return self._fail("Google Calendar isn't connected.")
        except httpx.HTTPStatusError as exc:
            return self._fail(
                f"Google Calendar refused it (HTTP {exc.response.status_code})."
            )
        except Exception as exc:  # never echo tokens or request details
            return self._fail(f"Couldn't add it ({type(exc).__name__}).")
        summary = {
            "added": event.get("summary", body["summary"]),
            "start": body["start"],
            "end": body["end"],
            "location": body.get("location", ""),
        }
        return ToolResult(
            tool_name="calendar_add",
            content=json.dumps(summary, ensure_ascii=False),
            success=True,
            metadata={"event_id": event.get("id", "")},
        )

    @staticmethod
    def _fail(message: str) -> ToolResult:
        return ToolResult(tool_name="calendar_add", content=message, success=False)


__all__ = ["CalendarAddTool", "build_event"]
