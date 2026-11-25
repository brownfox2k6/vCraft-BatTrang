"""Standardized JSON response envelope shared by all /api/* endpoints."""

from typing import Any

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    """Structured error detail included in failed API responses."""

    code: str
    message: str


class ApiResponse[T](BaseModel):
    """Uniform JSON envelope: { data, meta, error }."""

    data: T | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    error: ApiError | None = None
