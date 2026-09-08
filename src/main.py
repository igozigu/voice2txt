# -*- coding: utf-8 -*-
"""
녹취서 자동 생성기 — 메인 진입점

예외를 로그 파일로 기록하고 AppWindow를 실행한다.
"""
import sys
import os
import traceback


def main():
    """앱 시작."""
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
