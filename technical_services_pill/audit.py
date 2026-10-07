"""Tamper-evident, keyed hash-chaining for case history and the KB ledger.

For entry ``i``::

    prev_hash_i = entry[i-1].hash        # GENESIS_HASH for the first entry
    hash_i      = HMAC-SHA256(key, canonical_json({"prev_hash": prev_hash_i, **fields}))

The chain is keyed: editing an entry and recomputing every hash only passes
verification for someone who also holds the audit key. Anyone with the
database but not the key cannot forge a valid chain.

The key comes from ``TBC_AUDIT_KEY``. Without it, a random key is generated
once and kept in ``TBC_AUDIT_KEY_FILE`` (default ``data/audit.key``, mode
0600) so chains survive a restart. That default is for local demos only: in
production the key must live outside the database host (e.g. a secrets
manager), otherwise filesystem access to both lets someone re-sign the chain.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any

#: Anchor hash for the first entry in a chain (no predecessor).
GENESIS_HASH = "0" * 64

_KEY: bytes | None = None


def _load_key() -> bytes:
    env = os.environ.get("TBC_AUDIT_KEY", "").strip()
    if env:
        return env.encode()
    path = Path(os.environ.get("TBC_AUDIT_KEY_FILE", str(Path("data") / "audit.key")))
    if path.exists():
        return path.read_text().strip().encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(key)
    return key.encode()


def audit_key() -> bytes:
    global _KEY
    if _KEY is None:
        _KEY = _load_key()
    return _KEY


def canonical_json(obj: Any) -> str:
    """Deterministic JSON encoding (sorted keys, no whitespace)."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def compute_hash(prev_hash: str, fields: dict[str, Any]) -> str:
    """Keyed hash of ``fields`` chained to ``prev_hash``."""
    body = canonical_json({"prev_hash": prev_hash, **fields})
    return hmac.new(audit_key(), body.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_chain(entries: list[dict[str, Any]], fields: tuple[str, ...]) -> bool:
    """Recompute a chain of dict entries; True iff every link and hash holds."""
    prev = GENESIS_HASH
    for e in entries:
        if e.get("prev_hash") != prev:
            return False
        if e.get("hash") != compute_hash(prev, {f: e.get(f) for f in fields}):
            return False
        prev = e["hash"]
    return True
