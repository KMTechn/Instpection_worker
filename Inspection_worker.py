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
import keyboard # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< [추가] 키보드 라이브러리 임포트

# ####################################################################
# # 자동 업데이트 기능 (이벤트 로깅 추가)
# ####################################################################

REPO_OWNER = "KMTechn"
REPO_NAME = "Inspection_program"
CURRENT_VERSION = "v1.0.0" 

def check_for_updates(app_instance):
    try:
        api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        latest_version = response.json()['tag_name']
        if latest_version.strip().lower() != CURRENT_VERSION.strip().lower():
            app_instance._log_event('UPDATE_CHECK_FOUND', detail={'current': CURRENT_VERSION, 'latest': latest_version})
            for asset in response.json()['assets']:
                if asset['name'].endswith('.zip'):
                    return asset['browser_download_url'], latest_version
        return None, None
    except requests.exceptions.RequestException as e:
        print(f"업데이트 확인 중 오류: {e}")
        return None, None

def download_and_apply_update(url, app_instance):
    try:
        app_instance._log_event('UPDATE_STARTED', detail={'url': url})
        zip_path = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "update.zip")
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        temp_update_folder = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "temp_update")
        if os.path.exists(temp_update_folder):
            import shutil
            shutil.rmtree(temp_update_folder)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_update_folder)
        os.remove(zip_path)

        application_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        updater_script_path = os.path.join(application_path, "updater.bat")
        
        extracted_content = os.listdir(temp_update_folder)
        new_program_folder_path = os.path.join(temp_update_folder, extracted_content[0]) if len(extracted_content) == 1 and os.path.isdir(os.path.join(temp_update_folder, extracted_content[0])) else temp_update_folder
            
        with open(updater_script_path, "w", encoding='utf-8') as bat_file:
            bat_file.write(f"""@echo off
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
# # 메인 어플리케이션
# ####################################################################

@dataclass
class InspectionSession:
    master_label_code: str = ""
    item_code: str = ""
    item_name: str = ""
    item_spec: str = ""
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
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

class InspectionProgram:
    APP_TITLE = f"품질 검사 시스템 ({CURRENT_VERSION})"
    DEFAULT_FONT = 'Malgun Gothic'
    TRAY_SIZE = 60
    SETTINGS_DIR = 'config'
    SETTINGS_FILE = 'inspection_settings.json'
    IDLE_THRESHOLD_SEC = 420
    ITEM_CODE_LENGTH = 13
    
    DEFECT_PEDAL_KEY_NAME = 'F12'

    CURRENT_TRAY_STATE_FILE = "_current_inspection_state.json"
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

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(self.APP_TITLE)
        self.root.state('zoomed')
        
        self.current_mode = "standard"

        self.root.configure(bg=self.COLOR_BG)

        self.log_queue: queue.Queue = queue.Queue()
        self.log_file_path: Optional[str] = None
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
        
        # [수정] UI 피드백을 위한 이벤트 핸들러는 유지
        self.root.bind_all(f"<KeyPress-{self.DEFECT_PEDAL_KEY_NAME}>", self.on_pedal_press_ui_feedback)
        self.root.bind_all(f"<KeyRelease-{self.DEFECT_PEDAL_KEY_NAME}>", self.on_pedal_release_ui_feedback)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_pedal_press_ui_feedback(self, event=None):
        # 이 함수는 이제 오직 시각적 피드백만을 담당합니다.
        if self.current_mode != "standard":
            return
            
        if hasattr(self, 'defect_mode_indicator'):
            self.defect_mode_indicator.config(text="불량 모드 ON", background=self.COLOR_DEFECT, foreground='white')
        if hasattr(self, 'scan_entry'):
            self.scan_entry.config(highlightcolor=self.COLOR_DEFECT)

    def on_pedal_release_ui_feedback(self, event=None):
        # 이 함수는 이제 오직 시각적 피드백만을 담당합니다.
        if self.current_mode != "standard":
            if hasattr(self, 'scan_entry'):
                self.scan_entry.config(highlightcolor=self.COLOR_DEFECT)
            return

        if hasattr(self, 'defect_mode_indicator'):
            bg_color = self.COLOR_DEFECT_BG if self.current_mode == "defective_only" else self.COLOR_BG
            self.defect_mode_indicator.config(text="", background=bg_color)
        if hasattr(self, 'scan_entry'):
            self.scan_entry.config(highlightcolor=self.COLOR_PRIMARY)
    
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
        base=10; s,m,l,xl,xxl = (int(factor*self.scale_factor) for factor in [base,base+2,base+8,base+20,base+60])
        
        bg_color = self.COLOR_DEFECT_BG if self.current_mode == "defective_only" else self.COLOR_BG
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
        
        self.style.configure('TButton', font=(self.DEFAULT_FONT, m, 'bold'), padding=(int(15*self.scale_factor), int(10*self.scale_factor)), borderwidth=0)
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
        
        if hasattr(self, 'status_label'): self.status_label['font'] = (self.DEFAULT_FONT, s)

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
        ttk.Label(center_frame, text="작업자 이름", style='TLabel', font=(self.DEFAULT_FONT, int(12*self.scale_factor))).pack(pady=(10, 5))
        self.worker_entry = tk.Entry(center_frame, width=25, font=(self.DEFAULT_FONT, int(18*self.scale_factor), 'bold'), bd=2, relief=tk.SOLID, justify='center', highlightbackground=self.COLOR_BORDER, highlightcolor=self.COLOR_PRIMARY, highlightthickness=2)
        self.worker_entry.pack(ipady=int(12*self.scale_factor))
        self.worker_entry.bind('<Return>', self.start_work)
        self.worker_entry.focus()
        ttk.Button(center_frame, text="작업 시작", command=self.start_work, style='TButton', width=20).pack(pady=60, ipady=int(10*self.scale_factor))

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
                self._save_current_session_state()
                self._log_event('WORK_PAUSE')
            self._cancel_all_jobs()
            self.worker_name = ""
            self.show_worker_input_screen()

    def _load_session_state(self):
        today = datetime.date.today()
        sanitized_name = re.sub(r'[\\/*?:"<>|]', "", self.worker_name)
        self.log_file_path = os.path.join(self.save_folder, f"품질검사이벤트로그_{sanitized_name}_{today.strftime('%Y%m%d')}.csv")
        
        if not os.path.exists(self.log_file_path):
            self._log_event('LOG_FILE_CREATED', detail={'path': self.log_file_path})

        self.total_tray_count = 0
        self.completed_tray_times = []
        self.work_summary = {}
        self.tray_last_end_time = None
        lookback_days = 7
        lookback_start_date = today - datetime.timedelta(days=lookback_days)
        log_file_pattern = re.compile(f"품질검사이벤트로그_{re.escape(sanitized_name)}_(\\d{{8}})\\.csv")
        all_log_files = []
        try:
            for filename in os.listdir(self.save_folder):
                match = log_file_pattern.match(filename)
                if match:
                    file_date = datetime.datetime.strptime(match.group(1), '%Y%m%d').date()
                    if file_date >= lookback_start_date: all_log_files.append(os.path.join(self.save_folder, filename))
        except FileNotFoundError: pass
        all_completed_sessions = []
        for log_path in sorted(all_log_files):
            if not os.path.exists(log_path): continue
            try:
                with open(log_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('event') == 'SESSION_COMPLETE':
                            try:
                                details = json.loads(row['details'])
                                details['timestamp'] = datetime.datetime.fromisoformat(row['timestamp'])
                                all_completed_sessions.append(details)
                            except (json.JSONDecodeError, KeyError): continue
            except Exception as e: print(f"로그 파일 '{log_path}' 처리 중 오류: {e}")
        if not all_completed_sessions: return
        today_sessions_list = [s for s in all_completed_sessions if s['timestamp'].date() == today]
        start_of_week = today - datetime.timedelta(days=today.weekday())
        current_week_sessions_list = [s for s in all_completed_sessions if s['timestamp'].date() >= start_of_week]
        for session in today_sessions_list:
            item_code = session.get('item_code', 'UNKNOWN')
            if item_code not in self.work_summary: self.work_summary[item_code] = {'name': session.get('item_name', '알 수 없음'), 'spec': session.get('spec', ''), 'count': 0, 'test_count': 0}
            if session.get('is_test_tray', False): self.work_summary[item_code]['test_count'] += 1
            else: self.work_summary[item_code]['count'] += 1
            if not session.get('is_test_tray', False) and not session.get('is_partial_submission', False): self.total_tray_count += 1
        clean_sessions = [s for s in current_week_sessions_list if (s.get('good_count') == self.TRAY_SIZE and not s.get('has_error_or_reset') and not s.get('is_partial_submission') and not s.get('is_restored_session') and not s.get('is_test_tray'))]
        if clean_sessions:
            MINIMUM_REALISTIC_TIME_PER_PC = 2.0
            valid_times = [float(s.get('work_time_sec', 0.0)) for s in clean_sessions if float(s.get('work_time_sec', 0.0)) / self.TRAY_SIZE >= MINIMUM_REALISTIC_TIME_PER_PC]
            if valid_times: self.completed_tray_times = valid_times
        if any(self.work_summary): self.show_status_message(f"금일 작업 현황을 불러왔습니다.", self.COLOR_PRIMARY)
    
    def _save_current_session_state(self):
        if not self.current_session.master_label_code: return
        state_path = os.path.join(self.save_folder, self.CURRENT_TRAY_STATE_FILE)
        try:
            serializable_state = {k: v.isoformat() if isinstance(v, datetime.datetime) else v for k, v in self.current_session.__dict__.items()}
            with open(state_path, 'w', encoding='utf-8') as f: json.dump(serializable_state, f, indent=4)
        except Exception as e: print(f"현재 세션 상태 저장 실패: {e}")

    def _load_current_session_state(self):
        state_path = os.path.join(self.save_folder, self.CURRENT_TRAY_STATE_FILE)
        if not os.path.exists(state_path): return
        try:
            with open(state_path, 'r', encoding='utf-8') as f: saved_state = json.load(f)
            saved_worker = saved_state.get('worker_name')
            if not saved_worker: self._delete_current_session_state(); return
            total_scans = len(saved_state.get('good_items', [])) + len(saved_state.get('defective_items', []))
            msg_base = f"· 품목: {saved_state.get('item_name', '알 수 없음')}\n· 검사 수: {total_scans}개"
            if saved_worker == self.worker_name:
                if messagebox.askyesno("이전 작업 복구", f"이전에 마치지 못한 검사 작업을 이어서 시작하시겠습니까?\n\n{msg_base}"):
                    self._restore_session_from_state(saved_state)
                    self._log_event('SESSION_RESTORE')
                else: self._delete_current_session_state()
            else:
                response = messagebox.askyesnocancel("작업 인수 확인", f"이전 작업자 '{saved_worker}'님이 마치지 않은 작업이 있습니다.\n\n이 작업을 이어서 진행하시겠습니까?\n\n{msg_base}")
                if response is True:
                    self._restore_session_from_state(saved_state)
                    self._log_event('SESSION_TAKEOVER', detail={'previous': saved_worker, 'new': self.worker_name})
                elif response is False:
                    if messagebox.askyesno("작업 삭제", "이전 작업을 영구적으로 삭제하시겠습니까?"):
                        self._delete_current_session_state()
                        self.show_status_message(f"'{saved_worker}'님의 이전 작업이 삭제되었습니다.", self.COLOR_DEFECT)
                    else: self.worker_name = ""; self.show_worker_input_screen()
                else: self.worker_name = ""; self.show_worker_input_screen()
        except Exception as e:
            messagebox.showwarning("오류", f"이전 작업 상태 로드 실패: {e}")
            self._delete_current_session_state()

    def _restore_session_from_state(self, state: Dict[str, Any]):
        state['start_time'] = datetime.datetime.fromisoformat(state['start_time']) if state.get('start_time') else None
        self.current_session = InspectionSession(**state)
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

        if self.current_session.master_label_code:
            self._update_current_item_label()
            self._redraw_scan_trees()
            self._update_center_display()
            self._start_stopwatch(resume=True)
        else:
            self._reset_ui_to_waiting_state()
        
        self._apply_mode_ui()

        self.root.after(100, lambda: self._bind_focus_return_recursive(self.paned_window))
        
        self.scan_entry.focus()

    def _set_initial_sash_positions(self):
        self.paned_window.update_idletasks()
        try:
            total_width = self.paned_window.winfo_width()
            if total_width <= 1: self.root.after(50, self._set_initial_sash_positions); return
            sash_0_pos = int(total_width * 0.25)
            sash_1_pos = int(total_width * 0.75)
            self.paned_window.sashpos(0, sash_0_pos)
            self.paned_window.sashpos(1, sash_1_pos)
        except tk.TclError: pass

    def _create_left_sidebar_content(self, parent_frame):
        parent_frame.grid_columnconfigure(0, weight=1); parent_frame['padding'] = (10, 10)
        parent_frame.grid_rowconfigure(0, weight=1)
        
        top_frame = ttk.Frame(parent_frame, style='Sidebar.TFrame'); top_frame.grid(row=0, column=0, sticky='nsew', pady=(0, 10)); top_frame.grid_columnconfigure(0, weight=1)
        header_frame = ttk.Frame(top_frame, style='Sidebar.TFrame'); header_frame.grid(row=0, column=0, sticky='ew', pady=(0, 20)); header_frame.grid_columnconfigure(0, weight=1)
        worker_info_frame = ttk.Frame(header_frame, style='Sidebar.TFrame'); worker_info_frame.grid(row=0, column=0, sticky='w')
        ttk.Label(worker_info_frame, text=f"작업자: {self.worker_name}", style='Sidebar.TLabel').pack(side=tk.LEFT)
        buttons_frame = ttk.Frame(header_frame, style='Sidebar.TFrame'); buttons_frame.grid(row=0, column=1, sticky='e')
        ttk.Button(buttons_frame, text="작업자 변경", command=self.change_worker, style='Secondary.TButton').pack(side=tk.LEFT, padx=(0, 5))
        self.summary_title_label = ttk.Label(top_frame, text="누적 작업 현황", style='Subtle.TLabel', font=(self.DEFAULT_FONT, int(14*self.scale_factor),'bold')); self.summary_title_label.grid(row=1, column=0, sticky='w', pady=(0,10))
        tree_frame = ttk.Frame(top_frame, style='Sidebar.TFrame'); tree_frame.grid(row=2, column=0, sticky='nsew'); top_frame.grid_rowconfigure(2, weight=1); tree_frame.grid_columnconfigure(0, weight=1); tree_frame.grid_rowconfigure(0, weight=1)
        from tkinter import font as tkfont
        m = int(12 * self.scale_factor); heading_font = tkfont.Font(font=(self.DEFAULT_FONT, m, 'bold'))
        padding = 20; default_widths = {'item_name_spec': heading_font.measure("품목명") + padding, 'item_code': heading_font.measure("품목코드") + padding, 'count': heading_font.measure("완료 수량") + padding}
        cols = ('item_name_spec', 'item_code', 'count'); self.summary_tree = ttk.Treeview(tree_frame, columns=cols, show='headings', style='Treeview')
        self.summary_tree.heading('item_name_spec', text='품목명'); self.summary_tree.heading('item_code', text='품목코드'); self.summary_tree.heading('count', text='완료 수량')
        self.summary_tree.column('item_name_spec', width=self.column_widths.get('summary_tree_item_name_spec', default_widths['item_name_spec']), minwidth=default_widths['item_name_spec'], anchor='w', stretch=tk.YES)
        self.summary_tree.column('item_code', width=self.column_widths.get('summary_tree_item_code', default_widths['item_code']), minwidth=default_widths['item_code'], anchor='w', stretch=tk.NO)
        self.summary_tree.column('count', width=self.column_widths.get('summary_tree_count', default_widths['count']), minwidth=default_widths['count'], anchor='center', stretch=tk.NO)
        self.summary_tree.grid(row=0, column=0, sticky='nsew')
        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=self.summary_tree.yview); self.summary_tree['yscrollcommand'] = scrollbar.set; scrollbar.grid(row=0, column=1, sticky='ns')
        self.summary_tree.bind('<ButtonRelease-1>', lambda e: self._on_column_resize(e, self.summary_tree, 'summary_tree'))

    def _create_center_content(self, parent_frame):
        parent_frame.grid_rowconfigure(6, weight=1) 
        parent_frame.grid_columnconfigure(0, weight=1)

        mode_frame = ttk.Frame(parent_frame, style='TFrame')
        mode_frame.grid(row=0, column=0, sticky='ne', pady=(5, 10), padx=5)
        self.mode_switch_button = ttk.Button(mode_frame, text="불량 전용 모드", command=self.toggle_inspection_mode, style='Secondary.TButton')
        self.mode_switch_button.pack()

        self.current_item_label = ttk.Label(parent_frame, text="", style='ItemInfo.TLabel', justify='center', anchor='center')
        self.current_item_label.grid(row=1, column=0, sticky='ew', pady=(0, 20))
        
        self.main_progress_bar = ttk.Progressbar(parent_frame, orient='horizontal', mode='determinate', maximum=self.TRAY_SIZE, style='Main.Horizontal.TProgressbar')
        self.main_progress_bar.grid(row=2, column=0, sticky='ew', pady=(5, 20), padx=20)

        self.counter_frame = ttk.Frame(parent_frame, style='TFrame')
        self.counter_frame.grid(row=3, column=0, pady=(0, 20))
        self.good_count_label = ttk.Label(self.counter_frame, text="양품: 0", style='TLabel', foreground=self.COLOR_SUCCESS, font=(self.DEFAULT_FONT, int(14*self.scale_factor), 'bold'))
        self.main_count_label = ttk.Label(self.counter_frame, text=f"0 / {self.TRAY_SIZE}", style='MainCounter.TLabel', anchor='center')
        self.defect_count_label = ttk.Label(self.counter_frame, text="불량: 0", style='TLabel', foreground=self.COLOR_DEFECT, font=(self.DEFAULT_FONT, int(14*self.scale_factor), 'bold'))
        
        self.good_count_label.pack(side=tk.LEFT, padx=20)
        self.main_count_label.pack(side=tk.LEFT, padx=20)
        self.defect_count_label.pack(side=tk.LEFT, padx=20)
        
        self.scan_entry = tk.Entry(parent_frame, justify='center', font=(self.DEFAULT_FONT, int(30*self.scale_factor), 'bold'), bd=2, relief=tk.SOLID, highlightbackground=self.COLOR_BORDER, highlightcolor=self.COLOR_PRIMARY, highlightthickness=3)
        self.scan_entry.grid(row=4, column=0, sticky='ew', ipady=int(15*self.scale_factor), padx=30)
        self.scan_entry.bind('<Return>', self.process_scan)
        
        self.defect_mode_indicator = ttk.Label(parent_frame, text="", font=(self.DEFAULT_FONT, int(12*self.scale_factor), 'bold'), anchor='center')
        self.defect_mode_indicator.grid(row=5, column=0, sticky='ew', pady=(5,0), padx=30)

        list_container = ttk.Frame(parent_frame, style='TFrame')
        list_container.grid(row=6, column=0, sticky='nsew', pady=(10, 0), padx=30)
        list_container.grid_columnconfigure(0, weight=1)
        list_container.grid_columnconfigure(1, weight=1)
        list_container.grid_rowconfigure(0, weight=1)

        good_frame = ttk.Frame(list_container)
        good_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        good_frame.grid_rowconfigure(0, weight=1)
        good_frame.grid_columnconfigure(0, weight=1)
        
        cols = ('count', 'barcode')
        self.good_items_tree = ttk.Treeview(good_frame, columns=cols, show='headings', style='Treeview')
        self.good_items_tree.heading('count', text='No.')
        self.good_items_tree.heading('barcode', text='양품 바코드')
        self.good_items_tree.column('count', width=50, anchor='center', stretch=tk.NO)
        self.good_items_tree.column('barcode', anchor='w', stretch=tk.YES)
        self.good_items_tree.grid(row=0, column=0, sticky='nsew')
        good_scroll = ttk.Scrollbar(good_frame, orient='vertical', command=self.good_items_tree.yview)
        good_scroll.grid(row=0, column=1, sticky='ns')
        self.good_items_tree['yscrollcommand'] = good_scroll.set
        
        defect_frame = ttk.Frame(list_container)
        defect_frame.grid(row=0, column=1, sticky='nsew', padx=(5, 0))
        defect_frame.grid_rowconfigure(0, weight=1)
        defect_frame.grid_columnconfigure(0, weight=1)

        self.defective_items_tree = ttk.Treeview(defect_frame, columns=cols, show='headings', style='Treeview')
        self.defective_items_tree.heading('count', text='No.')
        self.defective_items_tree.heading('barcode', text='불량 바코드')
        self.defective_items_tree.column('count', width=50, anchor='center', stretch=tk.NO)
        self.defective_items_tree.column('barcode', anchor='w', stretch=tk.YES)
        self.defective_items_tree.grid(row=0, column=0, sticky='nsew')
        defect_scroll = ttk.Scrollbar(defect_frame, orient='vertical', command=self.defective_items_tree.yview)
        defect_scroll.grid(row=0, column=1, sticky='ns')
        self.defective_items_tree['yscrollcommand'] = defect_scroll.set
        
        self.root.after(100, self._apply_treeview_styles)

        button_frame = ttk.Frame(parent_frame)
        button_frame.grid(row=7, column=0, pady=(20, 0))
        ttk.Button(button_frame, text="현재 작업 리셋", command=self.reset_current_work).pack(side=tk.LEFT, padx=10)
        self.undo_button = ttk.Button(button_frame, text="↩️ 마지막 판정 취소", command=self.undo_last_inspection, state=tk.DISABLED)
        self.undo_button.pack(side=tk.LEFT, padx=10)
        self.submit_tray_button = ttk.Button(button_frame, text="✅ 현재 트레이 제출", command=self.submit_current_tray)
        self.submit_tray_button.pack(side=tk.LEFT, padx=10)

    def _create_right_sidebar_content(self, parent_frame):
        parent_frame.grid_columnconfigure(0, weight=1); parent_frame['padding'] = (10, 10)
        
        self.date_label = ttk.Label(parent_frame, style='Sidebar.TLabel', font=(self.DEFAULT_FONT, int(18*self.scale_factor),'bold'))
        self.date_label.grid(row=0, column=0, pady=(0,5))
        
        self.clock_label = ttk.Label(parent_frame, style='Sidebar.TLabel', font=(self.DEFAULT_FONT, int(24*self.scale_factor),'bold'))
        self.clock_label.grid(row=1, column=0, pady=(0,20))

        delay_frame = ttk.Frame(parent_frame, style='Card.TFrame', padding=10)
        delay_frame.grid(row=2, column=0, sticky='ew', pady=10)
        delay_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(delay_frame, text="⚙️ 스캔 딜레이 (초):", style='Subtle.TLabel', background=self.COLOR_SIDEBAR_BG).grid(row=0, column=0, sticky='w', padx=(0,10))
        delay_spinbox = ttk.Spinbox(delay_frame, from_=0.0, to=5.0, increment=0.5, textvariable=self.scan_delay_sec, width=6, font=(self.DEFAULT_FONT, int(12*self.scale_factor)))
        delay_spinbox.grid(row=0, column=1, sticky='e')

        self.info_cards = {
            'status': self._create_info_card(parent_frame, "⏰ 현재 작업 상태"), 
            'stopwatch': self._create_info_card(parent_frame, "⏱️ 현재 트레이 소요 시간"),
            'avg_time': self._create_info_card(parent_frame, "📊 평균 완료 시간"), 
            'best_time': self._create_info_card(parent_frame, "🥇 금주 최고 기록")
        }
        card_order = ['status', 'stopwatch', 'avg_time', 'best_time']
        for i, card_key in enumerate(card_order): 
            self.info_cards[card_key]['frame'].grid(row=i + 3, column=0, sticky='ew', pady=10)

        best_time_card = self.info_cards['best_time']
        best_time_card['frame'].config(style='VelvetCard.TFrame')
        best_time_card['label'].config(style='Velvet.Subtle.TLabel')
        best_time_card['value'].config(style='Velvet.Value.TLabel')
        
        parent_frame.grid_rowconfigure(len(self.info_cards) + 3, weight=1)
        legend_frame = ttk.Frame(parent_frame, style='Sidebar.TFrame', padding=(0,15))
        legend_frame.grid(row=len(self.info_cards) + 4, column=0, sticky='sew')
        
        ttk.Label(legend_frame, text="범례:", style='Subtle.TLabel').pack(anchor='w')
        ttk.Label(legend_frame, text="🟩 양품", style='Sidebar.TLabel', foreground=self.COLOR_SUCCESS).pack(anchor='w')
        ttk.Label(legend_frame, text="🟥 불량", style='Sidebar.TLabel', foreground=self.COLOR_DEFECT).pack(anchor='w')
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
        card = ttk.Frame(parent, style='Card.TFrame', padding=20); label = ttk.Label(card, text=label_text, style='Subtle.TLabel'); label.pack(); value_label = ttk.Label(card, text="-", style='Value.TLabel'); value_label.pack()
        return {'frame': card, 'label': label, 'value': value_label}

    def toggle_inspection_mode(self):
        if self.current_mode == "standard":
            self.current_mode = "defective_only"
            self._log_event('MODE_CHANGE_TO_DEFECTIVE')
        else:
            self.current_mode = "standard"
            self._log_event('MODE_CHANGE_TO_STANDARD')
        self._apply_mode_ui()

    def _apply_mode_ui(self):
        self.apply_scaling() 
        
        if not hasattr(self, 'good_count_label'):
            return

        self.center_pane.config(style='TFrame')
        
        self.good_count_label.pack_forget()
        self.main_count_label.pack_forget()
        self.defect_count_label.pack_forget()
        
        if self.current_mode == "standard":
            self.mode_switch_button.config(text="불량 전용 모드")
            self.main_progress_bar.grid(row=2, column=0, sticky='ew', pady=(5, 20), padx=20)
            
            self.good_count_label.pack(side=tk.LEFT, padx=20)
            self.main_count_label.pack(side=tk.LEFT, padx=20)
            self.defect_count_label.pack(side=tk.LEFT, padx=20)
            
            self.on_pedal_release_ui_feedback()
        else: 
            bg_color = self.COLOR_DEFECT_BG
            self.mode_switch_button.config(text="일반 모드로 복귀")
            
            self.main_progress_bar.grid_forget()
            
            self.defect_count_label.pack(side=tk.LEFT, padx=20)
            
            if hasattr(self, 'defect_mode_indicator'):
                self.defect_mode_indicator.config(text="", background=bg_color)
            if hasattr(self, 'scan_entry'):
                self.scan_entry.config(highlightcolor=self.COLOR_DEFECT)

        self._update_current_item_label()
        self._schedule_focus_return()

    def _schedule_focus_return(self, delay_ms: int = 100):
        if self.focus_return_job: self.root.after_cancel(self.focus_return_job)
        self.focus_return_job = self.root.after(delay_ms, self._return_focus_to_scan_entry)

    def _return_focus_to_scan_entry(self):
        try:
            if hasattr(self, 'scan_entry') and self.scan_entry.winfo_exists(): self.scan_entry.focus_set()
            self.focus_return_job = None
        except Exception: pass

    def _update_current_item_label(self):
        if not (hasattr(self, 'current_item_label') and self.current_item_label.winfo_exists()): return
        
        text = ""
        color = self.COLOR_TEXT
        
        if self.current_session.master_label_code:
            name_part = f"현재 품목: {self.current_session.item_name} ({self.current_session.item_code})"
            if self.current_mode == "standard":
                instruction = f"\n제품을 스캔하세요. (불량인 경우, {self.DEFECT_PEDAL_KEY_NAME} 페달을 밟은 상태에서 스캔)"
                text = f"{name_part}{instruction}"
                color = self.COLOR_TEXT
            else: 
                instruction = "\n\n⚠️ 불량 전용 모드: 모든 스캔은 불량 처리됩니다."
                text = f"{name_part}{instruction}"
                color = self.COLOR_DEFECT
        else:
            text = "현품표 라벨을 스캔하여 검사를 시작하세요."
            color = self.COLOR_TEXT_SUBTLE
            if self.current_mode == "defective_only":
                 text += "\n\n⚠️ 불량 전용 모드"
                 color = self.COLOR_DEFECT
            
        self.current_item_label['text'] = text
        self.current_item_label['foreground'] = color

    def process_scan(self, event=None):
        current_time = time.monotonic()
        if current_time - self.last_scan_time < self.scan_delay_sec.get():
            self.scan_entry.delete(0, tk.END)
            return
        self.last_scan_time = current_time

        barcode = self.scan_entry.get().strip()
        self.scan_entry.delete(0, tk.END)
        if not barcode: return

        # [수정] keyboard.is_pressed로 F12 키의 현재 상태를 직접 확인
        is_defect_scan = keyboard.is_pressed(self.DEFECT_PEDAL_KEY_NAME.lower())

        if barcode == "TEST_GENERATE_LOG":
            if not self.current_session.master_label_code:
                self.show_fullscreen_warning("테스트 스캔 오류", "먼저 현품표를 스캔하여 작업을 시작해야 합니다.", self.COLOR_DEFECT)
                return

            self.show_status_message("테스트 QR이 제품으로 처리되었습니다.", self.COLOR_PRIMARY)
            
            status = 'Defective' if self.current_mode == "defective_only" or is_defect_scan else 'Good'
            self.record_inspection_result(barcode, status)
            return 
        
        self._update_last_activity_time()

        if not self.current_session.master_label_code:
            if len(barcode) != self.ITEM_CODE_LENGTH:
                self.show_fullscreen_warning("작업 시작 오류", f"검사를 시작하려면 먼저 {self.ITEM_CODE_LENGTH}자리 현품표 라벨을 스캔해야 합니다.", self.COLOR_DEFECT); return
            matched_item = next((item for item in self.items_data if item['Item Code'] == barcode), None)
            if not matched_item:
                self.show_fullscreen_warning("품목 없음", f"현품표 코드 '{barcode}'에 해당하는 품목 정보를 찾을 수 없습니다.", self.COLOR_DEFECT); return
            
            self.current_session.master_label_code = barcode; self.current_session.item_code = barcode
            self.current_session.item_name = matched_item.get('Item Name', ''); self.current_session.item_spec = matched_item.get('Spec', '')
            self._update_current_item_label()
            self._log_event('MASTER_LABEL_SCANNED', detail={'code': barcode})
            self._start_stopwatch(); self._save_current_session_state()
            return

        if len(barcode) <= self.ITEM_CODE_LENGTH:
            self.show_fullscreen_warning("바코드 형식 오류", f"제품 바코드는 {self.ITEM_CODE_LENGTH}자리보다 길어야 합니다.", self.COLOR_DEFECT); return
        if self.current_session.item_code not in barcode:
            self.current_session.mismatch_error_count += 1; self.current_session.has_error_or_reset = True
            self.show_fullscreen_warning("품목 코드 불일치!", f"제품의 품목 코드가 일치하지 않습니다.\n[기준: {self.current_session.item_code}]", self.COLOR_DEFECT)
            self._log_event('SCAN_FAIL_MISMATCH', detail={'expected': self.current_session.item_code, 'scanned': barcode}); return
        if barcode in self.current_session.scanned_barcodes:
            self.current_session.mismatch_error_count += 1; self.current_session.has_error_or_reset = True
            self.show_fullscreen_warning("바코드 중복!", f"제품 바코드 '{barcode}'는 이미 검사되었습니다.", self.COLOR_DEFECT)
            self._log_event('SCAN_FAIL_DUPLICATE', detail={'barcode': barcode}); return

        if self.current_mode == "defective_only":
            self.record_inspection_result(barcode, 'Defective')
        else:
            if is_defect_scan: # [수정] 직접 확인한 키 상태로 분기
                self.record_inspection_result(barcode, 'Defective')
            else:
                self.record_inspection_result(barcode, 'Good')
    
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
        
        if len(self.current_session.good_items) == self.TRAY_SIZE:
            self.complete_session()
            
    def _redraw_scan_trees(self):
        if not hasattr(self, 'good_items_tree') or not self.good_items_tree.winfo_exists():
            return

        for i in self.good_items_tree.get_children():
            self.good_items_tree.delete(i)
        for i in self.defective_items_tree.get_children():
            self.defective_items_tree.delete(i)

        for idx, item in enumerate(self.current_session.good_items):
            self.good_items_tree.insert('', 0, values=(idx + 1, item['barcode']))
        
        for idx, item in enumerate(self.current_session.defective_items):
            self.defective_items_tree.insert('', 0, values=(idx + 1, item['barcode']))

    def complete_session(self):
        self._stop_stopwatch(); self._stop_idle_checker(); self.undo_button['state'] = tk.DISABLED
        is_test = self.current_session.is_test_tray; has_error = self.current_session.has_error_or_reset; is_partial = self.current_session.is_partial_submission; is_restored = self.current_session.is_restored_session
        if not is_test:
            self._log_event('SESSION_COMPLETE', detail={
                'master_label_code': self.current_session.master_label_code, 'item_code': self.current_session.item_code, 'item_name': self.current_session.item_name,
                'total_scan_count': len(self.current_session.scanned_barcodes), 'good_count': len(self.current_session.good_items), 'defective_count': len(self.current_session.defective_items),
                'good_items': self.current_session.good_items, 'defective_items': self.current_session.defective_items,
                'work_time_sec': self.current_session.stopwatch_seconds, 'error_count': self.current_session.mismatch_error_count,
                'total_idle_seconds': self.current_session.total_idle_seconds, 'has_error_or_reset': has_error, 'is_partial_submission': is_partial, 'is_restored_session': is_restored,
                'start_time': self.current_session.start_time.isoformat() if self.current_session.start_time else None, 'end_time': datetime.datetime.now().isoformat()})
        item_code = self.current_session.item_code
        if item_code not in self.work_summary: self.work_summary[item_code] = {'name': self.current_session.item_name, 'spec': self.current_session.item_spec, 'count': 0, 'test_count': 0}
        if is_test: self.work_summary[item_code]['test_count'] += 1; self.show_status_message("테스트 세션 완료!", self.COLOR_SUCCESS)
        else:
            self.work_summary[item_code]['count'] += 1
            if not is_partial: self.total_tray_count += 1
            if not has_error and not is_partial and not is_restored and self.current_session.stopwatch_seconds > 0: self.completed_tray_times.append(self.current_session.stopwatch_seconds)
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
        if self.info_cards.get('stopwatch'): self.info_cards['stopwatch']['value']['text'] = "00:00"
        self._set_idle_style(is_idle=True)
        self._update_center_display()
        if self.current_mode == "standard":
            self.on_pedal_release_ui_feedback()

    def undo_last_inspection(self):
        self._update_last_activity_time()
        if not self.current_session.scanned_barcodes: return
        last_barcode = self.current_session.scanned_barcodes.pop()
        
        removed_from_good = False
        for i, item in enumerate(self.current_session.good_items):
            if item['barcode'] == last_barcode:
                self.current_session.good_items.pop(i)
                removed_from_good = True
                break
        if not removed_from_good:
            for i, item in enumerate(self.current_session.defective_items):
                if item['barcode'] == last_barcode:
                    self.current_session.defective_items.pop(i)
                    break
        
        self._redraw_scan_trees()
        self._update_center_display()
        self._log_event('INSPECTION_UNDO', detail={'barcode': last_barcode})
        self.show_status_message(f"'{last_barcode}' 판정이 취소되었습니다.", self.COLOR_DEFECT)
        self._update_current_item_label()
        if not self.current_session.scanned_barcodes: self.undo_button['state'] = tk.DISABLED
        self._save_current_session_state()
        self._schedule_focus_return()
        
    def reset_current_work(self):
        self._update_last_activity_time()
        if self.current_session.master_label_code and messagebox.askyesno("확인", "현재 진행중인 검사를 초기화하시겠습니까?"):
            self._stop_stopwatch(); self._stop_idle_checker(); self.is_idle = False
            self._log_event('SESSION_RESET', detail={'scan_count': len(self.current_session.scanned_barcodes)})
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
            self.show_status_message("제출할 검사 내역이 없습니다.", self.COLOR_TEXT_SUBTLE); return
        
        good_count = len(self.current_session.good_items)
        defect_count = len(self.current_session.defective_items)
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
            self.summary_title_label.config(text=f"금일 작업 현황 (총 {self.total_tray_count} 파렛트)")

    def _update_summary_list(self):
        if not (hasattr(self, 'summary_tree') and self.summary_tree.winfo_exists()): return
        for i in self.summary_tree.get_children(): self.summary_tree.delete(i)
        for item_code, data in sorted(self.work_summary.items()):
            count_display = f"{data.get('count', 0)} 파렛트" + (f" (테스트: {data['test_count']})" if data.get('test_count', 0) > 0 else "")
            self.summary_tree.insert('', 'end', values=(f"{data.get('name', '')}", item_code, count_display))

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
        
        good_count = len(self.current_session.good_items)
        defect_count = len(self.current_session.defective_items)
        
        self.good_count_label['text'] = f"양품: {good_count}"
        self.defect_count_label['text'] = f"불량: {defect_count}"
        
        self.main_count_label['text'] = f"{good_count} / {self.TRAY_SIZE}"
        self.main_progress_bar['value'] = good_count

    def _update_clock(self):
        if not self.root.winfo_exists(): return
        now = datetime.datetime.now()
        if hasattr(self, 'date_label') and self.date_label.winfo_exists(): self.date_label['text'] = now.strftime('%Y-%m-%d')
        if hasattr(self, 'clock_label') and self.clock_label.winfo_exists(): self.clock_label['text'] = now.strftime('%H:%M:%S')
        self.clock_job = self.root.after(1000, self._update_clock)
        
    def _start_stopwatch(self, resume=False):
        if not resume: self.current_session.stopwatch_seconds = 0; self.current_session.start_time = datetime.datetime.now()
        self._update_last_activity_time()
        if self.stopwatch_job: self.root.after_cancel(self.stopwatch_job)
        self._update_stopwatch()

    def _stop_stopwatch(self):
        if self.stopwatch_job: self.root.after_cancel(self.stopwatch_job); self.stopwatch_job = None
        
    def _update_stopwatch(self):
        if not self.root.winfo_exists() or self.is_idle: return
        mins, secs = divmod(int(self.current_session.stopwatch_seconds), 60)
        if self.info_cards.get('stopwatch') and self.info_cards['stopwatch']['value'].winfo_exists(): self.info_cards['stopwatch']['value']['text'] = f"{mins:02d}:{secs:02d}"
        self.current_session.stopwatch_seconds += 1; self.stopwatch_job = self.root.after(1000, self._update_stopwatch)

    def _start_idle_checker(self):
        self._update_last_activity_time()
        if self.idle_check_job: self.root.after_cancel(self.idle_check_job)
        self.idle_check_job = self.root.after(1000, self._check_for_idle)

    def _stop_idle_checker(self):
        if self.idle_check_job: self.root.after_cancel(self.idle_check_job); self.idle_check_job = None

    def _update_last_activity_time(self):
        self.last_activity_time = datetime.datetime.now()
        if self.is_idle: self._wakeup_from_idle()

    def _check_for_idle(self):
        if not self.root.winfo_exists() or self.is_idle or not self.current_session.master_label_code or not self.last_activity_time:
            self.idle_check_job = self.root.after(1000, self._check_for_idle); return
        if (datetime.datetime.now() - self.last_activity_time).total_seconds() > self.IDLE_THRESHOLD_SEC:
            self.is_idle = True; self._set_idle_style(is_idle=True); self._log_event('IDLE_START')
        else: self.idle_check_job = self.root.after(1000, self._check_for_idle)
            
    def _wakeup_from_idle(self):
        if not self.is_idle: return
        self.is_idle = False
        if self.last_activity_time:
            idle_duration = (datetime.datetime.now() - self.last_activity_time).total_seconds()
            self.current_session.total_idle_seconds += idle_duration; self._log_event('IDLE_END', detail={'duration_sec': f"{idle_duration:.2f}"})
        self._set_idle_style(is_idle=False); self._start_idle_checker(); self._update_stopwatch(); self.show_status_message("작업 재개.", self.COLOR_SUCCESS)

    def _set_idle_style(self, is_idle: bool):
        if not (hasattr(self, 'info_cards') and self.info_cards): return
        style_prefix = 'Idle.' if is_idle else ''
        card_style = f'{style_prefix}TFrame' if style_prefix else 'Card.TFrame'
        for key in ['status', 'stopwatch', 'avg_time']:
            if self.info_cards.get(key):
                card = self.info_cards[key]; card['frame']['style'] = card_style; card['label']['style'] = f'{style_prefix}Subtle.TLabel'; card['value']['style'] = f'{style_prefix}Value.TLabel'
        status_widget = self.info_cards['status']['value']
        if is_idle:
            status_widget['text'] = "대기 중"; status_widget['foreground'] = self.COLOR_TEXT
            self.show_status_message("휴식 상태입니다. 스캔하여 작업을 재개하세요.", self.COLOR_IDLE, duration=10000)
        else: status_widget['text'] = "작업 중"; status_widget['foreground'] = self.COLOR_SUCCESS
            
    def _on_column_resize(self, event: tk.Event, tree: ttk.Treeview, name: str):
        if tree.identify_region(event.x, event.y) == "separator":
            self.root.after(10, self._save_column_widths, tree, name); self._schedule_focus_return()

    def _save_column_widths(self, tree: ttk.Treeview, name: str):
        for col_id in tree["columns"]: self.column_widths[f'{name}_{col_id}'] = tree.column(col_id, "width")
        self.save_settings()

    def _start_warning_beep(self):
        if self.error_sound: self.error_sound.play(loops=-1)
    def _stop_warning_beep(self):
        if self.error_sound: self.error_sound.stop()

    def show_fullscreen_warning(self, title: str, message: str, color: str):
        self._start_warning_beep()
        popup = tk.Toplevel(self.root); popup.title(title); popup.attributes('-fullscreen', True)
        popup.configure(bg=color); popup.grab_set()
        def on_popup_close(): self._stop_warning_beep(); popup.destroy(); self._schedule_focus_return()
        title_font = (self.DEFAULT_FONT, int(60*self.scale_factor), 'bold'); msg_font = (self.DEFAULT_FONT, int(30*self.scale_factor), 'bold')
        tk.Label(popup, text=title, font=title_font, fg='white', bg=color).pack(pady=(100, 50), expand=True)
        tk.Label(popup, text=message, font=msg_font, fg='white', bg=color, wraplength=self.root.winfo_screenwidth() - 100, justify=tk.CENTER).pack(pady=20, expand=True)
        btn = tk.Button(popup, text="확인 (클릭)", font=msg_font, command=on_popup_close, bg='white', fg=color, relief='flat', padx=20, pady=10)
        btn.pack(pady=50, expand=True); btn.focus_set()

    def _cancel_all_jobs(self):
        for job_attr in ['clock_job', 'status_message_job', 'stopwatch_job', 'idle_check_job', 'focus_return_job']:
            job_id = getattr(self, job_attr, None)
            if job_id: self.root.after_cancel(job_id); setattr(self, job_attr, None)
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
            self.save_settings(); self._cancel_all_jobs(); self.log_queue.put(None)
            if self.log_thread.is_alive(): self.log_thread.join(timeout=1.0)
            pygame.quit(); self.root.destroy()
            
    def _event_log_writer(self):
        while True:
            try:
                log_entry = self.log_queue.get(timeout=1.0)
                if log_entry is None: break
                if not self.log_file_path:
                    time.sleep(0.1)
                    self.log_queue.put(log_entry)
                    continue
                
                file_exists = os.path.exists(self.log_file_path) and os.stat(self.log_file_path).st_size > 0
                with open(self.log_file_path, 'a', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(['timestamp', 'worker_name', 'event', 'details'])
                    
                    writer.writerow([log_entry['timestamp'], log_entry['worker_name'], log_entry['event'], log_entry['details']])
            except queue.Empty:
                continue
            except Exception as e:
                print(f"로그 파일 쓰기 오류: {e}")

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
        self.log_queue.put(log_entry)

    def show_status_message(self, message: str, color: Optional[str] = None, duration: int = 4000):
        if self.status_message_job: self.root.after_cancel(self.status_message_job)
        self.status_label['text'] = message; self.status_label['fg'] = color or self.COLOR_TEXT
        self.status_message_job = self.root.after(duration, self._reset_status_message)
    
    def _reset_status_message(self):
        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            self.status_label['text'] = "준비"; self.status_label['fg'] = self.COLOR_TEXT
            
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = InspectionProgram()
    check_and_apply_updates(app) 
    app.run()