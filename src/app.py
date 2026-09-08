# -*- coding: utf-8 -*-
"""
녹취서 자동 생성기 — 메인 UI 창

customtkinter + windnd 기반 데스크톱 팝업.
드래그 앤 드롭 → 작업 시작/취소 → 원본 옆 녹취서 TXT 저장.
"""
import threading
import time
import logging
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field
from enum import Enum

import customtkinter as ctk

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {
    '.m4a', '.mp3', '.wav', '.aac', '.flac',
    '.ogg', '.wma', '.mp4', '.m4b',
}

WINDOW_TITLE = "녹취서 자동 생성기"
WINDOW_WIDTH = 560
WINDOW_HEIGHT = 640
MIN_WIDTH = 520
MIN_HEIGHT = 560


class FileStatus(Enum):
    """파일 처리 상태."""
    WAITING = "대기"
    CONVERTING = "변환중"
    TRANSCRIBING = "전사중"
    DIARIZING = "화자분리중"
    DONE = "완료"
    FAILED = "실패"
    CANCELLED = "취소"


@dataclass
class FileItem:
    """대기열 내 파일 항목."""
    path: Path
    status: FileStatus = FileStatus.WAITING
    error_msg: str = ""
    output_path: Optional[Path] = None


class AppWindow(ctk.CTk):
    """녹취서 자동 생성기 메인 창."""

    def __init__(self):
        super().__init__()

        # ── 설정 로드 ──
        from src.util.config import load_config
        config_obj = load_config()
        self.config = config_obj.to_dict()

        # ── 창 설정 ──
        self.title(WINDOW_TITLE)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(MIN_WIDTH, MIN_HEIGHT)
        self._center_window()

        # 테마
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # ── 상태 ──
        self.file_items: List[FileItem] = []
        self.is_processing = False
        self.worker_thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()

        # ── UI 구성 ──
        self._build_ui()

        # ── 드래그 앤 드롭 설정 ──
        self._setup_drop()

        # ── 종료 처리 ──
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ═══════════════════════════════════════════
    # UI 빌드
    # ═══════════════════════════════════════════
    def _build_ui(self):
        """UI 레이아웃 구성."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # 파일 목록 영역 확장

        # ── 1. 제목/안내 ──
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.grid(row=0, column=0, padx=16, pady=(16, 4), sticky="ew")

        ctk.CTkLabel(
            title_frame,
            text="음성 파일을 이 창으로 끌어다 놓으세요.",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_frame,
            text="지원 형식: m4a, mp3, wav, aac, flac, ogg, wma, mp4(음성)",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(anchor="w", pady=(2, 0))

        # ── 2. 드롭 영역 ──
        self.drop_frame = ctk.CTkFrame(
            self, height=80,
            border_width=2,
            border_color="gray",
            fg_color=("gray95", "gray17"),
        )
        self.drop_frame.grid(row=1, column=0, padx=16, pady=8, sticky="ew")
        self.drop_frame.grid_propagate(False)

        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text="🎵  여기에 파일을 놓으세요",
            font=ctk.CTkFont(size=14),
            text_color="gray",
        )
        self.drop_label.place(relx=0.5, rely=0.5, anchor="center")

        # ── 3. 파일 목록 ──
        list_frame = ctk.CTkFrame(self)
        list_frame.grid(row=2, column=0, padx=16, pady=4, sticky="nsew")
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        self.file_listbox = ctk.CTkTextbox(
            list_frame, height=160,
            font=ctk.CTkFont(family="Consolas", size=12),
            state="disabled",
        )
        self.file_listbox.grid(row=0, column=0, padx=4, pady=4, sticky="nsew")

        # ── 4. 진행 상태 ──
        progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        progress_frame.grid(row=3, column=0, padx=16, pady=4, sticky="ew")
        progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_label = ctk.CTkLabel(
            progress_frame,
            text="대기 중",
            font=ctk.CTkFont(size=12),
            anchor="w",
        )
        self.progress_label.grid(row=0, column=0, sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.progress_bar.set(0)

        # 진행 로그
        self.log_textbox = ctk.CTkTextbox(
            progress_frame, height=100,
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled",
        )
        self.log_textbox.grid(row=2, column=0, sticky="ew", pady=(4, 0))

        # ── 5. 버튼 행 ──
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=4, column=0, padx=16, pady=8, sticky="ew")
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)

        self.cancel_button = ctk.CTkButton(
            button_frame,
            text="작업 취소",
            width=140, height=40,
            fg_color="gray",
            hover_color="darkgray",
            command=self._on_cancel,
        )
        self.cancel_button.grid(row=0, column=0, padx=(0, 8), sticky="e")

        self.start_button = ctk.CTkButton(
            button_frame,
            text="작업 시작",
            width=140, height=40,
            command=self._on_start,
        )
        self.start_button.grid(row=0, column=1, padx=(8, 0), sticky="w")

        # ── 6. 하단 설정 한 줄 ──
        settings_frame = ctk.CTkFrame(self, fg_color="transparent")
        settings_frame.grid(row=5, column=0, padx=16, pady=(0, 12), sticky="ew")

        ctk.CTkLabel(settings_frame, text="모델:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.model_var = ctk.StringVar(value=self.config.get("whisper_model", "large-v3"))
        model_menu = ctk.CTkOptionMenu(
            settings_frame,
            values=["large-v3", "large-v2", "medium", "small", "base", "tiny"],
            variable=self.model_var,
            width=110, height=28,
            font=ctk.CTkFont(size=11),
        )
        model_menu.pack(side="left", padx=(4, 12))

        ctk.CTkLabel(settings_frame, text="장치:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.device_var = ctk.StringVar(value=self.config.get("device", "auto"))
        device_menu = ctk.CTkOptionMenu(
            settings_frame,
            values=["auto", "cuda", "cpu"],
            variable=self.device_var,
            width=80, height=28,
            font=ctk.CTkFont(size=11),
        )
        device_menu.pack(side="left", padx=(4, 12))

        ctk.CTkLabel(settings_frame, text="화자 수:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.speakers_var = ctk.StringVar(value="자동")
        speakers_menu = ctk.CTkOptionMenu(
            settings_frame,
            values=["자동", "2", "3", "4", "5", "6", "7", "8"],
            variable=self.speakers_var,
            width=70, height=28,
            font=ctk.CTkFont(size=11),
        )
        speakers_menu.pack(side="left", padx=(4, 0))

    # ═══════════════════════════════════════════
    # 드래그 앤 드롭
    # ═══════════════════════════════════════════
    def _setup_drop(self):
        """windnd로 드래그 앤 드롭 설정."""
        try:
            import windnd
            windnd.hook_dropfiles(self, func=self._on_drop)
            logger.info("windnd 드래그 앤 드롭 활성화")
        except ImportError:
            logger.warning("windnd를 찾을 수 없습니다. 드래그 앤 드롭이 비활성화됩니다.")
            self.drop_label.configure(text="⚠ windnd 모듈 없음 — 드래그 앤 드롭 불가")
        except Exception as e:
            logger.error("windnd 초기화 실패: %s", e)

    def _decode_path(self, raw: bytes) -> Optional[str]:
        """바이트 경로를 문자열로 디코드. cp949 → mbcs → utf-8 순서."""
        for enc in ('cp949', 'mbcs', 'utf-8', 'utf-8-sig'):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        logger.warning("경로 디코드 실패: %r", raw)
        return None

    def _on_drop(self, file_list):
        """파일 드롭 콜백."""
        added_count = 0
        skipped_count = 0

        for raw_path in file_list:
            # windnd는 바이트 리스트를 줌
            if isinstance(raw_path, bytes):
                decoded = self._decode_path(raw_path)
                if decoded is None:
                    skipped_count += 1
                    continue
                path = Path(decoded)
            else:
                path = Path(str(raw_path))

            # 폴더면 1depth 음성 파일만
            if path.is_dir():
                for child in path.iterdir():
                    if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                        if self._add_file(child):
                            added_count += 1
                continue

            # 지원 확장자 확인
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                logger.info("비지원 파일 건너뜀: %s", path.name)
                skipped_count += 1
                continue

            if self._add_file(path):
                added_count += 1

        self._refresh_file_list()
        self._append_log(f"파일 {added_count}개 추가" +
                         (f" ({skipped_count}개 건너뜀)" if skipped_count else ""))

    def _add_file(self, path: Path) -> bool:
        """파일을 대기열에 추가. 중복이면 False."""
        abs_path = path.resolve()
        for item in self.file_items:
            if item.path.resolve() == abs_path:
                return False
        self.file_items.append(FileItem(path=abs_path))
        return True

    # ═══════════════════════════════════════════
    # 버튼 동작
    # ═══════════════════════════════════════════
    def _on_start(self):
        """작업 시작 버튼."""
        # 처리할 파일이 있는지 확인
        pending = [f for f in self.file_items if f.status == FileStatus.WAITING]
        if not pending:
            self._append_log("처리할 파일이 없습니다. 파일을 드롭해 주세요.")
            return

        if self.is_processing:
            return

        self.is_processing = True
        self.cancel_event.clear()
        self.start_button.configure(state="disabled")

        # 워커 스레드 시작
        self.worker_thread = threading.Thread(
            target=self._worker_run, daemon=True
        )
        self.worker_thread.start()

    def _on_cancel(self):
        """작업 취소 버튼."""
        if not self.is_processing:
            # 처리 중이 아니면 파일 목록 초기화
            self.file_items.clear()
            self._refresh_file_list()
            self._update_progress("대기 중", 0)
            self._append_log("파일 목록을 비웠습니다.")
            return

        self.cancel_event.set()
        self._append_log("취소 요청 중…")

        # cancel_token에 등록된 프로세스도 종료
        try:
            from src.util.cancel import CancelToken
            if hasattr(self, '_cancel_token') and self._cancel_token:
                self._cancel_token.cancel()
        except Exception:
            pass

    def _on_close(self):
        """창 닫기."""
        if self.is_processing:
            from tkinter import messagebox
            if not messagebox.askyesno("종료 확인", "작업 중입니다. 정말 종료할까요?"):
                return
            self.cancel_event.set()
            try:
                from src.util.cancel import CancelToken
                if hasattr(self, '_cancel_token') and self._cancel_token:
                    self._cancel_token.cancel()
            except Exception:
                pass
        self.destroy()

    # ═══════════════════════════════════════════
    # 워커 스레드
    # ═══════════════════════════════════════════
    def _worker_run(self):
        """백그라운드 워커: 파일을 순서대로 처리."""
        from src.util.cancel import CancelToken, CancelledException
        from src.util.config import load_config

        self._cancel_token = CancelToken(self.cancel_event)
        config = load_config().to_dict()

        # 설정 UI 값 반영
        config["whisper_model"] = self.model_var.get()
        config["device"] = self.device_var.get()
        speakers_val = self.speakers_var.get()
        if speakers_val == "자동":
            config["min_speakers"] = None
        else:
            config["min_speakers"] = int(speakers_val)
            config["max_speakers"] = int(speakers_val)

        pending = [f for f in self.file_items if f.status == FileStatus.WAITING]
        total = len(pending)

        for idx, item in enumerate(pending, 1):
            if self.cancel_event.is_set():
                self._update_status(item, FileStatus.CANCELLED)
                continue

            try:
                self._process_file(item, idx, total, config, self._cancel_token)
            except CancelledException:
                self._update_status(item, FileStatus.CANCELLED)
                self.after(0, self._append_log, "사용자 요청으로 작업을 취소했습니다.")
                # 나머지 파일도 취소
                for remaining in pending[idx:]:
                    if remaining.status == FileStatus.WAITING:
                        self._update_status(remaining, FileStatus.CANCELLED)
                break
            except Exception as e:
                logger.error("파일 처리 실패 [%s]: %s", item.path.name, e, exc_info=True)
                item.error_msg = str(e)
                self._update_status(item, FileStatus.FAILED)
                self.after(0, self._append_log, f"❌ {item.path.name}: {e}")

        # 처리 완료
        self.after(0, self._finish_processing)

    def _process_file(self, item: FileItem, idx: int, total: int, config: dict, cancel_token):
        """단일 파일 처리 파이프라인."""
        from src.util.cancel import CancelledException
        from src.util.ffmpeg import convert_to_wav, find_ffmpeg, get_duration
        from src.pipeline.stt import WhisperSTT
        from src.pipeline.diarize import DiarizationEngine
        from src.pipeline.merge import full_merge
        from src.output.render import render_transcript
        from src.output.write import write_transcript, clean_temp_file

        import tempfile
        import os
        from datetime import datetime

        name = item.path.name
        self.after(0, self._update_progress, f"[{idx}/{total}] {name}", (idx - 1) / total)

        # ── 1. ffmpeg 확인 ──
        find_ffmpeg()  # FileNotFoundError if not found

        # ── 2. 변환중 ──
        self._update_status(item, FileStatus.CONVERTING)
        self.after(0, self._append_log, f"🔄 {name}: 오디오 변환 중…")

        temp_dir = tempfile.mkdtemp(prefix="transcript_")
        temp_wav = os.path.join(temp_dir, "temp_16k.wav")

        try:
            cancel_token.check()
            duration = convert_to_wav(str(item.path), temp_wav, cancel_token)
            self.after(0, self._append_log, f"   변환 완료 (길이: {duration:.1f}초)")

            # ── 3. 전사중 ──
            cancel_token.check()
            self._update_status(item, FileStatus.TRANSCRIBING)
            self.after(0, self._append_log, f"🎤 {name}: 음성 전사 중… (모델 준비에 시간이 걸릴 수 있습니다)")

            stt = WhisperSTT.get_instance(config)
            segments = stt.transcribe(
                temp_wav,
                language=config.get("language", "ko"),
                vad_filter=config.get("vad_filter", True),
                cancel_token=cancel_token,
            )
            self.after(0, self._append_log, f"   전사 완료: {len(segments)}개 세그먼트")

            # ── 4. 화자분리중 ──
            cancel_token.check()
            self._update_status(item, FileStatus.DIARIZING)
            self.after(0, self._append_log, f"👥 {name}: 화자 분리 중…")

            diarizer = DiarizationEngine.get_instance(config)
            speaker_segments = diarizer.diarize(
                temp_wav,
                min_speakers=config.get("min_speakers"),
                max_speakers=config.get("max_speakers", 8),
                cancel_token=cancel_token,
            )
            self.after(0, self._append_log, f"   화자 분리 완료: {len(speaker_segments)}개 구간")

            # ── 5. 병합 ──
            cancel_token.check()
            merged = full_merge(segments, speaker_segments)

            # 화자 수 계산
            speakers = set(seg.speaker for seg in merged)
            speaker_count = len(speakers)
            self.after(0, self._append_log, f"   화자 {speaker_count}명 감지")

            # ── 6. 렌더링 ──
            cancel_token.check()
            now = datetime.now()
            metadata = {
                "original_filename": item.path.name,
                "original_path": str(item.path),
                "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                "total_duration": duration,
                "language": config.get("language", "ko"),
                "speaker_count": speaker_count,
                "engine_info": f"faster-whisper {config.get('whisper_model', 'large-v3')} + pyannote",
            }
            text = render_transcript(merged, metadata)

            # ── 7. 저장 ──
            cancel_token.check()
            output_path = write_transcript(item.path, text)
            item.output_path = output_path

            self._update_status(item, FileStatus.DONE)
            self.after(0, self._append_log, f"✅ {name}: 완료 → {output_path.name}")
            self.after(0, self._update_progress, f"[{idx}/{total}] {name} 완료", idx / total)

        finally:
            # 임시 파일 정리
            try:
                if os.path.exists(temp_wav):
                    os.remove(temp_wav)
                os.rmdir(temp_dir)
            except OSError:
                pass
            # 취소 시 임시 txt 정리
            if self.cancel_event.is_set():
                clean_temp_file(item.path)

    def _finish_processing(self):
        """처리 완료 후 UI 복원."""
        self.is_processing = False
        self.start_button.configure(state="normal")

        done = sum(1 for f in self.file_items if f.status == FileStatus.DONE)
        failed = sum(1 for f in self.file_items if f.status == FileStatus.FAILED)
        cancelled = sum(1 for f in self.file_items if f.status == FileStatus.CANCELLED)

        summary = f"완료: {done}"
        if failed:
            summary += f" | 실패: {failed}"
        if cancelled:
            summary += f" | 취소: {cancelled}"
        self._update_progress(summary, 1.0 if not failed and not cancelled else 0)
        self._append_log(f"── 작업 종료 ({summary}) ──")
        self._refresh_file_list()

    # ═══════════════════════════════════════════
    # UI 갱신 (모두 after로 호출)
    # ═══════════════════════════════════════════
    def _update_status(self, item: FileItem, status: FileStatus):
        """파일 상태 갱신 + 목록 새로고침."""
        item.status = status
        self.after(0, self._refresh_file_list)

    def _refresh_file_list(self):
        """파일 목록 텍스트 갱신."""
        self.file_listbox.configure(state="normal")
        self.file_listbox.delete("0.0", "end")

        if not self.file_items:
            self.file_listbox.insert("0.0", "  (파일 없음)")
        else:
            lines = []
            for i, item in enumerate(self.file_items, 1):
                status_icon = {
                    FileStatus.WAITING: "⏳",
                    FileStatus.CONVERTING: "🔄",
                    FileStatus.TRANSCRIBING: "🎤",
                    FileStatus.DIARIZING: "👥",
                    FileStatus.DONE: "✅",
                    FileStatus.FAILED: "❌",
                    FileStatus.CANCELLED: "⛔",
                }.get(item.status, "")

                # 경로를 짧게
                path_str = str(item.path)
                if len(path_str) > 50:
                    path_str = "…" + path_str[-47:]

                line = f"  {i}. {status_icon} [{item.status.value}] {item.path.name}"
                line += f"\n     {path_str}"
                if item.error_msg:
                    line += f"\n     ⚠ {item.error_msg}"
                lines.append(line)

            self.file_listbox.insert("0.0", "\n".join(lines))

        self.file_listbox.configure(state="disabled")

        # 드롭 영역 라벨 갱신
        if self.file_items:
            self.drop_label.configure(text=f"🎵  {len(self.file_items)}개 파일 로드됨")
        else:
            self.drop_label.configure(text="🎵  여기에 파일을 놓으세요")

    def _update_progress(self, text: str, value: float):
        """진행률 라벨과 바 갱신."""
        self.progress_label.configure(text=text)
        self.progress_bar.set(max(0, min(1, value)))

    def _append_log(self, message: str):
        """진행 로그에 한 줄 추가."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", message + "\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")
        logger.info(message)

    # ═══════════════════════════════════════════
    # 유틸
    # ═══════════════════════════════════════════
    def _center_window(self):
        """창을 화면 중앙에 배치."""
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = (screen_w - WINDOW_WIDTH) // 2
        y = (screen_h - WINDOW_HEIGHT) // 2
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")
