"""ORM domain models registry imported by Alembic for metadata discovery."""

from app.core.database import Base
from app.models.audit import AuditLog
from app.models.auth import LoginAttempt, User, UserRole, UserSession
from app.models.media import MediaAsset, MediaCategory
from app.models.workshop import WorkshopApplication, WorkshopApplicationStatus

__all__ = [
    "AuditLog",
    "Base",
    "LoginAttempt",
    "MediaAsset",
    "MediaCategory",
    "User",
    "UserRole",
    "UserSession",
    "WorkshopApplication",
    "WorkshopApplicationStatus",
]
