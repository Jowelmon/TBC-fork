"""RBAC capability-registry invariant test (review finding R12).

Static scans app.py for every capability string passed to ``_need(user, "X")``
and asserts each is a declared member of the RBAC capability universe
(``rbac.PERMISSIONS`` values union + admin ``_ALL_CAPABILITIES``). This catches
typos / phantom capabilities at the API layer and turns "capability names need
verification" into a guarded invariant.

Also reports declared capabilities with NO enforcing endpoint
(``approve_knowledge_version`` / ``rollback_knowledge_version``) as a known
demo-scope gap (asserted-but-not-failed), surfaced in CI output.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Allow running without pytest (spec §8 runnable two ways).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from technical_services_pill.rbac import PERMISSIONS, _ALL_CAPABILITIES  # noqa: E402

# Matches _need(user, "capability_id") in app.py.
_NEED_RE = re.compile(r'_need\(\s*\w+\s*,\s*"([a-z_]+)"\s*\)')


def _declared_capabilities() -> set[str]:
    """Union of every capability granted to any role + the admin superset."""
    caps: set[str] = set(_ALL_CAPABILITIES)
    for granted in PERMISSIONS.values():
        caps |= set(granted)
    return caps


def _enforced_capabilities() -> set[str]:
    """Capabilities actually required by some app.py endpoint via _need()."""
    app_src = (ROOT / "technical_services_pill" / "app.py").read_text()
    return set(_NEED_RE.findall(app_src))


def test_enforced_capabilities_are_declared():
    """Every _need(user, 'X') capability must exist in the RBAC universe."""
    enforced = _enforced_capabilities()
    declared = _declared_capabilities()
    unknown = enforced - declared
    assert not unknown, (
        f"app.py enforces capabilities not declared in rbac.PERMISSIONS: "
        f"{sorted(unknown)}"
    )


def test_core_capabilities_enforced():
    """Core capabilities are exercised by at least one endpoint."""
    enforced = _enforced_capabilities()
    assert "view_case" in enforced, "no endpoint requires view_case"
    assert "read_audit_trail" in enforced, "no endpoint requires read_audit_trail"
    assert "approve_reject_modify" in enforced
    assert "record_outcome" in enforced
    assert "submit_feedback" in enforced


def test_phantom_capabilities_are_known_demo_scope():
    """Declared-but-unenforced capabilities must be the known demo set.

    ``approve_knowledge_version`` / ``rollback_knowledge_version`` are part of
    the §6 governance flow not yet wired to endpoints (KB versioning is
    store-internal in the hackathon build). This test fails if a NEW phantom
    appears so the gap is never silently widened.
    """
    phantom = _declared_capabilities() - _enforced_capabilities()
    known = {"approve_knowledge_version", "rollback_knowledge_version"}
    unexpected = phantom - known
    assert not unexpected, (
        f"unexpected declared-but-unenforced capabilities: {sorted(unexpected)}"
    )


if __name__ == "__main__":
    declared_count = len(_declared_capabilities())
    enforced = _enforced_capabilities()
    print(f"declared capabilities: {declared_count}")
    print(f"enforced by endpoints: {len(enforced)}")
    phantom = _declared_capabilities() - enforced
    print(f"phantom (declared, no endpoint): {sorted(phantom)}")
    sys.exit(0)