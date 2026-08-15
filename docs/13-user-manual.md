# User Manual

**Nkwanta — knowing what is blocking the road**

*14 August 2026 · Version 1.0*

---

## Before anything else: a safety note

**Never use this while driving.** Hand the phone to a passenger, or stop somewhere safe.

The map is designed to be *read*, not operated — you can see what is ahead without touching
anything. Reporting is a different matter, and if you must report while you are the one
driving, use the voice note: hold the button, speak, let go. It is there so that nobody has
a reason to type at a junction.

Nkwanta **does not call the police or an ambulance.** It puts your report in front of a
traffic control officer who decides whether to send a traffic warden. If someone is hurt,
call the emergency services yourself, first.

---

## 1. What Nkwanta is for

You are heading somewhere. Is the road clear?

Nkwanta answers that from reports by other people on the same roads. When several people
report the same thing, the system recognises it as one event and becomes more confident
about it. When enough people confirm it, a traffic officer sees it and can send a warden.

You do not need an account to look. You need one to report, to be warned about the roads
you use, and to see who reported what.

---

## 2. Getting started

### Opening it

Go to **https://nkwanta.onrender.com/** in any modern browser.

> **If the first page takes a while**, it can take up to a minute. The application sleeps
> when nobody is using it and has to wake up. Everything after that is immediate.

### Installing it on your phone

Nkwanta can be installed like an app, and this is worth doing — it opens faster and works
with a poor connection.

- **Android (Chrome):** tap the ⋮ menu → *Install app* or *Add to Home screen*
- **iPhone (Safari):** tap the Share button → *Add to Home Screen*

### Creating an account

Tap **Create an account**. You need an email address, a name and a password of at least
eight characters.

You will be created as a **commuter**. Officer, warden and administrator accounts are
created only by an administrator — nobody can sign themselves up as police.

> **Your email cannot be changed later.** It is how you sign in, and the system cannot yet
> send a verification message to a new address. Type it carefully.

---

## 3. The map

The first thing you see. Each circle is an incident.

**Colour tells you how confirmed it is:**

| Colour | Meaning |
|---|---|
| 🔴 Red — *verified* | Enough people have reported it that a traffic officer has been alerted |
| 🟡 Amber — *corroborated* | Several people independently, but not yet enough for the police |
| ⚪ Grey — *unconfirmed* | One report, or reports the system is not yet sure about |
| 🔵 Blue — *warden sent* | Someone has been dispatched |

**Size follows the same thing** — a bigger circle is a more confirmed incident.

Tap any circle to see what it is and how long ago it was last reported.

### What you see when signed out

Type, place, status and how recently — enough to decide whether to take that road.

You will not see who reported it, their photographs or recordings, or the numeric accuracy
score. All three are about the *people* rather than the road, and the score is built from
their track records. Sign in and they appear.

### If the map does not load

The map needs to fetch imagery from another service, and on a weak connection that can
fail. The list of incidents below it carries the same information. Nothing is lost.

---

## 4. Reporting something

Tap **Report**.

1. **What is blocking the road** — choose one of six: accident, flooding, road closure,
   lights out, roadworks, bad surface.
2. **Where** — tap *Use my location*, or pick the spot on the map.
3. **A note** — optional. "Two lanes blocked, backed up to Odorna" is more use than
   "accident".
4. **A photograph** — optional. You see it full size before it is sent, so you can check
   it shows what you mean.
5. **A voice note** — optional. Tap to start, tap to stop. **It stops by itself at the
   limit** rather than letting you talk for two minutes and then refusing it, and you can
   play it back before sending.

Then **Submit report**.

### About sharing your voice

**A recording is private unless you choose to share it.** Your voice identifies you, and
whether that matters is your call, not the system's. Officers and wardens can always hear
it — they need to, to act on it — but other commuters only if you tick the box.

You can change your mind later, in either direction. Nobody else can change it for you, not
even an administrator.

Photographs work the other way: shared by default, because a picture of a flooded road
describes the road rather than you. You can un-share one if it caught something you did not
notice.

### Reporting with no signal

**Just report anyway.** Your report is saved on the phone and sends itself when the
connection comes back. You will see *"No signal — your report is saved and will send by
itself."*

It cannot be sent twice, however many times the phone retries. That is handled.

### If something could not be attached

You will see *"Reported, but your photograph could not be attached"* with the reason. **Your
report still counts** — evidence is an addition to a report, never a requirement for one.
You can file a fresh report with the photograph if it matters.

---

## 5. Being warned about your routes

Tap **Routes**.

You will see named stretches of road. Follow the ones you use.

When something is reported on a road you follow and enough people confirm it, you get a
warning under **Alerts**. When it is cleared, you are told that too.

You are warned earlier than the police are called — deliberately. A commuter deciding
whether to leave now benefits from an early warning; sending a warden to something
unconfirmed wastes a warden.

