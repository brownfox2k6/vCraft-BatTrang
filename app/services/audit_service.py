"""Audit logging service for authentication and sensitive administrative events."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from app.models.audit import AuditLog
from app.repositories.audit_repository import AuditRepository


class AuditAction(StrEnum):
    """Canonical audit event action names."""

    AUTH_REGISTER = "auth.register"
    AUTH_LOGIN_SUCCESS = "auth.login_success"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_LOGOUT = "auth.logout"


class AuditLogEntry(BaseModel):
    """Serialized audit log record returned by admin inspection APIs."""

    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_email: str | None
    action: str
    target_type: str | None
    target_id: str | None
    ip_address: str | None
    user_agent: str | None
    details: dict[str, Any]
    created_at: datetime


def _default_utc_clock() -> datetime:
    return datetime.now(UTC)


def _to_entry(row: AuditLog) -> AuditLogEntry:
    return AuditLogEntry(
        id=row.id,
        actor_user_id=row.actor_user_id,
        actor_email=row.actor_email,
        action=row.action,
        target_type=row.target_type,
        target_id=row.target_id,
        ip_address=row.ip_address,
        user_agent=row.user_agent,
        details=dict(row.details) if row.details else {},
        created_at=row.created_at,
    )


class AuditService:
    """Service recording and listing security/admin audit events."""

    def __init__(
        self,
        repository: AuditRepository,
        clock: Callable[[], datetime] = _default_utc_clock,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def record(
        self,
        *,
        action: str,
        actor_user_id: uuid.UUID | None = None,
        actor_email: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict[str, Any] | None = None,
        commit: bool = False,
    ) -> AuditLogEntry:
        """Persist an audit event; set commit=True when called outside an existing transaction."""
        row = self._repository.create_log(
            action=action,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            target_type=target_type,
            target_id=target_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
            created_at=self._clock(),
        )
        if commit:
            self._repository.commit()
        return _to_entry(row)

    def list_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        action: str | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> list[AuditLogEntry]:
        """Return recent audit entries bounded to a safe page size."""
        clamped_limit = max(1, min(limit, 200))
        clamped_offset = max(0, offset)
        rows = self._repository.list_recent(
            limit=clamped_limit,
            offset=clamped_offset,
            action=action,
            actor_user_id=actor_user_id,
        )
        return [_to_entry(row) for row in rows]
