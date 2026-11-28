"""Repository for persisting and querying uploaded MediaAsset records."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select, update
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

    def get_assets_by_ids(self, asset_ids: Sequence[uuid.UUID]) -> list[MediaAsset]:
        """Fetch all MediaAsset rows matching the supplied UUIDs."""
        if not asset_ids:
            return []
        stmt = select(MediaAsset).where(MediaAsset.id.in_(asset_ids))
        return list(self._session.scalars(stmt).all())

    def assign_owner(self, asset_ids: Sequence[uuid.UUID], owner_user_id: uuid.UUID) -> int:
        """Attach an owner_user_id to unowned MediaAsset rows and return updated row count."""
        if not asset_ids:
            return 0
        updated_ids = list(
            self._session.scalars(
                update(MediaAsset)
                .where(MediaAsset.id.in_(asset_ids), MediaAsset.owner_user_id.is_(None))
                .values(owner_user_id=owner_user_id)
                .returning(MediaAsset.id)
            ).all()
        )
        self._session.flush()
        return len(updated_ids)

    def commit(self) -> None:
        """Commit the current database transaction."""
        self._session.commit()

    def rollback(self) -> None:
        """Rollback the current database transaction."""
        self._session.rollback()
