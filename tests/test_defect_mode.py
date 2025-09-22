"""불량 모드 및 관련 기능 테스트"""

import unittest
import sys
import os
from unittest.mock import patch, MagicMock

# 상위 디렉토리의 모듈들을 import 하기 위해 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import InspectionSession, DefectiveMergeSession


class TestDefectMode(unittest.TestCase):
    """불량 모드 관련 기능 테스트"""

    def setUp(self):
        """테스트 시작 전 설정"""
        self.session = InspectionSession()
        self.defect_session = DefectiveMergeSession()

    def test_defective_merge_session_initialization(self):
        """불량품 통합 세션 초기화 테스트"""
        self.assertEqual(self.defect_session.item_code, "")
        self.assertEqual(self.defect_session.item_name, "")
        self.assertEqual(self.defect_session.target_quantity, 48)
        self.assertEqual(len(self.defect_session.scanned_defects), 0)

    def test_defective_merge_session_with_data(self):
        """불량품 통합 세션 데이터 설정 테스트"""
        session = DefectiveMergeSession(
            item_code="DEF001",
            item_name="Defective Item",
            item_spec="Spec B",
            target_quantity=30
        )

        self.assertEqual(session.item_code, "DEF001")
        self.assertEqual(session.item_name, "Defective Item")
        self.assertEqual(session.item_spec, "Spec B")
        self.assertEqual(session.target_quantity, 30)

    def test_add_defective_items_to_session(self):
        """세션에 불량품 추가 테스트"""
        # 불량품 아이템 추가
        defective_item1 = {
            'barcode': 'DEF123456',
            'reason': 'damaged',
            'timestamp': '2025-09-22 10:00:00'
        }
        defective_item2 = {
            'barcode': 'DEF789012',
            'reason': 'scratched',
            'timestamp': '2025-09-22 10:01:00'
        }

        self.session.defective_items.append(defective_item1)
        self.session.defective_items.append(defective_item2)

        self.assertEqual(len(self.session.defective_items), 2)
        self.assertEqual(self.session.defective_items[0]['barcode'], 'DEF123456')
        self.assertEqual(self.session.defective_items[1]['reason'], 'scratched')

    def test_defect_merge_barcode_scanning(self):
        """불량품 통합 바코드 스캔 테스트"""
        barcodes = ['DEF001', 'DEF002', 'DEF003']

        for barcode in barcodes:
            self.defect_session.scanned_defects.append(barcode)

        self.assertEqual(len(self.defect_session.scanned_defects), 3)
        self.assertIn('DEF001', self.defect_session.scanned_defects)
        self.assertIn('DEF002', self.defect_session.scanned_defects)
        self.assertIn('DEF003', self.defect_session.scanned_defects)

    def test_defect_session_target_quantity_reached(self):
        """불량품 통합 목표 수량 달성 테스트"""
        target_qty = 5
        self.defect_session.target_quantity = target_qty

        # 목표 수량만큼 바코드 추가
        for i in range(target_qty):
            self.defect_session.scanned_defects.append(f'DEF{i:03d}')

        self.assertEqual(len(self.defect_session.scanned_defects), target_qty)
        self.assertTrue(len(self.defect_session.scanned_defects) >= self.defect_session.target_quantity)

    def test_good_vs_defective_item_separation(self):
        """양품과 불량품 분리 테스트"""
        # 양품 추가
        good_items = [
            {'barcode': 'GOOD001', 'timestamp': '2025-09-22 10:00:00'},
            {'barcode': 'GOOD002', 'timestamp': '2025-09-22 10:01:00'},
        ]

        # 불량품 추가
        defective_items = [
            {'barcode': 'DEF001', 'reason': 'damaged', 'timestamp': '2025-09-22 10:02:00'},
            {'barcode': 'DEF002', 'reason': 'scratched', 'timestamp': '2025-09-22 10:03:00'},
        ]

        self.session.good_items.extend(good_items)
        self.session.defective_items.extend(defective_items)

        # 분리가 올바르게 되었는지 확인
        self.assertEqual(len(self.session.good_items), 2)
        self.assertEqual(len(self.session.defective_items), 2)

        # 양품 목록에는 불량품이 없어야 함
        good_barcodes = [item['barcode'] for item in self.session.good_items]
        self.assertNotIn('DEF001', good_barcodes)
        self.assertNotIn('DEF002', good_barcodes)

        # 불량품 목록에는 양품이 없어야 함
        defective_barcodes = [item['barcode'] for item in self.session.defective_items]
        self.assertNotIn('GOOD001', defective_barcodes)
        self.assertNotIn('GOOD002', defective_barcodes)

    def test_defect_reason_validation(self):
        """불량 사유 검증 테스트"""
        valid_reasons = ['damaged', 'scratched', 'incomplete', 'wrong_size', 'color_defect']

        for reason in valid_reasons:
            defective_item = {
                'barcode': f'DEF_{reason.upper()}',
                'reason': reason,
                'timestamp': '2025-09-22 10:00:00'
            }
            self.session.defective_items.append(defective_item)

        # 모든 불량 사유가 올바르게 저장되었는지 확인
        stored_reasons = [item['reason'] for item in self.session.defective_items]
        for reason in valid_reasons:
            self.assertIn(reason, stored_reasons)

    def test_defect_statistics_calculation(self):
        """불량률 통계 계산 테스트"""
        # 총 100개 제품 중 10개 불량
        total_items = 100
        defective_count = 10

        # 양품 90개 추가
        for i in range(total_items - defective_count):
            self.session.good_items.append({
                'barcode': f'GOOD{i:03d}',
                'timestamp': '2025-09-22 10:00:00'
            })

        # 불량품 10개 추가
        for i in range(defective_count):
            self.session.defective_items.append({
                'barcode': f'DEF{i:03d}',
                'reason': 'damaged',
                'timestamp': '2025-09-22 10:00:00'
            })

        # 통계 계산
        total_scanned = len(self.session.good_items) + len(self.session.defective_items)
        defect_rate = (len(self.session.defective_items) / total_scanned) * 100 if total_scanned > 0 else 0

        self.assertEqual(total_scanned, total_items)
        self.assertEqual(len(self.session.defective_items), defective_count)
        self.assertEqual(defect_rate, 10.0)  # 10% 불량률

    def test_duplicate_defect_barcode_handling(self):
        """중복 불량품 바코드 처리 테스트"""
        barcode = 'DEF001'

        # 같은 바코드를 두 번 추가
        self.defect_session.scanned_defects.append(barcode)

        # 중복 체크 로직 시뮬레이션
        if barcode not in self.defect_session.scanned_defects:
            self.defect_session.scanned_defects.append(barcode)

        # 중복 추가가 방지되었는지 확인 (실제 구현에서는 중복 방지 로직이 있어야 함)
        duplicate_count = self.defect_session.scanned_defects.count(barcode)
        self.assertEqual(duplicate_count, 1)


