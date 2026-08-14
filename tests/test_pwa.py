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


def test_one_persons_evidence_is_never_cached_for_the_next() -> None:
    """The data cache is keyed by URL and knows nothing about who asked.

    An incident *detail* carries the evidence its viewer was entitled to see — a private
    recording, and a signed URL that still works. Caching one would mean the reporter
    views their own incident, signs out, and the next person on that phone is served it.
    The *list* is identical for everybody, so it is safe and is the thing worth having
    offline anyway.
    """
    handler = SW[SW.index("addEventListener(\"fetch\"") : SW.index("async function networkFirst")]
    assert 'startsWith("/incidents")' not in handler, (
        "this matches /incidents/{id} as well as /incidents, and caches private evidence"
    )
    assert '=== "/incidents"' in handler.replace("'", '"')


def test_the_worker_stays_out_of_the_way_on_a_development_machine() -> None:
    """`cacheFirst` is right for a commuter on a bad connection and wrong for anyone
    editing a file: the edit does not appear until the load after the one where it was
    made, so the server is serving new code while the page runs old code.

    Skipping registration is not enough on its own — a worker already registered keeps
    controlling the page — so it must also unregister and empty the caches.
    """
    app_js = JS["app.js"]
    assert "localhost" in app_js and "127.0.0.1" in app_js
    assert "unregister()" in app_js, "an existing worker would keep serving stale code"
    assert "caches.delete" in app_js, "its caches would outlive it"


def test_the_cache_version_is_bumped_when_the_shell_changes() -> None:
    """The classic service-worker failure: the fix is deployed, the server is serving it,
    and the user is still running the old JavaScript because `cacheFirst` handed them the
    copy it already had. The version constant is the only thing that evicts it."""
    version = re.search(r'const VERSION = "([^"]+)"', SW).group(1)
    assert version != "v1", "the version has never been bumped; deploys will not take effect"


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


# =============================================================================
# THE WORDS AND NUMBERS THE INTERFACE SHOWS
# =============================================================================


def test_the_interface_never_says_confidence_or_reputation() -> None:
    """Two internal names that mislead a road user.

    "Confidence" invites a reader to hear certainty when the number means corroboration,
    and "reputation" sounds like a social score rather than a record of reports that
    turned out to be true. The database and the code keep the original names — renaming
    columns mid-exam is how migrations go wrong — so the translation lives in one place,
    `LABEL`, and every view reads it from there.
    """
    views = {n: s for n, s in JS.items() if n not in {"ui.js", "sw.js"}}
    assert len(views) >= 10, "the module list is empty; this test would pass vacuously"
    for name, source in views.items():
        # Strip comments: the explanation of the rename is allowed to name the old words.
        code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
        # Strip identifiers — `inc.confidence` is the API field, not a visible word.
        code = re.sub(r"[.\w]*\b(confidence|reputation)s?\b", "", code)
        for word in ("Confidence", "Reputation", "Standing", "standing"):
            assert word not in code, f"{name} shows the internal word “{word}”"


def test_the_labels_are_defined_in_exactly_one_place() -> None:
    assert 'confidence: "Accuracy"' in JS["ui.js"].replace("'", '"')
    assert 'reputation: "Credibility"' in JS["ui.js"].replace("'", '"')


def test_percentages_are_rounded_down_not_nearest() -> None:
    """Rounding up overstates how sure the system is, and above 0.70 that number sends a
    warden to a road. When it is wrong it should be wrong in the direction of caution."""
    pct = re.search(r"export const pct = [^;]+;", JS["ui.js"]).group(0)
    assert "Math.floor" in pct
    assert "Math.round" not in pct
    assert "%" in pct, "pct must produce a percentage, not a fraction"


def test_no_view_shows_a_raw_probability() -> None:
    """0.62 means nothing to a commuter. Every score reaching the screen goes through
    `pct`, and a bar's width is floored for the same reason its number is."""
    for name, source in JS.items():
        assert "confidence.toFixed" not in source, f"{name} shows a raw probability"
        assert "reputation.toFixed" not in source, f"{name} shows a raw probability"
        assert "Math.round(inc.confidence*100)" not in source.replace(" ", ""), name


