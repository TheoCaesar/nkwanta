# Explainer 04 — Confidence and time decay

*Covers `app/confidence.py` and `tests/test_confidence_properties.py`.*

---

## 1. The question

Clustering answers *which reports describe the same event*. This module answers the
harder one: **should anyone act on it?**

That matters because the system decides whether police are called. It cannot simply
believe what it is told. Some reports are honest mistakes. Some are fabricated by
someone who wants a rival's route flagged as blocked. And a report that was true forty
minutes ago may be describing a road that is now clear.

---

## 2. The model in one line

```
weight  = reputation × decay(age) × evidence_strength
confidence = 1 − ∏ (1 − weightᵢ)
```

Three inputs per report, combined by a formula called **noisy-OR**.

### The three inputs

| Input | Meaning | Range |
|---|---|---|
| **reputation** | How often this person's past reports proved true. New accounts start at 0.5 — neither trusted nor distrusted | 0 to 1 |
| **decay(age)** | Halves every 45 minutes. A flood reported four hours ago says little about that road now | 0 to 1 |
| **evidence_strength** | A ceiling on what any single report can contribute. Currently 0.45 | fixed |

**Why the ceiling exists.** Without it, one reporter with a strong record could verify
an incident alone — and corroboration is the entire point. With it, no single report can
ever reach the escalation threshold, so summoning police always requires more than one
person. That is directly tested by
`test_no_single_report_can_verify_an_incident_alone`.

---

## 3. Noisy-OR, and why not just add the weights

The obvious approach is to sum the weights. It is wrong twice over.

**It can exceed 1.** Ten reports at 0.2 each sum to 2.0, which is not a probability of
anything. You would then clamp it — and a model that needs clamping to stay legal is a
model that has stopped meaning something.

**It treats the hundredth report as worth as much as the second.** In reality the first
independent confirmation changes your mind completely; the fiftieth changes nothing.

Noisy-OR fixes both. Read it as probability:

> If report *i* is independently right with probability *wᵢ*, then the chance they are
> **all** wrong is ∏(1 − wᵢ). So the chance at least one is right is 1 − ∏(1 − wᵢ).

Three properties fall out for free, each one we actually need:

| Property | Meaning |
|---|---|
| **Bounded** | Always in [0, 1]. No clamping anywhere in the code |
| **Monotonic** | More evidence never lowers confidence |
| **Saturating** | Each further report adds less than the last |

And critically: **multiplication is commutative, so the answer does not depend on the
order reports arrive in** — the same guarantee as clustering, for the same reason.

---

## 4. Does it behave sensibly?

Confidence for *n* fresh reports, by reporter reputation:

| n | rep 0.30 | rep 0.50 | rep 0.80 | rep 0.95 |
|---:|---:|---:|---:|---:|
| 1 | 0.135 | 0.225 | 0.360 | 0.427 |
| 2 | 0.252 | 0.399 | 0.590 | 0.672 |
| 3 | 0.353 | 0.535 | 0.738 | **0.812** |
| 4 | 0.440 | 0.639 | 0.832 | 0.893 |
| 5 | 0.516 | **0.720** | 0.893 | 0.938 |
| 8 | 0.687 | 0.870 | 0.972 | 0.988 |

Thresholds: **0.35** corroborated, **0.70** verified (escalate to the dispatch queue).

Read across and the model does what it should:

- **One unknown reporter → 0.225.** Visible on the map as unconfirmed, alerts nobody.
- **Five ordinary reporters → 0.720.** Crosses the threshold; police are told.
- **Three consistently reliable reporters → 0.812.** Trusted people escalate faster,
  which is the whole reason for tracking reputation.
- **Discredited reporters (0.30) need eight or more.** Someone inventing road closures
  from home cannot get there alone.

### Decay of a single average report

| Age | Confidence |
|---|---|
| 0 min | 0.225 |
| 45 min (one half-life) | 0.113 |
| 90 min | 0.056 |
| 6 hours | 0.001 |
| 24 hours | ~0 |

**This is what makes incidents clear themselves.** Nobody presses a "resolved" button.
If nobody confirms a report, it fades below the stale threshold and leaves the map on
its own.

**If asked "why not a close button?":** because nobody would press it. Systems that
depend on users tidying up after themselves fill with rubbish. Making staleness
automatic is the engineering answer, and exponential decay has no arbitrary cliff — a
linear fade needs a cut-off point where evidence vanishes in one step, and an incident
disappearing at exactly 90 minutes is a discontinuity no reporter would recognise.

---

## 5. The score is explainable, not just a number

`score()` returns the per-report evidence alongside the total: which reporter, what
reputation, how old, what weight.

That is not decoration. It is what lets the interface show an officer *why* confidence
is 0.91 rather than presenting a number and asking for trust. **A score an officer
cannot interrogate is one they will learn to ignore**, and then the system has a
dashboard nobody uses.

It is also why `incident_reports.weight` exists as a stored column rather than being
recomputed on demand.

---

## 6. The honest weakness: independence

Noisy-OR assumes reports are **independent**. They are not.

Six people stuck in the same jam are not six independent observations — they are one
event observed six times, by people who may have seen each other's hazard lights, heard
the same radio bulletin, or seen the incident already on this very map.

This means confidence is **systematically overstated** when reports come from a crowd
rather than from genuinely separate observers.

Recorded as **TD-15**. Not hidden, and not solved: the honest fixes all need data the
system does not yet have. Discounting reports that arrive after an incident becomes
publicly visible would help; so would weighting by how spatially spread the reporters
are, since six reports from six different approach roads really are more independent
than six from one queue.

**If asked "is your model correct?":** "No. It is a defensible approximation with a
known bias, and I can tell you the direction of the bias and what I would need to fix
it. The parameters are guesses fitted to no data, which is why they are environment
variables rather than constants."

---

## 7. What the numbers are, and what they are not

Every constant here — the 45-minute half-life, the 0.45 evidence strength, the 0.35 and
0.70 thresholds — is a **reasoned guess fitted to no data**. There is no historical
incident corpus to calibrate against, and none could be obtained inside the examination
window.

They are read from environment variables so they can be tuned in production without a
redeploy. They are recorded as TD-04.

The thing that *can* be defended is the **shape** of the model: bounded, monotonic,
saturating, decaying, order-independent. Those are structural properties, they are
proved by the property tests, and they hold whatever the constants turn out to be.

---

## 8. The thirty-second summary

> Each report contributes evidence equal to its reporter's reputation, multiplied by an
> exponential time decay with a 45-minute half-life, multiplied by a cap that stops any
> single report verifying an incident alone. Those are combined with noisy-OR —
> one minus the product of one minus each weight — which reads as "the probability that
> at least one reporter is right". That formula is bounded, monotonic and saturating
> without any clamping, and because multiplication is commutative it is independent of
> arrival order, same as the clustering. Decay is what lets stale incidents leave the
> map without anyone closing them. The known weakness is that noisy-OR assumes
> independence and six people in one jam are not independent, so confidence is
> systematically overstated for crowds — that is recorded as technical debt with the
> direction of the bias stated.
