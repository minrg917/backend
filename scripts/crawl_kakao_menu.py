"""카카오맵에서 대표 메뉴 몇 개를 가져오는 크롤링 스크립트 (BM 데모용).

    pip install selenium webdriver-manager
    poetry run python -m scripts.crawl_kakao_menu <카카오 place ID 또는 place_url> [--limit 5]

**독립 스크립트다 — API 서버(`app/`)에는 포함하지 않는다.** 이유는
`crawl_naver_menu.py`와 같다(무거움 · 비공식 · 불안정 · 캡차 가능성).

## 네이버와의 차이 (2026-08-24 확인)

- **첫 요청에 즉시 차단되지 않았다.** 단순 요청(curl)으로 200이 돌아왔다 —
  네이버는 같은 조건에서 즉시 429였다. 다만 이건 단순 요청 기준이고,
  셀레니움으로 실제 접근했을 때도 안 막힌다는 보장은 아니다.
- **iframe이 없다.** `https://place.map.kakao.com/{ID}`가 Vue 기반 단일 페이지
  앱이라(`<div id="app"></div>` 뿐이고 나머지는 JS가 그린다), 네이버처럼
  searchIframe/entryIframe을 오갈 필요가 없다. 구조가 더 단순하다.
- **place ID는 카카오 로컬 API로 미리 구할 수 있다** — `store_search.py`가 쓰는
  키워드 검색 API 응답의 `place_url`(`http://place.map.kakao.com/{ID}`)이 그대로
  이 스크립트의 입력이다. 검색·클릭 단계 자체가 필요 없다.

## ⚠️ 메뉴 선택자는 아직 모른다

실제로 렌더링된 화면을 본 적이 없어 `_MENU_ITEM_SELECTOR`가 placeholder다.
채우는 법은 `crawl_naver_menu.py`와 동일: 메뉴 화면에서 F12 → 메뉴 이름
우클릭 → 검사 → class 확인.

## ⚠️ 캡차가 뜨면 이 스크립트로 풀 수 없다

네이버와 같은 원칙이다 — 캡차는 코드로 우회하지 않는다. 뜨면 실패로 끝나고,
사람이 직접 확인해야 한다.
"""

import argparse
import json
import re
import sys
import time

from dataclasses import dataclass

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# 메뉴 이름/가격 선택자 (2026-08-24 실제 확인).
# <strong class="tit_item">브루드 커피</strong> / <p class="desc_item">4,500원</p>
# 가 짝을 이뤄 나온다. 네이버와 달리 해시가 아닌 읽을 수 있는 클래스명이라
# 배포가 바뀌어도 상대적으로 오래갈 가능성이 높다.
_MENU_NAME_SELECTOR = "strong.tit_item"
_MENU_PRICE_SELECTOR = "p.desc_item"

_PRICE_RE = re.compile(r"([\d,]+)\s*원")
_NOISE_KEYWORDS = ("사진", "리뷰", "평점", "더보기", "펼쳐보기", "메뉴판")


@dataclass(frozen=True)
class MenuItem:
    name: str
    price: int | None


def _place_id_from(value: str) -> str:
    match = re.search(r"place[./](?:map\.kakao\.com/)?(\d+)", value)
    return match.group(1) if match else value


def _build_driver() -> webdriver.Chrome:
    options = Options()
    #options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,2000")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def _click_menu_tab(driver: webdriver.Chrome) -> None:
    try:
        tab = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, '//*[contains(text(), "메뉴")]'))
        )
        tab.click()
        time.sleep(2)
    except TimeoutException:
        pass  # 메뉴 탭이 없는 가게(메뉴 미등록)일 수 있다.


def _debug_failure(driver: webdriver.Chrome, message: str) -> RuntimeError:
    try:
        driver.save_screenshot("kakao_crawl_debug.png")
        with open("kakao_crawl_debug.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        hint = " (kakao_crawl_debug.png / .html 확인)"
    except Exception:
        hint = " (디버그 파일 저장도 실패했습니다)"
    return RuntimeError(message + hint)


def fetch_menu(place_id_or_url: str, limit: int = 5) -> list[MenuItem]:
    place_id = _place_id_from(place_id_or_url)
    url = f"https://place.map.kakao.com/{place_id}"

    driver = _build_driver()
    try:
        driver.get(url)
        time.sleep(3)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "app"))
            )
        except TimeoutException as error:
            raise _debug_failure(driver, "페이지가 로드되지 않았습니다.") from error

        _click_menu_tab(driver)

        name_elements = driver.find_elements(By.CSS_SELECTOR, _MENU_NAME_SELECTOR)
        price_elements = driver.find_elements(By.CSS_SELECTOR, _MENU_PRICE_SELECTOR)
        if not name_elements:
            raise _debug_failure(driver, "메뉴 항목을 찾지 못했습니다.")

        # 이름과 가격이 문서 순서대로 1:1 대응한다고 가정한다. 개수가 안 맞으면
        # (다른 섹션의 tit_item/desc_item이 섞여 들어온 경우) 가격 없이 이름만 쓴다.
        paired = len(name_elements) == len(price_elements)

        items: list[MenuItem] = []
        seen: set[str] = set()
        for i, element in enumerate(name_elements):
            name = element.text.strip()
            if not name or name in seen or any(noise in name for noise in _NOISE_KEYWORDS):
                continue
            seen.add(name)

            price = None
            if paired:
                price_match = _PRICE_RE.search(price_elements[i].text)
                if price_match:
                    price = int(price_match.group(1).replace(",", ""))

            items.append(MenuItem(name=name, price=price))
            if len(items) >= limit:
                break

        return items
    finally:
        driver.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description="카카오맵 대표 메뉴 크롤링(BM 데모용)")
    parser.add_argument("place", help="카카오 place ID 또는 place_url")
    parser.add_argument("--limit", type=int, default=5, help="가져올 메뉴 개수 (기본 5)")
    parser.add_argument(
        "--json", action="store_true", help="사람이 읽는 출력 대신 JSON 배열을 stdout에 낸다"
    )
    args = parser.parse_args()

    try:
        items = fetch_menu(args.place, args.limit)
    except RuntimeError as error:
        if args.json:
            # 실패해도 stdout은 항상 유효한 JSON이어야 한다 — 호출부(백그라운드 작업)가
            # stderr까지 따로 다루지 않고 stdout 파싱 결과만으로 성공/실패를 가른다.
            print("[]")
            print(f"실패: {error}", file=sys.stderr)
            sys.exit(1)
        print(f"실패: {error}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps([{"name": i.name, "price": i.price} for i in items], ensure_ascii=False))
        return

    if not items:
        print("메뉴를 찾지 못했습니다.")
        return

    for item in items:
        price = f"{item.price:,}원" if item.price else "가격 미상"
        print(f"- {item.name}  ({price})")


if __name__ == "__main__":
    main()
