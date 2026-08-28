"""썸네일 추출 공통 로직 테스트 (R14 완성 영상 커버 / 9.2 촬영본 썸네일이 공유)."""

from pathlib import Path

import pytest

from app.services import media_thumbnail

MP4_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32


def test_generate_thumbnail_uses_representative_frame_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "result.mp4"
    source.write_bytes(MP4_BYTES)
    saved: dict[str, bytes] = {}
    captured: list[str] = []

    class FakeStorage:
        def save(self, key, stream, content_type=None):
            assert content_type == "image/jpeg"
            saved[key] = stream.read()
            return key

    def fake_run(command, **kwargs):
        del kwargs
        captured.extend(command)
        Path(command[-1]).write_bytes(b"jpeg")

    monkeypatch.setattr(media_thumbnail.subprocess, "run", fake_run)

    key = media_thumbnail.generate_thumbnail(FakeStorage(), source, "outputs/result.jpg")

    assert key == "outputs/result.jpg"
    assert "thumbnail=30,scale=720:-2" in captured
    assert saved[key] == b"jpeg"


def test_generate_thumbnail_returns_none_on_ffmpeg_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ffmpeg 실패는 부가 기능 실패일 뿐이라 예외를 던지지 않고 null만 돌려준다."""
    source = tmp_path / "result.mp4"
    source.write_bytes(MP4_BYTES)

    class FakeStorage:
        def save(self, key, stream, content_type=None):
            raise AssertionError("ffmpeg가 실패하면 저장을 시도하면 안 된다")

    def fake_run(command, **kwargs):
        del command, kwargs
        raise FileNotFoundError("ffmpeg not found")

    monkeypatch.setattr(media_thumbnail.subprocess, "run", fake_run)

    assert media_thumbnail.generate_thumbnail(FakeStorage(), source, "outputs/x.jpg") is None
