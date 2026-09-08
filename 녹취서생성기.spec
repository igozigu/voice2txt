# -*- mode: python ; coding: utf-8 -*-
"""
녹취서 자동 생성기 PyInstaller spec 파일

빌드: pyinstaller --noconfirm --clean 녹취서생성기.spec
결과: dist/녹취서생성기/녹취서생성기.exe (onedir, 최상위)
"""

import sys
from pathlib import Path

block_cipher = None

# 프로젝트 루트
PROJECT_ROOT = Path(SPECPATH)

a = Analysis(
    [str(PROJECT_ROOT / 'src' / 'main.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # config 예시
        (str(PROJECT_ROOT / 'config.example.json'), '.'),
    ],
    hiddenimports=[
        # customtkinter
        'customtkinter',
        # windnd
        'windnd',
        # faster-whisper 관련
        'faster_whisper',
        'ctranslate2',
        # pyannote 관련
        'pyannote.audio',
        'pyannote.audio.pipelines',
        'pyannote.core',
        'pyannote.pipeline',
        # torch 관련
        'torch',
        'torchaudio',
        'torchaudio.lib',
        # soundfile
        'soundfile',
        # 기타
        'numpy',
        'sklearn',
        'sklearn.cluster',
        'sklearn.utils',
        'speechbrain',
        'onnxruntime',
        'huggingface_hub',
        # 표준 라이브러리
        'logging.handlers',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'tkinter.test',
        'unittest',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,     # onedir: 바이너리를 COLLECT로 분리
    name='녹취서생성기',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,              # windowed (콘솔 없음)
    disable_windowed_traceback=False,
    # icon=str(PROJECT_ROOT / 'assets' / 'app.ico'),  # 아이콘 있으면 활성화
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='녹취서생성기',        # dist/녹취서생성기/ 폴더명
)
