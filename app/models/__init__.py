"""SQLAlchemy 모델 모음.

Alembic autogenerate가 테이블을 인식하려면 새 모델을 여기서 임포트해야 한다.
"""

from app.models.shorts_project import PromotionPurpose, ShortsProject, ShortsStatus
from app.models.store import Store
from app.models.store_insight import StoreInsight
from app.models.store_menu import StoreMenu
from app.models.store_photo import StorePhoto
from app.models.store_target_customer import StoreTargetCustomer, TargetStatus
from app.models.user import User
from app.models.video_format import VideoFormat

__all__ = [
    "PromotionPurpose",
    "ShortsProject",
    "ShortsStatus",
    "Store",
    "StoreInsight",
    "StoreMenu",
    "StorePhoto",
    "StoreTargetCustomer",
    "TargetStatus",
    "User",
    "VideoFormat",
]
