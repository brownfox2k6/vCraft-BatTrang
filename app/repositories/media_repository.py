"""Repository for persisting uploaded MediaAsset records."""

import uuid

from sqlalchemy.orm import Session

from app.models.media import MediaAsset, MediaCategory


class MediaRepository:
    """Database persistence layer for media_assets records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_asset(
        self,
        *,
        asset_id: uuid.UUID,
        owner_user_id: uuid.UUID | None,
        category: MediaCategory,
        original_filename: str,
        width: int,
        height: int,
        size_bytes: int,
        thumb_path: str,
        medium_path: str,
        large_path: str,
        mime_type: str = "image/webp",
    ) -> MediaAsset:
        """Stage a new MediaAsset row in the current DB session."""
        asset = MediaAsset(
            id=asset_id,
            owner_user_id=owner_user_id,
            category=category.value,
            original_filename=original_filename,
            mime_type=mime_type,
            width=width,
            height=height,
            size_bytes=size_bytes,
            thumb_path=thumb_path,
            medium_path=medium_path,
            large_path=large_path,
        )
        self._session.add(asset)
        self._session.flush()
        return asset

    def commit(self) -> None:
        """Commit the current database transaction."""
        self._session.commit()

    def rollback(self) -> None:
        """Rollback the current database transaction."""
        self._session.rollback()
