# Decision Log

*Every significant choice, dated, with the alternatives considered and the reason.*

Newest entries at the top. **Never edit an old entry.** If a decision is reversed, add a new
entry that supersedes it and mark the old one.

Format: what was decided, what else was considered, why, and what it costs.

---

## 13 August 2026 — front end and interface design

### D-038 — Avatars are initials; nobody uploads a profile photograph

**Decided:** Every avatar is initials on a disc, coloured deterministically from the user
id. There is no profile photograph upload for any role.

**Considered:** photographs for everyone, which is what users expect; and a staff-only
variant where wardens and officers upload one but commuters keep initials.

**Why:** A face attached to a name that already appears in an officer's evidence list
makes a reporter easier to identify, and **NFR-4a exists precisely to prevent that** — it
is the same requirement that defaults voice notes to private. No decision the system makes
is improved by knowing what a reporter looks like, so it is personal data with no
operational purpose. It would also add binary to PostgreSQL, already the debt most likely
to fail first under adoption (TD-19), and create a moderation burden with no moderator.

The staff-only variant was genuinely defensible — a warden is public-facing and
recognition helps an officer assigning one — and was set aside as complexity for a gain
the system does not need.

**Costs.** Looks less conventional than a product with photographs. Mitigated by treating
initials as a designed element rather than a placeholder, so the interface reads as
finished.

---

### D-037 — No front-end framework; native ES modules, no build step

**Decided:** The rebuilt interface uses native ES modules, plain CSS with custom
properties, and no bundler. If reactivity becomes unwieldy, Alpine.js from a CDN — still
no build.

**Considered:** React or Vue, which is the default expectation for an interface of this
quality.

**Why:** A framework requires a build step, which means Node in the deployment pipeline —
either a separate host, undoing D-012, or a build stage on Render. Deployment is worth 3
marks and is pass-or-fail, and that risk buys nothing the design needs: "modern and high
quality" is a consistent spacing scale, a restrained type scale, semantic colour tokens,
real loading and empty states, and sparing motion. None of that is a framework feature.

Native modules provide components and imports with zero tooling, and the deployed artefact
stays exactly what it is in the repository — which also makes it easier to explain.

**Costs.** More manual DOM work, and state synchronisation must be written rather than
inherited. Acceptable at roughly eight views.

---

### D-036 — The front-end budget was revisited late, and that was an error

**Decided:** Rebuild the interface to match the scope the API had already reached.

**Why this is recorded as a mistake rather than a plan:** D-010 cut the front end to 1.2
hours because implementation carried only 10 of 48 marks. That was correct under the
original constraint. When the deadline extended and the observed build rate proved far
higher than estimated (D-017), scope was revisited for the officer workflow, voice notes,
corridors and the circuit breaker — **and the front-end budget was not revisited with
them.** The API grew to Tier 2 while the page stayed at Tier 0.

The result was an interface with no role differentiation, no profile, no photo upload
despite a tested endpoint for it, and no validation worth the name. It was raised in
review by the author, not noticed by me.

**The lesson, stated plainly:** when a constraint that produced a decision changes, every
decision derived from it needs revisiting, not just the ones currently being worked on.

**Costs.** A full interface rebuild late in the schedule. Mitigated by building alongside
the existing page rather than replacing it, so a working demonstration exists throughout.

---

## 13 August 2026 — C circuit breaker and clearance

### D-035 — Every time-dependent module takes `now` as an argument

**Decided:** `circuit_breaker`, `confidence`, `clustering` and `staleness` all receive the
current time as a parameter. None of them calls `datetime.now()`.

**Considered:** reading the clock where it is needed, which is shorter.

**Why:** It is what makes time-dependent behaviour testable at all. A thirty-second
cooling-off period is verified by passing a timestamp thirty seconds later, in
microseconds. **A test suite that waits thirty seconds to check a thirty-second timeout is
one nobody runs, and one nobody runs stops being true.**

It also removes a whole class of flakiness. A test that reads the clock passes or fails
depending on when it happens to execute.

**Costs.** Slightly more verbose call sites, and one place — the worker loop — still has to
read the clock, because something must. That boundary is where the impurity is confined,
deliberately.

---

### D-034 — A circuit breaker guards the outbound gateway

**Decided:** Five consecutive failures open the breaker for thirty seconds, after which a
single test call is allowed. One failure from half-open re-opens immediately.

**Considered:** simple retry with backoff and no breaker.

**Why:** Retry alone does not solve the actual failure. When a provider is down, each
attempt costs a thirty-second timeout, so fifty queued notifications become twenty-five
minutes of the worker doing nothing but waiting — holding connections and starving
everything else. **Someone else's outage becomes ours.** The breaker converts a
thirty-second wait into a microsecond refusal.

