"""파일 처리 유틸리티 모듈"""

import os
import sys
from typing import Optional


def resource_path(relative_path: str) -> str:
    """ PyInstaller로 패키징했을 때의 리소스 경로를 가져옵니다. """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        # 메인 스크립트의 디렉토리를 기준으로 설정
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def find_file_in_subdirs(root_folder: str, filename: str) -> Optional[str]:
    """하위 디렉토리에서 파일을 찾습니다."""
    if not os.path.exists(root_folder):
        return None

    for root, dirs, files in os.walk(root_folder):
        if filename in files:
            return os.path.join(root, filename)
    return None


def ensure_directory_exists(directory_path: str) -> bool:
    """디렉토리가 없으면 생성합니다."""
    try:
        if not os.path.exists(directory_path):
            os.makedirs(directory_path, exist_ok=True)
        return True
    except Exception as e:
        print(f"디렉토리 생성 실패: {e}")
        return False


def get_safe_filename(filename: str) -> str:
    """파일명에서 안전하지 않은 문자를 제거합니다."""
    import re
    # 파일명에 사용할 수 없는 문자들을 언더스코어로 대체
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
    return safe_name.strip()