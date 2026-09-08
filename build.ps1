# build.ps1 — 녹취서 자동 생성기 빌드 스크립트
# 사용법: PowerShell에서 .\build.ps1 실행
# 전제: Python 3.11 64-bit, ffmpeg.exe가 PATH 또는 프로젝트 루트에 있을 것

param(
    [switch]$Clean,
    [switch]$SkipVenv
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$VenvDir = Join-Path $ProjectRoot ".venv"
$DistDir = Join-Path $ProjectRoot "dist"
$OutputDir = Join-Path $DistDir "녹취서생성기"
$ExePath = Join-Path $OutputDir "녹취서생성기.exe"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  녹취서 자동 생성기 빌드 시작" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# ── 1. 가상환경 설정 ──
if (-not $SkipVenv) {
    if (-not (Test-Path $VenvDir)) {
        Write-Host "[1/5] 가상환경 생성 중..." -ForegroundColor Yellow
        python -m venv $VenvDir
    } else {
        Write-Host "[1/5] 가상환경 이미 존재" -ForegroundColor Green
    }

    # 활성화
    $ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
    if (Test-Path $ActivateScript) {
        . $ActivateScript
    } else {
        Write-Error "가상환경 활성화 스크립트를 찾을 수 없습니다: $ActivateScript"
        exit 1
    }

    Write-Host "[2/5] 의존성 설치 중..." -ForegroundColor Yellow
    pip install -r (Join-Path $ProjectRoot "requirements.txt") --quiet
    # torch CUDA 설치 (GPU가 있는 경우 수동으로 아래 주석 해제)
    # pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
} else {
    Write-Host "[1-2/5] 가상환경 단계 건너뜀" -ForegroundColor Gray
}

# ── 3. 빌드 ──
if ($Clean) {
    Write-Host "[3/5] 이전 빌드 정리 중..." -ForegroundColor Yellow
    if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
    if (Test-Path (Join-Path $ProjectRoot "build")) { Remove-Item -Recurse -Force (Join-Path $ProjectRoot "build") }
}

Write-Host "[3/5] PyInstaller 빌드 중..." -ForegroundColor Yellow
$SpecFile = Join-Path $ProjectRoot "녹취서생성기.spec"
pyinstaller --noconfirm --clean $SpecFile

# ── 4. 추가 파일 복사 ──
Write-Host "[4/5] 추가 파일 복사 중..." -ForegroundColor Yellow

# ffmpeg.exe 복사
$FfmpegSources = @(
    (Join-Path $ProjectRoot "ffmpeg.exe"),
    (Get-Command ffmpeg -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
)
$FfmpegCopied = $false
foreach ($src in $FfmpegSources) {
    if ($src -and (Test-Path $src)) {
        Copy-Item $src (Join-Path $OutputDir "ffmpeg.exe") -Force
        Write-Host "   ffmpeg.exe 복사 완료: $src" -ForegroundColor Green
        $FfmpegCopied = $true
        break
    }
}
if (-not $FfmpegCopied) {
    Write-Warning "ffmpeg.exe를 찾을 수 없습니다. 수동으로 배포 폴더에 넣어 주세요."
}

# config.example.json → config.json
$ConfigDest = Join-Path $OutputDir "config.json"
if (-not (Test-Path $ConfigDest)) {
    Copy-Item (Join-Path $ProjectRoot "config.example.json") $ConfigDest
    Write-Host "   config.json 생성" -ForegroundColor Green
} else {
    Write-Host "   config.json 이미 존재 — 유지" -ForegroundColor Gray
}

# README.txt
$ReadmeSrc = Join-Path $ProjectRoot "README.txt"
if (Test-Path $ReadmeSrc) {
    Copy-Item $ReadmeSrc (Join-Path $OutputDir "README.txt") -Force
    Write-Host "   README.txt 복사 완료" -ForegroundColor Green
}

# ── 5. 검증 ──
Write-Host "[5/5] 빌드 결과 검증..." -ForegroundColor Yellow
if (Test-Path $ExePath) {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  ✅ 빌드 성공!" -ForegroundColor Green
    Write-Host "  $ExePath" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "  ❌ 빌드 실패: exe를 찾을 수 없습니다" -ForegroundColor Red
    Write-Host "  기대 경로: $ExePath" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    exit 1
}