Consecutive rather than total failures, because scattered failures are a blip and a total
counter would eventually trip on a healthy provider. One failure from half-open rather than
another five, because the test call was the point and four more failures means four more
thirty-second timeouts to learn what we already know.

**Costs.** While open, notifications are not delivered — but they are **not lost**: the
rows are already in the database and users see them in the application. Delivery is the
optional extra, which is exactly why giving up on it quickly is safe.

The demonstration gateway that can be told to fail is real debt (**TD-21**) and must not
survive to production.

---

### D-033 — A clearance goes to the people who were warned, not to a recomputed audience

**Decided:** When an incident is resolved or ages out, the clearance notification is sent
to exactly the users who received the original advisory, read from the notifications
already stored.

**Considered:** recomputing corridor matches at clearance time, which needs no extra
lookup.

**Why:** Two reasons, and the second would have bitten.

Consistency: nobody should be told a road has cleared when they were never told it was
blocked.

And an incident's centroid **moves** as reports accumulate — clustering recomputes it every
rebuild. Recomputing the match at clearance time could therefore reach a different set of
people, leaving some commuters permanently believing a road is shut. The set that was
warned is a fact; the set that would match now is a recalculation, and they are not the
same thing.

The clearance outbox row is written in the same transaction as the resolution, for the same
reason intake writes its outbox row alongside the report: a crash in between would leave
commuters believing a road is blocked forever, which is worse than never having warned
them.

**Costs.** A clearance for an incident whose advisory was never delivered reaches nobody,
which is correct. Three separate wordings to maintain — resolved, false alarm, expired —
because "we fixed it" and "there was nothing there" are different facts and a commuter
judging whether to trust the next warning deserves to know which.

**Prompted by review:** the gap was noticed when the author asked why the system only ever
reports blockages. A system that never reports clearances trains people to ignore it.

---

## 13 August 2026 — B corridors and commuter advisory

### D-032 — Incidents carry a stable cluster key separate from their primary key

**Decided:** `incidents.cluster_key` holds the smallest contributing report id. Anything
that needs to remember an incident across time — notifications, advisory idempotency keys
— references that rather than `incidents.id`.

**Considered:** keying on the primary key; making the projector update incidents in place
so ids survive.

**Why:** The projector deletes and recreates incident rows on every rebuild, because a new
report can merge two previously separate incidents and an append-only algorithm could never
discover that (D-020, explainer 05). Consequently `incidents.id` identifies *a row*, not
*an event*, and a notification keyed on it would be orphaned by the very next nearby
report — the same commuter warned twice about the same jam.

The cluster key survives because cluster membership is order-independent, so the minimum
member id is a property of which reports belong together rather than of when they arrived.
Updating in place was rejected because it reintroduces exactly the order dependence D-020
exists to eliminate.

**Costs.** One more column, and a second identity concept to explain. Backfilled with
`gen_random_uuid()` for existing rows, which is safe only because incidents are fully
derived and every rebuild overwrites it.

---

### D-031 — Advisory fan-out happens in the worker, not the projector

**Decided:** When an incident crosses the advisory threshold the projector writes **one**
outbox row. The worker matches corridors and creates one notification per subscriber.

**Considered:** looking up subscribers directly in the projector, which is fewer moving
parts.

**Why:** A busy corridor may have thousands of followers. Fanning out inside the request
that accepted a report would make submission slow in proportion to a road's popularity —
**the system would be slowest exactly when an incident matters most**. One small row keeps
submission constant-time and moves the expensive work to where being slow is harmless.

The same reasoning as the original outbox decision, applied one level further out.

**Costs.** A second event type and handler, and a rebuilt incident may briefly exist before
its advisory is processed. Bounded by the poll interval, two seconds.

---

### D-030 — Commuters are warned at 0.35; police are called at 0.70

**Decided:** Advisory notifications fire at the corroborated threshold. Dispatch still
requires verified.

**Considered:** one threshold for both, which is simpler to explain.

**Why:** The two decisions carry different costs of being wrong. Sending a warden to
nothing wastes a person who was needed at a real junction; telling a commuter about
something that turns out to be clear costs them a glance at a map. A single threshold
either spams wardens or leaves commuters uninformed about things the system already
half-believes.

The advisory threshold still sits above a single report — one report from an average
account scores about 0.225 — so no individual's unsupported word warns a whole corridor.

**Costs.** Some advisories will be about incidents that never reach verification, which is
the intended trade rather than a defect. Two thresholds to keep straight, both named
constants rather than literals.

**Not yet addressed:** nothing tells a commuter when a road *clears*. A system that reports
blockages and never reports clearances trains people to ignore it. Recorded as a gap.

---

## 13 August 2026 — F voice notes

### D-027 — Centroids use fsum and are clamped to their bounding box

