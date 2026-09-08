"""
녹취서 자동 생성기 - 화자 분리 모듈 (pyannote.audio)
pyannote/speaker-diarization-3.1 파이프라인을 싱글톤으로 로드하여
오디오 파일에서 화자별 발화 구간(SpeakerSegment)을 추출합니다.
"""

from dataclasses import dataclass
from typing import Optional, List, Any
from pathlib import Path
import os
import logging
import threading

logger = logging.getLogger("voice2txt.pipeline.diarize")

# PyTorch 및 pyannote.audio 동적/안전 로드 지원
try:
    import torch
except ImportError:
    torch = None

try:
    from pyannote.audio import Pipeline
except ImportError:
    Pipeline = None


@dataclass
class SpeakerSegment:
    """화자 분리 구간 데이터 클래스"""
    start: float
    end: float
    speaker: str


def _is_cancelled(cancel_token: Optional[Any]) -> bool:
    """취소 토큰의 취소 여부를 확인합니다."""
    if cancel_token is None:
        return False
    if isinstance(cancel_token, bool):
        return cancel_token
    if hasattr(cancel_token, "is_set") and callable(cancel_token.is_set):
        return cancel_token.is_set()
    if hasattr(cancel_token, "is_cancelled"):
        val = cancel_token.is_cancelled
        return val() if callable(val) else bool(val)
    if hasattr(cancel_token, "is_canceled"):
        val = cancel_token.is_canceled
        return val() if callable(val) else bool(val)
    if callable(cancel_token):
        return bool(cancel_token())
    return bool(cancel_token)


def resolve_hf_token(config: Optional[Any] = None) -> Optional[str]:
    """
    Hugging Face 토큰을 다음 순서로 탐색하여 반환합니다:
    1. config.json의 hf_token
    2. 환경변수 HF_TOKEN 또는 HUGGING_FACE_HUB_TOKEN
    3. %USERPROFILE%/.cache/huggingface/token
    """
    # 1. config 객체 또는 딕셔너리
    token = None
    if isinstance(config, dict):
        token = config.get("hf_token")
    elif config is not None:
        token = getattr(config, "hf_token", None)

    if token and str(token).strip():
        return str(token).strip()

    # 2. 환경변수
    env_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if env_token and str(env_token).strip():
        return str(env_token).strip()

    # 3. huggingface 캐시 파일
    try:
        cache_token_path = Path.home() / ".cache" / "huggingface" / "token"
        if cache_token_path.exists():
            cached = cache_token_path.read_text(encoding="utf-8").strip()
            if cached:
                return cached
    except Exception as e:
        logger.debug(f"HF 캐시 토큰 읽기 실패: {e}")

    return None