# =============================================================================
# ALERTS AND TAGS
# =============================================================================


def test_alerts_appear_at_the_top_of_the_screen() -> None:
    """The tab bar owns the bottom of the screen. A message that appears under a thumb
    resting on the navigation is a message nobody reads."""
    css = (APP_DIR / "css" / "app.css").read_text(encoding="utf-8")
    toast = re.search(r"\.toast\s*\{([^}]*)\}", css).group(1).replace(" ", "")
    assert "position:fixed" in toast
    assert re.search(r"top:", toast), "the alert must be anchored to the top"
    assert "bottom:" not in toast


@pytest.mark.parametrize("kind", ["info", "success", "warning", "error"])
def test_each_kind_of_alert_is_told_apart_by_colour(kind: str) -> None:
    css = (APP_DIR / "css" / "app.css").read_text(encoding="utf-8")
    rule = re.search(rf"\.toast--{kind}\s*\{{([^}}]*)\}}", css)
    assert rule, f"no styling for a {kind} alert"
    body = rule.group(1).replace(" ", "")
    assert "background:" in body and "color:" in body, (
        f"a {kind} alert must set both a background and a text colour, or it will be "
        "unreadable against one of the two themes"
    )


def test_an_error_alert_is_announced_and_stays_longer() -> None:
    ui = JS["ui.js"]
    assert 'role="alert"' in ui or "role\\=\"alert\"" in ui or "'alert'" in ui or '"alert"' in ui
    assert "assertive" in ui, "an error must interrupt a screen reader, not queue behind it"


def test_status_tags_are_capitalised_once_in_the_stylesheet() -> None:
    """Rather than in each of the four places a status is rendered — which is how three
    of them end up lower case."""
    css = (APP_DIR / "css" / "app.css").read_text(encoding="utf-8")
    tag = re.search(r"\.tag\s*\{([^}]*)\}", css).group(1).replace(" ", "")
    assert "text-transform:uppercase" in tag
    # And nowhere else: a tag that also upper-cases in JavaScript would be doing the same
    # job twice, and the two would drift.
    for name, source in JS.items():
        for line in source.splitlines():
            if 'class="tag' in line:
                assert "toUpperCase" not in line, f"{name} upper-cases a tag in JavaScript"


def test_the_report_tab_is_an_ordinary_tab() -> None:
    """It was a raised green pill, which read as a floating action button sitting on top
    of the navigation rather than as one of the five destinations."""
    css = (APP_DIR / "css" / "app.css").read_text(encoding="utf-8")
    fab = re.search(r"\.tabbar\s+a\.fab\s*\{([^}]*)\}", css).group(1).replace(" ", "")
    assert "justify-content:center" not in fab
    assert 'a.fab[aria-current="page"]' in css.replace(" ", "") or (
        'a[aria-current="page"]' in css.replace(" ", "")
    ), "the report tab needs the same active state as the others"


# =============================================================================
# WHAT A REPORTER ACTUALLY SENT
# =============================================================================


def test_the_incident_detail_can_open_a_single_report() -> None:
    """An incident is a claim; a report is the evidence for it. Somebody deciding whether
    to send a warden should be able to see the words, photograph and recording behind
    each one, not only the score they add up to."""
    detail = JS["map.js"]
    assert "data-report=" in detail and "data-detail=" in detail
    assert 'aria-expanded' in detail
    assert "<audio" in detail, "a recording must be playable in place"
    assert "<img" in detail, "a photograph must be visible, not a link to download"
    assert "e.note" in detail


def test_a_recording_the_reporter_kept_private_is_marked_as_such() -> None:
    assert "not shared" in JS["map.js"].lower()


