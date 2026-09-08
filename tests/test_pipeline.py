"""
파이프라인 모듈(STT, Diarize, Merge) 단위 테스트
"""

import unittest
from unittest.mock import MagicMock, patch
import threading

from src.pipeline.stt import Segment, WhisperSTT, _is_cancelled
from src.pipeline.diarize import SpeakerSegment, DiarizationEngine, resolve_hf_token
from src.pipeline.merge import (
    MergedSegment,
    assign_speakers,
    normalize_speakers,
    merge_consecutive,
    clean_segments,
    full_merge,
)


class TestSTT(unittest.TestCase):
    def setUp(self):
        WhisperSTT.reset_instance()

    def tearDown(self):
        WhisperSTT.reset_instance()

    def test_segment_dataclass(self):
        seg = Segment(start=0.0, end=1.5, text="안녕하세요")
        self.assertEqual(seg.start, 0.0)
        self.assertEqual(seg.end, 1.5)
        self.assertEqual(seg.text, "안녕하세요")

    def test_is_cancelled(self):
        self.assertFalse(_is_cancelled(None))
        self.assertFalse(_is_cancelled(False))
        self.assertTrue(_is_cancelled(True))

        event = threading.Event()
        self.assertFalse(_is_cancelled(event))
        event.set()
        self.assertTrue(_is_cancelled(event))

        # Callable
        self.assertTrue(_is_cancelled(lambda: True))
        self.assertFalse(_is_cancelled(lambda: False))

    @patch("src.pipeline.stt.WhisperModel")
    def test_whisper_stt_init_and_singleton(self, mock_model_cls):
        mock_instance = MagicMock()
        mock_model_cls.return_value = mock_instance

        # CPU 지정 시 int8
        stt_cpu = WhisperSTT(model_name="medium", device="cpu")
        self.assertEqual(stt_cpu.device, "cpu")
        self.assertEqual(stt_cpu.compute_type, "int8")

        # CUDA 지정 시 float16
        stt_cuda = WhisperSTT(model_name="large-v3", device="cuda")
        self.assertEqual(stt_cuda.device, "cuda")
        self.assertEqual(stt_cuda.compute_type, "float16")

        # 싱글톤 get_instance
        instance1 = WhisperSTT.get_instance({"whisper_model": "large-v3", "device": "cpu"})
        instance2 = WhisperSTT.get_instance()
        self.assertIs(instance1, instance2)

    @patch("src.pipeline.stt.WhisperModel")
    @patch("src.pipeline.stt.os.path.exists", return_value=True)
    def test_transcribe(self, mock_exists, mock_model_cls):
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model

        # 가짜 세그먼트 생성
        dummy_seg1 = MagicMock(start=0.0, end=1.2, text="  안녕하세요  ")
        dummy_seg2 = MagicMock(start=1.2, end=2.0, text="   ")  # 빈 세그먼트
        dummy_seg3 = MagicMock(start=2.0, end=3.5, text="반갑습니다.")
        mock_model.transcribe.return_value = ([dummy_seg1, dummy_seg2, dummy_seg3], None)

        stt = WhisperSTT(device="cpu")
        segments = stt.transcribe("dummy.wav", language="ko")

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].text, "안녕하세요")
        self.assertEqual(segments[1].text, "반갑습니다.")
        self.assertEqual(segments[0].start, 0.0)
        self.assertEqual(segments[1].end, 3.5)

    @patch("src.pipeline.stt.WhisperModel")
    @patch("src.pipeline.stt.os.path.exists", return_value=True)
    def test_transcribe_cancelled(self, mock_exists, mock_model_cls):
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model

        cancel_event = threading.Event()
        cancel_event.set()

        stt = WhisperSTT(device="cpu")
        with self.assertRaises(RuntimeError) as ctx:
            stt.transcribe("dummy.wav", cancel_token=cancel_event)
        self.assertIn("사용자 요청으로 작업을 취소했습니다.", str(ctx.exception))


