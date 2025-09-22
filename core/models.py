"""데이터 모델 정의 모듈"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import datetime


@dataclass
class InspectionSession:
    """한 트레이의 '검사' 세션 데이터를 관리합니다."""
    master_label_code: str = ""
    item_code: str = ""
    item_name: str = ""
    item_spec: str = ""
    phs: str = ""
    work_order_id: str = ""
    supplier_code: str = ""
    finished_product_batch: str = ""
    outbound_date: str = ""
    item_group: str = ""
    quantity: int = 60
    good_items: List[Dict[str, Any]] = field(default_factory=list)
    defective_items: List[Dict[str, Any]] = field(default_factory=list)
    scanned_barcodes: List[str] = field(default_factory=list)
    mismatch_error_count: int = 0
    total_idle_seconds: float = 0.0
    stopwatch_seconds: float = 0.0
    start_time: Optional[datetime.datetime] = None
    has_error_or_reset: bool = False
    is_test_tray: bool = False
    is_partial_submission: bool = False
    is_restored_session: bool = False
    is_remnant_session: bool = False
    consumed_remnant_ids: List[str] = field(default_factory=list)


@dataclass
class RemnantCreationSession:
    """잔량 생성을 위한 세션 데이터입니다."""
    item_code: str = ""
    item_name: str = ""
    item_spec: str = ""
    scanned_barcodes: List[str] = field(default_factory=list)


@dataclass
class DefectiveMergeSession:
    """불량품 통합 처리를 위한 세션 데이터입니다."""
    item_code: str = ""
    item_name: str = ""
    item_spec: str = ""
    target_quantity: int = 60
    scanned_defects: List[str] = field(default_factory=list)