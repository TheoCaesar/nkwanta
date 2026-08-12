# The Advanced Concept, Explained Simply

*Last updated: 12 August 2026*

The exam requires an advanced software engineering concept. This document explains ours
without assuming any specialist vocabulary. Every technical term used here also has a
full entry in [`03-glossary.md`](03-glossary.md).

---

## 1. Start with the problem, not the solution

Imagine it is 6:40 on a Tuesday morning. A tipper truck has jackknifed on the Spintex
Road. Over the next four minutes, nineteen people report it through the app.

Four hard questions fall out of that one sentence.

**Question one — are these nineteen reports about one crash or nineteen crashes?**
Nobody tells the system. It has to work it out from where each report came from and when.
Get this wrong and the map is a useless carpet of pins.

**Question two — is it real at all?**
Maybe two of the nineteen are mistaken. Maybe one is a fabrication by someone who wants a
rival's route blocked. The system decides whether police get called, so it cannot simply
believe whatever it is told.

**Question three — what if the server crashes at the wrong moment?**
Suppose it saves a report and then dies before warning anyone. The report sits in the
database looking perfectly healthy. No one is warned. No error is logged. Nobody ever
finds out. This is the worst kind of failure — the silent kind.

**Question four — what if two people's reports arrive in a different order for different
users?**
One person is on good 4G, another on failing 3G. Reports overtake each other in transit.
If the order changes the answer, two commuters open the app and see two different versions
of the same road.

Any student can build a form that saves a report to a database. Answering these four
questions is what makes the system genuinely engineered.

---

## 2. The concept in one sentence

> Reports are permanent records; Incidents are calculated from them by grouping reports
> that are close in place and time, weighted by how much each reporter has been trusted
> before and faded out as they age — with saving and notifying bound together so neither
> can happen without the other, and every notification carrying a unique key so a repeat
> attempt cannot warn anyone twice.

The rest of this document unpacks that sentence in four pieces, one per question above.

---

## 3. Piece one — reports are permanent, Incidents are calculated

Most student projects would create a table called `incidents` and update rows in it. We do
not. We keep two quite different things.

**Reports** are what people actually told us. Each one is written once and never changed —
a permanent note saying "this person said this thing, here, at this time." Even a report
later shown to be false stays exactly where it is. We add a new note recording the
contradiction rather than erasing history.

**Incidents** are our current best interpretation of those reports. They are worked out by
reading through the reports and grouping them.

The bank statement analogy is exact. A bank does not store your balance as a fact it edits.
It stores every transaction, permanently, and works the balance out. Your balance is a
*view*, not a record.

**What this buys us.** If we later discover our grouping rule was too aggressive, we fix
the rule, re-read every report and produce a corrected map. Nothing was lost, because we
never threw the raw material away. If we had been editing an `incidents` table all along,
the original reports would be gone and the mistake would be permanent.

It also means an officer can ask "why was a warden sent to Achimota at 07:12?" and get an
exact answer: these six reports, from these people, in this order.

