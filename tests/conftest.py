"""Shared test configuration.

Hypothesis profiles let the same property tests run at different intensities without
editing them. Iterating on a failure wants fast feedback; producing evidence for the
testing report wants thoroughness. Hard-coding a single example count forces a choice
between the two, and whichever you pick is wrong half the time.

    pytest                                   # 150 examples per property (default)
    HYPOTHESIS_PROFILE=dev pytest            # 50  — quick, for iterating
    HYPOTHESIS_PROFILE=thorough pytest       # 1000 — for the testing report

Every profile disables the per-example deadline. Clustering is O(n squared) in the size
of a generated set, so a large set can legitimately exceed Hypothesis's default 200 ms
without anything being wrong. A deadline here would flag slow *data*, not slow code.
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

_COMMON = dict(
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

settings.register_profile("dev", max_examples=50, **_COMMON)
settings.register_profile("default", max_examples=150, **_COMMON)
settings.register_profile("thorough", max_examples=1000, **_COMMON)

settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "default"))
