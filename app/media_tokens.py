"""Short-lived tokens that make a private attachment loadable by an image or audio tag.

THE PROBLEM
-----------
Attachment bytes are guarded by `may_play`, which needs to know who is asking. Every
other request in this system answers that with an `Authorization: Bearer …` header,
added by `fetch`.

`<img src>` and `<audio src>` cannot do that. The browser issues those requests itself,
and there is no way to attach a header to one. So a private attachment was, in practice,
unviewable by anybody at all — including the person who uploaded it, who could see it
listed and could not open it. Pasting the URL into the address bar failed for the same
reason, which is what it looks like from the outside: a blank image and a bare
`{"detail":"No such attachment."}`.

THE FIX
-------
When the API returns an attachment to somebody `may_play` has already cleared, it
appends a signed token to the URL. The token says one thing — *this attachment may be
served for the next ten minutes* — and it is signed with the same secret as the login
token, so it cannot be forged or edited.

This is the mechanism behind an S3 presigned URL, for the same reason: the entitlement
is checked once, where the caller is known, and then carried in the URL to a place where
they are not.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not name the viewer, so a token cannot be traced back to who requested it. That
also means a token that leaks works for anyone holding it — which is why it expires in
ten minutes and covers exactly one attachment. It is a capability, not an identity: it
grants sight of one file for a short while and nothing else. Anyone who can read the URL
could equally have been handed the file itself.

The header route still works and is still checked first. The token is an addition for
the two elements that cannot use a header, not a replacement for authentication.
"""

from __future__ import annotations

import datetime as dt
import uuid

import jwt

_ALGORITHM = "HS256"

# Long enough to open a popup, look at a photograph and play a recording. Short enough
# that a URL copied out of a page is worthless by the time anybody reads it.
TTL_SECONDS = 600

# An audience claim, so a login token can never be used as a media token and a media
# token can never be used to call the API. Both are signed with the same secret; without
# this they would be interchangeable, and a leaked media URL would become a session.
_AUDIENCE = "nkwanta:media"


def mint(attachment_id: uuid.UUID, secret: str, ttl_seconds: int = TTL_SECONDS) -> str:
    """A token permitting this one attachment to be served for a short while."""
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode(
        {
            "sub": str(attachment_id),
            "aud": _AUDIENCE,
            "iat": now,
            "exp": now + dt.timedelta(seconds=ttl_seconds),
        },
        secret,
        algorithm=_ALGORITHM,
    )


def permits(token: str | None, attachment_id: uuid.UUID, secret: str) -> bool:
    """Does this token permit this exact attachment, right now?

    Every failure is the same answer — no. A caller learns nothing about *why*, because
    "expired" and "forged" and "for a different file" are three different pieces of
    information and none of them are owed to somebody holding a token that does not work.
    """
    if not token:
        return False
    try:
        claims = jwt.decode(token, secret, algorithms=[_ALGORITHM], audience=_AUDIENCE)
    except jwt.InvalidTokenError:
        return False
    return claims.get("sub") == str(attachment_id)
