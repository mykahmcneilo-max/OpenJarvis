"""Background auto-sync: keep every connected source fresh every 10 minutes.

One service inside the API server:

* Connected connectors are synced through the server's own
  ``POST /v1/connectors/{id}/sync`` path, which already refuses to start a
  second sync of the same source ("already_syncing").
* Local importer scripts in ``~/.openjarvis`` (Apple data from the Mac,
  OneDrive, Outlook calendar) run as subprocesses, one at a time.
* Jobs never overlap: one worker thread runs them sequentially, and a lock
  file keeps a second server process from starting another worker.
* Failures back off exponentially (capped); successes reset the interval.
* State is persisted to ``auto_sync.json`` so it resumes after a restart.
* An unreachable Mac is reported as ``unavailable`` (existing Apple data is
  kept and stays searchable), not as an error.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 600
MAX_BACKOFF_SECONDS = 2 * 3600
CONNECTOR_TIMEOUT_SECONDS = 20 * 60
CONNECTOR_WAIT_SECONDS = 60  # then move on and check back next tick
RECHECK_SECONDS = 60
SCRIPT_TIMEOUT_SECONDS = 20 * 60
TICK_SECONDS = 30

# importer script -> (job id, label shown in the UI)
IMPORTERS = {
    "mac_apple_sync.py": ("apple", "Apple (Messages, Notes, Contacts, Calendar)"),
    "onedrive_index.py": ("onedrive", "OneDrive"),
    "outlook_calendar_index.py": ("outlook_calendar", "Outlook Calendar"),
}
# Sources fed by an importer rather than their own connector sync.
IMPORTED_SOURCES = {
    "imessage",
    "apple_notes",
    "apple_contacts",
    "apple_calendar",
    "apple_music",
    "apple_health",
}


@dataclass
class JobState:
    id: str
    label: str
    kind: str  # "connector" | "importer"
    state: str = "pending"  # pending|syncing|ok|error|unavailable
    last_success: Optional[float] = None
    last_attempt: Optional[float] = None
    next_run: float = 0.0
    failures: int = 0
    error: str = ""
    detail: str = ""


@dataclass
class AutoSyncState:
    interval_seconds: int = INTERVAL_SECONDS
    jobs: Dict[str, JobState] = field(default_factory=dict)


def backoff_seconds(failures: int, interval: int = INTERVAL_SECONDS) -> int:
    """Delay before retrying after *failures* consecutive failures."""
    if failures <= 0:
        return interval
    return min(interval * (2**failures), MAX_BACKOFF_SECONDS)


class AutoSync:
    """Runs due sync jobs sequentially in one daemon thread."""

    def __init__(
        self,
        base_url: str,
        home: Path,
        *,
        interval: int = INTERVAL_SECONDS,
        python: str = sys.executable,
        repo_dir: Optional[Path] = None,
        http: Any = None,
        run_script: Optional[Callable[..., subprocess.CompletedProcess]] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._home = home
        self._interval = interval
        self._python = python
        self._repo = repo_dir
        self._http = http
        self._run_script = run_script or subprocess.run
        self._clock = clock
        self._state_path = home / "auto_sync.json"
        self._lock_path = home / "auto_sync.lock"
        self._lock_file: Any = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._mutex = threading.Lock()
        self.state = self._load()

    # -- persistence ---------------------------------------------------------

    def _load(self) -> AutoSyncState:
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            jobs = {k: JobState(**v) for k, v in raw.get("jobs", {}).items()}
            for job in jobs.values():
                if job.state == "syncing":  # interrupted by a restart
                    job.state, job.detail = "pending", ""
            return AutoSyncState(interval_seconds=self._interval, jobs=jobs)
        except (OSError, ValueError, TypeError):
            return AutoSyncState(interval_seconds=self._interval)

    def _save(self) -> None:
        data = {
            "interval_seconds": self.state.interval_seconds,
            "jobs": {k: asdict(v) for k, v in self.state.jobs.items()},
        }
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self._state_path)

    def snapshot(self) -> Dict[str, Any]:
        with self._mutex:
            return {
                "interval_seconds": self.state.interval_seconds,
                "running": bool(self._thread and self._thread.is_alive()),
                "jobs": [asdict(j) for j in self.state.jobs.values()],
            }

    # -- single instance -----------------------------------------------------

    def _acquire_lock(self) -> bool:
        try:
            self._lock_file = open(self._lock_path, "a+")
            if os.name == "nt":
                import msvcrt

                self._lock_file.seek(0)
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            if self._lock_file:
                self._lock_file.close()
                self._lock_file = None
            return False

    # -- job discovery -------------------------------------------------------

    def _client(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=30)
        return self._http

    def discover(self) -> List[JobState]:
        found: List[JobState] = []
        try:
            resp = self._client().get(f"{self._base}/v1/connectors")
            for c in resp.json().get("connectors", []):
                cid = c.get("connector_id") or c.get("id")
                if not cid or not c.get("connected") or cid in IMPORTED_SOURCES:
                    continue
                found.append(
                    JobState(
                        id=cid, label=c.get("display_name") or cid, kind="connector"
                    )
                )
        except Exception as exc:
            logger.debug("auto-sync: connector discovery failed: %s", exc)
        for script, (jid, label) in IMPORTERS.items():
            if (self._home / script).is_file():
                found.append(JobState(id=jid, label=label, kind="importer"))
        return found

    def _merge(self, discovered: List[JobState]) -> None:
        with self._mutex:
            keep = {j.id for j in discovered}
            for job in discovered:
                if job.id not in self.state.jobs:
                    self.state.jobs[job.id] = job
                else:
                    self.state.jobs[job.id].label = job.label
            for jid in list(self.state.jobs):
                if jid not in keep:
                    del self.state.jobs[jid]

    # -- running -------------------------------------------------------------

    def _connector_status(self, job: JobState) -> Dict[str, Any]:
        return (
            self._client().get(f"{self._base}/v1/connectors/{job.id}/sync").json() or {}
        )

    @staticmethod
    def _finished(status: Dict[str, Any]) -> tuple[str, str]:
        if status.get("error"):
            return "error", str(status["error"])[:300]
        return "ok", f"{status.get('items_synced', 0)} items"

    def _sync_connector(self, job: JobState) -> tuple[str, str]:
        """Start (or check on) a connector sync without blocking the queue.

        A sync still running after :data:`CONNECTOR_WAIT_SECONDS` keeps going
        in the server; the job is re-checked on a later tick, so one long
        backfill (e.g. Gmail) can't hold up every other source.
        """
        status = self._connector_status(job)
        running = status.get("state") in ("syncing", "running")
        if running:
            started = job.detail.startswith("running since ")
            since = float(job.detail.split()[-1]) if started else self._clock()
            if self._clock() - since > CONNECTOR_TIMEOUT_SECONDS:
                return "error", "sync still running after 20 minutes"
            return "syncing", f"running since {since}"
        if job.state == "syncing":  # our earlier sync finished meanwhile
            return self._finished(status)
        resp = self._client().post(f"{self._base}/v1/connectors/{job.id}/sync")
        if resp.status_code >= 400:
            return "error", f"sync refused ({resp.status_code})"
        started_at = self._clock()
        deadline = started_at + CONNECTOR_WAIT_SECONDS
        while not self._stop.is_set() and self._clock() < deadline:
            status = self._connector_status(job)
            if status.get("state") not in ("syncing", "running"):
                return self._finished(status)
            self._stop.wait(3)
        return "syncing", f"running since {started_at}"

    def _run_importer(self, job: JobState) -> tuple[str, str]:
        script = next(s for s, (jid, _) in IMPORTERS.items() if jid == job.id)
        try:
            proc = self._run_script(
                [self._python, str(self._home / script)],
                cwd=str(self._repo or self._home),
                capture_output=True,
                text=True,
                timeout=SCRIPT_TIMEOUT_SECONDS,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        except subprocess.TimeoutExpired:
            return "error", "importer timed out after 20 minutes"
        out = (proc.stdout or "").strip().splitlines()
        err = (proc.stderr or "").strip().splitlines()
        if proc.returncode == 0:
            return "ok", "; ".join(out[-4:])[:300]
        text = " ".join(err[-2:] or out[-2:])
        if job.id == "apple" and ("Mac sync skipped" in text or "Can't find" in text):
            return "unavailable", (
                "Mac not reachable (asleep or off Wi-Fi). Existing Apple data is "
                "kept and searchable; fresh import resumes when the Mac is back."
            )
        return "error", text[:300] or f"exit code {proc.returncode}"

    def run_job(self, job: JobState) -> None:
        now = self._clock()
        with self._mutex:
            if job.state != "syncing":  # keep "running since" while re-checking
                job.last_attempt = now
                if job.kind == "importer":
                    job.state = "syncing"
            self._save()
        try:
            if job.kind == "connector":
                outcome, detail = self._sync_connector(job)
            else:
                outcome, detail = self._run_importer(job)
        except Exception as exc:
            outcome, detail = "error", f"{type(exc).__name__}: {exc}"[:300]
        end = self._clock()
        with self._mutex:
            job.state = outcome
            if outcome == "syncing":  # still running in the server
                job.detail = detail
                job.next_run = end + RECHECK_SECONDS
                self._save()
                return
            if outcome == "ok":
                job.last_success, job.failures, job.error = end, 0, ""
                job.detail = detail
            elif outcome == "unavailable":
                job.failures, job.error, job.detail = 0, "", detail
            else:
                job.failures += 1
                job.error = detail
            job.next_run = end + backoff_seconds(job.failures, self._interval)
            self._save()

    def run_due(self) -> int:
        """Run every job that is due now; returns how many ran."""
        self._merge(self.discover())
        ran = 0
        for job in sorted(self.state.jobs.values(), key=lambda j: j.next_run):
            if self._stop.is_set():
                break
            if job.next_run <= self._clock():
                self.run_job(job)
                ran += 1
        return ran

    def _loop(self, initial_delay: float) -> None:
        if self._stop.wait(initial_delay):
            return
        while not self._stop.is_set():
            try:
                self.run_due()
            except Exception:
                logger.exception("auto-sync tick failed")
            self._stop.wait(TICK_SECONDS)

    def start(self, initial_delay: float = 60) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        if not self._acquire_lock():
            logger.info("auto-sync already running in another process")
            return False
        self._thread = threading.Thread(
            target=self._loop, args=(initial_delay,), name="auto-sync", daemon=True
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._lock_file:
            self._lock_file.close()
            self._lock_file = None


__all__ = ["AutoSync", "JobState", "backoff_seconds", "INTERVAL_SECONDS"]
