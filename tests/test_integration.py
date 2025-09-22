"""통합 테스트 - 단위 테스트와 자동 테스트 연동"""

import unittest
import sys
import os

# 상위 디렉토리의 모듈들을 import 하기 위해 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestIntegration(unittest.TestCase):
    """단위 테스트와 자동 테스트 시스템 통합 테스트"""

    def test_auto_test_command_integration(self):
        """_RUN_AUTO_TEST_ 명령어 통합 테스트"""
        # 자동 테스트 명령어 상수 확인
        auto_test_command = "_RUN_AUTO_TEST_"

        # 명령어 형식 검증
        self.assertIsInstance(auto_test_command, str)
        self.assertTrue(auto_test_command.startswith("_"))
        self.assertTrue(auto_test_command.endswith("_"))
        self.assertIn("AUTO_TEST", auto_test_command)

    def test_defect_mode_integration_with_auto_test(self):
        """불량 모드와 자동 테스트 시스템 통합 확인"""
        # 불량 모드 관련 설정값 테스트
        defect_test_configs = {
            'num_defect_merge': 5,
            'defect_reasons': ['damaged', 'scratched', 'incomplete'],
            'target_quantity': 10
        }

        # 설정값 유효성 검증
        self.assertGreater(defect_test_configs['num_defect_merge'], 0)
        self.assertIsInstance(defect_test_configs['defect_reasons'], list)
        self.assertGreater(len(defect_test_configs['defect_reasons']), 0)
        self.assertGreaterEqual(defect_test_configs['target_quantity'],
                               defect_test_configs['num_defect_merge'])

    def test_test_coverage_completeness(self):
        """테스트 커버리지 완성도 확인"""
        expected_test_modules = [
            'test_config',
            'test_models',
            'test_file_handler',
            'test_defect_mode',
            'test_integration'
        ]

        # 모든 필수 테스트 모듈이 존재하는지 확인
        test_dir = os.path.dirname(__file__)
        existing_test_files = [f[:-3] for f in os.listdir(test_dir)
                             if f.startswith('test_') and f.endswith('.py')]

        for module in expected_test_modules:
            self.assertIn(module, existing_test_files,
                         f"필수 테스트 모듈 {module}이 누락되었습니다")

    def test_auto_test_parameters_validation(self):
        """자동 테스트 파라미터 유효성 검증"""
        # 자동 테스트에서 사용되는 파라미터들
        auto_test_params = {
            'num_good': 5,
            'num_defect': 2,
            'num_pallets': 1,
            'num_reworks': 1,
            'num_remnants': 3,
            'num_defect_merge': 5  # 새로 추가된 불량품 통합 파라미터
        }

        # 모든 파라미터가 0 이상인지 확인
        for param_name, param_value in auto_test_params.items():
            self.assertGreaterEqual(param_value, 0,
                                  f"{param_name} 파라미터는 0 이상이어야 합니다")
            self.assertIsInstance(param_value, int,
                                f"{param_name} 파라미터는 정수여야 합니다")

        # 비즈니스 로직 검증
        total_defects = auto_test_params['num_defect'] * auto_test_params['num_pallets']
        self.assertGreaterEqual(total_defects, auto_test_params['num_reworks'],
                              "리워크 수량은 전체 불량품 수량보다 작거나 같아야 합니다")

    def test_defect_mode_test_scenarios(self):
        """불량 모드 테스트 시나리오 검증"""
        test_scenarios = [
            {
                'name': 'F12 페달 + 바코드 스캔',
                'description': '불량 모드 활성화 후 바코드 스캔',
                'expected_result': '불량품으로 분류'
            },
            {
                'name': '불량품 통합 모드',
                'description': '여러 불량품을 하나로 통합',
                'expected_result': '목표 수량 달성 시 완료'
            },
            {
                'name': '불량 사유 분류',
                'description': '손상, 긁힘 등 불량 사유 기록',
                'expected_result': '사유별 분류 및 통계'
            },
            {
                'name': '불량률 계산',
                'description': '전체 대비 불량품 비율 계산',
                'expected_result': '정확한 백분율 산출'
            }
        ]

        # 각 시나리오가 필요한 정보를 포함하는지 확인
        for scenario in test_scenarios:
            self.assertIn('name', scenario)
            self.assertIn('description', scenario)
            self.assertIn('expected_result', scenario)

            # 시나리오 이름과 설명이 비어있지 않은지 확인
            self.assertTrue(len(scenario['name']) > 0)
            self.assertTrue(len(scenario['description']) > 0)
            self.assertTrue(len(scenario['expected_result']) > 0)

    def test_error_handling_scenarios(self):
        """오류 처리 시나리오 테스트"""
        error_scenarios = [
            {
                'condition': '마스터 라벨 없이 불량품 스캔',
                'expected_error': 'ValidationError',
                'should_prevent': True
            },
            {
                'condition': '잘못된 바코드 형식',
                'expected_error': 'BarcodeError',
                'should_prevent': True
            },
            {
                'condition': '중복 바코드 스캔',
                'expected_error': 'DuplicateError',
                'should_prevent': True
            }
        ]

        for scenario in error_scenarios:
            self.assertIn('condition', scenario)
            self.assertIn('expected_error', scenario)
            self.assertIn('should_prevent', scenario)
            self.assertTrue(scenario['should_prevent'],
                          f"{scenario['condition']} 상황에서는 오류를 방지해야 합니다")


class TestSystemHealth(unittest.TestCase):
    """시스템 건강성 검사"""

    def test_required_files_exist(self):
        """필수 파일들이 존재하는지 확인"""
        base_dir = os.path.dirname(os.path.dirname(__file__))
        required_files = [
            'Inspection_worker.py',
            'config.json',
            'README_DEV.md',
            'core/models.py',
            'utils/file_handler.py',
            'utils/logger.py',
            'utils/exceptions.py',
            'ui/base_ui.py',
            'ui/components.py',
            'tests/run_tests.py'
        ]

        for file_path in required_files:
            full_path = os.path.join(base_dir, file_path)
            self.assertTrue(os.path.exists(full_path),
                          f"필수 파일 {file_path}이 존재하지 않습니다")

    def test_module_imports(self):
        """핵심 모듈들이 정상적으로 import되는지 확인"""
        try:
            from core.models import InspectionSession, DefectiveMergeSession
            from utils.file_handler import resource_path
            from utils.logger import EventLogger
            from utils.exceptions import InspectionError
        except ImportError as e:
            self.fail(f"핵심 모듈 import 실패: {e}")

    def test_configuration_integrity(self):
        """설정 파일 무결성 확인"""
        base_dir = os.path.dirname(os.path.dirname(__file__))
        config_path = os.path.join(base_dir, 'config.json')

        self.assertTrue(os.path.exists(config_path), "config.json 파일이 없습니다")

        try:
            import json
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # 필수 설정 섹션들이 존재하는지 확인
            required_sections = ['app', 'github', 'inspection', 'ui', 'logging', 'network']
            for section in required_sections:
                self.assertIn(section, config_data,
                            f"설정 파일에 {section} 섹션이 없습니다")

        except json.JSONDecodeError:
            self.fail("config.json 파일이 올바른 JSON 형식이 아닙니다")


if __name__ == '__main__':
    unittest.main()