# Maintenance Strategy and Future Evolution

**Nkwanta: A Road Incident Reporting and Dispatch System for Urban Ghana**

*14 August 2026 · Theophilus Caesar, 22424543*

---

## 1. The question this document answers

Not "what would we build next" — that is a wish-list, and wish-lists are cheap. The
question is: **what happens to this system when it is used, and has it been built so that
what happens next is affordable?**

That is a different question, and it has a testable answer.

---

## 2. Lehman's laws, and what they predict here

Lehman observed that software in real use must keep changing or it stops being useful, and
that as it changes it grows more complex unless someone actively works against that. Three
of his laws bear directly on Nkwanta.

### 2.1 Continuing change — the system must adapt or become useless

**The prediction:** the moment a real commuter uses this, the two numbers at the heart of
it — 300 metres and 30 minutes — will be wrong. They were chosen by reasoning about Accra's
road spacing, not measured against anything (TD-03).

**What was built against it.** Reports are permanent; incidents are *derived*. The map is
not stored — it is recalculated from the reports. So changing the clustering rules does not
corrupt history or require a data migration: change the constants, replay, get a new map.
The evidence is the reports.

This is the strongest maintainability property in the system, and it exists precisely
because Lehman's first law was expected to apply.

### 2.2 Increasing complexity — entropy unless resisted

**The prediction:** each change makes the next one harder.

**What was built against it.** The dependency rule — the domain layer touches no database,
clock or network — is the resistance. It is not a style preference; it is what keeps
`clustering.py` at 100% coverage and property-tested while the routers sit at 40%. A
decision that stays pure stays testable, and a decision that stays testable stays cheap to
change.

**Where the resistance has already failed once**, and it is worth stating: `.t` and `.m`
were `display:inline`, and one CSS defect surfaced as three unrelated complaints across two
sessions because the symptom depended on which parent happened to force a column. That is
Lehman's second law arriving on schedule in the layer with the least structure.

### 2.3 Declining quality — unless rigorously maintained

**The prediction:** the system will be judged worse over time even if it does not change,
because expectations move.

**What was built against it.** 508 tests, 49 of which check the *documents* against the
code. Documentation rot is quality decline that nobody notices until someone trusts a
diagram and is wrong.

---

## 3. Maintenance strategy by category

The four standard categories, with what each actually means here and who would do it.

| Category | Share expected | What it looks like in Nkwanta |
|---|---:|---|
| **Corrective** — fixing defects | ~20% | Most defects here have been in the interface, not the domain. §5 says why that is likely to continue. |
| **Adaptive** — reacting to a changing environment | ~30% | Dependency updates, PostGIS versions, browser behaviour, hosting changes. The largest single item is leaving the free tier. |
| **Perfective** — improving what works | ~35% | Tuning the two clustering constants against real data. Everything else is secondary to that. |
| **Preventive** — reducing future cost | ~15% | The debt register. §4 is the plan. |

### 3.1 Routine operations

| Task | Frequency | Why |
|---|---|---|
| Check the outbox for rows at `MAX_ATTEMPTS` | Weekly | A poison message is skipped forever and is silent. `GET /admin/stats` shows the pending count. |
| Check the circuit breaker state | Weekly | `GET /admin/gateway`. An open breaker means deliveries are being refused. |
| Run the staleness sweep | Automatic; verify monthly | Confidence decays only when the sweep runs (TD-22). |
| Dependency audit | Monthly | Currently manual, verified once at build time (TD-10). |
| Database backup | Automatic on Neon; **verify a restore quarterly** | A backup nobody has restored is a hypothesis. |
| Run `HYPOTHESIS_PROFILE=thorough pytest` | Before any release | 1000 examples per property instead of 150. |

---

## 4. The debt repayment plan

Twenty-three items in `08-technical-debt.md`, classified **A** (acceptable), **S**
(scheduled) or **C** (critical). This is the order in which they would be repaid and why —
prioritised by **interest rate**, meaning how much worse each gets on its own, rather than
by how annoying it is.

### Release 1 — before any real user (the two Critical items)

| Item | Debt | Why first |
|---|---|---|
| **TD-21** | The gateway can be deliberately broken from the live deployment | It exists to demonstrate the circuit breaker in a viva. On a real system it is a switch for turning off everyone's warnings. |
| **TD-17** | Seed and drain endpoints exist in production | `POST /admin/seed` can wipe demonstration data. With real reports in the same table, that is destruction. |

Both are admin-only, so neither is a vulnerability today. Both are one environment flag to
remove, and both are unacceptable the day the first real reporter appears.

### Release 2 — before the system is trusted

| Item | Debt | Interest |
|---|---|---|
| **TD-18** | One database for development and production | **High and rising.** It has already produced two false test failures with different mechanisms. A second Neon project is free; this was a time decision, not a money one. |
| **TD-03** | Clustering constants hardcoded and untuned | **High.** These two numbers decide whether six reports are one flood or six. Repayment needs real data, which needs users, which is why it cannot come first. |
| **TD-11** | No CI — tests run when remembered | **Rising.** 508 tests are worth nothing on the day nobody runs them. |
| **TD-19** | Media stored in PostgreSQL rather than object storage | **Rising with adoption.** The first thing that breaks under load. |