class TestDiarize(unittest.TestCase):
    def setUp(self):
        DiarizationEngine.reset_instance()

    def tearDown(self):
        DiarizationEngine.reset_instance()

    def test_token_validation_empty(self):
        # 토큰이 없거나 빈 문자열일 때 ValueError 발생 검증
        with self.assertRaises(ValueError) as ctx:
            DiarizationEngine(hf_token="")
        self.assertEqual(str(ctx.exception), "화자 분리를 위해 Hugging Face 토큰이 config.json에 필요합니다.")

        with self.assertRaises(ValueError) as ctx2:
            DiarizationEngine(hf_token=None)
        self.assertEqual(str(ctx2.exception), "화자 분리를 위해 Hugging Face 토큰이 config.json에 필요합니다.")

    @patch("src.pipeline.diarize.Pipeline")
    def test_diarize_engine_singleton(self, mock_pipeline_cls):
        mock_pipeline = MagicMock()
        mock_pipeline_cls.from_pretrained.return_value = mock_pipeline

        engine1 = DiarizationEngine.get_instance({"hf_token": "hf_test123", "device": "cpu"})
        engine2 = DiarizationEngine.get_instance()
        self.assertIs(engine1, engine2)
        self.assertEqual(engine1.hf_token, "hf_test123")

    @patch("src.pipeline.diarize.Pipeline")
    @patch("src.pipeline.diarize.os.path.exists", return_value=True)
    def test_diarize_execution(self, mock_exists, mock_pipeline_cls):
        mock_pipeline = MagicMock()
        mock_pipeline_cls.from_pretrained.return_value = mock_pipeline

        # 가짜 Annotation 객체 생성
        mock_annotation = MagicMock()
        turn1 = MagicMock(start=0.0, end=2.0)
        turn2 = MagicMock(start=2.5, end=4.0)
        mock_annotation.itertracks.return_value = [
            (turn2, "track2", "SPEAKER_01"),
            (turn1, "track1", "SPEAKER_00"),
        ]
        # pipeline 호출 시 mock_annotation 반환
        mock_pipeline.return_value = mock_annotation

        engine = DiarizationEngine(hf_token="hf_test_token", device="cpu")
        spk_segments = engine.diarize("dummy.wav")

        # 시간순 정렬 확인
        self.assertEqual(len(spk_segments), 2)
        self.assertEqual(spk_segments[0].start, 0.0)
        self.assertEqual(spk_segments[0].speaker, "SPEAKER_00")
        self.assertEqual(spk_segments[1].start, 2.5)
        self.assertEqual(spk_segments[1].speaker, "SPEAKER_01")