**Decided:** `clustering.centroid` computes the mean with `math.fsum` and clamps the
result to the minimum and maximum of the values it averaged.

**Considered:** leaving it; widening the property test to a tolerance.

**Why:** A property test failed on three *identical* longitudes whose mean came out one
unit in the last place below the minimum input. Nothing overflows — the exact mean is not
representable in binary floating point, and the nearest representable value sits outside
the input range.

Physically femtometres, and meaningless. As an invariant it was false, and a centroid
escaping its own members' bounding box is the sort of thing that violates a database
constraint two years later, in a stack trace nobody can explain.

Widening the assertion to a tolerance was rejected for the same reason it was rejected in
D-020: the property being claimed is exact, and an approximate test claims something
weaker than the documentation does.

**Costs.** `fsum` is marginally slower than `sum`. Irrelevant at cluster sizes measured in
tens.

**Worth recording separately:** no example-based test would have found this. It needs
several identical coordinates with an unlucky bit pattern, which nobody writes by hand.
This is the concrete answer to "what did property-based testing actually buy you" — a real
invariant violation in code that had been passing, reviewed and deployed for several
sessions.

---

### D-026 — Recorded evidence raises a report's weight, but is capped

**Decided:** A report carrying a voice note or photograph is weighted 1.25× in the
confidence calculation, with the result capped at the existing single-report ceiling of
0.45.

**Considered:** treating attachments as presentation only, with no effect on confidence.

**Why:** A recording is materially harder to fabricate from an armchair than a tapped
coordinate — it demonstrates the reporter was somewhere with something to describe. That
is genuine evidence and ignoring it would waste it.

The cap is what keeps it honest. A weighted report still cannot reach the 0.70 escalation
threshold alone, so corroboration remains the only route to verification. Without the cap,
"attach any audio file" becomes a way of buying credibility. The bonus also *multiplies*
reputation rather than replacing it, so a discredited account cannot restore its standing
by attaching audio.

**Costs.** One more constant fitted to no data (TD-04). One extra query per rebuild to
find which reports carry evidence — batched across the whole neighbourhood, not per
report. `score()` gained an optional parameter, chosen over a required one specifically so
that all 53 existing confidence property tests were unaffected; a test asserts both paths
agree when no evidence is present.

---

### D-029 — The reporter decides who hears their recording — supersedes D-028

**Decided:** Attachments carry an `is_public` flag, set by the reporter at upload and
changeable by them at any time. Default off. A shared recording plays for anyone,
including signed-out visitors. An unshared one plays only for its owner and the control
room, and is omitted entirely from listings rather than merely refused.

**What was wrong with D-028.** Two things, and the first is an error of reasoning rather
than of judgement.

It **conflated two different privacy concerns**. NFR-4 protects the *reported party* —
the person being accused. D-028 applied it to the *reporter*. Those are different, and
the second does not follow from the first: a flood on Spintex Road accuses nobody, so
there is no reported party to protect and the justification simply did not apply.

It also **discarded most of the value of capturing voice**. "Tipper truck across two
lanes, backed up to Odorna" tells a commuter far more than *accident, confidence 0.88*.
Locking that away made the feature almost pointless for the people it was built for.

**Why consent rather than a blanket rule either way.** The concern is real but *narrow*.
It bites on accusatory reports — naming a trotro driver, reporting a violation — where a
speaker may be recognised by the person they accused. It does not bite on flooding. No
single rule fits both, and the reporter is the only person who knows which case they are
in. So they are asked.

Consent is **withdrawable**, and only the reporter may change it — not even an officer.
Consent somebody else can give on your behalf is not consent, and consent that cannot be
withdrawn is not a choice.

**Costs.** One column, one migration, one more thing for a client to display. Existing
attachments default to private, because they were uploaded with no opportunity to consent
and retroactively publishing them would be exactly what this column exists to prevent.

**What this does not solve.** A reporter who wants to help but does not want their voice
public still has to choose between the two. The real resolution is **transcription** —
publish the text, restrict the audio, and nobody has to choose. That has been moved from
"nice to have" to the top of the evolution plan as a direct consequence.

**Credit where due:** this was raised in review by the author, who asked why other users
should be denied information that would help them judge an incident. The original
reasoning did not survive the question.

---

### D-028 — Attachment playback is restricted; incidents remain public

> **Superseded by D-029 on 13 August 2026.** The reasoning below conflated protecting a
> reported party with protecting a reporter, and cost more transparency than it needed
> to. Retained unedited, because a decision log that quietly deletes its mistakes is not
> a record of anything.

**Decided:** Incident data is public. Attachment bytes are readable only by the person who
uploaded them and by the control room. An unauthorised request returns 404, not 403.