### Release 3 — before scale

TD-01 (in-process worker), TD-05 (synchronous projection), TD-06 (no dead-letter queue),
TD-14 (O(n²) clustering within a bucket). All four are the same story: fine at demonstration
volume, structural at city volume. **None requires a rewrite** — the outbox already
decouples the worker, so extracting it is a configuration change.

### Accepted indefinitely

TD-02, TD-07, TD-08, TD-09, TD-12, TD-13, TD-15, TD-16, TD-20, TD-22, TD-23. Each is a
reasonable trade-off recorded with its reasoning. **TD-15 deserves a note**: noisy-OR
assumes reports are independent, and a crowd watching one accident is not independent. The
score therefore overstates confidence in exactly the situation the system is designed for.
It is accepted because the *ordering* remains correct — more corroboration still ranks
higher — and ordering is what the dispatch queue uses.

### One immediate gap, not yet a debt entry

**FR-40, clearance, is Partial.** The code path exists and is wired; no test calls it and
no seeded incident demonstrates it. This is a testing gap rather than a shortcut, so it
lives in the SRS and the testing report rather than the debt register — but it is the first
thing to close after submission, because a warning system that never says "you can go now"
is half a system.

---

## 5. Where the next defects will come from

Predicting this is more useful than promising quality. Based on where the defects have
actually been:

| Area | Risk | Evidence |
|---|---|---|
| **The interface** | **Highest.** No end-to-end browser tests; the front end is verified by reading its source. | §4.4, §4.5, §4.6 of the testing report — three defects invisible to the suite, including offline never working |
| **Alembic drift** | **High.** No test applies the migration chain to an empty database and compares it to `Base.metadata`. | Not yet bitten. The most likely thing to bite. |
| **The outbox under contention** | Medium | `FOR UPDATE SKIP LOCKED` is tested with one worker, never two competing |
| **The domain core** | **Lowest** | 99% coverage, property-tested. Two of the eight known defects came from here, both found by Hypothesis before they reached anything. |

---

## 6. Future evolution

Ordered by the ratio of value to what it would cost the existing design.

### 6.1 Tune the clustering constants against real data — *first, and by a distance*

Everything else assumes the grouping is right. Collect reports for a month, hand-label which
described the same event, and fit the radius and window to that. **The architecture already
supports it**: replay produces a new map with no migration and no data loss.

This is not a feature. It is the difference between a system that works and one that
appears to.

### 6.2 Extract the worker — *cheap, structural*

TD-01. The outbox already decouples it; this is a deployment change on a paid tier.

### 6.3 Real notification delivery — *the obvious next feature*

Today the gateway logs. SMS or push turns a demonstration into a product. The circuit
breaker, the idempotency keys and the at-least-once semantics were all built for a real
gateway, so the work is an adapter, not a redesign.

### 6.4 Reroute advisories — *deferred deliberately*

Currently "your route is affected". A real alternative needs a routing engine and full road
network data. Cut at scoping (`02-problem-and-scope.md` §4) and still the right call.

### 6.5 Ride-sharing — *the headline exclusion, and it should stay excluded*

The largest item in the original brief and the largest scope risk: matching, payments,
identity verification, passenger safety, insurance, liability. **It shares nothing with the
report pipeline.**

Worth stating plainly in a viva: this was not cut because there was no time. It was cut
because it is a second product wearing the same name, and building half of it inside this
one would have damaged both. If it is ever built it should be a separate system that reads
Nkwanta's incident feed through its public API.

### 6.6 What should never be added

**Direct emergency dispatch.** NFR-05. Not a scope decision — a liability one. A system
that appears to summon an ambulance and does not is worse than no system, and no amount of
engineering makes that safe. The escalation flag in a human-monitored queue is the correct
design, not a placeholder for something better.

---

## 7. Handover

A new maintainer, in order:

1. `README.md` — orientation
2. `HANDOFF.md`, **latest dated section first** — where things actually stand
3. `docs/02-problem-and-scope.md` — so they do not rebuild something deliberately cut
4. `docs/09-system-design.md` — how it fits together
5. `docs/05-decision-log.md` — why, when the design looks odd. Every entry is dated and
   none is ever rewritten; a reversed decision is superseded by a new entry, so the
   reasoning at the time survives.
6. `docs/08-technical-debt.md` — what is knowingly imperfect, before assuming a shortcut
   was an accident

Then `RUNBOOK.md` to get it running, and `pytest` to confirm it is intact.

**The rule that keeps this true:** every significant choice is dated and appended, never
edited. A maintainer reading a decision from three months ago is reading what was known
three months ago — which is the only way to judge whether it still holds.
