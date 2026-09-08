# -*- coding: utf-8 -*-
"""녹취서 출력 모듈(render.py, write.py) 단위 테스트."""

import os
import tempfile
import unittest.mock as mock
from pathlib import Path

import pytest

from src.output.render import (
    SEPARATOR,
    TranscriptMetadata,
    TranscriptSegment,
    format_duration,
    format_timestamp,
    render_transcript,
)
from src.output.write import (
    clean_temp_file,
    get_output_path,
    write_transcript,
)


class TestRenderModule:
    """render.py 모듈 테스트 클래스."""

    def test_format_duration(self):
        """시간(초)이 HH:MM:SS 형식으로 올바르게 변환되는지 테스트."""
        assert format_duration(0) == "00:00:00"
        assert format_duration(5) == "00:00:05"
        assert format_duration(65) == "00:01:05"
        assert format_duration(754) == "00:12:34"
        assert format_duration(3661) == "01:01:01"
        assert format_duration(3600 * 25 + 120 + 3) == "25:02:03"
        assert format_duration(-10) == "00:00:00"

    def test_format_timestamp(self):
        """시간(초)이 [HH:MM:SS] 형식으로 올바르게 변환되는지 테스트."""
        assert format_timestamp(0) == "[00:00:00]"
        assert format_timestamp(1) == "[00:00:01]"
        assert format_timestamp(754) == "[00:12:34]"
        assert format_timestamp(3661.7) == "[01:01:01]"
        assert format_timestamp(-5) == "[00:00:00]"

    def test_separator_line(self):
        """구분선이 U+2500 문자 32개로 구성되어 있는지 테스트."""
        assert len(SEPARATOR) == 32
        assert all(ch == "─" for ch in SEPARATOR)
        assert ord(SEPARATOR[0]) == 0x2500

    def test_render_transcript_with_dataclass(self):
        """dataclass 형태의 메타데이터와 세그먼트로 녹취서 렌더링 테스트."""
        meta = TranscriptMetadata(
            original_filename="상담_20260908.m4a",
            original_path=r"D:\사건\김OO\상담_20260908.m4a",
            created_at="2026-09-08 20:45:12",
            total_duration=754,
            language="ko",
            speaker_count=2,
            engine_info="faster-whisper large-v3 + pyannote",
        )
        segments = [
            TranscriptSegment(
                start=1.0,
                end=4.5,
                speaker="화자1",
                text="안녕하세요. 오늘 상담 내용 녹음해도 될까요?",
            ),
            TranscriptSegment(
                start=5.0,
                end=8.0,
                speaker="화자2",
                text="네, 괜찮습니다.",
            ),
            TranscriptSegment(
                start=9.0,
                end=12.0,
                speaker="화자1",
                text="그럼 사실관계부터 정리하겠습니다.",
            ),
        ]

        result = render_transcript(segments, meta)

        expected_header = (
            "【녹취서】\n\n"
            "■ 원본파일: 상담_20260908.m4a\n"
            r"■ 원본경로: D:\사건\김OO\상담_20260908.m4a" + "\n"
            "■ 작성일시: 2026-09-08 20:45:12\n"
            "■ 총길이: 00:12:34\n"
            "■ 언어: ko\n"
            "■ 화자 수: 2\n"
            "■ 엔진: faster-whisper large-v3 + pyannote\n\n"
            "※ 본 문서는 자동 생성본입니다. 원본 음성과 대조해 확인하십시오.\n"
            "※ 화자 라벨은 성명이 아니라 구분용입니다. 필요 시 직접 바꿔 쓰십시오.\n\n"
            f"{SEPARATOR}\n"
            "[00:00:01] 화자1\n"
            "안녕하세요. 오늘 상담 내용 녹음해도 될까요?\n\n"
            "[00:00:05] 화자2\n"
            "네, 괜찮습니다.\n\n"
            "[00:00:09] 화자1\n"
            "그럼 사실관계부터 정리하겠습니다.\n\n"
            f"{SEPARATOR}\n"
        )
        assert result == expected_header

    def test_render_transcript_with_dict(self):
        """dict 형태의 메타데이터 및 세그먼트 입력 지원 및 화자 라벨 정규화 테스트."""
        meta = {
            "original_filename": "진술_2026.wav",
            "original_path": r"C:\Data\진술_2026.wav",
            "created_at": "2026-09-08 15:30:00",
            "total_duration": "00:01:30",
            "language": "ko",
            "speaker_count": 2,
            "engine_info": "faster-whisper",
        }
        segments = [
            {"start": 0.0, "speaker": "SPEAKER_00", "text": "진술을 시작합니다."},
            {"start": 10.0, "speaker": 2, "text": "네, 알겠습니다."},
        ]

        result = render_transcript(segments, meta)
        assert "■ 원본파일: 진술_2026.wav" in result
        assert "[00:00:00] 화자1\n진술을 시작합니다." in result
        assert "[00:00:10] 화자2\n네, 알겠습니다." in result

    def test_render_transcript_empty_segments(self):
        """세그먼트가 비어 있는 경우에도 헤더와 구분선이 정상 출력되는지 테스트."""
        meta = {
            "original_filename": "empty.m4a",
            "original_path": r"C:\Data\empty.m4a",
            "created_at": "2026-09-08 12:00:00",
            "total_duration": 0,
        }
        result = render_transcript([], meta)
        assert "■ 원본파일: empty.m4a" in result
        assert f"{SEPARATOR}\n\n{SEPARATOR}\n" in result


