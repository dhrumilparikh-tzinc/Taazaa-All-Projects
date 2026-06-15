"""add PARTIAL job status

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-05

JobStatus.partial is stored as the plain string "PARTIAL" in the status column
(VARCHAR, not a Postgres ENUM type) so no ALTER TYPE is needed — the column
already accepts any string value.  This migration is a no-op at the DB level;
it exists to document the new application-level status value.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The jobs.status column is VARCHAR — no DDL change required.
    # Update any lingering NULL status rows to PENDING for safety.
    op.execute(
        "UPDATE jobs SET status = 'PENDING' WHERE status IS NULL"
    )


def downgrade() -> None:
    # Remove any PARTIAL rows (convert back to FAILED so old code doesn't break)
    op.execute(
        "UPDATE jobs SET status = 'FAILED' WHERE status = 'PARTIAL'"
    )
