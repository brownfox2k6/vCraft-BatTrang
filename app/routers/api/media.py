"""Multi-image WebP upload REST API router (/api/media/*)."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.core.config import Settings
from app.core.responses import ApiError, ApiResponse
from app.i18n.catalog import translate
from app.models.media import MediaCategory
from app.routers.dependencies import get_media_service, get_request_lang, get_settings
from app.routers.guards import require_authenticated_api
from app.services.auth_service import AuthenticatedUser
from app.services.media_service import MediaAssetItem, MediaError, MediaService, UploadedImage

router = APIRouter(prefix="/api/media", tags=["media"])


def _media_error_response(exc: MediaError, lang: str) -> JSONResponse:
    body = ApiResponse[None](
        error=ApiError(
            code=exc.code,
            message=translate(exc.message_key, lang, **exc.message_params),
        )
    )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[list[MediaAssetItem]],
)
async def upload_media_images(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(require_authenticated_api)],
    service: Annotated[MediaService, Depends(get_media_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    files: Annotated[list[UploadFile], File()],
    category: Annotated[str, Form()] = MediaCategory.GENERAL.value,
) -> ApiResponse[list[MediaAssetItem]] | JSONResponse:
    """Upload 1-10 images, optimize to 3 WebP variants, and persist MediaAsset rows."""
    lang = get_request_lang(request)
    max_files = settings.media_max_files_per_request
    max_bytes = settings.media_max_bytes
    read_limit = max_bytes + 1
    payloads: list[UploadedImage] = []

    try:
        if len(files) > max_files:
            raise MediaError(
                status_code=422,
                code="MEDIA_TOO_MANY_FILES",
                message_key="media.errors.too_many_files",
                message_params={"max_files": max_files},
            )

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
            service.process_and_store_images,
            payloads,
            category=category,
            owner_user_id=current_user.id,
        )
    except MediaError as exc:
        return _media_error_response(exc, lang)
    finally:
        for upload in files:
            await upload.close()

    return ApiResponse(data=items, meta={"count": len(items)})
