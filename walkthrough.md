# 녹취서 자동 생성기 Walkthrough

에이전트 AI가 Windows용 로컬 데스크톱 앱을 **처음부터 구현·패키징**하기 위한 기본 설계도다.  
이 문서는 요구사항, 화면 명세, 처리 파이프라인, 산출물 규칙, 구현 순서, 복붙용 프롬프트를 한곳에 모은다.

---

## 0. 한 줄 목표

`m4a` 등 음성 파일을 드래그 앤 드롭하면, **화자가 분리된 법률 실무용 녹취서 TXT**를 **원본 음성 파일이 있는 폴더**에 자동 생성한다. 배포본은 **exe가 폴더 최상위에 있는 onedir 구조**다.

성공 기준 한 줄:

> 앱 폴더 최상위의 `녹취서생성기.exe`를 실행 → 팝업에서 파일 드롭 → `작업 시작` → 원본과 같은 폴더에 `{원본파일명}_녹취서.txt` 생성. `작업 취소`로 중단 가능.

---

## 1. 제품 정의

### 1.1 사용자

개업 변호사가 상담·회의·진술 녹음을 로컬에서 바로 녹취서로 만든다.  
음성 파일은 사건 폴더에 흩어져 있고, 결과는 그 폴더에 같이 두어야 한다.

### 1.2 핵심 동작

1. `녹취서생성기.exe` 실행 시 **작은 팝업 창**이 뜬다.
2. 창에 음성 파일을 **드래그 앤 드롭**한다. 여러 개 가능.
3. `작업 시작`을 누르면 대기열을 순서대로 처리한다.
4. 각 파일마다 같은 폴더에 `{stem}_녹취서.txt`를 만든다.
5. 처리 중 `작업 취소`를 누르면 현재 작업과 대기열을 중단한다.
6. 네트워크 전사는 쓰지 않는다. **로컬 STT + 로컬 화자 분리**만 사용한다.

### 1.3 명시적으로 하지 않는 것

- 클라우드 STT(OpenAI API, Clova, Google 등) 호출
- 화자 실명 자동 식별(성문 등록)
- DOCX/HWPX 변환(1차 범위 밖. TXT만)
- 실시간 마이크 녹음
- 설치 프로그램(NSIS 등) — 1차는 zip/onedir 폴더 배포

---

## 2. 실행·배포 형태

PyInstaller **onedir**만 사용한다. onefile은 시작이 느리고 임시 압축 해제 경로가 꼬인다.

### 2.1 배포 폴더 (필수)

빌드 산출물의 **최상위에 exe가 있어야** 한다.

```text
녹취서생성기/
├─ 녹취서생성기.exe          ← 사용자가 실행하는 앱. 반드시 최상위
├─ ffmpeg.exe                ← 번들(또는 _internal 안, 앱이 탐색 가능)
├─ config.json               ← 최초 실행 시 생성 가능
├─ README.txt
└─ _internal/                ← PyInstaller 의존성, 모델 캐시 경로 등
    ├─ ...site-packages...
    └─ models/               ← 가능하면 여기 또는 %LOCALAPPDATA%
```

금지:

- exe가 `_internal` 안에만 있는 구조
- 소스 실행(`python main.py`)만 되고 exe 빌드 스크립트가 없는 상태
- onefile로 `녹취서생성기.exe` 하나만 만들고 의존성을 숨긴 채 첫 실행 30초 이상 대기

개발 중 프로젝트 루트 권장:

```text
transcript-app/
├─ walkthrough.md
├─ README.md
├─ requirements.txt
├─ build.ps1
├─ 녹취서생성기.spec
├─ config.example.json
├─ src/
│  ├─ main.py
│  ├─ app.py
│  ├─ ui/
│  ├─ pipeline/
│  ├─ output/
│  └─ util/
├─ assets/
│  └─ app.ico
└─ tests/
   └─ fixtures/              ← 짧은 샘플 음성(선택)
```

