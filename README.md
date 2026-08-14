# Nkwanta

**Road incident reporting and dispatch for urban Ghana.**

*Nkwanta* is Twi for *junction*.

Road users report what is blocking traffic — accidents, floods, closures, failed traffic
lights, roadworks, broken surfaces. The system works out which reports describe the same real
event, judges how believable it is, warns commuters heading that way, and puts a job in front
of the police or a traffic warden.

Built as a submission for **CSCD602 Advanced Software Engineering**, University of Ghana —
a 48-hour individual project examination marked out of 50.

---

## Where to start reading

**If you have five minutes** — read this page, then
[`docs/04-advanced-concept.md`](docs/04-advanced-concept.md).

**If you are picking the project up** — read [`HANDOFF.md`](HANDOFF.md) first, latest dated
section, then [`CLAUDE.md`](CLAUDE.md).

**If a technical term is unfamiliar** — everything is explained in plain English in
[`docs/03-glossary.md`](docs/03-glossary.md). No prior knowledge assumed.

---

## The files

| File | What it is |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Working rules. Read before doing anything. |
| [`HANDOFF.md`](HANDOFF.md) | Dated session log. Where things stand right now. |
| [`docs/00-original-brief.txt`](docs/00-original-brief.txt) | The author's own words, unedited |
| [`docs/01-exam-requirements.md`](docs/01-exam-requirements.md) | What the exam demands, and what the marks are actually for |
| [`docs/02-problem-and-scope.md`](docs/02-problem-and-scope.md) | Problem, users, what is in, what is out, and why |
| [`docs/03-glossary.md`](docs/03-glossary.md) | Every technical term, in plain English |
| [`docs/04-advanced-concept.md`](docs/04-advanced-concept.md) | The advanced concept, explained without jargon |
| [`docs/05-decision-log.md`](docs/05-decision-log.md) | Every significant choice, dated, with reasoning |
| [`docs/06-effort-estimation.md`](docs/06-effort-estimation.md) | Use Case Points and bottom-up estimate, and the cuts they forced |
| [`docs/07-build-schedule.md`](docs/07-build-schedule.md) | Hour-by-hour plan for the remaining clock, with cut triggers |
| [`docs/08-technical-debt.md`](docs/08-technical-debt.md) | Live debt register — every shortcut, its cause and its repayment |
| [`docs/09-system-design.md`](docs/09-system-design.md) | Architecture, data model, sequences, lifecycle, deployment — with UML |
| [`docs/design/ui-designs.html`](docs/design/ui-designs.html) | UI/UX specification — every screen, every role, signed out and in |
| [`RUNBOOK.md`](RUNBOOK.md) | Run it locally, then deploy it. Written to be executed. |

### Explainers — one per module, written to be defended aloud

| File | Covers |
|---|---|
| [`docs/explainers/01-authentication.md`](docs/explainers/01-authentication.md) | Roles, tokens, why there is no driver role, why registration cannot escalate |
| [`docs/explainers/02-report-intake-and-the-outbox.md`](docs/explainers/02-report-intake-and-the-outbox.md) | The transactional outbox, idempotency, the longitude/latitude trap |
| [`docs/explainers/03-clustering-and-order-independence.md`](docs/explainers/03-clustering-and-order-independence.md) | Connected components, why incremental assignment fails, float associativity |
| [`docs/explainers/04-confidence-and-decay.md`](docs/explainers/04-confidence-and-decay.md) | Noisy-OR, why not to sum weights, and the independence assumption that is false |
| [`docs/explainers/05-the-outbox-worker-and-projection.md`](docs/explainers/05-the-outbox-worker-and-projection.md) | Draining the outbox, why rebuild beats update, preserving human decisions |
| [`docs/explainers/06-lifecycle-and-reputation.md`](docs/explainers/06-lifecycle-and-reputation.md) | Rules as data, computed vs decided states, why reputation uses a Beta prior |
| [`docs/explainers/07-voice-notes-and-evidence.md`](docs/explainers/07-voice-notes-and-evidence.md) | The answer to NFR-3, safe binary serving, and a real bug property testing found |
| [`docs/explainers/08-corridors-and-commuter-advisory.md`](docs/explainers/08-corridors-and-commuter-advisory.md) | Lines not points, two thresholds on purpose, and why a row id cannot identify an event |
| [`docs/explainers/09-circuit-breaker-and-clearance.md`](docs/explainers/09-circuit-breaker-and-clearance.md) | Three states, why the clock is a parameter, and a decay that was applied to nothing |

