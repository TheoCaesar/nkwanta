# CLAUDE.md — Working Instructions for This Project

> Read this file first in every session. It tells you what this project is, what has
> already been decided, and what you are not allowed to change without asking.

---

## 1. What this project is

**Nkwanta** (Twi for *junction*) is a road incident reporting and dispatch system for
urban Ghana. Road users report things that block traffic — accidents, floods, closures,
broken traffic lights, roadworks. The system works out which reports describe the same
real-world event, judges how believable they are, warns other commuters heading that way,
and puts a job in front of the police or a traffic warden.

It is being built as a submission for **CSCD602 Advanced Software Engineering**, a
48-hour individual project examination at the University of Ghana, examined by
Prof. Solomon Mensah. Marks total 50.

**The single most important thing to understand:** this exam does not reward a big
application. It rewards visible, disciplined engineering process. Implementation is
only 10 of the 50 marks. Requirements, estimation, design, testing, technical debt,
documentation and evolution are the other 40. A small system, impeccably documented,
beats a large system thrown together.

Full mark breakdown: `docs/01-exam-requirements.md`

---

## 2. Hard rules

These are not suggestions. Breaking them costs marks.

**Rule 1 — Do not expand scope.**
The feature set is frozen and recorded in `docs/02-problem-and-scope.md`. Ride-sharing,
transport subscriptions, real emergency-services integration and fare-abuse adjudication
are **deliberately excluded**. If you think something should be added, do not add it.
Write it in the backlog table instead and note it in `HANDOFF.md`. The examiner is
assessing whether the candidate can hold a scope line under time pressure.

**Rule 2 — Plain language before jargon, always.**
Every document in this project explains an idea in ordinary words first, then names the
technical term. Never introduce a term like "idempotent" or "projection" without a plain
sentence next to it. If you use a technical term anywhere in the docs, it must have an
entry in `docs/03-glossary.md`. Check before you commit.

**Rule 3 — Every decision gets dated.**
Any choice that a reader might later question goes in `docs/05-decision-log.md` with the
date, the options considered, and the reason. Session progress goes in `HANDOFF.md`
under a new dated heading. Never rewrite an old dated section — append a new one.

**Rule 4 — Technical debt is recorded as it happens, not reconstructed at the end.**
The moment you take a shortcut, write it into the debt register with its cause, impact,
priority and proposed fix. Debt discovered honestly during the build reads as competence.
Debt invented afterwards reads as invented, and this is worth 6 marks.

**Rule 5 — No feature that endangers a road user.**
The driver-facing view is passive and read-only. The system never asks someone to type
while driving. It never claims to summon an ambulance or the police directly — it places
an escalation flag in a queue that a human authority monitors. This is a stated design
constraint, not an oversight.

---

## 3. The advanced concept (one paragraph)

Reports are stored as permanent, unchangeable records. A background process groups
reports that are close together in **place and time** into a single Incident, and scores
how believable that Incident is based on how much the reporters have been trusted in the
past, fading out over time if nobody confirms it. Saving a report and queuing its
notifications happen in the same database transaction so a crash can never lose one
without the other. Notifications carry a unique key so a retry cannot warn the same
person twice.

The property that must always hold: **the order reports arrive in must not change the
final result.** If Kofi's report arrives before Ama's, or Ama's before Kofi's, the
Incident must end up identical either way.

Explained properly, in plain language: `docs/04-advanced-concept.md`

---

## 4. Technology

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI |
| Database | PostgreSQL with PostGIS (location data) |
| ORM / migrations | SQLAlchemy + Alembic |
| Frontend | One static HTML page, MapLibre GL, served by FastAPI via `StaticFiles` |
| Tests | pytest, plus **Hypothesis** for property-based tests |
| Hosting | Neon (database) + Render (API and page). **No Vercel** — see D-012. |

The outbox worker runs **in-process** as an asyncio task, not as a separate service, because
Render's free tier permits only one. This is deliberate, forced by the platform, and recorded
as technical debt — see D-013. Do not "fix" it.

Hypothesis is not optional. The order-independence property test is the centrepiece of
the testing section and is worth real marks.

---

## 5. Folder layout

```
nkwanta/
├── CLAUDE.md              <- you are here
├── HANDOFF.md             <- dated running log; read the latest entry
├── README.md              <- orientation for a first-time reader
└── docs/
    ├── 00-original-brief.txt      <- the user's own words, unedited
    ├── 01-exam-requirements.md    <- what the exam demands, and the mark scheme
    ├── 02-problem-and-scope.md    <- problem, users, what's in, what's out, backlog
    ├── 03-glossary.md             <- every technical term in plain English
    ├── 04-advanced-concept.md     <- the advanced concept, explained simply
    └── 05-decision-log.md         <- dated record of every significant choice
```

Code has not been written yet. When it is, it goes in `src/` (backend) and `web/`
(frontend) inside this same folder.

---

## 6. How to start a session

1. Read `HANDOFF.md`, latest dated section first. It says where things stand.
2. Read `docs/02-problem-and-scope.md` so you do not accidentally build a cut feature.
3. Do the work.
4. Append a new dated section to `HANDOFF.md` before you finish.
5. Add any new decisions to `docs/05-decision-log.md`.

---

## 7. Writing style for all documents

- Short sentences. One idea each.
- Explain, then name. "A record that is written once and never edited — an *immutable
  event*." Not the other way round.
- Tables for anything with more than three parallel items.
- No filler. If a sentence can go without losing meaning, cut it.
- Write for a reader who is intelligent but has not taken this course.
- British spelling, to match the exam paper.
