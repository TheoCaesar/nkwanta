# Explainer 06 — The lifecycle state machine and reputation

*Covers `app/lifecycle.py`, `app/reputation.py`, `app/services/dispatch.py`.*

---

## 1. The five states

```
reported ──▶ corroborated ──▶ verified ──▶ assigned ──▶ resolved
    ◀────────────┴───────────────┘            │
     (confidence falls as well as rises)      └──▶ verified   (unassign)
```

The distinction that matters is not the order — it is **who causes each move**.

| Kind | States | Caused by |
|---|---|---|
| **Computed** | reported, corroborated, verified | Confidence. Moves both ways as reports arrive and decay |
| **Decided** | assigned, resolved | A person did something |

Keeping these apart is what stops a decaying confidence score quietly un-assigning a
warden who is already standing at the junction. The reports that summoned them are
*supposed* to decay; that says nothing about whether the road is still blocked.

This is why the projector (explainer 05) captures assignment before a rebuild and carries
it across, rather than recomputing it.

---

## 2. Rules as data, not as `if` statements

Every legal move lives in one dictionary:

```python
RULES = {
    Action.ASSIGN:   Rule(source={VERIFIED},  target=ASSIGNED, roles={OFFICER, ADMIN}),
    Action.UNASSIGN: Rule(source={ASSIGNED},  target=VERIFIED, roles={OFFICER, ADMIN}),
    Action.RESOLVE:  Rule(source={ASSIGNED},  target=RESOLVED, roles={WARDEN, OFFICER, ADMIN}),
}
```

**Anything absent is illegal by construction.** There is no code path to forget.

The alternative — checking "was this incident ever assigned?" in each route handler — is
how the third handler someone adds becomes the one that forgets. Here a new endpoint
cannot forget, because the rules are not in the endpoint.

**If asked why:** "It turns a class of bug into an impossibility rather than into
something I have to remember. And it makes the machine readable in one screen, which
matters more than it sounds — a state machine you have to reconstruct by reading five
handlers is one nobody will reason about correctly."

### Two constraints worth defending

**You cannot assign an unverified incident.** If an officer could dispatch to anything,
the escalation threshold would be decoration. If something matters and confidence is low,
the answer is more corroboration, not a lower bar.

**You cannot resolve an incident nobody was sent to.** Otherwise the queue could be
cleared by wishful thinking. Resolution means *someone went and looked*, and that is
precisely what makes it usable as evidence about the reporters.

---

## 3. The interface is driven by the same rules

`allowed_actions(status, role)` returns what this person can do to this incident, and the
interface offers exactly that. A button that would be refused is never shown.

A property test asserts `allowed_actions` agrees with what `next_status` actually
permits, for every combination of state, action and role. If they drifted apart, a user
would be offered a button that then refuses them — which is a worse experience than not
offering it.

---

## 4. Reputation: closing the loop

Until this point reputation was a number that never moved. Confidence weighted every
report by its reporter's standing, but nothing ever changed that standing.

**Resolving an incident is the only place reputation changes**, and it is why resolution
records an outcome rather than just a time:

- **Confirmed** — a warden attended and the incident was real. Everyone who reported it
  is vindicated.
- **False alarm** — a warden attended and found nothing. Everyone who reported it is
  contradicted.

Both directions are necessary. If an incident could only ever be confirmed, reputation
could only rise, and fabricating a report would cost its author nothing.

### The formula

```
reputation = (confirmed + 2) / (confirmed + contradicted + 4)
```

This is the mean of a **Beta posterior** — the standard Bayesian estimate of a
probability from successes and failures. In plain terms: start everyone at a coin flip,
and give that starting assumption the weight of two imaginary confirmed reports and two
imaginary contradicted ones. Real outcomes then pull the number away from 0.5.

**Why not simply `confirmed / (confirmed + contradicted)`?**

Because one confirmed report would give **1.0** — total trust from a single lucky guess —
and one contradicted report would give **0.0**, permanent damnation from one mistake.

The first is an attack: file one true report, become fully trusted, then fabricate. The
prior closes it.

### What the numbers actually do

| Confirmations | Reputation |
|---:|---:|
| 0 (new account) | 0.500 |
| 1 | 0.600 |
| 3 | 0.714 |
| 5 | 0.778 |
| 10 | 0.857 |
| 20 | 0.917 |

Trust is **expensive to build** — around eighteen consecutive confirmations to pass 0.9.
And it is lost faster than it is gained: five confirmations reach 0.778, but three false
alarms after that drop it to 0.583. That asymmetry is deliberate. The cost of a false
report must exceed the benefit of a true one, or fabricating is profitable in
expectation.

### Two floors that matter

**Reputation never reaches 0.** A reporter at exactly zero could never recover — every
report they filed would carry zero weight, so none could ever be confirmed. That is a
trap with no exit, and an unjust one, since a road can genuinely clear before a warden
arrives.

**Reputation never reaches 1.** Nobody is certain.

### One confirmation per person, not per report

The reporters are collected with `DISTINCT`. Filing six reports about one incident earns
one confirmation, not six — otherwise the fastest route to a high reputation would be to
spam, and reputation would measure enthusiasm rather than reliability.

---

## 5. Who may do what

| Action | Roles | Extra check |
|---|---|---|
| Assign | officer, admin | Target must be an active warden |
| Unassign | officer, admin | — |
| Resolve | warden, officer, admin | **A warden may only resolve an incident they were sent to** |

That last check is enforced in `dispatch.resolve`, not in the state machine, because it
depends on the specific incident rather than on the state. Without it any warden could
clear the entire queue from a phone, and the assignment step would mean nothing.

A commuter can do none of these. A property test asserts `allowed_actions` returns an
empty list for a commuter in every state.

---

## 6. What is deliberately missing

| Missing | Why |
|---|---|
| Reopening a resolved incident | `resolved` is terminal. A road blocked again is a new event with new reports, which the clustering will pick up on its own |
| An audit trail of who did what | The incident holds only its current state. Recorded as a gap — the outbox pattern would carry it naturally |
| Notifying a warden they have been assigned | The outbox can carry this; the sink is still log-only |
| Time limits on an assignment | A warden who never resolves leaves the incident assigned indefinitely |

---

## 7. The thirty-second summary

> An incident has five states. The first three are computed from confidence and move in
> both directions as reports arrive and decay; the last two are decided by a person and
> arithmetic never touches them, which is why a rebuild carries assignment across rather
> than recomputing it. The legal moves live in one table, so anything not listed is
> impossible by construction rather than by remembering to check. An incident cannot be
> assigned unless it is verified, and cannot be resolved unless someone was sent — which
> is what makes resolution usable as evidence about the reporters. Resolving is the only
> place reputation moves: confirmed vindicates every reporter, false alarm contradicts
> them. The formula is a Beta posterior with a prior worth two observations each way, so
> one lucky report cannot buy total trust and one mistake is not fatal — and trust is
> deliberately lost faster than it is earned, so fabricating is not profitable in
> expectation.
