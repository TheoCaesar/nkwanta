# Software Requirements Specification

**Nkwanta: A Road Incident Reporting and Dispatch System for Urban Ghana**

*Version 1.0 · 14 August 2026 · Theophilus Caesar, 22424543*
*CSCD602 Advanced Software Engineering, University of Ghana*

---

## 1. Introduction

### 1.1 Purpose

This document states what Nkwanta must do, precisely enough that a stranger could tell
whether it does it. Every requirement below is numbered, given a priority, traced to the
code that implements it and to the test that holds it, and — where it was cut — to the
reason.

It is written for two readers: an examiner deciding whether the requirements were
engineered rather than assumed, and a maintainer six months from now deciding whether a
proposed change breaks something that was promised.

### 1.2 Scope

Nkwanta collects reports of things blocking urban roads in Ghana — accidents, floods,
closures, failed traffic signals, roadworks and surface defects — from ordinary road users.
It works out which reports describe the same real event, scores how believable each event
is, warns other commuters travelling that way, and puts credible events in front of a
traffic control officer who can send a warden.

**It is not an emergency service.** It never contacts the police or an ambulance. It places
an escalation flag in a queue that a human authority monitors. This distinction is a stated
constraint, not an oversight — see NFR-05.

### 1.3 Definitions

Every technical term is defined in plain English in `03-glossary.md`. The terms used most
in this document:

| Term | Meaning here |
|---|---|
| **Report** | One person's statement that something is blocking a road, at a place and a time. Permanent; never edited. |
| **Incident** | A group of reports judged to describe the same real event. Calculated, not stored by hand. |
| **Confidence** | How believable an Incident is, 0 to 1. Shown to users as **accuracy** (D-039). |
| **Reputation** | How often a user's past reports proved true. Shown to users as **credibility**. |
| **Corridor** | A named stretch of road a user can follow, so they are warned about it. |
| **Control room** | Officers, wardens and administrators collectively. |

### 1.4 References

| Document | What it holds |
|---|---|
| `02-problem-and-scope.md` | Problem statement, stakeholders, MoSCoW, exclusions |
| `04-advanced-concept.md` | The advanced concept in plain language |
| `05-decision-log.md` | Every significant choice, dated (D-nnn) |
| `06-effort-estimation.md` | Use Case Points and bottom-up estimate, and the cuts they forced |
| `08-technical-debt.md` | Known compromises (TD-nn) |
| `09-system-design.md` | Architecture, data model, sequences, lifecycle |

---

## 2. Overall description

### 2.1 Product perspective

A self-contained web application. No integration with any external system: no payment
provider, no mapping service beyond public map tiles, and — deliberately — no emergency
dispatch. The only outbound dependency is a notification gateway, and it is guarded by a
circuit breaker so that its failure cannot consume the system.

### 2.2 Users

| Actor | Role in the system | Volume assumption |
|---|---|---|
| **Commuter** | Files reports; follows corridors; receives warnings | The many. The sensor network. |
| **Traffic control officer** | Watches the dispatch queue; sends wardens | **The primary actor.** Few. |
| **Traffic warden** | Attends incidents; reports what was found | Few. |
| **Administrator** | Creates privileged accounts; oversees the system | One or two. |
| **Signed-out visitor** | Looks at the public map | Unknown, possibly many. |

**The primary actor is the officer, not the commuter.** Commuters produce the data; the
officer is the person whose job the system exists to do. That choice decides which screen
is the core one and makes the system demonstrable without a large user base.

### 2.3 Operating environment

Low-end Android phones on 3G, in traffic, often in bright sunlight. This is not a
background detail — it produced NFR-02, NFR-03 and NFR-07, the offline queue, and the
decision to ship no front-end build step (D-037).

### 2.4 Constraints

| Constraint | Consequence |
|---|---|
| 48 hours (extended to 56), one person | Scope cut against a written estimate — see Section 6 |
| Free hosting only | One process, so the worker runs in-process (TD-01) |
| No real road-network dataset | Corridors are hand-drawn; clustering constants are untuned (TD-03) |
| No real user base | Reputation cannot be validated against reality, only against its own arithmetic |

### 2.5 Assumptions and dependencies

- Reporters are mostly honest, and the dishonest are a minority whose reports fail to
  corroborate. Reputation is the defence, and it assumes the majority is not colluding.
- Reports of the same event arrive within 30 minutes and 300 metres of one another. **These
  two numbers are assumptions, not measurements** (TD-03).
