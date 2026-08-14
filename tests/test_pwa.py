"""The progressive web application.

A static front end has no compiler. The failures it is prone to are silent — a renamed
route, a manifest pointing at an icon that does not exist, an unescaped user string — and
none of them raise until somebody uses the thing.

So these tests read the files and check them against the API and against each other.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app

APP_DIR = pathlib.Path(__file__).resolve().parent.parent / "web" / "app"
INDEX = (APP_DIR / "index.html").read_text(encoding="utf-8")
MANIFEST = json.loads((APP_DIR / "manifest.webmanifest").read_text(encoding="utf-8"))
SW = (APP_DIR / "sw.js").read_text(encoding="utf-8")
JS = {p.name: p.read_text(encoding="utf-8") for p in APP_DIR.rglob("*.js")}


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# =============================================================================
# IT IS ACTUALLY SERVED
# =============================================================================


def test_the_app_is_reachable(client: TestClient) -> None:
    r = client.get("/app")
    assert r.status_code == 200
    assert "Nkwanta" in r.text


def test_the_original_page_still_works(client: TestClient) -> None:
    """Both interfaces run side by side until the rebuild is proven live. A graded
    deployment should never be one bad commit from having nothing to show."""
    assert client.get("/").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/static/app/index.html",
        "/static/app/css/app.css",
        "/static/app/js/app.js",
        "/static/app/js/api.js",
        "/static/app/manifest.webmanifest",
        "/static/app/icons/icon.svg",
        "/static/app/sw.js",
    ],
)
def test_every_asset_the_shell_needs_is_served(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 200, f"{path} is missing"


def test_the_service_worker_is_also_served_from_the_root(client: TestClient) -> None:
    """A service worker can only control paths at or below its own URL. Serving it at
    the root as well means its scope can be widened later without moving files."""
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert r.headers.get("Service-Worker-Allowed") == "/"


# =============================================================================
# THE MANIFEST PROMISES ONLY WHAT EXISTS
# =============================================================================


def test_every_icon_in_the_manifest_exists(client: TestClient) -> None:
    """A manifest pointing at a missing icon makes an app silently un-installable."""
    for entry in MANIFEST["icons"]:
        assert client.get(entry["src"]).status_code == 200, f"{entry['src']} is missing"


def test_the_manifest_has_a_maskable_icon() -> None:
    """Without one, Android crops the icon into a circle and clips the artwork."""
    purposes = " ".join(i.get("purpose", "") for i in MANIFEST["icons"])
    assert "maskable" in purposes


def test_the_manifest_is_installable() -> None:
    for key in ("name", "short_name", "start_url", "display", "icons"):
        assert MANIFEST.get(key), f"{key} is required for installability"
    assert MANIFEST["display"] in {"standalone", "fullscreen", "minimal-ui"}


def test_manifest_shortcuts_point_at_real_routes() -> None:
    defined = set(re.findall(r'router\.define\("([^"]+)"', JS["app.js"]))
    for shortcut in MANIFEST.get("shortcuts", []):
        route = shortcut["url"].split("#")[-1]
        assert route in defined, f"shortcut targets undefined route {route}"


# =============================================================================
# THE SERVICE WORKER IS CONSERVATIVE
# =============================================================================


def test_only_get_requests_are_ever_cached() -> None:
    """A cached POST would mean a report appearing to succeed twice, or an assignment
    replaying silently. Anything that changes state must reach the server or fail."""
    assert 'request.method !== "GET"' in SW


def test_attachments_and_auth_are_never_cached() -> None:
    """A voice recording identifies its speaker, and a cached token outlives a sign-out.
    Neither belongs in a cache shared by everyone using the device."""
    assert "/attachments/" in SW
    assert "/auth/" in SW


def test_a_stale_response_is_labelled_as_stale() -> None:
    """The interface says "showing what was last loaded" rather than pretending the data
    is current. That requires the worker to mark it."""
    assert "X-Nkwanta-Cached" in SW


def test_every_shell_file_listed_actually_exists() -> None:
    listed = re.findall(r'"(/static/app/[^"]+)"', SW)
    for path in listed:
        if path.endswith("/"):
            continue
        assert (APP_DIR.parent / path.replace("/static/", "")).exists(), f"{path} does not exist"


def test_the_worker_survives_a_missing_file_on_install() -> None:
    """`cache.addAll` fails the whole install if any single file 404s, leaving the app
    with no shell at all. Adding individually tolerates a miss.

    Checks for the *call* rather than the word, which also appears in the comment
    explaining why it is avoided — the same trap that caught the localStorage test.
    """
    assert "allSettled" in SW
    assert "cache.addAll(" not in SW
    assert ".addAll(" not in SW


# =============================================================================
# THE OFFLINE QUEUE
# =============================================================================


def test_reports_are_queued_rather_than_lost_when_offline() -> None:
    api = JS["api.js"]
    assert "indexedDB" in api
    assert "flushOutbox" in api
    assert "navigator.onLine" in api


def test_a_queued_report_carries_the_key_generated_at_capture() -> None:
    """This is what makes retrying safe. The key is generated when the report is made,
    not when it is sent, so the same physical report keeps one identity however many
    times it is attempted — see app/services/reports.py."""
    api = JS["api.js"]
    assert "idempotency_key" in api
    assert "crypto.randomUUID()" in api


def test_a_rejected_report_leaves_the_queue() -> None:
    """A report the server will never accept — bad coordinates, too old — would
    otherwise be retried forever and block everything behind it."""
    assert "nk:queuerejected" in JS["api.js"]


def test_the_queue_drains_on_reconnection_and_at_startup() -> None:
    assert 'addEventListener("online"' in JS["api.js"]
    assert "flushOutbox()" in JS["app.js"]


# =============================================================================
# WHAT THE INTERFACE MUST NOT DO
# =============================================================================


def test_user_supplied_text_is_escaped() -> None:
    """Display names and notes come from users and are written into the DOM. Without
    escaping, a display name containing a script tag runs in the control room."""
    assert "const esc =" in JS["ui.js"]
    for view in ("map.js", "alerts.js", "admin.js", "dispatch.js", "profile.js"):
        assert "esc(" in JS[view], f"{view} renders without escaping"


def test_no_secret_or_token_is_embedded() -> None:
    for name, src in JS.items():
        assert not re.search(r"eyJ[A-Za-z0-9_-]{20,}", src), f"a JWT appears in {name}"
        assert "JWT_SECRET" not in src, f"a secret name appears in {name}"


def test_the_token_is_not_kept_in_local_storage() -> None:
    """Checks for use rather than the bare word, which also appears in the comment
    explaining the choice."""
    for name, src in JS.items():
        assert "localStorage." not in src, f"{name} uses localStorage"
    assert "sessionStorage." in JS["api.js"]


def test_the_registration_form_has_no_role_field() -> None:
    """Mirrors the API, where the field does not exist. An interface offering a choice
    the server refuses is a worse lie than not offering it."""
    auth_view = JS["auth.js"]
    assert 'name="role"' not in auth_view


def test_only_the_admin_view_creates_privileged_accounts() -> None:
    assert "/auth/users" in JS["admin.js"]
    assert "/auth/users" not in JS["auth.js"]


# =============================================================================
# ROUTES AND ROLES
# =============================================================================


def _called_paths() -> set[str]:
    """Every path the application passes to `api(...)`, normalised.

    Order matters here and the first version got it wrong. Template expressions must be
    replaced *before* stripping a query string, because optional chaining inside a
    template — `${inc.evidence[0]?.report_id}` — contains a question mark. Splitting on
    `?` first truncated the path mid-expression and reported a false failure.
    """
    out: set[str] = set()
    for src in JS.values():
        for raw in re.findall(r"""api\(\s*[`"']([^`"']+)""", src):
            path = re.sub(r"\$\{[^}]*\}", "{x}", raw)   # template holes first
            path = path.split("?")[0].rstrip("/")       # then the query string
            if path.startswith("/"):
                out.add(path)
    return out


def test_every_endpoint_the_app_calls_exists(client: TestClient) -> None:
    """The failure a static front end is most prone to: a route is renamed, a button
    breaks, and nothing complains until somebody presses it."""
    known = {re.sub(r"\{[^}]+\}", "{x}", p).rstrip("/") for p in app.openapi()["paths"]}
    known |= {"/auth/login", "/auth/register"}          # built by concatenation

    unknown = sorted(
        p for p in _called_paths()
        if p not in known and not p.startswith("/auth/")
    )
    assert not unknown, f"the app calls endpoints that do not exist: {unknown}"


def test_the_extraction_finds_a_meaningful_number_of_calls() -> None:
    """Meta-test. The check above passes trivially over an empty set — which has already
    happened twice in this project, in the clustering generator and the route traversal."""
    calls = _called_paths()
    assert len(calls) >= 15, f"only found {len(calls)} API calls; extraction is broken"


def test_privileged_routes_declare_their_roles() -> None:
    app_js = JS["app.js"]
    assert 'router.define("/admin"' in app_js
    admin_line = next(l for l in app_js.splitlines() if '"/admin"' in l)
    assert 'roles: ["admin"]' in admin_line

    dispatch_line = next(l for l in app_js.splitlines() if '"/dispatch"' in l)
    assert "commuter" not in dispatch_line


def test_the_map_is_open_to_everyone() -> None:
    """A commuter checking the road ahead should not have to create an account first."""
    line = next(l for l in JS["app.js"].splitlines() if 'router.define("/",' in l)
    assert "roles" not in line


# =============================================================================
# ACCESSIBILITY AND DEGRADATION
# =============================================================================


def test_the_map_failing_does_not_take_the_view_down() -> None:
    """MapLibre loads from a CDN and tiles come from OpenStreetMap. Either can fail on
    exactly the connection this system's users have."""
    assert "typeof maplibregl === \"undefined\"" in JS["map.js"]
    assert "degrade(" in JS["map.js"]


def test_focus_is_always_visible_somehow() -> None:
    """Removing an outline without replacing it makes an interface unusable by keyboard.

    Removing one *and* providing another indicator is fine, and is what the text inputs
    do — they trade the outline for a coloured ring, which reads better against a
    rounded field. So the rule is not "never write outline:none", it is "never leave a
    focused element with no indication at all".
    """
    css = (APP_DIR / "css" / "app.css").read_text(encoding="utf-8")

    assert ":focus-visible" in css, "no global focus-visible treatment"

    for rule in re.findall(r"([^{}]*:focus[^{}]*)\{([^}]*)\}", css):
        selector, body = rule
        if "outline:none" not in body.replace(" ", ""):
            continue
        # An outline was removed — something else must mark the element.
        replaced = any(k in body for k in ("box-shadow", "border-color", "background"))
        is_the_mouse_only_reset = ":not(:focus-visible)" in selector
        assert replaced or is_the_mouse_only_reset, (
            f"`{selector.strip()}` removes the outline without replacing it"
        )


def test_motion_respects_the_reduced_motion_preference() -> None:
    css = (APP_DIR / "css" / "app.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css


def test_dark_mode_exists() -> None:
    """Not a preference here — this is read at night, in a car, at arm's length."""
    css = (APP_DIR / "css" / "app.css").read_text(encoding="utf-8")
    assert "prefers-color-scheme: dark" in css


def test_sheets_can_be_closed_by_keyboard() -> None:
    """A modal that traps focus and cannot be dismissed by keyboard is a trap."""
    ui = JS["ui.js"]
    assert '"Escape"' in ui
    assert '"Tab"' in ui


def test_touch_targets_are_large_enough() -> None:
    css = (APP_DIR / "css" / "app.css").read_text(encoding="utf-8")
    assert "min-height:44px" in css


def test_the_shell_has_a_definite_height() -> None:
    """A regression test for two bugs that were one bug.

    With `min-height:100dvh` the page grew past the viewport, so the tab bar scrolled
    away with the content instead of staying under the thumb — and a child with `flex:1`
    inside a parent with no definite height resolves to nothing, which is why the map was
    invisible on a phone while working on a desktop, where the viewport simply happened
    to be taller than the content.
    """
    css = (APP_DIR / "css" / "app.css").read_text(encoding="utf-8")
    app_rule = re.search(r"#app\s*\{([^}]*)\}", css).group(1).replace(" ", "")
    assert "min-height:100dvh" not in app_rule, "the shell must have a definite height"
    assert "height:100dvh" in app_rule


def test_the_navigation_cannot_scroll_away() -> None:
    """It is the primary navigation on a phone. It must stay under the thumb."""
    css = (APP_DIR / "css" / "app.css").read_text(encoding="utf-8")
    tabbar = re.search(r"\.tabbar\s*\{([^}]*)\}", css).group(1).replace(" ", "")
    assert "flex:none" in tabbar
    app_rule = re.search(r"#app\s*\{([^}]*)\}", css).group(1).replace(" ", "")
    assert "overflow:hidden" in app_rule, "the shell must not scroll; only .scroll does"


def test_the_map_has_a_minimum_height() -> None:
    """`flex:1` alone let the map collapse to nothing whenever the list beneath wanted
    the room — which on a short phone screen is always."""
    css = (APP_DIR / "css" / "app.css").read_text(encoding="utf-8")
    map_rule = re.search(r"#map\s*\{([^}]*)\}", css).group(1).replace(" ", "")
    assert re.search(r"min-height:\d+px", map_rule), "the map can collapse to zero height"


def test_the_voice_recorder_stops_itself_at_the_limit() -> None:
    """The point of the meter: stop at the cap rather than let someone speak for two
    minutes and then reject the upload."""
    report = JS["report.js"]
    assert "MAX_VOICE" in report
    assert "recorder.stop()" in report
    assert "WARN_AT" in report
