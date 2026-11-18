"""The request limiter is what stands between us and a 429 storm.

It gates every Gemini call, so a bug here either throttles the whole
application to a crawl or lets the burst through that it exists to stop.
Both are silent failures, which is why this is tested rather than trusted.
"""

from __future__ import annotations

import threading
import time
import unittest

from app.providers.rate_limit import WINDOW_SECONDS, RequestLimiter


class RequestLimiterTests(unittest.TestCase):
    def test_a_disabled_limiter_never_waits(self) -> None:
        limiter = RequestLimiter(0)
        started = time.monotonic()
        for _ in range(50):
            self.assertEqual(limiter.acquire(), 0.0)
        self.assertLess(time.monotonic() - started, 0.5)

    def test_calls_up_to_the_limit_pass_straight_through(self) -> None:
        limiter = RequestLimiter(5)
        started = time.monotonic()
        for _ in range(5):
            limiter.acquire()
        self.assertLess(
            time.monotonic() - started, 0.5, "the first N calls must not be delayed"
        )

    def test_the_call_over_the_limit_waits_for_the_window(self) -> None:
        """The whole point: the 3rd call of a 2-per-window limiter waits."""
        limiter = RequestLimiter(2, window=0.6)
        limiter.acquire()
        limiter.acquire()

        started = time.monotonic()
        limiter.acquire()
        waited = time.monotonic() - started

        self.assertGreater(waited, 0.3, "it should have waited for a slot")
        self.assertLess(waited, 2.0, "it waited far longer than the window")

    def test_a_drained_window_lets_calls_through_again(self) -> None:
        """Throttling must be temporary, not a one-off allowance."""
        limiter = RequestLimiter(2, window=0.4)
        limiter.acquire()
        limiter.acquire()
        time.sleep(0.5)  # the window has now passed

        started = time.monotonic()
        limiter.acquire()
        self.assertLess(time.monotonic() - started, 0.2)

    def test_the_window_is_a_minute_in_production(self) -> None:
        """Google counts per minute; the default must match that, not a test."""
        self.assertEqual(WINDOW_SECONDS, 60.0)
        self.assertEqual(RequestLimiter(15).window, 60.0)

    def test_it_never_admits_more_than_the_limit_at_once(self) -> None:
        """Ten threads, a limit of 3: only 3 may be admitted per window."""
        limiter = RequestLimiter(3, window=0.5)
        admitted: list[float] = []
        guard = threading.Lock()

        def worker() -> None:
            limiter.acquire()
            with guard:
                admitted.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(10)]
        start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        self.assertEqual(len(admitted), 10, "no thread may be left hanging")
        prompt = [t for t in admitted if t - start < 0.25]
        self.assertLessEqual(
            len(prompt), 3, f"{len(prompt)} admitted at once, limit is 3"
        )

    def test_timeout_sends_the_request_rather_than_blocking_forever(self) -> None:
        """A user staring at a blank screen is worse than a refused request."""
        limiter = RequestLimiter(1, window=30.0)
        limiter.acquire()
        started = time.monotonic()
        limiter.acquire(timeout=0.3)
        self.assertLess(
            time.monotonic() - started, 5.0, "it must give up, not wait 30s"
        )

    def test_penalise_makes_the_next_caller_wait(self) -> None:
        """A 429 says 'retry in 28s'; the next caller must not ignore that."""
        limiter = RequestLimiter(4, window=1.0)
        limiter.penalise(0.6)

        started = time.monotonic()
        limiter.acquire()
        self.assertGreater(
            time.monotonic() - started, 0.3, "the penalty was not applied"
        )

    def test_penalise_is_a_no_op_when_disabled(self) -> None:
        limiter = RequestLimiter(0)
        limiter.penalise(30.0)
        self.assertEqual(limiter.acquire(), 0.0)


class RetryHintTests(unittest.TestCase):
    def test_the_wait_google_asks_for_is_read_from_the_message(self) -> None:
        from app.providers.gemini_rest import retry_after

        body = (
            "You exceeded your current quota. * Quota exceeded for metric: "
            "generate_content_free_tier_requests, limit: 15. "
            "Please retry in 28.785854656s."
        )
        self.assertAlmostEqual(retry_after(body), 28.785854656, places=3)

    def test_a_message_without_a_hint_gives_zero(self) -> None:
        from app.providers.gemini_rest import retry_after

        self.assertEqual(retry_after("This model is experiencing high demand."), 0.0)

    def test_an_absurd_hint_is_capped(self) -> None:
        from app.providers.gemini_rest import retry_after

        self.assertEqual(retry_after("Please retry in 9999s."), 60.0)


if __name__ == "__main__":
    unittest.main()