**You will never be warned twice about the same incident**, however the reports arrive or
however many times the system retries.

---

## 6. Your profile

Tap **You**.

**Your credibility** — a percentage showing how often your reports have turned out to be
true. Everyone starts at 50%.

It rises when a warden confirms something you reported and falls when one attends and finds
nothing. It decides how much weight your reports carry: a report from someone with a strong
record counts for more.

It moves slowly on purpose. Reaching 90% takes around eighteen confirmations. Slow to build
means hard to fake, and it means one unlucky report does not ruin you.

**Your reports** — everything you have filed. Tap one to open it and see your note, the
exact place and time, and the photographs or recordings you attached. This is where you
check that your evidence actually arrived.

**Account** — change your display name or password. Your email is fixed.

---

## 7. For traffic control officers

Signing in as an officer adds a **Dispatch** tab.

### The queue

Incidents that have reached **70% accuracy**, most believable first. Nothing below that
appears — if something matters and the score is low, the answer is more corroboration, not
a lower bar.

### Deciding

Tap **Evidence** on any incident to see everyone who reported it, each person's
credibility, and how much each report contributed to the score.

**This is the point.** The number is not a verdict handed down by the system. It is a
summary you can take apart — five reports from unknown accounts and two from people with
long records reach similar scores by very different routes, and you can see which you are
looking at.

### Sending a warden

Choose an available warden and **Send warden**. You can recall one if you need to.

Buttons you cannot use are not shown. An incident that has not reached the threshold cannot
be assigned; one nobody was sent to cannot be closed. These are rules, not form validation.

---

## 8. For traffic wardens

Signing in as a warden shows only **what has been assigned to you**.

When you have attended, record what you found:

- **Road now clear** — you attended and it is passable again. Everyone who reported it has
  their credibility raised, and everyone who was warned is told the road is clear.
- **Nothing there** — you attended and found nothing blocking the road. Everyone who
  reported it has their credibility lowered.

> **These are different things.** Use *nothing there* when the report was mistaken — not
> when the problem cleared before you arrived. For that, use *road now clear*. The
> difference decides whether honest reporters are penalised for something that was true
> when they reported it.

You can add a note. Do — it is the record of what was actually found.

---

## 9. For administrators

Signing in as an administrator adds an **Admin** tab.

- **System totals** — accounts, reports, incidents, warnings sent, and anything waiting in
  the queue. A queue count above zero that stays there means deliveries are behind.
- **Accounts** — create officer, warden and administrator accounts, change roles, and
  deactivate an account. A deactivated account loses access on its next request, not
  whenever its sign-in expires.
- **Circuit breaker** — the state of outbound delivery. If it shows **open**, deliveries
  are being refused because the destination has been failing; it retries automatically
  after a cooling period.

---

## 10. Common questions

**Can other people see that I reported something?**
Only people signed in, and only your display name and credibility beside the incident. The
person or vehicle a report is *about* is never identified to anyone.

**Can I delete a report?**
No. Reports are permanent — that is what makes the record trustworthy. A report that turns
out to be wrong is not erased; the incident is closed as a false alarm and your credibility
adjusts. What you actually said survives.

**Why did my incident disappear from the map?**
If nobody confirms a report, its weight fades over about 45 minutes and it drops off. That
is deliberate: a four-hour-old unconfirmed report tells you very little about the road now.

**Why does the accuracy figure go down?**
The same fading. An incident nobody has re-reported becomes less certain as it ages.

**I reported something and the map still shows one report.**
Grouping happens a moment after submission, in the background. Give it a few seconds and
refresh.

**Does this call the police?**
No. It puts the incident in front of a traffic control officer who decides. See the safety
note at the top.

---

## 11. If something goes wrong

| Problem | What to do |
|---|---|
| The first page takes ages | Wait up to a minute. The application was asleep. |
| Signed out unexpectedly | Sign-ins last twelve hours. Sign in again. |
| "Incorrect username or password" | The message is the same for an unknown email and a wrong password, deliberately — so nobody can use the form to discover who has an account. Check both. |
| The map is blank but the list works | Map imagery could not be fetched. The list has the same information. |
| A recording will not play | If it is not yours, the person who made it has not shared it. That is their choice and it can be withdrawn at any time. |
| A report seems stuck as queued | It sends when you have a connection. Open the app with signal and it goes. |

---

## Demonstration accounts

For assessment. All use the password **`NkwantaDemo2026`**.

| Account | Role | Shows |
|---|---|---|
| `commuter@nkwanta.demo` | Commuter | Reporting, routes, alerts, profile |
| `officer@nkwanta.demo` | Officer | The dispatch queue and evidence |
| `warden@nkwanta.demo` | Warden | Assigned incidents and resolution |
| `admin@nkwanta.demo` | Administrator | Accounts, totals, circuit breaker |
