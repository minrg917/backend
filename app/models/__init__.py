"""SQLAlchemy 모델 모음.

Alembic autogenerate가 테이블을 인식하려면 새 모델을 여기서 임포트해야 한다.
"""

from app.models.format_favorite import FormatFavorite
from app.models.shooting_task import COMPLETED_STATUSES, FootageType, ShootingTask, TaskStatus
from app.models.shorts_project import PromotionPurpose, ShortsProject, ShortsStatus
from app.models.sns import PostStatus, SnsConnection, SnsPost, SnsPostMetric
from app.models.store import Store
from app.models.store_insight import StoreInsight
from app.models.store_menu import StoreMenu
from app.models.store_photo import StorePhoto
from app.models.store_target_customer import StoreTargetCustomer, TargetStatus
from app.models.storyboard_scene import StoryboardScene
from app.models.user import User
from app.models.video_format import VideoFormat
from app.models.video_output import RenderStatus, VideoOutput

__all__ = [
    "FormatFavorite",
    "COMPLETED_STATUSES",
    "FootageType",
    "PromotionPurpose",
    "ShootingTask",
    "TaskStatus",
    "ShortsProject",
    "ShortsStatus",
    "PostStatus",
    "SnsConnection",
    "SnsPost",
    "SnsPostMetric",
    "Store",
    "StoreInsight",
    "StoreMenu",
    "StorePhoto",
    "StoreTargetCustomer",
    "StoryboardScene",
    "TargetStatus",
    "RenderStatus",
    "User",
    "VideoFormat",
    "VideoOutput",
]
