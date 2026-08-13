"""A circuit breaker: stop calling something that is clearly broken.

THE PROBLEM
-----------
Your application sends notifications through an SMS provider. The provider goes down.

Every send now waits thirty seconds for a timeout before failing. With fifty
notifications queued that is twenty-five minutes of your system doing nothing but
waiting — holding connections, occupying workers, and starving everything else.

**Someone else's outage has become your outage.** That is the failure this prevents.


THE FIX
-------
Watch the failures. After enough in a row, stop even trying: fail instantly, with no
thirty-second wait. After a cooling-off period, let exactly one call through as a test.
If it works, resume. If not, wait again.

Three states, and the names come straight from the electrical device the pattern is named
after — a fuse that trips to protect the house and can be reset::

    CLOSED     normal. Current flows. Calls go through.
        │  (too many failures in a row)
        ▼
    OPEN       tripped. Calls fail instantly without trying.
        │  (cooling-off period elapses)
        ▼
    HALF_OPEN  testing. ONE call is allowed through.
        │                     │
        │ (it worked)         │ (it failed)
        ▼                     ▼
     CLOSED                  OPEN


This module is **pure**. It holds no connections, performs no I/O, and takes the current
time as an argument rather than reading a clock — so its whole behaviour, including
timeouts, can be tested deterministically without a single `sleep`.
"""

from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass, field


class BreakerState(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpen(Exception):
    """Raised instead of attempting a call the breaker has stopped allowing."""


@dataclass
class CircuitBreaker:
    """Failure counting and state, with the clock passed in.

    `failure_threshold` — consecutive failures before tripping. Consecutive matters: a
    single failure among many successes is a blip, not an outage.

    `reset_after` — how long to wait before testing again. Too short and a struggling
    provider is hammered while it tries to recover; too long and a brief outage costs
    minutes of unnecessary downtime.
    """

    name: str = "gateway"
    failure_threshold: int = 5
    reset_after: dt.timedelta = dt.timedelta(seconds=30)

    _state: BreakerState = field(default=BreakerState.CLOSED, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _opened_at: dt.datetime | None = field(default=None, init=False)

    # Counters, for the operations endpoint and for demonstrating the thing working.
    total_successes: int = field(default=0, init=False)
    total_failures: int = field(default=0, init=False)
    total_rejected: int = field(default=0, init=False)
    times_opened: int = field(default=0, init=False)

    # --- state ----------------------------------------------------------------

    def state(self, now: dt.datetime) -> BreakerState:
        """Current state, accounting for a cooling-off period that may have elapsed.

        The transition from OPEN to HALF_OPEN is driven by time rather than by an event,
        so it has to be evaluated on read. Nothing fires it.
        """
        if self._state is BreakerState.OPEN and self._opened_at is not None:
            if now - self._opened_at >= self.reset_after:
                return BreakerState.HALF_OPEN
        return self._state

    def allows(self, now: dt.datetime) -> bool:
        return self.state(now) is not BreakerState.OPEN

    def before_call(self, now: dt.datetime) -> None:
        """Raise rather than proceed, if the breaker has tripped.

        This is the entire point: **failing here takes microseconds**, where attempting
        the call would take a thirty-second timeout.
        """
        current = self.state(now)
        if current is BreakerState.OPEN:
            self.total_rejected += 1
            raise CircuitOpen(
                f"{self.name} is unavailable — the circuit opened after "
                f"{self.failure_threshold} consecutive failures. "
                f"Retrying at {(self._opened_at or now) + self.reset_after:%H:%M:%S}."
            )
        if current is BreakerState.HALF_OPEN:
            # Promote so a second concurrent caller is not also let through. Only one
            # test call is permitted per cooling-off period.
            self._state = BreakerState.HALF_OPEN

    # --- outcomes -------------------------------------------------------------

    def record_success(self, now: dt.datetime) -> None:
        """A call worked. Reset completely.

        Resetting the counter rather than decrementing it is deliberate: the threshold
        counts *consecutive* failures, so any success means the run has ended.
        """
        self.total_successes += 1
        self._consecutive_failures = 0
        self._state = BreakerState.CLOSED
        self._opened_at = None

    def record_failure(self, now: dt.datetime) -> None:
        """A call failed. Trip if this was the last straw.

        From HALF_OPEN a single failure re-opens immediately — the test call was the
        whole point, and it told us the provider is still down. Waiting for another four
        failures would mean four more thirty-second timeouts to learn what we already
        know.
        """
        self.total_failures += 1

        if self.state(now) is BreakerState.HALF_OPEN:
            self._trip(now)
            return

        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._trip(now)

    def _trip(self, now: dt.datetime) -> None:
        if self._state is not BreakerState.OPEN:
            self.times_opened += 1
        self._state = BreakerState.OPEN
        self._opened_at = now
        self._consecutive_failures = self.failure_threshold

    # --- observability --------------------------------------------------------

    def snapshot(self, now: dt.datetime) -> dict:
        state = self.state(now)
        retry_at = (
            (self._opened_at + self.reset_after).isoformat()
            if self._opened_at and state is BreakerState.OPEN
            else None
        )
        return {
            "name": self.name,
            "state": state.value,
            "consecutive_failures": self._consecutive_failures,
            "failure_threshold": self.failure_threshold,
            "reset_after_seconds": self.reset_after.total_seconds(),
            "retry_at": retry_at,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "total_rejected_without_trying": self.total_rejected,
            "times_opened": self.times_opened,
        }

    def reset(self) -> None:
        """Force back to closed. For operations and for tests, never automatic."""
        self._state = BreakerState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = None
