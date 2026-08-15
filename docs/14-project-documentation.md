# Project Documentation

**Nkwanta: A Road Incident Reporting and Dispatch System for Urban Ghana**

*Theophilus Caesar · 22424543 · CSCD602 Advanced Software Engineering*
*University of Ghana · Examiner: Prof. Solomon Mensah · 14 August 2026*

---

## How to read this document

This is the consolidating document. It covers all nineteen required sections in order.

Where a section has a dedicated document, this one gives the substance and points to it
rather than duplicating it — a duplicated section is a section that will disagree with its
original after the next change. Nothing here depends on reading the others.

| Referenced as | Full document |
|---|---|
| SRS | `10-srs.md` |
| Design | `09-system-design.md` |
| Testing | `11-testing-report.md` |
| Debt | `08-technical-debt.md` |
| Estimation | `06-effort-estimation.md` |
| Evolution | `12-maintenance-and-evolution.md` |
| Manual | `13-user-manual.md` |
| Decisions | `05-decision-log.md` (`D-nnn`) |

---

## 1. Title

**Nkwanta: A Road Incident Reporting and Dispatch System for Urban Ghana.**

*Nkwanta* is Twi for *junction* — the place where roads meet, and where they block.

---

## 2. Problem statement

When a road in Accra is blocked, the information exists — dozens of people are sitting in
it — and there is no path from those people to anyone who can act. A commuter three
kilometres back learns about it by arriving. A traffic control officer learns about it from
scattered phone calls, with no way to tell six calls about one accident from six separate
accidents.

Two failures, and they are the same failure: **the information is present and unusable.**

Three things make it hard rather than merely tedious:

1. **Reports arrive in no controlled order**, from phones with different signal, some twice.
2. **Not every report is true.** The system lets people report other people to the police,
   which makes it a harassment vector unless something defends against it.
3. **A warning that arrives late is worth nothing**, so the pipeline cannot be allowed to
   silently drop work.

---

## 3. Aim and objectives

**Aim.** Turn scattered reports from road users into a single, believable, actionable
picture of what is blocking the roads — and put that picture in front of both the commuter
about to set out and the officer who can send someone.

**Objectives.**

| # | Objective | Where it is met |
|---|---|---|
| 1 | Capture typed, located, timestamped reports from ordinary road users, safely and offline-tolerantly | SRS §3.2 |
| 2 | Group reports describing one real event, **independent of arrival order** | SRS FR-19, FR-20 |
| 3 | Score believability from reporter track record, decaying with age | SRS FR-21–FR-24 |
| 4 | Warn commuters on affected routes, exactly once each | SRS FR-35–FR-40 |
| 5 | Give officers a ranked queue whose scores can be interrogated, not just read | SRS FR-29 |
| 6 | Defend against false reporting without exposing either party | NFR-04, NFR-04a |
| 7 | Guarantee that saving a report and queueing its warnings cannot come apart | SRS FR-12 |

---

## 4. Stakeholders

| Stakeholder | Interest | Influence on the design |
|---|---|---|
| **Commuters and motorists** | Know before setting out | The public map needs no account; the driver-facing view is read-only (NFR-03) |
| **Traffic control officers (MTTD)** | A queue worth acting on | **Primary actor.** The dispatch queue is the core screen |
| **Traffic wardens** | Clear instructions, and to be believed | Resolution feeds reputation — the loop closes here |
| **Reported parties** | Not to be publicly accused | NFR-04: never identified. No field records them |
| **Reporters** | Not to be exposed for reporting | NFR-04a: voice private by default, withdrawable (D-029) |
| **Road maintenance agencies** | Structured defect reports | Report type 6, no separate workflow |
| **Administrators** | Oversight, abuse control | Roles assigned only by an admin; nobody self-registers as police |

**The primary actor is the officer, not the commuter.** Commuters are the sensor network;
the officer is the person whose job the system exists to do. That choice decides which
screen is the core one, and it makes the system demonstrable without a large user base.

---

## 5. Requirements analysis

The original brief was a wish-list containing at least three separate products. The
analysis that mattered was **unification**:

