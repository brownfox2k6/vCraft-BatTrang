"""Public local media serving route (/media/{relative_path:path}) with traversal guard."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.core.config import Settings
from app.routers.dependencies import get_settings

router = APIRouter(tags=["web-media"])


@router.get("/media/{relative_path:path}")
def serve_media_file(
    relative_path: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    """Serve processed WebP assets strictly from media_root with immutable cache headers."""
    if not relative_path or "\\" in relative_path or "\x00" in relative_path:
        raise HTTPException(status_code=404, detail="Media asset not found")

    media_root = Path(settings.media_root).resolve()
    try:
        target = (media_root / relative_path).resolve()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Media asset not found") from exc

    if not target.is_relative_to(media_root) or not target.is_file():
        raise HTTPException(status_code=404, detail="Media asset not found")
    if target.suffix.lower() != ".webp":
        raise HTTPException(status_code=404, detail="Media asset not found")

    return FileResponse(
        path=target,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
