"""Public workshop application API endpoints (/api/workshop-applications/*)."""

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.responses import ApiError, ApiResponse
from app.i18n.catalog import translate
from app.models.media import MediaCategory
from app.repositories.auth_repository import AuthRepository
from app.routers.auth_cookies import get_client_ip
from app.routers.dependencies import (
    get_db,
    get_media_service,
    get_request_lang,
    get_settings,
    get_workshop_application_service,
)
from app.services.media_service import MediaAssetItem, MediaError, MediaService, UploadedImage
from app.services.workshop_application_service import (
    WorkshopApplicationError,
    WorkshopApplicationInput,
    WorkshopApplicationResult,
    WorkshopApplicationService,
)

router = APIRouter(prefix="/api/workshop-applications", tags=["workshop-applications"])

_PUBLIC_MEDIA_CATEGORIES: frozenset[str] = frozenset(
    {MediaCategory.WORKSHOP.value, MediaCategory.CERTIFICATE.value}
)


def _error_json(
    *,
    status_code: int,
    code: str,
    message: str,
    meta: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ApiResponse[None](
        meta=meta or {},
        error=ApiError(code=code, message=message),
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers=headers,
    )


@router.post(
    "/media",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[list[MediaAssetItem]],
)
async def upload_public_application_media(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    media_service: Annotated[MediaService, Depends(get_media_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    files: Annotated[list[UploadFile], File()],
    category: Annotated[str, Form()] = MediaCategory.WORKSHOP.value,
) -> ApiResponse[list[MediaAssetItem]] | JSONResponse:
    """Upload workshop/certificate images for public applicants with per-IP rate limiting."""
    lang = get_request_lang(request)
    normalized_category = category.strip().lower()
    max_files = settings.media_max_files_per_request
    max_bytes = settings.media_max_bytes
    read_limit = max_bytes + 1

    try:
        if normalized_category not in _PUBLIC_MEDIA_CATEGORIES:
            raise MediaError(
                status_code=422,
                code="MEDIA_INVALID_CATEGORY",
                message_key="media.errors.invalid_category",
            )

        if len(files) > max_files:
            raise MediaError(
                status_code=422,
                code="MEDIA_TOO_MANY_FILES",
                message_key="media.errors.too_many_files",
                message_params={"max_files": max_files},
            )

        # Sliding-window IP rate limit using login_attempts table with dedicated scope prefix
        clock: Callable[[], datetime] = request.app.state.clock
        now = clock()
        window_seconds = settings.public_media_rate_limit_window_seconds
        window_start = now - timedelta(seconds=window_seconds)
        scope_key = f"public_media|{get_client_ip(request)}"[:320]
        rate_repo = AuthRepository(db)
        rate_repo.prune_stale_attempts(window_start)
        recent = rate_repo.count_recent_attempts(scope_key, window_start)
        if recent >= settings.public_media_rate_limit_max_uploads:
            oldest = rate_repo.get_oldest_attempt_in_window(scope_key, window_start)
            retry_after = window_seconds
            if oldest is not None:
                if oldest.tzinfo is None:
                    oldest = oldest.replace(tzinfo=UTC)
                remaining = math.ceil(
                    (oldest + timedelta(seconds=window_seconds) - now).total_seconds()
                )
                retry_after = max(1, remaining)
            rate_repo.commit()
            minutes = max(1, math.ceil(retry_after / 60))
            return _error_json(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code="RATE_LIMIT_EXCEEDED",
                message=translate(
                    "workshop_apply.errors.media_rate_limited", lang, minutes=minutes
                ),
                headers={"Retry-After": str(retry_after)},
            )

        # Record attempt before file processing so malformed/oversized spam still counts
        rate_repo.record_failed_attempt(scope_key, now)
        rate_repo.commit()

        payloads: list[UploadedImage] = []
        for upload in files:
            raw = await upload.read(read_limit)
            if len(raw) > max_bytes:
                raise MediaError(
                    status_code=413,
                    code="MEDIA_TOO_LARGE",
                    message_key="media.errors.too_large",
                    message_params={"max_mb": max(1, max_bytes // (1024 * 1024))},
                )
            payloads.append(UploadedImage(filename=upload.filename, content=raw))

        items = await run_in_threadpool(
            media_service.process_and_store_images,
            payloads,
            category=normalized_category,
            owner_user_id=None,
        )
    except MediaError as exc:
        return _error_json(
            status_code=exc.status_code,
            code=exc.code,
            message=translate(exc.message_key, lang, **exc.message_params),
        )
    finally:
        for upload in files:
            await upload.close()

    return ApiResponse(data=items, meta={"count": len(items)})


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[WorkshopApplicationResult],
)
def submit_workshop_application(
    payload: WorkshopApplicationInput,
    request: Request,
    service: Annotated[WorkshopApplicationService, Depends(get_workshop_application_service)],
) -> ApiResponse[WorkshopApplicationResult] | JSONResponse:
    """Create an inactive Artisan account + Pending WorkshopApplication in one transaction."""
    lang = get_request_lang(request)
    try:
        result = service.submit_application(
            payload,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            success_message=translate("workshop_apply.success.message", lang),
        )
    except WorkshopApplicationError as exc:
        field_errors = {field: translate(key, lang) for field, key in exc.field_errors.items()}
        meta: dict[str, object] = {"field_errors": field_errors} if field_errors else {}
        return _error_json(
            status_code=exc.status_code,
            code=exc.code,
            message=translate(exc.message_key, lang),
            meta=meta,
        )
    return ApiResponse(data=result)
