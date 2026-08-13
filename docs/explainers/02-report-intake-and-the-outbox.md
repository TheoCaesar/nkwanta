# Explainer 02 — Report intake and the transactional outbox

*Covers `app/services/reports.py`, `app/routers/reports.py`, `app/geo.py`.*
*This is the most important module in the submission. If you learn one explainer, this
one.*

---

## 1. The bug this exists to prevent

Here is what almost every first attempt looks like:

```python
save_report_to_database(report)     # line 1
send_notifications(report)          # line 2
```

Now imagine the server dies between line 1 and line 2. Power cut, deploy, crash,
anything.

The report is saved. It sits in the database looking completely healthy. Nobody is
warned. **No error is raised, nothing is logged, and no one ever finds out.**

For a system whose entire purpose is warning people, that is the worst possible
failure — it destroys the product while appearing to work perfectly. A loud failure
gets fixed. A silent one does not.

**The instinct to resist:** "make the gap smaller." You cannot. Small is not zero, and
at scale a one-in-ten-thousand window happens every day.

---

## 2. The fix: no gap at all

Instead of narrowing the window, remove it. Write both facts in **one database
transaction**:

```
BEGIN
  INSERT INTO reports (...)      -- what happened
  INSERT INTO outbox  (...)      -- "someone still needs telling"
COMMIT
```

PostgreSQL guarantees a transaction is all-or-nothing. There is no instant at which the
report exists and the instruction to act on it does not. The crash either happens before
the commit, in which case neither row exists, or after it, in which case both do.

A separate worker reads the outbox afterwards, does the actual sending, and ticks each
row off. If the worker dies mid-way, the unticked rows are still sitting there when it
restarts.

The table is called an **outbox** for the obvious reason — it is a tray of letters
waiting to be posted.

**If asked "why not just use a message queue?":** because then you have the same problem
one layer along — the database write and the queue publish are two systems, and there is
no transaction spanning both. You would be back to a crash window. The outbox works
precisely because the instruction lives in the *same database* as the data.

---

## 3. What the code actually does

`submit_report()` in `app/services/reports.py`:

```
1. validate            -- coordinates, timestamps. No database touched.
2. check idempotency   -- have we already seen this key?
3. build the Report
4. session.add(report)
5. session.add(outbox_message)     <-- both queued, nothing written yet
6. await session.commit()          <-- THE atomic moment. Both, or neither.
```

Steps 4, 5 and 6 are marked with a comment block in the source saying not to move them.
That is not decoration — inserting a `commit()` between the two `add()` calls would
silently reopen the exact window this design closes, and every test would still pass
except one.

### The test that guards it

`test_report_and_outbox_are_added_before_a_single_commit` records the order of
operations on a stubbed session and asserts:

- the report was added before any commit
- the outbox row was added before any commit
- there was **exactly one** commit

**If asked "how do you know the transaction is really atomic?":** "The database
guarantees atomicity — that is what a transaction is. What my test guarantees is that
my code actually puts both writes inside one. Those are different claims and the second
is the one I can get wrong."

---

## 4. Idempotency: why a retry cannot double-count

A phone on a struggling 3G connection sends a report. The response is lost. The phone
retries. Without protection you now have two reports of one accident, and the incident's
confidence has been inflated by a network glitch.

The client sends an `idempotency_key` — any unique string per report. The database has a
unique constraint on it.

There are **two** defences, and it is worth knowing why both exist:

| Defence | What it does | Why alone it is not enough |
|---|---|---|
| The `SELECT` before insert | Fast path for an obvious repeat | Two simultaneous retries both pass it |
| The unique constraint | Actually prevents the duplicate | Only fires at insert time, as an error |

The `SELECT` is an optimisation. **The constraint is the correctness.** When the
constraint fires we catch the `IntegrityError`, roll back, re-read the row the other
request committed, and return that — so the caller gets a sensible answer rather than a
500.

This is a **race condition**, and the pattern is worth naming: check-then-act is never
safe on its own. Only the database, which serialises the writes, can settle it.

### The outbox key is derived, not random

```python
idempotency_key=f"report.submitted:{report.id}"
```

Deterministic on purpose. If intake were ever replayed for the same report, it would
produce the same key and the unique constraint would refuse to enqueue the work twice.
A random UUID would have quietly created a second job.

---

## 5. Validation, and the coordinate trap

### The (longitude, latitude) problem

**PostGIS points are `POINT(longitude latitude)`. Everyday speech is "lat, long".**

They are backwards from each other, because PostGIS orders coordinates as `(x, y)` and
longitude is the x axis.

Accra is 5.60 N, −0.19 E. Swap them and you get 0.19 N, 5.60 E — a point in the Gulf of
Guinea roughly 600 km offshore. **Nothing crashes.** Every query runs, every index
works, every answer is wrong.

So the conversion lives in exactly one function, `to_wkt_point(lat, lon)` in
`app/geo.py`, which takes arguments in the human order and emits the PostGIS order. It
is directly tested.

The Ghana bounding-box check is the safety net: if coordinates are swapped, the result
lands outside Ghana and the report is rejected with a message that names the likely
cause.

### Timestamps

| Rule | Why |
|---|---|
| Not more than 2 minutes in the future | Phone clocks drift. Two minutes is drift; an hour is a lie or a bug. |
| Not more than 24 hours old | Older than that is history, not traffic information — and it would pollute clustering, which assumes reports arrive near the time they describe. |
| Naive timestamps assumed UTC | Ambiguous input resolved by a stated rule. Guessing the server's local zone would make behaviour change with deployment region. |

**Two clocks, again.** `occurred_at` is what the reporter claims and may be wrong.
`received_at` is our server clock and cannot be. Clustering uses `occurred_at`; auditing
uses `received_at`.

---

## 6. Who can do what

| Route | Who | Why |
|---|---|---|
| `POST /reports` | Any signed-in user | Reporting is the one thing everybody must be able to do. The system is worthless if the people who can see the problem cannot tell it. |
| `GET /reports/mine` | The owner | Your own submissions |
| `GET /reports` | Officers and admins only | **Raw reports are restricted.** A commuter sees incidents on the map, never other people's individual submissions — that would expose who reported what and where, which is exactly the harassment vector NFR-4 exists to prevent. |

That last row is worth volunteering in a viva. It shows the privacy requirement was
carried into the route design rather than written down and forgotten.

---

## 7. What is deliberately missing

| Missing | Why | Status |
|---|---|---|
| Rate limiting on submission | Arrives with the abuse controls | Debt, scheduled |
| Clustering triggered here | It runs from the outbox worker, so submission stays fast | By design |
| Photo and voice attachments | Coming in the media module | Planned |
| Reputation updated on submit | Only outcomes change reputation, and the outcome is not known yet | By design |

---

## 8. The thirty-second summary

> Submitting a report writes two rows in one transaction: the report itself, and an
> outbox row saying notifications are owed for it. Because it is one transaction, the
> database guarantees both or neither — so the system can never accept a report that
> nobody is warned about, which is the silent failure that would destroy this product.
> A background worker drains the outbox afterwards. Reports carry an optional
> idempotency key with a unique constraint behind it, so a retry on a bad connection
> returns the original report instead of inflating an incident's confidence with a
> duplicate. Coordinates are converted to PostGIS order in exactly one tested function,
> because swapping latitude and longitude moves Accra into the sea without raising
> anything.
