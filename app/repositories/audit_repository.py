"""Repository for persisting and querying security/administrative audit logs."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog


class AuditRepository:
    """Database persistence layer for audit_logs records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_log(
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
        created_at: datetime | None = None,
    ) -> AuditLog:
        """Stage a new AuditLog row in the current DB session."""
        entry = AuditLog(
            actor_user_id=actor_user_id,
            actor_email=actor_email[:255] if actor_email else None,
            action=action[:64],
            target_type=target_type[:64] if target_type else None,
            target_id=target_id[:128] if target_id else None,
            ip_address=ip_address[:45] if ip_address else None,
            user_agent=user_agent[:512] if user_agent else None,
            details=details or {},
        )
        if created_at is not None:
            entry.created_at = created_at
        self._session.add(entry)
        self._session.flush()
        return entry

    def list_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        action: str | None = None,
        actor_user_id: uuid.UUID | None = None,
    ) -> list[AuditLog]:
        """Return recent audit logs ordered newest-first with optional filters."""
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if actor_user_id is not None:
            stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
        stmt = stmt.offset(offset).limit(limit)
        return list(self._session.scalars(stmt).all())

    def commit(self) -> None:
        """Commit the current database transaction."""
        self._session.commit()
