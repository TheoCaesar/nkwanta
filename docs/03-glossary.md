# Glossary — Every Technical Term, in Plain English

*Last updated: 12 August 2026*

Every term used anywhere in this project appears here. Each entry follows the same shape:

> **The term** — what it means in ordinary words. *Why it matters here.*

If you meet a term in any project document that is not in this list, that is a bug in the
documentation. Add it.

---

## Part 1 — Terms in the advanced concept

These are the ones that matter most. They are the vocabulary you will be asked about in
the viva.

---

### Event

**Plain English:** A permanent note saying "this thing happened, at this time." You write
it once. You never go back and edit it or rub it out.

Think of a bank statement. If you spend GHS 50, the bank does not quietly reduce your
earlier balance figure. It adds a new line: *−50*. The old lines stay exactly as they
were, forever.

**Why it matters here:** When someone reports a flood at Kwame Nkrumah Circle, that report
becomes an event. Even if the report later turns out to be false, we do not delete it. We
add a *new* event saying "this was contradicted." The full history survives, which means
you can always answer "what did we know, and when did we know it?"

**Also called:** immutable event, append-only record.

---

### Append-only log

**Plain English:** A list you are only ever allowed to add to the bottom of. No editing
the middle, no deleting.

Like a ledger written in pen. Mistakes are corrected by writing a new correcting line,
not by tearing out a page.

**Why it matters here:** It makes the system auditable. A police officer can see exactly
which reports led to a warden being deployed, in the order they came in. Nothing can be
quietly rewritten after the fact.

---

### Projection

**Plain English:** A summary you build by reading through the whole list of events from
the start.

Your bank balance is a projection. The bank does not really "store" your balance as a
fact — it can work it out at any moment by adding up every transaction ever. The balance
is a *view* derived from the events.

**Why it matters here:** An "Incident" — the thing shown on the map as a single flood at
Circle — is not stored directly. It is calculated by reading all the individual reports
and grouping them. If we ever change how grouping works, we replay the reports and get a
new, corrected map. Nothing is lost.

**Related jargon:** *read model*, *materialised view*.

---

### Spatio-temporal clustering

**Plain English:** Grouping reports that are close together in **place** and close
together in **time**, because they are probably about the same real event.

"Spatio" = space, i.e. where. "Temporal" = time, i.e. when.

Five people report an accident within 300 metres of each other in the space of ten
minutes? That is almost certainly one accident, not five. But an accident at Circle on
Monday and another at Circle on Friday are two different accidents, even though the place
is identical. You need **both** dimensions to decide.

**Why it matters here:** This is the heart of the system. Without it the map would show
fifty pins for one accident and would be useless. The two numbers that control it — the
distance limit and the time window — are the most important settings in the whole
application.

---

### Corroboration

**Plain English:** Independent confirmation. Other people, who did not talk to each other,
reporting the same thing.

**Why it matters here:** One report is a rumour. Six reports from six unconnected people
is close to a fact. The system's confidence in an Incident rises with each independent
report that joins its cluster.

---

### Reputation score

**Plain English:** A number tracking how often a particular user's past reports turned out
to be true.

Someone whose reports are consistently confirmed by others earns a higher score, and their
future reports count for more. Someone who repeatedly reports things nobody else can see
earns a lower score, and their reports count for less.

**Why it matters here:** It is the defence against troublemakers and against honest
mistakes. Without it, one person could sit at home and fabricate a road closure. With it,
an unknown or discredited reporter cannot on their own push an Incident over the
threshold where police are alerted.

---

### Time decay

**Plain English:** Old information counting for less than fresh information, automatically,
as time passes.

A report of a flood from four hours ago tells you much less about the road *right now*
than a report from four minutes ago. So its weight shrinks steadily until it stops
affecting the map at all.

**Why it matters here:** It means stale Incidents clean themselves up. Nobody has to
remember to close them. If nobody confirms a report, it quietly fades out on its own.

---

### Transactional outbox

**Plain English:** A way of making sure that "save the report" and "remember to notify
people about it" either **both** happen or **neither** happens — never one without the
other.

Here is the problem it solves. Naively you would write the report to the database, then
send the notifications. But what if the server crashes in the gap between those two steps?
The report is saved and nobody is ever told. Silent failure, and nobody notices.

The fix: in one single database write, save the report *and* save a note-to-self saying
"notifications still owed for this report." Because it is one write, the database
guarantees you get both or neither. A separate background worker then picks up the
notes-to-self and sends them, ticking each one off as it goes. If it crashes, the
unticked notes are still sitting there when it restarts.

The name comes from the note-to-self list — it is an "outbox," like an outbox tray of
letters waiting to be posted.

**Why it matters here:** It is the difference between "we usually warn people" and "we
always warn people." For a system whose whole purpose is warning people, that distinction
is the product.

---

### Transaction

**Plain English:** A group of database changes that the database treats as one indivisible
action. All of them succeed, or all of them are undone.

