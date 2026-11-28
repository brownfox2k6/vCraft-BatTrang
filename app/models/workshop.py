"""ORM model for public artisan household workshop registration applications."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.auth import User


class WorkshopApplicationStatus(StrEnum):
    """Lifecycle states for a household workshop verification application."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class WorkshopApplication(Base):
    """Pending/reviewed artisan workshop registration linked to an inactive Artisan user."""

    __tablename__ = "workshop_applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_workshop_applications_status",
        ),
        CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_workshop_applications_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_workshop_applications_longitude",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_code: Mapped[str] = mapped_column(
        String(24), unique=True, index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    proposed_slug: Mapped[str] = mapped_column(String(140), index=True, nullable=False)
    name_vi: Mapped[str] = mapped_column(String(160), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(160), nullable=True)
    tagline_vi: Mapped[str | None] = mapped_column(String(240), nullable=True)
    tagline_en: Mapped[str | None] = mapped_column(String(240), nullable=True)
    artisan_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    address_vi: Mapped[str] = mapped_column(String(255), nullable=False)
    address_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    history_vi: Mapped[str] = mapped_column(Text, nullable=False)
    history_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    opening_hours: Mapped[str] = mapped_column(String(80), nullable=False)
    is_open_now: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    has_experience: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    experience_desc_vi: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_desc_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    workshop_media_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    certificate_media_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(24),
        index=True,
        nullable=False,
        default=WorkshopApplicationStatus.PENDING.value,
        server_default=WorkshopApplicationStatus.PENDING.value,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship("User", foreign_keys=[user_id], lazy="joined")
