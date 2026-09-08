"""Time budgets for optional external calls.

THE PROBLEM THIS SOLVES
-----------------------
Weather, Earth Engine and data.gov.in are all optional context. Every screen
that uses them already degrades cleanly when they are missing — "unavailable"
is a designed state, not an error.

But each of those services has its own internal timeout measured in TENS of
seconds (Earth Engine 60s, mandi 20s x 3 retries, weather 15s), and those are
the right values for a page whose whole purpose is that data. They are badly
wrong for a page that merely decorates itself with it.

Without a budget, an optional garnish holds the entire response hostage. That
is what made the Crop Advisor take two minutes: the ranking itself computed in
half a second, and then the page waited a minute on a satellite reading that,
by design, does not change a single score.

USE
---
    obs = await budgeted(sat.get_ndvi(lat, lon), 3.0, "satellite")

Returns None on timeout or failure. Never raises. The caller treats None the
same way it already treats "service unavailable", so no new branch is needed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Optional, TypeVar

log = logging.getLogger("agri.budget")

T = TypeVar("T")


async def budgeted(coro: Awaitable[T], seconds: float,
                   label: str = "external call",
                   default: Any = None) -> Optional[T]:
    """Await `coro` for at most `seconds`. Return `default` if it overruns.

    The coroutine is cancelled on timeout, so a slow Earth Engine query does
    not keep running in the background holding a worker thread after the
    farmer has already been served.
    """
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError:
        log.info("[BUDGET] %s exceeded %.1fs and was skipped", label, seconds)
        return default
    except Exception as exc:                            # noqa: BLE001
        log.warning("[BUDGET] %s failed: %s: %s", label, type(exc).__name__, exc)
        return default
