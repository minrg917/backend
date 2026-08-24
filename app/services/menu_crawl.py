"""가게 등록 직후 카카오맵에서 대표 메뉴를 자동으로 채우는 기능 (2.2 후속 처리).

**가게 등록 자체를 절대 막지 않는다.** 이 모듈의 모든 실패는 조용히 넘어간다 —
크롤링이 안 되면 사장님은 3.2에서 그대로 직접 입력하면 된다. 실패를 사장님에게
보여줄 이유가 없는 부가 기능이라는 게 이 모듈 전체를 관통하는 설계 원칙이다.

**동명 매장 오매칭을 피하려고 이름으로 재검색하지 않는다**(`docs/PM_DECISIONS.md`
2026-08-21 결정과 같은 원칙). 2.1 검색 단계에서 이미 잡아둔 `external_channel_url`이
카카오 플레이스 링크일 때만 크롤링한다. 없으면(네이버로만 잡혔거나 직접 입력한
가게) 시도 자체를 안 한다.

**서버 전체에서 동시에 1개만 돈다.** 헤드리스 크롬이 무거워서(200~350MB) 여러
가게 등록이 겹치면 API 메모리 압박·CPU 크레딧 소진으로 이어질 수 있다(2026-08-24
직접 확인 — 첫 시도에서 캡차, 재시도에서 성공했지만 크롬 자체의 무게는 별개
문제다). 두 uvicorn 워커가 별도 프로세스라 파이썬 락으로는 못 막아서, MySQL
네임드 락(`GET_LOCK`)으로 프로세스 경계를 넘어 막는다. 이미 도는 중이면
**기다리지 않고 그냥 건너뛴다** — 대기열을 만들 만큼 중요한 기능이 아니고,
쌓이면 오히려 다음 등록들까지 지연시킨다.

크롤링은 API 프로세스 안에서 셀레니움을 직접 돌리지 않고 **별도 프로세스로
분리**한다(`subprocess`) — 크롬이 멈추거나 뻗어도 API 워커 자체는 영향받지 않는다.
"""

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.models.store import Store
from app.models.store_menu import StoreMenu

logger = logging.getLogger(__name__)

_LOCK_NAME = "kakao_menu_crawl"
_LOCK_WAIT_SEC = 0  # 기다리지 않는다 — 락을 못 잡으면 바로 포기한다.
_CRAWL_TIMEOUT_SEC = 30
_MENU_LIMIT = 5

_KAKAO_PLACE_RE = re.compile(r"place\.map\.kakao\.com/(\d+)")
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def kakao_place_id(store: Store) -> str | None:
    """가게의 `external_channel_url`이 카카오 플레이스 링크면 ID를 뽑는다.

    NAVER 소스로 등록됐어도, 검색 단계의 후보 병합에서 카카오 링크가 채워져
    있을 수 있다(`store_search.merge_duplicates`가 NAVER 결과에 링크가 없으면
    카카오 것으로 채운다) — 그래서 `info_source`가 아니라 URL 자체를 본다.
    """
    if not store.external_channel_url:
        return None
    match = _KAKAO_PLACE_RE.search(store.external_channel_url)
    return match.group(1) if match else None


def _acquire_lock(db: Session) -> bool:
    """MySQL 네임드 락을 잡는다. 실패(다른 세션이 보유 중)면 `False`.

    별도 함수로 뺀 이유는 테스트 때문이다 — `GET_LOCK`은 MySQL 전용 함수라
    테스트에 쓰는 SQLite에서는 호출 자체가 안 된다. 여기만 흉내 내면 나머지
    ORM 로직(`db.query`, `db.add` 등)은 실제 SQLite로 그대로 검증할 수 있다.
    """
    return (
        db.execute(
            text("SELECT GET_LOCK(:name, :wait)"), {"name": _LOCK_NAME, "wait": _LOCK_WAIT_SEC}
        ).scalar()
        == 1
    )


def _release_lock(db: Session) -> None:
    db.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": _LOCK_NAME})


def enrich_menu_from_kakao(store_id: int, place_id: str, session_factory: sessionmaker) -> None:
    """백그라운드에서 실행된다(FastAPI `BackgroundTasks`).

    응답이 이미 나간 뒤에 돌기 때문에 원래 요청의 DB 세션은 재사용할 수 없다 —
    `session_factory`로 새 세션을 직접 연다.
    """
    db = session_factory()
    try:
        if not _acquire_lock(db):
            logger.info("메뉴 크롤링 건너뜀(다른 크롤링 진행 중): store_id=%s", store_id)
            return

        try:
            _crawl_and_save(db, store_id, place_id)
        finally:
            _release_lock(db)
    except Exception:
        # 백그라운드 작업의 예외는 아무도 안 본다 — 여기서 잡아 로그로만 남긴다.
        logger.exception("메뉴 크롤링 중 처리되지 않은 예외: store_id=%s", store_id)
    finally:
        db.close()


def _crawl_and_save(db: Session, store_id: int, place_id: str) -> None:
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.crawl_kakao_menu",
                place_id,
                "--limit",
                str(_MENU_LIMIT),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=_CRAWL_TIMEOUT_SEC,
            cwd=_PROJECT_ROOT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("메뉴 크롤링 타임아웃: store_id=%s", store_id)
        return
    except FileNotFoundError:
        # selenium/webdriver-manager가 이 환경에 없다(예: 로컬 개발 서버).
        # 배포 서버에만 크롤링용 의존성을 깔아두므로 조용히 넘어간다.
        logger.info("메뉴 크롤링 의존성 없음(개발 환경일 수 있음): store_id=%s", store_id)
        return

    if result.returncode != 0:
        logger.info("메뉴 크롤링 실패: store_id=%s stderr=%s", store_id, result.stderr[-500:])
        return

    try:
        items = json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.warning("메뉴 크롤링 출력 파싱 실패: store_id=%s", store_id)
        return

    if not items:
        return

    # 가게가 그 사이 삭제됐거나(경합), 사장님이 이미 메뉴를 직접 입력해뒀으면
    # 자동 수집 결과로 덮어쓰지 않는다 — 사람이 넣은 값이 우선이다.
    store = db.get(Store, store_id)
    if store is None:
        return
    if db.query(StoreMenu).filter(StoreMenu.store_id == store_id).first() is not None:
        logger.info("메뉴 이미 존재해 자동 수집 건너뜀: store_id=%s", store_id)
        return

    for item in items:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        db.add(StoreMenu(store_id=store_id, name=name[:200], price=item.get("price")))
    db.commit()
    logger.info("메뉴 자동 수집 완료: store_id=%s count=%d", store_id, len(items))
