"""
녹취서 자동 생성기 - 화자 병합 및 정규화 모듈
STT 전사 결과(Segment)와 화자 분리 결과(SpeakerSegment)를 시간 겹침(overlap) 및 거리를
기준으로 결합하고, 화자 라벨을 '화자1', '화자2'로 정규화한 뒤 연속 발화 병합 및 환각 문장을 제거합니다.
"""

from dataclasses import dataclass
from typing import List, Optional
import re
import logging

try:
    from src.pipeline.stt import Segment
    from src.pipeline.diarize import SpeakerSegment
except ImportError:
    try:
        from .stt import Segment
        from .diarize import SpeakerSegment
    except ImportError:
        # 독립 실행 또는 테스트를 위한 폴백 정의
        @dataclass
        class Segment:
            start: float
            end: float
            text: str

        @dataclass
        class SpeakerSegment:
            start: float
            end: float
            speaker: str

logger = logging.getLogger("voice2txt.pipeline.merge")


@dataclass
class MergedSegment:
    """화자가 배정된 최종 녹취 세그먼트 데이터 클래스"""
    start: float
    end: float
    text: str
    speaker: str


def assign_speakers(
    stt_segments: List[Segment],
    speaker_segments: List[SpeakerSegment]
) -> List[MergedSegment]:
    """
    각 STT 세그먼트에 대해 화자 세그먼트와의 시간 겹침(overlap)을 계산하여 가장 일치하는 화자를 배정합니다.

    규칙:
    - overlap = min(seg.end, spk.end) - max(seg.start, spk.start)
    - overlap > 0인 화자 중 가장 큰 겹침 구간을 가진 화자를 선택
    - 모든 화자와 overlap <= 0인 경우, 시간상 가장 가까운(최소 거리) 화자 구간 선택
    - 화자 세그먼트가 없거나 매칭 불가 시 기본값 "화자1" 배정
    """
    merged: List[MergedSegment] = []

    for seg in stt_segments:
        if not speaker_segments:
            assigned_speaker = "화자1"
        else:
            best_spk: Optional[SpeakerSegment] = None
            max_overlap = -1.0

            # 1. 겹치는 구간(overlap) 탐색
            for spk in speaker_segments:
                overlap = min(seg.end, spk.end) - max(seg.start, spk.start)
                if overlap > max_overlap:
                    max_overlap = overlap
                    best_spk = spk

            if max_overlap > 0 and best_spk is not None:
                assigned_speaker = best_spk.speaker
            else:
                # 2. overlap <= 0인 경우 시간상 가장 가까운 화자 구간 선택
                nearest_spk: Optional[SpeakerSegment] = None
                min_distance = float('inf')

                for spk in speaker_segments:
                    if spk.end <= seg.start:
                        dist = seg.start - spk.end
                    elif spk.start >= seg.end:
                        dist = spk.start - seg.end
                    else:
                        dist = 0.0

                    if dist < min_distance:
                        min_distance = dist
                        nearest_spk = spk

                if nearest_spk is not None:
                    assigned_speaker = nearest_spk.speaker
                else:
                    assigned_speaker = "화자1"

        merged.append(
            MergedSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text,
                speaker=assigned_speaker
            )
        )

    return merged


def _extract_speaker_sort_key(speaker: str):
    """
    화자 라벨에서 정렬 기준 키를 추출합니다.
    숫자가 포함된 경우 숫자 오름차순으로 정렬합니다. (예: SPEAKER_00 -> 0, SPEAKER_01 -> 1)
    """
    match = re.search(r'\d+', speaker)
    if match:
        return (0, int(match.group(0)), speaker)
    return (1, 0, speaker)


def normalize_speakers(segments: List[MergedSegment]) -> List[MergedSegment]:
    """
    화자 라벨을 '화자1', '화자2', ... 형식으로 정규화합니다.

    규칙:
    - SPEAKER_00 -> 화자1, SPEAKER_01 -> 화자2 등
    - 레이블 숫자 오름차순으로 정렬하여 1부터 시작하는 '화자N'으로 매핑
    """
    if not segments:
        return []

    # 고유 화자 라벨 수집 및 숫자 오름차순 정렬
    unique_speakers = list(dict.fromkeys(seg.speaker for seg in segments))
    unique_speakers.sort(key=_extract_speaker_sort_key)

    # 화자1, 화자2, ... 매핑 테이블 생성
    speaker_map = {
        label: f"화자{idx + 1}"
        for idx, label in enumerate(unique_speakers)
    }

    return [
        MergedSegment(
            start=seg.start,
            end=seg.end,
            text=seg.text,
            speaker=speaker_map.get(seg.speaker, seg.speaker)
        )
        for seg in segments
    ]


