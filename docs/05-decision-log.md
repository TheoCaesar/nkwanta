# Decision Log

*Every significant choice, dated, with the alternatives considered and the reason.*

Newest entries at the top. **Never edit an old entry.** If a decision is reversed, add a new
entry that supersedes it and mark the old one.

Format: what was decided, what else was considered, why, and what it costs.

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
