"""ffmpeg/ffprobe 연동 및 오디오 변환(WAV 16kHz 모노), 길이 측정 유틸리티."""

import os
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from typing import Optional, Union

from src.util.cancel import CancelToken, CancelledError
from src.util.log import get_logger

logger = get_logger("ffmpeg")

DURATION_REGEX = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)")
TIME_REGEX = re.compile(r"time=\s*(\d{2}):(\d{2}):(\d{2}(?:\.\d+)?)")


def get_app_dir() -> Path:
    """
    앱 실행 디렉토리를 반환합니다.
    - PyInstaller 배포본(frozen): exe 파일이 위치한 디렉토리
    - 개발 모드: 소스 루트 디렉토리 (voice2txt)
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # src/util/ffmpeg.py -> voice2txt 루트
    return Path(__file__).resolve().parent.parent.parent


def _get_subprocess_flags() -> dict:
    """Windows에서 ffmpeg 자식 프로세스의 콘솔 창이 뜨지 않도록 플래그를 반환합니다."""
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


def find_ffmpeg() -> Path:
    """
    ffmpeg 실행 파일의 경로를 탐색합니다.
    탐색 순서:
      1. 앱 실행 폴더 (exe와 동일 디렉토리)
      2. 앱 실행 폴더/_internal/
      3. 시스템 환경변수 PATH
    탐색 실패 시 FileNotFoundError("ffmpeg.exe를 앱 폴더에 두세요.")를 발생시킵니다.
    """
    app_dir = get_app_dir()

    candidates = [
        app_dir / "ffmpeg.exe",
        app_dir / "ffmpeg",
        app_dir / "_internal" / "ffmpeg.exe",
        app_dir / "_internal" / "ffmpeg",
    ]

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    # 시스템 PATH 검색
    for name in ("ffmpeg.exe", "ffmpeg"):
        path_which = shutil.which(name)
        if path_which:
            return Path(path_which).resolve()

    raise FileNotFoundError("ffmpeg.exe를 앱 폴더에 두세요.")


def find_ffprobe() -> Optional[Path]:
    """
    ffprobe 실행 파일의 경로를 탐색합니다.
    탐색 순서:
      1. 앱 실행 폴더
      2. 앱 실행 폴더/_internal/
      3. 시스템 환경변수 PATH
    찾지 못하면 None을 반환합니다.
    """
    app_dir = get_app_dir()

    candidates = [
        app_dir / "ffprobe.exe",
        app_dir / "ffprobe",
        app_dir / "_internal" / "ffprobe.exe",
        app_dir / "_internal" / "ffprobe",
    ]

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    for name in ("ffprobe.exe", "ffprobe"):
        path_which = shutil.which(name)
        if path_which:
            return Path(path_which).resolve()

    return None


def parse_duration_from_stderr(stderr_text: str) -> Optional[float]:
    """
    ffmpeg/ffprobe의 stderr 텍스트에서 재생 시간(초)을 추출합니다.
    Duration 라인 우선 탐색, 실패 시 time= 진행 라인의 마지막 값을 탐색합니다.
    """
    match = DURATION_REGEX.search(stderr_text)
    if match:
        h = float(match.group(1))
        m = float(match.group(2))
        s = float(match.group(3))
        return h * 3600.0 + m * 60.0 + s

    time_matches = TIME_REGEX.findall(stderr_text)
    if time_matches:
        last = time_matches[-1]
        h = float(last[0])
        m = float(last[1])
        s = float(last[2])
        return h * 3600.0 + m * 60.0 + s

    return None


def _get_wav_duration(path: Path) -> Optional[float]:
    """표준 라이브러리 wave 모듈을 사용하여 WAV 파일의 길이를 빠르게 측정합니다."""
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return float(frames) / float(rate)
    except Exception:
        pass
    return None


def get_duration(path: Union[str, Path]) -> float:
    """
    오디오 파일의 총 재생 시간(초)을 반환합니다.
    WAV 헤더 확인 -> ffprobe -> ffmpeg 순으로 길이를 추출합니다.
    """
    target_path = Path(path).resolve()
    if not target_path.is_file():
        raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {target_path}")

    # 1. WAV 파일인 경우 파이썬 표준 라이브러리로 즉시 확인
    if target_path.suffix.lower() == ".wav":
        wav_dur = _get_wav_duration(target_path)
        if wav_dur is not None and wav_dur > 0:
            return wav_dur

    # 2. ffprobe 사용 시도
    ffprobe_exe = find_ffprobe()
    if ffprobe_exe:
        try:
            cmd = [
                str(ffprobe_exe),
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(target_path),
            ]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                **_get_subprocess_flags(),
            )
            if res.returncode == 0:
                val = float(res.stdout.strip())
                if val > 0:
                    return val
        except Exception:
            pass

    # 3. ffmpeg -i 로 stderr Duration 파싱
    ffmpeg_exe = find_ffmpeg()
    try:
        cmd = [
            str(ffmpeg_exe),
            "-i", str(target_path),
            "-f", "null",
            "-",
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            **_get_subprocess_flags(),
        )
        duration = parse_duration_from_stderr(res.stderr)
        if duration is not None and duration > 0:
            return duration
    except Exception as e:
        if isinstance(e, FileNotFoundError):
            raise
        pass

    raise RuntimeError(f"오디오 길이를 확인할 수 없습니다: {target_path}")


def convert_to_wav(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    cancel_token: Optional[CancelToken] = None,
) -> float:
    """
    오디오 파일을 16kHz 모노 PCM WAV 형식으로 변환합니다.
    명령어: ffmpeg -y -i <input> -ac 1 -ar 16000 -vn <output>

    Args:
        input_path: 입력 오디오 파일 경로
        output_path: 변환 후 저장될 WAV 파일 경로
        cancel_token: 작업 취소 토큰 (선택 사항)

    Returns:
        float: 변환된 오디오의 총 재생 길이(초)

    Raises:
        FileNotFoundError: ffmpeg.exe 또는 입력 파일이 없는 경우
        CancelledError: 작업이 취소된 경우
        RuntimeError: ffmpeg 변환 실행 중 오류가 발생한 경우
    """
    if cancel_token:
        cancel_token.check()

    in_p = Path(input_path).resolve()
    out_p = Path(output_path).resolve()

    if not in_p.is_file():
        raise FileNotFoundError(f"입력 음성 파일을 찾을 수 없습니다: {in_p}")

    out_p.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg_exe = find_ffmpeg()
    cmd = [
        str(ffmpeg_exe),
        "-y",
        "-i", str(in_p),
        "-ac", "1",
        "-ar", "16000",
        "-vn",
        str(out_p),
    ]

    logger.info("오디오 변환 시작: %s -> %s", in_p.name, out_p.name)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **_get_subprocess_flags(),
    )

    if cancel_token:
        cancel_token.register_process(proc)

    stderr_chunks = []
    cancelled = False

    try:
        while True:
            if cancel_token and cancel_token.is_cancelled():
                cancelled = True
                try:
                    proc.terminate()
                    proc.wait(timeout=0.5)
                except (subprocess.TimeoutExpired, Exception):
                    try:
                        proc.kill()
                    except Exception:
                        pass
                raise CancelledError("사용자에 의해 오디오 변환 작업이 취소되었습니다.")

            try:
                _, stderr_data = proc.communicate(timeout=0.1)
                if stderr_data:
                    stderr_chunks.append(stderr_data)
                break
            except subprocess.TimeoutExpired:
                continue
    finally:
        if cancel_token:
            cancel_token.unregister_process(proc)
        # 실패 또는 취소 시 반쯤 생성된 불완전한 임시 파일 정리
        if (cancelled or proc.returncode != 0) and out_p.is_file():
            try:
                out_p.unlink(missing_ok=True)
            except Exception:
                pass

    full_stderr = "".join(stderr_chunks)

    if proc.returncode != 0:
        if cancel_token and cancel_token.is_cancelled():
            raise CancelledError("사용자에 의해 오디오 변환 작업이 취소되었습니다.")
        err_snippet = full_stderr[-1000:] if len(full_stderr) > 1000 else full_stderr
        raise RuntimeError(
            f"오디오 변환 실패 (ffmpeg 종료 코드 {proc.returncode}):\n{err_snippet}"
        )

    # 길이 측정: 1) ffmpeg 출력 파싱 -> 2) wav 헤더 -> 3) get_duration
    duration = parse_duration_from_stderr(full_stderr)
    if duration is None or duration <= 0:
        duration = _get_wav_duration(out_p)
    if duration is None or duration <= 0:
        try:
            duration = get_duration(out_p)
        except Exception:
            duration = 0.0

    logger.info("오디오 변환 완료: %s (길이: %.2f초)", out_p.name, duration)
    return duration
