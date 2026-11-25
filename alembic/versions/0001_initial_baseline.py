"""Initial baseline migration.

Revision ID: 0001_initial_baseline
Revises:
Create Date: 2026-11-26 00:45:00
"""

from collections.abc import Sequence

revision: str = "0001_initial_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Establish baseline Alembic revision tracking."""


def downgrade() -> None:
    """Revert baseline Alembic revision tracking."""
