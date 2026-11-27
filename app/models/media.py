"""ORM model for uploaded and Pillow-processed WebP media assets."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MediaCategory(StrEnum):
    """Allowed semantic categories for uploaded media assets."""

    WORKSHOP = "workshop"
    CERTIFICATE = "certificate"
    PRODUCT = "product"
    MILESTONE = "milestone"
    NEWS = "news"
    GENERAL = "general"


class MediaAsset(Base):
    """Persisted metadata and relative WebP paths for an uploaded image asset."""

    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(
            "category IN ('workshop', 'certificate', 'product', 'milestone', 'news', 'general')",
            name="ck_media_assets_category",
        ),
        CheckConstraint("width > 0", name="ck_media_assets_width_positive"),
        CheckConstraint("height > 0", name="ck_media_assets_height_positive"),
        CheckConstraint("size_bytes > 0", name="ck_media_assets_size_bytes_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    category: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=MediaCategory.GENERAL.value,
        server_default=MediaCategory.GENERAL.value,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="image/webp",
        server_default="image/webp",
    )
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    thumb_path: Mapped[str] = mapped_column(String(512), nullable=False)
    medium_path: Mapped[str] = mapped_column(String(512), nullable=False)
    large_path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
        server_default=func.now(),
    )
