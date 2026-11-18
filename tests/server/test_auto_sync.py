"""Tests for the background auto-sync service."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock

from openjarvis.server.auto_sync import AutoSync, backoff_seconds


class _Clock:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


def _http(connected=("gmail",), sync_state="idle", error=None):
    http = MagicMock()

    def get(url, **_):
        resp = MagicMock()
        if url.endswith("/v1/connectors"):
            resp.json.return_value = {
                "connectors": [
                    {"connector_id": c, "connected": True, "display_name": c}
                    for c in connected
                ]
                + [{"connector_id": "imessage", "connected": True}]
            }
        else:
            resp.json.return_value = {
                "state": sync_state,
                "error": error,
                "items_synced": 3,
            }
        return resp

    http.get.side_effect = get
    http.post.return_value = MagicMock(status_code=200)
    return http


def test_backoff_grows_and_caps():
    assert backoff_seconds(0) == 600
    assert backoff_seconds(1) == 1200
    assert backoff_seconds(10) == 7200


def test_runs_connectors_and_importers_then_waits_interval(tmp_path: Path):
    (tmp_path / "mac_apple_sync.py").write_text("")
    clock = _Clock()
    run = MagicMock(
        return_value=subprocess.CompletedProcess([], 0, stdout="iMessage: 5 items")
    )
    svc = AutoSync("http://x", tmp_path, http=_http(), run_script=run, clock=clock)
    assert svc.run_due() == 2  # gmail + apple; imessage is fed by the importer
    jobs = {j["id"]: j for j in svc.snapshot()["jobs"]}
    assert jobs["gmail"]["state"] == "ok" and jobs["apple"]["state"] == "ok"
    assert svc.run_due() == 0  # nothing due until 10 minutes pass
    clock.t += 601
    assert svc.run_due() == 2


def test_unreachable_mac_is_unavailable_not_error(tmp_path: Path):
    (tmp_path / "mac_apple_sync.py").write_text("")
    run = MagicMock(
        return_value=subprocess.CompletedProcess(
            [], 1, stdout="", stderr="Mac sync skipped (Mac asleep or unreachable?)"
        )
    )
    svc = AutoSync(
        "http://x", tmp_path, http=_http(connected=()), run_script=run, clock=_Clock()
    )
    svc.run_due()
    (job,) = svc.snapshot()["jobs"]
    assert job["state"] == "unavailable" and job["failures"] == 0
    assert "Existing Apple data is kept" in job["detail"]


def test_failures_back_off_and_state_survives_restart(tmp_path: Path):
    clock = _Clock()
    svc = AutoSync("http://x", tmp_path, http=_http(error="token expired"), clock=clock)
    svc.run_due()
    (job,) = svc.snapshot()["jobs"]
    assert job["state"] == "error" and job["failures"] == 1
    assert job["next_run"] == clock.t + 1200

    restarted = AutoSync("http://x", tmp_path, http=_http(), clock=clock)
    (job2,) = restarted.snapshot()["jobs"]
    assert job2["failures"] == 1 and job2["error"] == "token expired"
    assert restarted.run_due() == 0  # still backing off


def test_interrupted_sync_resumes_as_pending(tmp_path: Path):
    svc = AutoSync("http://x", tmp_path, http=_http(), clock=_Clock())
    svc.run_due()
    svc.state.jobs["gmail"].state = "syncing"
    svc._save()
    again = AutoSync("http://x", tmp_path, http=_http(), clock=_Clock())
    assert again.state.jobs["gmail"].state == "pending"


def test_jobs_never_overlap_and_single_instance_lock(tmp_path: Path):
    (tmp_path / "onedrive_index.py").write_text("")
    active = {"now": 0, "max": 0}
    lock = threading.Lock()

    def slow(*a, **k):
        with lock:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        threading.Event().wait(0.05)
        with lock:
            active["now"] -= 1
        return subprocess.CompletedProcess([], 0, stdout="ok")

    svc = AutoSync("http://x", tmp_path, http=_http(), run_script=slow)
    svc.run_due()
    assert active["max"] == 1

    first = AutoSync("http://x", tmp_path, http=_http())
    second = AutoSync("http://x", tmp_path, http=_http())
    assert first.start(initial_delay=3600) is True
    assert second.start(initial_delay=3600) is False
    first.stop()