def merge_consecutive(
    segments: List[MergedSegment],
    gap_threshold: float = 2.0
) -> List[MergedSegment]:
    """
    동일한 화자의 연속 발화 구간 사이의 공백(gap)이 gap_threshold 이하인 경우 하나의 세그먼트로 병합합니다.
    텍스트는 공백 한 칸으로 연결됩니다.
    """
    if not segments:
        return []

    merged: List[MergedSegment] = []
    current = MergedSegment(
        start=segments[0].start,
        end=segments[0].end,
        text=segments[0].text,
        speaker=segments[0].speaker
    )

    for nxt in segments[1:]:
        gap = nxt.start - current.end
        if nxt.speaker == current.speaker and gap <= gap_threshold:
            current.end = max(current.end, nxt.end)
            current.text = f"{current.text} {nxt.text}".strip()
        else:
            merged.append(current)
            current = MergedSegment(
                start=nxt.start,
                end=nxt.end,
                text=nxt.text,
                speaker=nxt.speaker
            )

    merged.append(current)
    return merged


def _clean_repeated_sentences_in_text(text: str) -> str:
    """
    단일 세그먼트 텍스트 내에서 3회 이상 연속 반복되는 동일 문장을 1회로 축약합니다.
    (예: '감사합니다. 감사합니다. 감사합니다.' -> '감사합니다.')
    """
    # 문장 종결 부호(.!?) 기준으로 분리
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if len(sentences) < 3:
        return text

    cleaned: List[str] = []
    i = 0
    n = len(sentences)
    while i < n:
        j = i
        norm_i = re.sub(r'[\s.!?]+$', '', sentences[i])
        while j < n:
            norm_j = re.sub(r'[\s.!?]+$', '', sentences[j])
            if norm_i == norm_j and norm_i != "":
                j += 1
            else:
                break

        run_length = j - i
        if run_length >= 3:
            cleaned.append(sentences[i])
        else:
            cleaned.extend(sentences[i:j])
        i = j

    return " ".join(cleaned)


def clean_segments(segments: List[MergedSegment]) -> List[MergedSegment]:
    """
    세그먼트 텍스트를 정제합니다.

    규칙:
    - 텍스트 앞뒤 공백 제거 (strip)
    - 빈 텍스트 세그먼트 제거
    - 단일 세그먼트 내 및 연속 세그먼트 간 동일 문장이 3회 이상 반복되는 환각(hallucination) 감지 시 1개만 유지
    """
    if not segments:
        return []

    # 1. 공백 제거 및 빈 세그먼트 필터링, 문장 내 반복 환각 축약
    cleaned: List[MergedSegment] = []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        text = _clean_repeated_sentences_in_text(text).strip()
        if not text:
            continue
        cleaned.append(
            MergedSegment(
                start=seg.start,
                end=seg.end,
                text=text,
                speaker=seg.speaker
            )
        )

    if not cleaned:
        return []

    # 2. 연속 세그먼트 간 동일 문장이 3회 이상 반복되는 환각 축약 (1개만 유지)
    deduped: List[MergedSegment] = []
    i = 0
    n = len(cleaned)
    while i < n:
        j = i
        norm_i = re.sub(r'[\s.!?]+$', '', cleaned[i].text)
        while j < n:
            norm_j = re.sub(r'[\s.!?]+$', '', cleaned[j].text)
            if norm_i == norm_j and norm_i != "":
                j += 1
            else:
                break

        run_length = j - i
        if run_length >= 3:
            # 3회 이상 연속 동일 문장 환각 -> 1개만 유지
            deduped.append(cleaned[i])
        else:
            deduped.extend(cleaned[i:j])
        i = j

    return deduped


def full_merge(
    stt_segments: List[Segment],
    speaker_segments: List[SpeakerSegment],
    gap_threshold: float = 2.0
) -> List[MergedSegment]:
    """
    STT 세그먼트와 화자 세그먼트를 결합하여 최종 녹취 세그먼트를 생성하는 메인 진입점 함수입니다.

    진행 순서:
    1. assign_speakers: 각 STT 세그먼트에 최대 overlap 또는 최단거리 화자 배정
    2. normalize_speakers: 화자 라벨을 '화자1', '화자2', ... 형식으로 정규화
    3. merge_consecutive: 동일 화자의 2초 이내 연속 발화 구간 병합
    4. clean_segments: 공백 제거, 빈 세그먼트 제거, 3회 이상 반복 환각 문장 축약
    """
    step1 = assign_speakers(stt_segments, speaker_segments)
    step2 = normalize_speakers(step1)
    step3 = merge_consecutive(step2, gap_threshold=gap_threshold)
    step4 = clean_segments(step3)
    return step4