# =============================================================================
# SHARED COMPONENTS
#
# Three views showed a row of figures and each built its own markup, so "2 awaiting a
# warden" and "42 reports held" were the same kind of fact rendered three ways. The same
# had happened to the account rows. These tests are about the versions not drifting apart
# again — which is the only failure a shared component actually has.
# =============================================================================


CSS = (APP_DIR / "css" / "app.css").read_text(encoding="utf-8")


@pytest.mark.parametrize("view", ["dispatch.js", "admin.js", "profile.js"])
def test_every_row_of_figures_uses_the_same_component(view: str) -> None:
    assert "statTiles(" in JS[view], f"{view} builds its own figures"
    # The hand-rolled version each view used to carry: a bare <strong> with the label
    # forced under it by an inline `display:block`. A single headline figure is still
    # allowed to size itself — what must not come back is a row of them built by hand.
    assert 'class="xs" style="display:block"' not in JS[view], (
        f"{view} still hand-builds a row of figures"
    )


def test_a_figure_is_a_tile_rather_than_loose_text() -> None:
    """A number with a word under it is a claim about the system. Three of them in a row
    with nothing between them read as one run-on sentence."""
    assert re.search(r"\.stat\s*\{[^}]*border", CSS), "a stat has no boundary"
    assert re.search(r"\.stats\s*\{[^}]*grid", CSS)
    # auto-fit, so six tiles wrap on a phone without the view knowing how many there are.
    assert "auto-fit" in re.search(r"\.stats\s*\{([^}]*)\}", CSS).group(1)


def test_figures_line_up_digit_by_digit() -> None:
    """Proportional digits make a column of numbers look ragged and slightly wrong."""
    stat = re.search(r"\.stat strong\s*\{([^}]*)\}", CSS).group(1).replace(" ", "")
    assert "font-variant-numeric:tabular-nums" in stat


def test_a_label_and_its_value_do_not_run_together() -> None:
    """They were two inline spans, which rendered as "Display nameAma Boateng"."""
    assert re.search(r"\.deet dt\s*\{", CSS) and re.search(r"\.deet dd\s*\{", CSS)
    deet = re.search(r"\.deet\s*\{([^}]*)\}", CSS).group(1).replace(" ", "")
    assert "display:grid" in deet
    assert "<dl class=\"deets\"" in JS["profile.js"], "an account row is a label/value pair"


def test_the_value_sits_under_its_label_until_there_is_room_for_one_line() -> None:
    assert re.search(r"@media \(min-width:640px\)\s*\{\s*\.deet\s*\{", CSS), (
        "the one-line arrangement should be the exception, not the phone layout"
    )


@pytest.mark.parametrize("label", ["display name", "password"])
def test_an_icon_only_action_still_says_what_it_does(label: str) -> None:
    """An icon button has no text, so its name has to come from somewhere. Without this a
    screen reader announces "button" and nothing else."""
    profile = JS["profile.js"].lower()
    assert f'aria-label="edit your {label}"' in profile or \
           f'aria-label="change your {label}"' in profile


def test_an_icon_is_hidden_from_screen_readers() -> None:
    """Beside a label it would be read twice; alone, its button carries the name."""
    assert 'aria-hidden="true"' in JS["ui.js"]


def test_your_own_reports_open_rather_than_showing_everything_at_once() -> None:
    profile = JS["profile.js"]
    assert 'class="disc"' in profile
    assert 'aria-expanded="false"' in profile
    assert "aria-controls=" in profile, "the button must name the panel it opens"


def test_the_chevron_turns_instead_of_being_swapped() -> None:
    """So the control keeps its identity through the change."""
    assert re.search(r'\.disc__head\[aria-expanded="true"\] \.chev\s*\{[^}]*rotate', CSS)


# =============================================================================
# THE SIGNED-OUT SHELL
#
# The server-side half of this is test_public_map.py. These are about the interface not
# offering what the API would refuse — and not being the thing that enforces it.
# =============================================================================


