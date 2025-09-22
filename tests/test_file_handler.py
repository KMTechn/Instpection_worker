"""파일 핸들러 유틸리티 테스트"""

import unittest
import tempfile
import os
import sys

# 상위 디렉토리의 모듈들을 import 하기 위해 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.file_handler import find_file_in_subdirs, ensure_directory_exists, get_safe_filename


class TestFileHandler(unittest.TestCase):
    """파일 핸들러 유틸리티 함수 테스트"""

    def setUp(self):
        """테스트 시작 전 설정"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """테스트 종료 후 정리"""
        # 임시 디렉토리와 파일들 정리
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_find_file_in_subdirs_existing_file(self):
        """하위 디렉토리에서 파일 찾기 - 존재하는 파일"""
        # 테스트용 하위 디렉토리와 파일 생성
        sub_dir = os.path.join(self.temp_dir, "subdir")
        os.makedirs(sub_dir)

        test_file = os.path.join(sub_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")

        # 파일 찾기 테스트
        found_path = find_file_in_subdirs(self.temp_dir, "test.txt")
        self.assertIsNotNone(found_path)
        self.assertTrue(found_path.endswith("test.txt"))
        self.assertTrue(os.path.exists(found_path))

    def test_find_file_in_subdirs_nonexistent_file(self):
        """하위 디렉토리에서 파일 찾기 - 존재하지 않는 파일"""
        found_path = find_file_in_subdirs(self.temp_dir, "nonexistent.txt")
        self.assertIsNone(found_path)

    def test_find_file_in_subdirs_nonexistent_directory(self):
        """하위 디렉토리에서 파일 찾기 - 존재하지 않는 디렉토리"""
        nonexistent_dir = os.path.join(self.temp_dir, "nonexistent")
        found_path = find_file_in_subdirs(nonexistent_dir, "test.txt")
        self.assertIsNone(found_path)

    def test_ensure_directory_exists_new_directory(self):
        """새 디렉토리 생성 테스트"""
        new_dir = os.path.join(self.temp_dir, "new_directory")
        self.assertFalse(os.path.exists(new_dir))

        result = ensure_directory_exists(new_dir)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(new_dir))

    def test_ensure_directory_exists_existing_directory(self):
        """기존 디렉토리 테스트"""
        result = ensure_directory_exists(self.temp_dir)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(self.temp_dir))

    def test_ensure_directory_exists_nested_directory(self):
        """중첩 디렉토리 생성 테스트"""
        nested_dir = os.path.join(self.temp_dir, "level1", "level2", "level3")
        self.assertFalse(os.path.exists(nested_dir))

        result = ensure_directory_exists(nested_dir)
        self.assertTrue(result)
        self.assertTrue(os.path.exists(nested_dir))

    def test_get_safe_filename_normal_filename(self):
        """일반 파일명 테스트"""
        filename = "normal_filename.txt"
        safe_name = get_safe_filename(filename)
        self.assertEqual(safe_name, filename)

    def test_get_safe_filename_unsafe_characters(self):
        """안전하지 않은 문자 포함 파일명 테스트"""
        unsafe_filename = "file<>:\"/\\|?*.txt"
        safe_name = get_safe_filename(unsafe_filename)

        # 안전하지 않은 문자들이 언더스코어로 대체되었는지 확인
        unsafe_chars = '<>:"/\\|?*'
        for char in unsafe_chars:
            self.assertNotIn(char, safe_name)

        # 결과에 언더스코어가 포함되어야 함
        self.assertIn('_', safe_name)
        # 확장자는 유지되어야 함
        self.assertTrue(safe_name.endswith('.txt'))

    def test_get_safe_filename_with_spaces(self):
        """공백 포함 파일명 테스트"""
        filename_with_spaces = "  file with spaces  .txt  "
        safe_name = get_safe_filename(filename_with_spaces)

        # 앞뒤 공백이 제거되었는지 확인
        self.assertFalse(safe_name.startswith(' '))
        self.assertFalse(safe_name.endswith(' '))
        self.assertTrue('file with spaces' in safe_name)


if __name__ == '__main__':
    unittest.main()