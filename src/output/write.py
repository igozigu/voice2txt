# -*- coding: utf-8 -*-
"""녹취서 파일 출력 및 저장 모듈.

원본 음성 파일과 동일한 디렉터리에 충돌 없이 녹취서 TXT 파일을 생성하며,
UTF-8 BOM(utf-8-sig) 인코딩 및 임시 파일을 통한 원자적(atomic) 저장을 보장합니다.
"""

import os
import sys
from pathlib import Path
from typing import List, Union


def get_output_path(source_path: Union[Path, str]) -> Path:
    """원본 음성 파일의 경로를 기반으로 저장할 녹취서 출력 파일 경로를 반환합니다.

    핵심 규칙:
    1. 결과 파일은 반드시 원본 파일과 동일한 디렉터리(source_dir)에 위치합니다.
       (앱 실행 디렉터리나 현재 작업 디렉터리(CWD)에 저장하지 않음)
    2. 기본 파일명 형식은 {stem}_녹취서.txt 입니다.
    3. 이미 대상 파일이 존재하는 경우 기존 파일을 덮어쓰지 않고,
       {stem}_녹취서_2.txt, {stem}_녹취서_3.txt ... 순으로 미사용 번호를 탐색하여 반환합니다.

    Args:
        source_path: 원본 음성 파일의 경로 (문자열 또는 Path 객체)

    Returns:
        충돌 없는 최종 녹취서 저장 경로 (Path)
    """
    path_obj = Path(source_path).resolve()
    source_dir = path_obj.parent
    stem = path_obj.stem

    base_name = f"{stem}_녹취서"
    candidate = source_dir / f"{base_name}.txt"

    # 파일이 아직 존재하지 않으면 기본 이름 사용
    if not candidate.exists():
        return candidate

    # 이미 존재하는 경우 _2, _3, _4 ... 순으로 미사용 경로 탐색
    counter = 2
    while True:
        candidate = source_dir / f"{base_name}_{counter}.txt"
        if not candidate.exists():
            return candidate
        counter += 1


def write_transcript(source_path: Union[Path, str], content: str) -> Path:
    """지정된 원본 파일 위치에 녹취서 내용을 UTF-8 BOM(utf-8-sig)으로 원자적으로 저장합니다.

    저장 절차:
    1. get_output_path()를 호출하여 충돌 없는 최종 출력 경로를 결정합니다.
    2. 먼저 임시 파일({name}.tmp.txt)에 utf-8-sig 인코딩으로 작성합니다.
    3. os.replace()를 통해 원자적(atomic)으로 최종 경로로 치환합니다.
    4. 쓰기 권한 등의 이유로 실패 시 정해진 한국어 안내 메시지와 함께 PermissionError를 발생시킵니다.

    Args:
        source_path: 원본 음성 파일의 경로
        content: 파일에 기록할 녹취서 전체 문자열

    Returns:
        최종 저장된 녹취서 파일 경로 (Path)

    Raises:
        PermissionError: 폴더 쓰기 권한이 없는 경우
            ("녹취서를 저장할 수 없습니다. 폴더 쓰기 권한을 확인하세요.")
        OSError: 기타 파일 입출력 오류
    """
    final_path = get_output_path(source_path)
    temp_path = final_path.with_name(f"{final_path.stem}.tmp.txt")

    try:
        # 1. 임시 파일에 UTF-8 BOM 인코딩으로 내용 작성
        with open(temp_path, "w", encoding="utf-8-sig") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        # 2. 원자적(atomic)으로 최종 대상 파일로 치환
        os.replace(temp_path, final_path)
        return final_path

    except PermissionError as e:
        # 쓰기 권한 실패 시 생성 중이던 임시 파일 정리 후 한국어 메시지로 재발생
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise PermissionError("녹취서를 저장할 수 없습니다. 폴더 쓰기 권한을 확인하세요.") from e

    except OSError as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        # Windows ERROR_ACCESS_DENIED (winerror=5) 또는 EACCES (errno=13) 권한 오류 매핑
        if getattr(e, "winerror", None) == 5 or getattr(e, "errno", None) == 13:
            raise PermissionError("녹취서를 저장할 수 없습니다. 폴더 쓰기 권한을 확인하세요.") from e
        raise


def clean_temp_file(source_path: Union[Path, str]) -> List[Path]:
    """해당 원본 파일과 연관된 .tmp.txt 임시 파일들을 모두 탐색하여 삭제합니다.

    작업 취소 시 반쯤 쓰인 임시 파일이나 예외 상황 후 잔여 임시 파일을 정리할 때 사용합니다.

    Args:
        source_path: 원본 음성 파일의 경로

    Returns:
        성공적으로 삭제된 임시 파일들의 경로 목록 (List[Path])
    """
    path_obj = Path(source_path).resolve()
    source_dir = path_obj.parent
    stem = path_obj.stem

    cleaned: List[Path] = []
    if not source_dir.exists() or not source_dir.is_dir():
        return cleaned

    # 원본 파일명(stem)으로 시작하는 모든 임시 파일 패턴 탐색
    # 예: {stem}*.tmp.txt, {stem}*.tmp
    patterns = [
        f"{stem}*.tmp.txt",
        f"{stem}*.tmp",
    ]

    seen = set()
    for pattern in patterns:
        for tmp_file in source_dir.glob(pattern):
            if tmp_file.is_file() and tmp_file not in seen:
                seen.add(tmp_file)
                try:
                    tmp_file.unlink()
                    cleaned.append(tmp_file)
                except OSError:
                    pass

    return cleaned