- PostgreSQL with PostGIS is available. The spatial queries are not portable to plain
  PostgreSQL.

---

## 3. Functional requirements

Priority uses MoSCoW. **Status** is `Implemented`, `Partial` or `Deferred`, and is a
statement of fact rather than intent — a requirement marked Implemented has a test named
against it.

### 3.1 Accounts and roles

| ID | Requirement | Priority | Status | Implemented in | Verified by |
|---|---|---|---|---|---|
| FR-01 | A visitor shall register an account with an email address, a display name and a password of at least 8 characters. | Must | Implemented | `routers/auth.py::register` | `test_auth.py` |
| FR-02 | Registration shall create a **commuter** and nothing else. No request may register a privileged role. | Must | Implemented | `routers/auth.py` — the schema has no role field | `test_auth.py`, `test_pwa.py` |
| FR-03 | Only an administrator shall create officer, warden or administrator accounts, or change an existing account's role. | Must | Implemented | `routers/auth.py::create_user`, `update_user` | `test_account_management.py` |
| FR-04 | A user shall sign in with email and password and receive a token valid for 12 hours. | Must | Implemented | `routers/auth.py::login` | `test_auth.py` |
| FR-05 | Sign-in shall give the same answer for an unknown email and a wrong password. | Must | Implemented | `routers/auth.py::login` | `test_auth.py` |
| FR-06 | A user shall change their own display name and password. The password change shall require the current password. | Should | Implemented | `routers/auth.py::update_me`, `change_password` | `test_account_management.py` |
| FR-07 | Email addresses shall not be changeable, because the system cannot yet send a verification message. | Should | Implemented | No route accepts it | `test_account_management.py` |
| FR-08 | An administrator shall deactivate an account, and a deactivated account shall lose access on its next request rather than when its token expires. | Should | Implemented | `auth.py::get_current_user` re-reads the user | `test_account_management.py` |

### 3.2 Reporting

| ID | Requirement | Priority | Status | Implemented in | Verified by |
|---|---|---|---|---|---|
| FR-09 | A signed-in user shall report an incident of one of six types, with a location, a time and an optional note. | Must | Implemented | `services/reports.py::submit_report` | `test_report_intake.py` |
| FR-10 | A report shall be permanent. No route shall edit or delete one. | Must | Implemented | `models.py` — `Report` has no mutable state | `test_models.py` |
| FR-11 | A report shall carry an idempotency key generated by the client at capture, and re-submitting the same key shall return the original report rather than create a second. | Must | Implemented | `services/reports.py`, `web/app/js/api.js` | `test_report_intake.py`, `test_pwa.py` |
| FR-12 | Saving a report and queueing its notifications shall occur in one database transaction. | Must | Implemented | `services/reports.py` | `test_integration_pipeline.py` |
| FR-13 | A report with coordinates outside Ghana shall be rejected with a message naming the likely cause. | Should | Implemented | `geo.py` | `test_report_intake.py` |
| FR-14 | A user shall attach up to three photographs and one voice recording to their own report, and to no one else's. | Should | Implemented | `services/attachments.py::attach` | `test_attachments.py` |
| FR-15 | The client shall stop recording at the size limit rather than reject the upload afterwards, and shall show the limit before it is reached. | Should | Implemented | `web/app/js/views/report.js` | `test_pwa.py` |
| FR-16 | A reporter shall play back a photograph or recording before sending it. | Should | Implemented | `web/app/js/views/report.js` | `test_pwa.py` |
| FR-17 | A report made without a connection shall be stored on the device and sent when the connection returns, without duplication. | Should | Implemented | `web/app/js/api.js` — IndexedDB queue | `test_pwa.py` |
| FR-18 | A user shall see their own reports and the evidence attached to each. | Should | Implemented | `routers/reports.py::mine`, `views/profile.js` | `test_pwa.py` |

### 3.3 Grouping, scoring and lifecycle

