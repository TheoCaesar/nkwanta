# Decision Log

*Every significant choice, dated, with the alternatives considered and the reason.*

Newest entries at the top. **Never edit an old entry.** If a decision is reversed, add a new
entry that supersedes it and mark the old one.

Format: what was decided, what else was considered, why, and what it costs.

---

## 13 August 2026 — B08 lifecycle and reputation

### D-025 — Reputation is a Beta posterior, not a success ratio

**Decided:** `reputation = (confirmed + 2) / (confirmed + contradicted + 4)`, floored at
0.02 and capped at 0.98. Updated only when an incident is resolved, once per reporter
regardless of how many reports they filed.

**Considered:** a plain success ratio; a fixed increment per outcome; leaving reputation
static as it had been.

**Why:** A plain ratio gives 1.0 after one confirmed report and 0.0 after one
contradiction. The first is an attack — file one true report, become fully trusted, then
fabricate. The second is unjust, since a road can genuinely clear before a warden
arrives. The prior removes both: one confirmation moves a new account from 0.50 to 0.60,
and reaching 0.9 takes roughly eighteen.

The floor exists because a reporter at exactly zero could never recover — every report
would carry zero weight, so none could ever be confirmed. A trap with no exit.

Counting distinct reporters rather than reports stops spamming from being the fastest
route to a high reputation.

**Costs.** The prior weight of 2 is another constant fitted to no data (TD-04). Trust is
lost faster than it is gained by construction, which is intended — the cost of a false
report must exceed the benefit of a true one — but it does mean an unlucky reporter is
penalised for a road that cleared before anyone arrived.

---

### D-024 — The lifecycle is a table of rules, not checks in handlers

**Decided:** Legal transitions live in one dictionary keyed by action, each entry naming
the states it may start from, the state it produces and the roles permitted. Anything
absent is refused.

**Considered:** conditional checks inside each route handler, which is the usual approach.

**Why:** Scattered checks are how the third handler someone adds becomes the one that
forgets. A table makes illegal moves unrepresentable rather than merely guarded, and it
makes the machine readable in one screen — a state machine you have to reconstruct from
five handlers is one nobody will reason about correctly.

The same table drives the interface through `allowed_actions`, so a button that would be
refused is never offered. A property test asserts the two agree for every combination of
state, action and role.

Two constraints are worth stating separately because they encode policy rather than
mechanics. **An unverified incident cannot be assigned** — otherwise the escalation
threshold is decoration. **An incident nobody was sent to cannot be resolved** —
otherwise the queue can be cleared by wishful thinking, and resolution stops being usable
as evidence about the reporters.

**Costs.** One more module, and the per-incident check that a warden may only resolve
what they were assigned lives in the service rather than the table, because it depends on
the specific incident rather than the state. That split is a small inconsistency and is
documented where it occurs.

---

## 13 August 2026 — B06 confidence

### D-023 — Confidence combines evidence with noisy-OR, not a sum

**Decided:** An incident's confidence is `1 − ∏(1 − wᵢ)`, where each report's weight is
`reputation × decay(age) × evidence_strength`. Evidence strength is capped at 0.45 so no
single report can ever reach the escalation threshold alone.

**Considered:** summing weights and clamping to 1; taking the maximum weight; a simple
count of corroborating reports.

**Why:** Summing is wrong twice — it exceeds 1, and it treats the hundredth report as
worth as much as the second, when in reality the first independent confirmation changes
your mind and the fiftieth changes nothing. Clamping would paper over the first problem
and a model that needs clamping to stay legal has stopped meaning anything. Taking the
maximum discards corroboration entirely, which is the one thing the system exists to
measure. A plain count ignores reporter reliability, so a discredited account would count
the same as a proven one.

Noisy-OR has a probabilistic reading — the chance at least one reporter is right — and
yields bounded, monotonic and saturating behaviour with no clamping. Because
multiplication is commutative it is also order-independent, matching the guarantee made
by clustering.

