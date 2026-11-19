"""School/training assignments: "what do I have due?" and "add this assignment".

Sources:
- A tracker note in the Obsidian vault (``Study/Assignments.md``), a Markdown
  table Jarvis reads and appends to. Covers anything without a feed (PCTE,
  screenshots the user texts in).
- Optional calendar feeds (D2L/Brightspace "Subscribe" iCal links), one URL per
  line in ``~/.openjarvis/assignment_feeds.txt``. The URL is a secret link, so it
  is never echoed back.

``assignment_add`` only appends a row to that one note; it can't edit or
delete anything else.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, List, Optional

import httpx

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec

HEADER = "| Assignment | Class | Due | Status |\n|---|---|---|---|\n"
TEMPLATE = (
    "---\ntype: tracker\ntags: [study, assignments]\n---\n\n# Assignments\n\n"
    'Jarvis reads this to answer "what do I have due" and adds rows when you text it '
    "an assignment or a screenshot. Mark Status `done` when finished. "
    "Related: [[School & Classes]], [[DDS-M Kit]].\n\n" + HEADER
)
DONE = {"done", "complete", "completed", "submitted", "x", "✅"}


def _config_dir() -> Path:
    from openjarvis.core.paths import get_config_dir

    return get_config_dir()


def tracker_path() -> Path:
    try:
        raw = (_config_dir() / "connectors" / "obsidian.json").read_text(
            encoding="utf-8"
        )
        vault = Path(json.loads(raw)["vault_path"])
    except (OSError, ValueError, KeyError):
        vault = Path.home() / "Documents" / "Jarvis Notes"
    return vault / "Study" / "Assignments.md"


def _parse_due(text: str) -> Optional[date]:
    text = text.strip()
    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m/%d",
        "%b %d %Y",
        "%b %d",
        "%B %d",
    ):
        try:
            d = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if "%Y" not in fmt and "%y" not in fmt:
            today = date.today()
            d = d.replace(year=today.year)
            if d < today - timedelta(days=60):
                d = d.replace(year=today.year + 1)
        return d
    return None


def read_tracker(path: Path) -> List[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        if not line.lstrip().startswith("|"):  # prose with [[a|b]] links isn't a row
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if (
            len(cells) < 3
            or cells[0] in ("Assignment", "")
            or set(cells[0]) <= {"-", ":"}
        ):
            continue
        cells += [""] * (4 - len(cells))
        rows.append(
            {
                "title": cells[0],
                "class": cells[1],
                "due": _parse_due(cells[2]),
                "due_text": cells[2],
                "status": cells[3],
                "source": "tracker",
            }
        )
    return rows


def _unfold(ics: str) -> List[str]:
    out: List[str] = []
    for line in ics.replace("\r\n", "\n").split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def parse_ics(ics: str) -> List[dict]:
    events, cur = [], None
    for line in _unfold(ics):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT" and cur is not None:
            events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, val = line.split(":", 1)
            cur[key.split(";")[0]] = val
    rows = []
    for ev in events:
        raw = ev.get("DTEND") or ev.get("DTSTART") or ""
        m = re.match(r"(\d{8})", raw)
        if not m:
            continue
        title = ev.get("SUMMARY", "Untitled").replace("\\,", ",").replace("\\;", ";")
        rows.append(
            {
                "title": title,
                "class": ev.get("LOCATION", "").replace("\\,", ","),
                "due": datetime.strptime(m.group(1), "%Y%m%d").date(),
                "due_text": "",
                "status": "",
                "source": "feed",
            }
        )
    return rows


def _feeds() -> List[str]:
    try:
        text = (_config_dir() / "assignment_feeds.txt").read_text(encoding="utf-8")
    except OSError:
        return []
    return [u.strip() for u in text.splitlines() if u.strip().startswith("http")]


@ToolRegistry.register("assignments_due")
class AssignmentsDueTool(BaseTool):
    """List assignments that are due soon or overdue."""

    tool_id = "assignments_due"
    is_local = True

    def __init__(
        self, fetch: Optional[Callable[[str], str]] = None, path: Optional[Path] = None
    ):
        self._fetch = fetch or (
            lambda url: httpx.get(url, timeout=20, follow_redirects=True).text
        )
        self._path = path

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="assignments_due",
            description=(
                "The user's school and training assignments (KSU/D2L, PCTE, etc.) "
                "due soon or overdue, from their tracker and D2L calendar feed. "
                "Use for 'what assignments do I have', 'what's due this week', "
                "'anything overdue'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "How many days ahead to include (default 14).",
                    },
                },
            },
            category="productivity",
            latency_estimate=1.0,
            timeout_seconds=30.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        days = params.get("days", 14)
        days = days if isinstance(days, int) and not isinstance(days, bool) else 14
        today = date.today()
        horizon = today + timedelta(days=max(1, min(days, 365)))
        path = self._path or tracker_path()
        rows = read_tracker(path)
        feed_errors = 0
        for url in _feeds():
            try:
                rows += parse_ics(self._fetch(url))
            except Exception:  # never echo the secret feed URL
                feed_errors += 1
        open_rows = [r for r in rows if r["status"].lower() not in DONE]
        due = sorted(
            (
                r
                for r in open_rows
                if r["due"]
                and r["due"] <= horizon
                and r["due"] >= today - timedelta(days=30)
            ),
            key=lambda r: r["due"],
        )
        undated = [r for r in open_rows if not r["due"]]
        items = [
            {
                "assignment": r["title"],
                "class": r["class"],
                "due": r["due"].isoformat(),
                "overdue": r["due"] < today,
                "days_left": (r["due"] - today).days,
                "status": r["status"],
            }
            for r in due
        ] + [
            {
                "assignment": r["title"],
                "class": r["class"],
                "due": r["due_text"] or "no date",
                "status": r["status"],
            }
            for r in undated
        ]
        note = ""
        if not rows:
            note = (
                "No assignments tracked yet. The user can text them in (or a "
                "screenshot) and you add them with assignment_add, or connect "
                "D2L's calendar feed."
            )
        if feed_errors:
            note += f" {feed_errors} calendar feed(s) couldn't be read right now."
        return ToolResult(
            tool_name="assignments_due",
            content=json.dumps(
                {"today": today.isoformat(), "items": items, "note": note.strip()},
                ensure_ascii=False,
            ),
            success=True,
            metadata={"count": len(items)},
        )


@ToolRegistry.register("assignment_add")
class AssignmentAddTool(BaseTool):
    """Append an assignment to the tracker note."""

    tool_id = "assignment_add"
    is_local = True

    def __init__(self, path: Optional[Path] = None):
        self._path = path

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="assignment_add",
            description=(
                "Add an assignment to the user's tracker (when they text one in, "
                "or send a screenshot of D2L/PCTE). Call once per assignment."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Assignment name."},
                    "class": {
                        "type": "string",
                        "description": "Course or program, e.g. 'KSU OS', 'PCTE'.",
                    },
                    "due": {
                        "type": "string",
                        "description": "Due date, ISO like 2026-11-24 (or blank).",
                    },
                },
                "required": ["title"],
            },
            category="productivity",
            latency_estimate=0.2,
            timeout_seconds=10.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        def cell(key: str, limit: int) -> str:
            return re.sub(r"[|\r\n]+", " ", str(params.get(key) or "")).strip()[:limit]

        title, klass, due = cell("title", 200), cell("class", 80), cell("due", 40)
        if not title:
            return ToolResult(
                tool_name="assignment_add",
                content="Need an assignment name.",
                success=False,
            )
        path = self._path or tracker_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        text = path.read_text(encoding="utf-8") if path.exists() else TEMPLATE
        if HEADER.strip().splitlines()[0] not in text:
            text = text.rstrip("\n") + "\n\n" + HEADER
        if any(
            r["title"].lower() == title.lower() and r["class"].lower() == klass.lower()
            for r in read_tracker(path)
        ):
            return ToolResult(
                tool_name="assignment_add",
                content=f"Already tracked: {title}",
                success=True,
            )
        text = text.rstrip("\n") + f"\n| {title} | {klass} | {due} | todo |\n"
        path.write_text(text, encoding="utf-8")
        return ToolResult(
            tool_name="assignment_add",
            content=json.dumps({"added": title, "class": klass, "due": due}),
            success=True,
        )


# Read-only views of the KSU reports Codex's daily school check writes into the
# vault (Study/KSU). Fixed file set: the tool can't read anything else.
SCHOOL_NOTES = {
    "deadlines": "Daily Deadline Report.md",
    "grades": "Grades and Recovery.md",
    "gpa": "GPA Scholarship and Next Steps.md",
    "semester": "Semester Plan.md",
    "registration": "Registration and School Mail.md",
}


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4 :].lstrip()
    return text


@ToolRegistry.register("school_status")
class SchoolStatusTool(BaseTool):
    """Read the latest KSU school report (deadlines, grades, GPA/HOPE, ...)."""

    tool_id = "school_status"
    is_local = True

    def __init__(self, folder: Optional[Path] = None, limit: int = 6000):
        self._folder = folder
        self._limit = limit

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="school_status",
            description=(
                "The user's latest verified KSU school report. topic: 'deadlines' "
                "(7 days behind to 14 ahead, submitted or not), 'grades' (scores, "
                "retakes, zeros), 'gpa' (GPA, HOPE scholarship, holds, aid, "
                "master's/transfer plan), 'semester' (all classes to term end), "
                "'registration' (spring registration, school email). Use for "
                "'did I submit', 'what's my GPA', 'am I keeping HOPE', "
                "'when's my final'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "enum": list(SCHOOL_NOTES),
                        "description": "Which report (default deadlines).",
                    },
                },
            },
            category="productivity",
            latency_estimate=0.2,
            timeout_seconds=10.0,
        )

    def execute(self, **params: Any) -> ToolResult:
        topic = params.get("topic") or "deadlines"
        if topic not in SCHOOL_NOTES:
            topic = "deadlines"
        folder = self._folder or tracker_path().parent / "KSU"
        path = folder / SCHOOL_NOTES[topic]
        try:
            text = _strip_frontmatter(path.read_text(encoding="utf-8"))
        except OSError:
            return ToolResult(
                tool_name="school_status",
                content=(
                    f"No '{topic}' report yet. Codex's daily school check writes it; "
                    "use assignments_due for the tracker instead."
                ),
                success=False,
            )
        age = (date.today() - datetime.fromtimestamp(path.stat().st_mtime).date()).days
        if len(text) > self._limit:
            text = text[: self._limit].rsplit("\n", 1)[0] + "\n…(trimmed)"
        stale = (
            f" Report is {age} days old; say it may be out of date." if age > 1 else ""
        )
        return ToolResult(
            tool_name="school_status",
            content=f"[{topic} report, updated {age} day(s) ago.{stale}]\n\n{text}",
            success=True,
            metadata={"topic": topic, "age_days": age},
        )


__all__ = [
    "AssignmentsDueTool",
    "AssignmentAddTool",
    "SchoolStatusTool",
    "parse_ics",
    "read_tracker",
]
