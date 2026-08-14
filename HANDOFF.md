# HANDOFF

**Running log for the Nkwanta project.** Newest section at the top. Append a new dated
section at the end of every working session. Never rewrite an older one — if something turns
out to have been wrong, say so in a new entry.

Each entry answers four questions: what happened, where things stand, what is unresolved,
what comes next.

---

## 13 August 2026 — Session 17: the interface rebuilt as a PWA

### What happened

**The interface was rebuilt**, after review found it had been left at Tier 0 while the API
grew to Tier 2. Recorded as **D-036**, and recorded as my error rather than as a plan: when
the deadline extended and scope was revisited, the front-end budget was not revisited with
it. The general lesson is written into the entry — *when a constraint that produced a
decision changes, every decision derived from it needs revisiting, not only the ones
currently being worked on.*

**Both interfaces now run side by side.** `/` is the original page, `/app` is the new one.
A graded deployment should never be one bad commit from having nothing to show; the old
page retires once the new one has been exercised live.

### What was built

Three API endpoints the design needed and that did not exist — `PATCH /auth/me`,
`POST /auth/me/password`, `PATCH /auth/users/{id}`. The last one is only a route: `is_active`
has been on the model and checked on every request since B03, with no way to set it.

A progressive web application in `web/app/` — **no framework and no build step** (**D-037**).
Native ES modules, plain CSS with custom properties. A bundler would put Node in the
deployment pipeline, and deployment is pass-or-fail for three marks; it buys nothing the
design needs, because "modern" here is a spacing scale, a type scale, semantic tokens and
real states, none of which are framework features.

Twelve modules: `api` (with the offline queue), `store`, `router`, `ui`, and eight views —
map, report, alerts, routes, profile, auth, dispatch, admin. Plus a service worker, a
manifest, and generated icons including a maskable one.

### Decisions worth defending

**Offline report queuing.** A report filed with no signal goes to IndexedDB and sends
itself when the connection returns. This is only safe because of a decision made at B04,
long before there was a client: every report carries an idempotency key generated **at
capture**, so the same physical report keeps one identity however many times it is
retried. NFR-2 asks for this; the design paid for it months earlier.

**The service worker is deliberately conservative.** GET only — a cached POST would mean a
report appearing to succeed twice. Attachments and `/auth/` are never cached, because a
recording identifies its speaker and a cached token outlives a sign-out. Stale responses
are labelled so the interface can say "showing what was last loaded" rather than pretend.
It does not use Background Sync: that API is absent on iOS, and a queue that works on some
phones is worse than one that works predictably on all of them.

**Avatars are initials** (**D-038**). A face beside a name in an officer's evidence list
makes a reporter easier to identify, which is what NFR-4a exists to prevent.

**Dark mode is a use case, not a preference** — this is read at night, in a car, at arm's
length.

### Three test failures worth recording

All three were the test being wrong rather than the code, and two were the same mistake.

**Optional chaining broke the endpoint extractor.** `${inc.evidence[0]?.report_id}`
contains a question mark, and the regex stripped query strings *before* template
expressions — truncating the path mid-expression. Order now reversed, with the reason in
the docstring.

**`addAll` and `localStorage` both matched their own explanatory comments.** A test that
greps source text is testing the prose as well as the behaviour. Both now check for the
call — `cache.addAll(`, `localStorage.` — rather than the word.

**The focus test was too blunt.** It forbade `outline:none` outright, but the text inputs
trade the outline for a coloured ring, which is both accessible and better looking. The
rule is not "never remove an outline", it is "never leave a focused element unmarked", and
the test now parses each `:focus` rule and checks for a replacement.

### Verified

| Check | Result |
|---|---|
| Full suite | **379 passed, 8 skipped** |
| All twelve ES modules parse | pass (checked with node) |
| Every endpoint the app calls exists in the schema | pass |
| Every manifest icon is served | pass |
| Every shell file the worker lists exists | pass |
| Service worker caches GET only, never attachments or auth | pass |
| No token or secret embedded; no localStorage | pass |
| Registration form has no role field | pass |
| Map failure degrades rather than blanks the view | pass |
| Focus visible, reduced motion, dark mode, 44px targets | pass |

### Unresolved

1. **Nothing pushed since session 14.** Migrations, reseed, commit, push, then click
   through `/app` on the live deployment.
2. Clearance still has no integration test and is not visible in the seeded demo.
3. The old page at `/` is still there by design, and should be retired once `/app` is
   proven.

### Next actions, in order

1. `alembic upgrade head`, `python -m scripts.seed_demo --reset`, `pytest`, push
2. Exercise `/app` live — install it, turn off data, file a report, watch it queue and send
3. The five submission documents: SRS, Testing Report, Technical Debt Plan, User Manual,
   consolidated Project Documentation

---

## 13 August 2026 — Session 16: B22 the web page — the build is complete

### What happened

**The last build item.** One static HTML page, no framework, no build step, served
directly by FastAPI (D-012). Everything it does goes through the same API documented at
`/docs` — nothing is special-cased for the page, which is what makes the generated
documentation a genuine second client rather than a description of one.

What is on it: a MapLibre map with incident pins sized and coloured by confidence and
status; an incident list; an evidence panel showing *why* a score is what it is; a report
form with map-pick, browser geolocation and voice recording; a notifications panel;
corridor follow and unfollow; the officer dispatch queue with warden assignment; and the
warden's own assignment list with resolve buttons.

**Everything is now reachable from a browser** — including the pieces built earlier that
had only ever been exercised through `/docs`.

### Choices worth defending

**The page must work when the network does not.** MapLibre loads from a CDN and tiles come
from OpenStreetMap; either can fail on a poor connection, which is precisely the connection
this system's users have. The map is wrapped in a try/catch and degrades to a message,
while the incident list below carries the same information. Tested.

**Incidents load without signing in.** A commuter checking the road ahead should not have
to create an account first. `loadIncidents()` runs at startup outside any auth branch.

**Voice sharing is unticked in the markup**, with a sentence explaining that a recording
identifies your voice. Consent given, never assumed — including by a pre-ticked box.

**Every user-supplied string is escaped** before reaching `innerHTML`. Display names, notes
and messages all come from users; without escaping, a display name containing a script tag
would execute. There is a test asserting `esc()` wraps each of them.

**The token lives in `sessionStorage`, not `localStorage`.** Neither is ideal — a httpOnly
cookie is the right answer and needs CSRF protection with it — but the weaker option should
not be chosen by accident. Recorded as debt.

### A small lesson from the test suite

`test_the_token_is_not_kept_in_local_storage` failed on its first run — because the word
`localStorage` appears in the **comment explaining why it was avoided**. The test matched
prose rather than code.

Fixed by checking for `localStorage.` with the dot, which distinguishes use from mention.
Minor, and worth recording: a test that greps source text is testing the documentation as
well as the behaviour, and needs to be written knowing that.

### Verified

| Check | Result |
|---|---|
| Full suite | **322 passed, 8 skipped** |
| Every endpoint the page calls exists in the API schema | pass |
| Page calls at least 10 endpoints (meta-test) | pass |
| Map failure does not take the page down | pass |
| Incidents load signed out | pass |
| Voice sharing unchecked in markup | pass |
| User text escaped before `innerHTML` | pass |
| No token or secret embedded | pass |

The "every endpoint exists" test is the useful one: a static page has no compiler, so
renaming a route silently breaks a button and nothing complains until someone clicks it.

### Where the build stands

All planned work is done: B01–B09, D, and enhancements A, B, C, D, E, F.
**322 tests, 8 integration tests skipped without a database, 34 API endpoints,
7 migrations, 35 dated decisions, 22 technical debt items, 9 module explainers.**

### Unresolved

1. **Migrations not applied and nothing pushed since session 14.** `alembic upgrade head`,
   reseed, commit, push.
2. Clearance has **no integration test** and is **not visible in the seeded demo** —
   seeded incidents are too recent to expire and none are resolved.
3. Keep-warm ping still not configured.
4. `sessionStorage` for the token — debt, not yet written up.

### Next actions, in order

1. `alembic upgrade head`, `python -m scripts.seed_demo --reset`, `pytest`, commit, push,
   then open the live page and click through it
2. Integration test for clearance, and a seeded resolved incident so the demo shows it
3. The remaining submission documents: SRS, Testing Report, Technical Debt Plan, User
   Manual, consolidated Project Documentation

