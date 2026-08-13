# Technical Debt Register

*Opened 12 August 2026, at B01 — before the first shortcut was taken.*
*Worth 6 of the 50 marks, more than design and more than testing.*

---

## How this register is kept

**Every entry is written the moment the shortcut is taken, never reconstructed
afterwards.** Debt recorded live reads as competence. Debt invented on the final evening
reads as invented, and an examiner who has marked a hundred of these can tell the
difference immediately.

Each item records: **Debt → Cause → Impact → Priority → Proposed Resolution**, and is
classified as required by the exam paper:

| Class | Meaning |
|---|---|
| **A — Acceptable** | A reasonable trade-off. May stay for the foreseeable future. |
| **S — Scheduled** | Must be repaid, and there is a named release for it. |
| **C — Critical** | Needs attention before any real user touches the system. |

Interest rate is noted where it matters: debt that gets *worse* on its own is more
urgent than debt that merely sits there.

---

## Summary

| ID | Debt | Class | Priority | Taken at |
|---|---|---|---|---|
| TD-01 | Outbox worker runs in-process, not as a separate service | A | Medium | B01 (D-013) |
| TD-02 | No event snapshotting — replay is O(n) | A | Low | Design |
| TD-03 | Clustering parameters hardcoded and untuned | S | **High** | Design |
| TD-04 | Reputation model is an unvalidated heuristic | S | Medium | Design |
| TD-05 | Projection updated synchronously in the request path | S | Medium | Design |
| TD-06 | No backpressure or dead letter queue on the outbox | S | Medium | Design |
| TD-07 | Front end is one unbuilt static page | A | Low | Estimation (D-010) |
| TD-08 | Notification sink is log-only; no real SMS or push | A | Low | Estimation |
| TD-09 | Free-tier host sleeps after 15 minutes | A | Low | B01 (D-014) |
| TD-10 | Dependency pinning verified once, no automated audit | S | Medium | B01 |
| TD-11 | No CI pipeline — tests run only when remembered | S | Medium | B01 |
| TD-12 | Single shared database, no read replica or partitioning | A | Low | Design |
| TD-13 | Single-linkage clustering chains along a corridor | A | Medium | B05 |
| TD-14 | Clustering is O(n²) within each type bucket | S | Low | B05 |
| TD-15 | Noisy-OR assumes independent reports; crowds overstate confidence | A | Medium | B06 |
| TD-16 | Rebuild neighbourhood bound is a guess, could miss a distant merge | A | Low | B09 |
| TD-17 | Demo seed and drain endpoints exist on the production deployment | **C** | Low now, critical before real use | D |
| TD-18 | One database for development and production; no staging | S | High before real use | D |
| TD-19 | Media in the database rather than object storage | S | High under adoption | F |
| TD-20 | Client-declared audio duration is unverified | A | Low | F |
| TD-21 | Gateway can be deliberately broken on the live deployment | **C** | Low now, critical before real use | C |
| TD-22 | Stored confidence decays only when the sweep runs | A | Low | C |

Items added during B02 onward are appended in build order.

---

## TD-01 — Outbox worker runs in-process

**Debt.** The background task that drains the outbox and sends notifications runs as an
`asyncio` task inside the same process as the web API, rather than as an independent
worker service.

**Cause.** Render's free tier permits exactly one service. A separate background worker
is a paid feature, and the examination budget is zero.

**Impact.**
- The worker cannot be scaled independently of the API.
- It dies whenever the API restarts or is redeployed — mid-flight sends are retried on
  restart, which is safe only because every notification carries an idempotency key.
- A slow or hanging gateway consumes event-loop capacity the API needs to serve requests.
- One process is a single point of failure for two responsibilities.

**Priority.** Medium. It is correct at the current volume and wrong at any real volume.

**Class.** A — acceptable, and honestly forced. It would be the first thing to change on
a paid plan.

**Proposed resolution.** Extract the drainer into its own process backed by Redis
Streams. The code is already written as a self-contained coroutine with no dependency on
FastAPI's request context, specifically so that this extraction is a move rather than a
rewrite.

---

## TD-02 — No event snapshotting

**Debt.** Incidents are rebuilt by replaying every report from the beginning. There are
no periodic "state so far" markers.

