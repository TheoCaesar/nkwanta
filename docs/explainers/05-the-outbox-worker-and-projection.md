# Explainer 05 — The outbox worker and the projection

*Covers `app/worker.py`, `app/services/projection.py`, `app/routers/incidents.py`.*
*This is where the pure modules finally connect to the running system.*

---

## 1. What this completes

Explainer 02 described half the transactional outbox: intake writes a report and an
instruction in one transaction, so the instruction can never be lost.

This is the other half — the thing that picks the instruction up and acts on it. Until
now, `POST /reports` had been faithfully writing outbox rows that nothing ever read.

```
POST /reports  ──▶  report row  +  outbox row      (one transaction, B04)
                                      │
                                      ▼
                            OutboxWorker claims it                (B09)
                                      │
                                      ▼
                    fetch the affected neighbourhood
                    run clustering (B05) and confidence (B06)
                    write incidents
                                      │
                                      ▼
                       GET /incidents  ──▶  the map
```

---

## 2. Why rebuild rather than update

When a report arrives, the projector does **not** work out which incident it belongs to
and add it. It deletes the affected incidents and rebuilds them from their reports.

That sounds wasteful. It is the only correct option.

A new report can **merge two incidents that were previously separate** — the
three-in-a-line case from explainer 03. Two clusters exist, a report arrives between
them, and now they are one. An algorithm that only ever appends a report to an existing
incident can never discover that.

Rebuilding is also what makes the replay property true: incidents are derived data, and
can always be reconstructed from the reports alone.

**If asked "isn't that expensive?":** "Yes, and it is bounded. I rebuild only the
neighbourhood that could have changed, not the whole map. The cost is real and it is
recorded as TD-14 with a fix that does not disturb the ordering guarantee."

---

## 3. The neighbourhood, and the trap in it

Rebuilding *everything* on every report would be correct and far too slow. So the
projector fetches only what could have changed:

**Step 1 — reports of the same type near the new one**, using `ST_DWithin` on the
geography column, which measures in metres and uses the GiST index. The search radius is
three times the clustering radius, because two reports further apart than the radius can
still end up in one incident by chaining through others.

**Step 2 — expand to whole incidents.** For every report found in step 1, also fetch
every other report in any incident it belongs to.

Step 2 is easy to miss and essential. Without it you can pull in half of an existing
incident, rebuild that half, and the other half simply vanishes — its reports were never
in the working set, so no cluster was produced for them. Expanding to whole incidents
keeps the operation closed: everything that goes out comes back.

---

## 4. Human decisions survive the rebuild

A rebuild deletes incidents and recreates them. If an officer has assigned a warden to
an incident, that assignment must not be destroyed because someone filed another report.

So before demolishing anything, the projector captures the status, assignee and
resolution time of any incident in the `assigned` or `resolved` state, keyed by the
**cluster key** — the smallest member report id. Because cluster membership is
order-independent, that key is stable across rebuilds, so the decision can be matched
back to the incident it belonged to.

**The principle:** confidence can compute `reported`, `corroborated` and `verified`.
`assigned` and `resolved` are human acts and are never reached by arithmetic. The
projector carries them across rather than recomputing over them.

---

## 5. The worker loop

```
every 2 seconds:
    claim a batch of up to 20 unprocessed rows
    for each: run its handler, mark it processed
    commit once for the whole batch
```

### Five decisions worth defending

**It runs in-process.** An asyncio task inside the API, not a separate service — because
Render's free tier permits one service. A genuine compromise forced by a genuine
constraint, recorded as TD-01 with its real costs: it cannot scale independently and it
dies when the API restarts. The class takes a sessionmaker and has no dependency on
FastAPI's request context, so extracting it later is a move rather than a rewrite.

**`FOR UPDATE SKIP LOCKED`.** Rows another worker is holding are stepped over rather than
waited on. With one worker this changes nothing; with several it is what stops two
grabbing the same row. Writing it correctly now costs nothing and means the extraction in
TD-01 needs no rethink.

**One commit per batch, not per row.** A crash mid-batch replays the whole batch. The
alternative — committing each row — could leave a row marked processed while its effects
were rolled back, which is exactly the split-brain the outbox exists to prevent.

**One bad row does not block the batch.** Failures are recorded on the row and the loop
moves on. Head-of-line blocking would mean a single poison message silently stops every
warning behind it.

**An exception never kills the loop.** If it did, every notification after it would be
lost with no error and no way to notice — the silent failure this whole design exists to
prevent.

### Retry and abandonment

Delivery is at-least-once, so failures are retried. After five attempts a row is left
alone: still in the table, unprocessed, with its error recorded. It is not deleted and
not retried forever.

That is a dead letter queue in the crudest possible form. TD-06 covers the real one, with
alerting and a replay path.

---

## 6. Seeing the result

| Endpoint | Who | Notes |
|---|---|---|
| `GET /incidents` | Everyone, including signed-out | The map feed. Faded incidents drop out by confidence, not by deletion |
| `GET /incidents/queue` | Officers and admins | Above the verification threshold, most believable first |
| `GET /incidents/{id}` | Everyone | **The evidence screen** — contributing reports and the weight each carried |

Note the asymmetry: **incidents are public, individual reports are not.** A commuter must
be able to check the road ahead; showing who reported what and where is the harassment
vector NFR-4 exists to prevent.

`GET /incidents/{id}` is the one worth demonstrating. It shows *why* confidence is what
it is — which reporters, how reliable, how recent, how much each counted. A score an
officer cannot interrogate is one they will learn to ignore, and then you have a
dashboard nobody uses. This is also why `incident_reports.weight` is a stored column
rather than recomputed on read.

---

## 7. Testing this needed a real database

Every other module is tested against pure functions and stubs. That is fast and catches
most things, and it cannot catch what only a real database can:

- is `ST_DWithin` actually measuring metres, or degrees?
- does the geography column round-trip latitude and longitude the right way round?
- do the cascade deletes behave?

So `tests/test_integration_pipeline.py` exercises the whole chain against real PostGIS,
and **skips automatically when `DATABASE_URL` is unset** so the suite still passes on a
machine with no database.

Two of those tests earn their keep on their own:

- *a distant report forms its own incident* — 8 km apart must never merge, which proves
  `ST_DWithin` is in metres. A geometry column instead of geography would silently
  compare degrees and this would fail.
- *coordinates survive the round trip* — if latitude and longitude were swapped going
  into the column, the centroid lands in the Gulf of Guinea and nothing else in the suite
  would notice.

Everything created is deleted afterwards, including when an assertion fails.

---

## 8. The thirty-second summary

> The worker drains the outbox rows that report intake has been writing. For each one it
> fetches the reports that could have been affected — near in space and time, then
> expanded to whole incidents so a rebuild cannot split one — runs the pure clustering
> and confidence functions over them, and rewrites those incidents. It rebuilds rather
> than updates because a new report can merge two previously separate incidents, which
> an append-only algorithm could never discover. Human decisions like assignment are
> captured before the rebuild and carried across, keyed by a cluster identity that is
> stable because membership is order-independent. It runs in-process as an asyncio task
> because the free hosting tier allows one service, which is recorded as technical debt
> with the extraction path already prepared.
