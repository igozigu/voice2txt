"""설정 관리 모듈 (config.json 읽기/쓰기 및 Hugging Face 토큰 탐색)."""

import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


def get_app_dir() -> Path:
    """앱 실행 디렉토리를 반환합니다 (배포 시 exe 위치, 개발 시 프로젝트 루트)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # src/util/config.py -> 프로젝트 루트 (voice2txt)
    return Path(__file__).resolve().parent.parent.parent


@dataclass
class AppConfig:
    """녹취서 자동 생성기 설정 데이터클래스."""

    whisper_model: str = "large-v3"
    device: str = "auto"
    compute_type_gpu: str = "float16"
    compute_type_cpu: str = "int8"
    language: str = "ko"
    hf_token: str = ""
    min_speakers: Optional[int] = None
    max_speakers: Optional[int] = 8
    vad_filter: bool = True

    def to_dict(self) -> dict:
        """설정을 딕셔너리로 변환합니다."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        """딕셔너리로부터 설정을 생성하며, 유효하지 않은 키는 무시합니다."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


def get_config_path() -> Path:
    """
    config.json 파일의 탐색 우선순위 경로를 반환합니다.
    1. exe (또는 앱 실행) 디렉토리
    2. 현재 작업 디렉토리(CWD)
    어디에도 파일이 없으면 기본적으로 앱 디렉토리의 config.json 경로를 반환합니다.
    """
    app_dir = get_app_dir()
    app_config = app_dir / "config.json"
    if app_config.is_file():
        return app_config

    cwd_config = Path.cwd() / "config.json"
    if cwd_config.is_file():
        return cwd_config

    return app_config


# 싱글톤 인스턴스 보관 변수
_config_instance: Optional[AppConfig] = None


def load_config(path: Optional[Path] = None) -> AppConfig:
    """
    설정 파일에서 설정을 불러옵니다.
    config.json이 존재하지 않으면 기본 설정으로 파일을 새로 생성합니다.
    """
    config_path = path or get_config_path()
    if not config_path.is_file():
        config = AppConfig()
        save_config(config, config_path)
        return config

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AppConfig.from_dict(data)
    except Exception:
        # 파일이 손상되었거나 읽을 수 없는 경우 기본 설정 반환
        return AppConfig()


def save_config(config: Optional[AppConfig] = None, path: Optional[Path] = None) -> None:
    """
    현재 설정 객체를 config.json 파일에 UTF-8 형식으로 저장합니다.
    """
    global _config_instance
    target_config = config or _config_instance or AppConfig()
    config_path = path or get_config_path()

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(target_config.to_dict(), f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_config(reload: bool = False) -> AppConfig:
    """
    싱글톤 패턴으로 AppConfig 인스턴스를 반환합니다.
    첫 호출 시 자동으로 config.json을 로드하거나 생성합니다.
    """
    global _config_instance
    if _config_instance is None or reload:
        _config_instance = load_config()
    return _config_instance


def set_config(config: AppConfig) -> None:
    """싱글톤 설정 인스턴스를 직접 설정합니다."""
    global _config_instance
    _config_instance = config


def get_hf_token(config: Optional[AppConfig] = None) -> str:
    """
    Hugging Face 토큰을 다음 우선순위로 탐색하여 반환합니다:
    1. config.json의 hf_token
    2. 환경변수 HF_TOKEN (또는 HUGGING_FACE_HUB_TOKEN)
    3. %USERPROFILE%/.cache/huggingface/token 파일
    """
    # 1) config.json
    cfg = config or get_config()
    if cfg.hf_token and cfg.hf_token.strip():
        return cfg.hf_token.strip()

    # 2) 환경변수 HF_TOKEN / HUGGING_FACE_HUB_TOKEN
    env_token = os.environ.get("HF_TOKEN", "").strip()
    if env_token:
        return env_token
    hub_token = os.environ.get("HUGGING_FACE_HUB_TOKEN", "").strip()
    if hub_token:
        return hub_token

    # 3) %USERPROFILE%/.cache/huggingface/token
    user_profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    cache_token_path = Path(user_profile) / ".cache" / "huggingface" / "token"
    if cache_token_path.is_file():
        try:
            token = cache_token_path.read_text(encoding="utf-8").strip()
            if token:
                return token
        except Exception:
            pass

    return ""