def test_there_is_no_navigation_at_all_when_signed_out() -> None:
    """It used to show two tabs — Map, and Sign in. That is a navigation bar whose every
    item is either where you already are or what the appbar button already does."""
    app_js = JS["app.js"]
    assert 'classList.toggle("signedOut"' in app_js
    assert re.search(r"#app\.signedOut \.tabbar\s*\{[^}]*display:none", CSS), (
        "an empty <nav> still holds its height and border — a stripe of nothing"
    )


def test_the_signed_out_map_has_no_list_beneath_it() -> None:
    """The list is a table of things the visitor cannot open."""
    assert "auth.signedIn" in JS["map.js"]
    assert "const open = !auth.signedIn" in JS["map.js"]


def test_the_hero_does_not_capture_taps_meant_for_the_map() -> None:
    """The difference between a banner and a lid.

    Without `pointer-events:none` the headline is an invisible sheet across the top of
    the map: markers under it cannot be tapped and the map cannot be dragged from there,
    which on a phone is most of the screen. The words float; the buttons take their taps
    back explicitly.
    """
    hero = re.search(r"\.hero \{([^}]*)\}", CSS).group(1).replace(" ", "")
    assert "pointer-events:none" in hero
    cta = re.search(r"\.hero__cta > \* \{([^}]*)\}", CSS).group(1).replace(" ", "")
    assert "pointer-events:auto" in cta, "the buttons would be unclickable"


def test_the_hero_reads_over_the_map_in_both_themes() -> None:
    """A map is not a background colour — it is light in daylight tiles and dark at
    night, and the text has to survive both. A gradient scrim, opaque where the words are
    and gone before it reaches the markers."""
    hero = re.search(r"\.hero \{([^}]*)\}", CSS).group(1)
    assert "linear-gradient" in hero
    assert "color:#fff" in hero.replace(" ", "")


def test_the_hero_states_something_the_map_does_not_already_say() -> None:
    """A banner over a live map that repeats the map is decoration. This one carries the
    live count, so the headline's claim is evidenced immediately under it."""
    map_js = JS["map.js"]
    assert 'id="count"' in map_js
    assert 'i.status === "verified"' in map_js, "the hero should show what is confirmed"
    assert "hero__count" in CSS


def test_the_hero_is_given_room_on_a_desktop_rather_than_left_as_the_phone_layout() -> None:
    """Desktop is not the phone stretched wide. The hero stays centred — a headline pinned
    left on a 1920px screen leaves the middle of the map, where the markers are, under
    nothing — but the measure and the fade both need more distance."""
    block = re.search(r"@media \(min-width:900px\) \{\s*\.hero \{(.*?)\n  \}", CSS, re.S)
    assert block, "the hero has no desktop treatment"
    assert ".hero h1" in block.group(0) and ".hero p" in block.group(0)


def test_the_zoom_control_moves_out_from_under_the_scrim() -> None:
    """A white control under a dark gradient is unreadable — and because the hero passes
    taps through, it would be usable and invisible at the same time."""
    assert 'open ? "bottom-right" : "top-right"' in JS["map.js"]


def test_a_desktop_side_panel_does_not_blank_what_it_describes() -> None:
    """A side panel exists so the context stays visible. Dimming the whole window behind
    a 420px card hides the map the card is about."""
    desktop = re.search(r"@media \(min-width:900px\)\{(.*?)\n  \}", CSS, re.S).group(1)
    assert ".scrim{background:" in desktop.replace(" ", ""), "the full-strength dim survives"
    faint = re.search(r"\.scrim\{background:rgba\([\d,.]*?([\d.]+)\)\}", desktop.replace(" ", ""))
    assert faint and float(faint.group(1)) < 0.2, "the desktop dim is still a blackout"


def test_the_appbar_joins_the_hero_rather_than_sitting_on_it() -> None:
    """White with a hairline border it read as a bar pasted over the banner — two
    surfaces meeting at a line where the design has one."""
    assert re.search(r"#app\.signedOut \.appbar\s*\{[^}]*border-bottom:0", CSS)


