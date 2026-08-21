# 사릴스(SARILS) — Backend

FLY AI 열정 2조. 소상공인이 AI의 도움을 받아 숏폼(릴스/쇼츠) 영상을 **기획 → 촬영 → 편집 → 게시**까지 혼자 끝낼 수 있게 해주는 서비스의 백엔드 레포지토리입니다.

## 기술 스택

| 구분 | 사용 기술 |
| --- | --- |
| 언어 | Python 3.12 |
| 프레임워크 | FastAPI |
| ORM | SQLAlchemy 2.0 (동기) |
| DB | MySQL 8 (로컬은 Docker) |
| 마이그레이션 | Alembic |
| 의존성 관리 | Poetry |
| 린트·포맷 | Ruff |

## 로컬 실행

> 초기 프로젝트 세팅 이후 작성 예정입니다.

## 문서

스펙 문서(기능명세서 · API 명세서 · ERD)는 **이 레포에 포함되어 있지 않습니다.** 팀 내부 채널과 Notion에서 공유합니다.

| 문서 | 위치 |
| --- | --- |
| API 명세서 | Notion **📍 API Spec** DB |
| 기능명세서 · ERD · 결정 기록 | 팀 내부 공유 (레포 미포함) |

작업 전에 해당 문서에서 요구사항(R번호)과 ERD 컬럼명을 먼저 확인해주세요. **API의 Body/Response 필드명은 ERD 컬럼명을 그대로 사용합니다.**

## 기여 방법

브랜치 전략·커밋 규칙·이슈/PR 흐름은 [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md)를 따릅니다.

```
이슈 등록 → feature/{이슈번호}-{작업내용} 브랜치 → 작업 → develop으로 PR → 리뷰 1명 승인 → Squash merge
```

`main`과 `develop`은 직접 push가 금지되어 있습니다.
