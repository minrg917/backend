"""가게 통합검색 (API명세서 2.1).

NAVER 지역 검색과 Kakao 로컬 키워드 검색을 동시에 호출해 하나의 목록으로 합친다
(기능명세서 S02.1.1). 설계상 지켜야 하는 것들:

- **한쪽이 실패해도 검색은 계속된다.** 외부 API 장애·타임아웃으로 전체가 500이 되면
  가게 등록 자체를 못 하게 되므로, 실패한 출처는 로그만 남기고 건너뛴다.
- **키가 없는 출처는 조용히 제외한다.** CI·신규 개발자 환경에 키가 없어도 서버가 뜬다.
- **`external_channel_url`은 검색 API가 준 값을 그대로 통과시킨다.** 이름·출처로
  재검색해서 채우지 않는다(동명 매장 오매칭 위험 — `docs/PM_DECISIONS.md` 2026-08-21).
"""

import asyncio
import logging
import re
from decimal import Decimal

import httpx

from app.core.config import settings
from app.schemas.store import SearchSource, StoreSearchResult

logger = logging.getLogger(__name__)

KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

# 출처당 가져올 최대 후보 수. NAVER 지역검색은 display 최대가 5다.
NAVER_DISPLAY = 5
KAKAO_SIZE = 15

_HTML_TAG = re.compile(r"<[^>]+>")
# 주소 끝에 붙는 괄호 보조표기 — NAVER는 "... 테헤란로 152 (역삼동)"처럼 법정동을 덧붙인다.
_PAREN = re.compile(r"\([^)]*\)")
# 중복 판정용 좌표 오차 — 약 50m. 위경도 0.00045도 ≈ 50m.
_COORD_TOLERANCE = Decimal("0.00045")


def _strip_html(value: str) -> str:
    """NAVER 지역검색의 title은 검색어가 `<b>`로 감싸여 오므로 태그를 제거한다."""
    return _HTML_TAG.sub("", value).strip()


def _naver_coord(raw: str | None) -> Decimal | None:
    """NAVER의 mapx/mapy를 위경도로 변환한다.

    현재 지역검색 API는 WGS84 좌표를 소수점 없이 10^7배한 정수 문자열로 준다
    (예: mapx="1270312345" → 127.0312345). 값이 이미 도 단위인 응답도 방어적으로 허용한다.
    """
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except (ArithmeticError, TypeError, ValueError):
        return None
    if abs(value) > 1000:  # 도 단위라면 |경도| <= 180 이므로 스케일된 값이다
        value = value / Decimal(10**7)
    return value.quantize(Decimal("0.0000001"))