| ID | Requirement | Priority | Status | Implemented in | Verified by |
|---|---|---|---|---|---|
| FR-19 | Reports within 300 m and 30 minutes of each other, of the same type, shall be grouped into one Incident. | Must | Implemented | `clustering.py`, `services/projection.py` | `test_clustering_properties.py` |
| FR-20 | **The grouping shall not depend on the order the reports arrived in.** | Must | Implemented | `clustering.py` — connected components | `test_clustering_properties.py` (Hypothesis) |
| FR-21 | Each Incident shall carry a confidence score derived from each contributing reporter's reputation, decayed by the age of their report. | Must | Implemented | `confidence.py` | `test_confidence_properties.py` |
| FR-22 | Confidence shall never decrease when a report is added, and shall never reach or exceed 1. | Must | Implemented | `confidence.py` — noisy-OR | `test_confidence_properties.py` (Hypothesis) |
| FR-23 | The weight each report contributed shall be stored, so the score can be explained rather than merely displayed. | Must | Implemented | `models.py::IncidentReport.weight` | `test_advisory.py` |
| FR-24 | An Incident shall be *corroborated* at 0.35 and *verified* at 0.70, and shall fall back if confidence decays. | Must | Implemented | `confidence.py`, `lifecycle.py` | `test_lifecycle.py` |
| FR-25 | An Incident below 0.05 shall fade from the map without anyone closing it. | Should | Implemented | `services/staleness.py` | `test_lifecycle.py` |
| FR-26 | Only a *verified* Incident shall be assignable, and only an *assigned* Incident shall be resolvable. | Must | Implemented | `lifecycle.py::RULES` | `test_lifecycle.py` |
| FR-27 | The API shall tell the client which actions are currently permitted, so an action that would be refused is never offered. | Should | Implemented | `routers/incidents.py` — `allowed_actions` | `test_lifecycle.py` |
| FR-28 | Rebuilding every Incident by replaying the reports shall produce the same map. | Must | Implemented | `services/projection.py` | `test_integration_pipeline.py` |

### 3.4 Dispatch and reputation

| ID | Requirement | Priority | Status | Implemented in | Verified by |
|---|---|---|---|---|---|
| FR-29 | An officer shall see verified Incidents ranked by confidence, with the contributing reports and each one's weight. | Must | Implemented | `routers/incidents.py::queue`, `get_incident` | `test_lifecycle.py` |
| FR-30 | An officer shall assign an available warden to a verified Incident, and shall recall one. | Must | Implemented | `services/dispatch.py` | `test_lifecycle.py` |
| FR-31 | A warden shall see only the Incidents assigned to them. | Must | Implemented | `routers/incidents.py::assigned_mine` | `test_lifecycle.py` |
| FR-32 | A warden shall resolve an Incident as *confirmed* or *false alarm*, with an optional note. | Must | Implemented | `services/dispatch.py::resolve` | `test_lifecycle.py` |
| FR-33 | Resolution shall raise the reputation of every contributing reporter when confirmed, and lower it when a false alarm. | Must | Implemented | `reputation.py` | `test_lifecycle.py` |
| FR-34 | Reputation shall move slowly: a new account starts at 0.5 and reaching 0.9 shall take roughly eighteen confirmations. | Must | Implemented | `reputation.py` — Beta posterior | `test_lifecycle.py` |

### 3.5 Warning commuters

| ID | Requirement | Priority | Status | Implemented in | Verified by |
|---|---|---|---|---|---|
| FR-35 | A user shall follow and unfollow named corridors. | Should | Implemented | `routers/corridors.py` | `test_advisory.py` |
| FR-36 | An Incident reaching 0.35 on a followed corridor shall produce one warning for each follower. | Should | Implemented | `services/advisory.py::fan_out` | `test_advisory.py` |
| FR-37 | **No follower shall be warned twice about the same Incident**, however many times delivery is retried or clusters merge. | Must | Implemented | `UNIQUE (user_id, incident_key)` on the cluster key | `test_advisory.py` |
| FR-38 | Commuters shall be warned at a lower threshold (0.35) than the one at which police are involved (0.70). | Should | Implemented | `confidence.py` | `test_advisory.py` |
| FR-39 | A user shall see their warnings, an unread count, and mark them read. | Should | Implemented | `routers/corridors.py` — corridors and the warnings they produce share a router | `test_advisory.py` |
| FR-40 | When an Incident is resolved or found to be a false alarm, everyone warned about it shall be told the road is clear. | Should | **Partial** | `services/advisory.py::fan_out_clearance` — written and wired; **no test calls it, and the seed contains no resolved Incident** | *none* |

### 3.6 The public map and privacy

