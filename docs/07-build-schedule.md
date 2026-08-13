# Build Schedule — 40 Hours Remaining

*Written 12 August 2026, with 40 hours left on the examination clock.*
*Derived from [`06-effort-estimation.md`](06-effort-estimation.md). Hours are relative to
"now" — slide the sleep block to align with your actual night.*

---

## 1. The budget

| | Hours |
|---|---:|
| Wall clock remaining | 40.0 |
| Sleep (one block, non-negotiable) | −7.0 |
| Meals and breaks | −2.0 |
| **Effective working time** | **31.0** |
| — of which build | 21.6 |
| — of which documentation | 7.0 |
| — of which buffer | 2.4 |

**Buffer is 2.4 hours, about 6%.** That is thin. It is only survivable because the cut list
in §5 is agreed in advance, so falling behind triggers a lookup rather than a decision.

**Selected tier: Tier 0, lean.** Tier 1 and Tier 2 are not attempted. See
[`06-effort-estimation.md`](06-effort-estimation.md) §4.

---

## 2. Hosting — settled, and simpler than planned

You have no accounts. That turned out to be useful, because building the plan around what is
actually free removed a whole component.

| Service | Purpose | Cost | Notes |
|---|---|---|---|
| **GitHub** | Source repository | Free | Required by the paper. Sign up first — the others authenticate through it. |
| **Neon** | PostgreSQL + PostGIS | Free, no card | 0.5 GB storage, 100 compute-hours/month, never expires. PostGIS enabled with `CREATE EXTENSION postgis;` |
| **Render** | FastAPI service | Free | 512 MB RAM, 0.1 CPU, 750 instance-hours/month |
| ~~Vercel~~ | ~~Front end~~ | — | **Dropped.** See D-012. |

### Vercel is no longer needed

The front end is one static HTML page. FastAPI can serve it directly via `StaticFiles`. That
removes an account, a deployment target, a build pipeline and all CORS configuration — for
free, because a single page does not benefit from a separate host.

### Two Render constraints that change the design

**One — free services sleep after 15 minutes of inactivity, and take 30–60 seconds to wake.**

This is a grading risk, not a technical one. An examiner clicks your link, waits a minute, and
concludes the application is broken. Three mitigations, all cheap:

1. State it plainly at the top of `Deployment_and_Source_Links.txt`: *"This is a free-tier
   deployment. The first request after a period of inactivity may take up to 60 seconds while
   the instance wakes. Subsequent requests are immediate."*
2. Set a free keep-warm ping (cron-job.org or similar) hitting `/health` every 10 minutes.
3. Load the site yourself before any scheduled demo or viva.

**Two — one free service means the outbox worker cannot be a separate process.**

A separate Render background worker is a paid feature. The outbox drainer therefore runs
in-process as an `asyncio` background task inside the API service. This is a real
architectural compromise, it is forced by a real constraint, and it produces one of the
strongest entries in the technical debt register. See D-013.

---

## 2a. What the B numbers mean

**B stands for "build task".** `B01` to `B22` are the task identifiers from the
bottom-up estimate in [`06-effort-estimation.md`](06-effort-estimation.md) §4 — the
breakdown that produced the hour figures.

They are used as a single vocabulary across the whole project so that an estimate, a
schedule entry, a commit message, a debt item and a test can all refer to the same
piece of work without ambiguity:

| Where | Example |
|---|---|
| Estimate | `B04 — report intake, 3.6 h` |
| Schedule | hours 4.5 – 8.1, marked ★ protected |
| Commit | `B04: report intake with transactional outbox` |
| Test file | `tests/test_report_intake.py` — "B04 — report intake" |
| Debt register | "taken at B01" |

The numbers are **not** sequential in time — they were assigned when the breakdown was
written, and the schedule reorders them. B22 (the web page) is built before B10 (the
circuit breaker), because value and risk order the work, not the numbering.

**If asked in the viva:** "They are task identifiers from my bottom-up effort estimate.
Using the same label in the estimate, the schedule, the commit history and the debt
register means any one of those can be traced to the others."

---

## 3. The schedule

★ marks protected work — the advanced concept. **Nothing here may be cut.** Total 13.6 hours.

