# Software Effort Estimation

*Last updated: 12 August 2026*
*Worth 5 of the 50 marks. The paper requires the estimate to have visibly influenced scope —
this document shows exactly how it did.*

---

## 1. Why two techniques, not one

The paper asks for one justified technique. This project uses **two**, deliberately, because
they answer different questions and one alone would mislead.

| Technique | Question it answers | Why it is used here |
|---|---|---|
| **Use Case Points (UCP)** | How big is this product, in absolute terms? | Formal, defensible, derives from the use cases already written. Gives a *product-level* figure. |
| **Bottom-up task estimation** | What can actually be built in the hours remaining? | UCP is calibrated for commercial team projects. At the granularity of a 48-hour solo prototype it breaks down, and pretending otherwise would be dishonest. |

**UCP was chosen over the alternatives** because Function Point Analysis needs a data-function
inventory that does not exist yet; COCOMO II needs a lines-of-code or size estimate, which is
circular this early; and story points are relative, meaning they cannot produce absolute hours
without velocity history that a solo 48-hour project cannot have. UCP derives directly from the
use case model, which is the artefact already available.

**The headline result is that the two techniques disagree by a factor of roughly 30.** That
disagreement is the most useful finding in this document, and Section 6 explains it.

---

## 2. Use Case Points — the calculation

### 2.1 Unadjusted Actor Weights (UAW)

| Actor | Type | Justification | Weight |
|---|---|---|---:|
| Commuter / motorist | Complex | Person via graphical interface | 3 |
| Traffic control officer | Complex | Person via graphical interface | 3 |
| System administrator | Complex | Person via graphical interface | 3 |
| Traffic warden | Average | Person, minimal text interface in this scope | 2 |
| Notification gateway | Simple | External system via API | 1 |
| Map tile provider | Simple | External system via API | 1 |
| | | **UAW** | **13** |

### 2.2 Unadjusted Use Case Weights (UUCW)

Classified by transaction count: Simple ≤3 (weight 5), Average 4–7 (weight 10),
Complex >7 (weight 15).

| ID | Use case | Type | Weight |
|---|---|---|---:|
| UC-01 | Register / authenticate | Average | 10 |
| UC-02 | Submit incident report | Complex | 15 |
| UC-03 | Cluster reports into incidents | Complex | 15 |
| UC-04 | Confidence scoring + reputation update | Complex | 15 |
| UC-05 | Incident lifecycle transitions | Average | 10 |
| UC-06 | Subscribe to corridor | Simple | 5 |
| UC-07 | Deliver commuter advisory | Average | 10 |
| UC-08 | View live incident map | Average | 10 |
| UC-09 | Officer dispatch queue | Average | 10 |
| UC-10 | Warden confirms resolution | Simple | 5 |
| UC-11 | Admin user management / moderation | Average | 10 |
| UC-12 | Rate limiting + abuse controls | Simple | 5 |
| | | **UUCW** | **120** |

**UUCP = UAW + UUCW = 13 + 120 = 133**

### 2.3 Technical Complexity Factor (TCF)

| Factor | Weight | Rating (0–5) | Product | Note |
|---|---:|---:|---:|---|
| T1 Distributed system | 2 | 3 | 6 | Background worker, separate database |
| T2 Response time / throughput | 1 | 4 | 4 | NFR-1: warnings within 10 seconds |
| T3 End-user efficiency | 1 | 4 | 4 | Low-end Android, 3G |
| T4 Complex internal processing | 1 | 5 | 5 | Clustering, decay, order-independence |
| T5 Reusability | 1 | 2 | 2 | — |
| T6 Easy to install | 0.5 | 2 | 1 | — |
| T7 Ease of use | 0.5 | 4 | 2 | Used under time pressure, sometimes in traffic |
| T8 Portability | 2 | 2 | 4 | — |
| T9 Ease of change | 1 | 3 | 3 | — |
| T10 Concurrency | 1 | 4 | 4 | Simultaneous reports racing on the same cluster |
| T11 Security objectives | 1 | 4 | 4 | Roles, abuse controls, location privacy |
| T12 Third-party access | 1 | 1 | 1 | — |
| T13 User training | 1 | 1 | 1 | — |
| | | **TFactor** | **41** | |

**TCF = 0.6 + (0.01 × 41) = 1.01**

### 2.4 Environmental Complexity Factor (ECF)

| Factor | Weight | Rating (0–5) | Product | Note |
|---|---:|---:|---:|---|
| E1 Familiarity with process | 1.5 | 3 | 4.5 | Lifecycle known from the course |
| E2 Application experience | 0.5 | 1 | 0.5 | New domain |
| E3 Object-oriented experience | 1 | 3 | 3.0 | — |
| E4 Lead analyst capability | 0.5 | 3 | 1.5 | — |
| E5 Motivation | 1 | 5 | 5.0 | It is an examination |
| E6 Stable requirements | 2 | 5 | 10.0 | Scope frozen and self-defined |
| E7 Part-time staff | −1 | 0 | 0.0 | Full-time, solo |
| E8 Difficult programming language | −1 | 2 | −2.0 | Python fluent; PostGIS and event patterns new |
| | | **EFactor** | **22.5** | |