The 0.45 cap is what forces corroboration: with it, even a perfectly trusted reporter
alone scores 0.427 against a 0.70 threshold, so summoning police always takes more than
one person.

**Costs.** Noisy-OR assumes independence and reports are not independent — six people in
one jam are one event seen six times. Confidence is therefore systematically overstated
for crowds, and the bias runs towards over-confidence, which is the more dangerous
direction. Recorded as **TD-15** with the direction of the error stated and two proposed
mitigations. Every constant is a guess fitted to no data (**TD-04**), which is why they
are environment variables rather than literals.

---

## 13 August 2026 — B05 clustering

### D-022 — Test data is generated around hotspots, not uniformly

**Decided:** The Hypothesis generator for clustering draws a few hotspot locations and
scatters reports around them, jittered by up to twice the clustering radius. It does not
draw reports uniformly across Accra.

**Considered:** uniform generation across the bounding box, which is the obvious first
implementation and was the original one.

**Why:** Uniform generation was measured and found to be **useless**. Across the Accra
bounding box — roughly 22 km by 28 km — with at most 25 reports and a 300 m radius, only
**1 generated set in 300** contained any merge at all.

Every property passed. That is the problem, not the reassurance: they were passing over
collections of singleton clusters, where order-independence is trivially true and proves
nothing. A test that passes for the wrong reason is worse than one that fails, because
it buys confidence it has not earned.

Hotspot generation also matches reality — real reports arrive around real events, not
scattered evenly over a city.

**Guarded by** `test_the_generator_actually_produces_merges`, which asserts more than
half of generated sets contain a genuine merge, so the suite cannot silently become
decorative again.

**Costs.** The generator is more complex than a uniform one, and the property suite runs
in about 30 seconds rather than 4. Both are worth it for tests that actually test.

---

### D-021 — Test intensity is a profile, not a hard-coded number

**Decided:** Hypothesis example counts come from named profiles in `tests/conftest.py` —
`dev` at 50, `default` at 150, `thorough` at 1000 — selected by the `HYPOTHESIS_PROFILE`
environment variable.

**Considered:** a single hard-coded `max_examples`.

**Why:** Iterating on a failure wants fast feedback; producing evidence for the testing
report wants thoroughness. One fixed number forces a choice between them and is wrong
half the time. Profiles let the same tests serve both without editing.

All profiles disable the per-example deadline: clustering is O(n²) in the size of a
generated set, so a large set can legitimately exceed Hypothesis's default 200 ms without
anything being wrong. A deadline there would flag slow *data*, not slow code.

**Costs.** One more thing to explain, and a reader who runs plain `pytest` sees 150
examples rather than the 1000 quoted in the testing report. The command is stated
alongside the figure wherever it appears.

---

### D-020 — Clustering by connected components, not incremental assignment

**Decided:** Reports are grouped by building a graph — an edge between two reports of the
same type, within the distance limit and the time window — and taking its connected
components, computed with union-find.

**Considered:** incremental assignment, where each arriving report joins the nearest
existing incident or starts a new one. This is the obvious approach and what most
implementations do.

**Why:** Incremental assignment is **order-dependent**, which breaks the one property the
whole system is built on. The counter-example is three reports in a line 200 m apart with
a 300 m radius: arriving A, B, C gives one incident; arriving A, C, B gives two, because
C starts its own before B arrives to bridge them. The flaw is not the tie-break — it is
that incremental assignment consults "what already exists", and that depends on order.

Connected components have no prior state to consult, and a graph's components provably do
not depend on the order edges were added. The linking rule is symmetric, which is
load-bearing: an asymmetric rule would make the graph directed and the argument would
collapse.

A related subtlety was found while testing: floating-point addition is not associative,
so summing centroid coordinates in different orders differed in the last bit. Rather than
weaken the property test to a tolerance — which would have let order matter a little —
the centroid sums in id order, making it bit-for-bit reproducible.

