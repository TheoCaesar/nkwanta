# Explainer 01 — Authentication and roles

*Covers `app/auth.py`, `app/routers/auth.py`, `app/security.py`, `app/schemas.py`.*
*Written so you can defend this in the viva without re-reading the code.*

---

## 1. The two questions, kept apart

Every protected request asks two different things, and the code keeps them in separate
places on purpose.

| Question | Meaning | Where |
|---|---|---|
| **Authentication** | Who is this? | `get_current_user` in `app/auth.py` |
| **Authorisation** | May they do this? | `require_role(...)` in `app/auth.py` |

Merging them is how systems end up with a logged-in commuter able to assign a warden.
Being logged in and being allowed are different facts.

**If asked in the viva:** "Authentication establishes identity; authorisation
establishes permission. I kept them as separate dependencies so every route declares
the role it needs at the route itself, rather than burying the check in a service
layer where you cannot see it."

---

## 2. The four actors

| Role | Who they are | What they can do |
|---|---|---|
| `commuter` | Motorists, passengers, pedestrians — anyone on the road | Report incidents, follow routes, receive warnings |
| `warden` | Field traffic warden | Receive assignments, confirm arrival and resolution |
| `officer` | MTTD control room | Triage the queue, verify incidents, assign wardens |
| `admin` | System administrator | Create privileged accounts, moderate, tune thresholds |

### Why there is no "driver" role

You asked about this specifically, and the answer is a design decision worth stating.

A driver and a passenger have **identical permissions**. Both report, both receive
warnings. Nothing in the system is permitted to one and denied to the other.

The difference between them is a *client-side mode*, not an account type. When the app
detects motion it switches the interface to read-only and offers voice input instead of
the keyboard — that is NFR-3, the rule that the system must not create the hazard it
exists to reduce.

Making "driver" a role would have implied the server knows who is currently driving. It
cannot know that, and designing as though it could would be dishonest.

**If asked:** "Driving is a state, not an identity. The same person is a driver on
Monday and a passenger on Tuesday. Permissions do not change, so the role does not
change — the client changes."

---

## 3. How logging in works, step by step

```
1. POST /auth/register  { email, password, display_name }
                                |
2.  password is hashed with bcrypt (never stored as typed)
                                |
3.  row written to users, role forced to 'commuter'
                                |
4.  a JWT is signed containing { sub: user id, role, exp }
                                |
5.  client stores the token and sends it on every later request:
        Authorization: Bearer eyJhbGci...
                                |
6.  get_current_user decodes it, checks the signature and expiry,
    then LOADS THE USER FROM THE DATABASE
                                |
7.  require_role compares that user's role against what the route demands
```

### What a JWT actually is

Three parts separated by dots: a header, some claims, and a signature.

The claims are **not encrypted** — anyone can read them. What they cannot do is change
them, because the signature is computed with a secret only the server knows. Alter one
character of the payload and the signature no longer matches.

So a token is not a secret document. It is a *tamper-evident* one.

**If asked "why not just send the user id?":** because anyone could send any user id.
The signature is what makes the claim trustworthy.

---

## 4. Six decisions worth defending

### 4.1 Self-registration cannot produce a privileged account

`RegisterRequest` has **no role field at all**. Registration hardcodes
`role=UserRole.COMMUTER`.

This matters more than a validation rule would. A check can be bypassed if someone
later forgets it; an input that does not exist cannot be supplied. There is no request
body anyone can craft that registers them as police.

Wardens, officers and admins come from exactly two places: the seed script, and an
admin calling `POST /auth/users`. Both are auditable.

*Tested by* `test_register_request_has_no_role_field`.

### 4.2 The database is consulted on every request

`get_current_user` does not trust the token's claims alone. It loads the user and
checks `is_active`.

A token is a snapshot from up to twelve hours ago. If an account is deactivated for
abuse, trusting the token would let that account keep working until the token happened
to expire. One database read per request is worth paying for that.

**If asked about the cost:** "It is one indexed primary-key lookup. The alternative is
a revocation list, which is another store to keep consistent. At this scale the read is
the simpler correct answer, and I recorded the scaling consideration rather than
pretending it does not exist."

