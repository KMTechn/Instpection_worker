"""설정 관리자 테스트"""

import unittest
import tempfile
import os
import json
from unittest.mock import patch, mock_open
import sys

# 상위 디렉토리의 모듈들을 import 하기 위해 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from Inspection_worker import ConfigManager
except ImportError:
    # 상대 경로로 다시 시도
    import sys
    sys.path.append('..')
    from Inspection_worker import ConfigManager


class TestConfigManager(unittest.TestCase):
    """ConfigManager 클래스 테스트"""

    def setUp(self):
        """테스트 시작 전 설정"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, "test_config.json")

    def tearDown(self):
        """테스트 종료 후 정리"""
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
        os.rmdir(self.temp_dir)

    def test_create_default_config(self):
        """기본 설정 생성 테스트"""
        with patch('os.path.dirname') as mock_dirname:
            mock_dirname.return_value = self.temp_dir
            config_manager = ConfigManager(self.config_file)

            # 기본 값들이 제대로 설정되었는지 확인
            self.assertEqual(config_manager.get('app.name'), 'Inspection Worker')
            self.assertEqual(config_manager.get('app.version'), 'v2.0.8')
            self.assertEqual(config_manager.get('github.repo_owner'), 'KMTechn')
            self.assertEqual(config_manager.get('inspection.tray_size'), 60)

    def test_get_nonexistent_key(self):
        """존재하지 않는 키 조회 테스트"""
        with patch('os.path.dirname') as mock_dirname:
            mock_dirname.return_value = self.temp_dir
            config_manager = ConfigManager(self.config_file)

            # 존재하지 않는 키는 기본값 반환
            self.assertIsNone(config_manager.get('nonexistent.key'))
            self.assertEqual(config_manager.get('nonexistent.key', 'default'), 'default')

    def test_set_and_get_value(self):
        """값 설정 및 조회 테스트"""
        with patch('os.path.dirname') as mock_dirname:
            mock_dirname.return_value = self.temp_dir
            config_manager = ConfigManager(self.config_file)

            # 새로운 값 설정
            config_manager.set('test.new_key', 'test_value')

            # 설정된 값이 제대로 조회되는지 확인
            self.assertEqual(config_manager.get('test.new_key'), 'test_value')

    def test_load_existing_config(self):
        """기존 설정 파일 로드 테스트"""
        # 테스트용 설정 파일 생성
        test_config = {
            'app': {
                'name': 'Test App',
                'version': 'v1.0.0'
            }
        }

        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(test_config, f)

        with patch('os.path.dirname') as mock_dirname:
            mock_dirname.return_value = self.temp_dir
            config_manager = ConfigManager(os.path.basename(self.config_file))

            # 파일에서 로드된 값 확인
            self.assertEqual(config_manager.get('app.name'), 'Test App')
            self.assertEqual(config_manager.get('app.version'), 'v1.0.0')


if __name__ == '__main__':
    unittest.main()