def _to_decimal(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    try:
        return Decimal(raw).quantize(Decimal("0.0000001"))
    except (ArithmeticError, TypeError, ValueError):
        return None


def _parse_naver(item: dict) -> StoreSearchResult:
    return StoreSearchResult(
        source=SearchSource.NAVER,
        name=_strip_html(item.get("title", "")),
        # 도로명주소가 있으면 그쪽이 더 정확하다
        address=item.get("roadAddress") or item.get("address") or None,
        jibun_address=item.get("address") or None,
        phone=item.get("telephone") or None,
        latitude=_naver_coord(item.get("mapy")),
        longitude=_naver_coord(item.get("mapx")),
        category=item.get("category") or None,
        # NAVER 지역검색은 기준 좌표를 받지 않아 거리를 주지 않는다.
        distance_m=None,
        external_channel_url=item.get("link") or None,
    )


def _parse_kakao(doc: dict) -> StoreSearchResult:
    distance = doc.get("distance")
    return StoreSearchResult(
        source=SearchSource.KAKAO,
        name=doc.get("place_name", ""),
        address=doc.get("road_address_name") or doc.get("address_name") or None,
        jibun_address=doc.get("address_name") or None,
        phone=doc.get("phone") or None,
        latitude=_to_decimal(doc.get("y")),
        longitude=_to_decimal(doc.get("x")),
        category=doc.get("category_group_name") or doc.get("category_name") or None,
        # 기준 좌표(x,y)를 넘긴 경우에만 채워져서 온다.
        distance_m=int(distance) if distance else None,
        external_channel_url=doc.get("place_url") or None,
        kakao_place_id=doc.get("id") or None,
    )


async def _fetch_naver(client: httpx.AsyncClient, keyword: str) -> list[StoreSearchResult]:
    """NAVER 지역검색을 호출한다.

    2026-06-25 NAVER API HUB(NCP)로 이관되면서 인증 방식이 바뀌었다.
    구방식(`openapi.naver.com` + `X-Naver-Client-Id`/`X-Naver-Client-Secret`)은
    2026-07-30 이전 발급 키만 2027-06-30까지 쓸 수 있어, 신규 키 기준인
    NCP API Gateway 헤더를 사용한다. 엔드포인트는 콘솔에서 확인해 설정으로 주입한다.
    """
    response = await client.get(
        settings.NAVER_SEARCH_LOCAL_URL,
        params={"query": keyword, "display": NAVER_DISPLAY},
        headers={
            "X-NCP-APIGW-API-KEY-ID": settings.NAVER_API_KEY_ID,
            "X-NCP-APIGW-API-KEY": settings.NAVER_API_KEY,
        },
    )
    response.raise_for_status()
    return [_parse_naver(item) for item in response.json().get("items", [])]


async def _fetch_kakao(
    client: httpx.AsyncClient,
    keyword: str,
    latitude: Decimal | None,
    longitude: Decimal | None,
) -> list[StoreSearchResult]:
    params: dict[str, str | int] = {"query": keyword, "size": KAKAO_SIZE}
    if latitude is not None and longitude is not None:
        # Kakao는 x=경도, y=위도. 기준 좌표를 주면 응답에 distance(m)가 함께 온다.
        params["x"] = str(longitude)
        params["y"] = str(latitude)
        params["sort"] = "distance"

    response = await client.get(
        KAKAO_KEYWORD_URL,
        params=params,
        headers={"Authorization": f"KakaoAK {settings.KAKAO_REST_API_KEY}"},
    )
    response.raise_for_status()
    return [_parse_kakao(doc) for doc in response.json().get("documents", [])]


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", name).lower()


def _normalize_address(address: str | None) -> str:
    if not address:
        return ""
    return re.sub(r"\s+", "", _PAREN.sub("", address)).lower()


def _address_tail(address: str | None) -> str:
    """주소에서 도로명·번지에 해당하는 뒤쪽 두 토큰만 뽑는다.

    출처마다 시도 표기가 달라(NAVER "서울특별시 강남구 테헤란로 152 (역삼동)" /
    Kakao "서울 강남구 테헤란로 152") 앞부분을 그대로 비교하면 같은 가게도 어긋난다.
    실제 응답을 비교해보면 뒤쪽 "테헤란로 152"는 양쪽이 일치하므로 그 부분만 본다.
    """
    if not address:
        return ""
    tokens = _PAREN.sub("", address).split()
    return "".join(tokens[-2:]).lower()


def _is_same_place(left: StoreSearchResult, right: StoreSearchResult) -> bool:
    """같은 가게로 볼지 판정한다 (기능명세서 S02.1.1 "상호명·주소·좌표 기준 중복 병합").

    상호명이 다르면 무조건 다른 가게로 본다 — 한 건물에 여러 가게가 있을 수 있어
    좌표만으로 합치면 서로 다른 매장이 묶인다.
    """
    if _normalize_name(left.name) != _normalize_name(right.name):
        return False

    left_address = _normalize_address(left.address)
    right_address = _normalize_address(right.address)
    if left_address and right_address:
        # 출처마다 지번/도로명이 섞여 있어 완전 일치를 요구하지 않고 포함 관계로 본다
        if left_address in right_address or right_address in left_address:
            return True
        # 시도 표기(서울 / 서울특별시)만 다른 경우가 많아 도로명·번지끼리도 비교한다.
        # 상호명이 이미 같다는 전제라 도로명·번지가 같으면 같은 가게로 봐도 안전하다.
        left_tail = _address_tail(left.address)
        if left_tail and left_tail == _address_tail(right.address):
            return True

    if None not in (left.latitude, left.longitude, right.latitude, right.longitude):
        return (
            abs(left.latitude - right.latitude) <= _COORD_TOLERANCE  # type: ignore[operator]
            and abs(left.longitude - right.longitude) <= _COORD_TOLERANCE  # type: ignore[operator]
        )

    # 이름은 같은데 주소·좌표를 하나도 비교할 수 없으면 합치지 않는다(오병합 방지)
    return False


def _merge_into(base: StoreSearchResult, other: StoreSearchResult) -> None:
    """먼저 잡힌 후보(base)의 빈 값을 뒤 후보(other)의 값으로 채운다.

    `source`는 base 것을 유지한다 — 어느 출처에서 먼저 찾았는지를 그대로 보여준다.
    """
    for field in (
        "address",
        "jibun_address",
        "phone",
        "latitude",
        "longitude",
        "category",
        "distance_m",
        "kakao_place_id",
    ):
        if getattr(base, field) is None and getattr(other, field) is not None:
            setattr(base, field, getattr(other, field))
    if not base.external_channel_url and other.external_channel_url:
        base.external_channel_url = other.external_channel_url


def merge_duplicates(results: list[StoreSearchResult]) -> list[StoreSearchResult]:
    """동일 가게 후보를 하나로 합친다. 입력 순서를 유지한다."""
    merged: list[StoreSearchResult] = []
    for candidate in results:
        for existing in merged:
            if _is_same_place(existing, candidate):
                _merge_into(existing, candidate)
                break
        else:
            merged.append(candidate)
    return merged


async def search_stores(
    keyword: str,
    latitude: Decimal | None = None,
    longitude: Decimal | None = None,
) -> list[StoreSearchResult]:
    """키워드로 두 출처를 동시에 검색하고 중복을 병합해 돌려준다."""
    timeout = httpx.Timeout(settings.EXTERNAL_API_TIMEOUT_SECONDS)

    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = []
        sources = []
        if settings.naver_search_enabled:
            tasks.append(_fetch_naver(client, keyword))
            sources.append(SearchSource.NAVER)
        if settings.kakao_search_enabled:
            tasks.append(_fetch_kakao(client, keyword, latitude, longitude))
            sources.append(SearchSource.KAKAO)

        if not tasks:
            logger.warning("장소 검색 API 키가 하나도 설정되지 않아 빈 결과를 반환합니다.")
            return []

        settled = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[StoreSearchResult] = []
    for source, outcome in zip(sources, settled, strict=True):
        if isinstance(outcome, BaseException):
            # 한 출처가 죽어도 나머지 결과는 그대로 내려준다
            logger.warning("%s 장소 검색 실패: %s", source.value, outcome)
            continue
        results.extend(outcome)

    return merge_duplicates(results)
