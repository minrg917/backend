"""replace face exposure level with requires-face boolean

Revision ID: c8d4e2f6a901
Revises: b3f1c7a90d42
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d4e2f6a901"
down_revision: str | None = "b3f1c7a90d42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "video_formats",
        sa.Column("requires_face", sa.Boolean(), nullable=True, comment="얼굴 노출 필수 여부"),
    )
    op.create_index(
        op.f("ix_video_formats_requires_face"),
        "video_formats",
        ["requires_face"],
        unique=False,
    )
    op.execute(
        sa.text(
            "UPDATE video_formats SET requires_face = CASE "
            "WHEN face_exposure_level = '낮음' THEN false "
            "WHEN face_exposure_level IN ('보통', '높음') THEN true "
            "ELSE NULL END"
        )
    )
    op.drop_index(op.f("ix_video_formats_face_exposure_level"), table_name="video_formats")
    op.drop_column("video_formats", "face_exposure_level")


def downgrade() -> None:
    op.add_column(
        "video_formats",
        sa.Column("face_exposure_level", sa.String(length=20), nullable=True),
    )
    op.create_index(
        op.f("ix_video_formats_face_exposure_level"),
        "video_formats",
        ["face_exposure_level"],
        unique=False,
    )
    op.execute(
        sa.text(
            "UPDATE video_formats SET face_exposure_level = CASE "
            "WHEN requires_face = true THEN '높음' "
            "WHEN requires_face = false THEN '낮음' "
            "ELSE NULL END"
        )
    )
    op.drop_index(op.f("ix_video_formats_requires_face"), table_name="video_formats")
    op.drop_column("video_formats", "requires_face")