**Considered:** making attachments as public as the incidents they belong to.

**Why:** **A voice recording identifies its speaker.** It is closer to biometric data than
to a text note. NFR-4 exists because a system where people report one another to the
police is a harassment vector, and audio is exactly what would expose a reporter.

404 rather than 403 because a 403 confirms the attachment exists, which is itself
information about somebody else's report.

**Costs.** A commuter cannot hear the evidence behind an incident they are looking at,
which is a real loss of transparency. Accepted: the alternative exposes reporters, and
between transparency and safety this system chooses safety — the same reasoning that put
NFR-4 in the SRS in the first place.

---

## 13 August 2026 — B08 lifecycle and reputation

### D-025 — Reputation is a Beta posterior, not a success ratio

**Decided:** `reputation = (confirmed + 2) / (confirmed + contradicted + 4)`, floored at
0.02 and capped at 0.98. Updated only when an incident is resolved, once per reporter
regardless of how many reports they filed.

**Considered:** a plain success ratio; a fixed increment per outcome; leaving reputation
static as it had been.

**Why:** A plain ratio gives 1.0 after one confirmed report and 0.0 after one
contradiction. The first is an attack — file one true report, become fully trusted, then
fabricate. The second is unjust, since a road can genuinely clear before a warden
arrives. The prior removes both: one confirmation moves a new account from 0.50 to 0.60,
and reaching 0.9 takes roughly eighteen.

The floor exists because a reporter at exactly zero could never recover — every report
would carry zero weight, so none could ever be confirmed. A trap with no exit.

Counting distinct reporters rather than reports stops spamming from being the fastest
route to a high reputation.

**Costs.** The prior weight of 2 is another constant fitted to no data (TD-04). Trust is
lost faster than it is gained by construction, which is intended — the cost of a false
report must exceed the benefit of a true one — but it does mean an unlucky reporter is
penalised for a road that cleared before anyone arrived.

---

### D-024 — The lifecycle is a table of rules, not checks in handlers

**Decided:** Legal transitions live in one dictionary keyed by action, each entry naming
the states it may start from, the state it produces and the roles permitted. Anything
absent is refused.

**Considered:** conditional checks inside each route handler, which is the usual approach.

**Why:** Scattered checks are how the third handler someone adds becomes the one that
forgets. A table makes illegal moves unrepresentable rather than merely guarded, and it
makes the machine readable in one screen — a state machine you have to reconstruct from
five handlers is one nobody will reason about correctly.

The same table drives the interface through `allowed_actions`, so a button that would be
refused is never offered. A property test asserts the two agree for every combination of
state, action and role.

Two constraints are worth stating separately because they encode policy rather than
mechanics. **An unverified incident cannot be assigned** — otherwise the escalation
threshold is decoration. **An incident nobody was sent to cannot be resolved** —
otherwise the queue can be cleared by wishful thinking, and resolution stops being usable
as evidence about the reporters.

**Costs.** One more module, and the per-incident check that a warden may only resolve
what they were assigned lives in the service rather than the table, because it depends on
the specific incident rather than the state. That split is a small inconsistency and is
documented where it occurs.

---

## 13 August 2026 — B06 confidence

### D-023 — Confidence combines evidence with noisy-OR, not a sum

**Decided:** An incident's confidence is `1 − ∏(1 − wᵢ)`, where each report's weight is
`reputation × decay(age) × evidence_strength`. Evidence strength is capped at 0.45 so no
single report can ever reach the escalation threshold alone.

**Considered:** summing weights and clamping to 1; taking the maximum weight; a simple
count of corroborating reports.

**Why:** Summing is wrong twice — it exceeds 1, and it treats the hundredth report as
worth as much as the second, when in reality the first independent confirmation changes
your mind and the fiftieth changes nothing. Clamping would paper over the first problem
and a model that needs clamping to stay legal has stopped meaning anything. Taking the
maximum discards corroboration entirely, which is the one thing the system exists to
measure. A plain count ignores reporter reliability, so a discredited account would count
the same as a proven one.

Noisy-OR has a probabilistic reading — the chance at least one reporter is right — and
yields bounded, monotonic and saturating behaviour with no clamping. Because
multiplication is commutative it is also order-independent, matching the guarantee made
by clustering.

The 0.45 cap is what forces corroboration: with it, even a perfectly trusted reporter
alone scores 0.427 against a 0.70 threshold, so summoning police always takes more than
one person.

**Costs.** Noisy-OR assumes independence and reports are not independent — six people in
one jam are one event seen six times. Confidence is therefore systematically overstated
for crowds, and the bias runs towards over-confidence, which is the more dangerous
direction. Recorded as **TD-15** with the direction of the error stated and two proposed
mitigations. Every constant is a guess fitted to no data (**TD-04**), which is why they
are environment variables rather than literals.

