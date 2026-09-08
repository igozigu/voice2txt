# -*- coding: utf-8 -*-
"""
녹취서 자동 생성기 — 메인 진입점

예외를 로그 파일로 기록하고 AppWindow를 실행한다.
"""
import sys
import os
import io
import traceback

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
    venv_site = app_dir / ".venv" / "Lib" / "site-packages"
    if venv_site.is_dir() and str(venv_site) not in sys.path:
        sys.path.insert(0, str(venv_site))

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
    except ImportError:
        logger.warning("torch를 찾을 수 없습니다")

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