---

## 13 August 2026 — Session 15: clearance notifications and the circuit breaker

### What happened

Two features, and building the first exposed a defect that had been present since B06.

**Clearance notifications.** A system that reports blockages and never reports clearances
trains people to ignore it. Three reasons a road stops being a problem, each worded
differently: `resolved` (someone attended, it is clear), `false_alarm` (someone attended
and found nothing), `expired` (nobody ever confirmed it). Distinguishing the second from
the first matters — "we fixed it" and "there was nothing there" are different facts, and a
commuter judging whether to trust the *next* warning deserves to know which they got.

**The audience is the audience of the original warning** (**D-033**), read from the
notifications already sent rather than recomputed from corridors. An incident's centroid
*moves* as reports accumulate, so recomputing at clearance time could reach a different set
of people and leave some commuters permanently believing a road is shut. The set that was
warned is a fact; the set that would match now is a recalculation.

The clearance outbox row is written **in the same transaction as the resolution**, for the
same reason intake writes its outbox row alongside the report.

### The defect the advisory revealed

**Stored confidence never decayed.**

Confidence is calculated when reports arrive and written to the incident row. Decay is
applied at the moment of calculation, and calculation only happens during a rebuild, which
only happens when a new report lands nearby.

So an incident reported once at 07:00 and never mentioned again kept its 07:00 confidence
**forever** — sitting on the map at 0.22 at midnight, hours after it had decayed to nothing
in principle.

The decay in `confidence.py` was correct, fully property-tested, and **applied to nothing
that was sitting still.** A unit-tested function can be right in isolation and unreached in
practice. That is worth saying out loud, because 53 passing property tests did not catch
it — only building a feature that depended on the behaviour did.

Fixed with a periodic sweep in the worker (`app/services/staleness.py`): every five minutes
it fades incidents whose newest report is more than eight half-lives old, writes the decayed
value down, and emits a clearance. It only touches incidents in a **computed** state — a
warden already at a junction must not be stood down because the reports that summoned them
decayed. Remaining approximation quantified as **TD-22**.

### The circuit breaker

Five consecutive failures open it for thirty seconds; one test call is then allowed; a
single failure from half-open re-opens immediately.

The problem it solves is not correctness — every line behaves as written. When a provider
is down, each attempt costs a thirty-second timeout, so fifty queued notifications become
twenty-five minutes of the worker doing nothing but waiting. **Someone else's outage
becomes ours.** The breaker turns a thirty-second wait into a microsecond refusal.

Verified behaviour, walked through:

```
07:00:00  closed     start
07:00:00  closed     failure 1, 2
07:00:00  open       failure 3 -> tripped
07:00:10  open       still refusing instantly
07:00:30  half_open  will allow one test call
07:00:31  open       test call failed -> open again
07:01:02  half_open  another 30s
07:01:02  closed     test call worked -> normal
```

**The clock is a parameter, not a call** (**D-035**). That is what makes a thirty-second
timeout testable in microseconds. Every time-dependent module in the project now follows
this — `confidence`, `clustering`, `staleness`, `circuit_breaker` — with the worker loop as
the single place the impurity is confined.

Notifications are **not lost** when the breaker is open: the rows are already in the
database and users see them in the application. Delivery is the optional extra, which is
exactly why giving up on it quickly is safe.

**Demonstrable in about a minute** via `/admin/gateway/fail`, `/admin/drain`,
`/admin/gateway`, `/admin/gateway/heal`.

### Verified

| Check | Result |
|---|---|
| Full suite | **309 passed, 8 skipped** |
| 34 documented API paths | pass |
| Breaker trips exactly at the threshold (property test) | pass |
| A success resets the consecutive run | pass |
| Half-open allows one call; one failure re-opens | pass |
| Rejections counted separately from failures | pass |
| Counters never disagree with calls attempted (property) | pass |
| Clearance wording differs per reason, no internal identifiers | pass |
| Clearance key derived, stable, distinct from the advisory key | pass |

New debt: **TD-21** the deliberately-breakable gateway on the live deployment (critical
before real use), **TD-22** stored confidence decays only when the sweep runs, with the
error quantified at about 7% between sweeps.

Explainer written: `09-circuit-breaker-and-clearance.md`.

### Unresolved

1. **Migrations not applied** — `alembic upgrade head`, then reseed with `--reset`.
2. No quiet hours; everyone following a road hears, including someone heading elsewhere.
3. Keep-warm ping still not configured.

### Next actions, in order

1. `alembic upgrade head`, `python -m scripts.seed_demo --reset`, `pytest`, commit, push
2. **B22 — the web page.** The map, report form, dispatch queue and notifications. This is
   the last build item; everything after it is documentation and packaging.

---

## 13 August 2026 — Session 14: B corridors and the commuter advisory

### What happened

**The commuter half of the product now exists.** Everything before this served the control
room; this is what a member of the public gets back for reporting. It is also the first
time the outbox delivers something a *user* can see.

**Corridors are LINESTRINGs, not points.** "Is this incident on my route?" is a question
about distance from a line, which `ST_DWithin` answers directly in metres against the GiST
index. A corridor modelled as a centre point with a radius could not answer it — a circle
covering the 20 km Tema Motorway would cover half of Accra.

**Two thresholds, deliberately** (**D-030**). Commuters are warned at 0.35; police are
called at 0.70. Not an inconsistency: sending a warden to nothing wastes someone needed at
a real junction, while telling a commuter about something that turns out to be clear costs
a glance at a map. Different costs of being wrong, different thresholds. Still above a
single report, so nobody's unsupported word warns a whole corridor.

**The fan-out is in the worker** (**D-031**). The projector writes *one* outbox row however
many people follow the road. Doing the fan-out during submission would make it slow in
proportion to a corridor's popularity — the system would be slowest exactly when an
incident matters most.

### The subtle one: identity

`incidents.id` is **useless for remembering anything**. The projector deletes and recreates
incident rows on every rebuild, so a notification keyed on the primary key would be
orphaned by the very next nearby report, and the same commuter would be warned twice about
the same jam.

Added `incidents.cluster_key` — the smallest contributing report id (**D-032**). It
survives rebuilds because cluster membership is order-independent, so the minimum member id
is a property of *which reports belong together* rather than of when they arrived.

The primary key identifies a row. The cluster key identifies the event. Only the second is
stable, because rows here are derived data and the event is not.

**Delivered once**, guaranteed by two unique constraints, both using `ON CONFLICT DO
NOTHING` rather than catching `IntegrityError` — a raised violation aborts the surrounding
transaction, which inside the worker would discard every notification queued behind it.
No "has it already crossed the threshold?" bookkeeping exists anywhere; the idempotency key
does that work, which is simpler and more reliable than tracking state that gets rebuilt
from scratch anyway.

**15 real Accra corridors seeded**, with subscriptions arranged so several commuters follow
the roads where the two verified incidents sit — otherwise the feature would demonstrate an
empty list.

### Verified

| Check | Result |
|---|---|
| Full suite | **282 passed, 8 skipped** |
| Migration 0006 → 0007 SQL valid | pass |
| 29 documented API paths | pass |
| Advisory threshold below dispatch, above one report | pass |
| Message contains no raw numbers or internal identifiers | pass |
| Notifications key on cluster key, not incident id | pass |
| LINESTRING WKT puts longitude first | pass |
| Every seeded corridor point inside Ghana | pass |
| Seeded subscriptions will actually produce notifications | pass |

Explainer written: `08-corridors-and-commuter-advisory.md`.

### Unresolved

1. **Migration 0007 not applied** — `alembic upgrade head`, then reseed with `--reset` so
   corridors and subscriptions exist.
2. **Nothing tells a commuter when a road clears.** A system that reports blockages and
   never reports clearances trains people to ignore it. Recorded in D-030 as a gap.
3. No quiet hours, no direction of travel — everyone following a road hears, including
   someone 15 km away going the other way.
4. Keep-warm ping still not configured.

### Next actions, in order

1. `alembic upgrade head`, `python -m scripts.seed_demo --reset`, `pytest`, commit, push
2. C — circuit breaker
3. B22 — the web page: map, report form, dispatch queue, notifications

---

## 13 August 2026 — Session 13: consent for recordings, superseding D-028

### What happened

**A design decision was challenged in review and did not survive.** The author asked why
other users should be denied a recording that would help them judge an incident. The
answer was that the original reasoning was wrong in two ways.

