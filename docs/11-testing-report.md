# Testing Report

**Nkwanta: A Road Incident Reporting and Dispatch System for Urban Ghana**

*14 August 2026 · Theophilus Caesar, 22424543*

---

## 1. What this report claims, and what it does not

**508 tests. 499 pass without a database; 9 more require PostGIS.** Coverage is 69% of
statements overall and **99% of the pure domain core**.

That second number is the one that matters, and the gap between it and the first is the
honest summary of this project's testing: the parts that *decide* things are tested almost
exhaustively, and the parts that *move data around* are tested through a narrow set of
integration paths. Section 6 says exactly where that leaves gaps.

This report does not claim the system is correct. It claims that a specific set of
properties has been checked, by a specific method, and it names the ones that have not.

---

## 2. Strategy

The usual testing pyramid assumes the expensive tests are the valuable ones. Here the
opposite held, for a structural reason: **the domain layer touches no database, clock or
network** (`09-system-design.md` §2). Calling `clustering.group()` costs nothing, so it can
be called ten thousand times with generated inputs.

That made property-based testing affordable on exactly the code where correctness is
hardest to reason about — and it is where the real defects were found.

| Level | What it covers | Count | Cost to run |
|---|---|---:|---|
| **Property-based** | The domain core: clustering, confidence, lifecycle, reputation, the breaker | 35 properties | seconds |
| **Unit** | Everything else pure: validation, tokens, geography, schemas | ~300 | seconds |
| **Contract** | Routes, roles, response shapes, the front end against the API | ~100 | seconds |
| **Integration** | The real pipeline against real PostGIS | 9 | ~3.5 minutes |
| **Document** | The SRS, the design document and this report, against the code they describe | 49 | instant |

The last row is unusual and deliberate — see §5.

---

## 3. The property-based tests

Thirty-five properties across five files, using Hypothesis. Three intensity profiles, so
the same properties run at different depths without editing them:

| Profile | Examples per property | Used for |
|---|---:|---|
| `dev` | 50 | Fast feedback while building |
| `default` | 150 | Every ordinary run |
| `thorough` | 1000 | Before submission — `HYPOTHESIS_PROFILE=thorough pytest` |

### The property the project exists to prove

**The order reports arrive in must not change the result.** Six people report one flood;
their phones have different signal; the reports land in any order. The incident must come
out identical either way.

`test_clustering_properties.py` generates report sets, shuffles them, groups both orders
and asserts the groupings are equal. This is not a demonstration on three hand-picked
inputs — it is 150 generated cases per run, 1000 before submission, each one shrunk to a
minimal counter-example if it fails.

### Other properties held

| Property | Why it matters |
|---|---|
| Confidence never decreases when a report is added | An extra witness cannot make an incident less believable |
| Confidence is bounded strictly below 1 | No amount of corroboration is certainty |
| Combining is commutative and associative | Same reason as order-independence, one level down |
| A cluster's centroid lies within the bounding box of its members | Catches coordinate errors that produce plausible-looking nonsense |
| Reputation stays within [0, 1] under any sequence of outcomes | The Beta posterior cannot be driven out of range |
| Every lifecycle transition is either in `RULES` or refused | The state machine has no undocumented edges |
| The breaker always reaches a terminal state under any failure sequence | It cannot get stuck half-open |

---

## 4. Defects found by testing

This is the section that justifies the method. Every one of these was found by a test, not
by using the application.

### 4.1 Floating-point addition is not associative — `D-027`

Hypothesis generated three reports at *identical* longitudes and the computed mean came out
one unit in the last place **below the minimum of its inputs**. A mean cannot be below its
own minimum; the summation order made it so.

No hand-written test would have chosen three identical longitudes — it looks like a
degenerate case not worth writing. The fix was `math.fsum` plus a clamp. **This is the
single best argument in the project for property-based testing**: the input was
uninteresting to a human and fatal to the invariant.

### 4.2 A property test that proved nothing — `D-022`

