"""
녹취서 자동 생성기 - STT 모듈 (faster-whisper)
faster-whisper 모델을 싱글톤으로 로드하여 음성 파일의 음성을 텍스트로 전사합니다.
"""

from dataclasses import dataclass
from typing import Optional, List, Any
import os
import logging
import threading

logger = logging.getLogger("voice2txt.pipeline.stt")

# PyTorch 및 faster-whisper 동적/안전 로드 지원
try:
    import torch
except ImportError:
    torch = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None


@dataclass
class Segment:
    """STT 전사 세그먼트 데이터 클래스"""
    start: float
    end: float
    text: str


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


class WhisperSTT:
    """faster-whisper 기반 STT 싱글톤 클래스"""

    _instance: Optional['WhisperSTT'] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        model_name: str = "large-v3",
        device: str = "auto",
        compute_type: Optional[str] = None
    ) -> None:
        """
        WhisperSTT 초기화 및 WhisperModel 로드.

        Args:
            model_name: faster-whisper 모델명 (기본값: "large-v3")
            device: 실행 장치 ("auto", "cuda", "cpu"). "auto"일 경우 CUDA 가용성 검사
            compute_type: 연산 정밀도 (device="cpu"이면 "int8", device="cuda"이면 "float16")
        """
        self.model_name = model_name

        # 장치(device) 자동 판별: "auto"인 경우 torch.cuda.is_available() 확인
        if device is None or str(device).lower() == "auto":
            if torch is not None and hasattr(torch, "cuda") and torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"
        else:
            self.device = str(device).lower()

        # 연산 정밀도(compute_type) 결정
        if compute_type is None or str(compute_type).lower() == "auto":
            if self.device == "cuda":
                self.compute_type = "float16"
            else:
                self.compute_type = "int8"
        else:
            self.compute_type = compute_type

        # 모델 로드 정보 로깅
        logger.info(
            f"faster-whisper 모델 로드 시작: model_name={self.model_name}, "
            f"device={self.device}, compute_type={self.compute_type}"
        )

        if WhisperModel is None:
            raise ImportError(
                "faster-whisper 패키지가 설치되지 않았습니다. "
                "pip install faster-whisper 명령으로 설치해 주세요."
            )

        try:
            self.model = WhisperModel(
                model_size_or_path=self.model_name,
                device=self.device,
                compute_type=self.compute_type
            )
            logger.info(
                f"faster-whisper 모델 로드 완료: model_name={self.model_name}, "
                f"device={self.device}, compute_type={self.compute_type}"
            )
        except Exception as e:
            if "out of memory" in str(e).lower():
                logger.error("faster-whisper 모델 로드 중 CUDA OOM 발생")
                raise RuntimeError("메모리 부족. 설정에서 모델을 medium으로 낮추세요.") from e
            logger.error(f"faster-whisper 모델 로드 실패: {e}")
            raise

    @classmethod
    def get_instance(cls, config: Optional[Any] = None) -> 'WhisperSTT':
        """
        WhisperSTT 싱글톤 인스턴스를 반환합니다.
        
        Args:
            config: 설정 딕셔너리 또는 객체 (whisper_model, device, compute_type_gpu, compute_type_cpu 등)
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    model_name = "large-v3"
                    device = "auto"
                    compute_type = None

                    if isinstance(config, dict):
                        model_name = config.get("whisper_model", "large-v3")
                        device = config.get("device", "auto")
                        compute_type_gpu = config.get("compute_type_gpu", "float16")
                        compute_type_cpu = config.get("compute_type_cpu", "int8")
                    elif config is not None:
                        model_name = getattr(config, "whisper_model", "large-v3")
                        device = getattr(config, "device", "auto")
                        compute_type_gpu = getattr(config, "compute_type_gpu", "float16")
                        compute_type_cpu = getattr(config, "compute_type_cpu", "int8")
                    else:
                        compute_type_gpu = "float16"
                        compute_type_cpu = "int8"

                    if str(device).lower() == "cuda":
                        compute_type = compute_type_gpu
                    elif str(device).lower() == "cpu":
                        compute_type = compute_type_cpu

                    cls._instance = cls(
                        model_name=model_name,
                        device=device,
                        compute_type=compute_type
                    )
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """싱글톤 인스턴스를 초기화합니다 (테스트용)."""
        with cls._lock:
            cls._instance = None

    def transcribe(
        self,
        wav_path: str,
        language: str = "ko",
        vad_filter: bool = True,
        cancel_token: Optional[Any] = None
    ) -> List[Segment]:
        """
        WAV 오디오 파일을 전사하여 세그먼트 리스트를 반환합니다.

        Args:
            wav_path: 입력 WAV 파일 경로
            language: 전사 언어 코드 (기본값: "ko")
            vad_filter: 음성 구간 검출(VAD) 필터 사용 여부 (기본값: True)
            cancel_token: 작업 취소 확인용 객체 또는 Event

        Returns:
            List[Segment]: 전사된 세그먼트 리스트 (start, end, text)

        Raises:
            RuntimeError: 작업 취소 또는 메모리 부족 발생 시
            FileNotFoundError: wav_path 파일이 존재하지 않는 경우
        """
        if not os.path.exists(wav_path):
            raise FileNotFoundError(f"전사할 오디오 파일을 찾을 수 없습니다: {wav_path}")

        # 시작 전 취소 확인
        if _is_cancelled(cancel_token):
            raise RuntimeError("사용자 요청으로 작업을 취소했습니다.")

        logger.info(f"STT 전사 시작: {wav_path} (language={language}, vad_filter={vad_filter})")

        try:
            segments_gen, info = self.model.transcribe(
                wav_path,
                language=language,
                vad_filter=vad_filter
            )

            result: List[Segment] = []
            for seg in segments_gen:
                # 세그먼트 처리 사이마다 취소 여부 확인
                if _is_cancelled(cancel_token):
                    logger.info("STT 전사 중 작업 취소 요청 감지됨")
                    raise RuntimeError("사용자 요청으로 작업을 취소했습니다.")

                # 양끝 공백 제거 및 빈 세그먼트 건너뛰기
                text = seg.text.strip() if seg.text else ""
                if not text:
                    continue

                result.append(
                    Segment(
                        start=float(seg.start),
                        end=float(seg.end),
                        text=text
                    )
                )

            logger.info(f"STT 전사 완료: 총 {len(result)}개 세그먼트 생성됨")
            return result

        except RuntimeError as e:
            if "사용자 요청으로 작업을 취소했습니다." in str(e):
                raise
            if "out of memory" in str(e).lower():
                logger.error("STT 전사 중 CUDA OOM 발생")
                raise RuntimeError("메모리 부족. 설정에서 모델을 medium으로 낮추세요.") from e
            raise
        except Exception as e:
            if "out of memory" in str(e).lower():
                logger.error("STT 전사 중 CUDA OOM 발생")
                raise RuntimeError("메모리 부족. 설정에서 모델을 medium으로 낮추세요.") from e
            logger.error(f"STT 전사 중 오류 발생: {e}")
            raise