**Costs.** Two, both recorded on the debt register rather than hidden. Single linkage
**chains**: a line of reports each 250 m apart merges into one long incident (TD-13). And
the pairwise comparison is O(n²) within each type bucket (TD-14). Complete linkage and
DBSCAN both address chaining but cost more than they fix here — complete linkage
fragments genuine incidents spanning a junction, and DBSCAN introduces parameters as
unvalidated as the two already present.

---

## 13 August 2026 — scope expansion, deadline extended by 8 hours

### D-019 — Media stored in the database, not object storage

**Decided:** Photos and voice notes are stored as binary columns in PostgreSQL, capped
at 250 KB per image and 500 KB per audio clip, with client-side downscaling before
upload.

**Considered:** Cloudflare R2, Cloudinary, Supabase storage — all have usable free
tiers.

**Why:** Every one of them is a fourth account, a fourth set of credentials, and a
fourth thing that can fail on deploy day. Neon's 0.5 GB holds roughly 2,000 capped
attachments, which is far more than a demonstration needs. The trade buys simplicity at
exactly the point in the schedule where a new integration failure would hurt most.

**Costs.** This is the wrong answer at any real scale: database backups balloon, and
binary in rows competes with the query workload for buffer cache. Recorded as debt with
the real fix named — object storage with presigned URLs, so the API never proxies bytes
at all.

---

### D-018 — Voice notes answer NFR-3 rather than decorating it

**Decided:** Voice note reporting is in scope, and is the designated answer to NFR-3.

**Why:** NFR-3 states the driver-facing view is passive and read-only, with no typing
while driving. Until now that was a constraint with no corresponding feature — the SRS
said what the system would not do without saying how a driver reports at all. Voice
input closes that gap: hold, speak, release.

This converts a likely viva concession into a designed answer. It also happens to suit
the user base better than typing does, independent of safety.

**Costs.** Audio storage, playback in the officer view, and a browser permission prompt.
Shares roughly 70% of its pipeline with photo evidence, so the pair costs less than the
sum of the parts.

---

### D-017 — Six enhancements accepted; the deliverable is no longer Tier 0

**Decided:** Build, in order — rich seed data, the Tier 1 officer workflow and lifecycle
state machine, voice notes, corridor subscriptions and commuter advisory, photo
evidence, and the circuit breaker.

**Considered:** holding the Tier 0 line agreed in D-009.

**Why:** Two things changed. The submission deadline moved out by 8 hours, and the
observed build rate is far above the bottom-up estimate's assumption — B01 and B02 were
budgeted at roughly 6 hours and took well under one. The 27.8-hour ceiling in
`06-effort-estimation.md` was calibrated against an assumption that no longer holds.

**What is now the binding constraint.** Not hours — **viva defensibility**. Rule 10
permits an oral examination on authorship and understanding, and code that cannot be
explained is worth less than absent code. Accordingly a plain-language explainer is
written for every module as it is built, in `docs/explainers/`. That is the throttle on
scope now, and it is a better one than the clock.

**Costs.** More surface to understand, more debt to track, and the estimation document
now describes a plan that was deliberately exceeded. That last point is recorded rather
than hidden: an estimate that was revised when its assumptions broke is a better
artefact than one quietly rewritten to match the outcome.

---

### D-016 — Warden added as a fourth role; no "driver" role

**Decided:** Roles are commuter, warden, officer, admin. There is no driver role.

**Why (warden):** The Tier 1 workflow needs both ends of the dispatch loop. A
control-room officer decides who goes; a field warden goes and confirms the road is
clear. Collapsing them would have made "assign" meaningless.

**Why (no driver):** A driver and a passenger have identical permissions — both report,
both receive warnings. The difference is a client-side mode, not an account type. When
the client detects motion it goes read-only and offers voice input (NFR-3). Making
driving a role would imply the server can tell who is currently driving, which it cannot
and should not.

