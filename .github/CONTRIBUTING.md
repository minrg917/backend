# CONTRIBUTING

사릴스 백엔드 레포에 기여할 때 지키는 브랜치·커밋·이슈·PR 규칙입니다. Claude Code를 포함한 모든 작업자는 이 규칙을 따릅니다.

## 1. 브랜치 전략

- `main`: 배포 가능한 안정 브랜치. 직접 push 금지, PR로만 merge.
- `develop`: 개발 통합 브랜치. 모든 기능/수정이 먼저 여기로 모인다. 직접 push 금지, PR로만 merge.
- `feature/{이슈번호}-{작업내용}`: 기능 개발 브랜치. `develop`에서 분기 → 완료 후 `develop`으로 PR.
  - 예: `feature/12-login-api`, `feature/15-signup-page`
- `fix/{이슈번호}-{작업내용}`: 버그 수정 브랜치. `develop`에서 분기 → 완료 후 `develop`으로 PR.
  - 예: `fix/20-cors-error`

**Merge 규칙**

- `feature/fix → develop`: PR 필수, 팀원 1명 이상 리뷰 승인 후 merge.
- `develop → main`: 일정 단위(주기적/기능 묶음 단위)로 병합, 배포 시점에 진행.
- Merge 방식은 **Squash and merge** 사용(여러 커밋을 하나로 합쳐서 `main` 히스토리를 깔끔하게 유지).
- merge 완료된 브랜치는 삭제한다.

## 2. 커밋 메시지 규칙

형식: `타입: 설명`

| 타입 | 설명 |
| --- | --- |
| feat | 기능 추가 |
| fix | 버그 수정 |
| docs | 문서 수정 |
| style | 코드 포맷팅, 세미콜론 등 (로직 변경 없음) |
| refactor | 리팩토링 |
| test | 테스트 코드 추가/수정 |
| chore | 빌드, 설정, 패키지 매니저 등 |

- 이슈 번호가 있으면 끝에 `(#이슈번호)`를 붙인다.
- 제목은 50자 이내, 명령형으로 작성한다.
- 예시:
  - `feat: 로그인 API 구현 (#12)`
  - `fix: CORS 에러 수정 (#20)`
  - `chore: FastAPI 초기 프로젝트 세팅`

## 3. 이슈

템플릿: `.github/ISSUE_TEMPLATE.md` (기능 설명 / 작업 내용 / 완료 조건)

사용법:

1. Issues 탭 → New issue → 작업 단위로 등록한다(번호는 자동 부여됨).
2. 그 번호로 브랜치명을 짓는다(예: `feature/12-login-api`).
3. PR 만들 때 설명에 `Closes #12`를 작성한다 → merge 시 이슈가 자동으로 종료된다.

GitHub에 바로 올리기 전에 초안이 필요하면 팀 내부에서 관리하는 이슈 초안 문서에 먼저 정리해두고, 실제로 이슈를 등록한 뒤에는 그 초안을 지운다. (초안 문서는 레포에 포함되지 않는다.)

## 4. PR

템플릿: `.github/PULL_REQUEST_TEMPLATE.md` (작업 내용 / 관련 이슈 / 체크리스트) — PR을 만들면 자동으로 채워진다.