| ID | Requirement | Priority | Status | Implemented in | Verified by |
|---|---|---|---|---|---|
| FR-41 | Anyone, without an account, shall see current Incidents on a map with their type, position, status and how recently they were reported. | Must | Implemented | `routers/incidents.py::list_incidents` | `test_public_map.py` |
| FR-42 | A signed-out visitor shall **not** be shown reporter identities, credibility, evidence, or the numeric confidence score. | Must | Implemented | `routers/incidents.py` — withheld server-side | `test_public_map.py` |
| FR-43 | A voice recording shall be private unless its reporter chooses to share it, and that choice shall be withdrawable by them and by nobody else. | Must | Implemented | `services/attachments.py::may_play`, `set_visibility` | `test_attachments.py` |
| FR-44 | A photograph shall be shared by default, and equally withdrawable. | Should | Implemented | `routers/attachments.py::upload_photo` | `test_attachments.py` |
| FR-45 | A refusal to serve an attachment shall be indistinguishable from the attachment not existing. | Must | Implemented | `routers/attachments.py` — 404, never 403 | `test_attachments.py` |
| FR-46 | The party a report is *about* shall never be identified to other users. | Must | Implemented | No field records them | `test_report_intake.py` |

### 3.7 Administration and resilience

| ID | Requirement | Priority | Status | Implemented in | Verified by |
|---|---|---|---|---|---|
| FR-47 | An administrator shall see system totals, list accounts, and create or modify privileged accounts. | Should | Implemented | `routers/admin.py`, `views/admin.js` | `test_account_management.py` |
| FR-48 | A failing outbound gateway shall be cut off after a threshold of failures and retried after a cooling period, rather than retried indefinitely. | Should | Implemented | `circuit_breaker.py` | `test_circuit_breaker.py` |
| FR-49 | A queued message that fails repeatedly shall be abandoned rather than block the queue behind it. | Should | Implemented | `worker.py` — `MAX_ATTEMPTS` | `test_worker.py` |
| FR-50 | Demonstration data shall be creatable and removable by one command. | Could | Implemented | `scripts/seed_demo.py` | `test_seed.py` |

---

## 4. Non-functional requirements

Carried forward from `02-problem-and-scope.md` with identifiers regularised. NFR-04a is
retained under its original name because it is cited in three decision-log entries.

| ID | Requirement | Rationale | Verified by |
|---|---|---|---|
| NFR-01 | A warning shall reach a subscribed user within 10 seconds of an Incident being verified. | A late warning has no value. | `test_integration_pipeline.py` |
| NFR-02 | The application shall work on a low-end Android device over 3G. | The actual device profile of the user base. | Offline queue and shell caching; `test_pwa.py` |
| NFR-03 | **The driver-facing view shall be passive and read-only.** No feature shall require typing while in motion; reporting shall be possible by voice. | The system must not create the hazard it exists to reduce. | `test_pwa.py`, `test_attachments.py` |
| NFR-04 | **The reported party shall never be identified to other users.** | The system lets people report other people to the police. Without this it is a harassment vector. | `test_report_intake.py` |
| NFR-04a | **A reporter's identity is theirs to disclose.** Recordings carry a voice, so they are private by default and shareable only by their author, revocably. | NFR-04 protects the accused; this protects the accuser. The two were conflated once — see D-029. | `test_attachments.py`, `test_public_map.py` |
| NFR-05 | No part of the interface shall claim that the system dispatches emergency services. | Liability, and honesty about what the system does. | `test_pwa.py` |
| NFR-06 | Location data shall be retained only while an Incident is active. No individual shall be tracked over time. | Privacy — the system knows where people are. | Staleness sweep; no trajectory is stored |
| NFR-07 | The incident map shall load in under 3 seconds on a 3G connection. | Usability under real conditions. | No build step, cache-first shell; **not measured** |

**NFR-07 is not verified.** No performance measurement was taken against a throttled
connection. It is stated as a target and should not be read as a claim. Recorded honestly
rather than asserted.

---

## 5. Use cases

The four that carry the system. Others are variations on these.

### UC-01 — Report something blocking the road

| | |
|---|---|
| **Actor** | Commuter (signed in) |
| **Pre** | The user has an account and a location, from GPS or the map |
| **Post** | A permanent report exists, and warnings for it are queued |
| **Requirements** | FR-09 to FR-18 |

1. The user selects an incident type.
2. The user provides a location.
3. The user optionally adds a note, photographs and a recording.
4. The system saves the report and queues its notifications **in one transaction**.
5. The system confirms.

