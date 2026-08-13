# Explainer 07 — Voice notes and recorded evidence

*Covers `app/services/attachments.py`, `app/routers/attachments.py`, the `Attachment`
model, and the evidence bonus in `app/confidence.py`.*

---

## 1. Why voice exists at all

NFR-3 in the SRS says: *the driver-facing view is passive and read-only; the system never
asks someone to type while driving.*

Until this module, that was **a constraint with no answer**. The requirement said what the
system would not do without saying how a driver reports anything. In a viva, "how does a
driver report a hazard?" would have been a question to concede.

Hold a button, speak, release.

That is the answer, and it happens to suit the user base better than a keyboard does
regardless of safety — spoken Twi or Ga into a phone is a lower barrier than typed English.

**If asked why not just let them type at a red light:** because a system that assumes
people will only use it when stationary is a system designed for how users ought to
behave rather than how they do. The safe path has to be the convenient one.

---

## 2. Where the bytes live, and why it is a separate table

Attachments are a **separate table**, not columns on `reports`. Two reasons, and the
first is the one that matters.

`reports` is the hottest table in the system — clustering scans it constantly. Binary
data stored in those rows competes with that workload for the database's buffer cache, so
a few hundred voice notes would slow down every clustering query even though none of them
ever reads the audio. In a table nothing scans, audio nobody is playing costs nothing.

Second, a report may carry none, one or several attachments. Nullable columns per kind
would mean a schema change for every new kind.

### Storing binary in PostgreSQL is the wrong answer at scale

Said plainly rather than defended. Object storage with presigned URLs is right: the API
issues a URL, the client uploads directly, playback goes straight from storage, and the
application never touches the bytes.

It is the right answer **here** because object storage means a fourth hosting account and
a fourth thing that can fail on deploy day, on a project whose largest sustained risk was
deployment. Recorded as decision D-019 and debt **TD-19**, which is the item that fails
first under real adoption.

Caps: **512 KB** for audio, **250 KB** for images. Enforced in the upload handler *and* as
a database CHECK constraint — a limit living only in application code is one a future
endpoint can forget.

---

## 3. Nothing the client sends can be believed

A file arriving over HTTP carries three things the client controls completely: its bytes,
its declared content type, and its filename. None can be trusted.

| Check | Why |
|---|---|
| **Allow-list of content types** | Never a block-list. A block-list is a list of the attacks you happened to think of. |
| Codec parameters stripped | Chrome sends `audio/webm;codecs=opus`. Rejecting that rejects the only thing browsers actually produce. |
| Size cap, in code and in the schema | Two independent enforcement points |
| Empty file refused | — |
| Only the report's author may attach | Reports are immutable records of what someone said. Letting a third party bolt evidence onto someone else's statement makes the record mean something its author never asserted. |
| One voice note per report, four attachments total | Bounds the damage from a malicious or broken client |

### Serving user-uploaded bytes safely

This is the part worth volunteering, because it is a genuine vulnerability class rather
than a validation rule.

A browser that decides for itself what a file contains can be tricked. Someone uploads a
file declared as `audio/webm` whose bytes are actually HTML; a browser sniffs the content,
sees markup, and **executes it on your origin** — with access to your cookies and your
session.

Three headers close it:

```
Content-Type: audio/webm             the type we recorded, stated explicitly
X-Content-Type-Options: nosniff      the browser may not overrule us
Content-Disposition: attachment      never render inline, whatever it is
```

**If asked:** "Serving user-uploaded content from your own origin is how stored XSS
happens. `nosniff` stops the browser second-guessing the declared type, and
`Content-Disposition: attachment` means even if it were HTML it would be downloaded
rather than executed."

---

## 4. Who hears a recording — and why the reporter decides

This is the design decision I would lead with, and it is worth telling as the story of
how it changed, because the first version was wrong.

**A recording of someone's voice is close to biometric.** It identifies the person who
made it in a way a text note does not. The first implementation therefore restricted
playback to the recorder and the control room, citing NFR-4.

That reasoning had **two flaws**, and the first is an error rather than a judgement call.

**It conflated two different concerns.** NFR-4 protects the *reported party* — the person
being accused. I applied it to the *reporter*. Those are not the same, and the second does
not follow from the first. A flood on Spintex Road accuses nobody, so there is no reported
party and the justification did not apply at all.

**It threw away most of the value of voice.** "Tipper truck across two lanes, backed up to
Odorna" tells a commuter far more than *accident, confidence 0.88*. That is precisely why
voice is worth capturing, and locking it away made the feature nearly pointless for the
people it was built for.

### The concern is real, but narrow

It bites on **accusatory** reports — naming a trotro driver, reporting a violation — where
the speaker may be recognised by the person they accused. In a neighbourhood, that is not
hypothetical, and the original brief contained exactly those cases.

It does not bite on flooding.

**No single rule fits both, and the reporter is the only person who knows which case they
are in.** So they are asked.

### How it works now