**It conflated two different privacy concerns.** NFR-4 protects the *reported party* — the
person being accused. D-028 applied it to the *reporter*. Those are different, and the
second does not follow from the first: a flood on Spintex Road accuses nobody, so there
was no reported party and the justification did not apply at all.

**It discarded most of the value of capturing voice.** "Tipper truck across two lanes,
backed up to Odorna" tells a commuter far more than *accident, confidence 0.88*.

The concern is real but **narrow** — it bites on accusatory reports, where a speaker may
be recognised by the person they accused, and not on flooding. No single rule fits both,
and the reporter is the only person who knows which case they are in.

**So they are asked.** `is_public` on each attachment, default off, set at upload and
changeable at any time through `PATCH /attachments/{id}/visibility`. Only the reporter may
change it — not even an officer, because consent somebody else can give on your behalf is
not consent, and consent that cannot be withdrawn is not a choice. The control room can
always play a recording regardless, since a warden being sent somewhere should hear why.

The listing endpoint filters with the same rule that guards the bytes, so an unshared
recording is **invisible rather than merely unplayable** — listing something and then
refusing it announces that it exists.

Recorded as **D-029**. D-028 is marked superseded and **kept unedited**: a decision log
that quietly deletes its mistakes is not a record of anything.

**Transcription was reclassified.** It had been a nice-to-have in the backlog. It is now
the **top item in the evolution plan**, because it is the actual resolution to this
tension rather than a feature — publish the text, restrict the audio, and no reporter has
to choose between helping and staying anonymous. The current design only *manages* that
trade-off.

**NFR-4a added to the SRS.** NFR-4 covers the accused; NFR-4a covers the accuser. The two
were conflated once, so they are now written down separately.

### Verified

| Check | Result |
|---|---|
| Full suite | **255 passed, 8 skipped** |
| Sharing defaults to off | pass |
| Shared recording plays for signed-out visitors | pass |
| Unshared recording silent to other commuters and to anonymous callers | pass |
| Owner can always play their own | pass |
| Officer, warden and admin can play anything | pass |
| Consent is per attachment, not per user | pass |
| Migration 0005 → 0006 SQL valid, existing rows default private | pass |

Existing attachments default to private on migration: they were uploaded with no
opportunity to consent, and retroactively publishing them would be precisely what the
column exists to prevent.

### Unresolved

1. **Migrations 0005 and 0006 not yet applied** — `alembic upgrade head` before pushing.
2. Seed data contains no attachments, so neither the evidence bonus nor sharing is
   visible in the demonstration.
3. Keep-warm ping still not configured.

### Next actions, in order

1. `pip install -r requirements.txt`, `alembic upgrade head`, `pytest`, commit, push
2. B — corridor subscriptions and commuter advisory
3. C — circuit breaker
4. B22 — the web page

---

## 13 August 2026 — Session 12: F voice notes, and a real bug found by property testing

### What happened

**F — voice notes.** NFR-3 said the driver-facing view must never ask anyone to type
while driving. Until now that was **a constraint with no answer** — the SRS said what the
system would not do without saying how a driver reports anything at all. Hold a button,
speak, release. In a viva, "how does a driver report a hazard?" was a question to concede;
now it is one to answer.

Attachments live in **their own table**, not as columns on `reports`. That table is
scanned constantly by clustering, and binary data in those rows would compete with the
query workload for buffer cache — audio nobody is playing would slow down every
clustering pass. In a table nothing scans, it costs nothing.

**Two security decisions worth volunteering.** Uploads are served with
`X-Content-Type-Options: nosniff` and `Content-Disposition: attachment`, because a file
declared as audio whose bytes are HTML can otherwise be sniffed by a browser and executed
on our origin — stored XSS. And **playback is restricted to the recorder and the control
room**, because a voice recording identifies its speaker; it is closer to biometric data
than to a text note, and NFR-4 exists to keep exactly that away from other users.
Unauthorised requests return 404 rather than 403, since a 403 confirms the attachment
exists. Recorded as **D-028**.

**Evidence is tied to the advanced concept, not bolted beside it.** A report carrying a
recording weighs 1.25× more (**D-026**) — a recording is much harder to fabricate from an
armchair than a tapped coordinate. Capped, so it can never carry a report past the
escalation threshold alone; corroboration remains the only route to verification. It
multiplies reputation rather than replacing it, so a discredited account cannot buy back
standing with audio.

### The finding of the session

**A clustering property test failed on code that had passed, been reviewed and been
deployed for five sessions.**

```
assert min(lons) <= centroid_longitude <= max(lons)
AssertionError: assert -0.11988551688412255 <= -0.11988551688412256
```

Three **identical** longitudes, whose mean came out one unit in the last place *below* the
minimum input. Nothing overflowed — the exact mean is simply not representable in binary
floating point, and the nearest representable value sits outside the range of its own
inputs.

Physically femtometres. As an invariant, false — and a cluster centroid escaping its own
bounding box is exactly the sort of thing that violates a database constraint two years
later in a stack trace nobody can explain.

**No example-based test would have found it.** It needs several identical coordinates with
an unlucky bit pattern, which nobody writes by hand.

Fixed with `math.fsum` plus a clamp, so the invariant holds by construction rather than by
luck (**D-027**). Verified at 1000 generated examples and pinned with a regression test
using the exact failing value.

**This is the concrete answer to "what did property-based testing actually buy you".**

### Verified

| Check | Result |
|---|---|
| Full suite | **245 passed, 8 skipped** |
| Centroid property at 1000 examples | pass |
| Order independence at 1000 examples | pass |
| Content-type allow-list rejects html, js, svg, octet-stream | pass |
| Browser codec parameters (`audio/webm;codecs=opus`) accepted | pass |
| Size cap at the exact boundary | pass |
| Evidence bonus cannot breach the single-report ceiling | pass |
| Existing confidence tests unaffected by the new parameter | pass |

New dependency: `python-multipart` — FastAPI raises at import without it when file
uploads are declared.

New debt: **TD-19** media in the database rather than object storage, the item that fails
first under real adoption; **TD-20** client-declared audio duration is unverified, which
is acceptable only while nothing makes decisions from it.

Explainer written: `07-voice-notes-and-evidence.md`.

### Unresolved

1. **Migration 0005 not yet applied** — `alembic upgrade head` before pushing.
2. No playback UI; the endpoint exists, the player arrives with the page at B22.
3. Seed data contains no attachments, so the evidence bonus is not visible in the demo.
4. Keep-warm ping still not configured.

### Next actions, in order

1. `pip install -r requirements.txt`, `alembic upgrade head`, `pytest`, commit, push
2. B — corridor subscriptions and commuter advisory
3. C — circuit breaker
4. B22 — the web page, at which point the map, the form and the player become visible

---

## 13 August 2026 — Session 11: B08 lifecycle, dispatch and the reputation loop

### What happened

**B08 — the officer workflow.** The dispatch queue now has something to do with the two
verified incidents the seed produces.

`app/lifecycle.py` holds every legal transition in **one table**. Anything absent is
impossible by construction rather than by remembering to check — the alternative is
conditional checks in each handler, which is how the third handler someone adds becomes
the one that forgets. The same table drives the interface through `allowed_actions`, so a
button that would be refused is never offered, and a property test asserts the two agree
for every combination of state, action and role. Recorded as **D-024**.

The distinction the module exists to enforce: **computed states** (reported,
corroborated, verified) come from confidence and move both ways; **decided states**
(assigned, resolved) come from a person and arithmetic never touches them. That is what
stops a decaying score un-assigning a warden already standing at the junction.

Two policy constraints worth defending: an unverified incident **cannot** be assigned, or
the escalation threshold is decoration; and an incident nobody was sent to **cannot** be
resolved, or the queue can be cleared by wishful thinking.

**The reputation loop is closed.** Until now reputation was seeded and never moved.
Resolving an incident now vindicates or contradicts every reporter, which is why
resolution records an *outcome* (migration 0004) and not just a time. Both directions are
required — if incidents could only be confirmed, fabricating would cost nothing.

