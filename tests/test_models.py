"""데이터 모델 테스트"""

import unittest
import datetime
import sys
import os

# 상위 디렉토리의 모듈들을 import 하기 위해 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import InspectionSession, RemnantCreationSession, DefectiveMergeSession


class TestInspectionSession(unittest.TestCase):
    """InspectionSession 모델 테스트"""

    def setUp(self):
        """테스트 시작 전 설정"""
        self.session = InspectionSession()

    def test_default_values(self):
        """기본값 설정 테스트"""
        self.assertEqual(self.session.master_label_code, "")
        self.assertEqual(self.session.item_code, "")
        self.assertEqual(self.session.quantity, 60)
        self.assertEqual(len(self.session.good_items), 0)
        self.assertEqual(len(self.session.defective_items), 0)
        self.assertEqual(len(self.session.scanned_barcodes), 0)
        self.assertFalse(self.session.has_error_or_reset)
        self.assertFalse(self.session.is_test_tray)

    def test_session_initialization_with_values(self):
        """값이 있는 세션 초기화 테스트"""
        session = InspectionSession(
            master_label_code="TEST001",
            item_code="ITEM001",
            item_name="Test Item",
            quantity=30
        )

        self.assertEqual(session.master_label_code, "TEST001")
        self.assertEqual(session.item_code, "ITEM001")
        self.assertEqual(session.item_name, "Test Item")
        self.assertEqual(session.quantity, 30)

    def test_add_scanned_barcode(self):
        """바코드 추가 테스트"""
        barcode = "123456789"
        self.session.scanned_barcodes.append(barcode)

        self.assertIn(barcode, self.session.scanned_barcodes)
        self.assertEqual(len(self.session.scanned_barcodes), 1)

    def test_add_good_item(self):
        """양품 아이템 추가 테스트"""
        good_item = {
            'barcode': '123456789',
            'timestamp': datetime.datetime.now().isoformat()
        }
        self.session.good_items.append(good_item)

        self.assertEqual(len(self.session.good_items), 1)
        self.assertEqual(self.session.good_items[0]['barcode'], '123456789')

    def test_add_defective_item(self):
        """불량품 아이템 추가 테스트"""
        defective_item = {
            'barcode': '987654321',
            'reason': 'damaged',
            'timestamp': datetime.datetime.now().isoformat()
        }
        self.session.defective_items.append(defective_item)

        self.assertEqual(len(self.session.defective_items), 1)
        self.assertEqual(self.session.defective_items[0]['barcode'], '987654321')
        self.assertEqual(self.session.defective_items[0]['reason'], 'damaged')


class TestRemnantCreationSession(unittest.TestCase):
    """RemnantCreationSession 모델 테스트"""

    def setUp(self):
        """테스트 시작 전 설정"""
        self.session = RemnantCreationSession()

    def test_default_values(self):
        """기본값 설정 테스트"""
        self.assertEqual(self.session.item_code, "")
        self.assertEqual(self.session.item_name, "")
        self.assertEqual(self.session.item_spec, "")
        self.assertEqual(len(self.session.scanned_barcodes), 0)

    def test_session_with_values(self):
        """값이 있는 세션 테스트"""
        session = RemnantCreationSession(
            item_code="REM001",
            item_name="Remnant Item",
            item_spec="Spec A"
        )

        self.assertEqual(session.item_code, "REM001")
        self.assertEqual(session.item_name, "Remnant Item")
        self.assertEqual(session.item_spec, "Spec A")


class TestDefectiveMergeSession(unittest.TestCase):
    """DefectiveMergeSession 모델 테스트"""

    def setUp(self):
        """테스트 시작 전 설정"""
        self.session = DefectiveMergeSession()

    def test_default_values(self):
        """기본값 설정 테스트"""
        self.assertEqual(self.session.item_code, "")
        self.assertEqual(self.session.item_name, "")
        self.assertEqual(self.session.item_spec, "")
        self.assertEqual(self.session.target_quantity, 48)
        self.assertEqual(len(self.session.scanned_defects), 0)

    def test_session_with_values(self):
        """값이 있는 세션 테스트"""
        session = DefectiveMergeSession(
            item_code="DEF001",
            item_name="Defective Item",
            target_quantity=50
        )

        self.assertEqual(session.item_code, "DEF001")
        self.assertEqual(session.item_name, "Defective Item")
        self.assertEqual(session.target_quantity, 50)

    def test_add_scanned_defect(self):
        """불량품 바코드 추가 테스트"""
        defect_barcode = "DEF123456"
        self.session.scanned_defects.append(defect_barcode)

        self.assertIn(defect_barcode, self.session.scanned_defects)
        self.assertEqual(len(self.session.scanned_defects), 1)


if __name__ == '__main__':
    unittest.main()