`build.ps1` 성공 후 `release/녹취서생성기/녹취서생성기.exe`가 생겨야 한다.

---

## 3. UI 명세

프레임워크: **Python 3.11 + tkinter + customtkinter + windnd**.  
Windows 전용. 드래그 앤 드롭은 `windnd.hook_dropfiles`를 사용한다.  
`tkinterdnd2`는 PyInstaller 훅이 불안정하므로 1차에서 쓰지 않는다.

### 3.1 창

| 항목 | 값 |
| --- | --- |
| 제목 | 녹취서 자동 생성기 |
| 크기 | 560 × 640, 최소 520 × 560 |
| 위치 | 화면 중앙 |
| 모드 | 일반 창(팝업처럼 단순). 항상 위는 기본 끄기 |
| 종료 | 처리 중이면 “작업 중인데 종료할까요?” 확인 |

### 3.2 레이아웃 (위→아래)

1. **제목/안내**  
   `음성 파일을 이 창으로 끌어다 놓으세요.`  
   지원 형식: `m4a, mp3, wav, aac, flac, ogg, wma, mp4(음성)`
2. **드롭 영역**  
   점선 박스. 파일이 없으면 `여기에 놓기`. 있으면 파일 목록.
3. **파일 목록**  
   파일명, 경로(짧게), 상태(`대기 / 변환중 / 전사중 / 화자분리중 / 완료 / 실패 / 취소`).
4. **진행 상태**  
   전체 n/m, 현재 파일 진행 로그 4~8줄, determinate progress bar.
5. **버튼 행**  
   왼쪽 `작업 취소`, 오른쪽 `작업 시작`. 둘 다 항상 보인다.
6. **하단 설정 한 줄**  
   모델(`large-v3` 기본), 장치(`auto`: CUDA 있으면 GPU, 없으면 CPU), 화자 수(`자동 / 2 / 3 / 4`).

### 3.3 버튼 동작

**작업 시작**

- 목록이 비어 있으면 시작하지 않고 안내.
- 처리 스레드가 이미 있으면 무시.
- 상태를 `변환중`부터 갱신.
- 처리 중에는 드롭은 가능하되, 새 파일은 대기열 끝에 추가만 한다. 시작 버튼은 비활성.

**작업 취소**

- `threading.Event`(이름: `cancel_event`)를 set.
- ffmpeg/자식 프로세스가 있으면 terminate.
- 현재 파일은 `취소`, 이후 대기 파일도 `취소`.
- 이미 완성된 txt는 삭제하지 않는다.
- 반쯤 쓰인 임시 파일(`*.tmp.txt`)은 삭제한다.
- 취소 후 시작 버튼을 다시 활성화.

### 3.4 드래그 앤 드롭 규칙

- 파일만 허용. 폴더를 떨어뜨리면 그 안의 1depth 음성 파일만 추가.
- 비지원 확장자는 목록에 넣지 않고 로그로 건너뜀.
- 같은 경로 중복 추가는 무시.
- 한글 경로·공백·`()` 모두 지원. `windnd`는 바이트로 오므로 **cp949/mbcs/utf-8 순으로 디코드**한다.

### 3.5 스레드

- UI 스레드에서 모델 로드·전사를 하면 안 된다.
- `pipeline`은 worker thread.
- UI 갱신은 `window.after(0, ...)`만 사용.

---

## 4. 입출력 규칙

### 4.1 입력

지원 확장자:

```text
.m4a .mp3 .wav .aac .flac .ogg .wma .mp4 .m4b
```

전처리: ffmpeg로 **16 kHz / mono / PCM WAV** 임시 파일 생성.

```text
ffmpeg -y -i "<input>" -ac 1 -ar 16000 -vn "<temp.wav>"
```

`ffmpeg.exe` 탐색 순서:

1. exe와 같은 폴더
2. `_internal/ffmpeg.exe`
3. PATH

없으면 작업을 실패 처리하고 “ffmpeg.exe가 앱 폴더에 없습니다”를 표시.