Formula is a Beta posterior, `(confirmed + 2) / (confirmed + contradicted + 4)`, recorded
as **D-025**. A plain success ratio would give 1.0 after one confirmed report — file one
true report, become fully trusted, then fabricate. The prior closes that: one
confirmation moves a new account 0.50 → 0.60, and 0.9 takes roughly eighteen. Trust is
deliberately lost faster than gained (5 confirmations = 0.778; 3 false alarms after that
= 0.583) so fabricating is not profitable in expectation. Reputation can never reach 0,
because a reporter at zero could never recover — every report would carry zero weight, so
none could ever be confirmed.

### A vacuous test caught for the second time

`tests/test_routing.py` guards against a literal path being shadowed by an earlier
parameterised one — `/incidents/queue` swallowed by `/incidents/{incident_id}` would
return 422 with nothing failing at startup.

The first version of its route traversal **found 5 routes out of 21**. FastAPI 0.141 does
not put included routes on `app.routes`; it inserts an `_IncludedRouter` wrapper holding
the original router. Every check passed over an almost-empty collection.

Same failure as the clustering generator in Session 7, and the same remedy: a meta-test
(`test_the_traversal_finds_the_real_routes`) that asserts the traversal finds at least 15
routes. **This is now a recurring pattern worth naming — when a test asserts something
about a collection, assert the collection is non-empty first.**

The actual ordering turned out to be safe: the literal paths have two segments so a
single-segment parameter cannot match them, and `/queue` is registered first.

### Verified

| Check | Result |
|---|---|
| Full suite | **211 passed, 8 skipped** |
| All 19 API paths registered and documented | pass |
| Migration 0003 → 0004 SQL valid | pass |
| Commuter offered no actions in any state | pass |
| Warden cannot self-assign | pass |
| Unverified incident cannot be assigned | pass |
| Unassigned incident cannot be resolved | pass |
| `allowed_actions` agrees with the guard for all combinations | pass |
| Reputation bounded, monotonic, never 0 or 1 | pass |

Explainer written: `06-lifecycle-and-reputation.md`.

### Unresolved

1. **Migration 0004 not yet applied** — `alembic upgrade head` before pushing.
2. Keep-warm ping still not configured.
3. No audit trail of who assigned or resolved what — only current state is kept.
4. Wardens are not notified of assignment; the outbox could carry it, sink is log-only.

### Next actions, in order

1. `alembic upgrade head`, `pytest`, commit, push
2. F — voice notes, the answer to NFR-3
3. B — corridor subscriptions and commuter advisory
4. E — photo evidence; C — circuit breaker

---

## 13 August 2026 — Session 10: integration verified, D seed data

### What happened

**The integration tests passed against real Neon PostGIS — all 8, in 104 seconds.** That
is the projection verified end to end for the first time: `ST_DWithin` measuring metres
rather than degrees, coordinates round-tripping through the geography column in the right
order, an 8 km separation refusing to merge, a later report merging into an existing
incident rather than spawning a neighbour. The runtime is network latency to Neon, not
slowness in the code.

**D — demonstration data.** 16 accounts and 38 reports across 20 real Greater Accra
locations, forming a Tuesday morning rush hour.

Two properties of this are load-bearing and both are tested:

- **Timestamps are relative to run time, never fixed.** Confidence halves every 45
  minutes, so hard-coded times would leave the map blank whenever anyone actually
  looked. An examiner would open it, see nothing, and conclude the system does not work.
- **Identifiers are deterministic** (`uuid5` from a fixed namespace), so re-running
  updates rather than duplicates.

Seeded reports go through the **ordinary outbox, clustering and confidence path**.
Nothing is special-cased, so what an examiner sees is produced by exactly the code that
handles live submissions.

### The scenario, dry-run through the real engine

38 reports → **20 incidents**:

| Place | Type | Reports | Confidence | Status |
|---|---|---:|---:|---|
| Kwame Nkrumah Circle | accident | 6 | 0.882 | **verified** |
| Kaneshie Market | closure | 5 | 0.728 | **verified** |
| Achimota junction | signal outage | 4 | 0.626 | corroborated |
| Spintex Road | flood | 3 | 0.555 | corroborated |
| Madina Market | accident | 3 | 0.146 | reported — *visibly fading, 95 min old* |
| Lapaz | closure | 1 | 0.040 | reported — *discredited reporter* |
| Nungua | flood | 1 | 0.020 | reported — *discredited reporter* |

Two verified, two corroborated, sixteen unconfirmed. Both mechanisms are visible at a
glance: **Madina has three reports and scores 0.146 because they are 95 minutes old**,
while Lapaz has a fresh report scoring 0.040 because its reporter has a 0.12 reputation.
Decay and reputation, each demonstrable without explanation.

**`POST /admin/seed`** refreshes the data from a browser, and **`POST /admin/drain`**
forces the worker to run immediately — useful mid-demonstration.

### Verified

| Check | Result |
|---|---|
| Integration suite against real Neon PostGIS | **8 passed** |
| Full suite | **175 passed, 8 skipped** |
| Every seeded place inside Ghana | pass — catches a lat/long swap in the table |
| All six incident types represented | pass |
| Reports span fresh and fading | pass |
| Nothing older than intake would accept | pass |
| Report keys unique | pass |

New debt: **TD-17** — `POST /admin/seed` and `/admin/drain` exist on the production
deployment. Classified **critical**: acceptable only because this deployment exists to be
marked. Resolution is to gate them on `ENVIRONMENT != "production"` at router
registration, so they cannot be reached at all rather than merely being protected.

### Unresolved

1. Seed not yet run against Neon — one command.
2. Keep-warm ping still not configured.
3. Clustering and confidence parameters remain guesses (TD-03, TD-04).

### Next actions, in order

1. `python -m scripts.seed_demo --reset`, then push and deploy
2. B08 and the officer workflow — lifecycle state machine, dispatch, assignment
3. F — voice notes, the answer to NFR-3
4. B — corridor subscriptions and commuter advisory

---

## 13 August 2026 — Session 9: B09 outbox worker — the system is connected

### What happened

**The pure modules are no longer orphans.** Until now `clustering.py` and
`confidence.py` were exercised only by tests; nothing in the running application called
them. B09 closes that loop.

`POST /reports` → outbox row (B04) → worker claims it → neighbourhood fetched with a
live PostGIS query → clustering and confidence run → incident written → `GET /incidents`.

**`app/services/projection.py`** — rebuilds incidents rather than updating them. That
matters: a new report can **merge two previously separate incidents**, and an algorithm
that only appends to an existing incident can never discover that. Rebuilding is also
what keeps the replay property true.

The neighbourhood fetch has two steps, and the second is easy to miss. Step 1 finds
same-type reports near in space and time. Step 2 expands to *whole incidents* — without
it, a rebuild can pull in half an incident and the other half silently vanishes, because
its reports were never in the working set.

**Human decisions survive rebuilds.** Assignment and resolution are captured before the
delete and carried across, keyed by the cluster's smallest member id — stable because
membership is order-independent. Confidence computes `reported`, `corroborated` and
`verified`; `assigned` and `resolved` are human acts and arithmetic never overwrites them.

**`app/worker.py`** — in-process asyncio drainer. `FOR UPDATE SKIP LOCKED` (a no-op with
one worker, correct with several), one commit per batch so a crash replays the whole
batch, failures recorded per row so one poison message cannot block everything behind it,
and an exception can never kill the loop.

**`app/routers/incidents.py`** — results are finally visible. Note the asymmetry:
incidents are public, individual reports are not. `GET /incidents/{id}` returns the
contributing reports and the weight each carried, which is what makes confidence
explainable rather than merely displayed.

### The testing gap, and how it was closed

Everything so far ran against pure functions and stubs. That cannot catch what only a
real database can: whether `ST_DWithin` measures metres or degrees, whether the geography
column round-trips coordinates the right way round, whether cascades behave.

PostGIS could not be installed in the build sandbox — `pgserver` ships only `plpgsql` and
`vector`, and there is no root for apt. So `tests/test_integration_pipeline.py` was
written to run against a real database and **skip automatically when `DATABASE_URL` is
unset**. Two of its cases earn their keep alone: an 8 km separation must not merge (proves
metres, not degrees), and coordinates must survive the round trip (a swap would put the
centroid in the Gulf of Guinea with nothing else noticing).

**These have not yet been run.** They need running locally against Neon — that is the
next action, and the first real verification of the projection.

### Verified

| Check | Result |
|---|---|
| Full suite | **154 passed, 8 skipped** (integration, awaiting a database) |
| Batch commits once, not per row | pass |
| One failing row does not block its batch | pass |
| Row abandoned after 5 attempts, left visible | pass |
| Unknown event type skipped, not retried forever | pass |
| Handler exception does not kill the loop | pass |
| Already-processed row not handled twice | pass |

