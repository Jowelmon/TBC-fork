"""Session identity: a signed cookie, not a spoofable ``?user=`` parameter.

``POST /login`` checks the user's PIN and sets an HMAC-signed cookie naming one of the fixed demo
users (``rbac.DEMO_USERS``). Every endpoint resolves its caller through
``resolve_user``, a FastAPI dependency: the cookie always wins when present
and valid. ``?user=`` only works as a fallback when ``TBC_DEMO_INSECURE=1``
is set (local demo/test convenience) and there is no valid session cookie —
the frontend shows a persistent banner whenever that flag is in effect, so
it is never a silent downgrade.

``TBC_SECRET`` should be set outside a demo: with no value configured, a
random secret is generated once per process, which is fine for a single
long-running demo server but means existing sessions are invalidated on
every restart.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from fastapi import HTTPException, Request, Response

from .rbac import DEMO_USERS

SESSION_COOKIE = "tbc_session"
_SECRET = os.environ.get("TBC_SECRET") or secrets.token_hex(32)


def _sign(user_id: str) -> str:
    mac = hmac.new(_SECRET.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    return f"{user_id}.{mac}"


def _verify(token: str | None) -> str | None:
    """Return the user id iff the cookie's signature is valid and the user
    still exists. Any tampering, truncation, or unknown user id -> None."""
    if not token or "." not in token:
        return None
    user_id, _, mac = token.rpartition(".")
    expected = hmac.new(_SECRET.encode(), user_id.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        return None
    return user_id if user_id in DEMO_USERS else None


# Per-user login PINs. Demo defaults are published in DEMO.md so judges can
# switch roles; set TBC_LOGIN_PINS="tech1:1234,mgr1:5678,..." to replace them.
# A real deployment would put SSO here instead.
_DEFAULT_PINS = {
    "tech1": "1111", "mgr1": "2222", "steward1": "3333",
    "steward2": "4444", "auditor1": "5555", "admin1": "9999",
}


def _pins() -> dict[str, str]:
    raw = os.environ.get("TBC_LOGIN_PINS", "").strip()
    if not raw:
        return _DEFAULT_PINS
    pairs = (item.split(":", 1) for item in raw.split(",") if ":" in item)
    return {u.strip(): p.strip() for u, p in pairs}


def check_pin(user_id: str, pin: str | None) -> bool:
    expected = _pins().get(user_id)
    return bool(expected and pin) and hmac.compare_digest(expected, pin)


def demo_insecure() -> bool:
    """Whether ``?user=`` is honoured as a fallback. Off by default."""
    return os.environ.get("TBC_DEMO_INSECURE", "0").strip() == "1"


def issue_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, _sign(user_id),
        httponly=True, samesite="lax", max_age=60 * 60 * 12,
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)


def resolve_user(request: Request, user: str | None = None) -> str:
    """FastAPI dependency: the authenticated caller for this request.

    The signed session cookie always takes priority over ``?user=``, so a
    valid technician session cannot be escalated by appending ``?user=
    admin1`` to the URL. ``?user=`` is honoured on its own only when
    ``TBC_DEMO_INSECURE=1``.
    """
    verified = _verify(request.cookies.get(SESSION_COOKIE))
    if verified:
        return verified
    if user and demo_insecure():
        return user
    raise HTTPException(
        status_code=401,
        detail=(
            "no session: POST /login first"
            if not user
            else "no session cookie, and ?user= is disabled "
                 "(set TBC_DEMO_INSECURE=1 to allow it for local demos/tests)"
        ),
    )


__all__ = [
    "SESSION_COOKIE",
    "check_pin",
    "demo_insecure",
    "issue_cookie",
    "clear_cookie",
    "resolve_user",
]
