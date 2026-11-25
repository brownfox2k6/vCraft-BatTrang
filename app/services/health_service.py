"""Service layer orchestrating application health checks."""

from typing import Literal

from pydantic import BaseModel

from app.repositories.health_repository import HealthRepository


class DatabaseUnavailableError(RuntimeError):
    """Raised when the backing database cannot be reached."""


class HealthData(BaseModel):
    """Health check payload returned inside the standardized JSON envelope."""

    status: Literal["ok"]
    database: Literal["ok"]


class HealthService:
    """Evaluates application and database readiness."""

    def __init__(self, repository: HealthRepository) -> None:
        self._repository = repository

    def check_health(self) -> HealthData:
        """Return health status after verifying database connectivity."""
        if not self._repository.ping():
            raise DatabaseUnavailableError("Database connection failed.")
        return HealthData(status="ok", database="ok")