**Cause.** Unnecessary at the seeded data volume, and snapshotting is roughly two hours
of work that the estimate could not accommodate.

**Impact.** Rebuild time grows linearly with the number of reports ever recorded. At a
few thousand reports this is milliseconds. At a few million it would be an outage.

**Priority.** Low now, and **it has an interest rate** — this gets worse every day the
system runs, without anyone touching it.

**Class.** A — acceptable, with a monitored trigger: revisit once report count passes
100,000.

**Proposed resolution.** Snapshot every 1,000 events; replay from the most recent
snapshot rather than from zero.

---

## TD-03 — Clustering parameters hardcoded and untuned

**Debt.** The radius (300 m) and time window (30 minutes) that decide whether two reports
describe the same event are fixed constants, chosen by reasoning rather than measurement.

**Cause.** No historical incident data exists to tune them against. None could be
obtained within the examination window.

**Impact.** This is the **most consequential unvalidated assumption in the system**. Set
too wide, two genuinely separate incidents merge and the map lies. Set too narrow, one
incident fragments into several and confidence never crosses the alert threshold, so the
police are never told. A single pair of numbers governs both failure modes, and the
correct values almost certainly differ between a dense junction like Circle and an open
stretch of the Tema Motorway.

**Priority.** **High.** It is the first thing that would be wrong in production.

**Class.** S — scheduled. Must be repaid before real users.

**Proposed resolution.** Make both configurable per incident type and per road class
(they are already read from environment variables, so this is a data change rather than a
code change). Then tune against labelled real incidents once any exist. Flooding needs a
materially wider radius than a collision.

---

## TD-22 — Stored confidence decays only when a sweep runs

**Debt.** Confidence is calculated when reports arrive and written to the incident row. It
does not decay continuously. A periodic sweep (every five minutes) fades incidents whose
newest report is more than eight half-lives old, but between sweeps the stored figure is
whatever it was when the last report landed.

**Cause.** The alternative is recomputing decay on every read, which makes the map query
expensive and makes its results depend on the moment you asked rather than on the data.

**Impact.** An incident's confidence can be **overstated by up to five minutes of decay** —
at a 45-minute half-life, about 7%. Enough to keep something marginally above a threshold
slightly longer than it should be; not enough to affect a decision anybody would make
differently.

The sweep itself is also an approximation: it uses time since the newest report rather than
recomputing the full noisy-OR. Eight half-lives is a factor of 256, so anything it clears
was genuinely below the stale threshold, but the *value it writes down* is a scaled
estimate rather than an exact recomputation.

**Priority.** Low. Both errors are small and both err towards keeping incidents alive
slightly too long, which is the safer direction.

**Class.** A — acceptable, with the magnitude of the error quantified rather than waved at.

**Worth recording:** this was invisible until the advisory was built. Decay was correct in
`confidence.py`, fully property-tested, and applied to nothing that was sitting still. A
unit-tested function can be right in isolation and unreached in practice.

**Proposed resolution.** Recompute exactly during the sweep by re-scoring from
`incident_reports`, and shorten the interval. Or move decay into the read query as a
generated expression, which PostgreSQL can index, and drop the stored column entirely.

---

## TD-21 — A gateway that can be told to fail exists in production

**Debt.** `ControllableGateway` and the `POST /admin/gateway/fail` endpoint let an
administrator deliberately break outbound delivery, and both are present on the live
deployment.

**Cause.** A circuit breaker whose behaviour cannot be shown is a paragraph in a document.
One that can be tripped live, on request, in thirty seconds, is evidence. This exists for
the demonstration, and stating that plainly is better than presenting it as resilience
engineering.

**Impact.** An administrator can disable notification delivery. Bounded — the notification
rows are still written and users still see them in the application, so nothing is lost —
but it is a switch that turns off a safety feature, on a public deployment, with a password
published in the submission.

**Priority.** Low for an examination artefact, **critical** before real use.

**Class.** C — critical, in the same sense as TD-17: it must not survive contact with real
users.

**Proposed resolution.** Register the gateway control endpoints only when
`ENVIRONMENT != "production"`, so they cannot be reached rather than merely being
protected, and default the deployed build to `LoggingGateway`.

---

## TD-19 — Media is stored in the database rather than in object storage

