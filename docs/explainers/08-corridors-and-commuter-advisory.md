# Explainer 08 — Corridors and the commuter advisory

*Covers `app/services/advisory.py`, `app/routers/corridors.py`, the `Corridor`,
`CorridorSubscription` and `Notification` models, and `incidents.cluster_key`.*

---

## 1. What this completes

Everything before this served the control room. This is what a member of the public gets
back for reporting.

It is also the first time the outbox delivers something a **user** can see. Until now it
faithfully carried instructions that only rebuilt internal state.

```
incident crosses 0.35
     └─▶ projection writes ONE outbox row        (cheap, same transaction)
             └─▶ worker matches corridors        (expensive, in the background)
                     └─▶ one notification per subscriber
                             └─▶ GET /notifications
```

---

## 2. A corridor is a line, not a point

`Corridor.path` is a **LINESTRING** in geography coordinates.

"Is this incident on my route?" is a question about **distance from a line**, and PostGIS
answers it directly: `ST_DWithin(corridor.path, incident.centroid, 250)` is true when the
incident is within 250 metres of *any point along* the road, measured in metres, using the
GiST index.

The obvious alternative — a centre point with a radius — cannot answer it. The Tema
Motorway is roughly 20 km long; a circle large enough to cover it would cover half of
Accra and every incident in the city would match.

**If asked why users pick from a list rather than drawing their own route:** drawing needs
a routing engine and full network data. Fifteen named Accra roads cover most journeys and
could be built now. It is in the backlog as a real limitation, not dressed up as a
preference.

---

## 3. Two thresholds, on purpose

| Action | Confidence needed |
|---|---|
| Warn commuters who follow the road | **0.35** (corroborated) |
| Put it in the dispatch queue | **0.70** (verified) |

This looks inconsistent and is not. **The two decisions have different costs.**

Sending a warden to nothing wastes a person who was needed at a real junction. Telling a
commuter about something that turns out to be clear costs them a glance at the map.

When the price of being wrong differs by that much, the threshold should differ too. A
single threshold would either spam wardens or leave commuters uninformed about things the
system already half-believes.

It is still above a single report — one report from an average account scores about 0.225,
so nobody's unsupported word warns a whole corridor.

---

## 4. Why the fan-out happens in the worker

The projector could look up subscribers itself. It must not.

A busy corridor might have thousands of followers. Doing that work inside the request that
accepted a report would make **submission slow in proportion to how popular the road is** —
the system would be at its slowest exactly when an incident matters most.

So the projector writes **one small row** saying "this incident deserves an advisory", and
the worker turns it into however many notifications are required. Submission stays fast and
constant-time; the expensive part happens where being slow is harmless.

This is the same reasoning as the original outbox decision, applied one level further out.

---

## 5. The identity problem, and `cluster_key`

This one is subtle and worth understanding, because getting it wrong would have produced a
bug that only appears after the second report.

**Incident rows are deleted and recreated on every rebuild.** The projector does not update
incidents; it throws away the affected ones and rebuilds them from their reports, because
a new report can merge two previously separate incidents (explainer 05).

So `incidents.id` is **useless as an identity**. A notification keyed on it would be
orphaned by the very next report to arrive nearby, and the same commuter would be warned
again about the same jam.

`cluster_key` is the smallest contributing report id. It survives rebuilds because cluster
membership is order-independent — the minimum member id is a property of *which reports
belong together*, not of when they arrived or which row currently represents them.

Everything that needs to remember an incident keys on this: the notification uniqueness
constraint, and the advisory's own idempotency key.

**If asked:** "The primary key identifies a row. The cluster key identifies the *event*.
They are different things, and only the second is stable, because rows are derived data
and the event is not."

---

## 6. Warned once, however many times we try

Delivery is at-least-once, so the worker may process the same advisory repeatedly — after a
crash, a retry, or a rebuild that re-queues it.

Two constraints make that survivable, and both use `ON CONFLICT DO NOTHING` rather than
catching an error:

| Level | Constraint | Effect |
|---|---|---|
| Outbox | `uq_outbox_idempotency_key` on `incident.advisory:{cluster_key}` | The same incident queues one advisory, ever |
| Notification | `uq_notifications_once_per_incident` on `(user_id, incident_key)` | Each person is warned once about each incident |

**Why `ON CONFLICT DO NOTHING` rather than catching `IntegrityError`:** a raised constraint
violation aborts the surrounding transaction. Inside the worker that would take the rest of
the batch down with it, so one duplicate advisory would discard every notification queued
behind it. Letting PostgreSQL skip the row keeps the transaction alive.

Note also that no "has it already crossed the threshold?" check exists anywhere. The
idempotency key does that work. Tracking previous state would mean storing it, and the
state is rebuilt from scratch every time — so the constraint is both simpler and more
reliable than the bookkeeping would have been.

### One person, one warning, even following two roads

A commuter following both Ring Road and Achimota–Circle, when an incident sits on both,
is one person and hears once. The fan-out de-duplicates by user before inserting, keeping
the first corridor so the message can still name a road.

---

## 7. What a commuter actually reads

> *Flooding on Spintex Road — reported by more than one person.*

Confidence appears **in words, not as a number**. "0.42" means nothing to someone deciding
whether to leave early; "reported by more than one person" tells them what they need. The
number is still on the incident for anyone who wants it.

The wording is also mapped per incident type — "Traffic lights out", not
"A signal_outage", which would leak an internal identifier into a user's notification.

---

## 8. What is deliberately missing

| Missing | Why |
|---|---|
| Push or SMS delivery | The sink is still the database. TD-08 — the outbox, idempotency and retry are all real; only the final adapter is a stub |
| Quiet hours | "Only warn me between 6 and 9 am" is an obvious next step and pure scope |
| Draw your own route | Needs a routing engine and network data. Backlog |
| Advisory when an incident **clears** | Arguably as useful as the warning. Nothing currently emits on resolution |
| Distance or direction of travel | Everyone following a road hears, even those 15 km away heading elsewhere |

That fourth row is the one worth volunteering — a system that tells you a road is blocked
and never tells you it is clear trains people to ignore it.

---

## 9. The thirty-second summary

> Commuters follow named roads, stored as PostGIS linestrings, so "is this incident on my
> route" is a distance-from-a-line query rather than a guess at a radius. When an incident
> crosses 0.35 the projector writes a single outbox row; the worker matches corridors and
> fans out one notification per subscriber. The fan-out is in the worker because a popular
> road has many followers, and doing it during report submission would make the system
> slowest exactly when an incident matters most. Commuters are warned at 0.35 but police
> are only called at 0.70, because the cost of being wrong differs — a wasted warden versus
> a wasted glance. Everything keys on a stable cluster key rather than the incident's
> primary key, because incident rows are deleted and rebuilt on every report, and unique
> constraints with ON CONFLICT DO NOTHING mean a replayed advisory warns nobody twice.
