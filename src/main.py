# -*- coding: utf-8 -*-
"""
녹취서 자동 생성기 — 메인 진입점

예외를 로그 파일로 기록하고 AppWindow를 실행한다.
"""
import sys
import os
import io
import traceback

# torch / pyannote가 사용하는 표준 라이브러리 모듈 명시적 import (PyInstaller base_library.zip 트리밍 방지)
import timeit
import dis
import opcode
import inspect
import ctypes
import ctypes.wintypes
import unittest
import unittest.mock
import copy
import pickle
import platform
import statistics
import fractions
import decimal
import concurrent.futures
import multiprocessing.pool

# GUI(noconsole) 모드에서 sys.stdout/sys.stderr가 None인 경우 발생하는
# AttributeError: 'NoneType' object has no attribute 'write' 방지
class SafeStream(io.StringIO):
    def write(self, s):
        return len(s) if s else 0
    def flush(self):
        pass
    def isatty(self):
        return False

if sys.stdout is None:
    sys.stdout = SafeStream()
if sys.stderr is None:
    sys.stderr = SafeStream()

# huggingface_hub 및 tqdm의 터미널 진행률 출력 비활성화 (GUI 환경 충돌 방지)
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["TQDM_DISABLE"] = "1"


def main():
    """앱 시작."""
    # 가상환경 .venv site-packages 자동 참조 (frozen 실행 시에도 로컬 패키지 연동)
    from pathlib import Path
    app_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent

    # pyvenv.cfg 기반 기본 Python 표준 라이브러리 경로 탐색 및 sys.path 추가
    cfg_path = app_dir / ".venv" / "pyvenv.cfg"
    if cfg_path.is_file():
        try:
            for line in cfg_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("home ="):
                    py_home = Path(line.split("=", 1)[1].strip())
                    py_lib = py_home / "Lib"
                    if py_lib.is_dir() and str(py_lib) not in sys.path:
                        sys.path.append(str(py_lib))
        except Exception:
            pass

    venv_site = app_dir / ".venv" / "Lib" / "site-packages"
    if venv_site.is_dir():
        if str(venv_site) not in sys.path:
            sys.path.insert(0, str(venv_site))

        # Windows에서 torch, ctranslate2 및 C-extension DLL 디렉터리 등록
        dll_dirs = [
            venv_site / "torch" / "lib",
            venv_site / "ctranslate2",
            venv_site / "onnxruntime" / "capi",
            venv_site / "scipy.libs",
            venv_site / "numpy.libs",
            venv_site / "av.libs",
        ]
        for d in dll_dirs:
            if d.is_dir():
                if hasattr(os, "add_dll_directory"):
                    try:
                        os.add_dll_directory(str(d))
                    except Exception:
                        pass
                os.environ["PATH"] = str(d) + ";" + os.environ.get("PATH", "")

    # Python 표준 라이브러리 경로 보강 (PyInstaller 기본 번들에서 누락된 timeit 등 stdlib 모듈 탐색)
    try:
        import sysconfig
        py_stdlib = sysconfig.get_path("stdlib")
        if py_stdlib and os.path.isdir(py_stdlib) and py_stdlib not in sys.path:
            sys.path.append(py_stdlib)
    except Exception:
        pass

    # 로깅 설정
    from src.util.log import setup_logging, get_logger
    setup_logging()
    logger = get_logger(__name__)

    logger.info("=" * 50)
    logger.info("녹취서 자동 생성기 시작")
    logger.info("Python %s", sys.version)
    logger.info("실행 경로: %s", sys.executable if getattr(sys, 'frozen', False) else __file__)
    logger.info("=" * 50)

    # GPU 정보 로그
    try:
        import torch
        if torch.cuda.is_available():
            logger.info("GPU: %s (CUDA %s)", torch.cuda.get_device_name(0), torch.version.cuda)
        else:
            logger.info("GPU 없음 — CPU 모드로 실행")
    except Exception as e:
        logger.warning("torch 로드 실패: %s", e)

    try:
        from src.app import AppWindow
        app = AppWindow()
        app.mainloop()
    except Exception:
        logger.critical("치명적 오류:\n%s", traceback.format_exc())
        # GUI가 안 뜰 수도 있으니 stderr에도 출력
        traceback.print_exc()
        sys.exit(1)

    logger.info("녹취서 자동 생성기 종료")


if __name__ == "__main__":
    main()