> Five items — traffic impediments, accidents, maintenance reports, road-condition reviews,
> and signal outages needing a warden — collapsed into **one report pipeline differentiated
> only by type.** They differ in who acts on them, not in how they are captured, grouped or
> scored.

This is the single most important requirements decision in the project. It converted a
sprawling brief into one well-engineered core, and it is what made the advanced concept
affordable inside 48 hours.

**Prioritisation** used MoSCoW, and the cuts are recorded with reasoning (SRS §6). Four
Won't-haves — ride-sharing, subscription transport, real emergency dispatch, fare
adjudication — were each cut for a stated reason, not for lack of time. Ride-sharing alone
is a second product: matching, payments, identity, passenger safety, liability, sharing
nothing with the report pipeline.

Two requirements arose from *reviewing* the brief rather than from the brief itself, and
both are load-bearing: **NFR-03** (the system must not create the hazard it exists to
reduce) and **NFR-04** (the reported party is never identified). A later review found
NFR-04 conflated protecting the accused with protecting the accuser, and **NFR-04a** was
added — see D-029.

---

## 6. Software Requirements Specification

**Full document: `10-srs.md`.**

Fifty numbered functional requirements, each with a MoSCoW priority, a status, the module
implementing it and the test verifying it. Seven non-functional requirements. Four use
cases with alternative flows.

| Group | Requirements |
|---|---|
| Accounts and roles | FR-01 – FR-08 |
| Reporting | FR-09 – FR-18 |
| Grouping, scoring, lifecycle | FR-19 – FR-28 |
| Dispatch and reputation | FR-29 – FR-34 |
| Warning commuters | FR-35 – FR-40 |
| Public map and privacy | FR-41 – FR-46 |
| Administration and resilience | FR-47 – FR-50 |

**49 of 50 implemented; FR-40 (clearance) is declared Partial.** Six of seven
non-functional requirements are verified by test; NFR-07 is declared a target rather than a
measurement. Both gaps are stated in the specification rather than rounded away.

---

## 7. Software effort estimation

**Full document: `06-effort-estimation.md`.**

Two techniques, deliberately, because they disagree and the disagreement is informative.

| Technique | Result |
|---|---|
| **Use Case Points** | 97.39 UCP → **1,948 person-hours** |
| **Bottom-up task breakdown** | ~64 person-hours for the reduced scope |

**The 30× gap is the finding, not an error.** UCP is calibrated on commercial projects with
teams, handovers, meetings, environments and support. A single developer, working
continuously, on a system with no stakeholders to consult and no integration to negotiate,
operates in conditions UCP does not model.

**What the estimate actually did.** It made the cuts non-negotiable. 1,948 hours against 48
available says plainly that the brief cannot be built, so the only question is what to
remove — and the removals in §5 followed from the arithmetic rather than from taste. That
is what estimation is for, and it is why it is worth 5 marks.

---

## 8. System analysis

The problem's two structural facts determine the architecture:

| The fact | What it forces |
|---|---|
| Reports arrive in an uncontrolled order, sometimes twice | Grouping must be order-independent and provable; every write carries a key making retries harmless |
| A warning that is not sent is worse than no system | Saving and enqueueing must be one transaction |
| Evidence must be auditable | Reports written once, never edited |
| The score decides police involvement | It must be explainable, not merely displayed |

**The advanced concept**, in one paragraph: reports are permanent, unchangeable records. A
background process groups reports close in place and time into an Incident, and scores its
believability from reporter track record, fading with age. Saving a report and queueing its
notifications happen in one transaction, so a crash cannot lose one without the other.
Notifications carry a unique key, so a retry cannot warn anyone twice.

**The property that must always hold: the order reports arrive in must not change the
result.** Full treatment in `04-advanced-concept.md`.

---

## 9. System design

**Full document: `09-system-design.md`, with nine diagrams.**

> **Diagram placement for the PDF build — see `docs/diagrams/README.md`.** Four essential
> diagrams exist as standalone SVG; the remaining five are Mermaid, which renders on GitHub.

**Architecture: layered, with a pure core.** Four layers, and one rule — the domain layer
imports nothing from above it and touches no database, clock or network.

That rule is not decoration. It is why property-based testing was affordable: Hypothesis
can call `clustering.group()` a thousand times because calling it costs nothing. A
clustering function that read from the database could not be tested that way, and the
order-independence property could not have been proved.