**Costs.** Migration 0003 swaps the role CHECK constraint. This is the payoff for
D-005's choice of VARCHAR + CHECK over a native PostgreSQL enum: the change runs inside
an ordinary transaction, where `ALTER TYPE ... ADD VALUE` historically could not.

---

## 12 August 2026 — B01 build issues

### D-015 — Dependencies pinned to the first versions with CPython 3.14 wheels

**Decided:** Move every pin forward to a version publishing a prebuilt wheel for CPython
3.14: `asyncpg` 0.30.0 → 0.31.0, `SQLAlchemy` 2.0.43 → 2.0.52, `pydantic` 2.11.7 → 2.13.4
(which pins `pydantic-core` 2.46.4), plus `fastapi`, `uvicorn`, `alembic`, `GeoAlchemy2`,
`pytest` and `hypothesis` brought to current.

**Considered:** installing Python 3.12 alongside 3.14 and building against that; asking
for the MSVC C++ build tools and a Rust toolchain to be installed.

**Why:** The development machine runs Python 3.14. Neither `asyncpg` 0.30.0 nor
`pydantic-core` 2.33.2 publishes a 3.14 wheel, so pip fell back to compiling both from
source — `asyncpg` failed on the missing MSVC C++ compiler, `pydantic-core` failed at the
Rust link step. Both alternatives cost more time than moving the pins, and installing a
compiler toolchain to build packages that ship perfectly good wheels one version later is
work for its own sake.

Availability was checked against the PyPI API rather than guessed, for every package with
a compiled extension.

**Costs.** Larger version jumps than intended mid-build — `fastapi` 0.116 → 0.141 and
`pytest` 8 → 9 are both major moves. Mitigated by re-running the full suite immediately
afterwards: 22 tests, all passing. `bcrypt` 5.0.0 needed no change because it ships a
`cp39-abi3` wheel — the stable ABI, which works on every later interpreter.

**Note for the debt register.** This is exactly the failure mode TD-10 describes: pins
were verified once, by hand, on one machine. A second machine with a different interpreter
found the gap immediately. Recorded there rather than treated as a one-off.

---

## 12 August 2026 — hosting, with 40 hours remaining

### D-014 — Render free-tier cold start accepted and disclosed

**Decided:** Deploy on Render's free tier despite the 15-minute idle spin-down and 30–60 second
wake time. Mitigated by a keep-warm ping every 10 minutes and an explicit note at the top of
`Deployment_and_Source_Links.txt`.

**Considered:** paying for a Render instance; Fly.io; Railway.

**Why:** The risk is not technical, it is a grading risk — an examiner clicks the link, waits,
and assumes the application is broken. That risk is fully addressed by disclosure and a ping,
both free. Paying to remove it would be spending money to solve a documentation problem.

**Costs:** first-load latency for anyone arriving cold. Disclosed rather than hidden.

---

### D-013 — Outbox worker runs in-process, not as a separate service

**Decided:** The outbox drainer runs as an `asyncio` background task inside the FastAPI
service rather than as an independent worker process.

**Considered:** a separate Render background worker; an external queue such as Redis.

**Why:** Render's free tier permits one service. A separate worker is a paid feature. This is a
genuine architectural compromise forced by a genuine constraint, which makes it a much better
technical debt entry than anything invented after the fact.

**Costs:** real ones, and all of them go in the debt register — the worker cannot scale
independently of the API, it dies whenever the API restarts, there is no backpressure if
reports arrive faster than it drains, and a slow gateway consumes capacity the API needs to
serve requests. Proposed resolution: extract to a separate process backed by Redis Streams.

---

### D-012 — Vercel dropped; the page is served by FastAPI

**Decided:** No separate front-end host. The single static page is served by FastAPI through
`StaticFiles`.

**Considered:** deploying the page to Vercel as originally planned.

