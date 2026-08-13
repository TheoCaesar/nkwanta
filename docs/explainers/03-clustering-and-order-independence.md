# Explainer 03 — Clustering and order independence

*Covers `app/clustering.py` and `tests/test_clustering_properties.py`.*
*This is the module that makes the project advanced rather than merely large.*

---

## 1. The question

Nineteen people report a jackknifed truck on the Spintex Road within four minutes.
Nobody tells the system it is one crash. It has to work that out from where and when
each report arrived.

Get it wrong and the map is a carpet of nineteen pins — worse than useless, because a
commuter cannot tell whether the road has one problem or nineteen.

---

## 2. The rule that must never break

> **The order reports arrive in must not change the result.**

If Kofi's report reaches the server before Ama's, or Ama's before Kofi's, the incident
must come out **identical**. Not similar — identical.

This is not a nicety. Over a mobile network, arrival order is effectively random: one
reporter is on 4G, another on failing 3G, and their reports overtake each other in
transit. If order changed the answer, two commuters could open the app and see genuinely
different maps of the same road, and neither would be wrong.

---

## 3. Why the obvious approach fails

The natural first attempt is **incremental**: when a report arrives, look for a nearby
incident, join it if there is one, otherwise start a new one.

That is order-dependent. Here is the counter-example, and it is in the test suite:

```
A ---------- B ---------- C
     200 m        200 m
        (A to C is 400 m)

Clustering radius: 300 m
```

**Arriving A, B, C:** A starts an incident. B is 200 m from A — joins. C is 200 m from
B — joins. **One incident.**

**Arriving A, C, B:** A starts an incident. C is 400 m from A — starts a *second*
incident. B now arrives and is within 300 m of both. Whichever it joins, the answer
differs from the first ordering.

The bug is not the tie-break. It is that incremental assignment asks *"what already
exists?"*, and what already exists depends on order.

**If asked in the viva, lead with this example.** It shows you found the failure mode
rather than avoided it by luck.

---

## 4. What we do instead

Recompute the whole grouping from the full set of reports, as a **graph problem**.

Draw an edge between two reports when all three hold:

1. same type — a flood and a collision at one junction are two events
2. within the distance limit
3. within the time window

Then the incidents are the **connected components** of that graph: the islands of
reports reachable from one another through some chain of links.

In the example above, A and C never link directly, but both link to B — so all three
sit in one component, whatever order they arrived in.

### Why this is order-independent, rigorously

The connected components of a graph **do not depend on the order the edges were added**.
That is a property of graphs, not a property of our implementation.

Two things make it hold here:

- **There is no "already exists" to consult.** The whole set is considered at once, so
  there is no prior state for order to influence.
- **The linking rule is symmetric** — `are_linked(a, b)` always equals
  `are_linked(b, a)`. This is load-bearing. An asymmetric rule would make the graph
  directed, and the argument would collapse.

This is **single-linkage agglomerative clustering**, computed with a **union-find**
(disjoint-set) structure.

---

## 5. Union-find, in plain terms

Two operations:

- `union(a, b)` — "these belong together"
- `find(a)` — "which group is this in?"

Start with everyone in their own group. For each linked pair, union them. At the end,
`find` tells you each report's group.

Both operations are effectively constant time, so the whole thing is fast.

The implementation includes two standard optimisations — path compression and union by
size. **Both change how quickly the answer is reached, never what it is.** That matters
here: an optimisation that altered the partition would silently break determinism.

---

## 6. The subtle bug: floating-point addition is not associative

This is the detail worth volunteering, because it shows the property test was taken
seriously rather than written to pass.

```python
(0.1 + 0.2) + 0.3   !=   0.1 + (0.2 + 0.3)
```

Both are 0.6 to any sane precision, but they differ in the final bit. Floating-point
addition is commutative but **not associative**.

The centroid of a cluster is the mean of its members' coordinates. Sum the same
coordinates in a different order and you can get a centroid differing by about
1e-16 degrees — a few nanometres on the ground. Physically meaningless.