New debt: **TD-16** — the rebuild neighbourhood bound (3× radius) is a chosen number, not
a derived one. With chaining (TD-13) a long enough chain could link incidents outside each
other's neighbourhood and a merge would be missed. Fix is to expand iteratively until no
cluster touches the edge.

Explainer written: `05-the-outbox-worker-and-projection.md`.

### Unresolved

1. **Integration tests not yet run against Neon.** This is the only real verification gap.
2. Demo accounts still do not exist — step D.
3. Clustering and confidence parameters remain guesses (TD-03, TD-04).
4. Keep-warm ping not configured.

### Next actions, in order

1. `pytest tests/test_integration_pipeline.py -v` locally against Neon
2. Commit, push, deploy — **this deploy changes what the app does**, unlike the last one
3. D — seed data and demo accounts: ~20 Accra junctions, ~60 reports, real clustering
4. B08 and the officer workflow — lifecycle state machine, dispatch, assignment

---

## 13 August 2026 — Session 8: B06 confidence, submission file created

### What happened

**Live deployment confirmed working.** `https://nkwanta.onrender.com/` returns a green
status with `PostGIS 3.6.0` in production. Deployment is retired as a risk.

**`Deployment_and_Source_Links.txt` created** — one of the six required submission files.
Student: Theophilus Caesar, 22424543. Title: *Nkwanta: A Road Incident Reporting and
Dispatch System for Urban Ghana*. Repository `github.com/TheoCaesar/nkwanta`. The file
opens with the free-tier cold-start warning so an examiner does not conclude the
application is broken, explains the four roles, and ends with a five-minute walkthrough
pointing at the parts worth seeing — including the swapped-coordinates rejection.

**B06 — confidence scoring.** Each report contributes
`reputation × decay(age) × evidence_strength`, and those weights combine with **noisy-OR**:
`1 − ∏(1 − wᵢ)`, read as "the probability that at least one reporter is right".

Chosen over summing weights, which fails twice: it exceeds 1, and it treats the hundredth
report as worth as much as the second. Noisy-OR is bounded, monotonic and saturating with
**no clamping anywhere** — and because multiplication is commutative, it is
order-independent, matching the guarantee clustering makes. Recorded as **D-023**.

The 0.45 evidence cap is what forces corroboration. Even a perfectly trusted reporter
alone scores 0.427 against a 0.70 threshold, so police are never summoned on one
person's word. Directly tested.

### Calibration — measured, not assumed

Confidence for *n* fresh reports:

| n | rep 0.30 | rep 0.50 | rep 0.95 |
|---:|---:|---:|---:|
| 1 | 0.135 | 0.225 | 0.427 |
| 3 | 0.353 | 0.535 | **0.812** |
| 5 | 0.516 | **0.720** | 0.938 |
| 8 | 0.687 | 0.870 | 0.988 |

One unknown reporter alerts nobody. Five ordinary reporters reach the police. Three
consistently reliable ones get there faster — which is the entire purpose of tracking
reputation. Discredited accounts need eight or more, so someone inventing closures from
home cannot get there alone.

A single average report decays 0.225 → 0.113 at 45 minutes → 0.001 at six hours. **That
is what makes incidents clear themselves**, with nobody pressing a button.

### Verified

| Check | Result |
|---|---|
| Full suite | **143 passed** (53 property-based) |
| Order independence of the score | pass, bit-for-bit identical |
| Bounded [0,1] with no clamping in the code | pass |
| More evidence never lowers confidence | pass |
| Each further report adds less than the last | pass |
| No single report can verify alone | pass |
| Live deployment | **green, PostGIS 3.6.0** |

New debt: **TD-15** — noisy-OR assumes independent reports and they are not. Six people
in one jam are one event seen six times, so confidence is systematically overstated for
crowds. The bias runs towards over-confidence, which is the more dangerous direction.
Recorded with two proposed mitigations rather than hidden.

Explainer written: `04-confidence-and-decay.md`.

### Unresolved

1. Confidence and clustering are both pure modules with **no caller yet**. They start
   running for real at B09, the outbox worker.
2. Clustering and confidence parameters remain guesses fitted to no data (TD-03, TD-04).
3. Keep-warm ping not yet configured at cron-job.org.
4. Seeded demo accounts declared in the submission file **do not exist yet** — the seed
   script creates them at step D.

### Next actions, in order

1. B09 — the outbox worker. Drains the outbox, runs clustering and confidence, writes
   incidents. This is where the pure modules finally connect to the running system.
2. D — rich seed data and demo accounts, at which point the application starts looking
   like a system rather than a prototype
3. B08 and the officer workflow — lifecycle state machine, dispatch, assignment

---

## 13 August 2026 — Session 7: B05 clustering, and the application is live

### What happened

**Deployed to Render successfully.** The first attempt failed at startup with
`RuntimeError: JWT_SECRET is still the development default` — which is the safeguard in
`app/main.py` working exactly as intended. A production service signing tokens with a
secret published in the repository is not degraded, it is unauthenticated, so it refuses
to boot rather than accepting forgeable tokens.

Root cause worth recording: `generateValue: true` in `render.yaml` only fires when Render
*creates* a service from the blueprint. An existing service does not pick up newly added
variables. Resolved by setting `JWT_SECRET` by hand in the dashboard. Added to the
runbook troubleshooting table, along with the note that `No open ports detected` is a
symptom — the app exited before binding — and the real error is always further up the log.

All three migrations applied to Neon during the build. **The application is live.**

**B05 — the clustering engine.** The module that makes this project advanced rather than
merely large.

Grouping is a **graph problem**: an edge between two reports of the same type that are
close in both place and time, and incidents are the connected components of that graph,
computed by union-find.

The alternative — incremental assignment, where each arriving report joins the nearest
existing incident — is order-dependent and therefore unusable. The counter-example is now
a test: three reports in a line 200 m apart with a 300 m radius give one incident arriving
A, B, C and two arriving A, C, B. Connected components give one either way, because a path
exists through the middle report. Recorded as **D-020**.

`app/clustering.py` is deliberately **pure** — no database, no clock, no randomness. That
is what allows thousands of generated cases per second, which is what makes the
order-independence property provable rather than merely asserted.

### Two findings worth keeping

**Floating-point addition is not associative.** `(0.1+0.2)+0.3` differs from
`0.1+(0.2+0.3)` in the last bit. Summing centroid coordinates in different orders produced
answers differing by about 1e-16 degrees — nanometres, physically meaningless, but a
broken promise nonetheless. The property test asserts *identical*, not *nearly identical*,
so it caught it. Fixed by sorting by report id before summing. Weakening the assertion to
a tolerance would have let order matter a little and hidden a whole class of bug.

**The property tests were passing vacuously, and it took measuring to notice.** The first
generator scattered reports uniformly over Accra's 22 km × 28 km box. With at most 25
reports and a 300 m radius, only **1 generated set in 300** contained any merge at all —
so every property was passing over collections of singleton clusters, where
order-independence is trivially true. The generator now seeds hotspots the way reality
does, and `test_the_generator_actually_produces_merges` asserts more than half of sets
contain a real merge, so the file cannot silently rot again. Recorded as **D-022**.

### Verified

| Check | Result |
|---|---|
| Full suite | **111 passed** (21 property-based) |
| Order independence over random shuffles | pass, bit-for-bit identical |
| Reversal of arrival order | pass |
| The three-in-a-line counter-example, all 6 orderings | pass |
| Every report in exactly one cluster | pass |
| No two distinct clusters are linked | pass |
| Idempotence — clustering twice changes nothing | pass |
| Generator produces genuine merges | pass, >50% of sets |
| Live deployment | **up** |

Hypothesis profiles added (**D-021**): `dev` 50 examples, `default` 150,
`thorough` 1000 via `HYPOTHESIS_PROFILE=thorough pytest` for the testing report.

New debt: **TD-13** single-linkage chaining along a corridor, **TD-14** O(n²) pair
comparison. Both with proposed resolutions that preserve order-independence.

Explainer written: `03-clustering-and-order-independence.md`.

### Unresolved

1. **The three clustering environment variables are not yet set on Render.** They have
   safe defaults in code, so the app runs — but setting them explicitly is what makes
   TD-03 repayable by configuration rather than redeploy.
