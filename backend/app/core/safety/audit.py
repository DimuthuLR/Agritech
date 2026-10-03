"""
Audit log writer — hash-chained, append-only.

Every gate decision (pass or fail) writes one row. Each row's hash
depends on the previous row's hash, forming a chain. Tampering with any
row invalidates all subsequent hashes — detectable at read time.
"""
import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog


def _canonical_json(payload: dict) -> str:
    """Deterministic JSON: sorted keys, no whitespace, UUIDs as strings."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _compute_hash(prev_hash: str | None, payload_json: str) -> str:
    """sha256(prev_hash || ':' || payload_json)"""
    chain_input = f"{prev_hash or ''}:{payload_json}".encode("utf-8")
    return hashlib.sha256(chain_input).hexdigest()


def write_audit(
    db: Session,
    *,
    kind: str,
    payload: dict[str, Any],
    actor: str | None = None,
    tenant_id: UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """
    Write an audit entry. Caller is responsible for db.commit().
    Returns the inserted (uncommitted) AuditLog object.
    """
    prev = (
        db.query(AuditLog)
        .order_by(AuditLog.id.desc())
        .limit(1)
        .first()
    )
    prev_hash = prev.hash if prev else None

    payload_json = _canonical_json(payload)
    our_hash = _compute_hash(prev_hash, payload_json)

    entry = AuditLog(
        kind=kind,
        actor=actor,
        tenant_id=tenant_id,
        target_type=target_type,
        target_id=target_id,
        model=model,
        prompt_version=prompt_version,
        ip_address=ip_address,
        payload=payload,
        prev_hash=prev_hash,
        hash=our_hash,
    )
    db.add(entry)
    return entry


def verify_chain(db: Session, limit: int | None = None) -> tuple[bool, int | None]:
    """
    Walk the audit chain and verify integrity.
    Returns (is_valid, first_bad_id).
    """
    query = db.query(AuditLog).order_by(AuditLog.id.asc())
    if limit:
        query = query.limit(limit)

    prev_hash: str | None = None
    for row in query:
        payload_json = _canonical_json(row.payload)
        expected = _compute_hash(prev_hash, payload_json)

        if row.prev_hash != prev_hash or row.hash != expected:
            return False, row.id

        prev_hash = row.hash

    return True, None