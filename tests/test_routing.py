"""Route registration order.

Starlette matches routes in registration order, first match wins. So a literal path
registered *after* a parameterised one that could swallow it is unreachable:

    GET /incidents/{incident_id}      registered first
    GET /incidents/queue              registered second  -->  never reached

The request for `/incidents/queue` matches `{incident_id}`, fails to parse "queue" as a
UUID, and returns 422. Nothing crashes at startup, the endpoint appears correctly in the
generated documentation, and it simply does not work.

The current ordering is safe — `/queue` precedes `/{incident_id}`, and the other literal
paths have two segments so a single-segment parameter cannot match them. This file exists
so that stays true when someone adds `/incidents/summary` in six months.
"""

from __future__ import annotations

import re

import pytest

from app.main import app

# Matches a path segment that is a parameter, e.g. {incident_id}
_PARAM = re.compile(r"\{[^}]+\}")


def _routes():
    """Every registered route, in registration order.

    FastAPI 0.141 does not put included routes directly on `app.routes`. It inserts an
    `_IncludedRouter` wrapper holding the original `APIRouter`, so the obvious traversal
    — `getattr(route, "routes", [route])` — finds only the four built-in documentation
    routes and silently yields nothing else.

    That is exactly how the first version of this file was written, and it made every
    check below pass over an empty collection. `test_the_traversal_finds_the_real_routes`
    exists because of it: a test that passes for the wrong reason is worse than one that
    fails.
    """
    for route in app.routes:
        inner = getattr(route, "original_router", None)
        candidates = inner.routes if inner is not None else [route]
        for r in candidates:
            path = getattr(r, "path", None)
            methods = getattr(r, "methods", None)
            if path and methods:
                yield path, methods


def _segments(path: str) -> list[str]:
    return [s for s in path.split("/") if s]


def test_the_traversal_finds_the_real_routes() -> None:
    """Meta-test. Every check below is vacuously true over an empty list, so this holds
    the line — and it caught the first version of `_routes`, which found five routes out
    of twenty-one."""
    found = {p for p, _ in _routes()}
    assert len(found) >= 15, f"traversal only found {len(found)} routes — it is broken"
    assert "/health" in found
    assert "/incidents/{incident_id}" in found


def test_no_literal_path_is_shadowed_by_an_earlier_parameter() -> None:
    """The check that matters. For every pair of routes sharing a method, a literal
    path must not be registered after a parameterised path that would match it."""
    seen: list[tuple[str, set]] = []
    problems: list[str] = []

    for path, methods in _routes():
        for earlier_path, earlier_methods in seen:
            if not (methods & earlier_methods):
                continue
            if not _PARAM.search(earlier_path):
                continue

            a, b = _segments(earlier_path), _segments(path)
            if len(a) != len(b):
                continue
            # Would the earlier, parameterised path match this literal one?
            if all(_PARAM.fullmatch(x) or x == y for x, y in zip(a, b)):
                if not _PARAM.search(path):
                    problems.append(
                        f"{path} is unreachable: {earlier_path} is registered first "
                        f"and matches it"
                    )
        seen.append((path, methods))

    assert not problems, "shadowed routes:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize(
    "literal,parameterised",
    [
        ("/incidents/queue", "/incidents/{incident_id}"),
        ("/incidents/wardens/available", "/incidents/{incident_id}"),
        ("/incidents/assigned/mine", "/incidents/{incident_id}"),
        ("/reports/mine", "/reports"),
    ],
)
def test_known_literal_routes_are_documented(literal: str, parameterised: str) -> None:
    """These are the specific paths at risk. If one disappears from the schema, it was
    either removed or shadowed — both worth noticing."""
    paths = app.openapi()["paths"]
    assert literal in paths, f"{literal} is missing from the API schema"
    assert parameterised in paths


def test_every_documented_path_is_reachable() -> None:
    """A path in the generated documentation that cannot be routed to is worse than one
    that is absent — it tells a reader the endpoint exists."""
    documented = set(app.openapi()["paths"])
    registered = {path for path, _ in _routes()}
    assert documented <= registered
