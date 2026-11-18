"""A process-wide cap on requests per minute to the Gemini API.

### Why this exists

The free tier allows **15 generate_content requests per minute**. One three
page booklet needs about sixteen: three pages read twice each for the
transcription-confidence signal, plus five attempted questions marked twice
each for the agreement signal. So the pipeline exceeds the quota on its own,
and the first thing that happens when it does is a 429 storm:

    Quota exceeded for metric: generate_content_free_tier_requests, limit: 15
    Please retry in 28.7s

Retrying into a limit that has not reset makes it worse, and the result was a
marking run that took 16s one time and 97s the next for identical input. The
variance was not the model and not the code; it was the quota.

A limiter in front of the transport turns that into something predictable: a
request waits for a slot instead of being refused and retried. It cannot make
the ceiling higher - only a paid tier does that - but it makes the time taken
a function of how many requests the work needs, which is a number we control
and can report honestly.

### Why a sliding window rather than a token bucket

Google counts requests in a rolling minute. A token bucket that refills
smoothly would allow a burst that the server then rejects, so this keeps the
actual timestamps and waits until the oldest one is a minute old. That is the
same rule the server applies, which is the only rule worth enforcing.

Set the limit to 0 to disable it (a paid key with a high ceiling, or tests).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60.0


class RequestLimiter:
    """Allows at most `per_minute` acquisitions in any rolling 60 seconds."""

    def __init__(self, per_minute: int, window: float = WINDOW_SECONDS) -> None:
        self._limit = max(0, int(per_minute))
        # The counting window is a parameter so the behaviour can be tested
        # at a one-second window instead of a sixty-second one. Google counts
        # per minute; nothing but a test should change this.
        self._window = float(window)
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def window(self) -> float:
        return self._window

    def acquire(self, *, timeout: float | None = None) -> float:
        """Block until a slot is free. Returns how long it waited.

        Waits in short steps while holding no lock longer than it must, so
        several threads queue in order rather than all waking at once.
        """
        if self._limit <= 0:
            return 0.0

        # Default: a little longer than the window, since the longest a slot
        # can legitimately take to free up is one window.
        if timeout is None:
            timeout = self._window * 2

        started = time.monotonic()
        while True:
            with self._lock:
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= self._window:
                    self._calls.popleft()

                if len(self._calls) < self._limit:
                    self._calls.append(now)
                    waited = now - started
                    if waited > 0.5:
                        logger.info(
                            "Waited %.1fs for a Gemini request slot (%s/min)",
                            waited,
                            self._limit,
                        )
                    return waited

                # The oldest call leaves the window at this time.
                sleep_for = self._window - (now - self._calls[0])

            if time.monotonic() - started + sleep_for > timeout:
                # Better to try and be refused than to block a request for
                # minutes with nothing on screen explaining why.
                logger.warning(
                    "Gave up waiting for a request slot after %.0fs; sending anyway",
                    time.monotonic() - started,
                )
                return time.monotonic() - started

            time.sleep(min(max(sleep_for, 0.05), 1.0))

    def penalise(self, seconds: float) -> None:
        """Record that the server asked us to wait, so queued callers do.

        When a 429 arrives despite the limiter - another process sharing the
        key, or a limit lower than configured - the window is filled so the
        next callers wait rather than piling on.
        """
        if self._limit <= 0 or seconds <= 0:
            return
        with self._lock:
            now = time.monotonic()
            # Pretend the window is full and will not drain for `seconds`.
            start = now - self._window + min(seconds, self._window)
            self._calls = deque([start] * self._limit)


_limiter: RequestLimiter | None = None
_limiter_lock = threading.Lock()


def get_limiter() -> RequestLimiter:
    """The one limiter every Gemini provider shares.

    Shared deliberately: transcription and marking draw on the same per-key
    quota, so two separate limiters would each think they had the whole
    allowance and together use twice it.
    """
    global _limiter
    with _limiter_lock:
        if _limiter is None:
            from app.core.config import settings

            _limiter = RequestLimiter(settings.gemini_requests_per_minute)
        return _limiter


def reset_limiter() -> None:
    """Drop the shared limiter so a settings change takes effect. For tests."""
    global _limiter
    with _limiter_lock:
        _limiter = None