2. Clustering still runs nowhere in production — it is a pure module with no caller until
   the outbox worker exists at B09.
3. Clustering parameters still provisional at 300 m / 30 min (TD-03, highest priority).
4. Student ID and project title still not recorded.
5. Live URL not yet written into `Deployment_and_Source_Links.txt` — that file does not
   exist yet.

### Next actions, in order

1. Set the three clustering variables on Render
2. B06 — confidence scoring with time decay, turning a cluster into a number an officer
   can act on
3. B09 — the outbox worker, at which point the outbox rows written since B04 finally get
   drained and clustering runs for real
4. D — rich seed data, the point at which the application starts looking like a system
   rather than a prototype

---

## 13 August 2026 — Session 6: B03 authentication, B04 report intake

### What happened

**Scope expanded.** Submission deadline extended by 8 hours, and the observed build rate
is far above the bottom-up estimate's assumption. Six enhancements accepted (D-017):
rich seed data, Tier 1 officer workflow, voice notes, corridor subscriptions and
advisory, photo evidence, circuit breaker. The binding constraint is no longer hours —
it is **viva defensibility**, so a plain-language explainer is now written for every
module in `docs/explainers/`.

**B03 — authentication.** Four roles: commuter, warden, officer, admin. Warden added at
migration 0003; the VARCHAR + CHECK choice from D-005 meant a constraint swap inside an
ordinary transaction rather than an `ALTER TYPE`. Deliberately **no driver role** — a
driver and a passenger have identical permissions, and the difference is a client-side
mode (NFR-3), not an account type. The server cannot know who is driving.

Security decisions worth defending:

- **Self-registration can only produce a commuter.** `RegisterRequest` has no role field
  at all, so escalation is not a check that could be forgotten — it is an input that
  does not exist.
- **The database is read on every request**, not just the token. A token is a snapshot
  from up to twelve hours ago; a deactivated account must lose access immediately.
- **Failed logins take constant time.** bcrypt runs against a dummy hash for unknown
  emails, so response timing cannot be used to discover which addresses are registered.
- **Admins are not implicitly allowed everywhere.** Implicit superuser access is how a
  permission system quietly stops meaning anything.

**B04 — report intake with the transactional outbox.** The most important module in the
submission. The report row and its outbox row are added to one session and committed by
a single `commit()`, so the database guarantees both or neither. There is no instant at
which a report exists and the instruction to act on it does not.

Idempotency has two layers, and the distinction matters: the `SELECT` before insert is
a fast path, the unique constraint is the correctness. Two simultaneous retries both
pass the `SELECT`; only the constraint settles it, and the `IntegrityError` is caught
and resolved by returning the row the other request committed.

`app/geo.py` isolates the (longitude, latitude) conversion in one tested function.
Accra reversed lands 600 km out in the Gulf of Guinea and **nothing raises** — every
query runs and every answer is wrong. The Ghana bounding box is the safety net, and its
rejection message names the likely cause.

### Verified

| Check | Result |
|---|---|
| Full suite | **89 passed** |
| Report and outbox added before exactly one commit | asserted directly, order recorded |
| Nothing written when validation fails | pass — no orphan outbox row |
| Swapped coordinates rejected | pass |
| Migration 0002 → 0003 SQL | valid |

Explainers written: `01-authentication.md`, `02-report-intake-and-the-outbox.md`.

### Deployment configuration — now complete

`render.yaml` declares all seven environment variables. **Exactly one must be typed by
hand in the Render dashboard: `DATABASE_URL`.** `JWT_SECRET` uses Render's
`generateValue: true`, so it is generated strongly and stays stable. The clustering
parameters are declared as environment variables specifically so TD-03 can be repaid by
configuration rather than a redeploy. Full table in `RUNBOOK.md` Part 3.

### Unresolved

1. **Still not deployed to Render.** This is now the only significant outstanding risk.
2. Migration 0003 not yet applied to Neon.
3. Clustering parameters still provisional at 300 m / 30 min — needed by B05.
4. Student ID and project title still not recorded.

### Next actions, in order

1. `pip install -r requirements.txt`, `alembic upgrade head`, `pytest`, commit, push
2. **Deploy to Render** and confirm `/ready` on the live URL
3. B05 — spatio-temporal clustering, the piece that decides nineteen reports are one crash
4. B06 — confidence with time decay
5. B09 — outbox worker, at which point the outbox rows written since B04 finally get drained

---

## 13 August 2026 — Session 5: B01 verified live, B02 data model built

### What happened

**B01 confirmed working end to end on the development machine.** `alembic upgrade head`
applied against Neon, all tests green, `/health` and `/ready` both returning 200 with
PostGIS reporting. The largest risk in the schedule is retired.

Two build problems surfaced and were fixed, both worth recording because both are the
kind of thing that eats an hour if hit at 3 a.m.:

- **Python 3.14 had no wheels** for `asyncpg` 0.30 or `pydantic-core` 2.33, so pip tried
  to compile from source and failed on the missing MSVC and Rust toolchains. Pins moved
  forward to the first versions publishing 3.14 wheels, checked against the PyPI API
  rather than guessed. Recorded as **D-015**.
- **`pytest` failed where `python -m pytest` passed.** Module invocation puts the working
  directory on `sys.path`; the console script does not. Fixed permanently with
  `pythonpath = .` in `pytest.ini`, and both invocations now verified.

**B02 — the data model — is written and tested.** Five tables:

| Table | Role |
|---|---|
| `users` | People, and how much their reports have been worth believing |
| `reports` | What people told us. **Append-only. Never updated.** |
| `incidents` | Our interpretation. **A projection, fully rebuildable.** |
| `incident_reports` | Which reports make up which incident. Also projection. |
| `outbox` | Notifications still owed |

The line between `reports` and `incidents` is the architecture. Reports are permanent;
incidents are calculated, the way a bank balance is calculated from transactions rather
than stored. Drop `incidents` and `incident_reports`, replay every report, and you must
get back exactly what was there — which is what the replay property test will assert at
B19.

Design decisions worth defending in the viva:

- **`reports` has no `status` column.** A mutable status invites an UPDATE, and the
  replay property depends on the table never being edited. A contradiction is a *new*
  row pointing at the old one through `contradicts_id`.
- **Two clocks on every report.** `occurred_at` is what the reporter claims and can be
  wrong or dishonest; `received_at` is our server clock and cannot be. Clustering uses
  the first, auditing the second.
- **`Geography`, not `Geometry`.** Distances come back in metres on a curved earth, so
  "within 300 m" means the same thing everywhere. `Geometry` returns degrees, which vary
  with latitude.
- **A report may belong to at most one incident**, enforced by a unique constraint. If
  clustering ever tries to place one in two, the database refuses — the bug surfaces as
  an error rather than as a quietly double-counted confidence score.
- **Enums are VARCHAR + CHECK, not native PostgreSQL enums.** Adding a seventh incident
  type becomes a constraint change rather than an `ALTER TYPE` that cannot run inside a
  transaction.
- **`ondelete=RESTRICT` on `reports.reporter_id`.** Deleting a user must never silently
  erase the reports that justified sending a warden somewhere.

Migration `0002` hand-written rather than autogenerated — autogenerate mishandles
GeoAlchemy2 geography columns and cannot express the partial index on the outbox at all.

### Verified

| Check | Result |
|---|---|
| Full suite after B02 | **45 passed** |
| `alembic upgrade head --sql` generates valid SQL for 0001→0002 | pass |
| GiST spatial indexes on `reports.location` and `incidents.centroid` | present |
| Partial index `WHERE processed_at IS NULL` on outbox | present |
| Both `pytest` and `python -m pytest` | pass |

### Unresolved

1. **Migration 0002 not yet run against Neon.** Offline SQL generation passes; the live
   run is one command.
2. **Render deployment not yet done.**
3. **Clustering parameters still provisional** — 300 m / 30 min. Needed by B05.
4. `JWT_SECRET` needs generating before B03.
5. Student ID and project title still not recorded.

### Next actions, in order

1. `alembic upgrade head` against Neon → confirms 0002
2. Push, run the Render blueprint, confirm `/ready` on the live URL
3. B03 — auth and seeded users
4. B04 — report intake with the transactional outbox. **The most important endpoint in
   the submission.**

---

## 12 August 2026 — Session 4: B01 complete, scaffold built and smoke-tested

