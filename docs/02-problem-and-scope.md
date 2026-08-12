# Problem, Users and Scope

*Last updated: 12 August 2026*
*Derived from the original brief in [`00-original-brief.txt`](00-original-brief.txt)*

---

## 1. The problem

Urban Ghana carries far more vehicles than its road network was built for. Private cars,
trucks and motorbikes dominate. Commercial transport is fragmented across okada, ride-hailing,
taxis and trotro. Subsidised public transport is thin, and there are fewer than five urban
trains. The result is bumper-to-bumper traffic at predictable hours — inbound in the morning,
outbound at night.

Congestion is then made considerably worse by events that nobody has a reliable way of
announcing:

- **road accidents**, which block lanes for as long as they take to clear
- **flooding and heavy rain**, which closes routes with no warning
- **power cuts**, which kill traffic lights at major junctions — a junction with no signal
  and no warden becomes a standstill within minutes
- **roadworks and maintenance**, often uncoordinated between agencies
- **road surface failure** — potholes, washouts, broken drainage

Two groups of people suffer, and neither can help the other:

**Commuters** set off with no idea what is ahead. By the time they can see the problem they
are already in it and cannot reroute. The information that would have saved them exists — the
drivers already stuck know all about it — but there is no channel connecting them.

**Authorities** — the Motor Transport and Traffic Directorate, metro traffic wardens,
emergency services — find out late and through informal channels. When a signal fails at a
major junction, there is no systematic way for that fact to reach whoever can deploy a warden.

### The problem statement

> Road users possess accurate, real-time knowledge of what is blocking traffic, but have no
> reliable way to pass it to the commuters behind them or to the authorities who can act on
> it. Congestion is therefore prolonged well beyond the duration of its underlying cause.

---

## 2. Who the system is for

| Actor | What they do | What they get |
|---|---|---|
| **Commuter / motorist** | Reports what is blocking the road; subscribes to routes they travel | Warnings about their route before setting out; alternative routes |
| **Pedestrian / passenger** | Reports hazards, flooding, failed signals | Same warnings, on foot or waiting at a stop |
| **Traffic control officer (MTTD)** | Monitors the verified incident queue; assigns wardens | A ranked, deduplicated, confidence-scored queue instead of scattered phone calls |
| **Traffic warden** | Receives deployment assignments; confirms arrival and resolution | Clear instruction on where to go and why |
| **Road maintenance agency** | Reviews surface-condition reports | Structured, located, corroborated defect reports |
| **System administrator** | Manages users, moderates abuse, tunes thresholds | Oversight and abuse controls |

**Primary actor: the traffic control officer.** Commuters are the sensor network; the officer
is the person whose job the system exists to do. This choice matters — it means the incident
queue is the core screen, and the system can be demonstrated convincingly without a large
real-world user base.

---

## 3. What is being built — in scope

Everything here shares one pipeline: a typed, located, timestamped report that gets grouped,
scored, and routed to someone.

| # | Feature | Notes |
|---|---|---|
| 1 | **Report an incident** | Six types: accident, flood, road closure, signal outage, roadworks, road-surface defect. Location, time, optional photo and note. |
| 2 | **Grouping and confidence scoring** | Reports close in place and time become one Incident. Confidence from reporter reputation, decayed over time. *The advanced concept — see [`04-advanced-concept.md`](04-advanced-concept.md).* |
| 3 | **Reporter reputation** | Rises when reports are confirmed, falls when contradicted. The defence against false reports. |
| 4 | **Incident lifecycle** | Reported → Corroborated → Verified → Assigned → Resolved. Illegal transitions blocked. |
| 5 | **Commuter advisory** | Users subscribe to corridors; incidents on those corridors trigger a warning. |
| 6 | **Authority dispatch queue** | Verified incidents above the confidence threshold enter a queue an officer can assign. |
| 7 | **Live public map** | Current incidents with type, confidence and age. The demonstration surface. |
| 8 | **Roles and permissions** | Commuter, officer, admin. |
| 9 | **Abuse controls** | Rate limiting, reputation floor before escalation, reported party never identified to other users. |

### Deliberately unified

Five separate items in the original brief collapsed into **one** report pipeline
differentiated only by type: traffic impediments, accidents, maintenance reports, road
condition reviews, and signal outages requiring warden deployment. They differ in who acts
on them, not in how they are captured, grouped or scored.

This is the single most important design decision in the project. It converts a sprawling
wish-list into one well-engineered core.

