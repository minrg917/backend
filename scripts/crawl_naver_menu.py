"""네이버 플레이스에서 대표 메뉴 몇 개를 가져오는 크롤링 스크립트 (BM 데모용).

    pip install selenium webdriver-manager
    poetry run python -m scripts.crawl_naver_menu "가게이름 지역명" [--limit 5]

**독립 스크립트다 — API 서버(`app/`)에는 포함하지 않는다.**

- 헤드리스 크롬이 필요해 무겁다. 운영 서버(t3.small, 2GB)에 물리면 API 프로세스가
  메모리 부족으로 죽을 수 있다.
- 네이버가 자동화 요청을 능동적으로 차단하는 걸 확인했다(2026-08-24) — 첫 요청부터
  429가 나기도 하고, 셀레니움으로 접근하면 캡차(사람 확인)가 뜨기도 한다.
  API 요청 경로에 두면 안 된다.
- 페이지 구조가 자주 바뀌는 비공식 크롤링이다.

**의존성을 `pyproject.toml`에 넣지 않았다.** 운영 배포와 무관한 일회성 도구다.

## ⚠️ 캡차는 이 스크립트로 풀 수 없다

네이버가 자동화를 의심하면 "보안 확인" 캡차를 띄운다(2026-08-24 실제 확인).
**이건 코드로 우회하지 않는다** — 세션이 그 상태로 막히면 스크립트는 실패로
끝나고, 브라우저를 직접 열어 사람이 풀어야 한다. 재시도 간격을 두고 다시
돌리면 캡차 없이 지나갈 때도 있다.

## 흐름 (2026-08-24 기준, 현재 네이버 지도 UI)

1. `map.naver.com/p/search/{검색어}` 로 검색
2. **검색어가 구체적이면(예: "행복분식 강남점") 결과가 하나로 바로 특정되어
   목록 없이 상세로 직행**하고, 모호하면(예: "스타벅스") 목록이 뜬다. 둘 다
   처리한다 — 먼저 상세(`entryIframe`)가 바로 뜨는지 짧게 확인하고, 없으면
   목록(`searchIframe`)에서 첫 결과를 클릭한다.
3. 상세 화면에 들어가면 기본 탭은 "홈"이다. **"메뉴" 탭을 직접 클릭**해야
   메뉴가 렌더링된다.
4. 메뉴 항목을 선택자로 찾는다. **이 선택자는 아직 확정 못 했다** — 캡차
   때문에 실제 메뉴 화면을 못 봤다. `_MENU_ITEM_SELECTOR`를 개발자 도구로
   확인해 채워야 한다(아래 안내 참고).

클래스명은 네이버가 빌드할 때마다 바뀌는 해시값이라 언제든 다시 깨질 수 있다.
"""

import argparse
import re
import sys
import time
from dataclasses import dataclass

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# 메뉴 "이름" 요소의 선택자 (2026-08-24 실제 확인: class="MenuContent__tit__OEjdC").
# 네이버는 CSS Modules를 써서 클래스명이 "컴포넌트명__역할__해시" 구조다.
# 해시(OEjdC)는 배포마다 바뀌지만 앞부분(MenuContent__tit)은 코드 구조가 안 바뀌는 한
# 유지되므로, 정확히 일치가 아니라 부분 일치(*=)로 잡아 해시 변경에 버티게 한다.
_MENU_ITEM_SELECTOR = '[class*="MenuContent__tit"]'
# 이름 요소에서 몇 단계까지 올라가며 가격을 찾을지. 가격 클래스명을 정확히 몰라도
# "이름을 감싸는 카드 어딘가에 가격 텍스트가 있다"는 가정으로 우회한다.
_PRICE_SEARCH_ANCESTOR_LEVELS = 4

_PRICE_RE = re.compile(r"([\d,]+)\s*원")
_NOISE_KEYWORDS = ("사진", "리뷰", "평점", "더보기", "펼쳐보기", "메뉴판", "이미지수")


@dataclass(frozen=True)
class MenuItem:
    name: str
    price: int | None


def _build_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,2000")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def _switch_to(driver: webdriver.Chrome, frame_id: str, timeout: int = 10) -> None:
    driver.switch_to.default_content()
    WebDriverWait(driver, timeout).until(
        EC.frame_to_be_available_and_switch_to_it((By.ID, frame_id))
    )


def _enter_detail(driver: webdriver.Chrome) -> None:
    """상세 화면(entryIframe)까지 들어간다.

    구체적인 검색어는 목록 없이 바로 상세로 연결되고, 모호한 검색어는 목록이
    뜬다. entryIframe이 바로 있는지 짧게 확인해보고, 없으면 목록에서 첫
    결과를 클릭하는 경로로 넘어간다.
    """
    try:
        _switch_to(driver, "entryIframe", timeout=4)
        return  # 이미 상세 화면이다
    except TimeoutException:
        pass

    _switch_to(driver, "searchIframe")
    container = driver.find_element(By.XPATH, '//*[@id="_pcmap_list_scroll_container"]/ul')
    links = container.find_elements(By.TAG_NAME, "a")
    if not links:
        raise RuntimeError("검색 결과가 없습니다.")
    target = links[1] if ("이미지수" in links[0].text or links[0].text == "") else links[0]
    target.send_keys(Keys.ENTER)
    time.sleep(2)

    _switch_to(driver, "entryIframe")