**Debt.** Voice notes and photographs are stored as binary columns in PostgreSQL, capped
at 512 KB and 250 KB respectively.

**Cause.** Object storage means a fourth hosting account, a fourth set of credentials and
a fourth thing that can fail on deploy day, on a project whose largest sustained risk was
deployment. Neon's 0.5 GB holds roughly a thousand capped attachments, far more than a
demonstration needs. Recorded at the time as decision D-019.

**Impact.**
- Database backups grow with media rather than with data, and restore times with them.
- Binary rows compete with the query workload for the buffer cache. *Partly mitigated*:
  attachments live in their own table, which nothing scans, so audio nobody is playing
  costs nothing. The mitigation would not exist had the bytes been columns on `reports`.
- Every playback is proxied through the API, so serving media consumes application
  capacity that should be answering requests.
- The 0.5 GB free tier becomes a hard ceiling on total uploads.

**Priority.** Low at demonstration scale, **high** with real users — this is the item
that fails first under adoption.

**Class.** S — scheduled.

**Proposed resolution.** Cloudflare R2 or equivalent, with presigned URLs so the API
never touches the bytes at all: it issues a URL, the client uploads directly, and
playback goes straight from storage. The `attachments` table keeps its metadata rows and
gains a key column in place of `data`, so the change is contained to one table and one
service module.

---

## TD-20 — Client-declared audio duration is not verified

**Debt.** `duration_seconds` on an attachment is whatever the client says it is. Nothing
decodes the file to check.

**Cause.** Verifying it means decoding audio server-side, which means `ffmpeg` or a
codec library — a substantial dependency for a value that is displayed and never acted
upon.

**Impact.** An officer could be shown "0:12" for a clip that is actually thirty seconds.
Mildly misleading, and no decision depends on it. The **size cap is the real limit**, and
that is enforced in both the upload handler and a database constraint.

**Priority.** Low.

**Class.** A — acceptable, provided nothing ever starts making decisions from this field.

**Proposed resolution.** Either decode and verify on upload, or stop storing it and read
the duration in the browser at playback time, which is where it is actually needed.

---

## TD-18 — One database serves both development and production

**Debt.** The local development environment and the deployed service point at the same
Neon database. There is no staging environment and no separate development data.

**Cause.** Neon's free tier allows more than one project, so this was avoidable — it was
not avoided because a single connection string is one less thing to configure wrongly
during a 48-hour build, and because the demonstration data needs to be visible on the
live site anyway.

**Impact.** Running the seed script locally changes what an examiner sees. A careless
migration or a stray `--reset` during development would take the live deployment with
it. There is no environment in which to test a destructive change safely, which means
destructive changes get tested in production or not at all.

**Priority.** Low for an examination artefact, **high** for anything real.

**Class.** S — scheduled.

**Proposed resolution.** A second Neon project for development, with `DATABASE_URL` in
`.env` pointing at it and only Render's environment pointing at production. Costs
nothing on the free tier; it was a time decision rather than a money one, which is worth
stating plainly rather than dressing up.

**A related bootstrap wrinkle**, recorded here because it is the same root cause:
`POST /admin/seed` requires an admin account that only the seed creates, so on a fresh
database the endpoint cannot be reached and the command-line script must run first. With
a separate development database this would have surfaced during setup rather than at
demonstration time.

---

## TD-17 — A demonstration-data endpoint exists in the production deployment

**Debt.** `POST /admin/seed` wipes and rebuilds the demonstration data, and it is present
on the live deployment. `POST /admin/drain` likewise forces the outbox worker to run.

**Cause.** Confidence decays with a 45-minute half-life, so seeded data is invisible
within a few hours. Refreshing it before a demonstration or viva has to be possible, and
doing it from a browser is markedly more reliable than asking someone to find a terminal
with the right environment configured.

**Impact.** An endpoint that deletes data exists on a public deployment. It is
admin-only, and the admin password is published in the submission — which is fine for an
examination artefact and would be unacceptable anywhere else. `clear_demo_data` only
removes rows whose identifiers the seed module generates, so real reports would survive,
but that is a property of the current implementation rather than a guarantee.

**Priority.** Low here, **critical** before any real use.

**Class.** C — critical, in the sense that it must not survive contact with real users.
Acceptable only because this deployment exists to be marked.

