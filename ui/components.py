"""특화된 UI 컴포넌트들"""

import tkinter as tk
from tkinter import ttk
from typing import List, Dict, Any, Optional, Callable
from .base_ui import BaseUIComponent, UIUtils


class ScannerInputComponent(BaseUIComponent):
    """바코드 스캐너 입력을 처리하는 컴포넌트"""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.entry: Optional[ttk.Entry] = None
        self.status_label: Optional[ttk.Label] = None

    def create_widgets(self):
        """스캐너 입력 관련 위젯들을 생성합니다."""
        self.frame = ttk.Frame(self.parent)

        # 입력 필드
        input_frame = ttk.Frame(self.frame)
        input_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(input_frame, text="바코드 스캔:").pack(side="left")
        self.entry = ttk.Entry(input_frame, font=('Arial', 12))
        self.entry.pack(side="left", fill="x", expand=True, padx=(5, 0))

        # 상태 표시
        self.status_label = ttk.Label(self.frame, text="스캔 대기 중...", style='Status.Good.TLabel')
        self.status_label.pack(pady=2)

    def setup_layout(self):
        """레이아웃을 설정합니다."""
        self.frame.pack(fill="x", padx=10, pady=5)

    def bind_scan_event(self, callback: Callable[[str], None]):
        """스캔 이벤트를 바인딩합니다."""
        def on_scan(event):
            barcode = self.entry.get().strip()
            if barcode:
                callback(barcode)
                self.entry.delete(0, 'end')

        self.entry.bind('<Return>', on_scan)
        self.entry.focus_set()

    def set_status(self, message: str, status_type: str = "normal"):
        """상태 메시지를 설정합니다."""
        if self.status_label:
            self.status_label.config(text=message)
            if status_type == "error":
                self.status_label.config(style='Status.Error.TLabel')
            elif status_type == "warning":
                self.status_label.config(style='Status.Warning.TLabel')
            else:
                self.status_label.config(style='Status.Good.TLabel')

    def get_input_value(self) -> str:
        """현재 입력된 값을 반환합니다."""
        return self.entry.get() if self.entry else ""

    def clear_input(self):
        """입력 필드를 비웁니다."""
        if self.entry:
            self.entry.delete(0, 'end')

    def focus_input(self):
        """입력 필드에 포커스를 설정합니다."""
        if self.entry:
            self.entry.focus_set()


class ProgressDisplayComponent(BaseUIComponent):
    """진행 상황을 표시하는 컴포넌트"""

    def __init__(self, parent: tk.Widget, total_quantity: int = 60):
        super().__init__(parent)
        self.total_quantity = total_quantity
        self.current_count = 0
        self.progress_bar: Optional[ttk.Progressbar] = None
        self.count_label: Optional[ttk.Label] = None
        self.percentage_label: Optional[ttk.Label] = None

    def create_widgets(self):
        """진행 표시 위젯들을 생성합니다."""
        self.frame = ttk.LabelFrame(self.parent, text="검사 진행률", padding=10)

        # 진행률 바
        self.progress_bar = ttk.Progressbar(
            self.frame,
            mode='determinate',
            maximum=self.total_quantity
        )
        self.progress_bar.pack(fill="x", pady=(0, 5))

        # 카운트 표시
        count_frame = ttk.Frame(self.frame)
        count_frame.pack(fill="x")

        self.count_label = ttk.Label(count_frame, text=f"0 / {self.total_quantity}")
        self.count_label.pack(side="left")

        self.percentage_label = ttk.Label(count_frame, text="0%")
        self.percentage_label.pack(side="right")

    def setup_layout(self):
        """레이아웃을 설정합니다."""
        self.frame.pack(fill="x", padx=10, pady=5)

    def update_progress(self, current: int):
        """진행률을 업데이트합니다."""
        self.current_count = current
        if self.progress_bar:
            self.progress_bar['value'] = current

        if self.count_label:
            self.count_label.config(text=f"{current} / {self.total_quantity}")

        if self.percentage_label:
            percentage = (current / self.total_quantity * 100) if self.total_quantity > 0 else 0
            self.percentage_label.config(text=f"{percentage:.1f}%")

    def reset_progress(self):
        """진행률을 리셋합니다."""
        self.update_progress(0)

    def set_total_quantity(self, total: int):
        """총 수량을 변경합니다."""
        self.total_quantity = total
        if self.progress_bar:
            self.progress_bar['maximum'] = total
        self.update_progress(self.current_count)


class DataDisplayComponent(BaseUIComponent):
    """데이터를 표시하는 테이블 컴포넌트"""

    def __init__(self, parent: tk.Widget, title: str, columns: List[str]):
        super().__init__(parent)
        self.title = title
        self.columns = columns
        self.treeview: Optional[ttk.Treeview] = None
        self.scrollbar: Optional[ttk.Scrollbar] = None

    def create_widgets(self):
        """데이터 표시 위젯들을 생성합니다."""
        self.frame = ttk.LabelFrame(self.parent, text=self.title, padding=5)

        # 트리뷰와 스크롤바 생성
        tree_frame = ttk.Frame(self.frame)
        tree_frame.pack(fill="both", expand=True)

        self.treeview = ttk.Treeview(tree_frame, columns=self.columns, show="tree headings")
        self.scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.treeview.yview)
        self.treeview.configure(yscrollcommand=self.scrollbar.set)

        # 컬럼 헤더 설정
        for col in self.columns:
            self.treeview.heading(col, text=col)
            self.treeview.column(col, width=100)

        self.treeview.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    def setup_layout(self):
        """레이아웃을 설정합니다."""
        self.frame.pack(fill="both", expand=True, padx=10, pady=5)

    def add_item(self, values: List[str], parent: str = ""):
        """아이템을 추가합니다."""
        if self.treeview:
            return self.treeview.insert(parent, "end", values=values)

    def clear_items(self):
        """모든 아이템을 제거합니다."""
        if self.treeview:
            for item in self.treeview.get_children():
                self.treeview.delete(item)

    def get_selected_item(self) -> Optional[Dict[str, str]]:
        """선택된 아이템을 반환합니다."""
        if not self.treeview:
            return None

        selection = self.treeview.selection()
        if not selection:
            return None

        item_id = selection[0]
        values = self.treeview.item(item_id)['values']

        return dict(zip(self.columns, values)) if values else None

    def set_column_width(self, column: str, width: int):
        """컬럼 너비를 설정합니다."""
        if self.treeview:
            self.treeview.column(column, width=width)