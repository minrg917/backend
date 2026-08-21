"""예외를 공통 에러 응답 포맷으로 변환하는 핸들러.

FastAPI가 기본으로 뱉는 `{"detail": ...}` 포맷을 쓰지 않고, API명세서
「공통 사항」의 `{"error_code": ..., "message": ...}` 포맷으로 통일한다.
`app/main.py`에서 `register_error_handlers(app)`으로 등록한다.
"""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

# FastAPI/Starlette가 직접 던지는 HTTPException(404, 405 등)에 붙일 기본 error_code.
# 여기 없는 상태코드는 HTTP 상태명(예: 418 → I_AM_A_TEAPOT)을 그대로 쓴다.
_DEFAULT_ERROR_CODES: dict[int, str] = {
    HTTPStatus.BAD_REQUEST: "BAD_REQUEST",
    HTTPStatus.UNAUTHORIZED: "UNAUTHORIZED",
    HTTPStatus.FORBIDDEN: "FORBIDDEN",
    HTTPStatus.NOT_FOUND: "NOT_FOUND",
    HTTPStatus.METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
    HTTPStatus.CONFLICT: "CONFLICT",
    HTTPStatus.UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
    HTTPStatus.INTERNAL_SERVER_ERROR: "INTERNAL_ERROR",
}

# Starlette가 던지는 HTTPException의 detail은 영문 표준 문구("Not Found" 등)라서,
# 그대로 두면 응답 메시지만 영어가 된다. 기본 문구인 경우에만 한국어로 바꾼다.
_DEFAULT_MESSAGES: dict[int, str] = {
    HTTPStatus.BAD_REQUEST: "잘못된 요청입니다.",
    HTTPStatus.UNAUTHORIZED: "인증이 필요합니다.",
    HTTPStatus.FORBIDDEN: "접근 권한이 없습니다.",
    HTTPStatus.NOT_FOUND: "요청한 경로를 찾을 수 없습니다.",
    HTTPStatus.METHOD_NOT_ALLOWED: "지원하지 않는 HTTP 메서드입니다.",
    HTTPStatus.INTERNAL_SERVER_ERROR: "서버 오류가 발생했습니다.",
}


def error_response(status_code: int, error_code: str, message: str) -> JSONResponse:
    """공통 에러 포맷 응답을 만든다."""
    return JSONResponse(
        status_code=status_code,
        content={"error_code": error_code, "message": message},
    )


def _default_error_code(status_code: int) -> str:
    if status_code in _DEFAULT_ERROR_CODES:
        return _DEFAULT_ERROR_CODES[status_code]
    try:
        return HTTPStatus(status_code).name
    except ValueError:
        return "ERROR"


def _localized_message(status_code: int, detail: object) -> str:
    """detail이 Starlette 기본 문구면 한국어 메시지로 바꾼다."""
    message = detail if isinstance(detail, str) else str(detail)
    try:
        is_default = message == HTTPStatus(status_code).phrase
    except ValueError:
        is_default = False
    if is_default and status_code in _DEFAULT_MESSAGES:
        return _DEFAULT_MESSAGES[status_code]
    return message


def _format_validation_message(exc: RequestValidationError) -> str:
    """Pydantic 검증 에러를 사람이 읽을 수 있는 한 줄로 만든다.

    프론트가 어느 필드가 문제인지 알아야 하므로 필드 경로를 함께 담는다.
    """
    parts: list[str] = []
    for error in exc.errors():
        # loc 예: ("body", "email") → "email" / ("query", "page") → "page"
        location = ".".join(str(item) for item in error["loc"][1:]) or str(error["loc"][0])
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts) or "요청 형식이 올바르지 않습니다."


def register_error_handlers(app: FastAPI) -> None:
    """앱에 공통 예외 핸들러를 등록한다."""

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.error_code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(
            exc.status_code,
            _default_error_code(exc.status_code),
            _localized_message(exc.status_code, exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            _format_validation_message(exc),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # 예상 못 한 예외는 내부 정보를 응답에 노출하지 않고 로그로만 남긴다.
        logger.exception("처리되지 않은 예외: %s %s", request.method, request.url.path)
        return error_response(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "서버 오류가 발생했습니다.",
        )
