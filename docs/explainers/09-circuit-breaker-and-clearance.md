# Explainer 09 — The circuit breaker, and telling people a road is clear

*Covers `app/circuit_breaker.py`, `app/gateway.py`, `app/services/staleness.py`, and the
clearance half of `app/services/advisory.py`.*

---

## Part one — the circuit breaker

### 1. The problem it exists to prevent

Your application sends notifications through an SMS provider. **The provider goes down.**

Every send now waits thirty seconds for a timeout before failing. With fifty
notifications queued that is twenty-five minutes of your system doing nothing but
waiting — holding connections, occupying workers, starving everything else.

**Someone else's outage has become your outage.**

That is the failure. Note that it is not a correctness problem: every individual piece of
code is behaving exactly as written. The system fails because a slow dependency consumes a
resource nobody was counting.

### 2. Three states

The name is literal — it is the fuse box. A breaker trips to protect the house, and can be
reset.

```
CLOSED     normal. Calls go through.
    │  (too many failures in a row)
    ▼
OPEN       tripped. Calls fail INSTANTLY, without trying.
    │  (cooling-off period elapses)
    ▼
HALF_OPEN  testing. ONE call is allowed through.
    │                      │
    │ (it worked)          │ (it failed)
    ▼                      ▼
 CLOSED                   OPEN
```

Walked through with a three-failure threshold and a thirty-second reset:

```
07:00:00  closed     start
07:00:00  closed     failure 1
07:00:00  closed     failure 2
07:00:00  open       failure 3        <- tripped
07:00:10  open       still refusing instantly
07:00:30  half_open  will allow one test call
07:00:31  open       test call failed -> open again
07:01:02  half_open  another 30s - test again
07:01:02  closed     test call worked -> back to normal
```

### 3. Four decisions worth defending

**Consecutive failures, not total.** A success resets the count to zero. Scattered
failures over a long period are a blip; five in a row is an outage. Counting totals would
trip the breaker eventually no matter how healthy the provider was.

**One failure re-opens from half-open.** Not another five. The test call was the entire
point and it told us the provider is still down — waiting for four more failures means
four more thirty-second timeouts to learn what we already know.

**Rejections are counted separately from failures.** A rejection is not a failure; nothing
was attempted. Conflating them would make the failure count meaningless the instant the
breaker opens.

**The clock is a parameter, not a call.** `state(now)`, `record_failure(now)`. This is what
makes the whole thing testable: a thirty-second cooling-off period is verified by passing a
timestamp thirty seconds later. **A test suite that waits thirty seconds to check a
thirty-second timeout is a test suite nobody runs**, and one nobody runs is one that stops
being true.

That last point generalises. Every module in this project that involves time —
`confidence`, `clustering`, `staleness`, this — takes `now` as an argument. None of them
read a clock.

### 4. What the breaker is actually guarding

`app/gateway.py` defines a port with two implementations: `LoggingGateway`, which writes
to the log, and `ControllableGateway`, which can be told to fail.

The second exists **for the demonstration**, and saying that plainly is better than
dressing it up. A circuit breaker whose behaviour cannot be shown is a paragraph in a
document. One that can be tripped live, on request, in thirty seconds, is evidence.
Recorded as TD-21: it must not exist in a real deployment.

**A gateway failure does not lose a notification.** The row is already in the database and
the user will see it in the application. Delivery is an optional extra on top — which is
precisely why it is safe to give up on quickly.

### 5. Demonstrating it

```
POST /admin/gateway/fail       break it deliberately
POST /admin/drain              generate some deliveries
GET  /admin/gateway            watch failures climb, then state: open
POST /admin/gateway/heal       bring the provider back
GET  /admin/gateway            still open — it waits out the cooling-off period
   (30 seconds)
GET  /admin/gateway            half_open, then closed after the next success
```

The pause after `heal` is worth pointing at: a provider that has just come back should not
immediately be hit with everything that queued up while it was down.