Like a bank transfer: money leaving one account and arriving in another must happen
together. There is no acceptable world where the first half happened and the second did
not.

---

### At-least-once delivery

**Plain English:** A promise that a message will definitely arrive — but with the honest
admission that it might arrive more than once.

The alternative promises are worse. "At most once" means it might never arrive. "Exactly
once" is extremely difficult to build and, over an unreliable network, essentially
impossible to guarantee. So real systems choose "at least once" and then handle the
duplicates.

**Why it matters here:** If the SMS gateway does not reply, we cannot tell whether the
message went out or not. We resend. That is the right call — better a duplicate warning
than no warning. Which is exactly why we then need the next term.

---

### Idempotency and idempotency keys

**Plain English:** Doing something twice has exactly the same effect as doing it once.

A light switch is *not* idempotent — flicking it twice returns you to where you started.
A lift call button *is* idempotent — pressing it five times summons exactly one lift.

An **idempotency key** is the practical trick for achieving this: attach a unique
reference to each action, and have the receiver remember which references it has already
handled. When a duplicate arrives carrying a reference it has seen before, it is quietly
discarded.

**Why it matters here:** It is what makes at-least-once delivery safe. We can retry
notifications freely, because a duplicate is recognised by its key and dropped. The user
gets exactly one warning even though we may have sent three.

---

### Circuit breaker

**Plain English:** An automatic switch that stops your system from repeatedly calling an
outside service that is clearly broken — and then checks back later to see if it has
recovered.

Named after the electrical device, and it works the same way. Too many failures in a row
and it "trips": all further calls fail instantly without even trying. After a cooling-off
period it lets a single test call through. If that succeeds, normal service resumes.

Without it, a dead SMS provider drags your entire system down with it. Every request piles
up waiting thirty seconds to time out, connections are exhausted, and an outage in someone
else's system becomes an outage in yours.

**Why it matters here:** SMS and push gateways in this region fail regularly. The system
must degrade gracefully rather than collapse. This is also very easy to *demonstrate* in a
viva, which makes it worth building.

---

### Order independence and convergence

**Plain English:** The final answer does not depend on what order the information arrived
in.

If Kofi's report reaches the server before Ama's, or Ama's before Kofi's, the resulting
Incident on the map must be **identical**. Over a mobile network, arrival order is
essentially random — one person is on 4G, another on a struggling 3G connection. If order
mattered, two users could legitimately see two different maps of the same reality.

**Why it matters here:** It is the single property most worth testing, and the one most
worth being able to articulate in a viva. It is also the reason this project is genuinely
"advanced" rather than merely "large."

**Related jargon:** *commutative* (order does not matter: 2+3 = 3+2) and *associative*
(grouping does not matter: (2+3)+4 = 2+(3+4)). Merging incidents must be both.

---

### CRDT (Conflict-free Replicated Data Type)

**Plain English:** A way of structuring data so that separate copies, updated
independently, always end up agreeing — without anyone having to arbitrate.

**Why it matters here:** We are not building a full CRDT. But our merge rule follows the
same reasoning, and citing the connection shows the design was reasoned about rather than
stumbled into.

---

### Property-based testing

**Plain English:** Instead of writing test cases by hand, you state a rule that must
*always* be true, and let the computer invent hundreds of random scenarios trying to break
it.

Ordinary test: "given these 3 reports, expect 1 incident." You wrote the 3 reports, so you
only test what you already thought of.

Property test: "for **any** set of reports whatsoever, in **any** arrival order, the result
is the same." The tool then generates 500 random sets in random orders and hunts for a
counter-example. When it finds one, it automatically shrinks it to the smallest failing
case — often two reports and a timestamp — so you can see exactly what broke.

**Why it matters here:** It finds the edge cases you would never think of, particularly
around timing boundaries. It is also uncommon in student submissions, so it stands out.

**Tool used:** Hypothesis (Python).

---

### State machine / guarded transition

**Plain English:** A written-down list of the states a thing can be in, and exactly which
moves between them are allowed.

An Incident here goes: Reported → Corroborated → Verified → Assigned → Resolved. A
**guard** is a rule blocking an illegal move — you cannot mark an Incident as Resolved if
it was never Assigned to anyone.

**Why it matters here:** It converts a whole class of bugs into impossibilities. Rather
than scattering `if` checks through the code and hoping you caught them all, the illegal
move simply cannot be expressed.

---

## Part 2 — Architecture and process terms

---

### CQRS (Command Query Responsibility Segregation)

**Plain English:** Keeping the code that *changes* things separate from the code that
*reads* things.

Writing is about rules and validation. Reading is about speed and convenient shapes. They
pull in opposite directions, so you stop forcing one model to serve both.

---

### Event bus

**Plain English:** An internal announcement channel. One part of the system announces
"a report was accepted"; any number of other parts listen and react, without the announcer
knowing or caring who is listening.

**Why it matters here:** Adding a new reaction later — say, an analytics dashboard —
requires no change to the reporting code at all.

---

### Consumer / projector

