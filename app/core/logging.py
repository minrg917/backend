"""요청 로깅.

**지금까지는 예외가 터졌을 때만 로그가 남았다.** 정상 요청은 아무 기록이 없어서
배포 후 "이 API가 느린가", "사장님이 어디서 막혔나"를 확인할 방법이 없다.

로그는 나중에 소급해서 만들 수 없다 — 배포 시점에 이미 있어야 한다.
"""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.core.config import settings

logger = logging.getLogger("sarils.request")

# 헬스체크는 로드밸런서·docker healthcheck가 주기적으로 때린다. INFO로 남기면
# 실제 사용자 요청이 그 사이에 묻힌다.
_QUIET_PATHS = frozenset({"/health"})


def configure_logging() -> None:
    """루트 로거에 핸들러를 붙인다.

    설정이 없으면 파이썬 기본 동작(WARNING 이상만, lastResort 핸들러)이라
    INFO 로그가 아예 나오지 않는다.
    """
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        # 컨테이너 로그는 시각을 직접 넣어야 한다 — docker logs는 붙여주지 않는다.
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        force=True,  # uvicorn이 먼저 잡아둔 설정을 덮어쓴다
    )


def _level_for(status_code: int) -> int:
    """상태코드로 로그 레벨을 정한다.

    5xx는 우리 잘못이라 ERROR, 4xx는 잘못된 요청이라 WARNING이다. 4xx를 ERROR로
    두면 로그인 실패 같은 정상적인 흐름이 에러 알림을 울리게 된다.
    """
    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO


def register_request_logging(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_requests(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # 한 요청에서 나온 로그를 묶어 보기 위한 짧은 식별자. 응답 Body에는 넣지
        # 않는다(공통 에러 포맷을 바꾸지 않기로 함) — 헤더로만 내보낸다.
        request_id = uuid.uuid4().hex[:8]
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            # 예외 핸들러가 잡지 못한 경우다. 여기서 남기지 않으면 요청 흔적이 사라진다.
            logger.exception(
                "%s %s %s -> EXC %.0fms", request_id, request.method, request.url.path, elapsed_ms
            )
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        level = (
            logging.DEBUG if request.url.path in _QUIET_PATHS else _level_for(response.status_code)
        )
        # 쿼리스트링은 남기지 않는다 — 검색어에 개인정보가 섞여 들어올 수 있고,
        # 경로만으로도 어느 API가 느린지는 충분히 드러난다.
        logger.log(
            level,
            "%s %s %s -> %d %.0fms",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response