**Proposed resolution.** Remove both endpoints from any non-examination build, gated on
`ENVIRONMENT != "production"` at router registration so they cannot be reached at all
rather than merely being protected. Seeding then happens only through
`scripts/seed_demo.py`, run deliberately by someone with database access.

---

## TD-16 — The rebuild neighbourhood is a heuristic, not a guarantee

**Debt.** When a report arrives, the projector rebuilds incidents within three times the
clustering radius and time window, then expands to whole incidents. Three is a chosen
number, not a derived one.

**Cause.** Rebuilding the entire map on every report would be correct and unusably slow.
Some bound was needed and there is no data to derive one from.

**Impact.** Single-linkage clustering chains (TD-13), so a sufficiently long chain of
reports could in principle link two incidents that lie outside the neighbourhood of each
other. The rebuild would then miss a merge that a full recomputation would have found.
The result would be two adjacent incidents where there should be one — visible on the
map, and not corrupting anything, but wrong.

**Priority.** Low. It needs a chain of reports each within 300 m of the next, spanning
more than 900 m, all within 90 minutes. Plausible on a congested corridor; not reachable
with seeded data.

**Class.** A — acceptable, with the failure mode understood and bounded.

**Proposed resolution.** Expand the neighbourhood iteratively — fetch, cluster, and if
any cluster touches the edge of the fetched region, widen and repeat until it does not.
That converges and removes the guess entirely. It was not attempted under time pressure
because it needs care to stay order-independent.

---

## TD-15 — Noisy-OR assumes reports are independent, and they are not

**Debt.** Confidence combines evidence with noisy-OR, `1 − ∏(1 − wᵢ)`, which treats each
report as an independent observation.

**Cause.** It is the standard formulation, it has the four structural properties the
design needs — bounded, monotonic, saturating, order-independent — and no alternative
could be calibrated without data that does not exist.

**Impact.** **Confidence is systematically overstated when reports come from a crowd.**
Six people stuck in the same jam are not six independent observations; they are one
event observed six times, by people who may have seen each other's hazard lights, heard
the same radio bulletin, or seen the incident already on this map. The bias runs one way
only — towards over-confidence — which is the more dangerous direction, since it means
escalating to police on thinner evidence than the number suggests.

**Priority.** Medium. Structural rather than a bug, and the direction of the error is
known.

**Class.** A — acceptable, with the bias documented rather than hidden.

**Proposed resolution.** Two measures, both needing data first. Discount reports arriving
after an incident becomes publicly visible on the map, since those reporters may be
echoing rather than observing. And weight by the spatial spread of reporters — six
reports from six different approach roads genuinely are more independent than six from
one queue, and the geometry to measure that is already stored.

---

## TD-13 — Single-linkage clustering chains

**Debt.** Reports are grouped as connected components of a "near in space and time"
graph. A line of reports each 250 m from the next merges into one incident even if the
two ends are kilometres apart.

**Cause.** Single linkage is inherent to the connected-components approach, and that
approach was chosen because it is provably order-independent — the property the whole
design exists to protect.

**Impact.** On a long congested corridor, several genuinely separate incidents could
merge into one enormous one. The map would show a single pin where a commuter needs
three, and the confidence score would be meaningless because it would aggregate
unrelated events.

**Priority.** Medium. Not reachable with seeded data; likely on a real Accra corridor at
rush hour, which is exactly when the system matters.

**Class.** A — acceptable for now, with the trade explicitly understood.

**Alternatives considered and rejected.** Complete linkage resists chaining but is far
more expensive and fragments genuine incidents spanning a junction. DBSCAN handles
chaining well but reintroduces parameters as unvalidated as the two already present
(TD-03).

**Proposed resolution.** A maximum-diameter cap applied as a post-pass. It must be a
post-pass: enforcing a cap *during* merging would reintroduce order dependence and break
the property the design is built on. The post-pass itself must be order-independent —
splitting on a deterministic criterion such as the widest pair.

---

## TD-14 — Clustering is O(n²) within each type and time bucket

**Debt.** Every pair of same-type reports is compared. With n reports that is n(n−1)/2
distance calculations.

**Cause.** Simple, obviously correct, and fast enough at demonstration scale. A spatial
index would have been premature optimisation before any load existed.