def test_the_teaser_answers_before_it_asks() -> None:
    """What is blocking the road comes first and costs nothing. Only then does it say
    what an account adds."""
    teaser = JS["map.js"]
    assert "teaserHtml" in teaser
    body = teaser[teaser.index("function teaserHtml") : teaser.index("function detailHtml")]
    assert "TYPE_LABEL" in body, "the visitor must be told what it is"
    assert "last_reported_at" in body, "and how long ago"
    assert "Sign in" in body
    # Named, not vague. "Sign in for more" asks somebody to pay for an unnamed thing.
    assert "Photographs" in body and "reliable" in body


def test_the_teaser_never_renders_gated_fields() -> None:
    """Belt and braces: the API withholds these, so the teaser reading them would render
    "null%" rather than leak anything — but a template that reaches for a field it must
    not have is one schema change away from showing it."""
    teaser = JS["map.js"]
    body = teaser[teaser.index("function teaserHtml") : teaser.index("function detailHtml")]
    for field in ("confidence", "report_count", "evidence", "reputation"):
        assert field not in body, f"the teaser reads {field}"


def test_markers_fall_back_to_status_when_the_score_is_withheld() -> None:
    """Pin size followed confidence, which a signed-out visitor is not given. The three
    statuses are that score banded at 0.35 and 0.70 — the same grammar, three steps."""
    assert re.search(r"open\s*\n?\s*\?\s*\(\{ reported:", JS["map.js"]), (
        "signed out, size must come from status rather than a field that is null"
    )


def test_create_an_account_lands_on_the_register_tab() -> None:
    """Arriving on the sign-in form and then having to find the right tab is a step that
    exists for no reason."""
    assert '"/register"' in JS["app.js"]
    assert 'start: "register"' in JS["app.js"]
    assert 'href="#/register"' in JS["map.js"]


def test_the_register_tab_is_opened_by_the_same_handler_a_tap_would_use() -> None:
    """One code path into register mode, rather than a second that has to be kept in
    step with the first."""
    auth_js = JS["auth.js"]
    assert '[data-mode="register"]\').click()' in auth_js
    click = auth_js.index('[data-mode="register"]\').click()')
    listener = auth_js.index('mount.querySelectorAll("[data-mode]")')
    assert listener < click, "the click fires before the listener exists"


def test_a_title_and_the_line_under_it_are_actually_stacked() -> None:
    """`.t` and `.m` are a pair used all over the app — a name and its detail, a type and
    its timestamp, a corridor and its description.

    They were inline spans, so they ran together on one line wherever the parent did not
    happen to be a flex column, and `.m`'s `margin-top` did nothing at all, because
    margins do not apply vertically to an inline box. It looked correct in the places a
    flex parent forced a column and wrong everywhere else, which is why one bug arrived
    three times as three unrelated complaints.
    """
    for selector in (r"\.t", r"\.m"):
        rule = re.search(rf"^  {selector} \{{([^}}]*)\}}", CSS, re.M)
        assert rule, f"{selector} has no rule"
        assert "display:block" in rule.group(1).replace(" ", ""), (
            f"{selector} is inline, so it will run into the line beside it"
        )


def test_the_pair_is_used_the_same_way_everywhere() -> None:
    """A meta line always follows a title. If one view used them side by side, making
    them block would break that view — so check the assumption rather than assume it."""
    users = [
        (name, line)
        for name, source in JS.items()
        for line in source.splitlines()
        if 'class="t"' in line
    ]
    assert len(users) >= 8, "no uses found; this test would pass vacuously"
    for name, line in users:
        assert 'class="m"' not in line, (
            f"{name} puts a title and its meta line on one line: {line.strip()}"
        )


def test_evidence_is_fetched_only_when_a_report_is_opened() -> None:
    """Twenty-five reports would otherwise be twenty-five requests nobody asked for, on a
    connection this system assumes is bad."""
    profile = JS["profile.js"]
    assert "loadEvidence" in profile
    assert "dataset.loaded" in profile, "opening and closing would ask again each time"
    assert "/attachments" in profile