**But the property test asserts results are identical, not nearly identical.** So it
would catch this, and it should: weakening the assertion to a tolerance would have
hidden a whole class of ordering bug behind an approximate comparison.

The fix is to **sort by report id before summing**. Addition order becomes a fact about
the data rather than about arrival sequence, and the result is bit-for-bit reproducible.

**If asked "why not just use a tolerance?":** "Because the property I am claiming is
that order does not matter. A tolerance would let order matter a little, and I would no
longer be testing the thing I wrote down."

---

## 7. The tests

Four properties, in order of importance. Hypothesis generates the cases.

| # | Property | What it catches |
|---|---|---|
| 1 | **Order independence** | The failure this module exists to prevent |
| 2 | **Partition** — every report in exactly one cluster | Lost reports (a warning never sent) and duplicated ones (inflated confidence) |
| 3 | **Separation** — no two clusters should have been one | Under-merging. Without it, "one cluster per report" would pass everything else |
| 4 | **Idempotence** — clustering twice changes nothing | Required for replay |

### Property 0: the tests actually test something

There is a fifth test, and the story behind it is worth telling.

The first version of the data generator scattered reports **uniformly** across the Accra
bounding box — roughly 22 km by 28 km. With at most 25 reports and a 300 m radius, two
of them almost never landed close enough to link.

Measured: **1 generated set in 300 contained any merge at all.**

Every property passed. That is precisely the problem — they were passing over
collections of singleton clusters, where order independence is trivially true and proves
nothing. **A test that passes for the wrong reason is worse than one that fails,**
because it buys confidence it has not earned.

The fix was to generate the way reality does: a few hotspots, with reports scattered
around them, jittered by up to twice the clustering radius so cases land on both sides
of the boundary. `test_the_generator_actually_produces_merges` now asserts that more
than half of generated sets contain a genuine merge, so the file cannot silently become
decorative again.

**If asked "how do you know your tests are any good?":** point at this. Most candidates
cannot answer that question at all.

### Running them

```bash
pytest                                  # 150 examples per property
HYPOTHESIS_PROFILE=dev pytest           # 50   — fast, for iterating
HYPOTHESIS_PROFILE=thorough pytest      # 1000 — for the testing report
```

---

## 8. Known limitation: chaining

Single-linkage clustering **chains**. A line of reports each 250 m from the next will
merge into one very long incident, even if the ends are kilometres apart.

That is a real weakness, it is inherent to single linkage, and it is in the debt
register rather than hidden.

**Why we accepted it:** the alternatives cost the property this module exists to
protect. Complete-linkage — requiring *every* pair within the radius — resists chaining
but is far more expensive and fragments genuine incidents that span a junction.
Density-based methods such as DBSCAN handle chaining well, but reintroduce parameters
that are just as unvalidated as the two we already have.

**The honest fix** is a maximum-diameter cap on a cluster, which needs care: enforcing
it during merging would reintroduce order dependence, so it has to be applied as a
post-pass that is itself order-independent. Recorded, not attempted under time pressure.

---

## 9. What is still provisional

The radius (300 m) and window (30 minutes) are **reasoned guesses with no data behind
them**. They are technical debt item TD-03, the highest priority on the register.

Too wide and two separate incidents merge, so the map lies. Too narrow and one incident
fragments, confidence never crosses the alert threshold, and the police are never told.
One pair of numbers governs both failure modes, and the right values almost certainly
differ between a dense junction like Circle and an open stretch of the Tema Motorway.

They are read from environment variables specifically so they can be tuned without a
redeploy.

---

## 10. The thirty-second summary

> Reports are grouped by treating it as a graph problem: an edge between two reports of
> the same type that are close in both place and time, and incidents are the connected
> components of that graph. I chose that over the obvious incremental approach because
> incremental assignment is order-dependent — three reports in a line 200 metres apart
> give one incident or two depending purely on arrival order. Connected components do
> not depend on edge insertion order, so the result is identical however reports arrive.
> I prove it with property-based tests that feed the same reports in hundreds of random
> orders and assert the output is bit-for-bit identical, which is also why centroids are
> summed in id order — floating-point addition is not associative.
