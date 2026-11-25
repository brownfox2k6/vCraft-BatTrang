"""Health-check REST API router."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.responses import ApiError, ApiResponse
from app.repositories.health_repository import HealthRepository
from app.routers.dependencies import get_db
from app.services.health_service import DatabaseUnavailableError, HealthData, HealthService

router = APIRouter(prefix="/api", tags=["health"])


def get_health_service(db: Annotated[Session, Depends(get_db)]) -> HealthService:
    """Build HealthService bound to the request's database session."""
    return HealthService(HealthRepository(db))


@router.get(
    "/health",
    response_model=ApiResponse[HealthData],
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ApiResponse[None]}},
)
def read_health(
    service: Annotated[HealthService, Depends(get_health_service)],
) -> ApiResponse[HealthData] | JSONResponse:
    """Verify application liveness and PostgreSQL connectivity."""
    try:
        health = service.check_health()
    except DatabaseUnavailableError as exc:
        error_body = ApiResponse[None](
            error=ApiError(code="DATABASE_UNAVAILABLE", message=str(exc)),
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error_body.model_dump(),
        )
    return ApiResponse(data=health)