**ECF = 1.4 − (0.03 × 22.5) = 0.725**

### 2.5 Result

**UCP = 133 × 1.01 × 0.725 = 97.39**

Rate selection by the Schneider & Winters rule: count E1–E6 rated below 3, plus E7–E8 rated
above 3. Here that total is **1** (only E2). A total of 2 or less indicates **20 hours per
UCP**.

> ### **Effort = 97.39 × 20 = 1,948 person-hours**
>
> ≈ 243 person-days ≈ **12.8 person-months**

Must-have subset only (UC-01 to UC-05, UC-08, UC-09): **69.56 UCP → 1,391 person-hours**,
which is 71% of full scope.

---

## 3. What that number actually means

**It does not mean the estimate failed.** It means the product, built properly for production
by a commercial team with full documentation, quality assurance, project management and team
communication overhead, is roughly **thirteen person-months** of work.

That is a credible figure for what has been specified, and it is worth stating plainly in the
submission. The examination window is 48 hours.

**Ratio of estimated work to available time: roughly 40 to 1.**

This is the single most important output of the estimation exercise. It says, unambiguously,
that the 48-hour deliverable **cannot be the product**. It has to be a deliberately chosen
vertical slice — narrow in features, complete in architecture — that exercises the design
end to end and demonstrates the advanced concept working.

Every scope decision from here follows from that sentence.

---

## 4. Bottom-up estimate — what actually fits

UCP sizes the product. It cannot size a 48-hour prototype, because its hour rates carry
overheads a solo exam build does not have. So the achievable slice is estimated bottom-up,
task by task.

**Learning-curve padding.** Each task carries a multiplier reflecting unfamiliarity: 1.2 for
routine work, up to 1.8 for the transactional outbox and the PostGIS clustering, which are new
territory. Padding is applied per task rather than as a blanket uplift so the reasoning is
visible.

### Tier 0 — the concept spine

The narrowest slice that still demonstrates the advanced concept and deploys as a working
application.

| ID | Task | Hours |
|---|---|---:|
| B01 | Scaffold, and stand up the deploy pipeline on day one | 2.0 |
| B02 | Data model: users, reports, incidents, outbox — four tables | 1.5 |
| B03 | Auth: JWT, three roles, no password-reset flow | 2.1 |
| B04 | Report intake: validation + event + outbox row in **one transaction** | 3.6 |
| B05 | Clustering consumer: spatio-temporal grouping via PostGIS | 4.5 |
| B06 | Confidence with exponential time decay, fixed reporter weight | 1.5 |
| B09 | Outbox worker + idempotency keys, log-only sink | 2.5 |
| B18 | Seed data: ~20 Accra junctions plus plausible reports | 0.8 |
| B19 | Property tests: order-independence, no-overlap | 2.0 |
| B21 | Deployment verification + credentials | 1.2 |
| B22 | Single-page map + report form, minimal styling | 2.5 |
| | **Raw** | **24.2** |
| | **With 15% contingency** | **27.8** |

### Tier 1 — spine plus the officer workflow

Adds: dispatch queue API and view (1.8), lifecycle state machine with guards (1.4), third
property test for replay equality (0.6), unit and integration tests (2.1).

**Raw 30.1 h → 34.6 h with contingency.**

### Tier 2 — full must-have plus should-have

Adds: full reputation model (1.6), proper MapLibre UI (2.0), rate limiting and abuse controls
(1.4), circuit breaker (1.7), corridor subscriptions and advisory delivery (2.1), admin screens
(1.9).

**Raw 40.9 h → 47.0 h with contingency.**

---

## 5. Fitting the estimate to the clock

Assuming implementation receives roughly 55% of remaining time, with the balance going to
testing, deployment and the required documentation:

| Hours left | Build time available | What fits |
|---:|---:|---|
| 20 | 11.0 | Below Tier 0 — the web interface must go |
| 24 | 13.2 | Below Tier 0 — the web interface must go |
| 28 | 15.4 | Below Tier 0 — the web interface must go |
| 32 | 17.6 | Below Tier 0 — the web interface must go |
| 36 | 19.8 | Below Tier 0 — the web interface must go |
| 40 | 22.0 | Below Tier 0 — the web interface must go |
| 48 | 26.4 | Tier 0 |

**Read that carefully. Even Tier 0 needs a full clean 48 hours.** Since the examination is
already underway, Tier 0 as specified does not fit either.

### The mitigation

Two things make this recoverable, and both are legitimate.

