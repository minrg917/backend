"""로컬 영상 파일에서 대표 프레임을 뽑아 썸네일로 저장한다.

R14 최종 영상 커버(`video_edit.py`)와 9.2 촬영본 썸네일(`footage.py`)이 같은
방식(ffmpeg로 프레임 한 장 추출 후 저장)을 쓴다 — 로직을 한 곳에 모아 추출
방식이 바뀌면 여기만 고치면 된다.
"""

import logging
import subprocess
from pathlib import Path

from app.core.config import settings
from app.storage import Storage, StorageError

logger = logging.getLogger(__name__)


def generate_thumbnail(storage: Storage, source_path: Path, thumbnail_key: str) -> str | None:
    """`source_path`(로컬 영상 파일)에서 대표 프레임 한 장을 뽑아 저장한다.

    **실패해도 예외를 던지지 않고 `None`을 돌려준다** — 썸네일은 부가 기능이라
    ffmpeg 실패(코덱 미지원 등)로 업로드·렌더 자체를 막을 이유가 없다.
    """
    thumbnail_path = source_path.with_suffix(".jpg")
    try:
        subprocess.run(
            [
                settings.FFMPEG_PATH,
                "-y",
                "-i",
                str(source_path),
                "-frames:v",
                "1",
                "-vf",
                "thumbnail=30,scale=720:-2",
                str(thumbnail_path),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        with thumbnail_path.open("rb") as stream:
            storage.save(thumbnail_key, stream, "image/jpeg")
        return thumbnail_key
    except (OSError, subprocess.SubprocessError, StorageError):
        logger.warning("썸네일 생성 실패", exc_info=True)
        return None
    finally:
        thumbnail_path.unlink(missing_ok=True)