Each ends with a thirty-second summary written to be said out loud. Rule 10 of the exam
paper permits an oral examination on authorship and understanding — see *viva voce* in
the [glossary](docs/03-glossary.md).

---

## The problem, briefly

Urban Ghana has far more vehicles than road capacity. Congestion is then made worse by events
nobody can announce reliably: accidents, flooding, power cuts that kill traffic signals,
uncoordinated roadworks, surface failures.

The information that would help already exists — the drivers stuck in it know exactly what is
wrong. There is simply no channel carrying it to the commuters behind them, or to the
authorities who could clear it.

> Road users possess accurate, real-time knowledge of what is blocking traffic, but have no
> reliable way to pass it to the commuters behind them or to the authorities who can act on
> it. Congestion is therefore prolonged well beyond the duration of its underlying cause.

---

## The advanced concept, in plain words

Nineteen people report the same jackknifed truck within four minutes. That raises four
questions a form-and-database application cannot answer:

1. **Is this one crash or nineteen crashes?** Nobody says. The system must work it out from
   where and when each report came in.
2. **Is it real?** Some reports are mistaken. Some are malicious. The system decides whether
   police are called, so it cannot simply believe what it is told.
3. **What if the server dies at the wrong moment** — after saving the report but before
   warning anyone? The report looks fine. Nobody is warned. No error appears. Silent failure.
4. **What if reports arrive in different orders?** One user is on 4G, another on failing 3G.
   If order changes the answer, two people see two different maps of the same road.

The answers:

- Reports are **permanent records**, never edited. Incidents are **calculated** from them, the
  way a bank balance is calculated from transactions rather than stored.
- Reports close in **place and time** are grouped into one Incident. Confidence comes from how
  reliable each reporter has proven to be, and **fades as the report ages** so stale incidents
  clear themselves.
- Saving a report and queuing its notifications happen in **one database transaction**, so
  there is no gap to crash in.
- Every notification carries a **unique key**, so a retry cannot warn the same person twice.

And the rule that must never break: **the order reports arrive in must not change the result.**
That is provable, not just assertable — property-based tests feed the same reports in hundreds
of random orders and check the answer never changes.

Full explanation: [`docs/04-advanced-concept.md`](docs/04-advanced-concept.md)

---

## Scope

**In:** incident reporting across six types · grouping and confidence scoring · reporter
reputation · incident lifecycle · commuter advisory · authority dispatch queue · live public
map · roles and permissions · abuse controls.

**Deliberately out:** ride-sharing · transport subscriptions · real emergency services
integration · trotro fare adjudication · turn-by-turn rerouting.

The exclusions are decisions, not omissions, and they are recorded with reasoning. The exam
awards 7 marks for requirements prioritisation and 5 for effort estimation that visibly shaped
scope — cutting well is part of what is being marked.

Details: [`docs/02-problem-and-scope.md`](docs/02-problem-and-scope.md)

---

## Stack

Python · FastAPI · PostgreSQL with PostGIS · SQLAlchemy · Alembic · a single static page with
MapLibre GL served by FastAPI · pytest with Hypothesis · Neon + Render.

Vercel and React were both dropped once the effort estimate reduced the front end to one page —
see D-012.

---

## Status

**Live at [nkwanta.onrender.com](https://nkwanta.onrender.com/). 322 tests passing.**

34 API endpoints · 7 migrations · 35 dated decisions · 22 technical debt items ·
9 module explainers · property-based tests for clustering, confidence, the lifecycle and
the circuit breaker.

| Step | State |
|---|---|
| B01 scaffold, health checks, PostGIS | done, deployed |
| B02 data model — five tables | done |
| B03 authentication, four roles | done |
| B04 report intake with the transactional outbox | done |
| B05 spatio-temporal clustering | done |
| B06 confidence with time decay | done |
| B09 outbox worker, projection, incidents API | done |
| D rich seed data and demo accounts | done |
| B08 lifecycle, dispatch, reputation loop | done |
| F voice notes, photos, evidence bonus | done |
| B corridor subscriptions and advisory | done |
| C circuit breaker, clearance notifications | done |
| B22 the web page | done — **the build is complete** |

The estimate that shaped all of this: Use Case Points puts full scope at **1,948
person-hours**, roughly forty times the original examination window. The deliverable is
therefore an explicit *vertical slice* — narrow in features, complete in architecture —
with the advanced concept ring-fenced against every cut.

Current state, open questions and next actions: [`HANDOFF.md`](HANDOFF.md), latest dated
section.