---

## 13 August 2026 — B05 clustering

### D-022 — Test data is generated around hotspots, not uniformly

**Decided:** The Hypothesis generator for clustering draws a few hotspot locations and
scatters reports around them, jittered by up to twice the clustering radius. It does not
draw reports uniformly across Accra.

**Considered:** uniform generation across the bounding box, which is the obvious first
implementation and was the original one.

**Why:** Uniform generation was measured and found to be **useless**. Across the Accra
bounding box — roughly 22 km by 28 km — with at most 25 reports and a 300 m radius, only
**1 generated set in 300** contained any merge at all.

Every property passed. That is the problem, not the reassurance: they were passing over
collections of singleton clusters, where order-independence is trivially true and proves
nothing. A test that passes for the wrong reason is worse than one that fails, because
it buys confidence it has not earned.

Hotspot generation also matches reality — real reports arrive around real events, not
scattered evenly over a city.

**Guarded by** `test_the_generator_actually_produces_merges`, which asserts more than
half of generated sets contain a genuine merge, so the suite cannot silently become
decorative again.

**Costs.** The generator is more complex than a uniform one, and the property suite runs
in about 30 seconds rather than 4. Both are worth it for tests that actually test.

---

### D-021 — Test intensity is a profile, not a hard-coded number

**Decided:** Hypothesis example counts come from named profiles in `tests/conftest.py` —
`dev` at 50, `default` at 150, `thorough` at 1000 — selected by the `HYPOTHESIS_PROFILE`
environment variable.

**Considered:** a single hard-coded `max_examples`.

**Why:** Iterating on a failure wants fast feedback; producing evidence for the testing
report wants thoroughness. One fixed number forces a choice between them and is wrong
half the time. Profiles let the same tests serve both without editing.

All profiles disable the per-example deadline: clustering is O(n²) in the size of a
generated set, so a large set can legitimately exceed Hypothesis's default 200 ms without
anything being wrong. A deadline there would flag slow *data*, not slow code.

**Costs.** One more thing to explain, and a reader who runs plain `pytest` sees 150
examples rather than the 1000 quoted in the testing report. The command is stated
alongside the figure wherever it appears.

---

### D-020 — Clustering by connected components, not incremental assignment

**Decided:** Reports are grouped by building a graph — an edge between two reports of the
same type, within the distance limit and the time window — and taking its connected
components, computed with union-find.

**Considered:** incremental assignment, where each arriving report joins the nearest
existing incident or starts a new one. This is the obvious approach and what most
implementations do.

**Why:** Incremental assignment is **order-dependent**, which breaks the one property the
whole system is built on. The counter-example is three reports in a line 200 m apart with
a 300 m radius: arriving A, B, C gives one incident; arriving A, C, B gives two, because
C starts its own before B arrives to bridge them. The flaw is not the tie-break — it is
that incremental assignment consults "what already exists", and that depends on order.

Connected components have no prior state to consult, and a graph's components provably do
not depend on the order edges were added. The linking rule is symmetric, which is
load-bearing: an asymmetric rule would make the graph directed and the argument would
collapse.

A related subtlety was found while testing: floating-point addition is not associative,
so summing centroid coordinates in different orders differed in the last bit. Rather than
weaken the property test to a tolerance — which would have let order matter a little —
the centroid sums in id order, making it bit-for-bit reproducible.

**Costs.** Two, both recorded on the debt register rather than hidden. Single linkage
**chains**: a line of reports each 250 m apart merges into one long incident (TD-13). And
the pairwise comparison is O(n²) within each type bucket (TD-14). Complete linkage and
DBSCAN both address chaining but cost more than they fix here — complete linkage
fragments genuine incidents spanning a junction, and DBSCAN introduces parameters as
unvalidated as the two already present.

---

## 13 August 2026 — scope expansion, deadline extended by 8 hours

### D-019 — Media stored in the database, not object storage

**Decided:** Photos and voice notes are stored as binary columns in PostgreSQL, capped
at 250 KB per image and 500 KB per audio clip, with client-side downscaling before
upload.

**Considered:** Cloudflare R2, Cloudinary, Supabase storage — all have usable free
tiers.

**Why:** Every one of them is a fourth account, a fourth set of credentials, and a
fourth thing that can fail on deploy day. Neon's 0.5 GB holds roughly 2,000 capped
attachments, which is far more than a demonstration needs. The trade buys simplicity at
exactly the point in the schedule where a new integration failure would hurt most.

**Costs.** This is the wrong answer at any real scale: database backups balloon, and
binary in rows competes with the query workload for buffer cache. Recorded as debt with
the real fix named — object storage with presigned URLs, so the API never proxies bytes
at all.

---

