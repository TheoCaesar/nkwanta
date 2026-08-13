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
| [`RUNBOOK.md`](RUNBOOK.md) | Run it locally, then deploy it. Written to be executed. |

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

**Planning and estimation complete. No code yet — and that is deliberate.** The exam paper
allocates the first 12 of 48 hours to requirements, estimation and design before
implementation begins.

The estimate landed hard: Use Case Points puts full scope at **1,948 person-hours**, about
forty times the examination window. The deliverable is therefore explicitly a *vertical
slice* — narrow in features, complete in architecture — with a pre-agreed cut list and the
advanced concept ring-fenced against it.

Next up: confirm hours remaining, verify hosting accounts, then deploy an empty application
before writing any feature code. See [`HANDOFF.md`](HANDOFF.md).
