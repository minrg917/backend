"""카카오맵 대표 메뉴 자동 수집 테스트 (`app/services/menu_crawl.py`).

실제 셀레니움·크롬은 부르지 않는다 — `subprocess.run`을 가짜로 대체해
**우리 코드의 판단**(락 획득 실패 시 건너뛰기, 실패를 조용히 삼키기, 이미 메뉴가
있으면 자동 수집을 건너뛰기)만 검증한다. 크롤링 자체의 성공 여부는 별개다.
"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session, sessionmaker

from app.models.store import Store
from app.models.store_menu import StoreMenu
from app.models.user import User
from app.services import menu_crawl


def _make_store(db_session: Session, external_channel_url: str | None) -> Store:
    user = User(
        email="owner@example.com",
        name="김사장",
        is_active=True,
        terms_agreed=True,
        marketing_agreed=False,
    )
    db_session.add(user)
    db_session.flush()

    store = Store(user_id=user.id, name="행복분식", external_channel_url=external_channel_url)
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)
    return store


def _session_factory(db_session: Session) -> sessionmaker:
    """테스트 세션을 재사용하는 팩토리. 실제로는 매번 새 세션을 여는 자리다."""
    return lambda: db_session


# ---------------------------------------------------------------- kakao_place_id


def test_kakao_place_id_extracts_from_url(db_session: Session) -> None:
    store = _make_store(db_session, "http://place.map.kakao.com/10534102")

    assert menu_crawl.kakao_place_id(store) == "10534102"


def test_kakao_place_id_none_for_naver_link(db_session: Session) -> None:
    """네이버 소스로 잡힌 가게(예: 사장님 자체 홈페이지 링크)는 재검색하지 않는다."""
    store = _make_store(db_session, "https://our-restaurant.example.com")

    assert menu_crawl.kakao_place_id(store) is None


def test_kakao_place_id_none_when_missing(db_session: Session) -> None:
    """직접 입력으로 등록된 가게는 채널 URL 자체가 없다."""
    store = _make_store(db_session, None)

    assert menu_crawl.kakao_place_id(store) is None


# ---------------------------------------------------------------- enrich_menu_from_kakao


def _fake_completed_process(stdout: str, returncode: int = 0) -> Any:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = ""
    return result


def test_enrich_saves_crawled_items(db_session: Session) -> None:
    store = _make_store(db_session, "http://place.map.kakao.com/10534102")
    items = [{"name": "브루드 커피", "price": 4500}, {"name": "카푸치노", "price": 5200}]

    with (
        patch("app.services.menu_crawl._acquire_lock", return_value=True),
        patch("app.services.menu_crawl._release_lock"),
        patch("app.services.menu_crawl.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _fake_completed_process(json.dumps(items))
        menu_crawl.enrich_menu_from_kakao(store.id, "10534102", _session_factory(db_session))

    menus = db_session.query(StoreMenu).filter(StoreMenu.store_id == store.id).all()
    assert {m.name for m in menus} == {"브루드 커피", "카푸치노"}
    assert {m.price for m in menus} == {4500, 5200}


def test_enrich_skips_when_lock_unavailable(db_session: Session) -> None:
    """서버에 다른 크롤링이 이미 도는 중이면 기다리지 않고 건너뛴다."""
    store = _make_store(db_session, "http://place.map.kakao.com/10534102")

    with (
        patch("app.services.menu_crawl._acquire_lock", return_value=False),
        patch("app.services.menu_crawl.subprocess.run") as mock_run,
    ):
        menu_crawl.enrich_menu_from_kakao(store.id, "10534102", _session_factory(db_session))

        mock_run.assert_not_called()


def test_enrich_silently_ignores_crawl_failure(db_session: Session) -> None:
    """실패해도 예외가 밖으로 새면 안 된다 — 백그라운드 작업이라 아무도 못 본다."""
    store = _make_store(db_session, "http://place.map.kakao.com/10534102")

    with (
        patch("app.services.menu_crawl._acquire_lock", return_value=True),
        patch("app.services.menu_crawl._release_lock"),
        patch("app.services.menu_crawl.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _fake_completed_process("[]", returncode=1)

        menu_crawl.enrich_menu_from_kakao(store.id, "10534102", _session_factory(db_session))

    assert db_session.query(StoreMenu).filter(StoreMenu.store_id == store.id).count() == 0


def test_enrich_ignores_malformed_output(db_session: Session) -> None:
    store = _make_store(db_session, "http://place.map.kakao.com/10534102")

    with (
        patch("app.services.menu_crawl._acquire_lock", return_value=True),
        patch("app.services.menu_crawl._release_lock"),
        patch("app.services.menu_crawl.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _fake_completed_process("이건 JSON이 아니다")

        menu_crawl.enrich_menu_from_kakao(store.id, "10534102", _session_factory(db_session))

    assert db_session.query(StoreMenu).filter(StoreMenu.store_id == store.id).count() == 0


def test_enrich_does_not_overwrite_existing_menu(db_session: Session) -> None:
    """사장님이 이미 직접 입력해뒀으면 자동 수집으로 덮어쓰지 않는다."""
    store = _make_store(db_session, "http://place.map.kakao.com/10534102")
    db_session.add(StoreMenu(store_id=store.id, name="사장님이 입력한 메뉴", price=1000))
    db_session.commit()

    with (
        patch("app.services.menu_crawl._acquire_lock", return_value=True),
        patch("app.services.menu_crawl._release_lock"),
        patch("app.services.menu_crawl.subprocess.run") as mock_run,
    ):
        mock_run.return_value = _fake_completed_process(
            json.dumps([{"name": "크롤링 메뉴", "price": 5000}])
        )

        menu_crawl.enrich_menu_from_kakao(store.id, "10534102", _session_factory(db_session))
        mock_run.assert_called_once()

    menus = db_session.query(StoreMenu).filter(StoreMenu.store_id == store.id).all()
    assert [m.name for m in menus] == ["사장님이 입력한 메뉴"]


def test_enrich_survives_timeout(db_session: Session) -> None:
    import subprocess

    store = _make_store(db_session, "http://place.map.kakao.com/10534102")

    with (
        patch("app.services.menu_crawl._acquire_lock", return_value=True),
        patch("app.services.menu_crawl._release_lock"),
        patch("app.services.menu_crawl.subprocess.run") as mock_run,
    ):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="crawl", timeout=30)

        menu_crawl.enrich_menu_from_kakao(store.id, "10534102", _session_factory(db_session))

    assert db_session.query(StoreMenu).filter(StoreMenu.store_id == store.id).count() == 0


def test_enrich_survives_missing_dependency(db_session: Session) -> None:
    """selenium이 안 깔린 환경(로컬 개발 등)에서도 API는 죽지 않는다."""
    store = _make_store(db_session, "http://place.map.kakao.com/10534102")

    with (
        patch("app.services.menu_crawl._acquire_lock", return_value=True),
        patch("app.services.menu_crawl._release_lock"),
        patch("app.services.menu_crawl.subprocess.run") as mock_run,
    ):
        mock_run.side_effect = FileNotFoundError()

        menu_crawl.enrich_menu_from_kakao(store.id, "10534102", _session_factory(db_session))

    assert db_session.query(StoreMenu).filter(StoreMenu.store_id == store.id).count() == 0
