"""Tamper-evident hash-chaining helpers for agent-state history.

Mirrors spec §6 ``AuditLog`` (hash-chained) and the brief's "Transparent" /
"Accountable" adjectives. The full Layer-8 AuditLog service is out of scope
here; this module provides the in-state chain that travels with the
``AgentState`` so every transition is independently verifiable.

Chain rule
----------
For history entry ``i``::

    prev_hash_i = history[i-1].hash        # GENESIS_HASH for the first entry
    hash_i      = sha256( canonical_json({
                      "prev_hash": prev_hash_i,
                      "from_state": ...,
                      "to_state": ...,
                      "at": ...,
                      "actor": ...,
                      "reason": ...,
                  }) )

Tampering with any field (or reordering) breaks the chain from that point on.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

#: Anchor hash for the first entry in the chain (no predecessor).
GENESIS_HASH = "0" * 64


def canonical_json(obj: Any) -> str:
    """Deterministic JSON encoding (sorted keys, no whitespace)."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def compute_hash(prev_hash: str, fields: dict[str, Any]) -> str:
    """Compute ``sha256(prev_hash || canonical_json(fields))``.

    ``fields`` carries the entry's semantic content (from_state, to_state, at,
    actor, reason) WITHOUT the ``hash`` field itself, and WITH ``prev_hash``
    folded in so the chain is order-dependent.
    """
    body = canonical_json({"prev_hash": prev_hash, **fields})
    return hashlib.sha256(body.encode("utf-8")).hexdigest()