### D-018 — Voice notes answer NFR-3 rather than decorating it

**Decided:** Voice note reporting is in scope, and is the designated answer to NFR-3.

**Why:** NFR-3 states the driver-facing view is passive and read-only, with no typing
while driving. Until now that was a constraint with no corresponding feature — the SRS
said what the system would not do without saying how a driver reports at all. Voice
input closes that gap: hold, speak, release.

This converts a likely viva concession into a designed answer. It also happens to suit
the user base better than typing does, independent of safety.

**Costs.** Audio storage, playback in the officer view, and a browser permission prompt.
Shares roughly 70% of its pipeline with photo evidence, so the pair costs less than the
sum of the parts.

---

### D-017 — Six enhancements accepted; the deliverable is no longer Tier 0

**Decided:** Build, in order — rich seed data, the Tier 1 officer workflow and lifecycle
state machine, voice notes, corridor subscriptions and commuter advisory, photo
evidence, and the circuit breaker.

**Considered:** holding the Tier 0 line agreed in D-009.

**Why:** Two things changed. The submission deadline moved out by 8 hours, and the
observed build rate is far above the bottom-up estimate's assumption — B01 and B02 were
budgeted at roughly 6 hours and took well under one. The 27.8-hour ceiling in
`06-effort-estimation.md` was calibrated against an assumption that no longer holds.

**What is now the binding constraint.** Not hours — **viva defensibility**. Rule 10
permits an oral examination on authorship and understanding, and code that cannot be
explained is worth less than absent code. Accordingly a plain-language explainer is
written for every module as it is built, in `docs/explainers/`. That is the throttle on
scope now, and it is a better one than the clock.

**Costs.** More surface to understand, more debt to track, and the estimation document
now describes a plan that was deliberately exceeded. That last point is recorded rather
than hidden: an estimate that was revised when its assumptions broke is a better
artefact than one quietly rewritten to match the outcome.

---

### D-016 — Warden added as a fourth role; no "driver" role

**Decided:** Roles are commuter, warden, officer, admin. There is no driver role.

**Why (warden):** The Tier 1 workflow needs both ends of the dispatch loop. A
control-room officer decides who goes; a field warden goes and confirms the road is
clear. Collapsing them would have made "assign" meaningless.

**Why (no driver):** A driver and a passenger have identical permissions — both report,
both receive warnings. The difference is a client-side mode, not an account type. When
the client detects motion it goes read-only and offers voice input (NFR-3). Making
driving a role would imply the server can tell who is currently driving, which it cannot
and should not.

**Costs.** Migration 0003 swaps the role CHECK constraint. This is the payoff for
D-005's choice of VARCHAR + CHECK over a native PostgreSQL enum: the change runs inside
an ordinary transaction, where `ALTER TYPE ... ADD VALUE` historically could not.

---

## 12 August 2026 — B01 build issues

### D-015 — Dependencies pinned to the first versions with CPython 3.14 wheels

**Decided:** Move every pin forward to a version publishing a prebuilt wheel for CPython
3.14: `asyncpg` 0.30.0 → 0.31.0, `SQLAlchemy` 2.0.43 → 2.0.52, `pydantic` 2.11.7 → 2.13.4
(which pins `pydantic-core` 2.46.4), plus `fastapi`, `uvicorn`, `alembic`, `GeoAlchemy2`,
`pytest` and `hypothesis` brought to current.

**Considered:** installing Python 3.12 alongside 3.14 and building against that; asking
for the MSVC C++ build tools and a Rust toolchain to be installed.

**Why:** The development machine runs Python 3.14. Neither `asyncpg` 0.30.0 nor
`pydantic-core` 2.33.2 publishes a 3.14 wheel, so pip fell back to compiling both from
source — `asyncpg` failed on the missing MSVC C++ compiler, `pydantic-core` failed at the
Rust link step. Both alternatives cost more time than moving the pins, and installing a
compiler toolchain to build packages that ship perfectly good wheels one version later is
work for its own sake.

Availability was checked against the PyPI API rather than guessed, for every package with
a compiled extension.

**Costs.** Larger version jumps than intended mid-build — `fastapi` 0.116 → 0.141 and
`pytest` 8 → 9 are both major moves. Mitigated by re-running the full suite immediately
afterwards: 22 tests, all passing. `bcrypt` 5.0.0 needed no change because it ships a
`cp39-abi3` wheel — the stable ABI, which works on every later interpreter.

**Note for the debt register.** This is exactly the failure mode TD-10 describes: pins
were verified once, by hand, on one machine. A second machine with a different interpreter
found the gap immediately. Recorded there rather than treated as a one-off.

---

## 12 August 2026 — hosting, with 40 hours remaining

### D-014 — Render free-tier cold start accepted and disclosed

