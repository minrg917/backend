"""가게 인사이트 조회 로직 (API명세서 3.5).

생성(쓰기)은 이 모듈 범위 밖이다 — 외부 상권 데이터 API 연동과 AI 추론이 붙는
별도 작업에서 다룬다. 여기서는 이미 만들어진 인사이트를 읽기만 한다.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.store import Store
from app.models.store_insight import StoreInsight


def list_insights(db: Session, store: Store, insight_type: str | None = None) -> list[StoreInsight]:
    """가게 인사이트를 최신순으로 돌려준다.

    `insight_type`을 주면 그 유형만 거른다(상권분석/카드뉴스/다음숏폼추천 등).
    한 화면에서 여러 유형을 함께 쓰는 경우가 있어 생략하면 전체를 내려준다.
    """
    statement = select(StoreInsight).where(StoreInsight.store_id == store.id)
    if insight_type:
        statement = statement.where(StoreInsight.insight_type == insight_type)
    return list(
        db.scalars(statement.order_by(StoreInsight.generated_at.desc(), StoreInsight.id.desc()))
    )