### What happened

Built the full B01 scaffold and **verified it runs** rather than assuming it does.

**Application skeleton**

- `app/main.py` — thin entry point: routers, static mount, lifespan. Starts successfully
  with **no database attached**, which matters because the first deploy goes out before
  Neon is wired in, and a service that refuses to start cannot be diagnosed from its logs.
- `app/config.py` — settings from environment. Contains `_normalise_db_url`, which fixes
  the three things wrong with a copy-pasted Neon connection string: missing `+asyncpg`
  driver, `sslmode` (which asyncpg rejects outright), and Heroku-style `postgres://`.
  **This is the single most common reason a first deploy to Neon fails**, so it is solved
  once and unit-tested.
- `app/db.py` — async engine, lazily created, `pool_pre_ping` because Neon drops idle
  connections.
- `app/routers/health.py` — `/health` (liveness, never touches the database) and `/ready`
  (checks database + PostGIS). Deliberately separate: the keep-warm ping hits `/health`
  every 10 minutes and must not burn Neon compute-hours.
- `app/security.py` — bcrypt + JWT.
- `web/index.html` — status page that live-polls both endpoints.

**Migrations.** Alembic wired for async, URL read from the environment so no credential is
ever committed. Migration `0001` enables PostGIS.

**Deployment.** `render.yaml` blueprint, one free service, `DATABASE_URL` marked
`sync: false` so it is set by hand in the dashboard. `RUNBOOK.md` written as an executable
checklist: accounts → local run → deploy → keep-warm ping, with a troubleshooting table.

### Verified, not assumed

Everything below was actually executed in a Linux sandbox:

| Check | Result |
|---|---|
| All 14 pinned dependencies resolve and install | pass |
| Application imports and boots | pass |
| `GET /` , `/health`, `/ready`, `/docs`, `/openapi.json` | 200, correct payloads |
| Boots and serves correctly with **no** `DATABASE_URL` | pass |
| Alembic fails with a *helpful* message when `DATABASE_URL` is unset | pass |
| **22 tests pass** (13 health + URL normalisation, 9 security) | pass |

**One real bug caught before it could cost time.** `passlib[bcrypt]==1.7.4` is broken
against `bcrypt` 5.0 — passlib reads `bcrypt.__about__.__version__`, an attribute removed
in bcrypt 4.1, and every hash call raises. This would have surfaced at hour 3.7 during
B03 with auth half-written. passlib removed; bcrypt now used directly in `app/security.py`,
with passwords over 72 bytes **rejected rather than silently truncated** — a truncated
password that still authenticates is a security bug, not a convenience.

**Technical debt register opened at `docs/08-technical-debt.md`** — before the first
shortcut, as required. Twelve items, each with Debt → Cause → Impact → Priority →
Proposed Resolution, classified Acceptable / Scheduled / Critical, plus a repayment plan
ordered by value per hour. Total identified debt ≈14 hours against a ≈22-hour build.

### Where things stand

**B01 is code-complete and tested. It has not been deployed** — that needs the accounts,
which only you can create.

Highest-consequence open item is **TD-03**: the clustering radius (300 m) and window
(30 min) are reasoned guesses with no data behind them. They are the most consequential
unvalidated assumption in the system and they are needed by hour 8.6.

### Unresolved

1. **Accounts not yet created** — GitHub, Neon, Render. This blocks deployment and
   nothing else. `RUNBOOK.md` Part 1 walks through it in about 15 minutes.
2. **Student ID and project title** still not recorded.
3. **Clustering parameters** still provisional. Needed before B05 at hour 8.6.
4. `JWT_SECRET` needs generating and setting in Render before B03.

### Next actions, in order

1. Work through `RUNBOOK.md` Parts 1–3 → **live URL with `/ready` reporting PostGIS**
2. Set up the keep-warm ping (Part 4)
3. B02 — data model: users, reports, incidents, outbox
4. B03 — auth against the seeded users
5. B04 — report intake, the single most important endpoint in the submission

---

## 12 August 2026 — Session 3: Schedule fixed, hosting settled

### What happened

**Clock confirmed at 40 hours remaining.** No hosting accounts existed, so the stack was
re-planned around what is actually free — which removed a component rather than adding work.

Budget: 40 wall-clock hours − 7 sleep − 2 meals and breaks = **31 effective hours**, split
21.6 build / 7.0 documentation / 2.4 buffer. Buffer is 6%, which is thin; it is only survivable
because the cut list is agreed in advance.

**Tier 0 (lean) selected.** Tiers 1 and 2 are not attempted.

Verified two hosting facts by search rather than assumption, both of which changed the plan:

- **Neon** free tier supports PostGIS via `CREATE EXTENSION postgis`. 0.5 GB, 100
  compute-hours/month, no card, never expires. Confirmed suitable.
- **Render** free web services sleep after **15 minutes** idle and take **30–60 seconds** to
  wake, on 512 MB RAM and 0.1 CPU.

Both findings produced decisions:

- **D-012 — Vercel dropped.** The front end is one static page; FastAPI serves it via
  `StaticFiles`. Removes an account, a deploy target, a build pipeline and all CORS setup.
- **D-013 — outbox worker runs in-process** as an asyncio task, because Render's free tier
  permits one service and a separate worker is paid. A real compromise forced by a real
  constraint, and one of the strongest debt entries available.
- **D-014 — Render cold start accepted and disclosed**, mitigated by a 10-minute keep-warm ping
  and an explicit note to the examiner. The risk is that a grader assumes the app is broken; the
  fix is disclosure, not money.

Wrote `docs/07-build-schedule.md`: hour-by-hour plan across all 40 hours, protected tasks
marked, cut triggers with thresholds, pre-hour-zero checklist, and the build order within the
code.

### Where things stand

**Schedule is fixed and the first move is unambiguous:** create three accounts (~15 min), then
scaffold and deploy an *empty* application by hour 2.5. Deployment is pass-or-fail for 3 marks
and is the largest single risk in a 48-hour build — it gets retired first, while there is time
to fix it.

**Protected work, 13.6 hours, may not be cut under any circumstance:** B04 report intake with
transactional outbox (3.6), B05 spatio-temporal clustering (4.5), B19a order-independence
property test (1.5), B06 confidence with decay (1.5), B09 outbox worker with idempotency (2.5).

**Cut order agreed** at five thresholds, checked at hours 13, 25 and 31. If behind, cut without
re-deliberating. Every cut taken goes into the debt register with its cause — worth 6 marks, and
a documented cut reads completely differently from an unfinished feature.

**Still no code**, and that remains correct. Hour 0 has not started.

### Unresolved

1. **Student ID and project title** still not recorded — needed for the submission package.
2. **Clustering parameters** still unset. Provisional: 300 m and 30 minutes, varying by type —
   flooding needs a wider radius than a collision. Must be fixed before B05 at hour 8.6.
3. **Sleep block placement.** The schedule puts it at hours 18–25; slide it to match the actual
   night. Do not skip it — the 6% buffer assumes a rested developer for B09 onwards.
4. Neon and Render accounts unverified. If either fails, that must surface in the first 15
   minutes, not at hour 30.

### Next actions, in order

1. **Fifteen-minute pre-flight:** GitHub repo → Neon project + `CREATE EXTENSION postgis` →
   Render free web service → save connection string → record student ID and project title
2. Fix the clustering distance and time window, with written justification
3. Start hour 0: B01 scaffold, then **deploy the empty application before writing any feature
   code**
4. Open `08-technical-debt.md` before the first shortcut is taken, not after
5. Then follow `docs/07-build-schedule.md` §3 exactly

---

## 12 August 2026 — Session 2: Effort estimation

### What happened

Confirmed the examination clock is **already running** (exact hours remaining still to be
supplied). Developer experience recorded as fluent in Python, new to FastAPI, PostGIS and
event-driven patterns — this feeds directly into the environmental factors below.

Performed the effort estimation using **two techniques**, because one would have misled.

**Use Case Points**, calculated in full: 6 actors → UAW 13. 12 use cases → UUCW 120. UUCP 133.
Technical Complexity Factor 1.01. Environmental Complexity Factor 0.725. **UCP 97.39.** Rate
selected by the Schneider & Winters rule at 20 hours per UCP.

> **Full scope: 1,948 person-hours ≈ 12.8 person-months. Must-have subset alone: 1,391 hours.**
>
> Against a 48-hour window that is a ratio of roughly **40 to 1**.