**Decided:** Deploy on Render's free tier despite the 15-minute idle spin-down and 30–60 second
wake time. Mitigated by a keep-warm ping every 10 minutes and an explicit note at the top of
`Deployment_and_Source_Links.txt`.

**Considered:** paying for a Render instance; Fly.io; Railway.

**Why:** The risk is not technical, it is a grading risk — an examiner clicks the link, waits,
and assumes the application is broken. That risk is fully addressed by disclosure and a ping,
both free. Paying to remove it would be spending money to solve a documentation problem.

**Costs:** first-load latency for anyone arriving cold. Disclosed rather than hidden.

---

### D-013 — Outbox worker runs in-process, not as a separate service

**Decided:** The outbox drainer runs as an `asyncio` background task inside the FastAPI
service rather than as an independent worker process.

**Considered:** a separate Render background worker; an external queue such as Redis.

**Why:** Render's free tier permits one service. A separate worker is a paid feature. This is a
genuine architectural compromise forced by a genuine constraint, which makes it a much better
technical debt entry than anything invented after the fact.

**Costs:** real ones, and all of them go in the debt register — the worker cannot scale
independently of the API, it dies whenever the API restarts, there is no backpressure if
reports arrive faster than it drains, and a slow gateway consumes capacity the API needs to
serve requests. Proposed resolution: extract to a separate process backed by Redis Streams.

---

### D-012 — Vercel dropped; the page is served by FastAPI

**Decided:** No separate front-end host. The single static page is served by FastAPI through
`StaticFiles`.

**Considered:** deploying the page to Vercel as originally planned.

**Why:** The front end was reduced to one static HTML page by the effort estimation. A separate
host for one page adds an account, a deployment target, a build pipeline and CORS
configuration, and returns nothing. Removing it also removes an entire class of "works locally,
broken in production" failure at the point in the schedule where that would hurt most.

**Costs:** none at this scale. If the front end ever grows into a real application, it moves
back out — recorded in the backlog.

---

## 12 August 2026 — after effort estimation

### D-011 — The concept spine is ring-fenced against all cuts

**Decided:** Tasks B04 (report intake with transactional outbox), B05 (spatio-temporal
clustering), B06 (confidence and time decay) and B09 (outbox worker with idempotency keys) may
not be cut, simplified below their stated form, or deferred. They total 12.1 hours.

**Considered:** treating everything as equally negotiable under time pressure.

**Why:** These four tasks *are* the advanced concept. Everything else in the build is
supporting structure. Under time pressure the temptation is to cut whatever is hardest, which
here would be exactly the wrong thing — it would leave a competent CRUD application with an
essay attached, and the essay would not be believed.

**Costs:** removes flexibility precisely when it will be most wanted. Accepted deliberately;
that is the point of deciding it now rather than at 3 a.m.

---

### D-010 — Ordered cut list agreed in advance

**Decided:** Six items to be cut, in a fixed order, as time requires: React app → single
static page; admin screens; circuit breaker; full reputation model; corridor subscriptions;
third property test.

**Considered:** deciding what to cut in the moment.

**Why:** Decisions made at hour 40 under fatigue are worse than decisions made at hour 12.
Fixing the order now means the cut becomes a lookup rather than a judgement call. It also
means each cut can be documented as deliberate — which is worth marks — instead of appearing
as something unfinished.

**Costs:** the circuit breaker was one of the better live demonstrations available. It moves to
the technical debt register as designed-but-not-built.

---

### D-009 — The deliverable is a vertical slice, not the product

**Decided:** The 48-hour output is explicitly a narrow-but-complete slice of the system,
described as such throughout the submission. Not a partial product, not an MVP — a slice
chosen to exercise the full architecture end to end.

**Considered:** presenting the build as a minimum viable product.

**Why:** Use Case Points puts full scope at 1,948 person-hours, roughly 40 times the
examination window; even the must-have subset is 1,391 hours. Any framing that implies the
product was attempted invites the question of why it is incomplete. Framing it as a
deliberately chosen slice invites the question of why *that* slice — which has a good answer.

**Costs:** none. This is a framing decision, and the honest framing is also the stronger one.

---

## 12 August 2026

### D-008 — Traffic control officer is the primary actor

**Decided:** The system is built around the authority's incident queue. Commuters are the
sensor network feeding it.

**Considered:** commuter-facing primary (motorists first, authorities downstream); balanced
two-sided design.

**Why:** It matches the users named in the original brief — emergency services and the police
traffic divisions. It also solves a demonstration problem: a purely commuter-facing crowd
advisory app is thin to show with no real user base, whereas a dispatch queue seeded with
test data demonstrates convincingly. A two-sided design roughly doubles the interface surface,
which the 48-hour budget will not carry.