---

## 4. What is deliberately excluded — and why

**These are not omissions. They are decisions, and they are worth marks.** The paper assesses
requirements prioritisation (7 marks) and requires effort estimation to visibly shape scope
(5 marks). Cutting deliberately and documenting the reasoning is how those marks are earned.

| Excluded | Reason | Where it goes |
|---|---|---|
| **Ride-sharing / matching stranded commuters with private vehicles** | An entire second product: matching, payments, identity verification, passenger safety, insurance and liability. Shares nothing with the report pipeline. The largest scope risk in the brief. | Future Evolution — headline item |
| **Subscription trotro and taxi services** | A third product: billing, recurring payments, schedules, capacity management. | Backlog — Won't have |
| **Real emergency services integration** | Cannot integrate with 191/193 within an exam. Simulating it creates genuine liability if anyone believes the app summoned help. | Reframed as an escalation flag in an authority queue |
| **Trotro fare-abuse adjudication (route splitting)** | Requires a complete reference dataset of approved routes and fares to judge against. That is the whole TroTroGo system, previously considered and set aside. | Kept as a plain report type that records the complaint with no resolution workflow — near-zero cost |
| **Separate road reviews / ratings feature** | A road-condition review *is* a report. Building two capture mechanisms for one concept is duplication. | Merged into report type 6 |
| **Automatic rerouting / turn-by-turn navigation** | Requires a routing engine and full road network data. Advisory only: "your route is affected, consider X." | Future Evolution |

### MoSCoW summary

- **Must have** — features 1, 2, 3, 4, 7, 8
- **Should have** — features 5, 6, 9
- **Could have** — photo attachments, incident comment threads, warden mobile confirmation
- **Won't have this time** — ride-sharing, subscriptions, real emergency dispatch, fare
  adjudication, turn-by-turn navigation

---

## 5. Non-functional requirements

These are where most submissions are thin. Two of them arose from reviewing the original
brief rather than from the brief itself, and both are worth stating explicitly.

| ID | Requirement | Why |
|---|---|---|
| NFR-1 | Reports must reach subscribed users within 10 seconds of verification | Late warnings have no value |
| NFR-2 | Must work on 3G and on low-end Android devices | The actual device profile of the user base |
| NFR-3 | **The driver-facing view is passive and read-only.** No typing while in motion. Reporting is passenger-first or voice-first. | The system must not create the hazard it exists to reduce. A road safety application that encourages phone use while driving is self-defeating. |
| NFR-4 | **The reported party is never identified to other users.** Escalation to authorities requires a reputation floor. Rate limits per user per hour. | The system lets users report other people to the police. Without controls that is a harassment and false-accusation vector. This will be asked about. |
| NFR-5 | No claim, anywhere in the interface, that the app dispatches emergency services | Liability, and honesty about what the system actually does |
| NFR-6 | Location data retained only as long as an incident is active; no persistent tracking of individuals | Privacy — the system knows where people are |
| NFR-7 | Incident map loads in under 3 seconds on a 3G connection | Usability under real conditions |

NFR-3 and NFR-4 came out of design review, not the original brief. Both are the kind of
consideration that distinguishes a submission that was thought about from one that was
merely built.

---

## 6. Backlog — the deliberately deferred

Kept so nothing is lost, and so the Future Evolution section has real content.

| Item | Priority | Notes |
|---|---|---|
| Ride-sharing for stranded commuters | High | The headline evolution item. Needs identity verification, payments, safety design. |
| Turn-by-turn rerouting | High | Requires routing engine and network data |
| Subscription transport services | Medium | Billing and scheduling subsystem |
| Trotro fare authority and adjudication | Medium | Effectively a separate system — see the TroTroGo concept |
| USSD / SMS reporting for feature phones | Medium | Significantly widens reach |
| Twi and Ga localisation | Medium | Real accessibility need for the actual user base |
| Integration with traffic count sensors | Low | Depends on infrastructure that does not exist yet |
| Warden mobile app with arrival confirmation | Low | Closes the dispatch loop |

---

## 7. Scope justification

Nine features across three user roles, sharing one pipeline and one scoring engine. Effort
estimation using Use Case Points will be performed next and will confirm or force revision of
this scope. **If the estimate exceeds the available implementation hours, features move from
Should-have to Could-have — not the other way round.**

The estimate drives the scope. That is the point of doing it, and the paper asks for the
evidence.
