"""In-memory job registry for asynchronous batch processing.

A batch upload returns instantly with a job_id; the actual matching runs
in a background thread and writes progress into the registry. The UI
polls ``GET /match/batch/{job_id}`` for status and ``/download`` for the
result once finished.

Why in-memory:
- We run with a single uvicorn worker (matching engine holds a large
  in-process TF-IDF matrix), so a process-local dict is the simplest store.
- For multi-worker deployment swap this for Redis or a DB-backed queue.

Lifecycle:
  pending -> running -> done | failed
The job entry also keeps the resulting xlsx bytes so download is O(1).
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class BatchJob:
    job_id: str
    filename: str
    total: int = 0
    processed: int = 0
    # pending | running | done | failed | cancelled
    status: str = "pending"
    error: Optional[str] = None
    result_bytes: Optional[bytes] = None
    result_filename: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    # Set by the cancel endpoint; the worker checks this between rows.
    cancel_requested: bool = False

    def to_public(self) -> dict:
        """Serializable progress snapshot for the polling endpoint."""
        now = time.time()
        elapsed = (self.finished_at or now) - self.started_at
        rate = (self.processed / elapsed) if elapsed > 0 and self.processed else 0.0
        remaining = max(self.total - self.processed, 0)
        eta = (remaining / rate) if rate > 0 else None
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "status": self.status,
            "total": self.total,
            "processed": self.processed,
            "percent": (self.processed / self.total * 100.0) if self.total else 0.0,
            "rate_per_s": round(rate, 2),
            "eta_s": round(eta, 1) if eta is not None else None,
            "elapsed_s": round(elapsed, 1),
            "error": self.error,
            # download is offered for both fully-finished and partial-cancelled runs.
            "download_ready": self.result_bytes is not None and self.status in ("done", "cancelled"),
            "cancel_requested": self.cancel_requested,
        }


class BatchCancelled(Exception):
    """Raised inside the worker to short-circuit a row loop on cancel."""


class JobRegistry:
    """Thread-safe registry of batch jobs + a worker pool to run them."""

    def __init__(self, max_workers: int = 2) -> None:
        self._jobs: dict[str, BatchJob] = {}
        self._lock = threading.Lock()
        # Long-running CPU work — separate pool from request handlers.
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="batch")

    def create(self, filename: str) -> BatchJob:
        job = BatchJob(job_id=uuid.uuid4().hex, filename=filename)
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> BatchJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def submit(self, job: BatchJob, work: Callable[[BatchJob], None]) -> None:
        """Schedule ``work(job)`` on the worker pool. The work function is
        responsible for updating job.processed / status while running."""
        def runner() -> None:
            job.status = "running"
            try:
                work(job)
                if job.status not in ("failed", "cancelled"):
                    job.status = "done"
            except BatchCancelled:
                job.status = "cancelled"
            except Exception as exc:  # noqa: BLE001
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
            finally:
                job.finished_at = time.time()

        self._executor.submit(runner)

    def request_cancel(self, job_id: str) -> bool:
        """Mark the given job as cancel-requested. Returns True if a running
        job was found; False if the job is missing or already terminal."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status not in ("pending", "running"):
                return False
            job.cancel_requested = True
            return True


# Process-wide singleton.
REGISTRY = JobRegistry()
