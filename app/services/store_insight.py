"""가게 인사이트 조회·생성 로직 (API명세서 3.5).

조회는 화면에서 그대로 쓰고, 생성(상권분석)은 가게 등록(2.2) 직후 백그라운드에서
자동으로 만들어 캐시해둔다 — 메뉴 자동수집(`app/services/menu_crawl.py`)과 같은
패턴이다(2026-08-27). 카드뉴스·다음숏폼추천 등 다른 인사이트 유형의 생성 로직은
아직 이 모듈 범위 밖이다.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.store import Store
from app.models.store_insight import StoreInsight
from app.services import ai_client
from app.services.store import MARKET_INSIGHT_TYPE

logger = logging.getLogger(__name__)


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


def generate_trade_area_insight(store_id: int, session_factory: sessionmaker) -> None:
    """백그라운드에서 실행된다(FastAPI `BackgroundTasks`, 가게 등록 2.2 직후).

    응답이 이미 나간 뒤에 돌기 때문에 원래 요청의 DB 세션은 재사용할 수 없다 —
    `session_factory`로 새 세션을 직접 연다. **가게 등록 자체를 절대 막지
    않는다** — 모든 실패는 조용히 넘어간다(`menu_crawl.py`와 같은 설계 원칙).
    """
    db = session_factory()
    try:
        _generate_and_save(db, store_id)
    except Exception:
        # 백그라운드 작업의 예외는 아무도 안 본다 — 여기서 잡아 로그로만 남긴다.
        logger.exception("상권분석 생성 중 처리되지 않은 예외: store_id=%s", store_id)
    finally:
        db.close()


def _generate_and_save(db: Session, store_id: int) -> None:
    store = db.get(Store, store_id)
    if store is None:
        return

    insight = ai_client.get_trade_area_insight(store)
    # 나이·성별 분포는 실제 통계 주장이라 AI 연동 전(placeholder)에는 아무 값도
    # 안 준다. 아무것도 못 받았으면 빈 행을 만들지 않는다 — "준비 중" 빈 상태와
    # "생성했는데 다 비어 있음"을 구분하지 않아도 되게 한다.
    if insight.summary is None and insight.age_distribution is None:
        return

    insight_data = None
    if insight.age_distribution is not None or insight.gender_distribution is not None:
        insight_data = {
            "age_distribution": insight.age_distribution,
            "gender_distribution": insight.gender_distribution,
        }

    db.add(
        StoreInsight(
            store_id=store_id,
            insight_type=MARKET_INSIGHT_TYPE,
            insight_title=insight.district_name,
            insight_content=insight.summary,
            insight_data=insight_data,
            # insight_source는 이 유형에서 채우지 않는다 — LLM+상권분석DB+외부
            # API를 종합한 결과라 "외부데이터/AI추론" 이분법에 안 맞는다
            # (docs/IMPLEMENTATION.md 2026-08-27 항목 참고).
        )
    )
    db.commit()
    logger.info("상권분석 생성 완료: store_id=%s", store_id)