**Costs:** the commuter experience is deliberately simpler than it would be in a real product.

---

### D-007 — Two non-functional requirements added that were not in the brief

**Decided:** NFR-3 (driver-facing view is passive and read-only) and NFR-4 (reported parties
never identified, reputation floor before escalation, rate limiting).

**Considered:** leaving both implicit.

**Why:** The brief asks motorists to report hazards, which invites phone use while driving —
a road safety system must not create the hazard it exists to reduce. And it lets users report
other people to the police, which is a harassment and false-accusation vector. Both will come
up in the viva. Better to have raised them first.

**Costs:** none material. Reporting becomes passenger-first or voice-first, which is the
correct design anyway.

---

### D-006 — Ride-sharing and transport subscriptions cut from scope

**Decided:** Both excluded. Ride-sharing becomes the headline Future Evolution item.

**Considered:** including a minimal ride-matching feature.

**Why:** Ride-sharing is an entire second product — matching, payments, identity verification,
passenger safety, insurance, liability — and shares nothing with the report pipeline.
Subscriptions are a third. Including either would consume the implementation budget and leave
the advanced concept half-built. The mark scheme rewards a small system engineered well over
a large one delivered thin.

**Costs:** loses the part of the brief the author was most personally attached to. Mitigated
by making it the lead item in Future Evolution, which is itself worth 3 marks.

---

### D-005 — Five brief features unified into one report pipeline

**Decided:** Traffic impediments, accidents, maintenance reports, road-condition reviews and
signal outages are all one polymorphic report type with a type discriminator and a per-type
resolution policy.

**Considered:** building each as a separate feature with its own model and screens.

**Why:** They differ only in who acts on them, not in how they are captured, grouped or
scored. One pipeline covers most of the brief with a single well-designed core, and reduces
implementation cost by roughly two-thirds.

**Costs:** per-type behaviour must be handled through policy objects rather than separate
code paths — slightly more abstraction up front, much less code overall.

---

### D-004 — Advanced concept: event-driven pipeline with spatio-temporal corroboration

**Decided:** Reports stored as permanent immutable events; Incidents as a projection built by
a clustering consumer; reputation-weighted confidence with time decay; transactional outbox
for guaranteed processing; idempotency keys for at-least-once notification; circuit breaker
on the outbound gateway.

**Considered:**
- bitemporal fare registry (the TroTroGo concept) — strong, but a different problem domain
- spatio-temporal permit conflict detection (the ClearWay road works concept) — arguably more
  rigorous, but less connected to the author's stated interests
- constraint-solving for signal timing — highest risk, hardest to validate

**Why:** It is genuinely forced by this domain rather than bolted on. Every element answers a
real question the system must handle: which reports are the same event, is it true, what if we
crash mid-way, what if reports arrive out of order. It also yields an order-independence
property that can be *proved* with property-based testing rather than merely claimed.

**Costs:** more moving parts than a CRUD application, and the outbox worker is extra
infrastructure. Accepted as the price of the concept marks.

---

### D-003 — Stack: Python / FastAPI / PostgreSQL + PostGIS / React

**Decided:** FastAPI backend, PostgreSQL with PostGIS, SQLAlchemy and Alembic, React with
Vite and MapLibre GL, pytest with Hypothesis. Hosted on Render, Neon and Vercel.

**Considered:** Node with TypeScript; Java with Spring Boot.

**Why:** Author is fastest in Python, which matters most under a 48-hour constraint. PostGIS
handles the location queries natively. Hypothesis is the strongest property-based testing tool
available in any of the candidate stacks, and the property tests are central to the testing
marks.

**Costs:** Spring Boot would have scored marginally better on architecture presentation. Not
worth the build time.

---

### D-002 — Project selected: road incident reporting and dispatch

**Decided:** Nkwanta, from the author's stated areas of interest.

**Considered:** TroTroGo bitemporal fare authority; ClearWay road works coordination; trotro
stop and dwell management; savings-group ledger.

**Why:** Author has direct experience of the problem, which matters for the viva. Stakeholders
are real and nameable. The domain forces a genuinely interesting technical core rather than
inviting one.

---

### D-001 — Scope discipline over feature count

**Decided:** Build the smallest system that fully exercises the lifecycle, and document the
cuts.

**Why:** Implementation is 10 of 50 marks. Requirements, estimation, design, testing, debt,
documentation and evolution are 40. The paper says outright that a large commercial system is
not expected and that disciplined practice under constraint is what is assessed. Optimising
for feature count optimises against the mark scheme.

---

## Template for new entries

```
### D-0XX — <short title>

**Decided:** what was chosen.

**Considered:** what else was on the table.

**Why:** the reasoning. Reference the mark scheme where relevant.

**Costs:** what this gives up. Every real decision costs something.
```