class DiarizationEngine:
    """pyannote.audio 기반 화자 분리 싱글톤 클래스"""

    _instance: Optional['DiarizationEngine'] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        hf_token: Optional[str],
        device: str = "auto"
    ) -> None:
        """
        DiarizationEngine 초기화 및 pyannote/speaker-diarization-3.1 파이프라인 로드.

        Args:
            hf_token: Hugging Face 액세스 토큰 (필수)
            device: 실행 장치 ("auto", "cuda", "cpu"). "auto"일 경우 CUDA 가용성 검사

        Raises:
            ValueError: hf_token이 비어 있거나 None인 경우
            RuntimeError: CUDA OOM 또는 모델 로드 실패 시
        """
        # Hugging Face 토큰 유효성 검증
        if not hf_token or not str(hf_token).strip():
            raise ValueError("화자 분리를 위해 Hugging Face 토큰이 config.json에 필요합니다.")
        self.hf_token = str(hf_token).strip()

        # 장치(device) 자동 판별: "auto"인 경우 torch.cuda.is_available() 확인
        if device is None or str(device).lower() == "auto":
            if torch is not None and hasattr(torch, "cuda") and torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"
        else:
            self.device = str(device).lower()

        logger.info(
            f"pyannote diarization 파이프라인 로드 시작: "
            f"model=pyannote/speaker-diarization-3.1, device={self.device}"
        )

        if Pipeline is None:
            raise ImportError(
                "pyannote.audio 패키지가 설치되지 않았습니다. "
                "pip install pyannote.audio 명령으로 설치해 주세요."
            )

        try:
            # GUI 환경에서 tqdm 출력으로 인한 'NoneType' object has no attribute 'write' 방지
            try:
                from huggingface_hub.utils import disable_progress_bars
                disable_progress_bars()
            except Exception:
                pass

            try:
                self.pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    token=self.hf_token
                )
            except TypeError:
                # pyannote 구버전 호환 (use_auth_token 매개변수 사용)
                self.pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=self.hf_token
                )

            if self.pipeline is None:
                raise RuntimeError(
                    "화자 분리 모델을 불러오지 못했습니다. "
                    "Hugging Face 약관 동의(gated model) 및 토큰 권한을 확인하세요."
                )

            if torch is not None:
                self.pipeline.to(torch.device(self.device))
            logger.info("pyannote diarization 파이프라인 로드 완료")

        except Exception as e:
            if "out of memory" in str(e).lower():
                logger.error("pyannote 파이프라인 로드 중 CUDA OOM 발생")
                raise RuntimeError("메모리 부족. 설정에서 모델을 medium으로 낮추세요.") from e
            logger.error(f"pyannote 파이프라인 로드 실패: {e}")
            raise

    @classmethod
    def get_instance(cls, config: Optional[Any] = None) -> 'DiarizationEngine':
        """
        DiarizationEngine 싱글톤 인스턴스를 반환합니다.
        config에서 hf_token 및 device를 읽어오며, 필요 시 환경변수 및 캐시 토큰을 탐색합니다.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    device = "auto"
                    if isinstance(config, dict):
                        device = config.get("device", "auto")
                    elif config is not None:
                        device = getattr(config, "device", "auto")

                    token = resolve_hf_token(config)
                    cls._instance = cls(hf_token=token, device=device)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """싱글톤 인스턴스를 초기화합니다 (테스트용)."""
        with cls._lock:
            cls._instance = None

    def diarize(
        self,
        wav_path: str,
        min_speakers: Optional[int] = None,
        max_speakers: Optional[int] = 8,
        cancel_token: Optional[Any] = None
    ) -> List[SpeakerSegment]:
        """
        WAV 오디오 파일에서 화자 분리를 수행하여 SpeakerSegment 리스트를 반환합니다.

        Args:
            wav_path: 입력 WAV 파일 경로
            min_speakers: 최소 화자 수 힌트 (기본값: None)
            max_speakers: 최대 화자 수 힌트 (기본값: 8)
            cancel_token: 작업 취소 확인용 객체 또는 Event

        Returns:
            List[SpeakerSegment]: 추출된 화자 구간 리스트 (start, end, speaker)

        Raises:
            RuntimeError: 작업 취소 또는 메모리 부족 발생 시
            FileNotFoundError: wav_path 파일이 존재하지 않는 경우
        """
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"화자 분리할 오디오 파일을 찾을 수 없습니다: {wav_path}")

        # 시작 전 취소 확인
        if _is_cancelled(cancel_token):
            raise RuntimeError("사용자 요청으로 작업을 취소했습니다.")

        logger.info(
            f"화자 분리(Diarization) 시작: {wav_path} "
            f"(min_speakers={min_speakers}, max_speakers={max_speakers})"
        )

        diarize_kwargs = {}
        if min_speakers is not None:
            diarize_kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            diarize_kwargs["max_speakers"] = max_speakers

        try:
            diarization = self.pipeline(wav_path, **diarize_kwargs)
        except Exception as e:
            if "out of memory" in str(e).lower():
                logger.error("화자 분리 추론 중 CUDA OOM 발생")
                raise RuntimeError("메모리 부족. 설정에서 모델을 medium으로 낮추세요.") from e
            logger.error(f"화자 분리 추론 중 오류 발생: {e}")
            raise

        # 화자 분리 완료 후 cancel_token 검사
        if _is_cancelled(cancel_token):
            logger.info("화자 분리 완료 후 작업 취소 요청 감지됨")
            raise RuntimeError("사용자 요청으로 작업을 취소했습니다.")

        # Annotation 객체로부터 화자 구간(Speaker turns) 추출
        if hasattr(diarization, "itertracks"):
            annotation = diarization
        elif hasattr(diarization, "speaker_diarization"):
            annotation = diarization.speaker_diarization
        else:
            annotation = diarization

        speaker_segments: List[SpeakerSegment] = []

        if hasattr(annotation, "itertracks"):
            for turn, track, speaker in annotation.itertracks(yield_label=True):
                speaker_segments.append(
                    SpeakerSegment(
                        start=float(turn.start),
                        end=float(turn.end),
                        speaker=str(speaker)
                    )
                )

        # 시작 시간 오름차순 정렬
        speaker_segments.sort(key=lambda s: s.start)

        logger.info(f"화자 분리 완료: 총 {len(speaker_segments)}개 화자 구간 추출됨")
        return speaker_segments
