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
import time

from fastapi import HTTPException, Request, Response

from .rbac import DEMO_USERS

SESSION_COOKIE = "tbc_session"
# Users this browser has proven the PIN for, so switching back to them does
# not need the PIN again and the browser never has to store PINs itself.
UNLOCK_COOKIE = "tbc_unlocked"
MAX_FAILURES = 5
LOCKOUT_SECONDS = 300
_failures: dict[str, list[float]] = {}  # "user@client" -> [count, locked_until]
_SECRET = os.environ.get("TBC_SECRET") or secrets.token_hex(32)


SESSION_SECONDS = 60 * 60 * 8
_revoked_nonces: set[str] = set()


def _mac(body: str) -> str:
    return hmac.new(_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()


def _sign(user_id: str) -> str:
    """``user.issued_at.nonce.mac``: sessions expire, and logging out revokes
    that exact session, so a copied cookie stops working."""
    body = f"{user_id}.{int(time.time())}.{secrets.token_hex(8)}"
    return f"{body}.{_mac(body)}"


def _verify(token: str | None) -> str | None:
    """Return the user id iff the cookie is genuine, unexpired, not logged
    out, and names a known user. Anything else -> None."""
    if not token or token.count(".") != 3:
        return None
    body, _, mac = token.rpartition(".")
    if not hmac.compare_digest(mac, _mac(body)):
        return None
    user_id, issued, nonce = body.split(".")
    if not issued.isdigit() or time.time() - int(issued) > SESSION_SECONDS or nonce in _revoked_nonces:
        return None
    return user_id if user_id in DEMO_USERS else None


def revoke(token: str | None) -> None:
    if token and token.count(".") == 3:
        _revoked_nonces.add(token.split(".")[2])


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


def locked_for(key: str) -> int:
    """Seconds left on a lockout after too many wrong PINs, or 0. ``key`` is
    user plus client address, so one client guessing cannot lock the real
    user out everywhere else."""
    _, until = _failures.get(key, [0, 0.0])
    return max(0, int(until - time.time()))


def record_pin_result(key: str, ok: bool) -> None:
    if ok:
        _failures.pop(key, None)
        return
    count, _ = _failures.get(key, [0, 0.0])
    count += 1
    until = time.time() + LOCKOUT_SECONDS if count >= MAX_FAILURES else 0.0
    _failures[key] = [0 if until else count, until]


def unlocked_users(request: Request) -> set[str]:
    token = request.cookies.get(UNLOCK_COOKIE)
    if not token or "." not in token:
        return set()
    body, _, mac = token.rpartition(".")
    expected = hmac.new(_SECRET.encode(), f"unlock:{body}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        return set()
    return {u for u in body.split(",") if u in DEMO_USERS}


def issue_unlock(response: Response, users: set[str]) -> None:
    body = ",".join(sorted(users))
    mac = hmac.new(_SECRET.encode(), f"unlock:{body}".encode(), hashlib.sha256).hexdigest()
    response.set_cookie(UNLOCK_COOKIE, f"{body}.{mac}", httponly=True, samesite="lax",
                        max_age=SESSION_SECONDS)


def demo_insecure() -> bool:
    """Whether ``?user=`` is honoured as a fallback. Off by default."""
    return os.environ.get("TBC_DEMO_INSECURE", "0").strip() == "1"


def issue_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, _sign(user_id),
        httponly=True, samesite="lax", max_age=SESSION_SECONDS,
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(UNLOCK_COOKIE)


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
    "issue_unlock",
    "revoke",
    "locked_for",
    "record_pin_result",
    "unlocked_users",
    "demo_insecure",
    "issue_cookie",
    "clear_cookie",
    "resolve_user",
]