**Why:** The front end was reduced to one static HTML page by the effort estimation. A separate
host for one page adds an account, a deployment target, a build pipeline and CORS
configuration, and returns nothing. Removing it also removes an entire class of "works locally,
broken in production" failure at the point in the schedule where that would hurt most.

**Costs:** none at this scale. If the front end ever grows into a real application, it moves
back out — recorded in the backlog.

---

## 12 August 2026 — after effort estimation

### D-011 — The concept spine is ring-fenced against all cuts

**Decided:** Tasks B04 (report intake with transactional outbox), B05 (spatio-temporal
clustering), B06 (confidence and time decay) and B09 (outbox worker with idempotency keys) may
not be cut, simplified below their stated form, or deferred. They total 12.1 hours.

**Considered:** treating everything as equally negotiable under time pressure.

**Why:** These four tasks *are* the advanced concept. Everything else in the build is
supporting structure. Under time pressure the temptation is to cut whatever is hardest, which
here would be exactly the wrong thing — it would leave a competent CRUD application with an
essay attached, and the essay would not be believed.

**Costs:** removes flexibility precisely when it will be most wanted. Accepted deliberately;
that is the point of deciding it now rather than at 3 a.m.

---

### D-010 — Ordered cut list agreed in advance

**Decided:** Six items to be cut, in a fixed order, as time requires: React app → single
static page; admin screens; circuit breaker; full reputation model; corridor subscriptions;
third property test.

**Considered:** deciding what to cut in the moment.

**Why:** Decisions made at hour 40 under fatigue are worse than decisions made at hour 12.
Fixing the order now means the cut becomes a lookup rather than a judgement call. It also
means each cut can be documented as deliberate — which is worth marks — instead of appearing
as something unfinished.

**Costs:** the circuit breaker was one of the better live demonstrations available. It moves to
the technical debt register as designed-but-not-built.

---

### D-009 — The deliverable is a vertical slice, not the product

**Decided:** The 48-hour output is explicitly a narrow-but-complete slice of the system,
described as such throughout the submission. Not a partial product, not an MVP — a slice
chosen to exercise the full architecture end to end.

**Considered:** presenting the build as a minimum viable product.

**Why:** Use Case Points puts full scope at 1,948 person-hours, roughly 40 times the
examination window; even the must-have subset is 1,391 hours. Any framing that implies the
product was attempted invites the question of why it is incomplete. Framing it as a
deliberately chosen slice invites the question of why *that* slice — which has a good answer.

**Costs:** none. This is a framing decision, and the honest framing is also the stronger one.

---

## 12 August 2026

### D-008 — Traffic control officer is the primary actor

**Decided:** The system is built around the authority's incident queue. Commuters are the
sensor network feeding it.

**Considered:** commuter-facing primary (motorists first, authorities downstream); balanced
two-sided design.

**Why:** It matches the users named in the original brief — emergency services and the police
traffic divisions. It also solves a demonstration problem: a purely commuter-facing crowd
advisory app is thin to show with no real user base, whereas a dispatch queue seeded with
test data demonstrates convincingly. A two-sided design roughly doubles the interface surface,
which the 48-hour budget will not carry.

**Costs:** the commuter experience is deliberately simpler than it would be in a real product.

---

### D-007 — Two non-functional requirements added that were not in the brief

**Decided:** NFR-3 (driver-facing view is passive and read-only) and NFR-4 (reported parties
never identified, reputation floor before escalation, rate limiting).

**Considered:** leaving both implicit.

**Why:** The brief asks motorists to report hazards, which invites phone use while driving —
a road safety system must not create the hazard it exists to reduce. And it lets users report
other people to the police, which is a harassment and false-accusation vector. Both will come
up in the viva. Better to have raised them first.

**Costs:** none material. Reporting becomes passenger-first or voice-first, which is the
correct design anyway.

---

### D-006 — Ride-sharing and transport subscriptions cut from scope

**Decided:** Both excluded. Ride-sharing becomes the headline Future Evolution item.

**Considered:** including a minimal ride-matching feature.

