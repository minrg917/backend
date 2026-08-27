"""SNS 게시물 성과 지표를 수집한다.

    poetry run python -m scripts.collect_sns_metrics

`deploy/sarils-metrics-collect.timer`가 하루 한 번 돌리는 배치다. 연결 확정
(16.3)된 게시물이 없으면 아무 일도 하지 않는다.
"""

from app.db.session import SessionLocal
from app.services.metrics_collector import collect_all


def main() -> None:
    with SessionLocal() as db:
        checked, collected = collect_all(db)
    print(f"성과 지표 수집 완료 — 확인 {checked}건, 수집 {collected}건")


if __name__ == "__main__":
    main()