**Data model.** Nine tables. Two are the design rather than incidental:

- **`reports` is append-only.** No status, no soft-delete. A report that turns out to be
  wrong is not edited — the incident is resolved as a false alarm and reputation moves.
- **`incidents` is derived.** It could be dropped and rebuilt by replaying the reports.
  That is what makes it safe to change the clustering rules later: the history is the
  reports, not the map.

**Three columns worth explaining:** `incidents.cluster_key` (the smallest member report id
— stable under merging, where a primary key is not), `incident_reports.weight` (stored so
the score is explainable), `outbox.idempotency_key` (unique, so a retry is a no-op).

---

## 10. Implementation

| Layer | Choice | Why |
|---|---|---|
| Backend | Python, FastAPI | Async, typed, generates its own API documentation |
| Database | PostgreSQL + PostGIS | `ST_DWithin` on `geography` measures real metres; a GiST index makes it fast |
| ORM | SQLAlchemy 2.0 async + Alembic | Typed models, versioned migrations |
| Front end | Native ES modules, no build step (D-037) | A build pipeline is a thing that breaks at hour 44 for reasons unrelated to the product |
| Tests | pytest + **Hypothesis** | The order-independence property cannot be demonstrated by examples |
| Hosting | Neon (database) + Render (application) | Free tier; no Vercel (D-012) |

**Scale:** ~2,000 statements of Python across 30 modules, 13 front-end ES modules, 508
tests, 7 migrations.

**The front end is an installable progressive web application** — offline report queueing
in IndexedDB, a service worker caching the shell, role-differentiated views, voice notes,
photographs, and a public map that needs no account.

Three implementation details worth defending in a viva:

- **The idempotency key is generated in the browser at capture**, not by the server at
  send. That is what makes the offline queue safe: the same physical report carries the
  same key however many times it is attempted.
- **`FOR UPDATE SKIP LOCKED`** lets multiple workers drain one queue without collision.
  There is one worker today; the query does not have to change when there are more.
- **Attachment URLs are signed and short-lived** (D-043), because `<img>` and `<audio>`
  cannot send an `Authorization` header — the same mechanism as an S3 presigned URL.

---

## 11. Testing and quality assurance

**Full document: `11-testing-report.md`.**

**508 tests. 499 without a database, 9 requiring PostGIS. 69% statement coverage overall,
99% on the pure domain core.**

The gap between those two numbers is the honest summary: the parts that *decide* things are
property-tested almost exhaustively; the parts that *move data around* rest on nine
integration paths.

**Thirty-five properties** under Hypothesis, at 150 examples each by default and 1,000
before submission. Eight defects were found by tests rather than by use. The best of them:
Hypothesis generated three *identical* longitudes and the computed mean came out one unit
in the last place below its own minimum, because floating-point addition is not
associative. No hand-written test picks that input — it looks degenerate and not worth
writing.

**Forty-nine tests check the documents against the code** — every module named in the SRS
exists, every table in the ER diagram is in the metadata and vice versa, quoted thresholds
match the constants, every citation resolves. Documentation rot is a defect class, and it
can be tested for.

---

## 12. Technical debt

**Full document: `08-technical-debt.md`. Repayment plan: `12-maintenance-and-evolution.md` §4.**

**Twenty-three items, every one recorded at the moment the shortcut was taken.** Each
records Debt → Cause → Impact → Priority → Proposed Resolution, classified **A**
(acceptable), **S** (scheduled) or **C** (critical).

| Class | Count | Meaning |
|---|---:|---|
| **C — Critical** | 2 | Must go before any real user: TD-17, TD-21 |
| **S — Scheduled** | 10 | Named release, ordered by interest rate |
| **A — Acceptable** | 11 | Reasonable trade-offs, recorded with reasoning |

**Two items have demonstrated their cost with dates.** TD-18 — one database serving
development and production — produced two false test failures by two different mechanisms,
both recorded. Debt whose cost has been observed twice is no longer theoretical.

**The most important item is TD-03**: the clustering constants, 300 metres and 30 minutes,
are untuned guesses. They are the two most consequential numbers in the system — they
decide whether six reports are one flood or six — and repaying this needs real data, which
needs users. The architecture was built so that repaying it is cheap: reports are the
history, incidents are derived, and a replay produces a new map under new parameters with
no migration.

