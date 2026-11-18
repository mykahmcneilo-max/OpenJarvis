"""calendar_add: turn "add this to my schedule" into a Google Calendar event."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from openjarvis.tools.calendar_add import CalendarAddTool, build_event


def test_timed_event_from_a_flyer():
    insert = MagicMock(return_value={"id": "e1", "summary": "Hive Art Social"})
    out = CalendarAddTool(insert=insert).execute(
        title="Hive Art Social",
        start="2026-11-21T20:00",
        end="2026-11-21T01:00",  # 8pm-1am runs past midnight
        location="333 Peters St SW, Atlanta",
        description="$10 at the door",
    )
    body = insert.call_args.args[0]
    start = datetime.fromisoformat(body["start"]["dateTime"])
    end = datetime.fromisoformat(body["end"]["dateTime"])
    assert out.success and json.loads(out.content)["added"] == "Hive Art Social"
    assert start.hour == 20 and start.tzinfo is not None
    assert (end - start).total_seconds() == 5 * 3600
    assert body["location"] == "333 Peters St SW, Atlanta"
    assert body["description"] == "$10 at the door"


def test_default_one_hour_and_all_day_events():
    timed = build_event({"title": "Gym", "start": "2026-11-19T07:00"})
    a = datetime.fromisoformat(timed["start"]["dateTime"])
    b = datetime.fromisoformat(timed["end"]["dateTime"])
    assert (b - a).total_seconds() == 3600
    day = build_event({"title": "Trip", "start": "2026-11-27", "end": "2026-11-29"})
    assert day["start"] == {"date": "2026-11-27"}
    assert day["end"] == {"date": "2026-11-30"}  # exclusive end


@pytest.mark.parametrize("params", [{"title": "", "start": "2026-11-21"}, {}])
def test_missing_title_fails_without_calling_google(params):
    insert = MagicMock()
    out = CalendarAddTool(insert=insert).execute(**params)
    assert not out.success
    insert.assert_not_called()


def test_google_errors_are_reported_plainly():
    insert = MagicMock(side_effect=RuntimeError("token=secret"))
    out = CalendarAddTool(insert=insert).execute(title="x", start="2026-11-21")
    assert not out.success and "secret" not in out.content