| Who | Unshared | Shared |
|---|---|---|
| The reporter | plays | plays |
| Officers, wardens, admins | plays | plays |
| Other commuters | **nothing** | plays |
| Signed-out visitors | **nothing** | plays |

- **Default is off.** Consent is given, never assumed — a client that forgets the field
  has not consented on the user's behalf.
- **Withdrawable at any time**, via `PATCH /attachments/{id}/visibility`.
- **Only the reporter may change it.** Not even an officer. Consent somebody else can
  give on your behalf is not consent, and consent that cannot be withdrawn is not a
  choice.
- **The control room can always play it**, shared or not. A warden being sent to a
  junction should hear why.

Two details that matter:

An unauthorised request returns **404, not 403**. A 403 confirms the attachment exists,
which is itself information about someone else's report.

The *listing* endpoint filters with the same rule that guards the bytes, so an unshared
recording is invisible rather than merely unplayable. Listing something and then refusing
it announces that it is there.

### What this still does not solve

A reporter who wants to help but does not want their voice public must still choose
between the two.

The real resolution is **transcription** — publish the text, restrict the audio, and
nobody has to choose. That is why transcription moved from a nice-to-have to the top of
the evolution plan: it is not a feature, it is the answer to a tension the current design
only manages.

*Recorded as D-029, superseding D-028. The superseded entry is kept unedited — a decision
log that quietly deletes its mistakes is not a record of anything.*

---

## 5. Recorded evidence counts for more

Media is tied into the advanced concept rather than bolted beside it. A report carrying a
voice note or photograph gets a **1.25× weight bonus** in the confidence calculation.

The reasoning: a recording is much harder to fabricate from an armchair than a tapped
coordinate. It demonstrates the reporter was somewhere, with something to describe.

Three constraints keep that honest:

**The bonus is capped.** A weighted report can never exceed the single-report ceiling of
0.45, so an attachment cannot on its own carry anything past the 0.70 escalation
threshold. Corroboration remains the only route to verification — otherwise "attach any
audio file" would become a way of buying credibility.

**It multiplies reputation rather than replacing it.** Someone with a 0.05 record who
attaches audio still scores below 0.05. You cannot restore a ruined standing with a
recording.

**It is optional in the code.** `score()` takes `with_recorded_evidence` as an optional
set, so every existing caller and all 53 pre-existing confidence property tests were
unaffected. A test asserts the two paths agree when the set is empty.

---

## 6. What property testing found while building this

The clustering property suite failed during this step, on a test that had passed for
several sessions:

```
assert min(lons) <= centroid_longitude <= max(lons)
AssertionError: assert -0.11988551688412255 <= -0.11988551688412256
```

Three **identical** longitudes, and their mean came out one unit in the last place
*below* the minimum input.

Nothing overflowed. The exact mean is simply not representable in binary floating point,
and the nearest representable value happens to sit outside the range of the inputs.

Physically that is femtometres — utterly meaningless. As an invariant it was false, and a
cluster centroid escaping its own members' bounding box is precisely the kind of thing
that quietly violates a database constraint two years later.

**No example-based test would have found it.** It needs several identical coordinates with
an unlucky bit pattern, which nobody writes by hand.

Fixed with `math.fsum` for an exactly-rounded sum, plus a clamp to the bounding box so
the invariant holds by construction rather than by luck. Verified at 1000 generated
examples, and pinned with a regression test using the exact failing value.

**If asked what property-based testing actually bought you, this is the answer** — a real
invariant violation in code that had been passing tests, reviewed, and deployed.

---

## 7. What is deliberately missing

| Missing | Why | Recorded |
|---|---|---|
| **Transcription of voice notes** | Needs a speech API, and Twi and Ga are poorly served by the commercial ones | **Top of the evolution plan** — see §4. Not a feature, the resolution to a real tension |
| Server-side duration verification | Needs `ffmpeg` for a value that is displayed and never acted upon | TD-20 |
| Virus scanning | No sensible option inside the examination window | Debt |
| Client-side downscaling before upload | The cap rejects large files rather than shrinking them | Front-end work |
| Playback in the officer interface | The endpoint exists; the player arrives with the web page at B22 | Planned |

---

## 8. The thirty-second summary

> Voice notes are the answer to NFR-3 — the rule that the system must never ask anyone to
> type while driving, which until then was a constraint with no corresponding feature.
> Attachments live in their own table rather than as columns on reports, because reports
> are scanned constantly by clustering and binary data there would compete for buffer
> cache. Uploads are validated against an allow-list of content types, with caps enforced
> both in code and in the schema, and served with `nosniff` and
> `Content-Disposition: attachment` so a file claiming to be audio cannot be sniffed as
> HTML and executed on our origin. A recording identifies its speaker, so **the reporter
> decides** whether other commuters hear it, defaulting to private and withdrawable at any
> time — I originally imposed a blanket restriction, which conflated protecting a reported
> party with protecting a reporter and cost more transparency than it needed to. The real
> resolution is transcription: publish the text, restrict the audio, and nobody has to
> choose. A report carrying evidence weighs 1.25× more in the confidence calculation,
> capped so corroboration remains the only route to verification.