**One — Phase 1 is already complete.** The paper allocates hours 1–12 to requirements,
scoping, estimation and design. Problem definition, stakeholders, scope, non-functional
requirements, the advanced concept, the decision log and this estimate are all written. Those
hours are banked. Implementation can therefore take a larger share of what remains than the
55% assumed above.

**Two — the front end is the right thing to sacrifice.** It costs 2.5 hours in Tier 0 and
carries almost no marks. FastAPI generates interactive API documentation automatically, which
is a genuine, usable, demonstrable interface. A single static HTML page with a map and a form
can be added on top for a fraction of the cost of a React application.

### Recommended cut list, in the order things should go

| Order | Cut | Saves | Cost of cutting |
|---:|---|---:|---|
| 1 | React app → one static HTML page against the API | ~1.5 h | Cosmetic only |
| 2 | Admin screens → admin operations via API and seeded data | ~1.9 h | None for the demo |
| 3 | Circuit breaker → designed and documented, not built | ~1.7 h | Loses a nice demo; goes in the debt register |
| 4 | Full reputation model → fixed weight plus decay | ~1.6 h | Concept still intact, simplified |
| 5 | Corridor subscriptions → seeded, not user-managed | ~2.1 h | Advisory still demonstrable |
| 6 | Third property test → keep the two strongest | ~0.6 h | Minor |

**Nothing on that list touches B04, B05, B06 or B09.** Those four tasks are the advanced
concept, they total 12.1 hours, and they are what the project is actually being marked on.
They are protected.

---

## 6. Why the two techniques disagree by 30×

Worth understanding, because it is a likely viva question.

Karner's 20 hours per UCP is calibrated against commercial projects and absorbs: formal
requirements sign-off, architecture review, project management, team communication, code
review, a separate QA cycle, user acceptance testing, release management and full production
documentation. Communication overhead alone grows quadratically with team size and vanishes
entirely at a team of one.

This project has none of those. It also benefits from framework scaffolding — FastAPI,
SQLAlchemy and Alembic generate a substantial amount of what UCP assumes is hand-written.

Dividing the fitted bottom-up figure by the must-have UCP gives an implied local rate of about
**0.6 hours per UCP**, against Karner's 20. That is not evidence the model is broken. It is
evidence that the model is measuring a different thing — a production system with full process
around it, rather than a solo prototype.

**Both numbers are correct. They answer different questions.** Reporting only the convenient
one would be the actual error.

---

## 7. Assumptions

1. One developer, working alone, no team communication overhead.
2. Python is fluent; FastAPI, PostGIS and event-driven patterns are new — reflected in E8 and
   in the per-task learning multipliers.
3. Hosting accounts on Render, Neon and Vercel exist and are verified before the build starts.
4. No real SMS or push provider is integrated. Notifications are written to a log, which
   demonstrates the outbox and idempotency mechanics without a paid dependency.
5. Seed data is authored by hand; no live traffic feed exists to import.
6. Requirements do not change mid-build. Scope is frozen per
   [`02-problem-and-scope.md`](02-problem-and-scope.md).
7. Contingency is 15%. This is low for a novel domain, and is justified only because scope is
   frozen and the fallback tiers are pre-defined.

## 8. Constraints

1. Hard 48-hour ceiling, already partly consumed.
2. Solo. No parallelisation is possible — every hour is sequential.
3. The application must be deployed and publicly reachable, and must **stay** reachable.
4. Nine separate documents must be produced, which consumes real hours that cannot be
   reassigned to building.
5. Sleep is not optional across a 48-hour window and is not modelled above. Any realistic plan
   must subtract it from the remaining clock before applying the table in Section 5.

---

## 9. How the estimate changed the project

This section is the one the mark scheme is actually asking for.

| # | Estimate finding | Decision taken |
|---|---|---|
| 1 | Full scope is 1,948 person-hours, ~40× the window | The deliverable is redefined as a vertical slice, not a product. Recorded as **D-009**. |
| 2 | Even the must-have set is 1,391 person-hours | Should-have features demoted to Could-have. Tier 2 abandoned before any code was written. |
| 3 | Tier 0 at 27.8 h does not fit the remaining clock | Six-item cut list produced and ordered, front end first. Recorded as **D-010**. |
| 4 | B04, B05, B06 and B09 total 12.1 h and carry the concept | Ring-fenced. Nothing may be cut from them. Recorded as **D-011**. |
| 5 | Clustering and outbox carry the highest learning multipliers (1.8) | Scheduled **first**, when time pressure is lowest and there is still room to recover. |
| 6 | Deployment is historically where 48-hour projects die | B01 stands the deploy pipeline up on day one, deploying an empty application, rather than leaving it to the end. |

Finding 6 deserves emphasis. Deployment is worth 3 marks and is pass-or-fail — an application
that does not deploy scores zero on implementation regardless of code quality. Deploying an
empty skeleton in hour one converts the single largest project risk into a solved problem.
