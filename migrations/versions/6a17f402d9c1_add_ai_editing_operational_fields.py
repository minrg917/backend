"""add AI editing operational fields

Revision ID: 6a17f402d9c1
Revises: a6a8e36cf73b
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "6a17f402d9c1"
down_revision: Union[str, Sequence[str], None] = "a6a8e36cf73b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("video_outputs", sa.Column("warnings", sa.JSON(), nullable=True))
    op.add_column("video_outputs", sa.Column("queue_position", sa.Integer(), nullable=True))
    op.add_column("video_outputs", sa.Column("estimated_wait_sec", sa.Integer(), nullable=True))
    op.add_column("video_outputs", sa.Column("stage_elapsed_sec", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("video_outputs", "stage_elapsed_sec")
    op.drop_column("video_outputs", "estimated_wait_sec")
    op.drop_column("video_outputs", "queue_position")
    op.drop_column("video_outputs", "warnings")
