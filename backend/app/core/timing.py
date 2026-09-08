"""Per-stage timing for the chat pipeline.

Built because "the chat is slow" is unactionable. Three or four minutes could
be the LLM, a retry storm, a stalled weather call, or an N+1 query — and each
has a completely different fix. Guessing wastes a change on the wrong one.

Usage:

    t = StageTimer("CHAT")
    with t.stage("intent detection"):
        ...
    t.count_retry("groq")
    t.finish()          # logs every stage plus the total

Deliberately cheap: a perf_counter read per stage and a dict. It stays on in
production, because the interesting slow request is the rare one you cannot
reproduce on demand.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, List

log = logging.getLogger("agri.timing")


class StageTimer:
    def __init__(self, label: str = "CHAT"):
        self.label = label
        self.started = time.perf_counter()
        self.stages: List[Dict[str, Any]] = []
        self.retries: Dict[str, int] = {}
        self.timeouts: Dict[str, int] = {}
        self.notes: List[str] = []
        log.info("[%s] request received", label)

    @contextmanager
    def stage(self, name: str):
        """Time one stage. Records the elapsed time even when it raises.

        Failures matter most here: a stage that threw after 30 seconds is
        exactly the thing being hunted, and a plain try/finally would lose it.
        """
        t0 = time.perf_counter()
        error = None
        try:
            yield self
        except Exception as exc:                        # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            elapsed = time.perf_counter() - t0
            self.stages.append({"stage": name, "seconds": round(elapsed, 3),
                                "error": error})
            log.info("[%s] %s: %.2fs%s", self.label, name, elapsed,
                     f"  ERROR {error}" if error else "")

    def mark(self, name: str, seconds: float) -> None:
        """Record a stage timed elsewhere (e.g. inside a provider)."""
        self.stages.append({"stage": name, "seconds": round(seconds, 3),
                            "error": None})
        log.info("[%s] %s: %.2fs", self.label, name, seconds)

    def count_retry(self, service: str) -> None:
        self.retries[service] = self.retries.get(service, 0) + 1

    def count_timeout(self, service: str) -> None:
        self.timeouts[service] = self.timeouts.get(service, 0) + 1

    def note(self, text: str) -> None:
        self.notes.append(text)

    @property
    def total(self) -> float:
        return time.perf_counter() - self.started

    def finish(self) -> Dict[str, Any]:
        total = self.total
        # Sorted slowest-first: the top line is the thing to fix.
        ranked = sorted(self.stages, key=lambda s: -s["seconds"])
        log.info("[%s] total: %.2fs", self.label, total)
        if ranked:
            top = ranked[0]
            log.info("[%s] slowest stage: %s (%.2fs, %.0f%% of total)",
                     self.label, top["stage"], top["seconds"],
                     100 * top["seconds"] / total if total else 0)
        if self.retries:
            log.warning("[%s] retries: %s", self.label, self.retries)
        if self.timeouts:
            log.warning("[%s] timeouts: %s", self.label, self.timeouts)

        return {
            "total_seconds": round(total, 3),
            "stages": self.stages,
            "slowest": ranked[0] if ranked else None,
            "retries": self.retries,
            "timeouts": self.timeouts,
            "notes": self.notes,
        }
