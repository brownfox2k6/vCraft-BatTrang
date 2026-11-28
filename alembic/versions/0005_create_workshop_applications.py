"""Create workshop_applications table for public artisan household registration.

Revision ID: 0005_workshop_applications
Revises: 0004_create_media_assets
Create Date: 2026-11-28 17:52:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_workshop_applications"
down_revision: str | Sequence[str] | None = "0004_create_media_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create workshop_applications table with status/coordinate constraints and indexes."""
    op.create_table(
        "workshop_applications",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("application_code", sa.String(length=24), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("proposed_slug", sa.String(length=140), nullable=False),
        sa.Column("name_vi", sa.String(length=160), nullable=False),
        sa.Column("name_en", sa.String(length=160), nullable=True),
        sa.Column("tagline_vi", sa.String(length=240), nullable=True),
        sa.Column("tagline_en", sa.String(length=240), nullable=True),
        sa.Column("artisan_name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("address_vi", sa.String(length=255), nullable=False),
        sa.Column("address_en", sa.String(length=255), nullable=True),
        sa.Column("history_vi", sa.Text(), nullable=False),
        sa.Column("history_en", sa.Text(), nullable=True),
        sa.Column("opening_hours", sa.String(length=80), nullable=False),
        sa.Column("is_open_now", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("has_experience", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("experience_desc_vi", sa.Text(), nullable=True),
        sa.Column("experience_desc_en", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("workshop_media_ids", sa.JSON(), nullable=False),
        sa.Column("certificate_media_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_workshop_applications_status",
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR (latitude >= -90 AND latitude <= 90)",
            name="ck_workshop_applications_latitude",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR (longitude >= -180 AND longitude <= 180)",
            name="ck_workshop_applications_longitude",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_workshop_applications_user_id"),
    )
    op.create_index(
        "ix_workshop_applications_application_code",
        "workshop_applications",
        ["application_code"],
        unique=True,
    )
    op.create_index(
        "ix_workshop_applications_proposed_slug",
        "workshop_applications",
        ["proposed_slug"],
        unique=False,
    )
    op.create_index(
        "ix_workshop_applications_status",
        "workshop_applications",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Drop workshop_applications table and its indexes."""
    op.drop_index("ix_workshop_applications_status", table_name="workshop_applications")
    op.drop_index("ix_workshop_applications_proposed_slug", table_name="workshop_applications")
    op.drop_index("ix_workshop_applications_application_code", table_name="workshop_applications")
    op.drop_table("workshop_applications")
