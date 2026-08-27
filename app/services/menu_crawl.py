"""가게 등록 직후 카카오맵에서 대표 메뉴를 자동으로 채우는 기능 (2.2 후속 처리).

**가게 등록 자체를 절대 막지 않는다.** 이 모듈의 모든 실패는 조용히 넘어간다 —
조회가 안 되면 사장님은 3.2에서 그대로 직접 입력하면 된다. 실패를 사장님에게
보여줄 이유가 없는 부가 기능이라는 게 이 모듈 전체를 관통하는 설계 원칙이다.

**동명 매장 오매칭을 피하려고 이름으로 재검색하지 않는다**(`docs/PM_DECISIONS.md`
2026-08-21 결정과 같은 원칙). 2.1 검색 단계에서 이미 잡아둔 `kakao_place_id`(또는
`external_channel_url`이 카카오 플레이스 링크일 때 거기서 뽑은 ID)가 있을 때만
조회한다. 없으면(네이버로만 잡혔거나 직접 입력한 가게) 시도 자체를 안 한다.

2026-08-27: 헤드리스 크롬으로 카카오맵 화면을 스크래핑하던 방식(`scripts/
crawl_kakao_menu.py`, 이제 삭제)을 카카오맵 웹사이트 자체가 화면을 그릴 때 쓰는
비공식 내부 API(`place-api.map.kakao.com`) 직접 호출로 교체했다. 실서버에서
메뉴 자동 수집이 계속 조용히 실패하던 걸 조사하다가 FE가 이 API를 찾아냈다
(2026-08-27, 실측 15회 이상 연속 호출 전부 성공).

**여전히 비공식 크롤링이라는 성격은 그대로다** — 공식 문서가 없고, 카카오가
내부 구조를 바꾸면 예고 없이 깨질 수 있다. 다만 무거운 크롬 프로세스(200~350MB)
대신 가벼운 HTTP 요청 하나라, 여러 가게 등록이 겹쳐도 API 프로세스에 부담이
없다 — 그래서 기존에 있던 "서버 전체 동시 1개만 크롤링" MySQL 락, 서브프로세스
격리, Chrome/Selenium 의존성을 전부 걷어냈다.
"""

import logging
import re

import httpx
from sqlalchemy.orm import Session, sessionmaker

from app.models.store import Store
from app.models.store_menu import StoreMenu

logger = logging.getLogger(__name__)

_MENU_LIMIT = 5
_REQUEST_TIMEOUT_SEC = 10.0
_MENU_API_URL = "https://place-api.map.kakao.com/places/panel3/{place_id}"
_KAKAO_PLACE_RE = re.compile(r"place\.map\.kakao\.com/(\d+)")
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


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


def enrich_menu_from_kakao(store_id: int, place_id: str, session_factory: sessionmaker) -> None:
    """백그라운드에서 실행된다(FastAPI `BackgroundTasks`).

    응답이 이미 나간 뒤에 돌기 때문에 원래 요청의 DB 세션은 재사용할 수 없다 —
    `session_factory`로 새 세션을 직접 연다.
    """
    db = session_factory()
    try:
        _crawl_and_save(db, store_id, place_id)
    except Exception:
        # 백그라운드 작업의 예외는 아무도 안 본다 — 여기서 잡아 로그로만 남긴다.
        logger.exception("메뉴 자동 수집 중 처리되지 않은 예외: store_id=%s", store_id)
    finally:
        db.close()


def _fetch_menu_items(place_id: str) -> list[dict]:
    """카카오맵 웹사이트가 화면을 그릴 때 쓰는 내부 API에서 메뉴를 가져온다.

    공식 API가 아니라서 실패를 예외적인 상황으로 다루지 않는다 — 호출 실패,
    비정상 응답, 메뉴가 아예 없는 가게 전부 빈 리스트로 수렴시켜 호출부가 한
    가지 방식으로만 처리하면 되게 한다. `Referer`/`Origin`/`pf` 헤더가 없으면
    406이 난다(2026-08-27 실측) — 이 웹사이트에서 온 요청인지를 이걸로 거른다.
    """
    try:
        response = httpx.get(
            _MENU_API_URL.format(place_id=place_id),
            headers={
                "Referer": f"https://place.map.kakao.com/{place_id}",
                "Origin": "https://place.map.kakao.com",
                "pf": "web",
                "User-Agent": _USER_AGENT,
            },
            timeout=_REQUEST_TIMEOUT_SEC,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError):
        logger.info("카카오 메뉴 조회 실패: place_id=%s", place_id)
        return []

    items = data.get("menu", {}).get("menus", {}).get("items") or []
    return items[:_MENU_LIMIT]


def _crawl_and_save(db: Session, store_id: int, place_id: str) -> None:
    items = _fetch_menu_items(place_id)
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
        db.add(
            StoreMenu(
                store_id=store_id,
                name=name[:200],
                price=item.get("price"),
                image_url=item.get("photo_url"),
            )
        )
    db.commit()
    logger.info("메뉴 자동 수집 완료: store_id=%s count=%d", store_id, len(items))
