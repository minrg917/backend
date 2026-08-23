"""애플리케이션 공통 예외.

API명세서 「공통 사항」의 에러 응답 포맷을 따른다.

```json
{"error_code": "STORE_NOT_FOUND", "message": "가게 정보를 찾을 수 없습니다."}
```

각 도메인은 아래 상태코드별 베이스 클래스를 상속해서 `error_code`/`message`만
바꾼 예외를 정의한다. 라우터에서는 이 예외를 그대로 raise 하면 되고,
JSON 응답으로 바꾸는 일은 `app.core.error_handlers`가 맡는다.

```python
class StoreNotFound(NotFoundError):
    error_code = "STORE_NOT_FOUND"
    message = "가게 정보를 찾을 수 없습니다."
```
"""

from http import HTTPStatus
from typing import Any


class AppError(Exception):
    """공통 에러 포맷으로 응답되는 모든 예외의 부모."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"
    message: str = "서버 오류가 발생했습니다."

    def __init__(
        self,
        message: str | None = None,
        *,
        error_code: str | None = None,
        status_code: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if message is not None:
            self.message = message
        if error_code is not None:
            self.error_code = error_code
        if status_code is not None:
            self.status_code = status_code
        # 일부 에러는 공통 두 필드만으로 부족하다 — 예: 14.1의 `incomplete_tasks`는
        # "어떤 태스크가 비었는지"를 알려줘야 프론트가 태스크 보드로 안내할 수 있다.
        # 여기 담긴 값은 응답 본문에 그대로 병합된다.
        self.extra: dict[str, Any] = extra or {}
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = HTTPStatus.BAD_REQUEST
    error_code = "BAD_REQUEST"
    message = "잘못된 요청입니다."


class UnauthorizedError(AppError):
    """인증 실패(토큰 없음/만료/위조)."""

    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "UNAUTHORIZED"
    message = "인증이 필요합니다."


class ForbiddenError(AppError):
    """인증은 됐지만 권한이 없음(예: 남의 가게 리소스 접근)."""

    status_code = HTTPStatus.FORBIDDEN
    error_code = "FORBIDDEN"
    message = "접근 권한이 없습니다."


class NotFoundError(AppError):
    status_code = HTTPStatus.NOT_FOUND
    error_code = "NOT_FOUND"
    message = "요청한 리소스를 찾을 수 없습니다."


class ConflictError(AppError):
    """이미 존재하는 리소스(예: 이메일 중복)."""

    status_code = HTTPStatus.CONFLICT
    error_code = "CONFLICT"
    message = "이미 존재하는 리소스입니다."


class UnprocessableEntityError(AppError):
    """형식은 맞지만 비즈니스 규칙상 처리할 수 없는 요청."""

    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    error_code = "UNPROCESSABLE_ENTITY"
    message = "요청을 처리할 수 없습니다."