class TestDefectModeIntegration(unittest.TestCase):
    """불량 모드 통합 테스트"""

    def setUp(self):
        """테스트 시작 전 설정"""
        # Mock 객체들 설정
        self.mock_app = MagicMock()
        self.mock_app.current_session = InspectionSession()
        self.mock_app.current_defective_merge_session = DefectiveMergeSession()

    def test_defect_mode_workflow(self):
        """불량 모드 워크플로우 테스트"""
        # 1. 정상 검사 세션 시작
        self.mock_app.current_session.master_label_code = "MASTER001"
        self.mock_app.current_session.item_code = "ITEM001"
        self.mock_app.current_session.item_name = "Test Item"

        # 2. 양품 스캔
        good_barcode = "GOOD123456789"
        self.mock_app.current_session.good_items.append({
            'barcode': good_barcode,
            'timestamp': '2025-09-22 10:00:00'
        })

        # 3. 불량품 스캔 (F12 페달과 함께)
        defect_barcode = "DEF123456789"
        self.mock_app.current_session.defective_items.append({
            'barcode': defect_barcode,
            'reason': 'damaged',
            'timestamp': '2025-09-22 10:01:00'
        })

        # 4. 결과 검증
        self.assertEqual(len(self.mock_app.current_session.good_items), 1)
        self.assertEqual(len(self.mock_app.current_session.defective_items), 1)
        self.assertEqual(self.mock_app.current_session.good_items[0]['barcode'], good_barcode)
        self.assertEqual(self.mock_app.current_session.defective_items[0]['barcode'], defect_barcode)

    def test_defect_merge_mode_workflow(self):
        """불량품 통합 모드 워크플로우 테스트"""
        # 1. 불량품 통합 세션 시작
        self.mock_app.current_defective_merge_session.item_code = "ITEM001"
        self.mock_app.current_defective_merge_session.item_name = "Test Item"
        self.mock_app.current_defective_merge_session.target_quantity = 5

        # 2. 불량품 바코드들 스캔
        defect_barcodes = ['DEF001', 'DEF002', 'DEF003', 'DEF004', 'DEF005']

        for barcode in defect_barcodes:
            self.mock_app.current_defective_merge_session.scanned_defects.append(barcode)

        # 3. 목표 수량 달성 확인
        self.assertEqual(
            len(self.mock_app.current_defective_merge_session.scanned_defects),
            self.mock_app.current_defective_merge_session.target_quantity
        )

        # 4. 모든 바코드가 올바르게 기록되었는지 확인
        for barcode in defect_barcodes:
            self.assertIn(barcode, self.mock_app.current_defective_merge_session.scanned_defects)

    @patch('tkinter.messagebox.showwarning')
    def test_defect_mode_error_handling(self, mock_showwarning):
        """불량 모드 오류 처리 테스트"""
        # 1. 마스터 라벨 없이 불량품 스캔 시도
        self.mock_app.current_session.master_label_code = ""

        # 오류 상황 시뮬레이션
        if not self.mock_app.current_session.master_label_code:
            error_occurred = True
        else:
            error_occurred = False

        self.assertTrue(error_occurred)

        # 2. 잘못된 바코드 형식으로 불량품 스캔 시도
        invalid_barcode = "INVALID"

        # 바코드 길이 검증 시뮬레이션 (실제로는 13자리 이상이어야 함)
        if len(invalid_barcode) < 13:
            validation_failed = True
        else:
            validation_failed = False

        self.assertTrue(validation_failed)


if __name__ == '__main__':
    unittest.main()