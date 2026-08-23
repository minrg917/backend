"""모델에서 공용으로 쓰는 컬럼 타입."""

from sqlalchemy import BigInteger, Integer

# ERD의 PK/FK는 전부 BIGINT다. 다만 SQLite는 `INTEGER PRIMARY KEY`일 때만
# 자동증가가 동작하므로, 테스트용 SQLite에서는 INTEGER로 대체한다.
BigInt = BigInteger().with_variant(Integer, "sqlite")
