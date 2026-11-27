"""Pillow-based multi-image WebP processing and local media storage service."""

import io
import os
import re
import shutil
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel

from app.core.config import Settings
from app.models.media import MediaAsset, MediaCategory
from app.repositories.media_repository import MediaRepository

MAX_IMAGE_PIXELS = 40_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class UploadedImage:
    """In-memory uploaded image payload passed from routers into MediaService."""

    filename: str | None
    content: bytes


@dataclass(frozen=True)
class _VariantSpec:
    name: str
    max_side: int
    quality: int


_VARIANT_SPECS: tuple[_VariantSpec, ...] = (
    _VariantSpec(name="thumb", max_side=400, quality=80),
    _VariantSpec(name="medium", max_side=960, quality=82),
    _VariantSpec(name="large", max_side=1600, quality=85),
)


class MediaAssetItem(BaseModel):
    """Serialized uploaded media asset returned by POST /api/media/upload."""

    id: uuid.UUID
    category: MediaCategory
    width: int
    height: int
    size_bytes: int
    thumb_url: str
    medium_url: str
    large_url: str


class MediaError(Exception):
    """Typed media validation or processing error carrying an API code and i18n key."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message_key: str,
        message_params: dict[str, object] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message_key = message_key
        self.message_params = message_params or {}


@dataclass(frozen=True)
class _ProcessedImage:
    width: int
    height: int
    variants: dict[str, bytes]


def _detect_allowed_magic(raw: bytes) -> str | None:
    if raw.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "WEBP"
    return None


def _sanitize_filename(filename: str | None) -> str:
    if not filename:
        return "upload.webp"
    base = Path(filename).name
    cleaned = _CONTROL_CHARS_RE.sub("", base).strip()
    return cleaned[:255] if cleaned else "upload.webp"


def _strip_metadata(image: Image.Image) -> Image.Image:
    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    target_mode = "RGBA" if has_alpha else "RGB"
    converted = image.convert(target_mode)
    clean = Image.new(target_mode, converted.size)
    clean.paste(converted)
    return clean


def _encode_webp_variants(raw_bytes: bytes) -> _ProcessedImage:
    if not raw_bytes or _detect_allowed_magic(raw_bytes) is None:
        raise MediaError(
            status_code=422,
            code="MEDIA_INVALID_FORMAT",
            message_key="media.errors.invalid_format",
        )

    try:
        with Image.open(io.BytesIO(raw_bytes)) as probe:
            if probe.width * probe.height > MAX_IMAGE_PIXELS:
                raise MediaError(
                    status_code=422,
                    code="MEDIA_INVALID_FORMAT",
                    message_key="media.errors.invalid_format",
                )
            probe.verify()

        with Image.open(io.BytesIO(raw_bytes)) as opened:
            if opened.width * opened.height > MAX_IMAGE_PIXELS:
                raise MediaError(
                    status_code=422,
                    code="MEDIA_INVALID_FORMAT",
                    message_key="media.errors.invalid_format",
                )
            opened.load()
            transposed = ImageOps.exif_transpose(opened)
            clean = _strip_metadata(transposed)
    except MediaError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise MediaError(
            status_code=422,
            code="MEDIA_INVALID_FORMAT",
            message_key="media.errors.invalid_format",
        ) from exc

    variants: dict[str, bytes] = {}
    large_size = clean.size

    for spec in _VARIANT_SPECS:
        resized = clean.copy()
        if max(resized.size) > spec.max_side:
            resized.thumbnail((spec.max_side, spec.max_side), Image.Resampling.LANCZOS)
        if spec.name == "large":
            large_size = resized.size
        out = io.BytesIO()
        resized.save(out, format="WEBP", quality=spec.quality, method=4)
        variants[spec.name] = out.getvalue()

    return _ProcessedImage(
        width=large_size[0],
        height=large_size[1],
        variants=variants,
    )


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    tmp_path = target.with_suffix(f"{target.suffix}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_bytes(data)
        os.replace(tmp_path, target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _to_item(asset: MediaAsset) -> MediaAssetItem:
    return MediaAssetItem(
        id=asset.id,
        category=MediaCategory(asset.category),
        width=asset.width,
        height=asset.height,
        size_bytes=asset.size_bytes,
        thumb_url=f"/media/{asset.thumb_path}",
        medium_url=f"/media/{asset.medium_path}",
        large_url=f"/media/{asset.large_path}",
    )


class MediaService:
    """Service validating, transforming to 3 WebP sizes, and persisting media assets."""

    def __init__(self, repository: MediaRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def process_and_store_images(
        self,
        files: Sequence[UploadedImage],
        *,
        category: str = MediaCategory.GENERAL.value,
        owner_user_id: uuid.UUID | None = None,
    ) -> list[MediaAssetItem]:
        """Validate and store 1..N images as 3 WebP variants, rolling back files on failure."""
        try:
            resolved_category = MediaCategory(category.strip().lower())
        except ValueError as exc:
            raise MediaError(
                status_code=422,
                code="MEDIA_INVALID_CATEGORY",
                message_key="media.errors.invalid_category",
            ) from exc

        if not files:
            raise MediaError(
                status_code=422,
                code="MEDIA_NO_FILES",
                message_key="media.errors.no_files",
            )

        max_files = self._settings.media_max_files_per_request
        if len(files) > max_files:
            raise MediaError(
                status_code=422,
                code="MEDIA_TOO_MANY_FILES",
                message_key="media.errors.too_many_files",
                message_params={"max_files": max_files},
            )

        max_bytes = self._settings.media_max_bytes
        processed_batch: list[tuple[str, _ProcessedImage]] = []
        for item in files:
            if len(item.content) > max_bytes:
                raise MediaError(
                    status_code=413,
                    code="MEDIA_TOO_LARGE",
                    message_key="media.errors.too_large",
                    message_params={"max_mb": max(1, max_bytes // (1024 * 1024))},
                )
            processed = _encode_webp_variants(item.content)
            processed_batch.append((_sanitize_filename(item.filename), processed))

        media_root = Path(self._settings.media_root).resolve()
        created_dirs: list[Path] = []
        created_assets: list[MediaAsset] = []

        try:
            for safe_name, processed in processed_batch:
                asset_id = uuid.uuid4()
                rel_dir = f"{resolved_category.value}/{asset_id}"
                asset_dir = media_root / resolved_category.value / str(asset_id)
                asset_dir.mkdir(parents=True, exist_ok=True)
                created_dirs.append(asset_dir)

                total_size = 0
                rel_paths: dict[str, str] = {}
                for spec in _VARIANT_SPECS:
                    payload = processed.variants[spec.name]
                    _atomic_write_bytes(asset_dir / f"{spec.name}.webp", payload)
                    rel_paths[spec.name] = f"{rel_dir}/{spec.name}.webp"
                    total_size += len(payload)

                asset = self._repository.create_asset(
                    asset_id=asset_id,
                    owner_user_id=owner_user_id,
                    category=resolved_category,
                    original_filename=safe_name,
                    width=processed.width,
                    height=processed.height,
                    size_bytes=total_size,
                    thumb_path=rel_paths["thumb"],
                    medium_path=rel_paths["medium"],
                    large_path=rel_paths["large"],
                )
                created_assets.append(asset)

            self._repository.commit()
        except Exception:
            self._repository.rollback()
            for created_dir in created_dirs:
                shutil.rmtree(created_dir, ignore_errors=True)
            raise

        return [_to_item(asset) for asset in created_assets]