**A1 — no connection.** At step 4 the report is stored on the device with the key generated
at step 1, and sent when the connection returns. The user is told it is queued, not that it
was sent.
**A2 — duplicate key.** The system returns the original report. A duplicate is the same
fact arriving twice, not an error.
**A3 — evidence rejected.** The report stands and the user is told which attachment failed
and why. Evidence is an addition to a report, never a precondition.

### UC-02 — Check the road ahead

| | |
|---|---|
| **Actor** | Anyone, including a signed-out visitor |
| **Pre** | None |
| **Post** | The user knows what is blocking the roads they can see |
| **Requirements** | FR-41, FR-42 |

1. The user opens the application.
2. The system shows current Incidents, sized and coloured by status.
3. The user selects one.
4. The system shows its type, status and how recently it was reported.
5. **If signed out**, the system names what an account would add and offers to sign in.

**A1 — the map fails to load.** Tiles come from a third party over the same poor connection
the system assumes. The list carries the same information and the view still works.

### UC-03 — Send a warden

| | |
|---|---|
| **Actor** | Traffic control officer — *the primary actor* |
| **Pre** | An Incident has reached 0.70 |
| **Post** | A warden is assigned; the Incident is *assigned* |
| **Requirements** | FR-26, FR-27, FR-29, FR-30 |

1. The officer opens the dispatch queue, ranked by confidence.
2. The officer opens the evidence: each reporter, their credibility, the weight each report
   carried.
3. The officer selects an available warden and assigns.

**A1 — confidence has fallen below 0.70 in the meantime.** The action is refused with its
reason. The interface never offered it, because it asks the API which actions exist.

### UC-04 — Close the loop

| | |
|---|---|
| **Actor** | Traffic warden |
| **Pre** | The Incident is assigned to this warden |
| **Post** | The Incident is resolved; every contributing reporter's reputation has moved |
| **Requirements** | FR-32, FR-33, FR-34, FR-40 |

1. The warden attends and records what was found.
2. The system resolves the Incident.
3. The system raises or lowers each contributing reporter's reputation.
4. The system queues a clearance message for everyone who was warned.

**Step 4 is the Partial requirement, FR-40.** The code path exists and is wired; nothing
tests it and no seeded Incident demonstrates it. Stated here rather than left for a reader
to discover.

---

## 6. Requirements that were cut, and why

Cutting deliberately against an estimate is itself a requirements activity. The full
reasoning is in `02-problem-and-scope.md` Section 4 and `06-effort-estimation.md` Section 9.

| Cut | Priority | Why | Where it went |
|---|---|---|---|
| Ride-sharing / matching stranded commuters | Won't | An entire second product — matching, payments, identity, passenger safety, liability. Shares nothing with the report pipeline. | Future evolution, headline item |
| Subscription trotro and taxi services | Won't | A third product: billing, schedules, capacity. | Backlog |
| Real emergency services integration | Won't | Cannot be done inside an exam, and simulating it creates real liability if believed. | Reframed as an escalation flag — NFR-05 |
| Trotro fare-abuse adjudication | Won't | Needs a complete reference dataset of approved routes and fares. | Kept as a report type with no adjudication |
| Turn-by-turn rerouting | Won't | Needs a routing engine and the full road network. | Advisory only |
| Separate road-condition reviews | Won't | A road review *is* a report. Two capture mechanisms for one concept. | Merged into report type 6 |

**The unification is the single most important requirements decision.** Five items in the
original brief became one report pipeline differentiated only by type. They differ in who
acts on them, not in how they are captured, grouped or scored. That converted a wish-list
into one well-engineered core, and it is what made the advanced concept affordable.

---

## 7. Traceability summary

| Group | Requirements | Implemented | Partial |
|---|---:|---:|---:|
| Accounts and roles | FR-01 – FR-08 | 8 | 0 |
| Reporting | FR-09 – FR-18 | 10 | 0 |
| Grouping and lifecycle | FR-19 – FR-28 | 10 | 0 |
| Dispatch and reputation | FR-29 – FR-34 | 6 | 0 |
| Warning commuters | FR-35 – FR-40 | 5 | **1** |
| Public map and privacy | FR-41 – FR-46 | 6 | 0 |
| Administration | FR-47 – FR-50 | 4 | 0 |
| **Total** | **50** | **49** | **1** |

Non-functional: seven stated, six verified by test, **one (NFR-07) stated as a target and
not measured**.

The two gaps are named rather than rounded away. A specification claiming fifty of fifty
would be a less useful document and a less honest one.
