"""기본 UI 컴포넌트와 유틸리티 클래스"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, Dict, Any
from abc import ABC, abstractmethod


class BaseUIComponent(ABC):
    """UI 컴포넌트의 기본 클래스"""

    def __init__(self, parent: tk.Widget):
        self.parent = parent
        self.frame = None
        self.callbacks: Dict[str, Callable] = {}

    @abstractmethod
    def create_widgets(self):
        """위젯들을 생성합니다."""
        pass

    @abstractmethod
    def setup_layout(self):
        """레이아웃을 설정합니다."""
        pass

    def set_callback(self, event_name: str, callback: Callable):
        """콜백 함수를 설정합니다."""
        self.callbacks[event_name] = callback

    def trigger_callback(self, event_name: str, *args, **kwargs):
        """콜백 함수를 실행합니다."""
        if event_name in self.callbacks:
            return self.callbacks[event_name](*args, **kwargs)


class UIUtils:
    """UI 관련 유틸리티 함수들"""

    @staticmethod
    def create_labeled_entry(parent: tk.Widget, label_text: str,
                           width: int = 20, row: int = 0, column: int = 0,
                           sticky: str = "ew") -> tuple[ttk.Label, ttk.Entry]:
        """라벨과 엔트리를 함께 생성합니다."""
        label = ttk.Label(parent, text=label_text)
        label.grid(row=row, column=column, sticky="w", padx=(5, 2), pady=2)

        entry = ttk.Entry(parent, width=width)
        entry.grid(row=row, column=column+1, sticky=sticky, padx=(2, 5), pady=2)

        return label, entry

    @staticmethod
    def create_button_with_style(parent: tk.Widget, text: str,
                                command: Optional[Callable] = None,
                                style: str = "Default.TButton") -> ttk.Button:
        """스타일이 적용된 버튼을 생성합니다."""
        button = ttk.Button(parent, text=text, command=command, style=style)
        return button

    @staticmethod
    def show_error_message(title: str, message: str, parent: Optional[tk.Widget] = None):
        """에러 메시지를 표시합니다."""
        messagebox.showerror(title, message, parent=parent)

    @staticmethod
    def show_info_message(title: str, message: str, parent: Optional[tk.Widget] = None):
        """정보 메시지를 표시합니다."""
        messagebox.showinfo(title, message, parent=parent)

    @staticmethod
    def show_warning_message(title: str, message: str, parent: Optional[tk.Widget] = None):
        """경고 메시지를 표시합니다."""
        messagebox.showwarning(title, message, parent=parent)

    @staticmethod
    def ask_yes_no(title: str, message: str, parent: Optional[tk.Widget] = None) -> bool:
        """예/아니오 확인 대화상자를 표시합니다."""
        return messagebox.askyesno(title, message, parent=parent)

    @staticmethod
    def bind_focus_return_recursive(widget: tk.Widget):
        """위젯과 모든 하위 위젯에 포커스 복귀 이벤트를 바인딩합니다."""
        def return_focus(event):
            widget.focus_set()

        widget.bind("<Button-1>", return_focus)

        for child in widget.winfo_children():
            UIUtils.bind_focus_return_recursive(child)

    @staticmethod
    def clear_widget_children(widget: tk.Widget):
        """위젯의 모든 자식 위젯을 제거합니다."""
        for child in widget.winfo_children():
            child.destroy()


class StyleManager:
    """UI 스타일을 관리하는 클래스"""

    def __init__(self):
        self.style = ttk.Style()

    def setup_default_styles(self):
        """기본 스타일들을 설정합니다."""
        # 기본 버튼 스타일
        self.style.configure('Default.TButton', padding=(10, 5))

        # 사이드바 스타일
        self.style.configure('Sidebar.TFrame', background='#f0f0f0')

        # 헤더 스타일
        self.style.configure('Header.TLabel', font=('Arial', 12, 'bold'))

        # 상태 표시 스타일
        self.style.configure('Status.Good.TLabel', foreground='green')
        self.style.configure('Status.Error.TLabel', foreground='red')
        self.style.configure('Status.Warning.TLabel', foreground='orange')

    def get_style(self) -> ttk.Style:
        """현재 스타일 객체를 반환합니다."""
        return self.style