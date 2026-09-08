# -*- coding: utf-8 -*-
"""녹취서 텍스트 렌더링 모듈.

STT 전사 결과 및 화자 분리 세그먼트와 메타데이터를 결합하여
법률 실무용 표준 서식의 녹취서 문자열을 생성합니다.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Union

# 법률 실무 표준 구분선: ─ (U+2500) 32자
SEPARATOR = "─" * 32


@dataclass
class TranscriptMetadata:
    """녹취서 메타데이터 데이터클래스."""

    original_filename: str
    original_path: str
    created_at: Union[str, datetime] = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    total_duration: Union[float, int, str] = 0.0
    language: str = "ko"
    speaker_count: Optional[int] = None
    engine_info: str = "faster-whisper large-v3 + pyannote"


@dataclass
class TranscriptSegment:
    """녹취서 발화 세그먼트 데이터클래스."""

    start: float
    end: float
    speaker: str
    text: str


def format_duration(seconds: Union[float, int]) -> str:
    """초 단위 시간을 HH:MM:SS 형식의 문자열로 변환합니다. (괄호 없음)

    Args:
        seconds: 변환할 초 단위 시간 (음수일 경우 0으로 처리)

    Returns:
        HH:MM:SS 형식의 문자열 (예: '00:12:34')
    """
    total_seconds = max(0, int(seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_timestamp(seconds: Union[float, int]) -> str:
    """초 단위 시간을 [HH:MM:SS] 형식의 문자열로 변환합니다.

    Args:
        seconds: 변환할 초 단위 시간 (음수일 경우 0으로 처리)

    Returns:
        [HH:MM:SS] 형식의 문자열 (예: '[00:00:01]')
    """
    return f"[{format_duration(seconds)}]"


def _extract_meta_field(metadata: Any, key: str, default: Any = None) -> Any:
    """메타데이터 객체(dataclass 또는 dict)에서 필드 값을 안전하게 추출합니다."""
    if isinstance(metadata, dict):
        return metadata.get(key, default)
    return getattr(metadata, key, default)


def _format_speaker_label(raw_speaker: Any) -> str:
    """화자 라벨을 '화자N' 형식으로 표준화합니다."""
    spk_str = str(raw_speaker).strip() if raw_speaker is not None else ""
    if not spk_str:
        return "화자1"

    # 이미 '화자1', '화자2' 형태인 경우 그대로 반환
    if spk_str.startswith("화자") and len(spk_str) > 2 and spk_str[2:].isdigit():
        return spk_str

    # 숫자만 넘어온 경우 (예: 1, 2)
    if spk_str.isdigit():
        return f"화자{spk_str}"

    # pyannote 기본 형태 'SPEAKER_00', 'SPEAKER_01' 등 처리
    if spk_str.startswith("SPEAKER_"):
        try:
            spk_num = int(spk_str.split("_")[1]) + 1
            return f"화자{spk_num}"
        except (IndexError, ValueError):
            pass

    return spk_str


def render_transcript(
    segments: Sequence[Union[TranscriptSegment, Dict[str, Any], Any]],
    metadata: Union[TranscriptMetadata, Dict[str, Any], Any],
) -> str:
    """세그먼트 목록과 메타데이터를 결합하여 최종 녹취서 TXT 문자열을 생성합니다.

    출력 서식:
    【녹취서】

    ■ 원본파일: {original_filename}
    ■ 원본경로: {original_path}
    ■ 작성일시: {created_at}  (format: YYYY-MM-DD HH:MM:SS)
    ■ 총길이: {total_duration}  (format: HH:MM:SS)
    ■ 언어: {language}
    ■ 화자 수: {speaker_count}
    ■ 엔진: {engine_info}

    ※ 본 문서는 자동 생성본입니다. 원본 음성과 대조해 확인하십시오.
    ※ 화자 라벨은 성명이 아니라 구분용입니다. 필요 시 직접 바꿔 쓰십시오.

    ────────────────────────────────
    [HH:MM:SS] 화자N
    발화 내용

    [HH:MM:SS] 화자M
    발화 내용

    ────────────────────────────────

    Args:
        segments: 세그먼트 시퀀스 (dict 또는 속성을 가진 객체: start, speaker, text)
        metadata: 메타데이터 (TranscriptMetadata 또는 dict)

    Returns:
        법률 실무용 규격의 녹취서 전체 문자열
    """
    # 1. 메타데이터 필드 파싱 및 포맷팅
    original_filename = str(_extract_meta_field(metadata, "original_filename", "") or "")
    original_path = str(_extract_meta_field(metadata, "original_path", "") or "")

    # 작성일시 (YYYY-MM-DD HH:MM:SS)
    created_val = _extract_meta_field(metadata, "created_at", None)
    if isinstance(created_val, (datetime, date)):
        created_at_str = created_val.strftime("%Y-%m-%d %H:%M:%S")
    elif created_val:
        created_at_str = str(created_val).strip()
    else:
        created_at_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 총길이 (HH:MM:SS)
    duration_val = _extract_meta_field(metadata, "total_duration", None)
    if duration_val is None:
        # 세그먼트의 최대 end 시간으로 계산 시도
        max_end = 0.0
        for seg in segments:
            seg_end = seg.get("end", 0.0) if isinstance(seg, dict) else getattr(seg, "end", 0.0)
            try:
                max_end = max(max_end, float(seg_end))
            except (TypeError, ValueError):
                pass
        total_duration_str = format_duration(max_end)
    elif isinstance(duration_val, (int, float)):
        total_duration_str = format_duration(duration_val)
    elif isinstance(duration_val, str):
        if ":" in duration_val:
            total_duration_str = duration_val.strip()
        else:
            try:
                total_duration_str = format_duration(float(duration_val))
            except ValueError:
                total_duration_str = duration_val.strip()
    else:
        total_duration_str = "00:00:00"

    # 언어
    language = str(_extract_meta_field(metadata, "language", "ko") or "ko")

    # 화자 수
    speaker_count_val = _extract_meta_field(metadata, "speaker_count", None)
    if speaker_count_val is not None:
        speaker_count_str = str(speaker_count_val)
    else:
        # 세그먼트에서 고유 화자 수 계산
        unique_speakers = set()
        for seg in segments:
            spk = seg.get("speaker") if isinstance(seg, dict) else getattr(seg, "speaker", None)
            if spk is not None:
                unique_speakers.add(_format_speaker_label(spk))
        speaker_count_str = str(len(unique_speakers)) if unique_speakers else "1"

    # 엔진 정보
    engine_info = str(
        _extract_meta_field(metadata, "engine_info", "faster-whisper large-v3 + pyannote")
        or "faster-whisper large-v3 + pyannote"
    )

    # 2. 문서 헤더 및 고정 문구 구성
    lines: List[str] = [
        "【녹취서】",
        "",
        f"■ 원본파일: {original_filename}",
        f"■ 원본경로: {original_path}",
        f"■ 작성일시: {created_at_str}",
        f"■ 총길이: {total_duration_str}",
        f"■ 언어: {language}",
        f"■ 화자 수: {speaker_count_str}",
        f"■ 엔진: {engine_info}",
        "",
        "※ 본 문서는 자동 생성본입니다. 원본 음성과 대조해 확인하십시오.",
        "※ 화자 라벨은 성명이 아니라 구분용입니다. 필요 시 직접 바꿔 쓰십시오.",
        "",
        SEPARATOR,
    ]

    # 3. 발화 세그먼트 본문 구성
    # 각 발화 블록: 타임스탬프+화자 줄, 다음 줄 본문, 빈 줄
    if segments:
        for seg in segments:
            if isinstance(seg, dict):
                start = seg.get("start", 0.0)
                speaker = seg.get("speaker", "화자1")
                text = seg.get("text", "")
            else:
                start = getattr(seg, "start", 0.0)
                speaker = getattr(seg, "speaker", "화자1")
                text = getattr(seg, "text", "")

            try:
                start_sec = float(start)
            except (TypeError, ValueError):
                start_sec = 0.0

            spk_label = _format_speaker_label(speaker)
            ts_str = format_timestamp(start_sec)
            text_str = str(text).strip() if text is not None else ""

            lines.append(f"{ts_str} {spk_label}")
            lines.append(text_str)
            lines.append("")

        lines.append(SEPARATOR)
    else:
        # 세그먼트가 없는 경우 빈 줄 하나 후 닫는 구분선
        lines.append("")
        lines.append(SEPARATOR)

    return "\n".join(lines) + "\n"
