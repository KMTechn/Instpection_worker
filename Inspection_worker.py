import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import datetime
import os
import sys
import threading
import time
import json
import re
from typing import List, Dict, Optional, Any
from PIL import Image, ImageTk
from dataclasses import dataclass, field
import queue
import pygame
import uuid
import requests
import zipfile
import subprocess
import keyboard
import random
import base64
import binascii

# ####################################################################
# # 자동 업데이트 기능
# ####################################################################

REPO_OWNER = "KMTechn"
REPO_NAME = "Instpection_worker"
CURRENT_VERSION = "v2.0.3" 

def check_for_updates(app_instance):
    """GitHub에서 최신 릴리스를 확인합니다."""
    try:
        api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        latest_release_data = response.json()
        latest_version = latest_release_data['tag_name']

        if latest_version.strip().lower() != CURRENT_VERSION.strip().lower():
            app_instance._log_event('UPDATE_CHECK_FOUND', detail={'current': CURRENT_VERSION, 'latest': latest_version})
            for asset in latest_release_data['assets']:
                if asset['name'].endswith('.zip'):
                    return asset['browser_download_url'], latest_version
        return None, None
    except requests.exceptions.RequestException as e:
        print(f"업데이트 확인 중 오류: {e}")
        return None, None

def download_and_apply_update(url, app_instance):
    """업데이트 파일을 다운로드하고 적용 스크립트를 실행합니다."""
    try:
        app_instance._log_event('UPDATE_STARTED', detail={'url': url})
        
        temp_dir = os.environ.get("TEMP", "C:\\Temp")
        zip_path = os.path.join(temp_dir, "update.zip")
        
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        temp_update_folder = os.path.join(temp_dir, "temp_update")
        if os.path.exists(temp_update_folder):
            import shutil
            shutil.rmtree(temp_update_folder)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_update_folder)
        os.remove(zip_path)

        application_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        updater_script_path = os.path.join(application_path, "updater.bat")
        
        extracted_content = os.listdir(temp_update_folder)
        new_program_folder_path = temp_update_folder
        if len(extracted_content) == 1 and os.path.isdir(os.path.join(temp_update_folder, extracted_content[0])):
                new_program_folder_path = os.path.join(temp_update_folder, extracted_content[0])
                
        with open(updater_script_path, "w", encoding='utf-8') as bat_file:
            bat_file.write(fr"""@echo off
chcp 65001 > nul
echo.
echo ==========================================================
echo  프로그램을 업데이트합니다. 이 창을 닫지 마세요.
echo ==========================================================
echo.
echo 잠시 후 프로그램이 자동으로 종료됩니다...
timeout /t 3 /nobreak > nul
taskkill /F /IM "{os.path.basename(sys.executable)}" > nul
echo.
echo 기존 파일을 백업하고 새 파일로 교체합니다...
xcopy "{new_program_folder_path}" "{application_path}" /E /H /C /I /Y > nul
echo.
echo 임시 업데이트 파일을 삭제합니다...
rmdir /s /q "{temp_update_folder}"
echo.
echo ========================================
echo  업데이트 완료!
echo ========================================
echo.
echo 3초 후에 프로그램을 다시 시작합니다.
timeout /t 3 /nobreak > nul
start "" "{os.path.join(application_path, os.path.basename(sys.executable))}"
del "%~f0"
            """)
        
        subprocess.Popen(updater_script_path, creationflags=subprocess.CREATE_NEW_CONSOLE)
        sys.exit(0)

    except Exception as e:
        app_instance._log_event('UPDATE_FAILED', detail={'error': str(e)})
        root_alert = tk.Tk()
        root_alert.withdraw()
        messagebox.showerror("업데이트 실패", f"업데이트 적용 중 오류가 발생했습니다.\n\n{e}\n\n프로그램을 다시 시작해주세요.", parent=root_alert)
        root_alert.destroy()

def check_and_apply_updates(app_instance):
    """업데이트를 확인하고 사용자에게 적용 여부를 묻습니다."""
    download_url, new_version = check_for_updates(app_instance)
    if download_url:
        root_alert = tk.Tk()
        root_alert.withdraw()
        if messagebox.askyesno("업데이트 발견", f"새로운 버전({new_version})이 발견되었습니다.\n지금 업데이트하시겠습니까? (현재: {CURRENT_VERSION})", parent=root_alert):
            root_alert.destroy()
            download_and_apply_update(download_url, app_instance)
        else:
            root_alert.destroy()

# ####################################################################
# # 데이터 클래스 및 유틸리티
# ####################################################################

@dataclass
class InspectionSession:
    """한 트레이의 검사 세션 데이터를 관리합니다."""
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

def resource_path(relative_path: str) -> str:
    """ PyInstaller로 패키징했을 때의 리소스 경로를 가져옵니다. """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# ####################################################################
# # 메인 어플리케이션
# ####################################################################

