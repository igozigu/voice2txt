"""로깅 설정 모듈 (%LOCALAPPDATA%/녹취서생성기/app.log 및 stderr)."""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_is_logging_setup = False


def get_log_dir() -> Path:
    """로그 디렉토리 경로(%LOCALAPPDATA%/녹취서생성기)를 반환하고 디렉토리를 생성합니다."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        local_app_data = str(Path.home() / "AppData" / "Local")
    log_dir = Path(local_app_data) / "녹취서생성기"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_path() -> Path:
    """로그 파일(app.log)의 전체 경로를 반환합니다."""
    return get_log_dir() / "app.log"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """
    애플리케이션 전역 로깅을 설정합니다.
    - %LOCALAPPDATA%/녹취서생성기/app.log 에 RotatingFileHandler (5MB, 3개 백업)
    - stderr 에 StreamHandler 출력 (개발 및 콘솔 확인용)
    """
    global _is_logging_setup
    root_logger = logging.getLogger()

    if _is_logging_setup:
        return logging.getLogger("녹취서생성기")

    root_logger.setLevel(level)

    # 포맷 설정
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. 파일 핸들러 (5MB 회전, 3개 보관, UTF-8)
    try:
        log_file = get_log_path()
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        sys.stderr.write(f"[WARNING] 로그 파일 핸들러 설정 실패: {e}\n")

    # 2. 콘솔/표준 에러 핸들러
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    _is_logging_setup = True

    logger = logging.getLogger("녹취서생성기")
    logger.info("로깅 초기화 완료. 로그 경로: %s", get_log_path())
    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    모듈별 로거를 반환합니다.
    로깅이 아직 설정되지 않은 경우 기본 설정을 수행합니다.
    """
    if not _is_logging_setup:
        setup_logging()
    return logging.getLogger(name or "녹취서생성기")