**Plain English:** A piece of code that listens to the announcement channel and does one
job in response. The projector's job is keeping the map view up to date.

---

### Snapshotting

**Plain English:** Saving a periodic "here is the total so far" marker, so you do not have
to re-add every transaction since the beginning of time.

**Why it matters here:** We are deliberately **not** doing this — it is recorded as
accepted technical debt. With a few thousand reports, replaying from the start is fast
enough. With a few million it would not be. Knowing where the ceiling is, and saying so, is
the point.

---

### Backpressure

**Plain English:** A way for an overloaded part of the system to tell the part feeding it
to slow down, instead of silently drowning.

**Why it matters here:** Our background worker has none. During a citywide flood, reports
could arrive faster than it processes them. This is a recorded debt item with a known fix.

---

### Dead letter queue

**Plain English:** A holding tray for messages that failed repeatedly, so they can be
examined by a human rather than retried forever or thrown away.

---

### Optimistic concurrency

**Plain English:** Letting two people edit the same thing at once, and detecting the clash
at save time rather than locking anyone out up front.

Each record carries a version number. You read version 4, and when you save you say "I am
updating version 4." If someone else already saved version 5, your save is rejected and
you are asked to retry with fresh data.

---

### Hexagonal architecture (ports and adapters)

**Plain English:** Keeping the core rules of your system in the middle, knowing nothing
about the outside world, with plug-in pieces around the edge that connect it to the
database, the web, the SMS provider and so on.

The core says "I need somewhere to save reports" (a **port**). A specific PostgreSQL
implementation plugs into that (an **adapter**). Swapping PostgreSQL for something else
means writing a new adapter and touching no core logic.

**Why it matters here:** The clustering and confidence logic ends up as pure functions with
no database involved, which is exactly why they are so easy to property-test.

---

### PostGIS

**Plain English:** An add-on for the PostgreSQL database that teaches it about maps —
distances, points, areas, and "find me everything within 300 metres of here."

---

## Part 3 — Software engineering process terms

---

### Technical debt

**Plain English:** A shortcut taken now that will cost more to fix later than it would have
cost to do properly today — the interest you pay on borrowed time.

Not all debt is bad. Deliberately borrowing time to hit a 48-hour deadline is a legitimate
engineering decision. Borrowing it accidentally, or never writing it down, is not.

**Why it matters here:** Worth 6 of the 50 marks. Each item is recorded as:
**Debt → Cause → Impact → Priority → Proposed Resolution**, and classified as *acceptable
for now*, *scheduled for a future release*, or *critical*.

---

### Functional vs non-functional requirement

**Plain English:**

- **Functional** — what the system *does*. "A user can report an accident."
- **Non-functional** — how *well* it does it. "The report must reach nearby users within
  ten seconds." "It must work on a 3G connection."

Non-functional requirements are where most real systems fail, and where most student
submissions are thin.

---

### MoSCoW prioritisation

**Plain English:** Sorting requirements into four buckets — **Mu**st have, **S**hould have,
**Co**uld have, **W**on't have this time.

The last bucket is the valuable one. Writing down what you consciously chose *not* to
build, and why, is evidence of judgement. Silently omitting it looks like you forgot.

---

### Use Case Points

**Plain English:** A way of estimating how long software will take by counting how many
distinct things it must do and how many kinds of user it serves, weighting each by
difficulty, and multiplying by an hours-per-point figure.

**Why it matters here:** Effort estimation is worth 5 marks, and the exam requires the
estimate to have visibly shaped what was built.

---

### Viva voce (usually just "viva")

**Plain English:** A spoken examination. The examiner sits with you, asks you to
demonstrate the software, and questions you about it.

Latin for "with the living voice" — meaning tested by talking rather than by writing.

**Why it matters here:** Rule 10 of the examination paper says the examiner **may
conduct an individual viva voce or demo to verify authorship, understanding and
implementation**. Rule 11 lists what you can be asked about: requirements, effort
estimation, architecture, implementation decisions, testing strategy and technical debt.

Two consequences shaped this whole project:

1. **Never include anything you cannot explain from first principles.** A clever feature
   you cannot account for is worth less than a simple one you can — it invites exactly
   the question you cannot answer.
2. Every module has a plain-language explainer in `docs/explainers/`, each ending with a
   thirty-second summary written to be said aloud.

---

### B01, B02, B03 … (build task identifiers)

**Plain English:** Labels for individual pieces of work. "B" is for *build task*.

They come from the bottom-up effort estimate in `06-effort-estimation.md` §4, and are
reused in the schedule, in commit messages, in the debt register and in test file
headers, so any one of those can be traced to the others.

The numbers are not in time order — the schedule reorders them by value and risk.

---

### Lehman's laws of software evolution

**Plain English:** A set of observations that software in real use must keep changing or it
becomes useless, and that as it changes it gets more complex unless someone actively works
to keep it simple.

**Why it matters here:** Covered in Session 4 of the course, and directly relevant to the
Maintenance and Future Evolution section, worth 3 marks.