def _click_menu_tab(driver: webdriver.Chrome) -> None:
    """상세 화면 기본 탭은 "홈"이다. "메뉴" 탭을 눌러야 메뉴가 렌더링된다."""
    try:
        tab = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, '//a[contains(text(), "메뉴")]'))
        )
        tab.click()
        time.sleep(2)
    except TimeoutException:
        # 메뉴 탭이 아예 없는 가게(메뉴 미등록)일 수 있다 — 호출부에서 빈 결과로 처리된다.
        pass


def _debug_failure(driver: webdriver.Chrome, message: str) -> RuntimeError:
    """실패한 순간의 화면을 파일로 남긴다. 캡차·구조 변경 여부를 나중에 확인하기 위함."""
    try:
        driver.switch_to.default_content()
        driver.save_screenshot("naver_crawl_debug.png")
        with open("naver_crawl_debug.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        with open("naver_crawl_debug_iframes.txt", "w", encoding="utf-8") as f:
            for frame in frames:
                f.write(f"id={frame.get_attribute('id')!r} name={frame.get_attribute('name')!r}\n")
        hint = " (naver_crawl_debug.png / .html / _iframes.txt 확인)"
    except Exception:
        hint = " (디버그 파일 저장도 실패했습니다)"
    return RuntimeError(message + hint)


def _find_nearby_price(name_element) -> int | None:
    """이름 요소에서 부모로 올라가며 가격처럼 생긴 텍스트를 찾는다.

    가격 요소의 정확한 클래스명은 모르지만, "이름을 감싸는 카드 어딘가에는
    가격이 있다"는 가정은 안전하다. 너무 위로 올라가면 옆 메뉴의 가격까지
    섞여 들어와서 단계를 제한한다.
    """
    node = name_element
    for _ in range(_PRICE_SEARCH_ANCESTOR_LEVELS):
        try:
            node = node.find_element(By.XPATH, "..")
        except NoSuchElementException:
            return None
        match = _PRICE_RE.search(node.text)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def _parse_menu_text(raw: str, limit: int) -> list[MenuItem]:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    items: list[MenuItem] = []
    seen: set[str] = set()
    i = 0
    while i < len(lines) and len(items) < limit:
        line = lines[i]
        if any(noise in line for noise in _NOISE_KEYWORDS) or _PRICE_RE.fullmatch(line):
            i += 1
            continue

        name = _PRICE_RE.sub("", line).strip()
        price = None
        if i + 1 < len(lines):
            price_match = _PRICE_RE.search(lines[i + 1])
            if price_match:
                price = int(price_match.group(1).replace(",", ""))
                i += 1

        if name and name not in seen:
            seen.add(name)
            items.append(MenuItem(name=name, price=price))
        i += 1

    return items


def fetch_menu(query: str, limit: int = 5) -> list[MenuItem]:
    driver = _build_driver()
    try:
        driver.get(f"https://map.naver.com/p/search/{query}")
        time.sleep(3)

        if "이용이 제한" in driver.page_source:
            raise RuntimeError("네이버가 요청을 차단했습니다(429). 잠시 후 다시 시도하세요.")

        try:
            _enter_detail(driver)
        except (TimeoutException, NoSuchElementException) as error:
            raise _debug_failure(driver, "상세 화면에 들어가지 못했습니다.") from error

        _click_menu_tab(driver)

        name_elements = driver.find_elements(By.CSS_SELECTOR, _MENU_ITEM_SELECTOR)
        if not name_elements:
            raise _debug_failure(driver, "메뉴 항목을 찾지 못했습니다.")

        items: list[MenuItem] = []
        seen: set[str] = set()
        for element in name_elements:
            name = element.text.strip()
            if not name or name in seen or any(noise in name for noise in _NOISE_KEYWORDS):
                continue
            seen.add(name)
            items.append(MenuItem(name=name, price=_find_nearby_price(element)))
            if len(items) >= limit:
                break

        return items
    finally:
        driver.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description="네이버 플레이스 대표 메뉴 크롤링(BM 데모용)")
    parser.add_argument("query", help='검색어. 예: "행복분식 강남점"')
    parser.add_argument("--limit", type=int, default=5, help="가져올 메뉴 개수 (기본 5)")
    args = parser.parse_args()

    try:
        items = fetch_menu(args.query, args.limit)
    except RuntimeError as error:
        print(f"실패: {error}", file=sys.stderr)
        sys.exit(1)

    if not items:
        print("메뉴를 찾지 못했습니다.")
        return

    for item in items:
        price = f"{item.price:,}원" if item.price else "가격 미상"
        print(f"- {item.name}  ({price})")


if __name__ == "__main__":
    main()
