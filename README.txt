╔════════════════════════════════════════════╗
║          녹취서 자동 생성기                 ║
╚════════════════════════════════════════════╝

■ 실행 방법
  녹취서생성기.exe를 더블클릭하세요.

■ 사전 준비
  1. ffmpeg.exe를 이 폴더(녹취서생성기.exe 옆)에 두세요.
     다운로드: https://www.gyan.dev/ffmpeg/builds/
  2. config.json의 hf_token에 Hugging Face 토큰을 입력하세요.
     토큰 생성: https://huggingface.co/settings/tokens
     모델 약관 동의:
       - https://huggingface.co/pyannote/speaker-diarization-3.1
       - https://huggingface.co/pyannote/segmentation-3.0

■ 사용법
  1. 녹취서생성기.exe 실행
  2. 음성 파일(m4a, mp3, wav 등)을 창에 끌어다 놓기
  3. [작업 시작] 클릭
  4. 원본 파일과 같은 폴더에 {파일명}_녹취서.txt 생성

■ 결과 저장 위치
  원본 음성 파일과 같은 폴더에 저장됩니다.
  예) D:\사건\김OO\상담.m4a → D:\사건\김OO\상담_녹취서.txt
  같은 이름이 있으면 _2, _3으로 번호가 붙습니다.

■ 설정 변경
  config.json을 메모장으로 열어 수정하세요.
  - whisper_model: STT 모델 (large-v3, medium 등)
  - device: 장치 (auto, cuda, cpu)
  - hf_token: Hugging Face 토큰

■ 문제 해결
  - 오류 로그: %LOCALAPPDATA%\녹취서생성기\app.log
  - GPU 메모리 부족: config.json에서 모델을 medium으로 변경
  - 한글 깨짐: 결과 파일은 UTF-8 BOM으로 저장됩니다

■ 지원 형식
  m4a, mp3, wav, aac, flac, ogg, wma, mp4(음성), m4b
