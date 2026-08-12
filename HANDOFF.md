# HANDOFF

**Running log for the Nkwanta project.** Newest section at the top. Append a new dated
section at the end of every working session. Never rewrite an older one — if something turns
out to have been wrong, say so in a new entry.

Each entry answers four questions: what happened, where things stand, what is unresolved,
what comes next.

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