The order-independence tests were passing while generating almost no merges: uniformly
random points in Greater Accra practically never land within 300 m of each other, so nearly
every generated case was a set of singletons, and shuffling singletons proves nothing.

Found by asking the obvious question of a suspiciously fast green suite. The fix was a
hotspot-based generator, plus **a meta-test asserting the generator actually produces
merges** — the test that watches the test.

### 4.3 Route traversal found 5 routes of 21

A test walking the application's routes to check every one declared its roles was finding
five. FastAPI 0.141 wraps included routers in `_IncludedRouter`, so the naive traversal
stopped one level up. The test was green and covering a quarter of what it claimed.

Fixed by traversing `original_router`, with a meta-test asserting the count is plausible.

### 4.4 The service worker controlled nothing — `D-045`

It was registered as `/static/app/sw.js` with scope `/static/app/`, from a page at `/app` —
outside that scope. A worker only controls clients within its scope, so it installed
successfully, cached the shell and was never consulted. **Offline had never worked in
production.**

Every existing test asserted what the worker *contained*. None asserted what it *reached*.
Found while writing a test for the retirement of the old page.

### 4.5 The installed application would have opened a 404 — `D-045`

The manifest's `start_url` and `scope` were `/static/app/`, which was never a route. It was
also in the worker's shell list, where `cache.add` failed at every install — and the
`Promise.allSettled` that deliberately tolerates one missing file is why nobody noticed.

### 4.6 A label and its value rendered as one word

`.t` and `.m` — the title/detail pair used across the whole interface — were
`display:inline`, so they ran together wherever the parent was not a flex column, and
`.m`'s `margin-top` did nothing at all. It looked correct in the places a flex parent
forced a column and wrong everywhere else, **which is why one bug arrived as three
unrelated complaints over two sessions.**

### 4.7 Evidence failures were swallowed

Attachment uploads ended in `.catch(() => {})`. A rejected photograph or recording vanished
without a word — the user saw "Reported. Thank you." and their evidence was simply absent.
Found by a user report, not by a test; the test came after.

### 4.8 The SRS named a file that does not exist

`test_srs.py` failed on its first run: the specification cited `routers/notifications.py`
as implementing FR-39, and there is no such file — those endpoints live in `corridors.py`.
A confident claim, in a graded document, about a file that does not exist. No human reader
would have caught it.

---

## 5. Testing the documents

Forty-nine tests check `10-srs.md`, `09-system-design.md` and this report itself against
the code they describe:
every module named as an implementation exists, every test named as verification exists,
every table in the ER diagram is in `Base.metadata` **and every table in the metadata is in
the diagram**, quoted thresholds match the constants, requirement numbering has no gaps or
duplicates, summary totals match the tables they summarise, and every `D-`, `TD-` and
`NFR-` citation resolves.

The reasoning: a document is read *instead of* the code. A diagram naming a module that was
renamed six commits ago is worse than no diagram — it is a confident statement that happens
to be false. Documentation rot is a defect class, and it is one that can be tested for.

Mermaid syntax cannot be checked from Python, so `scripts/validate-diagrams.mjs` parses
every diagram with the real parser. It earned its place immediately: one sequence diagram
would have rendered as a grey error box because a note contained a semicolon, which mermaid
reads as a statement separator.

---

## 6. Coverage, and what it does not cover

Measured with `coverage.py` over the 499 tests that run without a database. **The nine
integration tests are excluded, so the router and service figures are understated** — those
are exactly the modules the integration tests exercise.

| Layer | Coverage | Reading |
|---|---:|---|
| **Pure domain core** — clustering, confidence, lifecycle, reputation, breaker, geo, tokens, security | **99%** | Near-exhaustive, and property-tested rather than merely executed |
| Models and schemas | 99–100% | Constraints and shapes are asserted directly |
| Services | 26–84% | `dispatch.py` at 26% is the weakest; see below |
| Routers | 35–57% | Understated — integration tests excluded from this measurement |
| **Overall** | **69%** | |