### 4.2 출력 경로 (절대 규칙)

원본이 `D:\사건\김OO\상담_20260908.m4a` 이면 결과는 반드시:

```text
D:\사건\김OO\상담_20260908_녹취서.txt
```

- 앱 설치 폴더에 만들지 않는다.
- 바탕화면에 만들지 않는다.
- stem은 `Path(file).stem` (확장자 제외).
- 이미 파일이 있으면 **덮어쓰지 않는다.**  
  `상담_20260908_녹취서_2.txt`, `_3.txt` … 로 증가.
- 원자적 저장: `{name}.tmp.txt`에 쓴 뒤 `os.replace`.
- 인코딩: **UTF-8 with BOM** (`utf-8-sig`). 메모장·한글·워드 호환.

### 4.3 녹취서 TXT 포맷

법률 실무자가 바로 복사해 쓰도록 고정 포맷을 쓴다.

```text
【녹취서】

■ 원본파일: 상담_20260908.m4a
■ 원본경로: D:\사건\김OO\상담_20260908.m4a
■ 작성일시: 2026-09-08 20:45:12
■ 총길이: 00:12:34
■ 언어: ko
■ 화자 수: 2
■ 엔진: faster-whisper large-v3 + pyannote

※ 본 문서는 자동 생성본입니다. 원본 음성과 대조해 확인하십시오.
※ 화자 라벨은 성명이 아니라 구분용입니다. 필요 시 직접 바꿔 쓰십시오.

────────────────────────────────
[00:00:01] 화자1
안녕하세요. 오늘 상담 내용 녹음해도 될까요?

[00:00:05] 화자2
네, 괜찮습니다.

[00:00:09] 화자1
그럼 사실관계부터 정리하겠습니다.
────────────────────────────────
```

포맷 규칙:

- 화자 라벨은 `SPEAKER_00`이 아니라 **`화자1`, `화자2`** (1부터).
- 같은 화자가 연속 발화하면 **구간을 합친다.** 단 공백이 2초를 넘으면 분리.
- 타임스탬프는 `[HH:MM:SS]` (구간 시작).
- 한 발화 블록: 타임스탬프+화자 줄, 다음 줄 본문, 빈 줄.
- 숫자·날짜·고유명사는 Whisper 결과를 그대로 둔다. 자동 교정은 1차에서 최소만:
  - 양끝 공백 제거
  - 반복 환각 문장(연속 동일 문장 3회 이상) 축약
  - 빈 세그먼트 삭제

---

## 5. 기술 스택

로컬·한국어·화자 분리가 실무 품질의 최소 조건이다.

| 역할 | 선택 | 이유 |
| --- | --- | --- |
| STT | `faster-whisper` + `large-v3` | 원본 Whisper보다 빠르고, 한국어 품질이 실무선 |
| 정렬(선택) | WhisperX alignment 또는 세그먼트 타임스탬프 | 단어 단위까지 가면 pyannote 매칭이 정확 |
| 화자 분리 | `pyannote.audio` diarization | Whisper만으로는 화자를 모름 |
| 오디오 | 번들 `ffmpeg.exe` | m4a/aac 디코드 |
| GUI | customtkinter + windnd | 팝업·드롭·버튼이 단순 |
| 패키징 | PyInstaller onedir | exe가 폴더 최상위 |
| 언어 | Python 3.11 64-bit | torch/whisper 호환 |

1차에서 WhisperX 풀스택을 직접 의존하면 PyInstaller가 자주 깨진다.  
권장 구현은 **직접 파이프라인**:

1. faster-whisper 전사(세그먼트 timestamp)
2. pyannote 화자 구간
3. 구간 겹침(IoU/overlap duration)으로 화자 부여

GPU가 있으면 CUDA, 없으면 CPU `int8`. 앱 시작 시 장치를 로그에 표시.

### 5.1 모델·토큰

pyannote 게이트 모델은 Hugging Face 토큰이 필요하다.

`config.json`:

```json
{
  "whisper_model": "large-v3",
  "device": "auto",
  "compute_type_gpu": "float16",
  "compute_type_cpu": "int8",
  "language": "ko",
  "hf_token": "",
  "min_speakers": null,
  "max_speakers": 8,
  "vad_filter": true
}
```

토큰 탐색 순서:

1. `config.json`의 `hf_token`
2. 환경변수 `HF_TOKEN`
3. `%USERPROFILE%\.cache\huggingface\token`

토큰이 없으면:

- STT만 수행하고 화자는 전부 `화자1`로 두지 **않는다.**
- 작업을 실패 처리하고, 창에  
  `화자 분리 모델 약관 동의 및 HF 토큰이 필요합니다`  
  와 설정 방법을 보여 준다.

최초 실행 시 모델 다운로드가 길 수 있다. 진행 로그에 “모델 준비 중”을 표시한다.  
가능하면 빌드 머신에서 모델을 받아 `_internal/models`에 넣고 오프라인 로드한다.

### 5.2 하드웨어 가이드 (README에 그대로)

- RAM 16 GB 이상 권장
- CPU만: `medium` 또는 `large-v3` + int8, 1시간 녹음에 수십 분 가능
- NVIDIA GPU 8 GB+: `large-v3` 실무 기본
- 1차 기본 모델은 `large-v3`, 설정에서 `medium` 변경 가능

---

## 6. 아키텍처

```text
[UI: AppWindow]
    │ drop files / start / cancel
    ▼
[JobQueue]  파일 경로 리스트 + 상태
    │ worker thread
    ▼
[Pipeline.run(path, cancel_event)]
    ├─ 1. validate extension
    ├─ 2. ffmpeg → temp wav
    ├─ 3. faster-whisper transcribe
    ├─ 4. pyannote diarize
    ├─ 5. assign speakers by overlap
    ├─ 6. merge consecutive turns
    ├─ 7. render 녹취서 text
    └─ 8. atomic write next to source
```

모듈 책임:

| 모듈 | 책임 |
| --- | --- |
| `src/main.py` | 진입점, 예외를 로그 파일로 |
| `src/app.py` | 창, 드롭, 버튼, 진행률 |
| `src/pipeline/stt.py` | faster-whisper 로드/전사 |
| `src/pipeline/diarize.py` | pyannote 로드/추론 |
| `src/pipeline/merge.py` | 세그먼트-화자 매칭, 연속 발화 병합 |
| `src/output/render.py` | 녹취서 문자열 |
| `src/output/write.py` | `{stem}_녹취서.txt` 충돌 회피 저장 |
| `src/util/ffmpeg.py` | ffmpeg 경로, 변환, 길이 조회 |
| `src/util/cancel.py` | Event + 자식 프로세스 핸들 |
| `src/util/config.py` | config.json 읽기/쓰기 |
| `src/util/log.py` | `%LOCALAPPDATA%/녹취서생성기/app.log` |

모델은 싱글톤으로 한 번만 로드한다. 파일마다 다시 로드하지 않는다.

---

## 7. 화자 매칭 알고리즘

입력이 두 갈래다.

- STT 세그먼트: `{start, end, text}`
- 화자 구간: `{start, end, speaker}`

각 STT 세그먼트에 대해 겹치는 시간이 가장 긴 speaker를 부여한다.

```text
overlap = min(seg.end, spk.end) - max(seg.start, spk.start)
```

겹침이 0이면 `화자?`로 두지 말고, 시간상 가장 가까운 화자 구간을 쓴다.  
그래도 없으면 `화자1`.

그다음 같은 화자 연속 구간을 병합한다.  
병합 조건: 화자 동일 AND `next.start - prev.end <= 2.0초`.

화자 ID 정규화:

```text
SPEAKER_00 → 화자1
SPEAKER_01 → 화자2
...
```

등장 순서가 아니라 **레이블 숫자 오름차순**을 화자1부터 매긴다.  
(재실행 시 동일 파일에서 화자 번호가 크게 흔들리지 않게)