**Why:** Ride-sharing is an entire second product — matching, payments, identity verification,
passenger safety, insurance, liability — and shares nothing with the report pipeline.
Subscriptions are a third. Including either would consume the implementation budget and leave
the advanced concept half-built. The mark scheme rewards a small system engineered well over
a large one delivered thin.

**Costs:** loses the part of the brief the author was most personally attached to. Mitigated
by making it the lead item in Future Evolution, which is itself worth 3 marks.

---

### D-005 — Five brief features unified into one report pipeline

**Decided:** Traffic impediments, accidents, maintenance reports, road-condition reviews and
signal outages are all one polymorphic report type with a type discriminator and a per-type
resolution policy.

**Considered:** building each as a separate feature with its own model and screens.

**Why:** They differ only in who acts on them, not in how they are captured, grouped or
scored. One pipeline covers most of the brief with a single well-designed core, and reduces
implementation cost by roughly two-thirds.

**Costs:** per-type behaviour must be handled through policy objects rather than separate
code paths — slightly more abstraction up front, much less code overall.

---

### D-004 — Advanced concept: event-driven pipeline with spatio-temporal corroboration

**Decided:** Reports stored as permanent immutable events; Incidents as a projection built by
a clustering consumer; reputation-weighted confidence with time decay; transactional outbox
for guaranteed processing; idempotency keys for at-least-once notification; circuit breaker
on the outbound gateway.

**Considered:**
- bitemporal fare registry (the TroTroGo concept) — strong, but a different problem domain
- spatio-temporal permit conflict detection (the ClearWay road works concept) — arguably more
  rigorous, but less connected to the author's stated interests
- constraint-solving for signal timing — highest risk, hardest to validate

**Why:** It is genuinely forced by this domain rather than bolted on. Every element answers a
real question the system must handle: which reports are the same event, is it true, what if we
crash mid-way, what if reports arrive out of order. It also yields an order-independence
property that can be *proved* with property-based testing rather than merely claimed.

**Costs:** more moving parts than a CRUD application, and the outbox worker is extra
infrastructure. Accepted as the price of the concept marks.

---

### D-003 — Stack: Python / FastAPI / PostgreSQL + PostGIS / React

**Decided:** FastAPI backend, PostgreSQL with PostGIS, SQLAlchemy and Alembic, React with
Vite and MapLibre GL, pytest with Hypothesis. Hosted on Render, Neon and Vercel.

**Considered:** Node with TypeScript; Java with Spring Boot.

**Why:** Author is fastest in Python, which matters most under a 48-hour constraint. PostGIS
handles the location queries natively. Hypothesis is the strongest property-based testing tool
available in any of the candidate stacks, and the property tests are central to the testing
marks.

**Costs:** Spring Boot would have scored marginally better on architecture presentation. Not
worth the build time.

---

### D-002 — Project selected: road incident reporting and dispatch

**Decided:** Nkwanta, from the author's stated areas of interest.

**Considered:** TroTroGo bitemporal fare authority; ClearWay road works coordination; trotro
stop and dwell management; savings-group ledger.

**Why:** Author has direct experience of the problem, which matters for the viva. Stakeholders
are real and nameable. The domain forces a genuinely interesting technical core rather than
inviting one.

---

### D-001 — Scope discipline over feature count

**Decided:** Build the smallest system that fully exercises the lifecycle, and document the
cuts.

**Why:** Implementation is 10 of 50 marks. Requirements, estimation, design, testing, debt,
documentation and evolution are 40. The paper says outright that a large commercial system is
not expected and that disciplined practice under constraint is what is assessed. Optimising
for feature count optimises against the mark scheme.

---

## Template for new entries

```
### D-0XX — <short title>

**Decided:** what was chosen.

**Considered:** what else was on the table.

**Why:** the reasoning. Reference the mark scheme where relevant.

**Costs:** what this gives up. Every real decision costs something.
```
