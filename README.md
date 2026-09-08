# 녹취서 자동 생성기

음성 파일(m4a, mp3, wav 등)을 드래그 앤 드롭하면 **화자가 분리된 법률 실무용 녹취서 TXT**를 자동 생성하는 Windows 데스크톱 앱입니다.

## 주요 기능

- **드래그 앤 드롭**: 음성 파일을 창에 놓기만 하면 됩니다
- **화자 분리**: pyannote.audio 기반, 화자1/화자2/… 자동 구분
- **로컬 처리**: 인터넷 전송 없이 PC에서 직접 처리 (기밀 보장)
- **법률 실무 포맷**: `[HH:MM:SS] 화자N` 형식, UTF-8 BOM
- **원본 옆 저장**: 결과가 원본 음성 파일과 같은 폴더에 생성

## 설치 및 실행

### 필수 준비물

1. **ffmpeg.exe**: 앱 폴더(`녹취서생성기.exe` 옆)에 배치
   - 다운로드: https://www.gyan.dev/ffmpeg/builds/ (essentials 권장)

2. **Hugging Face 토큰**: 화자 분리 모델 사용에 필요
   - https://huggingface.co/settings/tokens 에서 토큰 생성
   - https://huggingface.co/pyannote/speaker-diarization-3.1 에서 약관 동의
   - https://huggingface.co/pyannote/segmentation-3.0 에서 약관 동의
   - `config.json`의 `hf_token` 필드에 입력

3. **GPU 권장** (없어도 동작)
   - NVIDIA GPU 8GB+ VRAM: `large-v3` 모델 사용 가능
   - CPU만: `int8` 양자화로 동작하지만 처리 시간이 김

### 실행

1. `녹취서생성기.exe` 더블클릭
2. 음성 파일을 창에 드래그 앤 드롭
3. `작업 시작` 클릭
4. 원본 파일과 같은 폴더에 `{파일명}_녹취서.txt` 생성

## 설정 (`config.json`)

```json
{
    "whisper_model": "large-v3",
    "device": "auto",
    "compute_type_gpu": "float16",
    "compute_type_cpu": "int8",
    "language": "ko",
    "hf_token": "여기에_HF_토큰_입력",
    "min_speakers": null,
    "max_speakers": 8,
    "vad_filter": true
}
```

| 항목 | 설명 | 기본값 |
|------|------|--------|
| `whisper_model` | STT 모델 | `large-v3` |
| `device` | 장치 (`auto`/`cuda`/`cpu`) | `auto` |
| `language` | 언어 코드 | `ko` |
| `hf_token` | Hugging Face API 토큰 | (비어 있음) |
| `max_speakers` | 최대 화자 수 | `8` |

## 출력 규칙

- **저장 위치**: 원본 음성 파일과 **같은 폴더**
- **파일명**: `{원본파일명}_녹취서.txt`
- **충돌 시**: `_녹취서_2.txt`, `_3.txt` … (기존 파일 보존)
- **인코딩**: UTF-8 with BOM (`utf-8-sig`) — 메모장/한글/워드 호환
- **화자 라벨**: `화자1`, `화자2` (성명이 아닌 구분용)

## 하드웨어 가이드

- **RAM**: 16GB 이상 권장
- **CPU만**: 1시간 녹음에 수십 분 소요 가능. `medium` 모델 권장
- **NVIDIA GPU 8GB+**: `large-v3` 사용 가능, 실시간 이상 속도

## 로그

오류 발생 시 아래 경로에서 로그를 확인하세요:

```
%LOCALAPPDATA%\녹취서생성기\app.log
```

## 지원 형식

`m4a`, `mp3`, `wav`, `aac`, `flac`, `ogg`, `wma`, `mp4`(음성), `m4b`

## 개발

```powershell
# 가상환경 생성 및 실행
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 개발 실행
python -m src.main

# 빌드
.\build.ps1
```

## 기술 스택

| 역할 | 라이브러리 |
|------|-----------|
| STT | faster-whisper + large-v3 |
| 화자 분리 | pyannote.audio 3.x |
| GUI | customtkinter + windnd |
| 오디오 | ffmpeg (번들) |
| 패키징 | PyInstaller onedir |

## 라이선스

내부 사용 전용