---

## 8. 구현 순서 (에이전트가 이 순서를 어기지 말 것)

한 단계가 검수 기준을 통과하기 전에 다음 단계로 가지 않는다.

### Phase 0 — 골격

- 가상환경, `requirements.txt`, 패키지 구조, `main.py`가 빈 창을 띄움
- `build.ps1` 초안

### Phase 1 — UI만

- 드롭, 목록, `작업 시작`/`작업 취소`
- 시작 시 실제 전사는 하지 않고 1초 sleep으로 상태 전이를 시뮬레이션
- 취소가 sleep 루프를 끊는지 확인

### Phase 2 — 출력 경로

- 더미 텍스트라도 **원본 옆**에 `{stem}_녹취서.txt` 생성
- 한글 경로, 이미 존재하는 파일 `_2` 증가, BOM 확인

### Phase 3 — ffmpeg

- 실제 m4a → wav, 실패 메시지, 임시파일 삭제(`finally`)

### Phase 4 — STT

- faster-whisper, 언어 `ko`, 세그먼트 로그
- GPU/CPU 자동

### Phase 5 — 화자 분리 + 병합 + 포맷

- pyannote, 매칭, 최종 템플릿

### Phase 6 — 안정화

- 취소가 ffmpeg/추론 중간에 먹히는지
- 다중 파일 큐
- 예외 시 해당 파일만 `실패`, 다음 파일 계속
- 로그 파일

### Phase 7 — 패키징

- spec, ffmpeg 동봉, exe 최상위
- 다른 PC(또는 깨끗한 경로)에서 exe만으로 실행

---

## 9. 검수 체크리스트

에이전트는 각 Phase 끝에 이 목록을 스스로 실행하고 결과를 보고한다.

기능

- [ ] exe가 배포 폴더 최상위에 있다
- [ ] 실행 즉시 팝업(메인 창)이 뜬다
- [ ] 창에 `작업 시작`, `작업 취소`가 있다
- [ ] m4a를 드롭하면 목록에 한글 파일명이 깨지지 않는다
- [ ] 시작 후 원본 폴더에 `{stem}_녹취서.txt`가 생긴다
- [ ] 앱 폴더에는 녹취서가 생기지 않는다
- [ ] 본문에 `화자1` 등 화자 라벨과 `[HH:MM:SS]`가 있다
- [ ] 동일 이름 재실행 시 `_2`가 붙고 원본 txt를 덮어쓰지 않는다
- [ ] 취소 시 새 txt가 더 이상 늘지 않는다
- [ ] 지원하지 않는 `.pdf` 드롭은 무시된다
- [ ] 두 파일을 드롭하면 순서대로 두 개의 txt가 생긴다

품질

- [ ] 2화자 샘플에서 화자가 최소 2개로 나뉜다
- [ ] 연속 동일 화자 줄이 과도하게 쪼개지지 않는다
- [ ] UTF-8 BOM이라 메모장에서 한글이 깨지지 않는다

안정

- [ ] UI가 전사 중  freeze되지 않는다
- [ ] 실패 파일이 전체 큐를 죽이지 않는다
- [ ] 임시 wav가 작업 후 삭제된다
- [ ] `%LOCALAPPDATA%/녹취서생성기/app.log`에 오류가 남는다

---

## 10. 의존성 초안

`requirements.txt` 방향. 버전은 구현 시 호환되는 최신 고정 버전을 잠근다.

```text
customtkinter
windnd
faster-whisper
pyannote.audio
torch
torchaudio
soundfile
numpy
pyinstaller
```

주의:

- Windows에서 torch는 CPU/CUDA 휠이 다르다. `build.ps1`에 설치 명령을 명시한다.
- `pyannote.audio`와 torch 버전 충돌이 나면 **화자 분리 가능한 조합을 우선**하고 WhisperX 전체 설치로 도망가지 않는다.
- `onnxruntime` 등이 따라오면 spec의 hiddenimports에 넣는다.

