"""In-memory job registry for streamed scrape progress.

The scraper takes anywhere from 15 to 90 seconds — too long for a single
blocking POST without surface area for "is it still running?". Per §8 of
LEAD_GENERATION_FIX.md, the frontend opens a job, then polls (or subscribes
via SSE) for status updates.

This module is the single source of truth for live job state. It is
single-process — a Redis-backed implementation is the upgrade if we ever
scale past one dyno, but for v1 a process-local dict is acceptable.

A job is keyed by `job_id` (a generated token) and bound to an `owner_uid`.
We only let the owner read or stream their own job.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# Background tasks live as long as the event loop; once finished, we keep
# them in the registry briefly so polling clients can collect the result.
_JOB_TTL_S = 300.0


@dataclass
class JobState:
    job_id: str
    owner_uid: str | None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    stage: str = "queued"
    progress: float = 0.0
    message: str | None = None
    raw_count: int = 0
    kept_count: int = 0
    dropped_count: int = 0
    enriched: int = 0
    enriched_total: int = 0
    partial: bool = False
    relaxed_filter: bool = False
    intent: dict[str, Any] | None = None
    kept_preview: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    finished: bool = False
    # Bumps every time the state changes — clients can compare to detect updates.
    revision: int = 0
    # Asyncio Event so SSE handlers can sleep until the next update.
    _changed: asyncio.Event = field(default_factory=asyncio.Event)

    def snapshot(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "stage": self.stage,
            "progress": self.progress,
            "message": self.message,
            "raw_count": self.raw_count,
            "kept_count": self.kept_count,
            "dropped_count": self.dropped_count,
            "enriched": self.enriched,
            "partial": self.partial,
            "relaxed_filter": self.relaxed_filter,
            "intent": self.intent,
            "kept_preview": list(self.kept_preview),
            "result": self.result,
            "error": self.error,
            "finished": self.finished,
        }


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = asyncio.Lock()

    async def create(self, owner_uid: str | None) -> JobState:
        await self._evict_expired()
        async with self._lock:
            job_id = secrets.token_urlsafe(12)
            state = JobState(job_id=job_id, owner_uid=owner_uid)
            self._jobs[job_id] = state
            return state

    def get(self, job_id: str) -> JobState | None:
        return self._jobs.get(job_id)

    def get_for(self, job_id: str, owner_uid: str | None) -> JobState | None:
        state = self._jobs.get(job_id)
        if not state:
            return None
        # Same-owner check. If the job has no owner (legacy / anon mode),
        # anyone can read it.
        if state.owner_uid and state.owner_uid != owner_uid:
            return None
        return state

    async def update(self, job_id: str, **kw: Any) -> None:
        state = self._jobs.get(job_id)
        if not state:
            return
        for k, v in kw.items():
            if k == "enriched_total":
                state.enriched_total = v
                continue
            if hasattr(state, k):
                setattr(state, k, v)
        state.revision += 1
        state._changed.set()
        # Reset so the next waiter sleeps. This is safe because every snapshot
        # consumer re-reads the full state, not the event.
        state._changed = asyncio.Event()

    async def append_kept(self, job_id: str, lead_preview: dict[str, Any]) -> None:
        state = self._jobs.get(job_id)
        if not state:
            return
        # Cap preview at 50 items so clients holding the SSE socket open for
        # a long scrape don't balloon memory.
        if len(state.kept_preview) >= 50:
            return
        state.kept_preview.append(lead_preview)
        state.revision += 1
        state._changed.set()
        state._changed = asyncio.Event()

    async def finish(
        self,
        job_id: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        state = self._jobs.get(job_id)
        if not state:
            return
        state.finished = True
        state.finished_at = time.time()
        state.stage = "error" if error else "done"
        state.progress = 1.0
        state.result = result
        state.error = error
        state.revision += 1
        state._changed.set()
        state._changed = asyncio.Event()

    async def wait_for_change(self, job_id: str, *, timeout: float = 1.0) -> None:
        state = self._jobs.get(job_id)
        if not state:
            return
        try:
            await asyncio.wait_for(state._changed.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return

    async def _evict_expired(self) -> None:
        now = time.time()
        async with self._lock:
            expired = [
                jid for jid, state in self._jobs.items()
                if state.finished and state.finished_at and (now - state.finished_at) > _JOB_TTL_S
            ]
            for jid in expired:
                self._jobs.pop(jid, None)


_REGISTRY = JobRegistry()


def get_registry() -> JobRegistry:
    return _REGISTRY