---

## 13. Deployment and accessibility

**Live:** https://nkwanta.onrender.com/ — **Repository:** https://github.com/TheoCaesar/nkwanta
Credentials and a seven-step walkthrough: `Deployment_and_Source_Links.txt`.

| Component | Host |
|---|---|
| API, worker and the web application | Render (free tier, one process) |
| PostgreSQL 16 + PostGIS 3.6 | Neon |

The application is served from the root by FastAPI — there is no separate front-end host
(D-012). The outbox worker runs in-process as an asyncio task, because the free tier permits
one service; this is forced rather than chosen, and recorded as **TD-01**.

**Known deployment characteristics**, stated rather than hidden: the free instance sleeps
after inactivity, so the first request can take up to a minute (TD-09). Demonstration seed
and gateway-failure endpoints exist in production for the viva, and are the two Critical
debt items.

---

## 14. User manual

**Full document: `13-user-manual.md`.** Per role — commuter, officer, warden,
administrator — with troubleshooting and demonstration credentials.

It opens with a safety note, before anything else: **never use this while driving**, and
**the system does not call the police or an ambulance.** A manual that explains reporting
before saying that has put the instruction where nobody reads it.

---

## 15. Maintenance strategy

**Full document: `12-maintenance-and-evolution.md`.**

Built around Lehman's laws, because they predict what happens here specifically:

- **Continuing change.** The two clustering constants will be wrong the moment a real
  commuter appears. Reports permanent + incidents derived is the property that makes fixing
  them cheap.
- **Increasing complexity.** The dependency rule is the resistance — a decision that stays
  pure stays testable, and a decision that stays testable stays cheap to change. It has
  already failed once, in the layer with the least structure (the CSS).
- **Declining quality.** 508 tests, 49 of which check documents against code.

Routine operations are listed with frequencies: outbox rows at `MAX_ATTEMPTS` (a poison
message is skipped forever and is silent), breaker state, staleness sweep, dependency
audit, and **a quarterly restore test — a backup nobody has restored is a hypothesis.**

---

## 16. Future evolution

Ordered by value against cost to the existing design (`12-` §6):

1. **Tune the clustering constants against real data.** Not a feature — the difference
   between a system that works and one that appears to. Everything else assumes the
   grouping is right.
2. **Extract the worker.** The outbox already decouples it; a deployment change.
3. **Real notification delivery.** The breaker, the idempotency keys and the at-least-once
   semantics were all built for a real gateway. The work is an adapter, not a redesign.
4. **Reroute advisories.** Needs a routing engine and full road-network data.
5. **Ride-sharing — should stay excluded.** Not cut for lack of time. It is a second
   product wearing the same name, and building half of it inside this one would damage
   both. If ever built, it should be a separate system reading Nkwanta's public incident
   feed.
6. **Never: direct emergency dispatch.** NFR-05. A system that appears to summon an
   ambulance and does not is worse than no system.

---

## 17. Limitations

Stated plainly. Every one is recorded elsewhere with its reasoning; none is discovered by
the reader.

| Limitation | Consequence |
|---|---|
| **The clustering constants are untuned** | The system's central judgement rests on two reasoned guesses (TD-03) |
| **Reputation is unvalidated** | The model is arithmetically sound and empirically unchecked — no real outcomes exist to check it against (TD-04) |
| **Noisy-OR assumes independent reports** | A crowd watching one accident is not independent, so confidence is overstated in exactly the situation the system is for. Accepted because the *ordering* stays correct, and ordering is what the queue uses (TD-15) |
| **Clearance (FR-40) is untested** | The code path exists and is wired; no test calls it and no seeded incident demonstrates it |
| **NFR-07 is unmeasured** | "Under 3 seconds on 3G" is a target, not a result |
| **No end-to-end browser tests** | Three real interface defects were invisible to the suite, including offline never having worked |
| **No CI** | 508 tests are worth nothing on the day nobody runs them (TD-11) |
| **Single shared database** | No environment in which to test a destructive change safely (TD-18) |
| **Media stored in PostgreSQL** | The first thing to break under adoption (TD-19) |
| **Notification delivery is log-only** | No SMS or push; the gateway is a sink (TD-08) |

