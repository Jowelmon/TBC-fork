"""Role-based access control for the Technical Services Fault Diagnosis pill.

Implements the RBAC matrix from spec §6. Roles and capabilities are string
keys so they cross over cleanly to FastAPI dependency injection and JWT
claims. This module is self-contained: it depends only on the standard library
(and reuses no domain models) so it can be imported by the API layer without
pulling in the agent state machine.

Capabilities (string keys):
    view_case                 — view case state + trace
    approve_reject_modify     — HITL approve / reject / modify verdict
    record_outcome            — record/verify maintenance outcome
    submit_feedback           — submit expert corrections to governance
    approve_knowledge_version — approve a new KnowledgeVersion
    rollback_knowledge_version — roll back to a prior KnowledgeVersion
    read_audit_trail          — read the tamper-evident audit trail
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    """RBAC roles from spec §5/§6."""

    TECHNICIAN = "technician"
    ASSET_OPS_MANAGER = "asset_ops_manager"
    KNOWLEDGE_STEWARD = "knowledge_steward"
    AUDITOR = "auditor"
    ADMIN = "admin"


# Full capability universe — admin gets all of these.
_ALL_CAPABILITIES: frozenset[str] = frozenset(
    {
        "view_case",
        "approve_reject_modify",
        "record_outcome",
        "submit_feedback",
        "approve_knowledge_version",
        "rollback_knowledge_version",
        "read_audit_trail",
        "capture_expert_knowledge",
    }
)

# Spec §6 RBAC matrix.
PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.TECHNICIAN: frozenset({"view_case", "record_outcome"}),
    Role.ASSET_OPS_MANAGER: frozenset(
        {
            "view_case",
            "approve_reject_modify",
            "record_outcome",
            "submit_feedback",
            "capture_expert_knowledge",
        }
    ),
    Role.KNOWLEDGE_STEWARD: frozenset(
        {
            "view_case",
            "submit_feedback",
            "approve_knowledge_version",
            "read_audit_trail",
            "capture_expert_knowledge",
        }
    ),
    Role.AUDITOR: frozenset({"view_case", "read_audit_trail"}),
    Role.ADMIN: _ALL_CAPABILITIES,
}


def _coerce_role(role: Role | str) -> Role:
    """Accept a Role or its string value (case-sensitive per the enum)."""
    if isinstance(role, Role):
        return role
    try:
        return Role(role)
    except ValueError as exc:
        raise PermissionError(f"unknown role: {role!r}") from exc


def can(role: Role | str, capability: str) -> bool:
    """True iff ``role`` holds ``capability`` per spec §6."""
    return capability in PERMISSIONS[_coerce_role(role)]


def require(role: Role | str, capability: str) -> None:
    """Raise ``PermissionError`` if ``role`` lacks ``capability``.

    Mirrors spec TC9 (technician attempts POST /approval -> 403).
    """
    if not can(role, capability):
        r = _coerce_role(role)
        raise PermissionError(
            f"role {r.value!r} lacks capability {capability!r}"
        )


@dataclass(frozen=True)
class User:
    """A principal: an authenticated user id plus their role."""

    user_id: str
    role: Role


def user(user_id: str, role: Role | str) -> User:
    """Construct a ``User`` from a role value or Role member."""
    return User(user_id=user_id, role=_coerce_role(role))


# Demo principals for the hackathon — one per role (spec §5).
DEMO_USERS: dict[str, User] = {
    "tech1": User("tech1", Role.TECHNICIAN),
    "mgr1": User("mgr1", Role.ASSET_OPS_MANAGER),
    "steward1": User("steward1", Role.KNOWLEDGE_STEWARD),
    "steward2": User("steward2", Role.KNOWLEDGE_STEWARD),
    "auditor1": User("auditor1", Role.AUDITOR),
    "admin1": User("admin1", Role.ADMIN),
}