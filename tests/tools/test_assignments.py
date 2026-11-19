"""assignments_due / assignment_add: 'what do I have due' over iMessage."""

from __future__ import annotations

import json
from datetime import date, timedelta

from openjarvis.tools import assignments
from openjarvis.tools.assignments import (
    AssignmentAddTool,
    AssignmentsDueTool,
    parse_ics,
)


def _due(tmp_path, monkeypatch, fetch=None, feeds=""):
    monkeypatch.setattr(assignments, "_config_dir", lambda: tmp_path)
    (tmp_path / "assignment_feeds.txt").write_text(feeds, encoding="utf-8")
    return AssignmentsDueTool(fetch=fetch, path=tmp_path / "Assignments.md")


def test_add_then_list_sorted_and_skips_done(tmp_path, monkeypatch):
    path = tmp_path / "Assignments.md"
    add = AssignmentAddTool(path=path)
    soon = (date.today() + timedelta(days=2)).isoformat()
    later = (date.today() + timedelta(days=9)).isoformat()
    assert add.execute(
        title="OS Assignment 7", **{"class": "KSU OS"}, due=later
    ).success
    assert add.execute(title="PCTE lab 4", **{"class": "PCTE"}, due=soon).success
    assert add.execute(title="Old quiz", due=soon).success
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "| Old quiz |  | " + soon + " | todo |",
            "| Old quiz |  | " + soon + " | done |",
        ),
        encoding="utf-8",
    )
    assert (
        "Already tracked"
        in add.execute(title="pcte LAB 4", **{"class": "pcte"}).content
    )

    out = json.loads(_due(tmp_path, monkeypatch).execute().content)
    names = [i["assignment"] for i in out["items"]]
    assert names == ["PCTE lab 4", "OS Assignment 7"]
    assert out["items"][0]["days_left"] == 2


def test_overdue_and_undated_are_listed(tmp_path, monkeypatch):
    path = tmp_path / "Assignments.md"
    add = AssignmentAddTool(path=path)
    add.execute(title="Late essay", due=(date.today() - timedelta(days=3)).isoformat())
    add.execute(title="Kit review")
    out = json.loads(_due(tmp_path, monkeypatch).execute().content)
    late, undated = out["items"]
    assert late["overdue"] is True and late["assignment"] == "Late essay"
    assert undated == {
        "assignment": "Kit review",
        "class": "",
        "due": "no date",
        "status": "todo",
    }


def test_d2l_feed_is_merged_and_url_never_echoed(tmp_path, monkeypatch):
    day = (date.today() + timedelta(days=5)).strftime("%Y%m%d")
    ics = (
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:Module 8 Quiz - Due\r\n"
        f"DTSTART:{day}T235900Z\r\nLOCATION:CYBR 3100\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    tool = _due(
        tmp_path,
        monkeypatch,
        fetch=lambda url: ics,
        feeds="https://d2l.example/feed?token=SECRET\n",
    )
    out = json.loads(tool.execute(days=7).content)
    assert out["items"][0]["assignment"] == "Module 8 Quiz - Due"
    assert out["items"][0]["class"] == "CYBR 3100"

    def boom(url):
        raise RuntimeError(url)

    broken = _due(
        tmp_path,
        monkeypatch,
        fetch=boom,
        feeds="https://d2l.example/feed?token=SECRET\n",
    )
    content = broken.execute().content
    assert "SECRET" not in content and "couldn't be read" in content


def test_empty_tracker_explains_how_to_fill_it(tmp_path, monkeypatch):
    out = json.loads(_due(tmp_path, monkeypatch).execute().content)
    assert out["items"] == [] and "assignment_add" in out["note"]


def test_parse_ics_handles_folded_lines():
    ics = "BEGIN:VEVENT\nSUMMARY:Long\n  title\nDTEND;VALUE=DATE:20261201\nEND:VEVENT\n"
    (row,) = parse_ics(ics)
    assert row["title"] == "Long title" and row["due"].isoformat() == "2026-12-01"


def test_prose_with_alias_links_is_not_a_row(tmp_path):
    path = tmp_path / "Assignments.md"
    path.write_text(
        "[[Study/School HQ|School HQ]] · [[Plan|plan]]\n\n"
        "| Assignment | Class | Due | Status |\n|---|---|---|---|\n"
        "| Quiz 3 | CSE | 2026-11-20 | todo |\n",
        encoding="utf-8",
    )
    assert [r["title"] for r in assignments.read_tracker(path)] == ["Quiz 3"]


def test_school_status_reads_only_its_reports(tmp_path):
    from openjarvis.tools.assignments import SchoolStatusTool

    (tmp_path / "GPA Scholarship and Next Steps.md").write_text(
        "---\ntags: [ksu]\n---\n# GPA\nHOPE 3.50, eligible\n", encoding="utf-8"
    )
    tool = SchoolStatusTool(folder=tmp_path, limit=40)
    out = tool.execute(topic="gpa")
    assert out.success and "HOPE 3.50" in out.content and "tags:" not in out.content
    # unknown topics fall back to deadlines, which doesn't exist here
    missing = tool.execute(topic="../../secrets")
    assert not missing.success and "deadlines" in missing.content