| Hours | Task | Dur | |
|---|---|---:|---|
| 0.00 – 0.75 | Accounts: GitHub repo, Neon project + PostGIS, Render service | 0.75 | |
| 0.75 – 2.50 | **B01** Scaffold FastAPI + SQLAlchemy + Alembic → **deploy empty app live** | 1.75 | |
| 2.50 – 3.70 | **B02** Data model + migrations: users, reports, incidents, outbox | 1.20 | |
| 3.70 – 4.50 | **B03** Auth: seeded users, JWT, three roles | 0.80 | |
| 4.50 – 8.10 | **B04** Report intake — validation + event + outbox row in ONE transaction | 3.60 | ★ |
| 8.10 – 8.60 | Break / meal | 0.50 | |
| 8.60 – 13.10 | **B05** Clustering consumer — spatio-temporal grouping via PostGIS | 4.50 | ★ |
| 13.10 – 14.60 | **B19a** Property test: order-independence | 1.50 | ★ |
| 14.60 – 16.10 | **B06** Confidence + exponential time decay | 1.50 | ★ |
| 16.10 – 17.00 | Buffer / debug | 0.90 | |
| 17.00 – 18.00 | Meal, wind down | 1.00 | |
| **18.00 – 25.00** | **SLEEP** | **7.00** | |
| 25.00 – 27.50 | **B09** Outbox worker in-process + idempotency keys | 2.50 | ★ |
| 27.50 – 28.00 | **B18** Seed data: ~20 Accra junctions and corridors | 0.50 | |
| 28.00 – 29.20 | **B22** Single page: map, report form, incident queue | 1.20 | |
| 29.20 – 29.70 | Break | 0.50 | |
| 29.70 – 30.50 | **B19b** Property test: no overlapping incidents | 0.80 | |
| 30.50 – 31.50 | **B21** Deploy verification, credentials, live smoke test, keep-warm ping | 1.00 | |
| 31.50 – 33.00 | Design diagrams: architecture, use case, class, sequence, ER | 1.50 | |
| 33.00 – 35.00 | SRS | 2.00 | |
| 35.00 – 36.00 | Testing report + finalise technical debt register | 1.00 | |
| 36.00 – 36.80 | User manual | 0.80 | |
| 36.80 – 38.00 | Consolidated project documentation + PDF assembly | 1.20 | |
| 38.00 – 38.50 | `Deployment_and_Source_Links.txt` + package ZIP | 0.50 | |
| 38.50 – 40.00 | Final buffer + submit to Sakai | 1.50 | |

### Why this order

**Deploy an empty application at hour 2.5.** Deployment is worth 3 marks and is pass-or-fail —
an application that does not deploy scores zero on implementation regardless of code quality.
Doing it first, with nothing in it, converts the single largest project risk into a solved
problem while there is still time to solve it. Every subsequent push is then a small,
verifiable increment.

**Hardest work first, while rested.** B04 and B05 carry the highest learning multipliers (1.8)
and together are 8.1 hours. They are scheduled before sleep, when there is still room to
recover from a wrong turn.

**The property test sits immediately after clustering, not at the end.** It is the thing that
proves the concept works, and it will find bugs in B05. Writing it while B05 is still fresh in
mind is much cheaper than returning to it at hour 35.

**Documentation is last but not squeezed.** Seven hours are reserved. Much of it draws on work
already written — scope, glossary, concept, decisions and estimation are done, which is why
seven hours is enough for what is normally a much larger job.

---

## 4. Do this before hour 0

Fifteen minutes, and it removes the schedule's biggest unknown:

1. Create the GitHub repository — public, or private with examiner access
2. Sign up to **Neon** (GitHub login, no card), create a project, run `CREATE EXTENSION postgis;`
3. Sign up to **Render** (GitHub login), confirm you can create a free web service
4. Save the Neon connection string somewhere safe
5. Record your **student ID** and **project title** — needed for the submission package

If Neon or Render fails at this stage, that is the moment to find out, not at hour 30.

---

## 5. Cut triggers — decided now, applied without deliberation

Check against the schedule at hours 13, 25 and 31. If you are behind, cut in this order and do
not re-litigate.

| If behind by | Cut | Saves |
|---|---|---:|
| 1 hour | Second property test (B19b) — keep order-independence, it is the important one | 0.8 |
| 2 hours | Single page → serve the FastAPI generated API documentation as the interface | 1.2 |
| 3 hours | Auth → single shared bearer token per role, no JWT | 0.5 |
| 4 hours | Seed data → 5 junctions instead of 20 | 0.3 |
| 5+ hours | Confidence decay → static confidence, decay documented as designed-not-built | 1.0 |

**Never cut B04, B05 or B09.** If those are at risk, cut documentation polish instead — a
rougher document describing a working concept beats a polished document describing an absent
one.

Every cut taken goes straight into the technical debt register with its cause. That is worth
6 marks, and a cut you documented reads entirely differently from a feature you simply
did not finish.

---

## 6. Build order within the code

1. `models.py` — users, reports, incidents, outbox. Four tables, no more.
2. Alembic migration, applied against Neon. Verify PostGIS responds.
3. `POST /reports` — validate, write the report event and the outbox row in one transaction.
   **This one endpoint is the heart of the submission.**
4. `clustering.py` — pure functions, no database. Takes reports, returns incident groupings.
   Pure because that is what makes it property-testable.
5. The projector that calls it and persists the result.
6. `confidence.py` — also pure. Score plus exponential decay.
7. `worker.py` — asyncio task draining the outbox, honouring idempotency keys, logging sends.
8. `GET /incidents` — the map feed.
9. `index.html` — one page, MapLibre, a form, a list.
10. `test_properties.py` — Hypothesis. Order-independence first.

Keeping steps 4 and 6 as pure functions with no database access is not stylistic. It is what
allows Hypothesis to generate thousands of cases in seconds, and it is the reason the testing
section will have real evidence in it.
