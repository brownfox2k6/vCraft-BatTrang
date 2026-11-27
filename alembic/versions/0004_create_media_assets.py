"""Create media_assets table for WebP image upload pipeline.

Revision ID: 0004_create_media_assets
Revises: 0003_add_csrf_and_audit_logs
Create Date: 2026-11-27 21:18:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_create_media_assets"
down_revision: str | Sequence[str] | None = "0003_add_csrf_and_audit_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create media_assets table with category/dimension constraints and indexes."""
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(length=32), server_default="general", nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=64), server_default="image/webp", nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("thumb_path", sa.String(length=512), nullable=False),
        sa.Column("medium_path", sa.String(length=512), nullable=False),
        sa.Column("large_path", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('workshop', 'certificate', 'product', 'milestone', 'news', 'general')",
            name="ck_media_assets_category",
        ),
        sa.CheckConstraint("width > 0", name="ck_media_assets_width_positive"),
        sa.CheckConstraint("height > 0", name="ck_media_assets_height_positive"),
        sa.CheckConstraint("size_bytes > 0", name="ck_media_assets_size_bytes_positive"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_media_assets_owner_user_id", "media_assets", ["owner_user_id"], unique=False
    )
    op.create_index("ix_media_assets_created_at", "media_assets", ["created_at"], unique=False)


def downgrade() -> None:
    """Drop media_assets table and its indexes."""
    op.drop_index("ix_media_assets_created_at", table_name="media_assets")
    op.drop_index("ix_media_assets_owner_user_id", table_name="media_assets")
    op.drop_table("media_assets")