**Impact.** Fine at hundreds of reports, poor at tens of thousands. Recomputing over a
full day of citywide reports would become noticeably slow.

**Priority.** Low now. **Has an interest rate** — cost grows quadratically with adoption,
so it worsens fastest exactly when the system succeeds.

**Class.** S — scheduled.

**Proposed resolution.** Two steps, neither of which changes the result. First, bucket by
time window so only temporally-adjacent reports are compared. Second, use the PostGIS
GiST index to fetch spatial candidates rather than testing every pair — the index already
exists for this reason. The connected-components structure is unaffected, so the
order-independence property survives untouched.

---

## TD-04 — Reputation model is an unvalidated heuristic

**Debt.** The formula converting a reporter's history into a trust weight is a reasoned
guess, not a model fitted to outcomes.

**Cause.** No historical data. Fitting a real model is out of scope for 48 hours and
arguably out of scope for software engineering.

**Impact.** Accuracy is unknown. The system may over-trust a lucky new reporter or
under-trust a reliable one. Because reputation gates escalation to authorities, errors
here have real consequences in both directions.

**Priority.** Medium.

**Class.** S — scheduled.

**Proposed resolution.** Log every prediction alongside the eventual confirmed outcome
from day one, so that a model can be fitted later against real data. Logging is cheap now
and the data is impossible to recover retrospectively.

---

## TD-05 — Projection updated synchronously in the request path

**Debt.** Clustering runs during the HTTP request that submits a report, rather than in
the background.

**Cause.** Simpler, and fast enough at current volume. Doing it properly needs the
separate worker that TD-01 also blocks on.

**Impact.** Report submission is slower than it needs to be, and submission latency now
depends on how many nearby reports already exist — which is exactly backwards, since the
system is slowest precisely when an incident is busiest and reports matter most.

**Priority.** Medium.

**Class.** S — scheduled. Resolves naturally alongside TD-01.

**Proposed resolution.** Move clustering behind the event bus so submission returns as
soon as the report and its outbox row are committed.

---

## TD-06 — No backpressure or dead letter queue

**Debt.** The outbox drainer has no way to signal that it is falling behind, and messages
that fail repeatedly are retried indefinitely rather than parked for inspection.

**Cause.** Not reachable at expected volumes, and it is a meaningful amount of work.

**Impact.** During a citywide event — the exact scenario the system exists for — reports
could arrive faster than the drainer clears them, with no signal until the queue is
visibly enormous. A permanently failing message retries forever, consuming capacity.

**Priority.** Medium. Note the irony: the failure mode appears exactly when the system is
most needed.

**Class.** S — scheduled.

**Proposed resolution.** Bounded queue with a depth metric and alerting; move messages to
a dead letter table after five failed attempts.

---

## TD-07 — Front end is a single unbuilt static page

**Debt.** No React application, no build pipeline, no component structure. One hand-written
HTML file.

**Cause.** The effort estimate reduced the interface budget to 1.2 hours (D-010). A
separate front end would have cost roughly 6 hours and displaced protected work.

**Impact.** Limited interactivity, no offline capability, no reusable components, and
styling is inline. Adding a second page means copy-paste.

**Priority.** Low. It carries almost no marks and the API documentation serves as a real
interface.

**Class.** A — acceptable, and deliberately chosen rather than run out of time on.

**Proposed resolution.** React with Vite, deployed separately, once the interface needs
more than one page.

---

## TD-08 — Notification sink is log-only

**Debt.** Notifications are written to the application log rather than sent by SMS or
push.

**Cause.** Every gateway with real reach in Ghana requires payment and identity
verification, neither achievable inside the examination window.

**Impact.** The delivery path is unproven against a real provider. Rate limits, encoding
and provider-specific failure modes are all untested.

**Priority.** Low for the submission, **blocking** for any real deployment.

**Class.** A — acceptable for an examination artefact.

**Mitigation already in place.** The outbox, idempotency keys and retry logic are all
real and fully exercised against the log sink. Only the final adapter is a stub, and it
sits behind an interface precisely so it can be swapped without touching anything else.

**Proposed resolution.** Implement an SMS adapter against the existing interface. Add the
circuit breaker at the same time — see TD deferred item from D-010.

---

## TD-09 — Free-tier host sleeps after 15 minutes

