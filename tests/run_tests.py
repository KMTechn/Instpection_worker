"""테스트 실행 스크립트"""

import unittest
import sys
import os

# 상위 디렉토리의 모듈들을 import 하기 위해 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 테스트 모듈들 import
from test_config import TestConfigManager
from test_models import TestInspectionSession, TestRemnantCreationSession, TestDefectiveMergeSession
from test_file_handler import TestFileHandler
from test_defect_mode import TestDefectMode, TestDefectModeIntegration
from test_integration import TestIntegration, TestSystemHealth


def run_all_tests():
    """모든 테스트를 실행합니다."""
    # 테스트 스위트 생성
    test_suite = unittest.TestSuite()

    # 설정 관리자 테스트 추가
    test_suite.addTest(unittest.makeSuite(TestConfigManager))

    # 데이터 모델 테스트 추가
    test_suite.addTest(unittest.makeSuite(TestInspectionSession))
    test_suite.addTest(unittest.makeSuite(TestRemnantCreationSession))
    test_suite.addTest(unittest.makeSuite(TestDefectiveMergeSession))

    # 파일 핸들러 테스트 추가
    test_suite.addTest(unittest.makeSuite(TestFileHandler))

    # 불량 모드 테스트 추가
    test_suite.addTest(unittest.makeSuite(TestDefectMode))
    test_suite.addTest(unittest.makeSuite(TestDefectModeIntegration))

    # 통합 테스트 추가
    test_suite.addTest(unittest.makeSuite(TestIntegration))
    test_suite.addTest(unittest.makeSuite(TestSystemHealth))

    # 테스트 실행
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)

    return result


def run_specific_test(test_name):
    """특정 테스트만 실행합니다."""
    if test_name == "config":
        suite = unittest.makeSuite(TestConfigManager)
    elif test_name == "models":
        suite = unittest.TestSuite()
        suite.addTest(unittest.makeSuite(TestInspectionSession))
        suite.addTest(unittest.makeSuite(TestRemnantCreationSession))
        suite.addTest(unittest.makeSuite(TestDefectiveMergeSession))
    elif test_name == "file_handler":
        suite = unittest.makeSuite(TestFileHandler)
    elif test_name == "defect_mode" or test_name == "defect":
        suite = unittest.TestSuite()
        suite.addTest(unittest.makeSuite(TestDefectMode))
        suite.addTest(unittest.makeSuite(TestDefectModeIntegration))
    elif test_name == "integration" or test_name == "system":
        suite = unittest.TestSuite()
        suite.addTest(unittest.makeSuite(TestIntegration))
        suite.addTest(unittest.makeSuite(TestSystemHealth))
    else:
        print(f"알 수 없는 테스트: {test_name}")
        print("사용 가능한 테스트: config, models, file_handler, defect_mode, integration")
        return None

    runner = unittest.TextTestRunner(verbosity=2)
    return runner.run(suite)


if __name__ == '__main__':
    print("=" * 50)
    print("Inspection Worker 시스템 테스트 실행")
    print("=" * 50)

    if len(sys.argv) > 1:
        # 특정 테스트 실행
        test_name = sys.argv[1]
        print(f"테스트 실행: {test_name}")
        result = run_specific_test(test_name)
    else:
        # 모든 테스트 실행
        print("모든 테스트 실행")
        result = run_all_tests()

    if result:
        print("\n" + "=" * 50)
        print(f"테스트 결과: {result.testsRun}개 실행")
        print(f"성공: {result.testsRun - len(result.failures) - len(result.errors)}개")
        print(f"실패: {len(result.failures)}개")
        print(f"오류: {len(result.errors)}개")

        if result.failures:
            print("\n실패한 테스트:")
            for test, traceback in result.failures:
                print(f"- {test}")

        if result.errors:
            print("\n오류가 발생한 테스트:")
            for test, traceback in result.errors:
                print(f"- {test}")

        print("=" * 50)

        # 모든 테스트가 성공했으면 0, 실패가 있으면 1 반환
        sys.exit(0 if result.wasSuccessful() else 1)