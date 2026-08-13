"""B22 — the web page.

A static page has no compiler and no type checker. The failure it is prone to is silent:
a route gets renamed, the page keeps calling the old path, and nothing complains until a
human clicks the button.

So these tests read `web/index.html` and check it against the actual API schema. Crude,
and it catches exactly the mistake that would otherwise reach a demonstration.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from app.main import app

PAGE = pathlib.Path(__file__).resolve().parent.parent / "web" / "index.html"
HTML = PAGE.read_text(encoding="utf-8")

# Paths the page builds by concatenation rather than as one literal, so a regex over the
# source cannot see them whole.
CONCATENATED = {"/auth/login", "/auth/register"}


def _api_paths() -> set[str]:
    """Documented paths, with parameter names normalised so they can be compared."""
    return {
        re.sub(r"\{[^}]+\}", "{x}", p).rstrip("/")
        for p in app.openapi()["paths"]
    }


def _called_paths() -> set[str]:
    """Every path the page passes to `api(...)`, with template holes normalised."""
    literal = set(re.findall(r"""api\(\s*["'`]([^"'`?]+)""", HTML))
    templated = set(re.findall(r"api\(\s*`([^`?]+)`", HTML))
    out = set()
    for raw in literal | templated:
        path = re.sub(r"\$\{[^}]+\}", "{x}", raw).rstrip("/")
        if path and path.startswith("/"):
            out.add(path)
    return out


# --- the check that matters ---------------------------------------------------


def test_every_endpoint_the_page_calls_exists() -> None:
    """Renaming a route without updating the page is the failure this prevents. It
    produces no error anywhere until somebody clicks the button."""
    known = _api_paths()
    unknown = sorted(
        p for p in _called_paths()
        if p not in known and not any(p.startswith(c.rsplit("/", 1)[0]) for c in CONCATENATED)
    )
    assert not unknown, f"the page calls endpoints that do not exist: {unknown}"


@pytest.mark.parametrize("path", sorted(CONCATENATED))
def test_the_concatenated_auth_paths_exist(path: str) -> None:
    assert path in _api_paths()


def test_the_page_calls_a_meaningful_number_of_endpoints() -> None:
    """Meta-test, for the same reason the clustering generator and the route traversal
    have one: if the extraction silently stops working, every check above passes over an
    empty set. This has now caught two such bugs in this project."""
    assert len(_called_paths()) >= 10


# --- it must not break if the network does -----------------------------------


def test_the_map_library_failing_does_not_take_the_page_with_it() -> None:
    """The map loads from a CDN and draws tiles from OpenStreetMap. Either can fail on a
    poor connection — which is precisely the connection this system's users have. The
    incident list carries the same information, so the page has to survive without it."""
    assert "try {" in HTML and "catch" in HTML
    assert "Map could not load" in HTML


def test_incidents_load_without_signing_in() -> None:
    """A commuter checking the road ahead must not have to create an account first.
    `loadIncidents` is called at startup, outside any auth branch."""
    tail = HTML.split("// Start")[-1]
    assert "loadIncidents()" in tail


# --- privacy and safety surfaced in the interface ----------------------------


def test_voice_sharing_is_off_by_default_in_the_markup() -> None:
    """Consent is given, never assumed — including by a pre-ticked box."""
    checkbox = re.search(r'<input[^>]*id="sharevoice"[^>]*>', HTML)
    assert checkbox is not None
    assert "checked" not in checkbox.group(0)


def test_the_page_explains_what_sharing_a_recording_means() -> None:
    assert "identifies your voice" in HTML


def test_the_driving_warning_is_present() -> None:
    """NFR-3. The system must not create the hazard it exists to reduce, and saying so
    in the interface is part of that."""
    assert "Never type while driving" in HTML


def test_the_evidence_panel_explains_the_score() -> None:
    """A number an officer cannot interrogate is one they learn to ignore."""
    assert "half-life" in HTML
    assert "reputation" in HTML.lower()


# --- no secrets, no surprises -------------------------------------------------


def test_no_token_or_secret_is_hardcoded() -> None:
    assert not re.search(r"eyJ[A-Za-z0-9_-]{20,}", HTML), "a JWT appears to be embedded"
    assert "JWT_SECRET" not in HTML


def test_the_token_is_not_kept_in_local_storage() -> None:
    """`sessionStorage` dies with the tab; `localStorage` persists and is readable by any
    injected script. Neither is ideal — a httpOnly cookie is the right answer — but the
    weaker option should not be the one chosen by accident.

    Checks for *use* (`localStorage.`) rather than the bare word, which also appears in
    the comment explaining why it was avoided. The first version of this test failed on
    its own documentation, which is a small lesson about matching prose instead of code.
    """
    assert "localStorage." not in HTML, "the page reads or writes localStorage"
    assert "sessionStorage." in HTML


def test_user_supplied_text_is_escaped_before_rendering() -> None:
    """Display names, notes and messages all come from users and are written into the
    DOM with innerHTML. Without escaping, a display name containing a script tag would
    execute."""
    assert "const esc =" in HTML
    for field in ("n.message", "e.reporter_name", "c.name"):
        assert f"esc({field})" in HTML, f"{field} is rendered without escaping"