**Debt.** Render free services spin down after 15 minutes of inactivity and take 30–60
seconds to wake.

**Cause.** Zero budget.

**Impact.** Primarily a **grading** risk, not a technical one: an examiner clicks the
link, waits, and concludes the application is broken.

**Priority.** Low technically, high in consequence, and fully mitigated.

**Class.** A — acceptable.

**Mitigation.** A keep-warm ping every 10 minutes against `/health`, which deliberately
does not touch the database so it costs no Neon compute. Plus an explicit note to the
examiner, because a ping can lapse and a sentence cannot.

---

## TD-10 — Dependencies pinned but not audited

**Debt.** Versions are pinned exactly, and were verified to install and pass tests once,
by hand. There is no automated vulnerability scanning or update process.

**Cause.** No time for tooling.

**Impact.** A vulnerability disclosed in any pinned package goes unnoticed. Pinning
prevents surprise breakage and equally prevents surprise fixes.

**Priority.** Medium. Grows over time.

**Class.** S — scheduled.

**Proposed resolution.** Enable Dependabot on the repository; add `pip-audit` to CI when
CI exists (TD-11).

**Repaid twice at B01, both times by running the thing rather than trusting it:**

1. `passlib[bcrypt]` was broken against bcrypt 5.0 — passlib 1.7.4 reads
   `bcrypt.__about__.__version__`, removed in bcrypt 4.1. passlib removed; bcrypt now used
   directly.
2. The original pins had **no wheels for CPython 3.14**, the interpreter on the
   development machine. pip fell back to compiling `asyncpg` (needs MSVC) and
   `pydantic-core` (needs Rust) from source, and both failed. Pins moved forward to the
   first versions publishing 3.14 wheels — see D-015.

**This is the case for the debt, not against it.** Pinning was verified once, by hand, on
one machine. A second machine with a different interpreter found the gap in minutes. The
register said the risk was "a vulnerability goes unnoticed"; the realised risk was instead
"the project does not install at all on a supported Python." Automated resolution testing
across interpreter versions would have caught it, and that is what the proposed resolution
should cover — not just vulnerability scanning.

---

## TD-11 — No continuous integration

**Debt.** Tests run when someone remembers to run them. Nothing blocks a broken push.

**Cause.** Roughly 40 minutes of work that the estimate could not fit, against a build
budget already 6% short.

**Impact.** A regression can reach the deployed application. On a solo project at this
timescale the window is small, but the property tests are the most valuable thing in the
repository and nothing currently guarantees they were run.

**Priority.** Medium.

**Class.** S — scheduled.

**Proposed resolution.** A GitHub Actions workflow running `pytest` on push. Roughly
fifteen lines. This is the highest value-per-minute item on the register and should be
taken first if any buffer survives.

---

## TD-12 — Single database, no replication or partitioning

**Debt.** One Neon instance, no read replica, no partitioning of the reports table.

**Cause.** Correct at this scale, and the free tier offers nothing else.

**Impact.** No horizontal read scaling; the reports table grows without bound.

**Priority.** Low.

**Class.** A — acceptable.

**Proposed resolution.** Partition reports by month once the table passes ten million
rows; add a read replica when map queries begin to affect write latency.

---

## Repayment plan

Ordered by value per hour of work, not by severity — which is how repayment actually gets
prioritised in practice.

| Order | Item | Effort | Why here |
|---:|---|---|---|
| 1 | TD-11 CI pipeline | 0.7 h | Protects everything else. Cheapest insurance available. |
| 2 | TD-03 Tunable clustering parameters | 1.5 h | Highest-consequence unknown in the system |
| 3 | TD-01 + TD-05 Extract the worker | 4 h | Two items, one fix |
| 4 | TD-08 Real SMS adapter + circuit breaker | 3 h | Blocking for any real deployment |
| 5 | TD-06 Backpressure + dead letter queue | 3 h | Fails exactly when the system matters most |
| 6 | TD-04 Fit the reputation model | — | Blocked on data that must be logged from day one |
| 7 | TD-02 Snapshotting | 2 h | Deferred until 100,000 reports |

**Total identified debt: roughly 14 hours** against a build of roughly 22. That ratio is
worth stating plainly in the submission — it is normal for a time-boxed prototype, and
being able to quantify it is the point of keeping the register.