---

## 11. 빌드 스크립트 요구

`build.ps1`:

1. `.venv` 사용
2. `pyinstaller --noconfirm --clean 녹취서생성기.spec`
3. `ffmpeg.exe`를 `dist/녹취서생성기/` **최상위**로 복사
4. `config.example.json`을 `config.json`으로 복사(이미 있으면 유지)
5. `README.txt` 복사
6. 완료 후 `dist/녹취서생성기/녹취서생성기.exe` 존재 여부를 검사하고 실패 시 exit 1

spec 요지:

- `console=False` (windoowed). 대신 로그 파일.
- `name='녹취서생성기'`
- onedir (`COLLECT`)
- 아이콘 있으면 사용
- `datas`에 필요한 모델/에셋만. site-packages 전체를 수동 복사하지 말 것

---

## 12. 에러 메시지 (사용자에게 보이는 문장)

기술 스택 트레이스백을 팝업에 그대로 뿌리지 않는다. 짧은 한국어.

| 상황 | 메시지 |
| --- | --- |
| ffmpeg 없음 | ffmpeg.exe를 앱 폴더에 두세요. |
| 토큰 없음 | 화자 분리를 위해 Hugging Face 토큰이 config.json에 필요합니다. |
| CUDA OOM | 메모리 부족. 설정에서 모델을 medium으로 낮추세요. |
| 깨진 오디오 | 이 파일은 읽지 못했습니다. 재생 가능한 파일인지 확인하세요. |
| 권한 | 녹취서를 저장할 수 없습니다. 폴더 쓰기 권한을 확인하세요. |
| 취소 | 사용자 요청으로 작업을 취소했습니다. |

상세는 로그 파일 경로를 한 줄 더 보여 준다.

---

## 13. 에이전트 운영 규칙

- 한국어 주석·커밋 메시지·UI 문구.
- 추측으로 API를 바꾸지 말고, 이 문서의 파일명 규칙·버튼 문구를 그대로 쓴다.
- “나중에 넣으면 됩니다”로 화자 분리를 빼지 않는다. 화자 분리가 안 되면 미완료다.
- GUI를 웹서버/브라우저로 대체하지 않는다.
- 결과 파일을 앱 디렉터리에 저장하는 구현은 오답이다.
- 비밀키를 소스에 하드코딩하지 않는다.
- 테스트용으로 긴 유튜브 음원을 받지 않는다. 수 초~1분 샘플만.

---

## 14. 복붙용 프롬프트

아래를 순서대로 에이전트에 넣는다.  
시스템/마스터를 먼저 넣고, Phase 프롬프트는 한 번에 하나만.

### 14.1 마스터 프롬프트 (항상 유지)

```text
당신은 Windows 데스크톱 앱을 구현하는 시니어 Python 엔지니어다.
작업 루트의 walkthrough.md가 유일한 제품 명세다. 추측으로 요구사항을 바꾸지 마라.

목표:
음성 파일(m4a 등)을 드래그 앤 드롭하면 화자가 분리된 녹취서 TXT를
원본 음성 파일이 있는 폴더에 {원본stem}_녹취서.txt 로 생성하는 로컬 앱.

필수 제약:
1) 배포는 PyInstaller onedir. exe는 배포 폴더 최상위. 이름은 녹취서생성기.exe.
2) 실행 시 데스크톱 팝업(메인 창)이 뜬다. 웹 UI 금지.
3) 창에 버튼 문구 그대로: "작업 시작", "작업 취소".
4) 입력은 드래그 앤 드롭. windnd 사용. 한글 경로 깨지면 실패다.
5) 출력은 원본과 같은 디렉터리. 앱 폴더/바탕화면 저장 금지.
6) 이미 *_녹취서.txt가 있으면 덮어쓰지 말고 _2, _3...
7) UTF-8 BOM. 화자 라벨은 화자1, 화자2. 타임스탬프 [HH:MM:SS].
8) STT는 faster-whisper, 화자 분리는 pyannote. 클라우드 STT 금지.
9) UI 스레드에서 추론 금지. cancel_event로 취소.
10) ffmpeg.exe를 앱이 찾을 수 있게 번들.

구현 전 walkthrough.md를 읽고, 지금 단계의 완료 조건만 구현하라.
매 응답 마지막에: 변경 파일 목록, 직접 확인한 체크리스트, 다음 단계 한 줄을 적어라.
통과하지 못한 항목이 있으면 Phase를 끝내지 마라.
```

