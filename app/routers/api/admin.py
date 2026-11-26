"""Management Board (Admin) REST API endpoints (/api/admin/*)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.responses import ApiResponse
from app.models.auth import UserRole
from app.routers.dependencies import get_audit_service
from app.routers.guards import require_roles_api
from app.services.audit_service import AuditLogEntry, AuditService
from app.services.auth_service import AuthenticatedUser

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/audit-logs", response_model=ApiResponse[list[AuditLogEntry]])
def list_audit_logs(
    _admin: Annotated[AuthenticatedUser, Depends(require_roles_api(UserRole.ADMIN))],
    audit_service: Annotated[AuditService, Depends(get_audit_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    action: Annotated[str | None, Query()] = None,
) -> ApiResponse[list[AuditLogEntry]]:
    """Return recent security and administrative audit log entries for Admin inspection."""
    entries = audit_service.list_recent(limit=limit, offset=offset, action=action)
    return ApiResponse(
        data=entries,
        meta={"limit": limit, "offset": offset, "count": len(entries)},
    )