class TestMerge(unittest.TestCase):
    def test_assign_speakers_max_overlap(self):
        stt_segs = [
            Segment(start=1.0, end=3.0, text="안녕하세요."),
            Segment(start=3.5, end=5.0, text="네 반갑습니다."),
        ]
        spk_segs = [
            SpeakerSegment(start=0.5, end=2.5, speaker="SPEAKER_00"),  # overlap 1.5s
            SpeakerSegment(start=2.5, end=3.2, speaker="SPEAKER_01"),  # overlap 0.5s
            SpeakerSegment(start=3.4, end=5.2, speaker="SPEAKER_01"),  # overlap 1.5s
        ]

        merged = assign_speakers(stt_segs, spk_segs)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].speaker, "SPEAKER_00")
        self.assertEqual(merged[1].speaker, "SPEAKER_01")

    def test_assign_speakers_no_overlap_nearest(self):
        stt_segs = [
            Segment(start=10.0, end=12.0, text="중간에 떨어진 말입니다."),
        ]
        spk_segs = [
            SpeakerSegment(start=1.0, end=3.0, speaker="SPEAKER_00"),   # distance = 7.0
            SpeakerSegment(start=15.0, end=18.0, speaker="SPEAKER_01"), # distance = 3.0
        ]

        merged = assign_speakers(stt_segs, spk_segs)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].speaker, "SPEAKER_01")

    def test_assign_speakers_empty_speaker_segments(self):
        stt_segs = [Segment(start=0.0, end=1.0, text="테스트")]
        merged = assign_speakers(stt_segs, [])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].speaker, "화자1")

    def test_normalize_speakers(self):
        segments = [
            MergedSegment(start=0.0, end=1.0, text="A", speaker="SPEAKER_01"),
            MergedSegment(start=1.0, end=2.0, text="B", speaker="SPEAKER_00"),
            MergedSegment(start=2.0, end=3.0, text="C", speaker="SPEAKER_02"),
        ]

        normalized = normalize_speakers(segments)
        # SPEAKER_00 -> 화자1, SPEAKER_01 -> 화자2, SPEAKER_02 -> 화자3
        self.assertEqual(normalized[0].speaker, "화자2")
        self.assertEqual(normalized[1].speaker, "화자1")
        self.assertEqual(normalized[2].speaker, "화자3")

    def test_merge_consecutive(self):
        segments = [
            MergedSegment(start=0.0, end=2.0, text="안녕하세요.", speaker="화자1"),
            MergedSegment(start=2.5, end=4.0, text="오늘 상담 오셨군요.", speaker="화자1"),  # gap 0.5 <= 2.0 -> 병합
            MergedSegment(start=7.0, end=8.0, text="네 맞습니다.", speaker="화자2"),       # 화자 다름
            MergedSegment(start=11.0, end=12.0, text="질문이 있습니다.", speaker="화자2"), # gap 3.0 > 2.0 -> 분리
        ]

        merged = merge_consecutive(segments, gap_threshold=2.0)
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[0].speaker, "화자1")
        self.assertEqual(merged[0].start, 0.0)
        self.assertEqual(merged[0].end, 4.0)
        self.assertEqual(merged[0].text, "안녕하세요. 오늘 상담 오셨군요.")

        self.assertEqual(merged[1].speaker, "화자2")
        self.assertEqual(merged[1].text, "네 맞습니다.")

        self.assertEqual(merged[2].speaker, "화자2")
        self.assertEqual(merged[2].text, "질문이 있습니다.")

    def test_clean_segments_hallucination_and_empty(self):
        segments = [
            MergedSegment(start=0.0, end=1.0, text="   ", speaker="화자1"),  # 빈 세그먼트 삭제
            MergedSegment(start=1.0, end=2.0, text="감사합니다.", speaker="화자1"),
            MergedSegment(start=2.0, end=3.0, text="감사합니다.", speaker="화자1"),
            MergedSegment(start=3.0, end=4.0, text="감사합니다.", speaker="화자1"),  # 3회 연속 동일 환각 -> 1개로 축약
            MergedSegment(start=4.0, end=5.0, text="네.", speaker="화자2"),
            MergedSegment(start=5.0, end=6.0, text="네.", speaker="화자2"),          # 2회 연속은 유지
        ]

        cleaned = clean_segments(segments)
        self.assertEqual(len(cleaned), 3)
        self.assertEqual(cleaned[0].text, "감사합니다.")
        self.assertEqual(cleaned[1].text, "네.")
        self.assertEqual(cleaned[2].text, "네.")

    def test_clean_segments_intra_text_repetition(self):
        segments = [
            MergedSegment(
                start=0.0,
                end=5.0,
                text="감사합니다. 감사합니다. 감사합니다. 감사합니다.",
                speaker="화자1"
            )
        ]
        cleaned = clean_segments(segments)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0].text, "감사합니다.")

    def test_full_merge(self):
        stt_segs = [
            Segment(start=0.0, end=1.5, text="안녕하세요."),
            Segment(start=2.0, end=3.5, text="반갑습니다."),
            Segment(start=4.0, end=5.5, text="네, 안녕하세요."),
        ]
        spk_segs = [
            SpeakerSegment(start=0.0, end=3.8, speaker="SPEAKER_00"),
            SpeakerSegment(start=3.9, end=6.0, speaker="SPEAKER_01"),
        ]

        final_segments = full_merge(stt_segs, spk_segs, gap_threshold=2.0)
        self.assertEqual(len(final_segments), 2)
        # SPEAKER_00 -> 화자1, 연속 병합됨
        self.assertEqual(final_segments[0].speaker, "화자1")
        self.assertEqual(final_segments[0].start, 0.0)
        self.assertEqual(final_segments[0].end, 3.5)
        self.assertEqual(final_segments[0].text, "안녕하세요. 반갑습니다.")

        # SPEAKER_01 -> 화자2
        self.assertEqual(final_segments[1].speaker, "화자2")
        self.assertEqual(final_segments[1].text, "네, 안녕하세요.")


if __name__ == "__main__":
    unittest.main()