---

## Part two — telling people the road is clear

### 6. A defect the advisory revealed

Building the advisory exposed something that had been wrong since B06 and was not visible
until then.

**Confidence is calculated when reports arrive, and stored. It does not decay in the
database.** Decay is applied at the moment of calculation, and calculation only happens
during a rebuild, which only happens when a new report lands nearby.

So an incident reported once at 07:00 and never mentioned again keeps its 07:00 confidence
**forever**. It sits on the map at 0.22 at midnight, hours after it decayed to nothing in
principle. The decay described in explainer 04 was real in the arithmetic and applied to
nothing that was sitting still.

Two possible fixes. Recompute on every read — which makes the map query expensive and its
results depend on when you asked. Or sweep periodically, which is what `staleness.py` does:
every five minutes the worker asks which incidents have gone quiet long enough to have
faded, writes the decayed confidence down, and clears them.

The sweep uses **time since the newest report** rather than recomputing the full noisy-OR.
After eight half-lives — six hours at the default — the strongest possible single
contribution has shrunk by a factor of 256, which is below the stale threshold from any
starting point. It is an approximation, it errs towards keeping incidents slightly too
long, and that is the right direction to err.

**It only touches incidents in a computed state.** An incident an officer has assigned is a
human decision, and a warden already at the junction must not be stood down because the
reports that summoned them decayed.

### 7. Three ways a road stops being a problem

| Reason | What happened | What the commuter reads |
|---|---|---|
| `resolved` | A warden attended, the road is clear | "Flooding on Spintex Road has been cleared." |
| `false_alarm` | A warden attended and found nothing | "Flooding reported on Spintex Road could not be found — the road is clear." |
| `expired` | Nobody ever confirmed it; it aged out | "Flooding reported on Spintex Road was never confirmed and has been removed." |

Distinguishing the second from the first matters. "We fixed it" and "there was nothing
there" are different facts, and a commuter deciding how much to trust the *next* warning
deserves to know which one they got.

### 8. The audience is the audience of the warning

The clearance goes to **exactly the people who were warned**, taken from the notifications
already sent rather than recomputed from corridors.

Two reasons, and the second is the one that would have bitten.

It guarantees consistency: nobody is told a road has cleared when they were never told it
was blocked.

And it survives change. An incident's centroid **moves** as reports accumulate — the
clustering recomputes it every rebuild. Recompute the corridor match at clearance time and
you may reach a different set of people, leaving some commuters permanently believing a
road is still shut. The set that was warned is a fact; the set that would match now is a
recalculation, and they are not the same thing.

### 9. Queued in the same transaction as the resolution

`dispatch.resolve` writes the clearance outbox row inside the transaction that marks the
incident resolved — for exactly the reason report intake writes its outbox row alongside
the report.

A crash between "resolved" and "told everyone" would leave commuters permanently believing
a road is blocked. That is worse than never having warned them, because it teaches people
the warnings are wrong.

**A system that reports blockages and never reports clearances trains people to ignore
it.** That is why this exists at all, and it was a gap in the design until it was pointed
out in review.

---

## 10. The thirty-second summary

> The circuit breaker stops the system calling a provider that is clearly down. Five
> consecutive failures and it opens: further calls fail in microseconds instead of waiting
> thirty seconds each, so a dead SMS gateway cannot exhaust our workers and turn someone
> else's outage into ours. After a cooling-off period it allows exactly one test call, and
> a single failure re-opens it — the test call was the point. The clock is passed in as an
> argument, so a thirty-second timeout is tested by passing a timestamp thirty seconds
> later rather than by sleeping. On the clearance side: building the advisory revealed that
> stored confidence never decays on its own, so a periodic sweep fades out incidents nobody
> confirmed and tells whoever was warned that the road is clear — sent to exactly the
> people who received the original warning, because the incident's centroid moves and
> recomputing the audience would reach a different set.