class InspectionProgram:
    """품질 검사 작업을 위한 메인 GUI 어플리케이션 클래스입니다."""
    APP_TITLE = f"품질 검사 시스템 ({CURRENT_VERSION})"
    DEFAULT_FONT = 'Malgun Gothic'
    TRAY_SIZE = 60
    SETTINGS_DIR = 'config'
    SETTINGS_FILE = 'inspection_settings.json'
    IDLE_THRESHOLD_SEC = 420
    ITEM_CODE_LENGTH = 13
    DEFECT_PEDAL_KEY_NAME = 'F12'

    COLOR_BG = "#F5F7FA"
    COLOR_SIDEBAR_BG = "#FFFFFF"
    COLOR_TEXT = "#343A40"
    COLOR_TEXT_SUBTLE = "#6C757D"
    COLOR_PRIMARY = "#0D6EFD"
    COLOR_SUCCESS = "#28A745"
    COLOR_DEFECT = "#DC3545"
    COLOR_IDLE = "#FFC107"
    COLOR_BORDER = "#CED4DA"
    COLOR_VELVET = "#8A0707"
    COLOR_DEFECT_BG = "#FADBD8" 
    COLOR_REWORK_BG = "#E8DAEF" 
    COLOR_REWORK = "#8E44AD"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(self.APP_TITLE)
        self.root.state('zoomed')
        self.root.configure(bg=self.COLOR_BG)
        
        self.current_mode = "standard" # 'standard' 또는 'rework'
        
        self.log_queue: queue.Queue = queue.Queue()
        self.log_file_path: Optional[str] = None
        self.rework_log_file_path: Optional[str] = None
        self.log_thread = threading.Thread(target=self._event_log_writer, daemon=True)
        self.log_thread.start()

        try:
            self.root.iconbitmap(resource_path(os.path.join('assets', 'logo.ico')))
        except Exception as e:
            print(f"아이콘 로드 실패: {e}")

        pygame.init()
        pygame.mixer.init()
        try:
            self.success_sound = pygame.mixer.Sound(resource_path('assets/success.wav'))
            self.error_sound = pygame.mixer.Sound(resource_path('assets/error.wav'))
        except pygame.error as e:
            messagebox.showwarning("사운드 파일 오류", f"사운드 파일을 로드할 수 없습니다: {e}")
            self.success_sound = self.error_sound = None

        self.application_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        self.config_folder = os.path.join(self.application_path, self.SETTINGS_DIR)
        os.makedirs(self.config_folder, exist_ok=True)
        self.settings = self.load_app_settings()
        self._setup_paths()
        
        initial_delay = self.settings.get('scan_delay', 0.0)
        self.scan_delay_sec = tk.DoubleVar(value=initial_delay)
        self.last_scan_time = 0.0
        self.scale_factor = self.settings.get('scale_factor', 1.0)
        self.paned_window_sash_positions: Dict[str, int] = self.settings.get('paned_window_sash_positions', {})
        self.column_widths: Dict[str, int] = self.settings.get('column_widths_inspector', {})

        self.worker_name = ""
        self.current_session = InspectionSession()
        self.items_data = self.load_items()
        
        self.work_summary: Dict[str, Dict[str, Any]] = {}

        self.completed_tray_times: List[float] = []
        self.total_tray_count = 0
        self.tray_last_end_time: Optional[datetime.datetime] = None
        self.info_cards: Dict[str, Dict[str, ttk.Widget]] = {}
        self.logo_photo_ref = None
        self.is_idle = False
        self.last_activity_time: Optional[datetime.datetime] = None
        self.completed_master_labels: set = set()
        
        self.reworkable_defects: Dict[str, Dict[str, Any]] = {}
        self.reworked_items_today: List[Dict[str, Any]] = []

        self.status_message_job: Optional[str] = None
        self.clock_job: Optional[str] = None
        self.stopwatch_job: Optional[str] = None
        self.idle_check_job: Optional[str] = None
        self.focus_return_job: Optional[str] = None
        
        try:
            self.computer_id = hex(uuid.getnode())
        except Exception:
            import socket
            self.computer_id = socket.gethostname()
        self.CURRENT_TRAY_STATE_FILE = f"_current_inspection_state_{self.computer_id}.json"

        self._setup_core_ui_structure()
        self._setup_styles()
        
        self.show_worker_input_screen()
        
        self.root.bind('<Control-MouseWheel>', self.on_ctrl_wheel)
        self.root.bind_all(f"<KeyPress-{self.DEFECT_PEDAL_KEY_NAME}>", self.on_pedal_press_ui_feedback)
        self.root.bind_all(f"<KeyRelease-{self.DEFECT_PEDAL_KEY_NAME}>", self.on_pedal_release_ui_feedback)
        
        self.is_auto_testing_defect = False

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_pedal_press_ui_feedback(self, event=None):
        if self.current_mode != "standard": return
        if hasattr(self, 'defect_mode_indicator'):
            self.defect_mode_indicator.config(text="불량 모드 ON", background=self.COLOR_DEFECT, foreground='white')
        if hasattr(self, 'scan_entry'):
            self.scan_entry.config(highlightcolor=self.COLOR_DEFECT)

    def on_pedal_release_ui_feedback(self, event=None):
        bg_color = self.COLOR_BG
        if self.current_mode == "rework": 
            bg_color = self.COLOR_REWORK_BG
        
        highlight_color = self.COLOR_PRIMARY
        if self.current_mode == "rework": 
            highlight_color = self.COLOR_REWORK

        if hasattr(self, 'defect_mode_indicator'):
            self.defect_mode_indicator.config(text="", background=bg_color)
        if hasattr(self, 'scan_entry'):
            self.scan_entry.config(highlightcolor=highlight_color)
    
    def _setup_paths(self):
        self.save_folder = "C:\\Sync"
        os.makedirs(self.save_folder, exist_ok=True)

    def load_app_settings(self) -> Dict[str, Any]:
        path = os.path.join(self.config_folder, self.SETTINGS_FILE)
        try:
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): return {}

    def save_settings(self):
        try:
            path = os.path.join(self.config_folder, self.SETTINGS_FILE)
            current_settings = {
                'scale_factor': self.scale_factor,
                'column_widths_inspector': self.column_widths,
                'paned_window_sash_positions': self.paned_window_sash_positions,
                'scan_delay': self.scan_delay_sec.get()
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(current_settings, f, indent=4, ensure_ascii=False)
            self._log_event('SETTINGS_UPDATED', detail=current_settings)
        except Exception as e: print(f"설정 저장 오류: {e}")

    def load_items(self) -> List[Dict[str, str]]:
        item_path = resource_path(os.path.join('assets', 'Item.csv'))
        encodings_to_try = ['utf-8-sig', 'cp949', 'euc-kr', 'utf-8']
        for encoding in encodings_to_try:
            try:
                with open(item_path, 'r', encoding=encoding) as file:
                    items = list(csv.DictReader(file))
                    self._log_event('ITEM_DATA_LOADED', detail={'item_count': len(items), 'path': item_path})
                    return items
            except UnicodeDecodeError: continue
            except FileNotFoundError:
                messagebox.showerror("오류", f"필수 파일 없음: {item_path}")
                self.root.destroy()
                return []
            except Exception as e:
                messagebox.showerror("파일 읽기 오류", f"파일 읽기 오류: {e}")
                self.root.destroy()
                return []
        messagebox.showerror("인코딩 감지 실패", f"'{os.path.basename(item_path)}' 파일의 인코딩을 알 수 없습니다.")
        self.root.destroy()
        return []

    def _setup_core_ui_structure(self):
        status_bar = tk.Frame(self.root, bg=self.COLOR_SIDEBAR_BG, bd=1, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_label = tk.Label(status_bar, text="준비", anchor=tk.W, bg=self.COLOR_SIDEBAR_BG, fg=self.COLOR_TEXT)
        self.status_label.pack(side=tk.LEFT, padx=10, pady=4)
        self.paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.left_pane = ttk.Frame(self.paned_window, style='Sidebar.TFrame')
        self.center_pane = ttk.Frame(self.paned_window, style='TFrame')
        self.right_pane = ttk.Frame(self.paned_window, style='Sidebar.TFrame')
        self.paned_window.add(self.left_pane, weight=1)
        self.paned_window.add(self.center_pane, weight=3)
        self.paned_window.add(self.right_pane, weight=1)
        self.worker_input_frame = ttk.Frame(self.root, style='TFrame')

    def _setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        m = int(12 * self.scale_factor)
        self.style.configure('Good.Treeview.Heading', background=self.COLOR_SUCCESS, foreground='white', font=(self.DEFAULT_FONT, m, 'bold'))
        self.style.configure('Defect.Treeview.Heading', background=self.COLOR_DEFECT, foreground='white', font=(self.DEFAULT_FONT, m, 'bold'))
        self.apply_scaling()

    def apply_scaling(self):
        base = 10
        s, m, l, xl, xxl = (int(factor * self.scale_factor) for factor in [base, base + 2, base + 8, base + 20, base + 60])
        
        bg_color = self.COLOR_BG
        is_rework_state = self.current_mode == "rework"

        if is_rework_state:
            bg_color = self.COLOR_REWORK_BG

        fg_color = self.COLOR_TEXT
        self.style.configure('TFrame', background=bg_color)
        self.style.configure('Sidebar.TFrame', background=self.COLOR_SIDEBAR_BG)
        self.style.configure('Card.TFrame', background=self.COLOR_SIDEBAR_BG, relief='solid', borderwidth=1, bordercolor=self.COLOR_BORDER)
        self.style.configure('Idle.TFrame', background=self.COLOR_IDLE, relief='solid', borderwidth=1, bordercolor=self.COLOR_BORDER)
        self.style.configure('TLabel', background=bg_color, foreground=fg_color, font=(self.DEFAULT_FONT, m))
        self.style.configure('Sidebar.TLabel', background=self.COLOR_SIDEBAR_BG, foreground=self.COLOR_TEXT, font=(self.DEFAULT_FONT, m))
        self.style.configure('Idle.TLabel', background=self.COLOR_IDLE, foreground=self.COLOR_TEXT, font=(self.DEFAULT_FONT, m))
        self.style.configure('Subtle.TLabel', background=self.COLOR_SIDEBAR_BG, foreground=self.COLOR_TEXT_SUBTLE, font=(self.DEFAULT_FONT, s))
        self.style.configure('Idle.Subtle.TLabel', background=self.COLOR_IDLE, foreground=self.COLOR_TEXT_SUBTLE, font=(self.DEFAULT_FONT, s))
        self.style.configure('Value.TLabel', background=self.COLOR_SIDEBAR_BG, foreground=self.COLOR_TEXT, font=(self.DEFAULT_FONT, int(l * 1.2), 'bold'))
        self.style.configure('Idle.Value.TLabel', background=self.COLOR_IDLE, foreground=self.COLOR_TEXT, font=(self.DEFAULT_FONT, int(l * 1.2), 'bold'))
        self.style.configure('Title.TLabel', background=bg_color, foreground=fg_color, font=(self.DEFAULT_FONT, int(xl * 1.5), 'bold'))
        self.style.configure('ItemInfo.TLabel', background=bg_color, foreground=fg_color, font=(self.DEFAULT_FONT, l, 'bold'))
        self.style.configure('MainCounter.TLabel', background=bg_color, foreground=fg_color, font=(self.DEFAULT_FONT, xxl, 'bold'))
        self.style.configure('TButton', font=(self.DEFAULT_FONT, m, 'bold'), padding=(int(15 * self.scale_factor), int(10 * self.scale_factor)), borderwidth=0)
        self.style.map('TButton', background=[('!active', self.COLOR_PRIMARY), ('active', '#0B5ED7')], foreground=[('!active', 'white')])
        self.style.configure('Secondary.TButton', font=(self.DEFAULT_FONT, s, 'bold'), borderwidth=0)
        self.style.map('Secondary.TButton', background=[('!active', self.COLOR_TEXT_SUBTLE), ('active', self.COLOR_TEXT)], foreground=[('!active', 'white')])
        self.style.configure('TCheckbutton', background=self.COLOR_SIDEBAR_BG, foreground=self.COLOR_TEXT, font=(self.DEFAULT_FONT, m))
        self.style.map('TCheckbutton', indicatorcolor=[('selected', self.COLOR_PRIMARY), ('!selected', self.COLOR_BORDER)])
        self.style.configure('VelvetCard.TFrame', background=self.COLOR_VELVET, relief='solid', borderwidth=1, bordercolor=self.COLOR_BORDER)
        self.style.configure('Velvet.Subtle.TLabel', background=self.COLOR_VELVET, foreground='white', font=(self.DEFAULT_FONT, s))
        self.style.configure('Velvet.Value.TLabel', background=self.COLOR_VELVET, foreground='white', font=(self.DEFAULT_FONT, int(l * 1.2), 'bold'))
        self.style.configure('Treeview.Heading', font=(self.DEFAULT_FONT, m, 'bold'))
        self.style.configure('Treeview', rowheight=int(25 * self.scale_factor), font=(self.DEFAULT_FONT, m))
        self.style.configure('Main.Horizontal.TProgressbar', troughcolor=self.COLOR_BORDER, background=self.COLOR_PRIMARY, thickness=int(25 * self.scale_factor))
        if hasattr(self, 'status_label'):
            self.status_label['font'] = (self.DEFAULT_FONT, s)

    def on_ctrl_wheel(self, event):
        self.scale_factor += 0.1 if event.delta > 0 else -0.1
        self.scale_factor = max(0.7, min(2.5, self.scale_factor))
        self.apply_scaling()
        if self.worker_name: self.show_inspection_screen()
        else: self.show_worker_input_screen()

    def _clear_main_frames(self):
        if self.worker_input_frame.winfo_ismapped(): self.worker_input_frame.pack_forget()
        if self.paned_window.winfo_ismapped(): self.paned_window.pack_forget()

    def show_worker_input_screen(self):
        self.current_mode = "standard"
        self._apply_mode_ui()
        self._clear_main_frames()
        self.worker_input_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        for widget in self.worker_input_frame.winfo_children(): widget.destroy()
        self.worker_input_frame.grid_rowconfigure(0, weight=1)
        self.worker_input_frame.grid_columnconfigure(0, weight=1)
        center_frame = ttk.Frame(self.worker_input_frame, style='TFrame')
        center_frame.grid(row=0, column=0)
        try:
            logo_path = resource_path(os.path.join('assets', 'logo.png'))
            logo_img = Image.open(logo_path)
            max_width = 400 * self.scale_factor
            logo_img_resized = logo_img.resize((int(max_width), int(max_width * (logo_img.height / logo_img.width))), Image.Resampling.LANCZOS)
            self.logo_photo_ref = ImageTk.PhotoImage(logo_img_resized)
            ttk.Label(center_frame, image=self.logo_photo_ref, style='TLabel').pack(pady=(40, 20))
        except Exception as e: print(f"로고 로드 실패: {e}")
        ttk.Label(center_frame, text=self.APP_TITLE, style='Title.TLabel').pack(pady=(20, 60))
        ttk.Label(center_frame, text="작업자 이름", style='TLabel', font=(self.DEFAULT_FONT, int(12 * self.scale_factor))).pack(pady=(10, 5))
        self.worker_entry = tk.Entry(center_frame, width=25, font=(self.DEFAULT_FONT, int(18 * self.scale_factor), 'bold'), bd=2, relief=tk.SOLID, justify='center', highlightbackground=self.COLOR_BORDER, highlightcolor=self.COLOR_PRIMARY, highlightthickness=2)
        self.worker_entry.pack(ipady=int(12 * self.scale_factor))
        self.worker_entry.bind('<Return>', self.start_work)
        self.worker_entry.focus()
        ttk.Button(center_frame, text="작업 시작", command=self.start_work, style='TButton', width=20).pack(pady=60, ipady=int(10 * self.scale_factor))

    def start_work(self, event=None):
        worker_name = self.worker_entry.get().strip()
        if not worker_name:
            messagebox.showerror("오류", "작업자 이름을 입력해주세요.")
            return
        self.worker_name = worker_name
        self._load_session_state()
        self._log_event('WORK_START')
        self._load_current_session_state()
        if self.root.winfo_exists() and not self.paned_window.winfo_ismapped():
            self.show_inspection_screen()

    def change_worker(self):
        msg = "작업자를 변경하시겠습니까?"
        if self.current_session.master_label_code:
            msg += "\n\n진행 중인 작업은 다음 로그인 시 복구할 수 있도록 저장됩니다."
        if messagebox.askyesno("작업자 변경", msg):
            if self.current_session.master_label_code:
                self.current_session.is_partial_submission = True
                self.complete_session()
            self._cancel_all_jobs()
            self.worker_name = ""
            self.show_worker_input_screen()
    
    def _load_session_state(self):
        today = datetime.date.today()
        sanitized_name = re.sub(r'[\\/*?:"<>|]', "", self.worker_name)
        
        self.log_file_path = os.path.join(self.save_folder, f"검사작업이벤트로그_{sanitized_name}_{today.strftime('%Y%m%d')}.csv")
        if not os.path.exists(self.log_file_path):
            self._log_event('LOG_FILE_CREATED', detail={'path': self.log_file_path})

        self.rework_log_file_path = os.path.join(self.save_folder, f"리워크작업이벤트로그_{sanitized_name}_{today.strftime('%Y%m%d')}.csv")
        if not os.path.exists(self.rework_log_file_path):
             self._log_event('REWORK_LOG_FILE_CREATED', detail={'path': self.rework_log_file_path})

        self.total_tray_count = 0
        self.completed_tray_times = []
        self.work_summary = {}
        self.tray_last_end_time = None
        self.reworked_items_today = []
        
        if os.path.exists(self.rework_log_file_path):
            try:
                with open(self.rework_log_file_path, 'r', encoding='utf-8-sig') as f:
                    reader = list(csv.DictReader(f))
                
                for row in reader:
                    if row.get('worker') != self.worker_name: continue
                    
                    if row.get('event') == 'REWORK_SUCCESS':
                        try:
                            details = json.loads(row.get('details', '{}'))
                            barcode = details.get('barcode')
                            rework_time = details.get('rework_time')
                            if barcode and rework_time:
                                self.reworked_items_today.append({
                                    'barcode': barcode,
                                    'rework_time': rework_time
                                })
                        except (json.JSONDecodeError, AttributeError):
                            continue
                self.reworked_items_today.sort(key=lambda x: x.get('rework_time', ''), reverse=True)
            except Exception as e:
                print(f"금일 리워크 로그 파일 '{self.rework_log_file_path}' 처리 중 오류: {e}")

        all_completed_sessions = []
        log_file_pattern = re.compile(r"검사작업이벤트로그_.*_(\d{8})\.csv")
        try:
            all_log_files = [os.path.join(self.save_folder, f) for f in os.listdir(self.save_folder) if log_file_pattern.match(f)]
            for log_path in sorted(all_log_files):
                with open(log_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('event') == 'TRAY_COMPLETE':
                            try:
                                details = json.loads(row['details'])
                                details['timestamp'] = datetime.datetime.fromisoformat(row['timestamp'])
                                all_completed_sessions.append(details)
                            except (json.JSONDecodeError, KeyError, TypeError): continue
        except Exception as e:
            print(f"전체 검사 로그 파일 처리 중 오류: {e}")

        self.completed_master_labels.clear()
        today_sessions_list = [s for s in all_completed_sessions if s['timestamp'].date() == today]
        for session in today_sessions_list:
            master_code = session.get('master_label_code')
            if master_code: self.completed_master_labels.add(master_code)

        if self.completed_master_labels:
            self._log_event('COMPLETED_LABELS_LOADED', detail={'count': len(self.completed_master_labels)})
        
        start_of_week = today - datetime.timedelta(days=today.weekday())
        current_week_sessions_list = [s for s in all_completed_sessions if s['timestamp'].date() >= start_of_week]

        for session in today_sessions_list:
            item_code = session.get('item_code', 'UNKNOWN')
            if not item_code: continue

            if item_code not in self.work_summary:
                self.work_summary[item_code] = {'name': session.get('item_name', '알 수 없음'), 
                                                'spec': session.get('item_spec', ''), 
                                                'pallet_count': 0, 
                                                'test_pallet_count': 0,
                                                'defective_ea_count': 0}
            
            defective_count_in_session = len(session.get('defective_product_barcodes', []))
            self.work_summary[item_code]['defective_ea_count'] += defective_count_in_session

            if session.get('is_test', False):
                self.work_summary[item_code]['test_pallet_count'] += 1
            else:
                self.work_summary[item_code]['pallet_count'] += 1
            
            if not session.get('is_test', False) and not session.get('is_partial', False):
                self.total_tray_count += 1
        
        clean_sessions = [s for s in current_week_sessions_list if (
            s.get('scan_count') == s.get('tray_capacity') and not s.get('has_error_or_reset') and 
            not s.get('is_partial_submission') and not s.get('is_restored_session'))
        ]
        if clean_sessions:
            MINIMUM_REALISTIC_TIME_PER_PC = 2.0
            valid_times = [float(s.get('work_time_sec', 0.0)) for s in clean_sessions if s.get('tray_capacity', 0) > 0 and (float(s.get('work_time_sec', 0.0)) / s.get('tray_capacity')) >= MINIMUM_REALISTIC_TIME_PER_PC]
            if valid_times: self.completed_tray_times = valid_times
        if any(self.work_summary):
            self.show_status_message(f"금일 작업 현황을 불러왔습니다.", self.COLOR_PRIMARY)

    def _save_current_session_state(self):
        if not self.current_session.master_label_code: return
        state_path = os.path.join(self.save_folder, self.CURRENT_TRAY_STATE_FILE)
        try:
            serializable_state = self.current_session.__dict__.copy()
            serializable_state['start_time'] = serializable_state['start_time'].isoformat() if serializable_state['start_time'] else None
            serializable_state['worker_name'] = self.worker_name
            with open(state_path, 'w', encoding='utf-8') as f: json.dump(serializable_state, f, indent=4)
        except Exception as e: print(f"현재 세션 상태 저장 실패: {e}")

    def _load_current_session_state(self):
        state_path = os.path.join(self.save_folder, self.CURRENT_TRAY_STATE_FILE)
        if not os.path.exists(state_path): return
        try:
            with open(state_path, 'r', encoding='utf-8') as f: saved_state = json.load(f)
            saved_worker = saved_state.get('worker_name')
            if not saved_worker:
                self._delete_current_session_state()
                return
            total_scans = len(saved_state.get('scanned_barcodes', []))
            msg_base = f"· 품목: {saved_state.get('item_name', '알 수 없음')}\n· 검사 수: {total_scans}개"
            if saved_worker == self.worker_name:
                if messagebox.askyesno("이전 작업 복구", f"이전에 마치지 못한 검사 작업을 이어서 시작하시겠습니까?\n\n{msg_base}"):
                    self._restore_session_from_state(saved_state)
                    self._log_event('TRAY_RESTORE')
                else: self._delete_current_session_state()
            else:
                response = messagebox.askyesnocancel("작업 인수 확인", f"이전 작업자 '{saved_worker}'님이 마치지 않은 작업이 있습니다.\n\n이 작업을 이어서 진행하시겠습니까?\n\n{msg_base}")
                if response is True:
                    self._restore_session_from_state(saved_state)
                    self._log_event('TRAY_TAKEOVER', detail={'previous': saved_worker, 'new': self.worker_name})
                elif response is False:
                    if messagebox.askyesno("작업 삭제", "이전 작업을 영구적으로 삭제하시겠습니까?"):
                        self._delete_current_session_state()
                        self.show_status_message(f"'{saved_worker}'님의 이전 작업이 삭제되었습니다.", self.COLOR_DEFECT)
                    else:
                        self.worker_name = ""
                        self.show_worker_input_screen()
                else:
                    self.worker_name = ""
                    self.show_worker_input_screen()
        except Exception as e:
            messagebox.showwarning("오류", f"이전 작업 상태 로드 실패: {e}")
            self._delete_current_session_state()

    def _restore_session_from_state(self, state: Dict[str, Any]):
        state.pop('worker_name', None)
        state.pop('is_defective_only_session', None) 
        
        state['start_time'] = datetime.datetime.fromisoformat(state['start_time']) if state.get('start_time') else None
        session_fields = InspectionSession.__dataclass_fields__
        for field_name in session_fields:
            if field_name not in state:
                state[field_name] = session_fields[field_name].default_factory() if callable(session_fields[field_name].default_factory) else session_fields[field_name].default
        
        self.current_session = InspectionSession(**state)
        self.current_session.is_restored_session = True
        
        self.current_mode = "standard"
        self.show_status_message("이전 검사 작업을 복구했습니다.", self.COLOR_PRIMARY)

    def _delete_current_session_state(self):
        state_path = os.path.join(self.save_folder, self.CURRENT_TRAY_STATE_FILE)
        if os.path.exists(state_path):
            try: os.remove(state_path)
            except Exception as e: print(f"임시 세션 파일 삭제 실패: {e}")

    def _bind_focus_return_recursive(self, widget):
        interactive_widgets = (ttk.Button, tk.Entry, ttk.Spinbox, ttk.Treeview, ttk.Checkbutton, ttk.Scrollbar)
        if not isinstance(widget, interactive_widgets):
            widget.bind("<Button-1>", lambda e: self._schedule_focus_return())
        for child in widget.winfo_children():
            self._bind_focus_return_recursive(child)
            
    def show_inspection_screen(self):
        self._clear_main_frames()
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        for pane in [self.left_pane, self.center_pane, self.right_pane]:
            for widget in pane.winfo_children(): widget.destroy()
        self._create_left_sidebar_content(self.left_pane)
        self._create_center_content(self.center_pane)
        self._create_right_sidebar_content(self.right_pane)
        
        self.root.after(50, self._set_initial_sash_positions)
        self._update_clock()
        self._start_idle_checker()
        self._update_all_summaries()
        
        self._apply_mode_ui()
        
        if self.current_session.master_label_code:
            self._update_current_item_label()
            self._redraw_scan_trees()
            self._update_center_display()
            self._start_stopwatch(resume=True)
        else:
            self._reset_ui_to_waiting_state()

        self.root.after(100, lambda: self._bind_focus_return_recursive(self.paned_window))
        self.scan_entry.focus()

    def _set_initial_sash_positions(self):
        self.paned_window.update_idletasks()
        try:
            total_width = self.paned_window.winfo_width()
            if total_width <= 1:
                self.root.after(50, self._set_initial_sash_positions)
                return
            sash_0_pos, sash_1_pos = int(total_width * 0.25), int(total_width * 0.75)
            self.paned_window.sashpos(0, sash_0_pos)
            self.paned_window.sashpos(1, sash_1_pos)
        except tk.TclError: pass

    def _create_left_sidebar_content(self, parent_frame):
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame.grid_rowconfigure(1, weight=1)
        parent_frame['padding'] = (10, 10)
        
        top_frame = ttk.Frame(parent_frame, style='Sidebar.TFrame')
        top_frame.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        top_frame.grid_columnconfigure(0, weight=1)
        worker_info_frame = ttk.Frame(top_frame, style='Sidebar.TFrame')
        worker_info_frame.grid(row=0, column=0, sticky='w')
        ttk.Label(worker_info_frame, text=f"작업자: {self.worker_name}", style='Sidebar.TLabel').pack(side=tk.LEFT)
        buttons_frame = ttk.Frame(top_frame, style='Sidebar.TFrame')
        buttons_frame.grid(row=0, column=1, sticky='e')
        ttk.Button(buttons_frame, text="완료 현황 보기", command=self.show_completion_summary_window, style='Secondary.TButton').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(buttons_frame, text="작업자 변경", command=self.change_worker, style='Secondary.TButton').pack(side=tk.LEFT, padx=(0, 5))

        summary_container = ttk.Frame(parent_frame, style='Sidebar.TFrame')
        summary_container.grid(row=1, column=0, sticky='nsew')
        summary_container.grid_columnconfigure(0, weight=1)
        summary_container.grid_rowconfigure(1, weight=1) 
        summary_container.grid_rowconfigure(3, weight=1) 

        self.summary_title_label = ttk.Label(summary_container, text="금일 작업 현황", style='Subtle.TLabel', font=(self.DEFAULT_FONT, int(14 * self.scale_factor), 'bold'))
        self.summary_title_label.grid(row=0, column=0, sticky='w', pady=(5, 5))
        good_tree_frame = ttk.Frame(summary_container, style='Sidebar.TFrame')
        good_tree_frame.grid(row=1, column=0, sticky='nsew', pady=(0, 10))
        good_tree_frame.grid_columnconfigure(0, weight=1)
        good_tree_frame.grid_rowconfigure(0, weight=1)

        cols = ('item_name_spec', 'item_code', 'count')
        self.good_summary_tree = ttk.Treeview(good_tree_frame, columns=cols, show='headings', style='Treeview')
        self.good_summary_tree.heading('item_name_spec', text='품목명')
        self.good_summary_tree.heading('item_code', text='품목코드')
        self.good_summary_tree.heading('count', text='완료 수량 (파렛트)')
        
        self.good_summary_tree.column('item_name_spec', minwidth=100, anchor='w', stretch=tk.YES)
        self.good_summary_tree.column('item_code', minwidth=100, anchor='w', stretch=tk.YES)
        self.good_summary_tree.column('count', minwidth=100, anchor='center', stretch=tk.YES)
        
        self.good_summary_tree.grid(row=0, column=0, sticky='nsew')
        good_scrollbar = ttk.Scrollbar(good_tree_frame, orient='vertical', command=self.good_summary_tree.yview)
        self.good_summary_tree['yscrollcommand'] = good_scrollbar.set
        good_scrollbar.grid(row=0, column=1, sticky='ns')
        self.good_summary_tree.bind('<ButtonRelease-1>', lambda e: self._on_column_resize(e, self.good_summary_tree, 'good_summary'))

        ttk.Label(summary_container, text="불량 현황", style='Subtle.TLabel', font=(self.DEFAULT_FONT, int(13 * self.scale_factor), 'bold')).grid(row=2, column=0, sticky='w', pady=(10, 5))
        defect_tree_frame = ttk.Frame(summary_container, style='Sidebar.TFrame')
        defect_tree_frame.grid(row=3, column=0, sticky='nsew')
        defect_tree_frame.grid_columnconfigure(0, weight=1)
        defect_tree_frame.grid_rowconfigure(0, weight=1)

        self.defect_summary_tree = ttk.Treeview(defect_tree_frame, columns=cols, show='headings', style='Treeview')
        self.defect_summary_tree.heading('item_name_spec', text='품목명')
        self.defect_summary_tree.heading('item_code', text='품목코드')
        self.defect_summary_tree.heading('count', text='불량 수량 (개)')

        self.defect_summary_tree.column('item_name_spec', minwidth=100, anchor='w', stretch=tk.YES)
        self.defect_summary_tree.column('item_code', minwidth=100, anchor='w', stretch=tk.YES)
        self.defect_summary_tree.column('count', minwidth=100, anchor='center', stretch=tk.YES)

        self.defect_summary_tree.grid(row=0, column=0, sticky='nsew')
        defect_scrollbar = ttk.Scrollbar(defect_tree_frame, orient='vertical', command=self.defect_summary_tree.yview)
        self.defect_summary_tree['yscrollcommand'] = defect_scrollbar.set
        defect_scrollbar.grid(row=0, column=1, sticky='ns')
        self.defect_summary_tree.bind('<ButtonRelease-1>', lambda e: self._on_column_resize(e, self.defect_summary_tree, 'defect_summary'))

    def _create_center_content(self, parent_frame):
        parent_frame.grid_columnconfigure(0, weight=1)
        
        mode_frame = ttk.Frame(parent_frame, style='TFrame')
        mode_frame.grid(row=0, column=0, sticky='ne', pady=(5, 10), padx=5)
        self.rework_mode_button = ttk.Button(mode_frame, text="리워크 모드", command=self.toggle_rework_mode, style='Secondary.TButton')
        self.rework_mode_button.pack(side=tk.RIGHT, padx=(5,0))

        self.current_item_label = ttk.Label(parent_frame, text="", style='ItemInfo.TLabel', justify='center', anchor='center')
        self.current_item_label.grid(row=1, column=0, sticky='ew', pady=(0, 20))
        
        view_container = ttk.Frame(parent_frame, style='TFrame')
        view_container.grid(row=2, column=0, sticky='nsew')
        parent_frame.grid_rowconfigure(2, weight=1)
        view_container.grid_columnconfigure(0, weight=1)
        view_container.grid_rowconfigure(0, weight=1)

        self.inspection_view_frame = ttk.Frame(view_container, style='TFrame')
        self.inspection_view_frame.grid(row=0, column=0, sticky='nsew')
        self.inspection_view_frame.grid_columnconfigure(0, weight=1)
        self.inspection_view_frame.grid_rowconfigure(4, weight=1)

        self.main_progress_bar = ttk.Progressbar(self.inspection_view_frame, orient='horizontal', mode='determinate', maximum=self.TRAY_SIZE, style='Main.Horizontal.TProgressbar')
        self.main_progress_bar.grid(row=0, column=0, sticky='ew', pady=(5, 20), padx=20)
        
        self.counter_frame = ttk.Frame(self.inspection_view_frame, style='TFrame')
        self.counter_frame.grid(row=1, column=0, pady=(0, 20))
        
        self.good_count_label = ttk.Label(self.counter_frame, text="양품: 0", style='TLabel', foreground=self.COLOR_SUCCESS, font=(self.DEFAULT_FONT, int(14 * self.scale_factor), 'bold'))
        self.main_count_label = ttk.Label(self.counter_frame, text=f"0 / {self.TRAY_SIZE}", style='MainCounter.TLabel', anchor='center')
        self.defect_count_label = ttk.Label(self.counter_frame, text="불량: 0", style='TLabel', foreground=self.COLOR_DEFECT, font=(self.DEFAULT_FONT, int(14 * self.scale_factor), 'bold'))
        
        self.good_count_label.pack(side=tk.LEFT, padx=20)
        self.main_count_label.pack(side=tk.LEFT, padx=20)
        self.defect_count_label.pack(side=tk.LEFT, padx=20)


        self.scan_entry_inspection = tk.Entry(self.inspection_view_frame, justify='center', font=(self.DEFAULT_FONT, int(30 * self.scale_factor), 'bold'), bd=2, relief=tk.SOLID, highlightbackground=self.COLOR_BORDER, highlightcolor=self.COLOR_PRIMARY, highlightthickness=3)
        self.scan_entry_inspection.grid(row=2, column=0, sticky='ew', ipady=int(15 * self.scale_factor), padx=30)
        self.scan_entry_inspection.bind('<Return>', self.process_scan)
        
        self.defect_mode_indicator = ttk.Label(self.inspection_view_frame, text="", font=(self.DEFAULT_FONT, int(12 * self.scale_factor), 'bold'), anchor='center')
        self.defect_mode_indicator.grid(row=3, column=0, sticky='ew', pady=(5, 0), padx=30)
        
        self.list_paned_window = ttk.PanedWindow(self.inspection_view_frame, orient=tk.HORIZONTAL)
        self.list_paned_window.grid(row=4, column=0, sticky='nsew', pady=(10, 0), padx=30)
        
        self.good_frame = ttk.Frame(self.list_paned_window)
        self.good_frame.grid_rowconfigure(0, weight=1)
        self.good_frame.grid_columnconfigure(0, weight=1)
        cols = ('count', 'barcode')
        self.good_items_tree = ttk.Treeview(self.good_frame, columns=cols, show='headings', style='Treeview')
        self.good_items_tree.heading('count', text='No.')
        self.good_items_tree.heading('barcode', text='양품 바코드')
        self.good_items_tree.column('count', width=50, anchor='center', stretch=tk.NO)
        self.good_items_tree.column('barcode', anchor='w', stretch=tk.YES)
        self.good_items_tree.grid(row=0, column=0, sticky='nsew')
        good_scroll = ttk.Scrollbar(self.good_frame, orient='vertical', command=self.good_items_tree.yview)
        good_scroll.grid(row=0, column=1, sticky='ns')
        self.good_items_tree['yscrollcommand'] = good_scroll.set
        
        self.defect_frame = ttk.Frame(self.list_paned_window)
        self.defect_frame.grid_rowconfigure(0, weight=1)
        self.defect_frame.grid_columnconfigure(0, weight=1)
        self.defective_items_tree = ttk.Treeview(self.defect_frame, columns=cols, show='headings', style='Treeview')
        self.defective_items_tree.heading('count', text='No.')
        self.defective_items_tree.heading('barcode', text='불량 바코드')
        self.defective_items_tree.column('count', width=50, anchor='center', stretch=tk.NO)
        self.defective_items_tree.column('barcode', anchor='w', stretch=tk.YES)
        self.defective_items_tree.grid(row=0, column=0, sticky='nsew')
        defect_scroll = ttk.Scrollbar(self.defect_frame, orient='vertical', command=self.defective_items_tree.yview)
        defect_scroll.grid(row=0, column=1, sticky='ns')
        self.defective_items_tree['yscrollcommand'] = defect_scroll.set
        
        self.list_paned_window.add(self.good_frame, weight=1)
        self.list_paned_window.add(self.defect_frame, weight=1)
        
        self.button_frame = ttk.Frame(self.inspection_view_frame, style='TFrame')
        self.button_frame.grid(row=5, column=0, pady=(20, 0))
        self.reset_button = ttk.Button(self.button_frame, text="현재 작업 리셋", command=self.reset_current_work)
        self.reset_button.pack(side=tk.LEFT, padx=10)
        self.undo_button = ttk.Button(self.button_frame, text="↩️ 마지막 판정 취소", command=self.undo_last_inspection, state=tk.DISABLED)
        self.undo_button.pack(side=tk.LEFT, padx=10)
        self.submit_tray_button = ttk.Button(self.button_frame, text="✅ 현재 트레이 제출", command=self.submit_current_tray)
        self.submit_tray_button.pack(side=tk.LEFT, padx=10)

        self.rework_view_frame = ttk.Frame(view_container, style='TFrame')
        self.rework_view_frame.grid(row=0, column=0, sticky='nsew')
        self.rework_view_frame.grid_columnconfigure(0, weight=1)
        self.rework_view_frame.grid_rowconfigure(1, weight=1)

        rework_top_frame = ttk.Frame(self.rework_view_frame, style='TFrame')
        rework_top_frame.grid(row=0, column=0, sticky='ew', pady=(10, 5), padx=20)
        
        self.rework_count_label = ttk.Label(rework_top_frame, text="금일 리워크 완료: 0개", style='TLabel', foreground=self.COLOR_REWORK, font=(self.DEFAULT_FONT, int(14 * self.scale_factor), 'bold'))
        self.rework_count_label.pack(side=tk.LEFT)

        rework_list_container = ttk.Frame(self.rework_view_frame, style='TFrame')
        rework_list_container.grid(row=1, column=0, sticky='nsew', padx=20, pady=10)
        rework_list_container.grid_columnconfigure(0, weight=1)
        rework_list_container.grid_columnconfigure(1, weight=1)
        rework_list_container.grid_rowconfigure(1, weight=1)

        ttk.Label(rework_list_container, text="리워크 대상", font=(self.DEFAULT_FONT, int(12*self.scale_factor), 'bold'), foreground=self.COLOR_DEFECT).grid(row=0, column=0)
        ttk.Label(rework_list_container, text="리워크 완료 (금일)", font=(self.DEFAULT_FONT, int(12*self.scale_factor), 'bold'), foreground=self.COLOR_SUCCESS).grid(row=0, column=1)

        rework_needed_frame = ttk.Frame(rework_list_container)
        rework_needed_frame.grid(row=1, column=0, sticky='nsew', padx=(0, 5))
        rework_needed_frame.grid_rowconfigure(0, weight=1)
        rework_needed_frame.grid_columnconfigure(0, weight=1)
        
        needed_cols = ('barcode', 'defect_time')
        self.rework_needed_tree = ttk.Treeview(rework_needed_frame, columns=needed_cols, show='headings')
        self.rework_needed_tree.heading('barcode', text='바코드')
        self.rework_needed_tree.heading('defect_time', text='불량 발생 시간')
        self.rework_needed_tree.column('barcode', anchor='w')
        self.rework_needed_tree.column('defect_time', width=180, anchor='center')
        self.rework_needed_tree.grid(row=0, column=0, sticky='nsew')
        needed_scroll = ttk.Scrollbar(rework_needed_frame, orient='vertical', command=self.rework_needed_tree.yview)
        needed_scroll.grid(row=0, column=1, sticky='ns')
        self.rework_needed_tree['yscrollcommand'] = needed_scroll.set

        reworked_frame = ttk.Frame(rework_list_container)
        reworked_frame.grid(row=1, column=1, sticky='nsew', padx=(5, 0))
        reworked_frame.grid_rowconfigure(0, weight=1)
        reworked_frame.grid_columnconfigure(0, weight=1)

        reworked_cols = ('barcode', 'rework_time')
        self.reworked_today_tree = ttk.Treeview(reworked_frame, columns=reworked_cols, show='headings')
        self.reworked_today_tree.heading('barcode', text='바코드')
        self.reworked_today_tree.heading('rework_time', text='리워크 시간')
        self.reworked_today_tree.column('barcode', anchor='w')
        self.reworked_today_tree.column('rework_time', width=180, anchor='center')
        self.reworked_today_tree.grid(row=0, column=0, sticky='nsew')
        reworked_scroll = ttk.Scrollbar(reworked_frame, orient='vertical', command=self.reworked_today_tree.yview)
        reworked_scroll.grid(row=0, column=1, sticky='ns')
        self.reworked_today_tree['yscrollcommand'] = reworked_scroll.set
        
        rework_bottom_frame = ttk.Frame(self.rework_view_frame, style='TFrame')
        rework_bottom_frame.grid(row=2, column=0, sticky='ew', pady=(5, 10), padx=20)
        rework_bottom_frame.grid_columnconfigure(0, weight=1)

        self.scan_entry_rework = tk.Entry(rework_bottom_frame, justify='center', font=(self.DEFAULT_FONT, int(30 * self.scale_factor), 'bold'), bd=2, relief=tk.SOLID, highlightbackground=self.COLOR_BORDER, highlightcolor=self.COLOR_REWORK, highlightthickness=3)
        self.scan_entry_rework.grid(row=0, column=0, sticky='ew', ipady=int(15 * self.scale_factor))
        self.scan_entry_rework.bind('<Return>', self.process_scan)
        
        self.scan_entry = self.scan_entry_inspection
        
        self.root.after(100, self._apply_treeview_styles)

    def _create_right_sidebar_content(self, parent_frame):
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_frame['padding'] = (10, 10)
        
        self.date_label = ttk.Label(parent_frame, style='Sidebar.TLabel', font=(self.DEFAULT_FONT, int(18 * self.scale_factor), 'bold'))
        self.date_label.grid(row=0, column=0, pady=(0, 5))
        self.clock_label = ttk.Label(parent_frame, style='Sidebar.TLabel', font=(self.DEFAULT_FONT, int(24 * self.scale_factor), 'bold'))
        self.clock_label.grid(row=1, column=0, pady=(0, 20))
        
        delay_frame = ttk.Frame(parent_frame, style='Card.TFrame', padding=10)
        delay_frame.grid(row=2, column=0, sticky='ew', pady=10)
        delay_frame.grid_columnconfigure(1, weight=1)
        ttk.Label(delay_frame, text="⚙️ 스캔 딜레이 (초):", style='Subtle.TLabel', background=self.COLOR_SIDEBAR_BG).grid(row=0, column=0, sticky='w', padx=(0, 10))
        delay_spinbox = ttk.Spinbox(delay_frame, from_=0.0, to=5.0, increment=0.5, textvariable=self.scan_delay_sec, width=6, font=(self.DEFAULT_FONT, int(12 * self.scale_factor)))
        delay_spinbox.grid(row=0, column=1, sticky='e')

        self.rework_filter_frame = ttk.Frame(parent_frame, style='Card.TFrame', padding=10)
        self.rework_filter_frame.grid(row=3, column=0, sticky='ew', pady=10)
        self.rework_filter_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(self.rework_filter_frame, text="♻️ 리워크 기간 설정", style='Subtle.TLabel', background=self.COLOR_SIDEBAR_BG, font=(self.DEFAULT_FONT, int(11*self.scale_factor), 'bold')).grid(row=0, column=0, columnspan=2, sticky='w')

        today = datetime.date.today()
        one_week_ago = today - datetime.timedelta(days=7)

        self.rework_start_date_var = tk.StringVar(value=one_week_ago.strftime('%Y-%m-%d'))
        self.rework_end_date_var = tk.StringVar(value=today.strftime('%Y-%m-%d'))

        ttk.Label(self.rework_filter_frame, text="시작:", style='Subtle.TLabel', background=self.COLOR_SIDEBAR_BG).grid(row=1, column=0, sticky='w', pady=(5,0))
        start_date_entry = tk.Entry(self.rework_filter_frame, textvariable=self.rework_start_date_var, font=(self.DEFAULT_FONT, int(12 * self.scale_factor)))
        start_date_entry.grid(row=2, column=0, columnspan=2, sticky='ew')

        ttk.Label(self.rework_filter_frame, text="종료:", style='Subtle.TLabel', background=self.COLOR_SIDEBAR_BG).grid(row=3, column=0, sticky='w', pady=(5,0))
        end_date_entry = tk.Entry(self.rework_filter_frame, textvariable=self.rework_end_date_var, font=(self.DEFAULT_FONT, int(12 * self.scale_factor)))
        end_date_entry.grid(row=4, column=0, columnspan=2, sticky='ew')

        load_button = ttk.Button(self.rework_filter_frame, text="불량 데이터 조회", command=self.on_load_rework_data_click, style='Secondary.TButton')
        load_button.grid(row=5, column=0, columnspan=2, sticky='ew', pady=(10,0))

        self.info_cards = {
            'status': self._create_info_card(parent_frame, "⏰ 현재 작업 상태"),
            'stopwatch': self._create_info_card(parent_frame, "⏱️ 현재 트레이 소요 시간"),
            'avg_time': self._create_info_card(parent_frame, "📊 평균 완료 시간"),
            'best_time': self._create_info_card(parent_frame, "🥇 금주 최고 기록")
        }
        card_order = ['status', 'stopwatch', 'avg_time', 'best_time']
        for i, card_key in enumerate(card_order):
            self.info_cards[card_key]['frame'].grid(row=i + 4, column=0, sticky='ew', pady=10)
        
        best_time_card = self.info_cards['best_time']
        best_time_card['frame'].config(style='VelvetCard.TFrame')
        best_time_card['label'].config(style='Velvet.Subtle.TLabel')
        best_time_card['value'].config(style='Velvet.Value.TLabel')
        
        parent_frame.grid_rowconfigure(len(self.info_cards) + 4, weight=1)
        legend_frame = ttk.Frame(parent_frame, style='Sidebar.TFrame', padding=(0, 15))
        legend_frame.grid(row=len(self.info_cards) + 5, column=0, sticky='sew')
        ttk.Label(legend_frame, text="범례:", style='Subtle.TLabel').pack(anchor='w')
        ttk.Label(legend_frame, text="🟩 양품", style='Sidebar.TLabel', foreground=self.COLOR_SUCCESS).pack(anchor='w')
        ttk.Label(legend_frame, text="🟥 불량", style='Sidebar.TLabel', foreground=self.COLOR_DEFECT).pack(anchor='w')
        ttk.Label(legend_frame, text="🟪 리워크", style='Sidebar.TLabel', foreground=self.COLOR_REWORK).pack(anchor='w')
        ttk.Label(legend_frame, text="🟨 휴식/대기", style='Sidebar.TLabel', foreground="#B8860B").pack(anchor='w')

    def _apply_treeview_styles(self):
        try:
            self.good_items_tree.heading('count', style='Good.Treeview.Heading')
            self.good_items_tree.heading('barcode', style='Good.Treeview.Heading')
            self.defective_items_tree.heading('count', style='Defect.Treeview.Heading')
            self.defective_items_tree.heading('barcode', style='Defect.Treeview.Heading')
        except tk.TclError:
            print("Note: Custom treeview heading colors may not be supported on this OS.")

    def _create_info_card(self, parent: ttk.Frame, label_text: str) -> Dict[str, ttk.Widget]:
        card = ttk.Frame(parent, style='Card.TFrame', padding=20)
        label = ttk.Label(card, text=label_text, style='Subtle.TLabel')
        label.pack()
        value_label = ttk.Label(card, text="-", style='Value.TLabel')
        value_label.pack()
        return {'frame': card, 'label': label, 'value': value_label}

    def toggle_rework_mode(self):
        """'리워크 모드'를 켜고 끕니다."""
        if self.current_mode != "rework":
            self.current_mode = "rework"
            today = datetime.date.today()
            one_week_ago = today - datetime.timedelta(days=7)
            self.rework_start_date_var.set(one_week_ago.strftime('%Y-%m-%d'))
            self.rework_end_date_var.set(today.strftime('%Y-%m-%d'))
            self._load_reworkable_defects(one_week_ago, today)
        else:
            self.current_mode = "standard"
            self.reworkable_defects.clear()
            self._populate_rework_trees()

        self._log_event('MODE_CHANGE', detail={'mode': self.current_mode})
        self._apply_mode_ui()
        self._update_current_item_label()
    
    def _apply_mode_ui(self):
        """현재 모드에 맞게 UI를 엄격하게 분리하여 표시합니다."""
        self.apply_scaling()
        if not hasattr(self, 'rework_mode_button'): return

        is_rework = self.current_mode == 'rework'

        self.rework_mode_button.config(text="검사 모드로" if is_rework else "리워크 모드")
        
        if is_rework:
            self.rework_view_frame.tkraise()
            self.rework_filter_frame.grid()
            self.scan_entry = self.scan_entry_rework
            self.rework_count_label.config(text=f"금일 리워크 완료: {len(self.reworked_items_today)}개")
        else:
            self.inspection_view_frame.tkraise()
            self.rework_filter_frame.grid_remove()
            self.scan_entry = self.scan_entry_inspection
            
        self.on_pedal_release_ui_feedback()
        self._update_current_item_label()
        self._schedule_focus_return()

    def _populate_rework_trees(self):
        """리워크 대상 및 완료 목록 Treeview를 다시 그립니다."""
        if not hasattr(self, 'rework_needed_tree'): return

        for i in self.rework_needed_tree.get_children(): self.rework_needed_tree.delete(i)
        for i in self.reworked_today_tree.get_children(): self.reworked_today_tree.delete(i)

        for barcode, info in self.reworkable_defects.items():
            try:
                dt_obj = datetime.datetime.fromisoformat(info['timestamp'])
                timestamp_str = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
            except (TypeError, ValueError):
                timestamp_str = info.get('timestamp', '알 수 없음')
            self.rework_needed_tree.insert('', 'end', values=(barcode, timestamp_str))
        
        for item in self.reworked_items_today:
            self.reworked_today_tree.insert('', 'end', values=(item['barcode'], item['rework_time']))
    
    def _schedule_focus_return(self, delay_ms: int = 100):
        if self.focus_return_job: self.root.after_cancel(self.focus_return_job)
        self.focus_return_job = self.root.after(delay_ms, self._return_focus_to_scan_entry)

    def _return_focus_to_scan_entry(self):
        try:
            if hasattr(self, 'scan_entry') and self.scan_entry.winfo_exists():
                self.scan_entry.focus_set()
            self.focus_return_job = None
        except Exception: pass

    def _update_current_item_label(self):
        if not (hasattr(self, 'current_item_label') and self.current_item_label.winfo_exists()): return
        text, color = "", self.COLOR_TEXT

        if self.current_mode == "rework":
            text = f"♻️ 리워크 모드: 성공적으로 수리된 제품의 바코드를 스캔하세요.\n(리워크 대상: {len(self.reworkable_defects)}개 / 금일 완료: {len(self.reworked_items_today)}개)"
            color = self.COLOR_REWORK
        elif self.current_session.master_label_code:
            name_part = f"현재 품목: {self.current_session.item_name} ({self.current_session.item_code})"
            instruction = f"\n양품 {self.current_session.quantity}개를 목표로 스캔하세요. (불량: {self.DEFECT_PEDAL_KEY_NAME} 페달)"
            text = f"{name_part}{instruction}"
        else: 
            text = "현품표 라벨을 스캔하여 검사를 시작하세요."
            color = self.COLOR_TEXT_SUBTLE
        
        self.current_item_label['text'], self.current_item_label['foreground'] = text, color

    def _parse_new_format_qr(self, qr_data: str) -> Optional[Dict[str, str]]:
        if '=' not in qr_data or '|' not in qr_data: return None
        try:
            parsed = dict(pair.split('=', 1) for pair in qr_data.strip().split('|'))
            if 'CLC' in parsed and 'WID' in parsed: return parsed
            return None
        except ValueError: return None

    def _start_automated_test_thread(self, item_code: str, num_good: int, num_defect: int, num_pallets: int):
        """선택된 품목 코드와 수량으로 자동화 테스트 스레드를 시작합니다."""
        if not item_code:
            messagebox.showwarning("품목 선택 오류", "테스트를 시작할 품목이 선택되지 않았습니다.")
            return
        threading.Thread(
            target=self._automated_test_sequence, 
            args=(item_code, num_good, num_defect, num_pallets), 
            daemon=True
        ).start()

    def _prompt_for_test_item(self):
        """자동 테스트 시작 시 품목과 수량을 선택할 수 있는 팝업창을 띄웁니다."""
        if not self.items_data:
            messagebox.showerror("오류", "Item.csv에 데이터가 없어 테스트를 진행할 수 없습니다.")
            return

        popup = tk.Toplevel(self.root)
        popup.title("자동 테스트 설정")
        popup.geometry("500x320")
        popup.transient(self.root)
        popup.grab_set()
        
        main_frame = ttk.Frame(popup, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="1. 테스트할 품목을 선택하세요.").pack(pady=(0, 5), anchor='w')
        item_display_list = [f"{item.get('Item Name', '이름없음')} ({item.get('Item Code', '코드없음')})" for item in self.items_data]
        item_combobox = ttk.Combobox(main_frame, values=item_display_list, state="readonly", font=(self.DEFAULT_FONT, 12))
        item_combobox.pack(fill=tk.X, pady=(0, 15))
        if item_display_list:
            item_combobox.set(item_display_list[0])

        ttk.Label(main_frame, text="2. 테스트 수량을 설정하세요.").pack(pady=(0, 5), anchor='w')
        settings_frame = ttk.Frame(main_frame)
        settings_frame.pack(fill=tk.X)
        settings_frame.columnconfigure(1, weight=1)

        ttk.Label(settings_frame, text="양품 수량 (개/파렛트):").grid(row=0, column=0, sticky='w', padx=5, pady=2)
        good_var = tk.StringVar(value="5")
        ttk.Spinbox(settings_frame, from_=1, to=100, textvariable=good_var, width=10).grid(row=0, column=2, sticky='e', padx=5, pady=2)
        
        ttk.Label(settings_frame, text="불량 수량 (개/파렛트):").grid(row=1, column=0, sticky='w', padx=5, pady=2)
        defect_var = tk.StringVar(value="2")
        ttk.Spinbox(settings_frame, from_=0, to=100, textvariable=defect_var, width=10).grid(row=1, column=2, sticky='e', padx=5, pady=2)
        
        ttk.Label(settings_frame, text="테스트 파렛트 수:").grid(row=2, column=0, sticky='w', padx=5, pady=2)
        pallet_var = tk.StringVar(value="1")
        ttk.Spinbox(settings_frame, from_=1, to=10, textvariable=pallet_var, width=10).grid(row=2, column=2, sticky='e', padx=5, pady=2)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=20)

        def get_settings():
            try:
                num_good = int(good_var.get())
                num_defect = int(defect_var.get())
                num_pallets = int(pallet_var.get())
                if num_good <= 0 or num_defect < 0 or num_pallets <= 0:
                    raise ValueError("수량은 0보다 커야 합니다 (불량 제외).")
                return num_good, num_defect, num_pallets
            except (ValueError, TypeError) as e:
                messagebox.showerror("입력 오류", f"수량 설정이 올바르지 않습니다.\n{e}", parent=popup)
                return None, None, None

        def start_with_selection():
            num_good, num_defect, num_pallets = get_settings()
            if num_good is None: return

            selected_str = item_combobox.get()
            if not selected_str:
                messagebox.showwarning("선택 오류", "콤보박스에서 품목을 선택해주세요.", parent=popup)
                return
            try:
                item_code = re.search(r'\((\S+)\)$', selected_str).group(1)
                popup.destroy()
                self._start_automated_test_thread(item_code, num_good, num_defect, num_pallets)
            except (AttributeError, IndexError):
                messagebox.showerror("오류", "선택된 품목에서 품목 코드를 추출할 수 없습니다.", parent=popup)

        def start_with_random():
            num_good, num_defect, num_pallets = get_settings()
            if num_good is None: return

            random_item = random.choice(self.items_data)
            item_code = random_item.get('Item Code')
            popup.destroy()
            self._start_automated_test_thread(item_code, num_good, num_defect, num_pallets)

        ttk.Button(button_frame, text="선택한 품목으로 시작", command=start_with_selection).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="무작위 품목으로 시작", command=start_with_random).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="취소", command=popup.destroy).pack(side=tk.LEFT, padx=10)

    def _automated_test_sequence(self, test_item_code: str, num_good: int, num_defect: int, num_pallets: int):
        """선택된 품목 코드와 수량으로 자동화 테스트의 전체 시나리오를 실행합니다."""
        try:
            TEST_WORKER = "AutoTester"
            REWORK_COUNT = 5
            DELAY = 1.8 

            self.root.after(0, lambda: messagebox.showinfo("테스트 시작", f"자동화된 테스트를 시작합니다.\n\n품목: {test_item_code}\n작업자: {TEST_WORKER}\n설정: 양품 {num_good}, 불량 {num_defect}개씩 {num_pallets} 파렛트"))
            time.sleep(DELAY)

            if self.worker_name:
                self.root.after(0, self.change_worker)
                time.sleep(DELAY)

            self.root.after(0, lambda: self._create_test_defect_logs(test_item_code, REWORK_COUNT))
            self.root.after(0, lambda: self.show_status_message(f"{REWORK_COUNT}개의 테스트 불량 데이터 생성 완료", self.COLOR_PRIMARY))
            time.sleep(DELAY)

            self.root.after(0, lambda: self.worker_entry.insert(0, TEST_WORKER))
            time.sleep(0.5)
            self.root.after(0, self.start_work)
            self.root.after(0, lambda: self.show_status_message("로그인 자동 실행", self.COLOR_PRIMARY))
            time.sleep(DELAY)

            for pallet_num in range(num_pallets):
                self.root.after(0, lambda p=pallet_num+1: self.show_status_message(f"파렛트 {p}/{num_pallets} 검사 시작", self.COLOR_PRIMARY))
                time.sleep(DELAY)

                master_label = self._generate_test_master_label(test_item_code, quantity=num_good)
                self.root.after(0, lambda ml=master_label: self._process_scan_logic(ml))
                self.root.after(0, lambda: self.show_status_message("현품표 스캔", self.COLOR_PRIMARY))
                time.sleep(DELAY)

                for i in range(num_good):
                    barcode = f"TEST-GOOD-P{pallet_num}-{test_item_code}-{datetime.datetime.now().strftime('%f')}-{i}"
                    self.root.after(0, lambda b=barcode: self._process_scan_logic(b))
                    self.root.after(0, lambda n=i+1: self.show_status_message(f"양품 스캔 ({n}/{num_good})", self.COLOR_SUCCESS))
                    time.sleep(DELAY)

                for i in range(num_defect):
                    self.is_auto_testing_defect = True
                    barcode = f"TEST-DEFECT-P{pallet_num}-{test_item_code}-{datetime.datetime.now().strftime('%f')}-{i}"
                    self.root.after(0, lambda b=barcode: self._process_scan_logic(b))
                    self.root.after(0, lambda n=i+1: self.show_status_message(f"불량 스캔 ({n}/{num_defect})", self.COLOR_DEFECT))
                    time.sleep(DELAY)
                self.is_auto_testing_defect = False

                self.root.after(0, lambda p=pallet_num+1: self.show_status_message(f"파렛트 {p} 자동 완료 처리", self.COLOR_PRIMARY))
                time.sleep(DELAY)

            self.root.after(0, self.toggle_rework_mode)
            self.root.after(0, lambda: self.show_status_message("리워크 모드로 전환", self.COLOR_REWORK))
            time.sleep(DELAY)

            if self.reworkable_defects:
                rework_barcode = list(self.reworkable_defects.keys())[0]
                self.root.after(0, lambda: self._process_scan_logic(rework_barcode))
                self.root.after(0, lambda: self.show_status_message(f"리워크 스캔: {rework_barcode}", self.COLOR_REWORK))
                time.sleep(DELAY)
            
            self.root.after(0, self.toggle_rework_mode)
            self.root.after(0, lambda: self.show_status_message("일반 모드로 복귀", self.COLOR_PRIMARY))
            time.sleep(DELAY)

            self.root.after(0, lambda: messagebox.showinfo("테스트 완료", "자동화된 테스트가 성공적으로 완료되었습니다."))

        except Exception as e:
            self.is_auto_testing_defect = False
            self.root.after(0, lambda: messagebox.showerror("테스트 오류", f"자동 테스트 중 오류가 발생했습니다:\n{e}"))

    def _create_test_defect_logs(self, item_code: str, count: int):
        """리워크 테스트를 위한 불량 데이터를 로그 파일에 직접 생성합니다."""
        if not self.worker_name:
            self.root.after(0, lambda: messagebox.showwarning("오류", "먼저 작업자로 로그인해주세요."))
            return
            
        self.root.after(0, lambda: self.show_status_message(f"'{item_code}' 불량 데이터 {count}개 생성 중...", self.COLOR_DEFECT))
        
        for i in range(count):
            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
            test_barcode = f"TEST-DEFECT-{item_code}-{timestamp}-{i+1:04d}"
            self._log_event('INSPECTION_DEFECTIVE', detail={'barcode': test_barcode})
            time.sleep(0.01)

        self.root.after(0, lambda: self.show_status_message(f"테스트용 불량 데이터 {count}개 생성 완료.", self.COLOR_SUCCESS))

    def _generate_test_master_label(self, item_code: str, quantity: int = 10) -> str:
        """테스트용 현품표 QR 문자열을 생성합니다."""
        now = datetime.datetime.now()
        return f"WID=TEST-WID-{now.strftime('%H%M%S')}|CLC={item_code}|QT={quantity}|FPB=TEST-FPB|OBD={now.strftime('%Y%m%d')}|PHS={now.hour}|SPC=TEST-SPC|IG=TEST-IG"

    def _generate_rework_test_logs(self, count: int):
        self.show_status_message(f"리워크 테스트 로그 {count}개 생성 중...", self.COLOR_REWORK)
        self.root.update_idletasks()

        base_timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        for i in range(count):
            barcode = f"TEST-REWORK-{base_timestamp}-{i+1:03d}"
            defect_time = (datetime.datetime.now() - datetime.timedelta(seconds=count-i)).isoformat()
            self._log_event('INSPECTION_DEFECTIVE', detail={'barcode': barcode})
            
            reworked_data = {
                'barcode': barcode,
                'rework_time': (datetime.datetime.now() - datetime.timedelta(seconds=count-i-1)).strftime('%Y-%m-%d %H:%M:%S')
            }
            self.reworked_items_today.insert(0, reworked_data)
            
            log_detail = {
                'barcode': barcode,
                'rework_time': reworked_data['rework_time'],
                'original_defect_info': {
                    'timestamp': defect_time,
                    'worker': self.worker_name
                }
            }
            self._log_event('REWORK_SUCCESS', detail=log_detail)

        self.rework_count_label.config(text=f"금일 리워크 완료: {len(self.reworked_items_today)}개")
        self._populate_rework_trees()
        self._update_current_item_label()
        self.show_status_message(f"리워크 테스트 로그 {count} 세트를 생성했습니다.", self.COLOR_SUCCESS)
        self._update_summary_title()

    def _generate_test_logs(self, count: int):
        if not self.current_session.master_label_code:
            if not self.items_data:
                self.show_fullscreen_warning("오류", "품목 데이터(Item.csv)가 없습니다.", self.COLOR_DEFECT)
                return

            random_item = random.choice(self.items_data)
            self.current_session.item_code = random_item.get('Item Code', '')
            self.current_session.item_name = random_item.get('Item Name', '')
            self.current_session.item_spec = random_item.get('Spec', '')
            self.current_session.quantity = count

            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
            self.current_session.master_label_code = f"TEST-MASTER-{self.current_session.item_code}-{timestamp}"
            self._log_event('RANDOM_TEST_SESSION_START', detail={'item_code': self.current_session.item_code, 'item_name': self.current_session.item_name})
            
            self._update_current_item_label()
            self._update_center_display()
            self.root.update_idletasks()
            
            for i in range(count):
                test_barcode = f"TEST-{self.current_session.item_code}-{timestamp}-{i+1:03d}"
                self.record_inspection_result(test_barcode, 'Good')
            return

        original_session_info = self.current_session.__dict__.copy()
        tray_capacity = original_session_info.get('quantity', 60)
        if tray_capacity <= 0: tray_capacity = 60

        num_pallets_to_create = (count + tray_capacity - 1) // tray_capacity
        items_to_generate = count

        self.show_status_message(f"테스트 로그 {count}개 생성 중...", self.COLOR_PRIMARY)
        self.root.update_idletasks()

        for pallet_num in range(num_pallets_to_create):
            self.current_session = InspectionSession()
            for key, value in original_session_info.items():
                if hasattr(self.current_session, key):
                    setattr(self.current_session, key, value)
            
            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
            self.current_session.master_label_code = f"TEST-TRAY-{original_session_info['item_code']}-{timestamp}"

            items_for_this_pallet = min(items_to_generate, tray_capacity)
            self.current_session.quantity = items_for_this_pallet

            for i in range(items_for_this_pallet):
                barcode = f"TEST-{self.current_session.item_code}-{timestamp}-{i:03d}"
                self.current_session.good_items.append({'barcode': barcode, 'timestamp': datetime.datetime.now().isoformat(), 'status': 'Good'})
                self.current_session.scanned_barcodes.append(barcode)
            
            self.complete_session()
            
            items_to_generate -= items_for_this_pallet
            if items_to_generate <= 0:
                break
        
        self.show_status_message(f"테스트 로그 {count}개 생성을 완료했습니다.", self.COLOR_SUCCESS)

    def process_scan(self, event=None):
        """UI의 스캔 엔트리에서 바코드를 읽어 로직을 실행합니다."""
        raw_barcode = self.scan_entry.get().strip()
        self.scan_entry.delete(0, tk.END)
        self._process_scan_logic(raw_barcode)

    def _process_scan_logic(self, raw_barcode: str):
        """바코드 데이터를 받아 실제 처리 로직을 수행합니다."""
        current_time = time.monotonic()
        if current_time - self.last_scan_time < self.scan_delay_sec.get():
            return
        self.last_scan_time = current_time
        
        if not raw_barcode: return

        if raw_barcode.upper().startswith("_CREATE_DEFECTS_"):
            try:
                parts = raw_barcode.split('_')
                item_code = parts[2]
                count = int(parts[3])
                threading.Thread(target=self._create_test_defect_logs, args=(item_code, count), daemon=True).start()
            except Exception as e:
                messagebox.showerror("오류", f"불량 데이터 생성 코드 형식 오류입니다.\n형식: _CREATE_DEFECTS_[품목코드]_[수량]_\n오류: {e}")
            return
        
        if raw_barcode.upper() == "_RUN_AUTO_TEST_":
            self.root.after(0, self._prompt_for_test_item)
            return

        barcode = raw_barcode
        try:
            if '|' not in raw_barcode and len(raw_barcode) > 20:
                temp_barcode = raw_barcode.replace('-', '+').replace('_', '/')
                padded_barcode = temp_barcode + '=' * (-len(temp_barcode) % 4)
                decoded_bytes = base64.b64decode(padded_barcode)
                decoded_string = decoded_bytes.decode('utf-8')
                if '|' in decoded_string and '=' in decoded_string:
                    barcode = decoded_string
                    self._log_event('QR_BASE64_DECODED', detail={'original': raw_barcode, 'decoded': barcode})
        except (binascii.Error, UnicodeDecodeError):
            pass

        self._update_last_activity_time()
        
        if barcode.upper().startswith("TEST_LOG_"):
            try:
                count = int(barcode.upper().split('_')[2])
                if count > 0:
                    if self.current_mode == 'rework':
                        self._generate_rework_test_logs(count)
                    else:
                        self._generate_test_logs(count)
                    return
            except (IndexError, ValueError):
                pass

        if self.current_mode == 'rework':
            if barcode in self.reworkable_defects:
                self.record_rework_success(barcode)
            else:
                self.show_fullscreen_warning("리워크 대상 아님", f"해당 바코드'{barcode}'는 리워크 대상 목록에 없습니다.", self.COLOR_DEFECT)
                self._log_event('REWORK_FAIL_NOT_FOUND', detail={'barcode': barcode})
            return

        is_master_label_format = False
        parsed_data = self._parse_new_format_qr(barcode)
        if parsed_data:
            is_master_label_format = True
        elif len(barcode) == self.ITEM_CODE_LENGTH and any(item['Item Code'] == barcode for item in self.items_data):
            is_master_label_format = True

        if self.current_session.master_label_code and is_master_label_format and barcode != self.current_session.master_label_code:
            self.show_status_message(f"'{self.current_session.item_name}' 작업을 자동 제출하고 새 작업을 시작합니다.", self.COLOR_PRIMARY)
            self.root.update_idletasks()
            time.sleep(1)
            self.current_session.is_partial_submission = True
            self.complete_session()
        
        if not self.current_session.master_label_code:
            if not is_master_label_format:
                self.show_fullscreen_warning("작업 시작 오류", "먼저 현품표 라벨을 스캔하여 작업을 시작해주세요.", self.COLOR_DEFECT)
                return
            
            if parsed_data and barcode in self.completed_master_labels:
                self.show_fullscreen_warning("작업 중복", f"이미 완료된 현품표입니다.\n\n{barcode}", self.COLOR_DEFECT)
                self._log_event('SCAN_FAIL_DUPLICATE_MASTER', detail={'barcode': barcode})
                return
            
            if parsed_data:
                item_code_from_qr = parsed_data.get('CLC')
                matched_item = next((item for item in self.items_data if item['Item Code'] == item_code_from_qr), None)
                if not matched_item:
                    self.show_fullscreen_warning("품목 없음", f"새 현품표의 품목코드 '{item_code_from_qr}'에 해당하는 정보를 찾을 수 없습니다.", self.COLOR_DEFECT)
                    return
                self.current_session.phs = parsed_data.get('PHS', '')
                self.current_session.master_label_code = barcode
                self.current_session.item_code = item_code_from_qr
                self.current_session.item_name = matched_item.get('Item Name', '')
                self.current_session.item_spec = matched_item.get('Spec', '')
                self.current_session.work_order_id = parsed_data.get('WID', '')
                self.current_session.supplier_code = parsed_data.get('SPC', '')
                self.current_session.finished_product_batch = parsed_data.get('FPB', '')
                self.current_session.outbound_date = parsed_data.get('OBD', '')
                self.current_session.item_group = parsed_data.get('IG', '')
                try: self.current_session.quantity = int(parsed_data.get('QT', self.TRAY_SIZE))
                except (ValueError, TypeError): self.current_session.quantity = self.TRAY_SIZE
                self._log_event('MASTER_LABEL_SCANNED', detail=parsed_data)
            else: # Legacy format
                matched_item = next((item for item in self.items_data if item['Item Code'] == barcode), None)
                if not matched_item:
                    self.show_fullscreen_warning("품목 없음", f"현품표 코드 '{barcode}'에 해당하는 품목 정보를 찾을 수 없습니다.", self.COLOR_DEFECT)
                    return
                self.current_session.master_label_code, self.current_session.item_code = barcode, barcode
                self.current_session.item_name = matched_item.get('Item Name', '')
                self.current_session.item_spec = matched_item.get('Spec', '')
                self.current_session.quantity = self.TRAY_SIZE
                self._log_event('MASTER_LABEL_SCANNED', detail={'code': barcode, 'format': 'legacy'})
            
            self._apply_mode_ui()
            self._update_center_display()
            self._update_current_item_label()
            self._start_stopwatch()
            self._save_current_session_state()
            return

        if self.current_session.master_label_code:
            is_auto_testing_defect = getattr(self, 'is_auto_testing_defect', False)
            is_defect_scan = keyboard.is_pressed(self.DEFECT_PEDAL_KEY_NAME.lower()) or is_auto_testing_defect
            
            if len(barcode) <= self.ITEM_CODE_LENGTH:
                self.show_fullscreen_warning("바코드 형식 오류", f"제품 바코드는 {self.ITEM_CODE_LENGTH}자리보다 길어야 합니다.", self.COLOR_DEFECT)
                return
            if self.current_session.item_code not in barcode:
                self.current_session.mismatch_error_count += 1
                self.current_session.has_error_or_reset = True
                self.show_fullscreen_warning("품목 코드 불일치!", f"제품의 품목 코드가 일치하지 않습니다.\n[기준: {self.current_session.item_code}]", self.COLOR_DEFECT)
                self._log_event('SCAN_FAIL_MISMATCH', detail={'expected': self.current_session.item_code, 'scanned': barcode})
                return
            if barcode in self.current_session.scanned_barcodes:
                self.current_session.mismatch_error_count += 1
                self.current_session.has_error_or_reset = True
                self.show_fullscreen_warning("바코드 중복!", f"제품 바코드 '{barcode}'는 이미 검사되었습니다.", self.COLOR_DEFECT)
                self._log_event('SCAN_FAIL_DUPLICATE', detail={'barcode': barcode})
                return
            
            status = 'Defective' if is_defect_scan else 'Good'
            self.record_inspection_result(barcode, status)

    def record_inspection_result(self, barcode: str, status: str):
        if status == 'Good':
            if self.success_sound: self.success_sound.play()
            item_data = {'barcode': barcode, 'timestamp': datetime.datetime.now().isoformat(), 'status': 'Good'}
            self.current_session.good_items.append(item_data)
            self._log_event('INSPECTION_GOOD', detail={'barcode': barcode})
        else:
            if self.success_sound: self.success_sound.play()
            item_data = {'barcode': barcode, 'timestamp': datetime.datetime.now().isoformat(), 'status': 'Defective'}
            self.current_session.defective_items.append(item_data)
            self.current_session.has_error_or_reset = True
            self._log_event('INSPECTION_DEFECTIVE', detail={'barcode': barcode})

        self.current_session.scanned_barcodes.append(barcode)
        self._redraw_scan_trees()
        self._update_center_display()
        self._update_current_item_label()
        self.undo_button['state'] = tk.NORMAL
        self._save_current_session_state()
        
        if len(self.current_session.good_items) >= self.current_session.quantity:
            self.complete_session()

    def on_load_rework_data_click(self):
        start_date_str = self.rework_start_date_var.get()
        end_date_str = self.rework_end_date_var.get()
        
        try:
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            messagebox.showerror("날짜 형식 오류", "날짜를 'YYYY-MM-DD' 형식으로 입력해주세요.")
            return
            
        if start_date > end_date:
            messagebox.showerror("기간 설정 오류", "시작 날짜는 종료 날짜보다 이전이어야 합니다.")
            return

        if self.current_mode != 'rework':
            self.toggle_rework_mode()

        self._load_reworkable_defects(start_date, end_date)
        self._update_current_item_label()
        self._schedule_focus_return()

    def record_rework_success(self, barcode: str):
        if self.success_sound: self.success_sound.play()
        
        original_defect_info = self.reworkable_defects.pop(barcode, None)
        if original_defect_info is None: return

        reworked_data = {
            'barcode': barcode,
            'rework_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.reworked_items_today.insert(0, reworked_data)
        
        log_detail = {
            'barcode': barcode,
            'rework_time': reworked_data['rework_time'],
            'original_defect_info': original_defect_info
        }
        self._log_event('REWORK_SUCCESS', detail=log_detail)
        
        self.rework_count_label.config(text=f"금일 리워크 완료: {len(self.reworked_items_today)}개")
        self.show_status_message(f"리워크 성공: {barcode}", self.COLOR_SUCCESS)
        
        self._populate_rework_trees()
        self._update_current_item_label()
        self._update_summary_title()

    def _load_reworkable_defects(self, start_date: datetime.date, end_date: datetime.date):
        self.reworkable_defects.clear()
        defects = {}
        reworked = set()
        
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        self.show_status_message(f"{start_date_str} ~ {end_date_str} 기간의 데이터를 불러오는 중...", self.COLOR_REWORK)
        self.root.update_idletasks()

        log_file_pattern = re.compile(r"검사작업이벤트로그_.*_(\d{8})\.csv")
        rework_log_file_pattern = re.compile(r"리워크작업이벤트로그_.*_(\d{8})\.csv")

        try:
            all_log_files = [os.path.join(self.save_folder, f) for f in os.listdir(self.save_folder) if log_file_pattern.match(f)]
            for log_path in all_log_files:
                try:
                    match = log_file_pattern.search(os.path.basename(log_path))
                    if not match: continue
                    
                    file_date = datetime.datetime.strptime(match.group(1), '%Y%m%d').date()
                    if not (start_date <= file_date <= end_date): continue
                    
                    with open(log_path, 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row.get('event') == 'INSPECTION_DEFECTIVE':
                                details_str = row.get('details')
                                if not details_str: continue
                                try:
                                    details = json.loads(details_str)
                                    barcode = details.get('barcode')
                                    if barcode:
                                        defects[barcode] = {
                                            'timestamp': row.get('timestamp'),
                                            'worker': row.get('worker')
                                        }
                                except json.JSONDecodeError: continue
                except Exception as e:
                    print(f"불량 목록 로드 중 '{log_path}' 파일 처리 오류: {e}")

            all_rework_files = [os.path.join(self.save_folder, f) for f in os.listdir(self.save_folder) if rework_log_file_pattern.match(f)]
            for log_path in all_rework_files:
                try:
                    with open(log_path, 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row.get('event') == 'REWORK_SUCCESS':
                                details_str = row.get('details')
                                if not details_str: continue
                                try:
                                    details = json.loads(details_str)
                                    barcode = details.get('barcode')
                                    if barcode: reworked.add(barcode)
                                except json.JSONDecodeError: continue
                except Exception as e:
                     print(f"리워크 목록 로드 중 '{log_path}' 파일 처리 오류: {e}")

        except FileNotFoundError:
            print("로그 폴더를 찾을 수 없습니다.")

        self.reworkable_defects = {barcode: info for barcode, info in defects.items() if barcode not in reworked}
        
        self._populate_rework_trees()
        self._log_event("REWORK_LIST_LOADED", detail={'count': len(self.reworkable_defects), 'start_date': start_date_str, 'end_date': end_date_str})
        self.show_status_message(f"리워크 가능 불량품 {len(self.reworkable_defects)}개를 불러왔습니다.", self.COLOR_REWORK)
        
    def _redraw_scan_trees(self):
        if not hasattr(self, 'good_items_tree') or not self.good_items_tree.winfo_exists(): return
        for i in self.good_items_tree.get_children(): self.good_items_tree.delete(i)
        for i in self.defective_items_tree.get_children(): self.defective_items_tree.delete(i)
        for idx, item in enumerate(self.current_session.good_items):
            self.good_items_tree.insert('', 0, values=(idx + 1, item['barcode']))
        for idx, item in enumerate(self.current_session.defective_items):
            self.defective_items_tree.insert('', 0, values=(idx + 1, item['barcode']))

    def complete_session(self):
        self._stop_stopwatch()
        self._stop_idle_checker()
        self.undo_button['state'] = tk.DISABLED
        is_test = "TEST" in self.current_session.master_label_code
        has_error = self.current_session.has_error_or_reset
        is_partial = self.current_session.is_partial_submission
        is_restored = self.current_session.is_restored_session

        log_detail = {
            'master_label_code': self.current_session.master_label_code,
            'item_code': self.current_session.item_code,
            'item_name': self.current_session.item_name,
            'item_spec': self.current_session.item_spec,
            'scan_count': len(self.current_session.scanned_barcodes),
            'tray_capacity': self.current_session.quantity,
            'scanned_product_barcodes': [item['barcode'] for item in self.current_session.good_items],
            'defective_product_barcodes': [item['barcode'] for item in self.current_session.defective_items],
            'work_time_sec': self.current_session.stopwatch_seconds,
            'error_count': self.current_session.mismatch_error_count,
            'total_idle_seconds': self.current_session.total_idle_seconds,
            'has_error_or_reset': has_error,
            'is_partial_submission': is_partial,
            'is_restored_session': is_restored,
            'start_time': self.current_session.start_time.isoformat() if self.current_session.start_time else None,
            'end_time': datetime.datetime.now().isoformat(),
            'is_test': is_test
        }
        self._log_event('TRAY_COMPLETE', detail=log_detail)
        
        if not is_test and self._parse_new_format_qr(self.current_session.master_label_code):
            self.completed_master_labels.add(self.current_session.master_label_code)

        item_code = self.current_session.item_code
        if item_code not in self.work_summary:
            self.work_summary[item_code] = {'name': self.current_session.item_name, 'spec': self.current_session.item_spec, 
                                            'pallet_count': 0, 'test_pallet_count': 0, 'defective_ea_count': 0}

        defective_count_in_session = len(self.current_session.defective_items)
        self.work_summary[item_code]['defective_ea_count'] += defective_count_in_session
        self.work_summary[item_code]['name'] = self.current_session.item_name
        self.work_summary[item_code]['spec'] = self.current_session.item_spec

        if is_test:
            self.work_summary[item_code]['test_pallet_count'] += 1
            self.show_status_message(f"테스트 세션('{self.current_session.item_name}')이 완료되었습니다.", self.COLOR_SUCCESS)
        else:
            self.work_summary[item_code]['pallet_count'] += 1
            if not is_partial: self.total_tray_count += 1
            if not has_error and not is_partial and not is_restored and self.current_session.stopwatch_seconds > 0:
                self.completed_tray_times.append(self.current_session.stopwatch_seconds)
            if is_partial: self.show_status_message(f"'{self.current_session.item_name}' 부분 제출 완료!", self.COLOR_PRIMARY)
            else: self.show_status_message(f"'{self.current_session.item_name}' 1 파렛트 검사 완료!", self.COLOR_SUCCESS)

        self.current_session = InspectionSession()
        self._redraw_scan_trees()
        self._delete_current_session_state()
        self._update_all_summaries()
        self._reset_ui_to_waiting_state()
        self.tray_last_end_time = datetime.datetime.now()

    def _reset_ui_to_waiting_state(self):
        self._update_current_item_label()
        if self.info_cards.get('stopwatch'):
            self.info_cards['stopwatch']['value']['text'] = "00:00"
        self._set_idle_style(is_idle=True)
        self._apply_mode_ui()
        self._update_center_display()
        self.on_pedal_release_ui_feedback()

    def undo_last_inspection(self):
        self._update_last_activity_time()
        if not self.current_session.scanned_barcodes: return
        last_barcode = self.current_session.scanned_barcodes.pop()
        last_item_status = None
        for i, item in enumerate(self.current_session.good_items):
            if item['barcode'] == last_barcode:
                self.current_session.good_items.pop(i)
                last_item_status = "Good"
                break
        if not last_item_status:
            for i, item in enumerate(self.current_session.defective_items):
                if item['barcode'] == last_barcode:
                    self.current_session.defective_items.pop(i)
                    last_item_status = "Defective"
                    break
        self._redraw_scan_trees()
        self._update_center_display()
        self._log_event('INSPECTION_UNDO', detail={'barcode': last_barcode, 'status': last_item_status})
        self.show_status_message(f"'{last_barcode}' 판정이 취소되었습니다.", self.COLOR_DEFECT)
        self._update_current_item_label()
        if not self.current_session.scanned_barcodes: self.undo_button['state'] = tk.DISABLED
        self._save_current_session_state()
        self._schedule_focus_return()
        
    def reset_current_work(self):
        self._update_last_activity_time()
        if self.current_session.master_label_code and messagebox.askyesno("확인", "현재 진행중인 검사를 초기화하시겠습니까?"):
            self._stop_stopwatch()
            self._stop_idle_checker()
            self.is_idle = False
            self._log_event('TRAY_RESET', detail={'scan_count': len(self.current_session.scanned_barcodes)})
            self.current_session = InspectionSession()
            self._redraw_scan_trees()
            self._delete_current_session_state()
            self._update_all_summaries()
            self.undo_button['state'] = tk.DISABLED
            self._reset_ui_to_waiting_state()
            self.show_status_message("현재 작업이 초기화되었습니다.", self.COLOR_DEFECT)
            self._schedule_focus_return()

    def submit_current_tray(self):
        self._update_last_activity_time()
        if not self.current_session.master_label_code or not self.current_session.scanned_barcodes:
            self.show_status_message("제출할 검사 내역이 없습니다.", self.COLOR_TEXT_SUBTLE)
            return
        good_count, defect_count = len(self.current_session.good_items), len(self.current_session.defective_items)
        msg = f"현재 양품 {good_count}개, 불량 {defect_count}개가 검사되었습니다.\n이 트레이를 완료로 처리하시겠습니까?"
        if messagebox.askyesno("트레이 제출 확인", msg):
            self.current_session.is_partial_submission = True
            self.complete_session()
        self._schedule_focus_return()

    def _update_all_summaries(self):
        self._update_summary_title()
        self._update_summary_list()
        self._update_avg_time()
        self._update_best_time()
        self._update_center_display()
        
    def _update_summary_title(self):
        if hasattr(self, 'summary_title_label') and self.summary_title_label.winfo_exists():
            rework_text = f" / 리워크 {len(self.reworked_items_today)}개" if self.reworked_items_today else ""
            total_pallets = sum(d.get('pallet_count', 0) + d.get('test_pallet_count', 0) for d in self.work_summary.values())
            self.summary_title_label.config(text=f"금일 작업 현황 (총 {total_pallets} 파렛트{rework_text})")

    def _update_summary_list(self):
        if not (hasattr(self, 'good_summary_tree') and self.good_summary_tree.winfo_exists()): return

        for i in self.good_summary_tree.get_children(): self.good_summary_tree.delete(i)
        for i in self.defect_summary_tree.get_children(): self.defect_summary_tree.delete(i)
        
        for item_code, data in sorted(self.work_summary.items()):
            pallet_count = data.get('pallet_count', 0)
            test_pallet_count = data.get('test_pallet_count', 0)
            if pallet_count > 0 or test_pallet_count > 0:
                count_display = f"{pallet_count} 파렛트"
                if test_pallet_count > 0:
                    count_display += f" (테스트: {test_pallet_count})"
                self.good_summary_tree.insert('', 'end', values=(f"{data.get('name', '')}", item_code, count_display.strip()))

            defective_ea_count = data.get('defective_ea_count', 0)
            if defective_ea_count > 0:
                count_display = f"{defective_ea_count} 개"
                self.defect_summary_tree.insert('', 'end', values=(f"{data.get('name', '')}", item_code, count_display))

    def _update_avg_time(self):
        card = self.info_cards.get('avg_time')
        if not card or not card['value'].winfo_exists(): return
        if self.completed_tray_times:
            avg = sum(self.completed_tray_times) / len(self.completed_tray_times)
            card['value']['text'] = f"{int(avg // 60):02d}:{int(avg % 60):02d}"
        else: card['value']['text'] = "-"
    
    def _update_best_time(self):
        card = self.info_cards.get('best_time')
        if not card or not card['value'].winfo_exists(): return
        if self.completed_tray_times:
            best_time = min(self.completed_tray_times)
            card['value']['text'] = f"{int(best_time // 60):02d}:{int(best_time % 60):02d}"
        else: card['value']['text'] = "-"

    def _update_center_display(self):
        if not (hasattr(self, 'main_count_label') and self.main_count_label.winfo_exists()): return
        
        if self.current_session.master_label_code:
            good_count = len(self.current_session.good_items)
            defect_count = len(self.current_session.defective_items)
            total_quantity_in_tray = self.current_session.quantity

            self.good_count_label['text'] = f"양품: {good_count}"
            self.defect_count_label['text'] = f"불량: {defect_count}"
            self.main_count_label.config(text=f"{good_count} / {total_quantity_in_tray}")
            self.main_progress_bar['maximum'] = total_quantity_in_tray
            self.main_progress_bar.config(value=good_count)
        else:
            self.good_count_label['text'] = "양품: -"
            self.defect_count_label['text'] = "불량: -"
            self.main_count_label.config(text="- / -")
            self.main_progress_bar.config(value=0)
            self.main_progress_bar['maximum'] = self.TRAY_SIZE

    def _update_clock(self):
        if not self.root.winfo_exists(): return
        now = datetime.datetime.now()
        if hasattr(self, 'date_label') and self.date_label.winfo_exists():
            self.date_label['text'] = now.strftime('%Y-%m-%d')
        if hasattr(self, 'clock_label') and self.clock_label.winfo_exists():
            self.clock_label['text'] = now.strftime('%H:%M:%S')
        self.clock_job = self.root.after(1000, self._update_clock)
        
    def _start_stopwatch(self, resume=False):
        if not resume:
            self.current_session.stopwatch_seconds = 0
            self.current_session.start_time = datetime.datetime.now()
        self._update_last_activity_time()
        if self.stopwatch_job: self.root.after_cancel(self.stopwatch_job)
        self._update_stopwatch()

    def _stop_stopwatch(self):
        if self.stopwatch_job:
            self.root.after_cancel(self.stopwatch_job)
            self.stopwatch_job = None
            
    def _update_stopwatch(self):
        if not self.root.winfo_exists() or self.is_idle: return
        mins, secs = divmod(int(self.current_session.stopwatch_seconds), 60)
        if self.info_cards.get('stopwatch') and self.info_cards['stopwatch']['value'].winfo_exists():
            self.info_cards['stopwatch']['value']['text'] = f"{mins:02d}:{secs:02d}"
        self.current_session.stopwatch_seconds += 1
        self.stopwatch_job = self.root.after(1000, self._update_stopwatch)

    def _start_idle_checker(self):
        self._update_last_activity_time()
        if self.idle_check_job: self.root.after_cancel(self.idle_check_job)
        self.idle_check_job = self.root.after(1000, self._check_for_idle)

    def _stop_idle_checker(self):
        if self.idle_check_job:
            self.root.after_cancel(self.idle_check_job)
            self.idle_check_job = None

    def _update_last_activity_time(self):
        self.last_activity_time = datetime.datetime.now()
        if self.is_idle: self._wakeup_from_idle()

    def _check_for_idle(self):
        is_active_session = self.current_session.master_label_code or self.current_mode == 'rework'
        if not self.root.winfo_exists() or self.is_idle or not is_active_session or not self.last_activity_time:
            self.idle_check_job = self.root.after(1000, self._check_for_idle)
            return
        if (datetime.datetime.now() - self.last_activity_time).total_seconds() > self.IDLE_THRESHOLD_SEC:
            self.is_idle = True
            self._set_idle_style(is_idle=True)
            self._log_event('IDLE_START')
        else: self.idle_check_job = self.root.after(1000, self._check_for_idle)
            
    def _wakeup_from_idle(self):
        if not self.is_idle: return
        self.is_idle = False
        if self.last_activity_time:
            idle_duration = (datetime.datetime.now() - self.last_activity_time).total_seconds()
            if self.current_session.master_label_code:
                self.current_session.total_idle_seconds += idle_duration
            self._log_event('IDLE_END', detail={'duration_sec': f"{idle_duration:.2f}"})
        self._set_idle_style(is_idle=False)
        self._start_idle_checker()
        if self.current_session.master_label_code:
            self._update_stopwatch()
        self.show_status_message("작업 재개.", self.COLOR_SUCCESS)

    def _set_idle_style(self, is_idle: bool):
        if not (hasattr(self, 'info_cards') and self.info_cards): return
        style_prefix = 'Idle.' if is_idle else ''
        card_style = f'{style_prefix}TFrame' if style_prefix else 'Card.TFrame'
        for key in ['status', 'stopwatch', 'avg_time']:
            if self.info_cards.get(key):
                card = self.info_cards[key]
                card['frame']['style'], card['label']['style'], card['value']['style'] = card_style, f'{style_prefix}Subtle.TLabel', f'{style_prefix}Value.TLabel'
        status_widget = self.info_cards['status']['value']
        if is_idle:
            status_widget['text'], status_widget['foreground'] = "대기 중", self.COLOR_TEXT
            self.show_status_message("휴식 상태입니다. 스캔하여 작업을 재개하세요.", self.COLOR_IDLE, duration=10000)
        else:
            status_widget['text'], status_widget['foreground'] = "작업 중", self.COLOR_SUCCESS
            
    def _on_column_resize(self, event: tk.Event, tree: ttk.Treeview, name: str):
        if tree.identify_region(event.x, event.y) == "separator":
            self.root.after(10, self._save_column_widths, tree, name)
            self._schedule_focus_return()

    def _save_column_widths(self, tree: ttk.Treeview, name: str):
        for col_id in tree["columns"]: self.column_widths[f'{name}_{col_id}'] = tree.column(col_id, "width")
        self.save_settings()

    def _start_warning_beep(self):
        if self.error_sound: self.error_sound.play(loops=-1)

    def _stop_warning_beep(self):
        if self.error_sound: self.error_sound.stop()

    def show_fullscreen_warning(self, title: str, message: str, color: str):
        self._start_warning_beep()
        popup = tk.Toplevel(self.root)
        popup.title(title)
        popup.attributes('-fullscreen', True)
        popup.configure(bg=color)
        popup.grab_set()
        def on_popup_close():
            self._stop_warning_beep()
            popup.destroy()
            self._schedule_focus_return()
        title_font = (self.DEFAULT_FONT, int(60 * self.scale_factor), 'bold')
        msg_font = (self.DEFAULT_FONT, int(30 * self.scale_factor), 'bold')
        tk.Label(popup, text=title, font=title_font, fg='white', bg=color).pack(pady=(100, 50), expand=True)
        tk.Label(popup, text=message, font=msg_font, fg='white', bg=color, wraplength=self.root.winfo_screenwidth() - 100, justify=tk.CENTER).pack(pady=20, expand=True)
        btn = tk.Button(popup, text="확인 (클릭)", font=msg_font, command=on_popup_close, bg='white', fg=color, relief='flat', padx=20, pady=10)
        btn.pack(pady=50, expand=True)
        btn.focus_set()

    def _cancel_all_jobs(self):
        for job_attr in ['clock_job', 'status_message_job', 'stopwatch_job', 'idle_check_job', 'focus_return_job']:
            job_id = getattr(self, job_attr, None)
            if job_id:
                self.root.after_cancel(job_id)
                setattr(self, job_attr, None)
        self._stop_warning_beep()

    def on_closing(self):
        if messagebox.askokcancel("종료", "프로그램을 종료하시겠습니까?"):
            if self.worker_name: self._log_event('WORK_END')
            if self.worker_name and self.current_session.master_label_code:
                if messagebox.askyesno("작업 저장", "진행 중인 작업을 저장하고 종료할까요?"): self._save_current_session_state()
                else: self._delete_current_session_state()
            else: self._delete_current_session_state()
            if hasattr(self, 'paned_window') and self.paned_window.winfo_exists():
                try:
                    num_panes = len(self.paned_window.panes())
                    if num_panes > 1: self.paned_window_sash_positions = {str(i): self.paned_window.sashpos(i) for i in range(num_panes - 1)}
                except tk.TclError: pass
            self.save_settings()
            self._cancel_all_jobs()
            self.log_queue.put((None, None))
            if self.log_thread.is_alive(): self.log_thread.join(timeout=1.0)
            pygame.quit()
            self.root.destroy()
            
    def _event_log_writer(self):
        while True:
            try:
                log_type, log_entry = self.log_queue.get(timeout=1.0)
                if log_entry is None: break

                target_path = self.rework_log_file_path if log_type == 'rework' else self.log_file_path

                if not target_path:
                    time.sleep(0.1)
                    self.log_queue.put((log_type, log_entry))
                    continue

                file_exists = os.path.exists(target_path) and os.stat(target_path).st_size > 0
                with open(target_path, 'a', newline='', encoding='utf-8-sig') as f:
                    headers = ['timestamp', 'worker', 'event', 'details']
                    writer = csv.DictWriter(f, fieldnames=headers)
                    if not file_exists:
                        writer.writeheader()
                    
                    log_entry_for_csv = log_entry.copy()
                    log_entry_for_csv['worker'] = log_entry_for_csv.pop('worker_name')
                    writer.writerow(log_entry_for_csv)

            except queue.Empty: continue
            except Exception as e: print(f"로그 파일 쓰기 오류: {e}")

    def _log_event(self, event_type: str, detail: Optional[Dict] = None):
        if not self.worker_name and event_type not in ['UPDATE_CHECK_FOUND', 'UPDATE_STARTED', 'UPDATE_FAILED', 'ITEM_DATA_LOADED']:
            return
            
        worker = self.worker_name if self.worker_name else "System"
        
        log_entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'worker_name': worker,
            'event': event_type,
            'details': json.dumps(detail, ensure_ascii=False) if detail else ''
        }
        
        log_type = 'rework' if event_type.startswith('REWORK_') else 'main'
        self.log_queue.put((log_type, log_entry))

    def show_status_message(self, message: str, color: Optional[str] = None, duration: int = 4000):
        if self.status_message_job: self.root.after_cancel(self.status_message_job)
        self.status_label['text'], self.status_label['fg'] = message, color or self.COLOR_TEXT
        self.status_message_job = self.root.after(duration, self._reset_status_message)
    
    def _reset_status_message(self):
        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            self.status_label['text'], self.status_label['fg'] = "준비", self.COLOR_TEXT
            
    def run(self):
        self.root.mainloop()

    def show_completion_summary_window(self):
        summary_win = tk.Toplevel(self.root)
        summary_win.title("작업 완료 현황")
        summary_win.geometry("1000x700")
        summary_win.configure(bg=self.COLOR_BG)

        top_frame = ttk.Frame(summary_win, style='Sidebar.TFrame', padding=10)
        top_frame.pack(fill=tk.X)
        ttk.Label(top_frame, text="완료된 작업 현황", style='Sidebar.TLabel', font=(self.DEFAULT_FONT, 14, 'bold')).pack(side=tk.LEFT)
        
        tree_frame = ttk.Frame(summary_win, style='TFrame', padding=10)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        cols = ('obd', 'phs', 'item_code', 'item_name', 'count')
        tree = ttk.Treeview(tree_frame, columns=cols, show='headings')
        tree.grid(row=0, column=0, sticky='nsew')
        
        tree.heading('obd', text='출고 날짜')
        tree.heading('phs', text='차수')
        tree.heading('item_code', text='품목 코드')
        tree.heading('item_name', text='품목명')
        tree.heading('count', text='완료된 트레이 수')

        tree.column('obd', width=120, anchor='center')
        tree.column('phs', width=60, anchor='center')
        tree.column('item_code', width=150, anchor='w')
        tree.column('item_name', width=250, anchor='w')
        tree.column('count', width=120, anchor='center')

        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        tree['yscrollcommand'] = scrollbar.set

        def refresh_data():
            try:
                summary_data = self._get_completion_summary_data()
                self._populate_summary_tree(tree, summary_data)
                self.show_status_message("완료 현황을 새로고침했습니다.", self.COLOR_SUCCESS)
            except Exception as e:
                messagebox.showerror("오류", f"데이터를 불러오는 중 오류가 발생했습니다:\n{e}", parent=summary_win)

        ttk.Button(top_frame, text="새로고침", command=refresh_data, style='Secondary.TButton').pack(side=tk.RIGHT)
        
        refresh_data()
        summary_win.transient(self.root)
        summary_win.grab_set()
        self.root.wait_window(summary_win)

    def _get_completion_summary_data(self) -> Dict:
        """모든 로그 파일을 읽어 날짜별, 차수별로 완료된 트레이를 집계합니다."""
        summary = {}
        log_file_pattern = re.compile(r"검사작업이벤트로그_.*_(\d{8})\.csv")
        
        all_log_files = [os.path.join(self.save_folder, f) for f in os.listdir(self.save_folder) if log_file_pattern.match(f)]

        for log_path in all_log_files:
            try:
                with open(log_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('event') == 'TRAY_COMPLETE':
                            details = json.loads(row['details'])
                            
                            master_code = details.get('master_label_code')
                            if not master_code: continue

                            qr_data = self._parse_new_format_qr(master_code)
                            if not qr_data: continue

                            obd = qr_data.get('OBD', 'N/A')
                            phs = qr_data.get('PHS', 'N/A')
                            item_code = details.get('item_code')
                            item_name = details.get('item_name', '알 수 없음')
                            
                            if not item_code: continue

                            key = (obd, phs, item_code)
                            if key not in summary:
                                summary[key] = {'count': 0, 'item_name': item_name}
                            summary[key]['count'] += 1
            except Exception as e:
                print(f"'{log_path}' 처리 중 오류: {e}")
        
        return summary

    def _populate_summary_tree(self, tree: ttk.Treeview, data: Dict):
        """집계된 데이터를 Treeview에 채웁니다."""
        for i in tree.get_children():
            tree.delete(i)
        
        sorted_keys = sorted(data.keys(), key=lambda x: (x[0], x[1]), reverse=True)

        for key in sorted_keys:
            obd, phs, item_code = key
            info = data[key]
            tree.insert('', 'end', values=(obd, phs, item_code, info['item_name'], info['count']))


if __name__ == "__main__":
    app = InspectionProgram()
    threading.Thread(target=check_and_apply_updates, args=(app,), daemon=True).start()
    app.run()