### 4.3 Failed logins take the same time whether or not the account exists

In `login`, if no user is found the code still runs `verify_password` against a dummy
hash.

bcrypt is deliberately slow — roughly 100 ms. If we skipped it for unknown emails, a
missing account would answer in 5 ms and a real account with a wrong password in
105 ms. That difference is measurable, and it turns the login form into a tool for
discovering which email addresses are registered.

This is a **timing attack**, and equalising the work is the standard defence.

*Related:* the error message is identical in both cases — "Incorrect email or
password." Distinguishing them leaks the same fact through the response body instead.

### 4.4 Admins are not implicitly allowed everything

`require_role(UserRole.OFFICER)` denies an admin. If an admin should be able to assign
wardens, that route lists admin explicitly.

Implicit superuser access is how permission systems quietly stop meaning anything —
every awkward case gets solved by making someone an admin, and eventually admin is the
only role that matters.

*Tested by* `test_admin_is_not_implicitly_allowed_everywhere`.

### 4.5 401 and 403 mean different things

- **401 Unauthorized** — I do not know who you are. (Badly named; it means
  unauthenticated.)
- **403 Forbidden** — I know who you are, and no.

Returning 403 to an anonymous caller tells them nothing about how to proceed. Our 403
says which roles would have worked and which one you are, because by then the caller is
already identified and the information helps them rather than an attacker.

### 4.6 Uniqueness is enforced by the database, not by a prior check

Registration does not `SELECT` to see whether the email exists. It inserts and catches
the integrity error.

Two simultaneous registrations with the same address would both pass a prior `SELECT`,
and one would still fail at the insert. The check would have bought nothing except the
illusion of safety. This is a **race condition**, and the database constraint is the
only thing that actually closes it.

---

## 5. Password handling

| Concern | What we do | Why |
|---|---|---|
| Storage | bcrypt, cost factor 12 | Deliberately slow, so guessing at scale is expensive |
| Salting | Automatic, per password | Two people with the same password get different hashes, so cracking one does not crack the other |
| Length limit | Rejected above 72 bytes | bcrypt silently truncates at 72; a truncated password that still authenticates is a security bug |
| Minimum length | 8 characters | Enforced in the schema, so it fails before reaching any logic |
| Serialisation | `password_hash` appears in no response schema | There is no route by which it can leak |

**If asked "why not SHA-256?":** because SHA-256 is fast, and fast is exactly wrong for
passwords. A modern GPU computes billions of SHA-256 hashes per second. bcrypt is built
to be slow and to *stay* slow — the cost factor can be raised as hardware improves.

---

## 6. What is deliberately missing

Say these before an examiner finds them. Each is in the debt register.

| Missing | Why | Where it goes |
|---|---|---|
| Password reset flow | Needs email delivery, which needs a provider and money | Debt, scheduled |
| Phone / OTP login | The real user base has phones, not email. Needs a paid SMS gateway | Future evolution — the honest primary route for Ghana |
| Refresh tokens | Twelve-hour expiry then log in again. Simpler, and adequate at this scale | Debt, low priority |
| Rate limiting on login | Arrives with the abuse controls | Debt, scheduled |
| Token revocation list | Mitigated by the per-request `is_active` check | Acceptable |

**If asked "what would you do differently for real users?":** "Phone-number
registration with an SMS one-time code. Email is the wrong primary identifier for this
user base — I used it because an SMS gateway costs money and needs identity
verification I could not complete inside the examination window. It is the first item
in the evolution plan, not an oversight."

---

## 7. The thirty-second summary

> Four roles: commuter, warden, officer, admin. Passwords are bcrypt-hashed with a
> per-password salt. Login returns a signed JWT carrying the user id and role, valid
> twelve hours. Every protected route declares the roles it accepts, and the guard
> loads the user from the database rather than trusting the token, so a deactivated
> account loses access immediately. Self-registration can only ever produce a commuter
> — the request schema has no role field, so privilege escalation is not a check that
> could be missed, it is an input that does not exist.
