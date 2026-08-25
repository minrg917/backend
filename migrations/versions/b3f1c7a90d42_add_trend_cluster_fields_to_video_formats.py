"""add trend cluster fields to video_formats

Revision ID: b3f1c7a90d42
Revises: 005c4b0383a9
Create Date: 2026-08-25 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f1c7a90d42'
down_revision: Union[str, Sequence[str], None] = '005c4b0383a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'video_formats',
        sa.Column(
            'guide_video_url',
            sa.String(length=255),
            nullable=True,
            comment='가이드 영상 URL(촬영 준비 화면에서 사용)',
        ),
    )
    op.add_column(
        'video_formats',
        sa.Column(
            'trend_challenge_id',
            sa.String(length=160),
            nullable=True,
            comment='AI 트렌드 클러스터 챌린지 ID',
        ),
    )
    op.add_column(
        'video_formats',
        sa.Column(
            'trend_rank',
            sa.Integer(),
            nullable=True,
            comment='AI 트렌드 클러스터 순위',
        ),
    )
    op.create_unique_constraint(
        'uq_video_formats_trend_challenge_id', 'video_formats', ['trend_challenge_id']
    )
    op.create_index(
        op.f('ix_video_formats_trend_rank'), 'video_formats', ['trend_rank'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_video_formats_trend_rank'), table_name='video_formats')
    op.drop_constraint(
        'uq_video_formats_trend_challenge_id', 'video_formats', type_='unique'
    )
    op.drop_column('video_formats', 'trend_rank')
    op.drop_column('video_formats', 'trend_challenge_id')
    op.drop_column('video_formats', 'guide_video_url')