class TestWriteModule:
    """write.py 모듈 테스트 클래스."""

    def test_get_output_path_naming_rules(self, tmp_path):
        """출력 파일명 규칙 및 충돌 회피(_2, _3...) 테스트."""
        source_file = tmp_path / "상담.m4a"
        source_file.touch()

        # 1. 파일이 없을 때 기본 경로: {stem}_녹취서.txt
        p1 = get_output_path(source_file)
        assert p1 == tmp_path / "상담_녹취서.txt"
        assert p1.parent == tmp_path

        # 2. 파일이 이미 존재할 때: _2.txt
        p1.touch()
        p2 = get_output_path(source_file)
        assert p2 == tmp_path / "상담_녹취서_2.txt"

        # 3. _2.txt도 존재할 때: _3.txt
        p2.touch()
        p3 = get_output_path(source_file)
        assert p3 == tmp_path / "상담_녹취서_3.txt"

    def test_output_path_never_app_dir(self, tmp_path):
        """저장 경로가 항상 원본 파일의 디렉터리이며 CWD나 앱 디렉터리가 아님을 검증."""
        custom_folder = tmp_path / "사건_123"
        custom_folder.mkdir()
        audio_path = custom_folder / "음성.mp3"
        audio_path.touch()

        output_path = get_output_path(audio_path)
        assert output_path.parent == custom_folder
        assert output_path.parent != Path.cwd()

    def test_write_transcript_atomic_and_encoding(self, tmp_path):
        """write_transcript가 UTF-8 BOM으로 작성되고 원자적으로 저장되는지 테스트."""
        source_file = tmp_path / "진술.wav"
        source_file.touch()
        content = "【녹취서】\n테스트 내용입니다."

        out_path = write_transcript(source_file, content)
        assert out_path == tmp_path / "진술_녹취서.txt"
        assert out_path.is_file()

        # UTF-8 BOM 확인 (첫 3바이트: 0xEF, 0xBB, 0xBF)
        raw_bytes = out_path.read_bytes()
        assert raw_bytes.startswith(b"\xef\xbb\xbf")

        # 텍스트 복원 확인
        decoded = out_path.read_text(encoding="utf-8-sig")
        assert decoded == content

        # 임시 파일(.tmp.txt)이 작업 후 남아있지 않은지 검증
        tmp_files = list(tmp_path.glob("*.tmp.txt"))
        assert len(tmp_files) == 0

    def test_write_transcript_incremental_save(self, tmp_path):
        """동일 소스에 대해 반복 호출 시 덮어쓰지 않고 _2, _3으로 생성되는지 테스트."""
        source_file = tmp_path / "녹음.m4a"
        source_file.touch()

        w1 = write_transcript(source_file, "1차 녹취")
        assert w1 == tmp_path / "녹음_녹취서.txt"

        w2 = write_transcript(source_file, "2차 녹취")
        assert w2 == tmp_path / "녹음_녹취서_2.txt"

        assert w1.read_text(encoding="utf-8-sig") == "1차 녹취"
        assert w2.read_text(encoding="utf-8-sig") == "2차 녹취"

    def test_clean_temp_file(self, tmp_path):
        """clean_temp_file이 관련된 임시 파일만 올바르게 삭제하는지 테스트."""
        source_file = tmp_path / "상담.m4a"
        source_file.touch()

        # 관련된 임시 파일 생성
        tmp1 = tmp_path / "상담_녹취서.tmp.txt"
        tmp2 = tmp_path / "상담_녹취서_2.tmp.txt"
        tmp1.write_text("임시1")
        tmp2.write_text("임시2")

        # 다른 원본의 임시 파일 생성 (삭제되면 안 됨)
        other_tmp = tmp_path / "기타_녹취서.tmp.txt"
        other_tmp.write_text("기타임시")

        cleaned = clean_temp_file(source_file)
        assert tmp1 in cleaned
        assert tmp2 in cleaned
        assert other_tmp not in cleaned

        assert not tmp1.exists()
        assert not tmp2.exists()
        assert other_tmp.exists()

    def test_permission_error_handling(self):
        """쓰기 권한 실패 시 정해진 한국어 메시지로 PermissionError가 발생하는지 테스트."""
        with mock.patch("builtins.open", side_effect=PermissionError("Permission denied")):
            with pytest.raises(PermissionError) as exc_info:
                write_transcript(Path("C:/test/sample.m4a"), "내용")
            assert str(exc_info.value) == "녹취서를 저장할 수 없습니다. 폴더 쓰기 권한을 확인하세요."
