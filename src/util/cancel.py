"""작업 취소 토큰 및 자식 프로세스 생명주기 관리 모듈."""

import subprocess
import threading
from typing import Set


class CancelledException(Exception):
    """작업이 사용자에 의해 취소되었을 때 발생하는 예외."""

    pass


# CancelledError 별칭 호환성 제공
CancelledError = CancelledException


class CancelToken:
    """작업 취소 제어 및 자식 프로세스 생명주기를 관리하는 클래스."""

    def __init__(self, event: threading.Event = None) -> None:
        self._event = event if event is not None else threading.Event()
        self._processes: Set[subprocess.Popen] = set()
        self._lock = threading.Lock()

    def register_process(self, proc: subprocess.Popen) -> None:
        """취소 시 함께 종료할 자식 프로세스를 등록합니다."""
        with self._lock:
            self._processes.add(proc)

    def unregister_process(self, proc: subprocess.Popen) -> None:
        """완료된 자식 프로세스를 등록 해제합니다."""
        with self._lock:
            self._processes.discard(proc)

    def cancel(self) -> None:
        """취소 이벤트를 설정하고 등록된 모든 자식 프로세스를 종료합니다."""
        self._event.set()
        with self._lock:
            for proc in list(self._processes):
                try:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=0.5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                except Exception:
                    pass
            self._processes.clear()

    def check(self) -> None:
        """취소 여부를 검사하고, 취소 상태인 경우 CancelledError를 발생시킵니다."""
        if self._event.is_set():
            raise CancelledError("작업이 사용자에 의해 취소되었습니다.")

    def is_cancelled(self) -> bool:
        """취소 상태인지 여부를 반환합니다."""
        return self._event.is_set()

    def is_set(self) -> bool:
        """threading.Event 인터페이스 호환을 위한 메서드."""
        return self._event.is_set()

    def reset(self) -> None:
        """새 작업을 위해 취소 상태와 등록 프로세스 목록을 초기화합니다."""
        self._event.clear()
        with self._lock:
            self._processes.clear()