### 14.2 Phase 0 프롬프트

```text
walkthrough.md Phase 0만 수행하라.

할 일:
- Python 3.11 전제 프로젝트 골격 생성
- src/main.py, src/app.py (빈 창 + 제목 "녹취서 자동 생성기")
- requirements.txt, config.example.json, README.md
- .gitignore (venv, dist, build, __pycache__, *.wav temp)
아직 빌드 성공까지 가지 말고 spec 초안과 build.ps1 뼈대만 둔다.
customtkinter 창이 560x640, 화면 중앙에 뜨면 완료.
```

### 14.3 Phase 1 프롬프트

```text
walkthrough.md Phase 1만 수행하라.

할 일:
- 드롭 영역, 파일 목록, 진행 로그, progress bar
- 버튼 "작업 취소" 왼쪽, "작업 시작" 오른쪽
- windnd로 파일 드롭. 한글 경로 디코드 처리
- 작업 시작 시 worker thread에서 파일마다 상태를
  대기→변환중→전사중→화자분리중→완료 로 1초 간격 시뮬레이션
- 작업 취소 시 Event set, 남은 파일 취소
실제 whisper/pyannote 호출 금지.
시뮬레이션만으로 시작/취소/다중파일이 되면 완료.
```

### 14.4 Phase 2 프롬프트

```text
walkthrough.md Phase 2만 수행하라.

할 일:
- 시뮬레이션 완료 시 더미 녹취서 텍스트를 원본 파일과 같은 폴더에 저장
- 파일명 규칙: {stem}_녹취서.txt
- 충돌 시 _2, _3
- utf-8-sig, 임시파일 후 os.replace
- 저장 경로가 앱 cwd가 아님을 단위 함수로 검증하는 테스트 작성
샘플 경로 예: C:\테스트폴더\상담.m4a → C:\테스트폴더\상담_녹취서.txt
이 규칙이 깨지면 이후 Phase를 진행하지 마라.
```

### 14.5 Phase 3 프롬프트

```text
walkthrough.md Phase 3만 수행하라.

할 일:
- src/util/ffmpeg.py
- exe 옆, _internal, PATH 순으로 ffmpeg.exe 탐색
- m4a/mp3/wav를 16kHz mono wav로 변환
- 실패 시 사용자용 한국어 메시지
- 변환 후 길이를 로그에 표시
- finally에서 temp wav 삭제 (단, 다음 Phase가 바로 쓸 때는 Pipeline이 삭제를 책임)
작업 취소를 ffmpeg 실행 중에도 가능하게 Popen + terminate.
```

### 14.6 Phase 4 프롬프트

```text
walkthrough.md Phase 4만 수행하라.

할 일:
- faster-whisper 싱글톤 로더
- device auto (cuda 있으면 cuda, 없으면 cpu)
- language="ko", vad_filter=True
- 세그먼트 {start,end,text} 리스트 반환
- UI 로그에 부분 문장 스트리밍처럼 최근 줄을 보여 줘도 된다
- 아직 화자 분리 없이 저장하지 마라. 세그먼트는 메모리/콜백으로만.
GPU 없으면 medium 폴백을 config로 가능하게 하되 기본값은 large-v3.
모델 로드는 첫 작업 시작 시 한 번만.
```

### 14.7 Phase 5 프롬프트

