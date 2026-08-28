"""add thumbnail_url to shooting_tasks

Revision ID: e96ee07addd2
Revises: 6a17f402d9c1
Create Date: 2026-08-28 10:33:50.998002

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e96ee07addd2'
down_revision: Union[str, Sequence[str], None] = '6a17f402d9c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('shooting_tasks', sa.Column('thumbnail_url', sa.String(length=255), nullable=True, comment='촬영본 대표 프레임 썸네일(영상만, ffmpeg 추출 실패 시 null)'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('shooting_tasks', 'thumbnail_url')