**Bottom-up task estimation** for what actually fits, with per-task learning multipliers from
1.2 (routine) to 1.8 (outbox and PostGIS clustering). Three tiers produced:

| Tier | Contents | Raw | +15% contingency |
|---|---|---:|---:|
| 0 | Concept spine + auth + one static page | 24.2 h | **27.8 h** |
| 1 | Tier 0 + officer workflow + lifecycle + full tests | 30.1 h | 34.6 h |
| 2 | Full must-have + should-have | 40.9 h | 47.0 h |

**Finding: even Tier 0 needs a clean 48 hours.** Since the clock is already part-consumed,
Tier 0 as specified does not fit either. Two mitigations apply — Phase 1 documentation is
already banked, freeing hours the paper allocates to planning; and the front end is the
correct thing to sacrifice, since FastAPI's generated API documentation is a genuine
demonstrable interface at zero cost.

All arithmetic was computed programmatically rather than by hand, and re-checked.

Three decisions recorded: **D-009** (the deliverable is a vertical slice, not the product),
**D-010** (ordered cut list agreed in advance, so cuts become a lookup rather than a 3 a.m.
judgement call), **D-011** (the concept spine is ring-fenced against all cuts).

### Where things stand

`docs/06-effort-estimation.md` is complete and is a submission-ready artefact. It covers
technique justification, the full UCP working, the bottom-up breakdown, assumptions,
constraints, why the two techniques disagree by 30×, and — the section the mark scheme is
actually asking for — a table of six specific ways the estimate changed the project.

**Scope is now tiered rather than flat.** Tier 0 is the target. Tiers 1 and 2 are stretch.
The cut list is pre-ordered.

**Protected work (12.1 h, may not be cut):** B04 report intake with transactional outbox,
B05 spatio-temporal clustering, B06 confidence with time decay, B09 outbox worker with
idempotency keys.

**Still no code.** Correct at this stage.

### Unresolved

1. **Hours remaining on the clock is still unknown.** This is the one input needed to pick a
   tier and produce a concrete hour-by-hour schedule. Everything else is ready.
2. **Sleep is not modelled.** It must be subtracted from the remaining clock before the fit
   table in `06-effort-estimation.md` §5 is applied.
3. Clustering parameters still unset — distance limit and time window. Provisional: 300 m and
   30 minutes, varying by incident type. Flooding needs a wider radius than a collision.
4. Reputation formula still unspecified. Tier 0 uses a fixed reporter weight, so this can wait,
   but the simplification must go in the debt register when taken.
5. Hosting accounts on Render, Neon and Vercel assumed to exist — **verify before B01**, since
   the whole schedule depends on deploying on day one.
6. No student ID or project title recorded for the submission package.

### Next actions, in order

1. **Confirm hours remaining** → select tier → produce the hour-by-hour schedule
2. Verify Render, Neon and Vercel accounts work *before* anything else
3. B01: scaffold and deploy an empty application immediately — this retires the largest risk
4. Write the SRS (can run in parallel with the build, and reuses §5 and §7 of the scope doc)
5. Open `07-technical-debt.md` **before** the first shortcut is taken
6. Design diagrams: architecture, use case, class, sequence for report→notification, ER
7. Then build in this order: data model → report intake with outbox → clustering → confidence
   → outbox worker → dispatch queue → page
8. Property tests written **alongside** the clustering work, not after

---

## 12 August 2026 — Session 1: Project selection, scope, documentation set

### What happened

Worked through project selection from a standing start.

Reviewed the exam paper and all six course session decks (Introduction, Requirements
Engineering, Technical Debt, Program Evolution Dynamics, Software Design & Architecture,
Software Effort Estimation). Established the critical fact about the mark scheme:
**implementation is 10 of 50 marks, and the surrounding process is 40.** Every decision since
has followed from that.

Considered and set aside several candidate projects: a savings-group ledger, a bitemporal
trotro fare authority, road works conflict coordination, a station queue manager, and a
transport settlement ledger. Author's stated interests — urban congestion and stranded
commuters — pointed to the current choice.

Received the author's own written brief (`docs/00-original-brief.txt`) and reviewed it. The
brief described roughly seven distinct products. Cut it to one.

Wrote the full documentation set.

### Where things stand

**Project: Nkwanta** — road incident reporting and dispatch for urban Ghana. Road users
report what is blocking traffic; the system works out which reports describe the same event,
scores how believable it is, warns commuters heading that way, and queues a job for the
police or a traffic warden.

**Primary actor:** traffic control officer (MTTD). Commuters are the sensor network.

**Advanced concept:** an event-driven pipeline. Reports are permanent, unchangeable records.
Incidents are calculated from them by grouping reports close in place and time, weighted by
reporter reputation and faded out as they age. Saving a report and queuing its notifications
happen in one database transaction so a crash cannot lose one without the other. Notifications
carry unique keys so a retry cannot warn anyone twice. A circuit breaker protects against a
failing SMS gateway.

**The property that must hold:** the order reports arrive in must not change the final result.
This is provable with property-based tests, and is the centrepiece of the testing section.

**Stack decided:** Python / FastAPI / PostgreSQL with PostGIS / React with MapLibre / pytest
with Hypothesis. Render + Neon + Vercel.

**Scope frozen at nine features.** Ride-sharing, transport subscriptions, real emergency
dispatch, fare adjudication and turn-by-turn rerouting are all deliberately excluded and
recorded in the backlog.

**Documentation complete:**

| File | Contents |
|---|---|
| `CLAUDE.md` | Working rules for future sessions |
| `docs/00-original-brief.txt` | Author's own words, unedited |
| `docs/01-exam-requirements.md` | Exam digest and mark scheme analysis |
| `docs/02-problem-and-scope.md` | Problem, users, in/out decisions, NFRs, backlog |
| `docs/03-glossary.md` | Every technical term in plain English |
| `docs/04-advanced-concept.md` | The concept explained without jargon |
| `docs/05-decision-log.md` | Eight dated decisions with reasoning |

**No code written yet.** This is correct and deliberate — the exam paper states explicitly
that implementation must not begin until requirements and estimation are done, and allocates
the first 12 of 48 hours to that work.

### Unresolved

1. **The 48-hour clock has not started.** Nothing here is time-bound yet. Confirm the actual
   examination window before beginning.
2. **Effort estimation not yet done.** Use Case Points is the intended technique. This is the
   next substantive piece of work and it may force the scope down further. If it does, that
   is a good outcome, not a setback — the paper explicitly asks how the estimate shaped scope.
3. **Clustering parameters undecided.** The distance limit and time window are the two most
   important numbers in the system and there is no real data to tune them against. Likely
   starting point: 300 m and 30 minutes, varying by incident type. Flooding should probably
   use a wider radius than a collision.
4. **Reputation formula not specified.** Needs a concrete, defensible calculation, not a vague
   intention.
5. **No student ID or project title recorded** for the submission package.
6. **Seed data needed** for the demonstration. Around 20 real Accra junctions and corridors,
   plus enough plausible reports for the dispatch queue to look alive.

### Next actions, in order

1. Confirm the examination window and start time
2. Perform Use Case Points estimation → adjust scope if required → record as a decision
3. Write the SRS: functional requirements, the NFRs already drafted, MoSCoW table
4. Design: architecture diagram, use case diagram, class diagram for the report/incident
   core, sequence diagram for report submission through to notification, ER diagram
5. Fix the clustering parameters and the reputation formula, with written justification
6. Open the technical debt register **before** coding starts and add to it continuously
7. Begin implementation: data model → report intake with outbox → clustering consumer →
   confidence scoring → dispatch queue → map → notifications
8. Property tests alongside the clustering work, not after it

### Notes for whoever picks this up

- Read `CLAUDE.md` first. The five hard rules there exist for good reasons.
- Do not add features. The cut list is a decision, not an oversight, and it is worth marks.
- Record technical debt the moment it is created. Debt reconstructed on the final evening
  reads as invented, and it is worth 6 marks — more than design, more than testing.
- Plain language before jargon in every document. If a technical term appears anywhere and
  is not in `docs/03-glossary.md`, that is a documentation bug.
- The viva matters. Do not include anything that cannot be explained from first principles.

---

## Template for new entries

```
## <date> — Session N: <short title>

### What happened

### Where things stand

### Unresolved

### Next actions, in order
```