---

## 18. Conclusion

The examination rewards visible engineering process, not application size: implementation
is 10 marks of 48, and requirements, estimation, design, testing, debt, documentation and
evolution are the other 38. Nkwanta was built to that shape deliberately — a small system,
documented and tested in depth, rather than a large one thrown together.

Three things are worth pointing at.

**The scope decision.** Five features became one pipeline. A 1,948-hour estimate against 48
available hours made the cuts arithmetic rather than opinion, and every cut is recorded with
its reason.

**The advanced concept is proved, not asserted.** Order-independence is not demonstrated on
three hand-picked inputs — it is a property checked against a thousand generated cases,
holding because connected components and noisy-OR are commutative *by construction*. The
method found a real floating-point defect that no example-based test would have chosen.

**The record is honest.** Twenty-three debt items written as the shortcuts were taken.
Forty-five dated decisions, none rewritten — a reversed decision is superseded by a new
entry so the reasoning at the time survives. One requirement declared Partial and one
non-functional requirement declared unmeasured, in three documents each, rather than
rounded up to a full mark.

That last point is the one to defend. A submission claiming fifty of fifty would be a less
useful document and a less honest one, and the difference between the two is most of what
this course is about.

---

## 19. References

**Course material**

- Mensah, S. (2026). *CSCD602 Advanced Software Engineering*, University of Ghana.
  Session 4: software evolution and Lehman's laws.
- Lehman, M. M. (1980). Programs, life cycles, and laws of software evolution.
  *Proceedings of the IEEE*, 68(9), 1060–1076.

**Methods**

- Karner, G. (1993). *Resource Estimation for Objectory Projects.* Objective Systems.
  (Use Case Points — `06-effort-estimation.md`.)
- Cunningham, W. (1992). The WyCash portfolio management system. *OOPSLA '92*.
  (The technical debt metaphor.)
- Kruchten, P., Nord, R., Ozkaya, I. (2012). Technical debt: from metaphor to theory and
  practice. *IEEE Software*, 29(6). (The classification used in `08-technical-debt.md`.)
- Fowler, M. (2011). *CircuitBreaker*. martinfowler.com. (`circuit_breaker.py`.)
- Richardson, C. *Pattern: Transactional outbox.* microservices.io. (The core pattern.)
- Claessen, K., Hughes, J. (2000). QuickCheck: a lightweight tool for random testing of
  Haskell programs. *ICFP '00*. (The property-based testing method Hypothesis implements.)
- MacIver, D. R. et al. *Hypothesis: property-based testing for Python.*

**Third-party components** *(acknowledged under Rule 6 of the examination paper)*

| Component | Licence | Use |
|---|---|---|
| FastAPI, Starlette, Pydantic | MIT | API framework, validation |
| SQLAlchemy, Alembic | MIT | ORM and migrations |
| GeoAlchemy2, Shapely | MIT / BSD | Spatial types |
| asyncpg | Apache 2.0 | PostgreSQL driver |
| PostGIS | GPL-2.0 | Spatial database extension |
| bcrypt, PyJWT | Apache 2.0 / MIT | Password hashing, tokens |
| pytest, pytest-asyncio, Hypothesis | MIT / MPL-2.0 | Testing |
| MapLibre GL JS | BSD-3-Clause | Map rendering |
| OpenStreetMap tiles | ODbL | Map imagery — attributed in the interface |
| Mermaid | MIT | Diagrams in `09-system-design.md` |

No third-party code was copied into this project. All application code is original.

**Project documents**

`00-original-brief.txt` · `01-exam-requirements.md` · `02-problem-and-scope.md` ·
`03-glossary.md` · `04-advanced-concept.md` · `05-decision-log.md` ·
`06-effort-estimation.md` · `07-build-schedule.md` · `08-technical-debt.md` ·
`09-system-design.md` · `10-srs.md` · `11-testing-report.md` ·
`12-maintenance-and-evolution.md` · `13-user-manual.md` ·
`design/ui-designs.html` · `explainers/01`–`09` · `HANDOFF.md` · `RUNBOOK.md`