**Coverage is a measure of what ran, not of what was checked.** A line executed by a test
that asserts nothing counts the same as a line whose every branch is pinned by a property.
The 99% figure means something because those modules are property-tested; the 69% figure is
mostly a statement about which code needs a database to run.

### The weakest number, named

`services/dispatch.py` at **26%**. This is where assignment, recall and resolution live —
the reputation feedback loop. Its *rules* are tested exhaustively in `lifecycle.py` (100%),
because they were deliberately separated out as pure functions. What is thin is the code
that carries those decisions to the database.

---

## 7. What is not tested

Named rather than left to be discovered.

| Gap | Consequence | Status |
|---|---|---|
| **Clearance fan-out — FR-40** | `fan_out_clearance` is called by no test; `handle_incident_cleared` has never run in one; there is no assertion that it is registered in `HANDLERS`, though there is exactly that assertion for the advisory event. Deleting the registration would keep the suite green. | Declared Partial in the SRS |
| **NFR-07 — 3-second load on 3G** | Never measured against a throttled connection. Stated as a target, not a result. | Declared unverified in the SRS |
| **Browser end-to-end** | No Playwright or Selenium. The front end is tested by reading its source and checking it against the API — which catches renamed routes and missing handlers, and cannot catch anything about rendering. | Accepted; §4.6 is what this gap costs |
| **Load and concurrency** | `FOR UPDATE SKIP LOCKED` is tested for correctness with one worker, never with two competing. | Accepted |
| **Security scanning** | No dependency audit, no static analysis, no penetration testing. Authorisation is tested per-route; the absence of vulnerabilities is not established. | Accepted |
| **Migrations** | No test applies the Alembic chain to an empty database and compares it to `Base.metadata`. A drift between the two would not be caught. | Accepted, and the most likely to bite |

---

## 8. Two recurring faults — in the tests themselves

Worth recording because both recurred after being identified once, which makes them
patterns rather than incidents.

### 8.1 Vacuous assertions

**A test that asserts something about a collection must first assert the collection is not
empty.** This produced three green-but-worthless tests: the clustering generator (§4.2),
the route traversal (§4.3), and an endpoint extraction in the PWA tests that found nothing
and was satisfied.

Every affected test now carries a meta-assertion — `assert len(x) >= n, "this would pass
vacuously"`.

### 8.2 Tests that read source text also read the prose

A test grepping for a banned string matched the *comment explaining why the string was
banned*. **Four times.** Most recently, a test asserting the old service-worker path was
gone matched the comment describing why it had been removed.

The rule now: assert on the call form (`register("/static/app/sw.js"`), never the bare
token.

There is a general lesson under both, and it appears three more times in `HANDOFF.md` in
non-test form: **a claim that has not been re-checked is not evidence, however many times
it has been repeated.** A passing test is a claim.

---

## 9. How to run

```bash
pytest                                        # 499 without a database
pytest -q --ignore=tests/test_integration_pipeline.py   # skip the slow ones
HYPOTHESIS_PROFILE=thorough pytest            # 1000 examples per property
DATABASE_URL=... pytest                       # all 508, including PostGIS

node scripts/validate-diagrams.mjs docs/09-system-design.md   # needs `npm i mermaid jsdom`
```

The integration tests are slow — about 3.5 minutes — because every projection is several
spatial queries against a hosted database. They also share that database with the deployed
instance (**TD-18**), which has produced two false failures; both are recorded there with
their mechanisms, and the tests now wait for the pipeline to settle rather than assuming
this process did the work.

---

## 10. Summary

| Measure | Value |
|---|---|
| Tests | 508 |
| Passing without a database | 499 |
| Requiring PostGIS | 9 |
| Property-based | 35 properties × 150 examples (1000 in `thorough`) |
| Statement coverage, overall | 69% |
| Statement coverage, pure domain core | **99%** |
| Defects found by tests rather than by use | 6 of the 8 in §4 |
| Requirements verified by a named test | 49 of 50 |
| Non-functional requirements verified | 6 of 7 |