*Terms: [event](03-glossary.md#event), [append-only log](03-glossary.md#append-only-log),
[projection](03-glossary.md#projection).*

---

## 4. Piece two — grouping by place and time, weighted by trust

### Grouping

Two reports join the same Incident when all three hold:

1. they are the same **type** (a flood and a crash are never the same event)
2. they are within a set **distance** of each other
3. they are within a set **time window** of each other

Both distance and time are needed. Two crashes at Circle on Monday and Friday share a
location but are obviously separate. Two reports 15 km apart in the same minute are
obviously separate too. Only the combination identifies one real-world event.

*Term: [spatio-temporal clustering](03-glossary.md#spatio-temporal-clustering).*

### Trust

Each Incident carries a **confidence** score, and each user carries a **reputation** score.

Confidence rises as independent reports join the cluster — but not equally. A report from
someone whose past reports have consistently been confirmed moves the needle more than one
from an unknown account. Reputation itself moves with outcomes: confirmed reports raise it,
contradicted ones lower it.

Confidence also **decays**. A report of a flood from four hours ago says very little about
that road right now, so its contribution shrinks steadily until it stops counting at all.

This gives three useful behaviours, none of which needed a human:

- one anonymous report is shown as unconfirmed and does not alert anybody
- six independent reports from trusted users cross the threshold and reach the police
- an unconfirmed report nobody else sees fades off the map by itself

**Why decay rather than a "close incident" button?** Because nobody would ever press it.
Systems that depend on users tidying up after themselves fill with rubbish. Making
staleness automatic is the engineering answer.

*Terms: [corroboration](03-glossary.md#corroboration),
[reputation score](03-glossary.md#reputation-score), [time decay](03-glossary.md#time-decay).*

---

## 5. Piece three — saving and notifying cannot come apart

Here is the naive version, and it is what most submissions will do:

```
1. save the report to the database
2. send notifications to affected users
```

The gap between line 1 and line 2 is a trap. Crash there and the report is saved and
nobody is ever told. Nothing looks wrong. No error appears anywhere. For a system whose
entire purpose is warning people, this is a failure that destroys the product while
appearing perfectly healthy.

The fix is to make saving and "remember to notify" a single indivisible database write:

```
1. in ONE database transaction:
     - save the report
     - save a note-to-self: "notifications still owed for this report"
2. a separate background worker reads the notes-to-self,
   sends each notification, and ticks it off
```

Because step 1 is one transaction, the database itself guarantees you get both parts or
neither. There is no gap left to crash in. And if the worker dies mid-way, the unticked
notes are still sitting there when it restarts.

The list of notes-to-self is called an **outbox** — like a tray of letters waiting to be
posted. Hence the name of the pattern.

*Terms: [transactional outbox](03-glossary.md#transactional-outbox),
[transaction](03-glossary.md#transaction).*

### The duplicate problem this creates

Retrying safely raises a new question. If the SMS gateway does not answer, we genuinely
cannot tell whether the message went out. So we resend — better a duplicate warning than
none. That is a deliberate choice called
**[at-least-once delivery](03-glossary.md#at-least-once-delivery)**.

To stop users receiving the same alert three times, every notification carries a unique
reference. The sender records which references it has already handled and silently discards
repeats. Send it five times, the user is warned once. That property is called
**[idempotency](03-glossary.md#idempotency-and-idempotency-keys)** — like a lift call button,
where pressing repeatedly still summons exactly one lift.

Finally, if the gateway fails repeatedly we stop calling it entirely for a cooling-off
period, then let one test call through to see if it has recovered. Without this, a dead SMS
provider takes our whole system down with it: every request queues up waiting to time out
until nothing else can get through. That is a
**[circuit breaker](03-glossary.md#circuit-breaker)**, and it is easy to demonstrate live.

---

## 6. Piece four — the property that must never break

> **The order reports arrive in must not change the final result.**

If Kofi's report reaches the server before Ama's, or Ama's before Kofi's, the Incident must
end up identical. Not similar. Identical.

This is not a nicety. Over mobile networks, arrival order is effectively random. If order
mattered, two commuters could open the app and see genuinely different maps of the same
road, and neither would be wrong.

Two well-known mathematical properties are what make this true, and the merge rule must
satisfy both:

- **commutative** — order does not matter, the way `2 + 3` equals `3 + 2`
- **associative** — grouping does not matter, the way `(2 + 3) + 4` equals `2 + (3 + 4)`

This is the same reasoning behind
**[CRDTs](03-glossary.md#crdt-conflict-free-replicated-data-type)**, the family of data
structures designed so that independently-updated copies always end up agreeing without
anyone arbitrating. We are not building a full CRDT, but the design follows the same logic,
and saying so shows the choice was reasoned rather than accidental.

*Term: [order independence / convergence](03-glossary.md#order-independence-and-convergence).*

---

## 7. How we prove it, rather than assert it

This is where the concept earns its marks, because the property above can be **tested**
rather than merely claimed.

Ordinary testing writes examples by hand: "given these three reports, expect one incident."
The weakness is obvious — you wrote the three reports, so you only ever test the cases you
already thought of. The bug you did not think of survives.

**Property-based testing** inverts this. You state a rule that must always hold, and the
tool invents hundreds of random scenarios trying to break it. When it finds a failure it
automatically shrinks it to the smallest version that still fails — often two reports and a
timestamp — so the cause is immediately visible.

Three properties will be tested this way, using Hypothesis:

| # | Property | In plain terms |
|---|---|---|
| 1 | Order independence | Feed the same reports in any order; the Incidents produced are always identical. |
| 2 | No overlapping Incidents | No two Incidents of the same type ever occupy the same place and time. If they did, they should have been one. |
| 3 | Replay equals stored state | Rebuilding the map from scratch off the raw reports reproduces exactly what is currently stored. |

Property 1 is the centrepiece and the one to lead with in the viva.

*Term: [property-based testing](03-glossary.md#property-based-testing).*

---

## 8. Where the shortcuts are

Being able to say precisely how your own design falls short is worth more marks than
pretending it does not. These are deliberate, recorded, and each has a known fix.

| Shortcut taken | Why | What it costs | Fix |
|---|---|---|---|
| Announcements handled inside the app rather than through a dedicated queue | No time to run Redis or Kafka in 48 hours | Cannot scale past one server | Move to Redis Streams |
| The map is updated during the request, not in the background | Simpler, and fast enough at this size | Report submission is slower than it needs to be | Move the projector to a worker |
| No periodic "totals so far" markers | Not needed at a few thousand reports | Rebuilding gets slower as reports accumulate | Add snapshots every 1,000 events |
| Distance and time-window values hardcoded | No real data yet to tune them against | Wrong in dense traffic vs open highway | Make them configurable per road class |
| Reputation formula is a reasoned guess, not a validated model | No historical data exists to fit one | Accuracy unknown | Validate against real outcomes after launch |
| Background worker has no way to say "slow down" | Not reachable at expected volumes | Could fall behind during a citywide flood | Add backpressure and a dead letter queue |

Full register with causes, impacts and priorities: `06-technical-debt.md` *(to be written
during the build)*.

---

## 9. The thirty-second version, for the viva

If asked "what is advanced about your project?", say this:

> Reports are permanent records that are never edited. Incidents are calculated from them
> by grouping reports close in place and time, weighted by how reliable each reporter has
> proven to be, and fading out as they age. Saving a report and queuing its notifications
> happen in one database transaction, so a crash can never save a report that nobody is
> warned about. Notifications carry unique keys, so retrying cannot warn anyone twice. And
> the whole merge is order-independent — I prove it with property-based tests that feed the
> same reports in hundreds of random orders and assert the result never changes.

Then stop talking and let them ask.