```text
walkthrough.md Phase 5만 수행하라. 이 Phase가 제품의 핵심이다.

할 일:
- pyannote diarization. hf token은 config/env/캐시 순
- STT 세그먼트와 화자 구간 overlap 매칭
- SPEAKER_00 → 화자1 매핑
- 2초 이내 동일 화자 병합
- walkthrough.md 4.3 템플릿 그대로 렌더링
- 원본 옆에 {stem}_녹취서.txt 저장
토큰 없으면 화자 없이 저장하지 말고 실패 처리.
짧은 2화자 샘플이 있으면 돌려보고, 화자 수가 2 이상으로 나오는지 로그로 보고하라.
```

### 14.8 Phase 6 프롬프트

```text
walkthrough.md Phase 6만 수행하라.

할 일:
- 파일 단위 try/except. 한 파일 실패가 큐를 멈추지 않음
- 취소 시 tmp txt 삭제, 완료분 유지
- %LOCALAPPDATA%\녹취서생성기\app.log
- 처리 중 종료 확인 대화상자
- 드롭된 비지원 확장자 안내
- README.md에 HF 토큰, ffmpeg, GPU, 출력 규칙 작성
체크리스트 기능/안정 항목을 모두 손으로 확인한 것처럼 항목별 OK/NG를 보고하라.
```

### 14.9 Phase 7 프롬프트

```text
walkthrough.md Phase 7만 수행하라.

할 일:
- 녹취서생성기.spec onedir, console=False, 이름 녹취서생성기
- hiddenimports는 실제 빌드 오류를 보고 추가
- build.ps1이 dist/녹취서생성기/녹취서생성기.exe 를 만들고
  그 폴더 최상위에 ffmpeg.exe를 복사
- 빌드 산출물에서 python 없이 exe를 실행해 창이 뜨는지 확인
exe가 _internal 안에만 있으면 실패다. COLLECT 구조를 고쳐라.
README.txt를 배포 폴더 최상위에 포함하라.
```

### 14.10 수정용 짧은 프롬프트

버그가 났을 때만 사용.

```text
walkthrough.md를 기준으로 회귀를 고쳐라.
바꾸지 말 것: 출력 파일명 {stem}_녹취서.txt, 저장 위치=원본 폴더,
버튼 문구, exe 최상위, 로컬 STT+화자분리.
지금 증상: {여기에 증상}
재현: {단계}
기대: {기대}
수정 후 관련 체크리스트만 재확인하라.
```

---

## 15. 에이전트에게 줄 수락 테스트 시나리오

개발 PC에서 수동으로 이 순서만 통과하면 1차 완료다.

1. `build.ps1` 실행 → `release` 또는 `dist/녹취서생성기/녹취서생성기.exe` 존재.
2. exe 더블클릭 → 창 제목 `녹취서 자동 생성기`, 버튼 두 개 보임.
3. 한글 경로 폴더의 `회의.m4a`를 창에 드롭.
4. `작업 시작` 클릭.
5. 같은 폴더에 `회의_녹취서.txt` 생성.
6. 메모장으로 열어 한글 정상, `화자1`/`화자2`, 타임스탬프 확인.
7. 다시 시작 → `회의_녹취서_2.txt` 생성, 기존 파일 유지.
8. 긴 파일 처리 중 `작업 취소` → 상태가 취소, 추가 산출 없음.
9. `config.json`과 로그 경로가 README와 일치.

---

## 16. 이후 확장 (1차 금지, 설계만 메모)

2차에 넣어도 되는 것. 지금 구현하지 말 것.

- 화자 이름 수동 매핑(화자1=의뢰인)
- HWPX/DOCX보내기
- 재생 바+클릭 시 해당 구간 재생
- 배심/속기 스타일 템플릿 선택
- GPU 없는 PC용 별도 lite 빌드(`medium` 고정)

1차 범위가 늘어나면 exe 배포가 실패하기 쉽다.  
**팝업 + 드롭 + 시작/취소 + 원본 옆 `_녹취서.txt` + 화자 분리**만 닫는다.
