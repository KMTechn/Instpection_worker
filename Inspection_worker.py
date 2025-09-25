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
from dataclasses import dataclass, field

# 분리된 모듈들 import
from core.models import InspectionSession, RemnantCreationSession, DefectiveMergeSession
from utils.file_handler import resource_path, find_file_in_subdirs, ensure_directory_exists, get_safe_filename
from utils.logger import EventLogger
from ui.base_ui import UIUtils, StyleManager
from ui.components import ScannerInputComponent, ProgressDisplayComponent, DataDisplayComponent
from utils.exceptions import InspectionError, ConfigurationError, FileHandlingError, BarcodeError, SessionError, ValidationError, NetworkError, UpdateError
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


# 라벨 이미지 생성을 위한 라이브러리 import
# 실행 전 "pip install qrcode pillow" 명령어 실행 필요
try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    import qrcode
except ImportError:
    messagebox.showerror("라이브러리 오류", "'qrcode'와 'Pillow' 라이브러리가 필요합니다.\n\n터미널에서 'pip install qrcode pillow' 명령어를 실행해주세요.")
    sys.exit()

# #####################################################################
# # 설정 관리 클래스
# #####################################################################

class ConfigManager:
    """애플리케이션 설정을 관리하는 클래스"""

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """설정 파일을 로드합니다."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, self.config_file)

            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # 기본 설정 생성
                return self._create_default_config()
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"설정 파일 로드 오류: {e}")
            return self._create_default_config()

    def _create_default_config(self) -> Dict[str, Any]:
        """기본 설정을 생성합니다."""
        default_config = {
            "app": {
                "name": "Inspection Worker",
                "version": "v2.0.8",
                "description": "품질 검사 시스템"
            },
            "github": {
                "repo_owner": "KMTechn",
                "repo_name": "Inspection_worker"
            },
            "inspection": {
                "tray_size": 60,
                "idle_threshold_sec": 420,
                "item_code_length": 13,
                "default_product_code": "",
                "sound_enabled": True
            },
            "ui": {
                "window_title": "KMTech 검사 시스템",
                "window_geometry": "1400x800",
                "theme": "default"
            },
            "logging": {
                "enabled": True,
                "log_file": "inspection_log.csv",
                "session_file": "session_data.json",
                "max_log_size": 1048576
            },
            "network": {
                "update_check_timeout": 5,
                "download_timeout": 120,
                "auto_update_check": True
            }
        }
        self.save_config(default_config)
        return default_config

    def get(self, key_path: str, default=None):
        """점 표기법으로 설정값을 가져옵니다. 예: 'app.version'"""
        keys = key_path.split('.')
        value = self.config

        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key_path: str, value):
        """점 표기법으로 설정값을 설정합니다."""
        keys = key_path.split('.')
        config = self.config

        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]

        config[keys[-1]] = value

    def save_config(self, config_data=None):
        """설정을 파일로 저장합니다."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, self.config_file)

            data = config_data if config_data is not None else self.config

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"설정 파일 저장 오류: {e}")

# 전역 설정 매니저 인스턴스
config = ConfigManager()

# #####################################################################
# # 자동 업데이트 기능
# #####################################################################

def check_for_updates(app_instance):
    """GitHub에서 최신 릴리스를 확인합니다."""
    try:
        repo_owner = config.get('github.repo_owner')
        repo_name = config.get('github.repo_name')
        current_version = config.get('app.version')
        timeout = config.get('network.update_check_timeout', 5)

        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"
        response = requests.get(api_url, timeout=timeout)
        response.raise_for_status()
        latest_release_data = response.json()
        latest_version = latest_release_data['tag_name']

        if latest_version.strip().lower() != current_version.strip().lower():
            app_instance._log_event('UPDATE_CHECK_FOUND', detail={'current': current_version, 'latest': latest_version})
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
        
        download_timeout = config.get('network.download_timeout', 120)
        response = requests.get(url, stream=True, timeout=download_timeout)
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
                
        # 보안: 경로 인젝션 방지를 위한 입력 검증
        import shlex

        # 경로 검증 및 이스케이프
        safe_executable = shlex.quote(os.path.basename(sys.executable))
        safe_new_path = shlex.quote(new_program_folder_path)
        safe_app_path = shlex.quote(application_path)
        safe_temp_folder = shlex.quote(temp_update_folder)
        safe_restart_path = shlex.quote(os.path.join(application_path, os.path.basename(sys.executable)))

        # 경로 유효성 검증
        if not os.path.exists(new_program_folder_path) or not os.path.exists(application_path):
            raise ValueError("Invalid update paths detected")

        # 템플릿 기반 안전한 배치 파일 생성
        batch_template = """@echo off
chcp 65001 > nul
echo.
echo ==========================================================
echo  프로그램을 업데이트합니다. 이 창을 닫지 마세요.
echo ==========================================================
echo.
echo 잠시 후 프로그램이 자동으로 종료됩니다...
timeout /t 3 /nobreak > nul
taskkill /F /IM {executable} > nul
echo.
echo 기존 파일을 백업하고 새 파일로 교체합니다...
xcopy {source_path} {dest_path} /E /H /C /I /Y > nul
echo.
echo 임시 업데이트 파일을 삭제합니다...
rmdir /s /q {temp_path}
echo.
echo ========================================
echo  업데이트 완료!
echo ========================================
echo.
echo 3초 후에 프로그램을 다시 시작합니다.
timeout /t 3 /nobreak > nul
start "" {restart_path}
del "%~f0"
"""

        with open(updater_script_path, "w", encoding='utf-8') as bat_file:
            bat_file.write(batch_template.format(
                executable=safe_executable,
                source_path=safe_new_path,
                dest_path=safe_app_path,
                temp_path=safe_temp_folder,
                restart_path=safe_restart_path
            ))
        
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

# #####################################################################
# # 데이터 클래스 및 유틸리티
# #####################################################################

# #####################################################################
# # 메인 어플리케이션
# #####################################################################

class InspectionProgram:
    """품질 검사 작업을 위한 메인 GUI 어플리케이션 클래스입니다."""
    DEFAULT_FONT = 'Malgun Gothic'
    SETTINGS_DIR = 'config'
    SETTINGS_FILE = 'inspection_settings.json'
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
    COLOR_SPARE_BG = "#FDEBD0"
    COLOR_SPARE = "#F39C12"

    def __init__(self):
        self.root = tk.Tk()
        # 설정에서 앱 제목 동적 생성
        app_title = f"{config.get('ui.window_title', '품질 검사 시스템')} ({config.get('app.version', 'v2.0.8')})"
        self.root.title(app_title)
        self.root.state('zoomed')
        self.root.configure(bg=self.COLOR_BG)
        
        self.current_mode = "standard" 
        
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
        self.current_remnant_session = RemnantCreationSession()

        # 불량 처리 모드 관련 변수들
        self.defect_merge_log_file_path: Optional[str] = None
        self.current_defective_merge_session = DefectiveMergeSession()
        self.available_defects: Dict[str, Dict[str, Any]] = {}

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
        
        self.is_excluding_item = False
        self.exclusion_context = {}

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
        

        # [수정] 현품표 교체 관련 상태 변수 수정
        self.master_label_replace_state: Optional[str] = None
        self.replacement_context: Dict[str, Any] = {}

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
        elif self.current_mode == "remnant":
            bg_color = self.COLOR_SPARE_BG
        
        highlight_color = self.COLOR_PRIMARY
        if self.current_mode == "rework": 
            highlight_color = self.COLOR_REWORK
        elif self.current_mode == "remnant":
            highlight_color = self.COLOR_SPARE

        if hasattr(self, 'defect_mode_indicator'):
            self.defect_mode_indicator.config(text="", background=bg_color)
        if hasattr(self, 'scan_entry'):
            self.scan_entry.config(highlightcolor=highlight_color)
    
    def _setup_paths(self):
        self.save_folder = "C:\\Sync"

        # 데이터 폴더
        self.remnants_folder = os.path.join(self.save_folder, "spare")
        self.defects_data_folder = os.path.join(self.save_folder, "defects_merged")

        # 라벨 폴더
        self.labels_folder = os.path.join(self.save_folder, "labels")
        self.remnant_labels_folder = os.path.join(self.labels_folder, "remnant_labels")
        self.defective_labels_folder = os.path.join(self.labels_folder, "defective_labels")

        # 기본 폴더 생성
        os.makedirs(self.save_folder, exist_ok=True)
        os.makedirs(self.remnants_folder, exist_ok=True)
        os.makedirs(self.defects_data_folder, exist_ok=True)
        os.makedirs(self.labels_folder, exist_ok=True)
        os.makedirs(self.remnant_labels_folder, exist_ok=True)
        os.makedirs(self.defective_labels_folder, exist_ok=True)

    def _get_daily_folder_path(self, base_path: str) -> str:
        """주어진 기본 경로 하위에 오늘 날짜(YYYY-MM-DD) 폴더를 만들고 경로를 반환합니다."""
        today_str = datetime.date.today().strftime('%Y-%m-%d')
        path = os.path.join(base_path, today_str)
        os.makedirs(path, exist_ok=True)
        return path

    def _find_file_in_subdirs(self, root_folder: str, filename: str) -> Optional[str]:
        """하위 폴더를 재귀적으로 탐색하여 파일을 찾고 전체 경로를 반환합니다."""
        for dirpath, _, filenames in os.walk(root_folder):
            if filename in filenames:
                return os.path.join(dirpath, filename)
        return None

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
        if self.current_mode == "rework":
            bg_color = self.COLOR_REWORK_BG
        elif self.current_mode == "remnant":
            bg_color = self.COLOR_SPARE_BG

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

        app_title = f"{config.get('ui.window_title', '품질 검사 시스템')} ({config.get('app.version', 'v2.0.8')})"
        ttk.Label(center_frame, text=app_title, style='Title.TLabel').pack(pady=(20, 60))
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

        self.defect_merge_log_file_path = os.path.join(self.save_folder, f"불량처리로그_{sanitized_name}_{today.strftime('%Y%m%d')}.csv")
        if not os.path.exists(self.defect_merge_log_file_path):
                self._log_event('DEFECT_MERGE_LOG_FILE_CREATED', detail={'path': self.defect_merge_log_file_path})

        # 모든 로그를 동일한 위치에 저장 (테스트와 실제 구분 없음)

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
                        if row.get('worker') != self.worker_name:
                            continue
                        
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
                                                 'defective_ea_count': 0}
            
            defective_count_in_session = len(session.get('defective_product_barcodes', []))
            self.work_summary[item_code]['defective_ea_count'] += defective_count_in_session

            self.work_summary[item_code]['pallet_count'] += 1
            
            if not session.get('is_partial', False):
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
        
        self.good_summary_tree.column('item_name_spec', anchor='w')
        self.good_summary_tree.column('item_code', anchor='center')
        self.good_summary_tree.column('count', anchor='center')
        
        self.good_summary_tree.grid(row=0, column=0, sticky='nsew')
        good_scrollbar = ttk.Scrollbar(good_tree_frame, orient='vertical', command=self.good_summary_tree.yview)
        self.good_summary_tree['yscrollcommand'] = good_scrollbar.set
        good_scrollbar.grid(row=0, column=1, sticky='ns')

        self.good_summary_tree.bind('<Configure>', lambda e, t=self.good_summary_tree: self._adjust_treeview_columns(t))
        
        ttk.Label(summary_container, text="불량 현황", style='Subtle.TLabel', font=(self.DEFAULT_FONT, int(13 * self.scale_factor), 'bold')).grid(row=2, column=0, sticky='w', pady=(10, 5))
        defect_tree_frame = ttk.Frame(summary_container, style='Sidebar.TFrame')
        defect_tree_frame.grid(row=3, column=0, sticky='nsew')
        defect_tree_frame.grid_columnconfigure(0, weight=1)
        defect_tree_frame.grid_rowconfigure(0, weight=1)

        self.defect_summary_tree = ttk.Treeview(defect_tree_frame, columns=cols, show='headings', style='Treeview')
        self.defect_summary_tree.heading('item_name_spec', text='품목명')
        self.defect_summary_tree.heading('item_code', text='품목코드')
        self.defect_summary_tree.heading('count', text='불량 수량 (개)')

        self.defect_summary_tree.column('item_name_spec', anchor='w')
        self.defect_summary_tree.column('item_code', anchor='center')
        self.defect_summary_tree.column('count', anchor='center')

        self.defect_summary_tree.grid(row=0, column=0, sticky='nsew')
        defect_scrollbar = ttk.Scrollbar(defect_tree_frame, orient='vertical', command=self.defect_summary_tree.yview)
        self.defect_summary_tree['yscrollcommand'] = defect_scrollbar.set
        defect_scrollbar.grid(row=0, column=1, sticky='ns')

        self.defect_summary_tree.bind('<Configure>', lambda e, t=self.defect_summary_tree: self._adjust_treeview_columns(t))
        
        self.good_summary_tree.bind("<Double-1>", self._on_summary_double_click)
        self.defect_summary_tree.bind("<Double-1>", self._on_summary_double_click)

    def _adjust_treeview_columns(self, treeview: ttk.Treeview):
        """Treeview의 컬럼 너비를 사용 가능한 공간에 맞춰 균등하게 조정합니다."""
        cols = treeview['columns']
        if not cols:
            return
        
        width = treeview.winfo_width()
        if width > 30:
            width -= 20 
        
        col_width = width // len(cols)
        
        for col in cols:
            treeview.column(col, width=col_width, stretch=tk.NO, anchor='center')
        
        if 'item_name_spec' in cols:
            treeview.column('item_name_spec', anchor='w')

    def _create_center_content(self, parent_frame):
        parent_frame.grid_columnconfigure(0, weight=1)
        
        mode_frame = ttk.Frame(parent_frame, style='TFrame')
        mode_frame.grid(row=0, column=0, sticky='ne', pady=(5, 10), padx=5)

        self.defective_mode_button = ttk.Button(mode_frame, text="불량 처리 모드", command=self.toggle_defective_mode, style='Secondary.TButton')
        self.defective_mode_button.pack(side=tk.RIGHT, padx=(5,0))
        self.remnant_mode_button = ttk.Button(mode_frame, text="잔량 모드", command=self.toggle_remnant_mode, style='Secondary.TButton')
        self.remnant_mode_button.pack(side=tk.RIGHT, padx=(5,0))
        self.rework_mode_button = ttk.Button(mode_frame, text="리워크 모드", command=self.toggle_rework_mode, style='Secondary.TButton')
        self.rework_mode_button.pack(side=tk.RIGHT, padx=(5,0))

        self.current_item_label = ttk.Label(parent_frame, text="", style='ItemInfo.TLabel', justify='center', anchor='center')
        self.current_item_label.grid(row=1, column=0, sticky='ew', pady=(0, 20))
        
        view_container = ttk.Frame(parent_frame, style='TFrame')
        view_container.grid(row=2, column=0, sticky='nsew')
        parent_frame.grid_rowconfigure(2, weight=1)
        view_container.grid_columnconfigure(0, weight=1)
        view_container.grid_rowconfigure(0, weight=1)

        self._create_inspection_view(view_container)
        self._create_rework_view(view_container)
        self._create_remnant_view(view_container)
        self._create_defective_view(view_container)

        self.scan_entry = self.scan_entry_inspection
        
        self.root.after(100, self._apply_treeview_styles)

    def _create_inspection_view(self, container):
        self.inspection_view_frame = ttk.Frame(container, style='TFrame')
        self.inspection_view_frame.grid(row=0, column=0, sticky='nsew')
        self.inspection_view_frame.grid_columnconfigure(0, weight=1)
        self.inspection_view_frame.grid_rowconfigure(4, weight=1)

        tray_size = config.get('inspection.tray_size', 60)
        self.main_progress_bar = ttk.Progressbar(self.inspection_view_frame, orient='horizontal', mode='determinate', maximum=tray_size, style='Main.Horizontal.TProgressbar')
        self.main_progress_bar.grid(row=0, column=0, sticky='ew', pady=(5, 20), padx=20)
        
        self.counter_frame = ttk.Frame(self.inspection_view_frame, style='TFrame')
        self.counter_frame.grid(row=1, column=0, pady=(0, 20))
        
        self.good_count_label = ttk.Label(self.counter_frame, text="양품: 0", style='TLabel', foreground=self.COLOR_SUCCESS, font=(self.DEFAULT_FONT, int(14 * self.scale_factor), 'bold'))
        tray_size = config.get('inspection.tray_size', 60)
        self.main_count_label = ttk.Label(self.counter_frame, text=f"0 / {tray_size}", style='MainCounter.TLabel', anchor='center')
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
        
        self.replace_master_label_button = ttk.Button(self.button_frame, text="🔄 완료 현품표 교체", command=self.initiate_master_label_replacement)
        self.replace_master_label_button.pack(side=tk.LEFT, padx=10)

        self.submit_tray_button = ttk.Button(self.button_frame, text="✅ 현재 트레이 제출", command=self.submit_current_tray)
        self.submit_tray_button.pack(side=tk.LEFT, padx=10)

    def _create_rework_view(self, container):
        self.rework_view_frame = ttk.Frame(container, style='TFrame')
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
        rework_list_container.grid_rowconfigure(1, weight=1)

        ttk.Label(rework_list_container, text="금일 리워크 완료 목록", font=(self.DEFAULT_FONT, int(12*self.scale_factor), 'bold'), foreground=self.COLOR_SUCCESS).grid(row=0, column=0)
        
        reworked_frame = ttk.Frame(rework_list_container)
        reworked_frame.grid(row=1, column=0, sticky='nsew', padx=(5, 0))
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

    def _create_remnant_view(self, container):
        self.remnant_view_frame = ttk.Frame(container, style='TFrame')
        self.remnant_view_frame.grid(row=0, column=0, sticky='nsew')
        self.remnant_view_frame.grid_columnconfigure(0, weight=1)
        self.remnant_view_frame.grid_rowconfigure(1, weight=1)

        remnant_info_frame = ttk.Frame(self.remnant_view_frame, style='TFrame')
        remnant_info_frame.grid(row=0, column=0, sticky='ew', pady=10, padx=20)
        self.remnant_item_label = ttk.Label(remnant_info_frame, text="등록할 품목: (첫 제품 스캔 대기)", style='TLabel', foreground=self.COLOR_SPARE, font=(self.DEFAULT_FONT, int(14 * self.scale_factor), 'bold'))
        self.remnant_item_label.pack(side=tk.LEFT)
        self.remnant_count_label = ttk.Label(remnant_info_frame, text="수량: 0", style='TLabel', font=(self.DEFAULT_FONT, int(14 * self.scale_factor), 'bold'))
        self.remnant_count_label.pack(side=tk.RIGHT)

        remnant_list_frame = ttk.Frame(self.remnant_view_frame)
        remnant_list_frame.grid(row=1, column=0, sticky='nsew', padx=20, pady=5)
        remnant_list_frame.grid_rowconfigure(0, weight=1)
        remnant_list_frame.grid_columnconfigure(0, weight=1)
        
        cols = ('count', 'barcode')
        self.remnant_items_tree = ttk.Treeview(remnant_list_frame, columns=cols, show='headings')
        self.remnant_items_tree.heading('count', text='No.')
        self.remnant_items_tree.heading('barcode', text='잔량품 바코드')
        self.remnant_items_tree.column('count', width=50, anchor='center', stretch=tk.NO)
        self.remnant_items_tree.column('barcode', anchor='w', stretch=tk.YES)
        self.remnant_items_tree.grid(row=0, column=0, sticky='nsew')
        remnant_scroll = ttk.Scrollbar(remnant_list_frame, orient='vertical', command=self.remnant_items_tree.yview)
        remnant_scroll.grid(row=0, column=1, sticky='ns')
        self.remnant_items_tree['yscrollcommand'] = remnant_scroll.set

        remnant_bottom_frame = ttk.Frame(self.remnant_view_frame, style='TFrame')
        remnant_bottom_frame.grid(row=2, column=0, sticky='ew', pady=10, padx=20)
        remnant_bottom_frame.grid_columnconfigure(0, weight=1)
        
        self.scan_entry_remnant = tk.Entry(remnant_bottom_frame, justify='center', font=(self.DEFAULT_FONT, int(30 * self.scale_factor), 'bold'), bd=2, relief=tk.SOLID, highlightbackground=self.COLOR_BORDER, highlightcolor=self.COLOR_SPARE, highlightthickness=3)
        self.scan_entry_remnant.grid(row=0, column=0, sticky='ew', ipady=int(15 * self.scale_factor))
        self.scan_entry_remnant.bind('<Return>', self.process_scan)

        remnant_button_frame = ttk.Frame(self.remnant_view_frame, style='TFrame')
        remnant_button_frame.grid(row=3, column=0, pady=(20, 0))
        ttk.Button(remnant_button_frame, text="취소", command=self.cancel_remnant_creation).pack(side=tk.LEFT, padx=10)
        ttk.Button(remnant_button_frame, text="✅ 잔량표 생성", command=self._generate_remnant_label).pack(side=tk.LEFT, padx=10)

    def _create_defective_view(self, container):
        """불량 처리 모드의 UI를 생성합니다."""
        self.defective_view_frame = ttk.Frame(container, style='TFrame')
        self.defective_view_frame.grid(row=0, column=0, sticky='nsew')
        self.defective_view_frame.grid_columnconfigure(0, weight=1)
        self.defective_view_frame.grid_columnconfigure(1, weight=1)
        self.defective_view_frame.grid_rowconfigure(1, weight=1)

        # --- 왼쪽: 전체 불량 현황 ---
        left_frame = ttk.Frame(self.defective_view_frame, style='TFrame')
        left_frame.grid(row=0, column=0, rowspan=2, sticky='nsew', padx=(20, 10), pady=10)
        left_frame.grid_rowconfigure(1, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(left_frame, text="처리 가능 불량품 목록 (전체 작업자)", style='TLabel', font=(self.DEFAULT_FONT, int(12 * self.scale_factor), 'bold')).grid(row=0, column=0, sticky='w')

        cols = ('item_name', 'item_code', 'unprocessed', 'processed')
        self.available_defects_tree = ttk.Treeview(left_frame, columns=cols, show='headings')
        self.available_defects_tree.grid(row=1, column=0, sticky='nsew')
        self.available_defects_tree.heading('item_name', text='품목명')
        self.available_defects_tree.heading('item_code', text='품목코드')
        self.available_defects_tree.heading('unprocessed', text='미처리')
        self.available_defects_tree.heading('processed', text='처리완료')
        self.available_defects_tree.column('item_code', width=120, anchor='center')
        self.available_defects_tree.column('unprocessed', width=60, anchor='center')
        self.available_defects_tree.column('processed', width=60, anchor='center')

        self.available_defects_tree.tag_configure('processed_item', foreground='gray')

        # --- 오른쪽: 불량품 합치기 세션 ---
        right_frame = ttk.Frame(self.defective_view_frame, style='TFrame')
        right_frame.grid(row=0, column=1, rowspan=2, sticky='nsew', padx=(10, 20), pady=10)
        right_frame.grid_rowconfigure(2, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        session_ctrl_frame = ttk.Frame(right_frame, style='TFrame')
        session_ctrl_frame.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        session_ctrl_frame.grid_columnconfigure(1, weight=1)

        self.defect_session_label = ttk.Label(session_ctrl_frame, text="[불량 합치기] 버튼을 누르거나, 불량품/불량표를 스캔하세요.", style='TLabel')
        self.defect_session_label.grid(row=0, column=0, columnspan=2, sticky='w')

        ttk.Label(session_ctrl_frame, text="목표수량:", style='TLabel').grid(row=1, column=0, sticky='w', pady=5)
        self.defect_target_qty_spinbox = ttk.Spinbox(session_ctrl_frame, from_=1, to=200, increment=1, width=5)
        # 불량품 통합 모드 기본 목표 수량: 48개
        self.defect_target_qty_spinbox.set(48)
        self.defect_target_qty_spinbox.grid(row=1, column=1, sticky='w', pady=5)

        self.start_defect_merge_button = ttk.Button(session_ctrl_frame, text="불량 합치기", command=self.start_defective_merge_session)
        self.start_defect_merge_button.grid(row=2, column=0, pady=5, sticky='w')

        self.add_defect_button = ttk.Button(session_ctrl_frame, text="불량 입력하기", command=self.show_add_defect_popup)
        self.add_defect_button.grid(row=2, column=1, pady=5, padx=5, sticky='w')

        self.scan_entry_defective = tk.Entry(right_frame, justify='center', font=(self.DEFAULT_FONT, int(20 * self.scale_factor), 'bold'), bd=2, relief=tk.SOLID, highlightbackground=self.COLOR_BORDER, highlightcolor=self.COLOR_DEFECT, highlightthickness=3, state=tk.DISABLED)
        self.scan_entry_defective.grid(row=1, column=0, sticky='ew', ipady=int(10 * self.scale_factor))
        self.scan_entry_defective.bind('<Return>', self.process_scan)

        scanned_list_frame = ttk.Frame(right_frame, style='TFrame')
        scanned_list_frame.grid(row=2, column=0, sticky='nsew', pady=(10,0))
        scanned_list_frame.grid_rowconfigure(0, weight=1)
        scanned_list_frame.grid_columnconfigure(0, weight=1)

        self.scanned_defects_tree = ttk.Treeview(scanned_list_frame, columns=('no', 'barcode'), show='headings')
        self.scanned_defects_tree.grid(row=0, column=0, sticky='nsew')
        self.scanned_defects_tree.heading('no', text='No.')
        self.scanned_defects_tree.heading('barcode', text='스캔된 불량품 바코드')
        self.scanned_defects_tree.column('no', width=50, anchor='center')

        bottom_button_frame = ttk.Frame(right_frame, style='TFrame')
        bottom_button_frame.grid(row=3, column=0, sticky='e', pady=(10, 0))
        self.cancel_defect_merge_button = ttk.Button(bottom_button_frame, text="취소", command=self.cancel_defective_merge_session, state=tk.DISABLED)
        self.cancel_defect_merge_button.pack(side=tk.LEFT, padx=5)
        # 불량표 수동 생성 버튼 (2번째 생성 시기)
        self.generate_defect_label_button = ttk.Button(bottom_button_frame, text="불량표 생성", command=self.generate_defective_label, state=tk.DISABLED)
        self.generate_defect_label_button.pack(side=tk.LEFT, padx=5)

        self.available_defects_tree.bind('<<TreeviewSelect>>', self.on_available_defect_select)
        self.available_defects_tree.bind('<Double-1>', self.on_available_defect_double_click)

    def show_add_defect_popup(self):
        """불량품을 직접 입력받는 팝업 창을 표시합니다."""
        popup = tk.Toplevel(self.root)
        popup.title("불량품 직접 입력")
        popup.geometry("500x200")
        popup.transient(self.root)
        popup.grab_set()

        main_frame = ttk.Frame(popup, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="등록할 불량품의 바코드를 스캔(입력)하세요.", font=(self.DEFAULT_FONT, 12)).pack(pady=(0, 10))

        barcode_entry = ttk.Entry(main_frame, font=(self.DEFAULT_FONT, 14))
        barcode_entry.pack(fill=tk.X, ipady=5)
        barcode_entry.focus_set()

        def on_confirm():
            barcode = barcode_entry.get().strip()
            if not barcode:
                messagebox.showwarning("입력 오류", "바코드를 입력해주세요.", parent=popup)
                return

            self._record_manual_defect(barcode)
            popup.destroy()

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=(20, 0))

        confirm_button = ttk.Button(button_frame, text="등록", command=on_confirm)
        confirm_button.pack(side=tk.LEFT, padx=10)

        cancel_button = ttk.Button(button_frame, text="취소", command=popup.destroy)
        cancel_button.pack(side=tk.LEFT)

        barcode_entry.bind('<Return>', lambda e: on_confirm())

    def on_available_defect_select(self, event=None):
        pass

    def _record_manual_defect(self, barcode: str):
        """팝업에서 입력된 바코드를 불량품으로 기록합니다."""
        # 1. 바코드에서 품목 코드 추출
        detected_item_code = None
        for item in self.items_data:
            item_code = item.get('Item Code')
            if item_code and item_code in barcode:
                detected_item_code = item_code
                break

        if not detected_item_code:
            messagebox.showerror("오류", "바코드에서 유효한 품목 코드를 찾을 수 없습니다.")
            return

        # 2. 품목 정보 가져오기
        matched_item = next((item for item in self.items_data if item['Item Code'] == detected_item_code), None)
        item_name = matched_item.get('Item Name', '알 수 없음') if matched_item else '알 수 없음'

        # 3. 불량 이벤트 기록
        self._log_event('INSPECTION_DEFECTIVE', detail={
            'barcode': barcode,
            'item_code': detected_item_code,
            'item_name': item_name,
            'direct_scan': True,  # 수동 입력임을 표시
            'scan_time': datetime.datetime.now().isoformat()
        })

        # 4. UI 새로고침
        self.show_status_message(f"'{item_name}' 불량품이 등록되었습니다.", self.COLOR_SUCCESS)
        self.load_all_defective_items()

    def on_available_defect_double_click(self, event=None):
        """불량품 목록 더블클릭 시 관련 동작 메뉴 표시"""
        if not self.available_defects_tree.selection():
            return

        selection = self.available_defects_tree.selection()[0]
        item_values = self.available_defects_tree.item(selection, 'values')
        if len(item_values) < 4:
            return

        item_name, item_code, worker, count = item_values

        # 컨텍스트 메뉴 생성
        context_menu = tk.Menu(self.root, tearoff=0)

        # 불량 합치기 시작
        if not self.current_defective_merge_session.item_code:
            context_menu.add_command(
                label=f"🔗 '{item_name}' 불량 합치기 시작",
                command=lambda: self._start_defect_merge_from_menu(item_code)
            )

        # 불량품 세부 정보 보기
        context_menu.add_command(
            label=f"📋 '{item_name}' 불량품 세부 정보 보기",
            command=lambda: self._show_defect_details(item_code, worker)
        )

        # 불량표 즉시 생성 (기존 불량품으로)
        context_menu.add_command(
            label=f"🏷️ '{item_name}' 불량표 즉시 생성",
            command=lambda: self._generate_instant_defect_label(item_code, worker)
        )

        context_menu.add_separator()

        # 불량품 삭제 (관리자 기능)
        context_menu.add_command(
            label=f"🗑️ '{item_name}' 불량품 목록에서 제거",
            command=lambda: self._remove_defects_from_list(item_code, worker)
        )

        # 마우스 위치에 메뉴 표시
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def _start_defect_merge_from_menu(self, item_code):
        """메뉴에서 불량 합치기 시작"""
        defect_data = self.available_defects.get(item_code)
        if not defect_data or not defect_data.get('unprocessed_barcodes'):
            messagebox.showwarning("처리 불가", "해당 품목은 처리할 미처리 불량품이 없습니다.")
            return

        # 해당 품목을 선택하고 세션 시작
        for child in self.available_defects_tree.get_children():
            item_values = self.available_defects_tree.item(child, 'values')
            if len(item_values) > 1 and item_values[1] == item_code:
                self.available_defects_tree.selection_set(child)
                self.available_defects_tree.focus(child)
                break

        # 선택된 품목으로 세션 생성
        self.current_defective_merge_session = DefectiveMergeSession(
            item_code=item_code,
            item_name=defect_data.get('name', ''),
            item_spec=defect_data.get('spec', ''),
            target_quantity=int(self.defect_target_qty_spinbox.get())
        )
        # 이미 존재하는 미처리 불량품들을 세션에 바로 추가
        self.current_defective_merge_session.scanned_defects.extend(list(defect_data.get('unprocessed_barcodes', [])))

        self.scan_entry_defective.config(state=tk.NORMAL)
        self.cancel_defect_merge_button.config(state=tk.NORMAL)
        self.generate_defect_label_button.config(state=tk.NORMAL)
        self.start_defect_merge_button.config(state=tk.DISABLED)
        self._schedule_focus_return()
        self._update_defective_mode_ui()
        self.show_status_message(f"'{item_code}' 불량 합치기를 시작했습니다.", self.COLOR_SUCCESS)

    def _show_defect_details(self, item_code, worker):
        """불량품 세부 정보 표시"""
        defect_key = f"{item_code}_{worker}"
        defect_info = self.available_defects.get(defect_key, {})
        barcodes = defect_info.get('barcodes', set())

        # 팝업 창 생성
        popup = tk.Toplevel(self.root)
        popup.title(f"불량품 세부 정보 - {item_code}")
        popup.geometry("600x400")
        popup.transient(self.root)
        popup.grab_set()

        main_frame = ttk.Frame(popup, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 정보 표시
        info_frame = ttk.LabelFrame(main_frame, text="불량품 정보", padding=10)
        info_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(info_frame, text=f"품목코드: {item_code}", font=('맑은 고딕', 12, 'bold')).pack(anchor='w')
        ttk.Label(info_frame, text=f"작업자: {worker}", font=('맑은 고딕', 10)).pack(anchor='w')
        ttk.Label(info_frame, text=f"불량품 수량: {len(barcodes)}개", font=('맑은 고딕', 10)).pack(anchor='w')

        # 바코드 목록
        barcode_frame = ttk.LabelFrame(main_frame, text="불량품 바코드 목록", padding=10)
        barcode_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 바코드 리스트박스
        listbox_frame = ttk.Frame(barcode_frame)
        listbox_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(listbox_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        barcode_listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, font=('맑은 고딕', 9))
        barcode_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=barcode_listbox.yview)

        # 바코드 추가
        for barcode in sorted(barcodes):
            barcode_listbox.insert(tk.END, barcode)

        # 버튼 프레임
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)

        ttk.Button(button_frame, text="닫기", command=popup.destroy).pack(side=tk.RIGHT)

    def _generate_instant_defect_label(self, item_code, worker):
        """선택된 불량품으로 즉시 불량표 생성"""
        defect_key = f"{item_code}_{worker}"
        if not self.available_defects.get(defect_key):
            messagebox.showwarning("오류", "선택된 품목의 불량품이 없습니다.")
            return

        if messagebox.askyesno("불량표 즉시 생성",
                             f"'{item_code}' 품목의 모든 불량품({len(self.available_defects[defect_key]['barcodes'])}개)으로\n"
                             f"불량표를 즉시 생성하시겠습니까?"):

            # 임시 세션 생성
            from core.models import DefectiveMergeSession
            temp_session = DefectiveMergeSession()
            temp_session.item_code = item_code
            temp_session.scanned_defects = list(self.available_defects[defect_key]['barcodes'])

            # 품목 정보 조회
            matched_item = next((item for item in self.items_data if item.get('Item Code') == item_code), None)
            if matched_item:
                temp_session.item_name = matched_item.get('Item Name', item_code)
                temp_session.item_spec = matched_item.get('Specifications', '')
            else:
                temp_session.item_name = item_code
                temp_session.item_spec = ''

            # 기존 세션 백업
            original_session = self.current_defective_merge_session
            self.current_defective_merge_session = temp_session

            try:
                # 불량표 생성
                self.generate_defective_label()
                # 생성 성공 시 해당 불량품을 available_defects에서 제거
                if defect_key in self.available_defects:
                    del self.available_defects[defect_key]
                self.load_all_defective_items()
                self.show_status_message(f"불량표 즉시 생성 완료", self.COLOR_SUCCESS)
            finally:
                # 원래 세션 복원
                self.current_defective_merge_session = original_session

    def _remove_defects_from_list(self, item_code, worker):
        """불량품 목록에서 제거"""
        defect_key = f"{item_code}_{worker}"
        if messagebox.askyesno("불량품 제거",
                             f"'{item_code}' 품목의 불량품을 목록에서 제거하시겠습니까?\n"
                             f"(작업자: {worker}, 수량: {len(self.available_defects.get(defect_key, {}).get('barcodes', set()))}개)"):

            if defect_key in self.available_defects:
                del self.available_defects[defect_key]
                self.load_all_defective_items()
                self.show_status_message(f"'{item_code}' 불량품이 목록에서 제거되었습니다.", self.COLOR_SUCCESS)

                # 현재 세션이 제거된 품목과 같다면 세션 취소
                if self.current_defective_merge_session.item_code == item_code:
                    self.cancel_defective_merge_session()

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
        
        parent_frame.grid_rowconfigure(len(self.info_cards) + 4, weight=1)
        legend_frame = ttk.Frame(parent_frame, style='Sidebar.TFrame', padding=(0, 15))
        legend_frame.grid(row=len(self.info_cards) + 5, column=0, sticky='sew')
        ttk.Label(legend_frame, text="범례:", style='Subtle.TLabel').pack(anchor='w')
        ttk.Label(legend_frame, text="🟩 양품", style='Sidebar.TLabel', foreground=self.COLOR_SUCCESS).pack(anchor='w')
        ttk.Label(legend_frame, text="🟥 불량", style='Sidebar.TLabel', foreground=self.COLOR_DEFECT).pack(anchor='w')
        ttk.Label(legend_frame, text="🟪 리워크", style='Sidebar.TLabel', foreground=self.COLOR_REWORK).pack(anchor='w')
        ttk.Label(legend_frame, text="📦 잔량", style='Sidebar.TLabel', foreground=self.COLOR_SPARE).pack(anchor='w')
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
        if self.current_mode == "rework":
            self.current_mode = "standard"
        else:
            if self.current_session.master_label_code:
                messagebox.showwarning("작업 중", "진행 중인 검사 작업이 있습니다.\n리워크 모드로 전환할 수 없습니다.")
                return
            self.current_mode = "rework"
            
        self._log_event('MODE_CHANGE', detail={'mode': self.current_mode})
        self._apply_mode_ui()
        self._update_current_item_label()
    
    def toggle_remnant_mode(self):
        if self.current_mode == "remnant":
            self.current_mode = "standard"
            self.cancel_remnant_creation(force_clear=True)
        else:
            if self.current_session.master_label_code:
                messagebox.showwarning("작업 중", "진행 중인 검사 작업이 있습니다.\n잔량 모드로 전환할 수 없습니다.")
                return
            self.current_mode = "remnant"

        self._log_event('MODE_CHANGE', detail={'mode': self.current_mode})
        self._apply_mode_ui()

    def toggle_defective_mode(self):
        if self.current_mode == "defective":
            self.current_mode = "standard"
            self.cancel_defective_merge_session()
        else:
            if self.current_session.master_label_code:
                messagebox.showwarning("작업 중", "진행 중인 검사 작업이 있습니다.\n불량 처리 모드로 전환할 수 없습니다.")
                return
            self.current_mode = "defective"
            self.load_all_defective_items()

        self._log_event('MODE_CHANGE', detail={'mode': self.current_mode})
        self._apply_mode_ui()

    def load_all_defective_items(self):
        self.show_status_message("전체 작업자 불량 데이터를 불러오는 중...", self.COLOR_PRIMARY)
        self.root.update_idletasks()

        available_defects = {}
        reworked_barcodes = set()
        processed_defects = set() # 불량표에 포함된 바코드

        # 1. 이미 생성된 모든 불량표에서 바코드 목록을 가져옵니다.
        if os.path.exists(self.defects_data_folder):
            for root, _, files in os.walk(self.defects_data_folder):
                for filename in files:
                    if filename.endswith('.json'):
                        try:
                            with open(os.path.join(root, filename), 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                processed_defects.update(data.get('barcodes', []))
                        except (json.JSONDecodeError, IOError) as e:
                            print(f"불량 데이터 파일 '{filename}' 처리 중 오류: {e}")

        # 2. 리워크된 바코드 목록을 가져옵니다.
        log_folder = self.save_folder
        rework_log_pattern = re.compile(r"리워크작업이벤트로그_.*\.csv")
        if os.path.exists(log_folder):
            for filename in os.listdir(log_folder):
                if rework_log_pattern.match(filename):
                    try:
                        with open(os.path.join(log_folder, filename), 'r', encoding='utf-8-sig') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                if row.get('event') == 'REWORK_SUCCESS':
                                    details = json.loads(row.get('details', '{}'))
                                    if 'barcode' in details:
                                        reworked_barcodes.add(details['barcode'])
                    except Exception as e:
                        print(f"리워크 로그 파일 '{filename}' 처리 중 오류: {e}")

        # 3. 검사 로그를 처리하여 불량품을 집계합니다.
        inspection_log_pattern = re.compile(r"검사작업이벤트로그_.*\.csv")
        if os.path.exists(log_folder):
            for filename in os.listdir(log_folder):
                if inspection_log_pattern.match(filename):
                    try:
                        with open(os.path.join(log_folder, filename), 'r', encoding='utf-8-sig') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                if row.get('event') == 'INSPECTION_DEFECTIVE':
                                    details = json.loads(row.get('details', '{}'))
                                    barcode = details.get('barcode')
                                    if not barcode or barcode in reworked_barcodes:
                                        continue

                                    item_code_from_barcode = None
                                    for item in self.items_data:
                                        item_code = item.get('Item Code')
                                        if item_code and item_code in barcode:
                                            item_code_from_barcode = item_code
                                            break

                                    if item_code_from_barcode:
                                        worker_name = row.get('worker', '알수없음')
                                        # 품목별로 데이터를 집계 (작업자 구분 없이)
                                        defect_key = item_code_from_barcode

                                        if defect_key not in available_defects:
                                            matched_item = next((i for i in self.items_data if i['Item Code'] == item_code_from_barcode), None)
                                            available_defects[defect_key] = {
                                                'item_code': item_code_from_barcode,
                                                'name': matched_item.get('Item Name', '알수없음') if matched_item else '알수없음',
                                                'spec': matched_item.get('Spec', '') if matched_item else '',
                                                'unprocessed_barcodes': set(),
                                                'processed_barcodes': set()
                                            }

                                        # 처리 여부에 따라 분리하여 저장
                                        if barcode in processed_defects:
                                            available_defects[defect_key]['processed_barcodes'].add(barcode)
                                        else:
                                            available_defects[defect_key]['unprocessed_barcodes'].add(barcode)
                    except Exception as e:
                        print(f"검사 로그 파일 '{filename}' 처리 중 오류: {e}")

        self.available_defects = available_defects
        self._update_defective_mode_ui()
        self.show_status_message("불량 데이터 로드 완료.", self.COLOR_SUCCESS)

    def _update_defective_mode_ui(self):
        for i in self.available_defects_tree.get_children():
            self.available_defects_tree.delete(i)

        sorted_items = sorted(self.available_defects.items(), key=lambda item: item[1]['name'])
        for item_code, data in sorted_items:
            unprocessed_count = len(data.get('unprocessed_barcodes', set()))
            processed_count = len(data.get('processed_barcodes', set()))

            tag = ()
            if unprocessed_count == 0 and processed_count > 0:
                tag = ('processed_item',)

            if unprocessed_count > 0 or processed_count > 0:
                 self.available_defects_tree.insert('', 'end', values=(
                    data['name'],
                    data['item_code'],
                    unprocessed_count,
                    processed_count
                ), tags=tag)

        session = self.current_defective_merge_session
        if session.item_code:
            self.defect_session_label.config(text=f"처리 중: {session.item_name} ({session.item_code}) - {len(session.scanned_defects)} / {session.target_quantity}")
        else:
            self.defect_session_label.config(text="'불량 합치기'를 시작하거나 불량표를 바로 스캔하세요.")

        for i in self.scanned_defects_tree.get_children():
            self.scanned_defects_tree.delete(i)

        for i, barcode in enumerate(session.scanned_defects):
            self.scanned_defects_tree.insert('', 'end', values=(i + 1, barcode))

    def start_defective_merge_session(self):
        # 품목이 선택되지 않은 경우 빈 세션으로 시작 (불량표/불량품 바코드 스캔으로 자동 설정됨)
        self.current_defective_merge_session = DefectiveMergeSession(
            item_code="",  # 첫 번째 스캔으로 결정됨
            item_name="",  # 첫 번째 스캔으로 결정됨
            item_spec="",  # 첫 번째 스캔으로 결정됨
            target_quantity=int(self.defect_target_qty_spinbox.get())
        )

        self.scan_entry_defective.config(state=tk.NORMAL)
        self.cancel_defect_merge_button.config(state=tk.NORMAL)
        self.generate_defect_label_button.config(state=tk.NORMAL)
        self.start_defect_merge_button.config(state=tk.DISABLED)
        # self.available_defects_tree.config(selectmode=tk.NONE)
        self._schedule_focus_return()
        self._update_defective_mode_ui()

    def cancel_defective_merge_session(self):
        if self.current_defective_merge_session.scanned_defects:
            if not messagebox.askyesno("취소 확인", "진행중인 불량품 집계를 취소하시겠습니까?"):
                return

        self.current_defective_merge_session = DefectiveMergeSession()

        self.scan_entry_defective.config(state=tk.DISABLED)
        self.cancel_defect_merge_button.config(state=tk.DISABLED)
        self.generate_defect_label_button.config(state=tk.DISABLED)
        self.start_defect_merge_button.config(state=tk.NORMAL)
        # self.available_defects_tree.config(selectmode=tk.BROWSE)
        self._update_defective_mode_ui()

    def _process_defective_merge_scan(self, barcode: str):
        session = self.current_defective_merge_session

        # 불량표 QR 코드 처리 (최우선)
        defect_qr_data = None
        try:
            if barcode.strip().startswith('{') and barcode.strip().endswith('}'):
                data = json.loads(barcode)
                if 'id' in data and data['id'].startswith('DEFECT-'):
                    defect_qr_data = data
        except json.JSONDecodeError:
            pass

        if defect_qr_data:
            self._add_defective_label_to_current_session(defect_qr_data)
            return

        # 세션이 시작되지 않은 경우, 바코드에서 품목 코드를 추출하여 자동 세션 시작
        if not session.item_code:
            # 바코드에서 품목 코드 추출
            detected_item_code = None
            for item in self.items_data:
                item_code = item.get('Item Code')
                if item_code and item_code in barcode:
                    detected_item_code = item_code
                    break

            if detected_item_code:
                # 자동으로 세션 시작
                session.item_code = detected_item_code
                matched_item = next((item for item in self.items_data if item['Item Code'] == detected_item_code), None)
                if matched_item:
                    session.item_name = matched_item.get('Item Name', '')
                    session.item_spec = matched_item.get('Spec', '')

                session.target_quantity = 48  # 기본 목표 수량
                self.show_status_message(f"품목 '{session.item_name}' 불량품 통합 세션 자동 시작", self.COLOR_DEFECT, 3000)
                self._update_defective_mode_ui()
            else:
                if True:
                    self.show_fullscreen_warning("오류", "바코드에서 품목 코드를 인식할 수 없습니다.\n먼저 처리할 품목을 선택하거나 품목 코드가 포함된 바코드를 스캔해주세요.", self.COLOR_DEFECT)
                return

        # 바코드에 현재 세션의 품목 코드가 포함되어 있는지 확인
        if session.item_code not in barcode:
            self.show_fullscreen_warning("품목 불일치", f"현재 처리 중인 품목({session.item_name} - {session.item_code})과 다른 바코드입니다.", self.COLOR_DEFECT)
            return

        # available_defects에서 먼저 확인하고, 없으면 직접 처리 (현품표 없이 스캔된 경우)
        available_barcodes = set()
        for defect_key, defect_data in self.available_defects.items():
            if defect_data['item_code'] == session.item_code:
                available_barcodes.update(defect_data['barcodes'])

        # available_defects에 없는 바코드라면 불량품으로 직접 기록 (INSPECTION_DEFECTIVE 이벤트 생성)
        if barcode not in available_barcodes:
            self._log_event('INSPECTION_DEFECTIVE', detail={
                'barcode': barcode,
                'item_code': session.item_code,
                'item_name': session.item_name,
                'direct_scan': True,  # 현품표 없이 직접 스캔된 경우 표시
                'scan_time': datetime.datetime.now().isoformat()
            })
            self.show_status_message("불량품으로 직접 기록되었습니다.", self.COLOR_DEFECT, 2000)

        if barcode in session.scanned_defects:
            self.show_fullscreen_warning("중복 스캔", "이미 이 상자에 추가된 불량품입니다.", self.COLOR_DEFECT)
            return

        if self.success_sound: self.success_sound.play()
        session.scanned_defects.append(barcode)
        self._update_defective_mode_ui()

        # 불량표 자동 생성 조건: 목표 수량 달성 시
        if len(session.scanned_defects) >= session.target_quantity:
            self.show_status_message(f"목표 수량({session.target_quantity}개)에 도달했습니다. 불량표를 생성합니다.", self.COLOR_SUCCESS)
            # 자동으로 불량표 생성 (1번째 생성 시기)
            self.generate_defective_label()

    def generate_defective_label(self):
        """불량표를 생성하고 로그를 기록합니다.

        불량표 생성 시기:
        1. 자동 생성: 불량품 통합 세션에서 목표 수량 달성 시 (len(scanned_defects) >= target_quantity)
        2. 수동 생성: "불량표 생성" 버튼 클릭 시

        생성 파일:
        - 불량표 이미지: labels/불량표_DEFECT-YYYYMMDD-HHMMSSΜΜΜΜΜΜ.png
        - 불량표 데이터: defects_data/YYYYMMDD/DEFECT-YYYYMMDD-HHMMSSΜΜΜΜΜΜ.json

        저장 내용:
        - defect_box_id: 불량상자 고유 ID
        - creation_date: 생성일시 (ISO 형식)
        - worker: 작업자명
        - item_code, item_name, item_spec: 품목 정보
        - quantity: 불량품 수량
        - barcodes: 스캔된 불량품 바코드 목록
        """
        session = self.current_defective_merge_session
        if not session.scanned_defects:
            messagebox.showwarning("오류", "스캔된 불량품이 없습니다.")
            return

        now = datetime.datetime.now()
        defect_box_id = f"DEFECT-{now.strftime('%Y%m%d-%H%M%S%f')}"

        try:
            image_path = self._generate_defective_label_image(
                defect_box_id=defect_box_id,
                item_code=session.item_code,
                item_name=session.item_name,
                item_spec=session.item_spec,
                quantity=len(session.scanned_defects),
                worker_name=self.worker_name,
                creation_date=now.strftime('%Y-%m-%d %H:%M:%S')
            )
            if sys.platform == "win32":
                os.startfile(image_path)
        except Exception as e:
            messagebox.showerror("라벨 생성 오류", f"불량표 라벨 이미지 생성 중 오류가 발생했습니다: {e}")
            return

        defect_data = {
            "defect_box_id": defect_box_id,
            "creation_date": now.isoformat(),
            "worker": self.worker_name,
            "item_code": session.item_code,
            "item_name": session.item_name,
            "item_spec": session.item_spec,
            "quantity": len(session.scanned_defects),
            "barcodes": session.scanned_defects
        }
        try:
            daily_data_path = self._get_daily_folder_path(self.defects_data_folder)
            filepath = os.path.join(daily_data_path, f"{defect_box_id}.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(defect_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            if True:
                messagebox.showerror("저장 오류", f"불량표 데이터 파일 저장 중 오류가 발생했습니다: {e}")
            return

        self._log_event('DEFECT_MERGE_COMPLETE', detail=defect_data)

        messagebox.showinfo("생성 완료", f"불량표 생성이 완료되었습니다.\n\n불량상자 ID: {defect_box_id}")

        self.cancel_defective_merge_session()
        self.load_all_defective_items()

        # 불량표 생성 완료를 반환값으로 알림 (테스트용)
        return defect_box_id

    def _generate_defective_label_image(self, defect_box_id, item_code, item_name, item_spec, quantity, worker_name, creation_date):
        """'불량표' 라벨 이미지를 생성합니다."""
        config = {
            'size': (800, 400), 'bg_color': "#FADBD8", 'text_color': "#C0392B", 'padding': 30,
            'font_path': "C:/Windows/Fonts/malgunbd.ttf",
            'font_sizes': {'title': 60, 'header': 20, 'body': 22, 'quantity': 40, 'unit': 20, 'footer': 16,},
            'qr_code': {'size': 220, 'box_size': 10, 'border': 4,},
            'layout': {
                'title_top_margin': 25, 'header_line_margin': 15, 'content_top_margin': 30,
                'table_line_height': 45, 'table_header_x': 50, 'table_value_x': 170,
                'footer_bottom_margin': 40, 'footer_line_margin': 15,
            }
        }
        W, H = config['size']

        fonts = {}
        try:
            for name, size in config['font_sizes'].items():
                fonts[name] = ImageFont.truetype(config['font_path'], size)
        except IOError:
            for name in config['font_sizes']: fonts[name] = ImageFont.load_default()

        qr_data = json.dumps({'id': defect_box_id, 'code': item_code, 'qty': quantity})
        qr = qrcode.QRCode(version=1, box_size=config['qr_code']['box_size'], border=config['qr_code']['border'])
        qr.add_data(qr_data)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color=config['text_color'], back_color=config['bg_color']).resize((config['qr_code']['size'], config['qr_code']['size']))

        img = Image.new('RGB', (W, H), config['bg_color'])
        draw = ImageDraw.Draw(img)

        title_text = "불 량 표"
        title_bbox = draw.textbbox((0, 0), title_text, font=fonts['title'])
        title_w, title_h = title_bbox[2] - title_bbox[0], title_bbox[3] - title_bbox[1]
        draw.text(((W - title_w) / 2, config['layout']['title_top_margin']), title_text, font=fonts['title'], fill=config['text_color'])
        line_y = config['layout']['title_top_margin'] + title_h + config['layout']['header_line_margin']
        draw.line([(config['padding'], line_y), (W - config['padding'], line_y)], fill=config['text_color'], width=3)

        info_items = [
            {'label': "품 목 명", 'value': f": {item_name}"},
            {'label': "품목코드", 'value': f": {item_code}"},
            {'label': "규    격", 'value': f": {item_spec}"},
        ]
        y_pos = line_y + config['layout']['content_top_margin']
        for item in info_items:
            draw.text((config['layout']['table_header_x'], y_pos), item['label'], font=fonts['header'], fill=config['text_color'])
            draw.text((config['layout']['table_value_x'], y_pos), item['value'], font=fonts['body'], fill=config['text_color'])
            y_pos += config['layout']['table_line_height']

        draw.text((config['layout']['table_header_x'], y_pos), "수    량", font=fonts['header'], fill=config['text_color'])
        qty_text = str(quantity)
        draw.text((config['layout']['table_value_x'], y_pos-10), f": {qty_text}", font=fonts['quantity'], fill=config['text_color'], stroke_width=1)
        draw.text((config['layout']['table_value_x'] + draw.textlength(f": {qty_text}", font=fonts['quantity']) + 5, y_pos), "EA", font=fonts['unit'], fill=config['text_color'])

        footer_y = H - config['layout']['footer_bottom_margin']
        draw.line([(config['padding'], footer_y - config['layout']['footer_line_margin']), (W - config['padding'], footer_y - config['layout']['footer_line_margin'])], fill=config['text_color'], width=1)
        footer_text = f"ID: {defect_box_id} | 생성일: {creation_date} | 작업자: {worker_name}"
        draw.text((config['padding'], footer_y), footer_text, font=fonts['footer'], fill=config['text_color'])

        img.paste(qr_img, (W - config['qr_code']['size'] - config['padding'], line_y + config['layout']['content_top_margin']))

        daily_labels_path = self._get_daily_folder_path(self.defective_labels_folder)
        filepath = os.path.join(daily_labels_path, f"{defect_box_id}.png")
        img.save(filepath)
        return filepath

    def _apply_mode_ui(self):
        self.apply_scaling()
        if not hasattr(self, 'rework_mode_button'): return

        is_rework = self.current_mode == 'rework'
        is_remnant = self.current_mode == 'remnant'
        is_defective = self.current_mode == 'defective'

        self.rework_mode_button.config(text="검사 모드로" if is_rework else "리워크 모드")
        self.remnant_mode_button.config(text="검사 모드로" if is_remnant else "잔량 모드")
        if hasattr(self, 'defective_mode_button'):
            self.defective_mode_button.config(text="검사 모드로" if is_defective else "불량 처리 모드")

        # 모든 모드 버튼의 표시/숨김을 완전히 제어
        # 먼저 모든 버튼 숨기기
        if hasattr(self, 'rework_mode_button'):
            self.rework_mode_button.pack_forget()
        if hasattr(self, 'remnant_mode_button'):
            self.remnant_mode_button.pack_forget()
        if hasattr(self, 'defective_mode_button'):
            self.defective_mode_button.pack_forget()

        # 현재 모드에 따라 필요한 버튼들만 다시 표시
        if is_defective:
            # 불량 모드: 불량 모드 버튼만 표시
            if hasattr(self, 'defective_mode_button'):
                self.defective_mode_button.pack(side=tk.RIGHT, padx=(5,0))
        else:
            # 다른 모드들: 모든 모드 버튼 표시
            if hasattr(self, 'defective_mode_button'):
                self.defective_mode_button.pack(side=tk.RIGHT, padx=(5,0))
            if hasattr(self, 'remnant_mode_button'):
                self.remnant_mode_button.pack(side=tk.RIGHT, padx=(5,0))
            if hasattr(self, 'rework_mode_button'):
                self.rework_mode_button.pack(side=tk.RIGHT, padx=(5,0))

        if is_rework:
            self.rework_view_frame.tkraise()
            self.scan_entry = self.scan_entry_rework
        elif is_remnant:
            self.remnant_view_frame.tkraise()
            self.scan_entry = self.scan_entry_remnant
        elif is_defective:
            self.defective_view_frame.tkraise()
            self.scan_entry = self.scan_entry_defective
        else:
            self.inspection_view_frame.tkraise()
            self.scan_entry = self.scan_entry_inspection

        self.on_pedal_release_ui_feedback()
        self._update_current_item_label()
        self._schedule_focus_return()

    def _populate_rework_trees(self):
        if not hasattr(self, 'reworked_today_tree'): return

        for i in self.reworked_today_tree.get_children(): self.reworked_today_tree.delete(i)
        
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

        if self.master_label_replace_state == 'awaiting_old_completed':
            text = "완료된 현품표 교체: 교체할 기존 현품표를 스캔하세요."
            color = self.COLOR_PRIMARY
        elif self.master_label_replace_state == 'awaiting_new_replacement':
            text = "완료된 현품표 교체: 적용할 새로운 현품표를 스캔하세요."
            color = self.COLOR_SUCCESS
        elif self.master_label_replace_state == 'awaiting_additional_items':
            needed = self.replacement_context.get('items_needed', 0)
            scanned = len(self.replacement_context.get('additional_items', []))
            text = f"수량 추가: {needed - scanned}개 더 추가 스캔하세요. (총 {needed}개)"
            color = self.COLOR_PRIMARY
        elif self.master_label_replace_state == 'awaiting_removed_items':
            needed = self.replacement_context.get('items_to_remove_count', 0)
            scanned = len(self.replacement_context.get('removed_items', []))
            text = f"수량 제외: {needed - scanned}개 더 제외 스캔하세요. (총 {needed}개)"
            color = self.COLOR_DEFECT
        elif self.current_mode == "rework":
            text = f"♻️ 리워크 모드: 성공적으로 수리된 제품의 바코드를 스캔하세요."
            color = self.COLOR_REWORK
        elif self.current_mode == "remnant":
            text = f"📦 잔량 등록 모드: 등록할 제품의 바코드를 스캔하여 목록을 만드세요."
            color = self.COLOR_SPARE
        elif self.current_session.is_remnant_session:
            text = f"📦 잔량 검사: '{self.current_session.item_name}'의 잔량을 검사합니다.\n총 {self.current_session.quantity}개 목표"
            color = self.COLOR_SPARE
        elif self.current_session.master_label_code:
            name_part = f"현재 품목: {self.current_session.item_name} ({self.current_session.item_code})"
            instruction = f"\n총 {self.current_session.quantity}개 목표로 스캔하세요. (불량: {self.DEFECT_PEDAL_KEY_NAME} 페달)"
            text = f"{name_part}{instruction}"
        else: 
            text = "현품표 라벨을 스캔하여 검사를 시작하세요."
            color = self.COLOR_TEXT_SUBTLE
        
        self.current_item_label['text'], self.current_item_label['foreground'] = text, color

    def _parse_new_format_qr(self, qr_data: str) -> Optional[Dict[str, str]]:
        # JSON 형식 현품표 QR 코드 처리
        if qr_data.strip().startswith('{') and qr_data.strip().endswith('}'):
            try:
                parsed = json.loads(qr_data)
                if False:
                    print(f"[DEBUG] JSON 파싱 성공: {parsed}")
                if 'CLC' in parsed:
                    return parsed
                return None
            except json.JSONDecodeError as e:
                if False:
                    print(f"[DEBUG] JSON 파싱 실패: {e}, QR 데이터: {qr_data}")
                pass

        # 기존 형식 (=, |로 구분) 처리
        if '=' not in qr_data or '|' not in qr_data:
            return None
        try:
            parsed = dict(pair.split('=', 1) for pair in qr_data.strip().split('|'))
            if 'CLC' in parsed and 'WID' in parsed: return parsed
            return None
        except ValueError:
            return None

    def _complete_session_logic_only(self, session: InspectionSession):
        if session.master_label_code:
            self.completed_master_labels.add(session.master_label_code)

        log_detail = {
            'master_label_code': session.master_label_code, 'item_code': session.item_code,
            'item_name': session.item_name, 'item_spec': session.item_spec,
            'scan_count': len(session.scanned_barcodes), 'tray_capacity': session.quantity,
            'scanned_product_barcodes': [item['barcode'] for item in session.good_items],
            'defective_product_barcodes': [item['barcode'] for item in session.defective_items],
            'work_time_sec': session.stopwatch_seconds, 'error_count': session.mismatch_error_count,
            'total_idle_seconds': session.total_idle_seconds, 'has_error_or_reset': session.has_error_or_reset,
            'is_partial_submission': session.is_partial_submission, 'is_restored_session': session.is_restored_session,
            'start_time': session.start_time.isoformat() if session.start_time else None,
            'end_time': datetime.datetime.now().isoformat(), 
            'is_remnant_session': session.is_remnant_session 
        }
        self._log_event('TRAY_COMPLETE', detail=log_detail)
        item_code = session.item_code
        if item_code not in self.work_summary:
            self.work_summary[item_code] = {'name': session.item_name, 'spec': session.item_spec, 
                                             'pallet_count': 0, 'defective_ea_count': 0}
        self.work_summary[item_code]['defective_ea_count'] += len(session.defective_items)
        self.work_summary[item_code]['pallet_count'] += 1
        if not session.is_partial_submission:
            self.total_tray_count += 1
            self.completed_tray_times.append(session.stopwatch_seconds)
    
    def process_scan(self, event=None):
        raw_barcode = self.scan_entry.get().strip()
        self.scan_entry.delete(0, tk.END)
        self._process_scan_logic(raw_barcode)

    def _process_scan_logic(self, raw_barcode: str):
        if self.master_label_replace_state:
            if self.master_label_replace_state in ['awaiting_old_completed', 'awaiting_new_replacement']:
                self._handle_historical_replacement_scan(raw_barcode)
            elif self.master_label_replace_state == 'awaiting_additional_items':
                self._handle_additional_item_scan(raw_barcode)
            elif self.master_label_replace_state == 'awaiting_removed_items':
                self._handle_removed_item_scan(raw_barcode)
            return

        current_time = time.monotonic()
        if current_time - self.last_scan_time < self.scan_delay_sec.get():
            return
        self.last_scan_time = current_time
        
        if not raw_barcode: return
        
        if getattr(self, 'is_excluding_item', False):
            self._handle_exclusion_scan(raw_barcode)
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
        

        if self.current_mode == 'rework':
            self._process_rework_scan(barcode)
        elif self.current_mode == 'remnant':
            self._process_remnant_scan(barcode)
        elif self.current_mode == 'defective':
            self._process_defective_merge_scan(barcode)
        else:
            self._process_inspection_scan(barcode)

    def _process_inspection_scan(self, barcode: str):
        remnant_id = None
        
        try:
            if barcode.strip().startswith('{') and barcode.strip().endswith('}'):
                data = json.loads(barcode)
                if 'id' in data and data['id'].upper().startswith('SPARE-'):
                    remnant_id = data['id']
        except json.JSONDecodeError:
            pass

        if not remnant_id and barcode.upper().startswith("SPARE-"):
            remnant_id = barcode

        if remnant_id:
            if self.current_session.master_label_code:
                self._add_remnant_to_current_session(remnant_id)
            else:
                self.show_fullscreen_warning("작업 순서 오류", "먼저 현품표를 스캔하여 작업을 시작해주세요.\n잔량표는 진행 중인 작업에만 추가할 수 있습니다.", self.COLOR_DEFECT)
                self._log_event('SCAN_FAIL_REMANT_WITHOUT_MASTER', detail={'remnant_id': remnant_id})
            return

        is_master_label_format = False
        parsed_data = self._parse_new_format_qr(barcode)
        item_code_length = config.get('inspection.item_code_length', 13)

        if parsed_data:
            is_master_label_format = True
        elif len(barcode) == item_code_length and any(item['Item Code'] == barcode for item in self.items_data):
            is_master_label_format = True

        if self.current_session.master_label_code:
            if is_master_label_format:
                self.show_status_message(f"'{self.current_session.item_name}' 작업을 자동 제출하고 새 작업을 시작합니다.", self.COLOR_PRIMARY)
                self.root.update_idletasks()
                time.sleep(1)
                self.current_session.is_partial_submission = True
                self.complete_session()
                self.root.after(100, lambda: self._process_inspection_scan(barcode))
            else:
                is_defect_scan = keyboard.is_pressed(self.DEFECT_PEDAL_KEY_NAME.lower())
                
                item_code_length = config.get('inspection.item_code_length', 13)
                if len(barcode) <= item_code_length:
                    self.show_fullscreen_warning("바코드 형식 오류", f"제품 바코드는 {item_code_length}자리보다 길어야 합니다.", self.COLOR_DEFECT)
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
        else:
            if is_master_label_format:
                if parsed_data and barcode in self.completed_master_labels:
                    if messagebox.askyesno("작업 재개 확인", "이미 제출된 작업입니다.\n이어서 진행하시겠습니까?"):
                        self._resume_submitted_session(barcode)
                    return

                item_info = parsed_data if parsed_data else {'CLC': barcode}
                item_code_from_label = item_info.get('CLC')
                matched_item = next((item for item in self.items_data if item['Item Code'] == item_code_from_label), None)

                if not matched_item:
                    self.show_fullscreen_warning("품목 없음", f"현품표의 품목코드 '{item_code_from_label}' 정보를 찾을 수 없습니다.", self.COLOR_DEFECT)
                    return

                self.current_session.master_label_code = barcode
                self.current_session.item_code = matched_item.get('Item Code', '')
                self.current_session.item_name = matched_item.get('Item Name', '')
                self.current_session.item_spec = matched_item.get('Spec', '')

                if parsed_data:
                    # 생산 현품표 형식 필드 매핑
                    self.current_session.phs = parsed_data.get('PHS', '')
                    self.current_session.work_order_id = parsed_data.get('WID', '')
                    self.current_session.supplier_code = parsed_data.get('SPC', '')
                    self.current_session.finished_product_batch = parsed_data.get('FPB', '')
                    self.current_session.outbound_date = parsed_data.get('OBD', '')
                    self.current_session.item_group = parsed_data.get('PJT', '')

                    # 수량 설정 (생산 형식: QT, 테스트 형식: QTY)
                    tray_size = config.get('inspection.tray_size', 60)
                    qty_field = parsed_data.get('QT') or parsed_data.get('QTY')
                    try:
                        self.current_session.quantity = int(qty_field) if qty_field else tray_size
                    except (ValueError, TypeError):
                        self.current_session.quantity = tray_size
                    self._log_event('MASTER_LABEL_SCANNED', detail=parsed_data)
                else:
                    tray_size = config.get('inspection.tray_size', 60)
                    self.current_session.quantity = tray_size
                    self._log_event('MASTER_LABEL_SCANNED', detail={'code': barcode, 'format': 'legacy'})

                self._apply_mode_ui()
                self._update_center_display()
                self._update_current_item_label()
                self._start_stopwatch()
                self._save_current_session_state()
            else:
                self.show_fullscreen_warning("작업 시작 오류", "먼저 현품표 라벨을 스캔하여 작업을 시작해주세요.", self.COLOR_DEFECT)

    def _process_rework_scan(self, barcode: str):
        if any(item['barcode'] == barcode for item in self.reworked_items_today):
            self.show_fullscreen_warning("리워크 중복", f"해당 바코드'{barcode}'는 이미 오늘 리워크 처리되었습니다.", self.COLOR_DEFECT)
            self._log_event('REWORK_FAIL_DUPLICATE', detail={'barcode': barcode})
        else:
            self.record_rework_success(barcode)

    def _process_remnant_scan(self, barcode: str):
        parsed_data = self._parse_new_format_qr(barcode)
        item_code_length = config.get('inspection.item_code_length', 13)

        # 자동 테스트 모드에서는 TEST- 바코드 허용
        if parsed_data or barcode.upper().startswith("SPARE-") or len(barcode) < item_code_length:
            self.show_fullscreen_warning("스캔 오류", "잔량 등록 모드에서는 제품 바코드만 스캔할 수 있습니다.", self.COLOR_DEFECT)
            return

        if barcode in self.current_remnant_session.scanned_barcodes:
            self.show_fullscreen_warning("바코드 중복", f"이미 등록된 바코드입니다: {barcode}", self.COLOR_DEFECT)
            return

        try:
            item_code_from_barcode = None
            for item in self.items_data:
                item_code = item.get('Item Code')
                if item_code and item_code in barcode:
                    item_code_from_barcode = item_code
                    break
            if not item_code_from_barcode:
                    raise ValueError("바코드에서 품목 코드를 찾을 수 없습니다.")
        except Exception as e:
            self.show_fullscreen_warning("바코드 형식 오류", f"제품 바코드에서 유효한 품목 코드를 찾을 수 없습니다.\n{e}", self.COLOR_DEFECT)
            return

        if not self.current_remnant_session.item_code:
            matched_item = next((item for item in self.items_data if item['Item Code'] == item_code_from_barcode), None)
            if not matched_item:
                self.show_fullscreen_warning("품목 없음", f"품목코드 '{item_code_from_barcode}'에 해당하는 정보를 찾을 수 없습니다.", self.COLOR_DEFECT)
                return
            
            self.current_remnant_session.item_code = item_code_from_barcode
            self.current_remnant_session.item_name = matched_item.get("Item Name", "")
            self.current_remnant_session.item_spec = matched_item.get("Spec", "")
            self.remnant_item_label.config(text=f"등록 품목: {self.current_remnant_session.item_name} ({self.current_remnant_session.item_code})")
        
        elif self.current_remnant_session.item_code != item_code_from_barcode:
            self.show_fullscreen_warning("품목 불일치", f"다른 종류의 품목은 함께 등록할 수 없습니다.\n(현재 품목: {self.current_session.item_code})", self.COLOR_DEFECT)
            return
        
        if self.success_sound: self.success_sound.play()
        self.current_remnant_session.scanned_barcodes.append(barcode)
        self._update_remnant_list()
    
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
        
        if self.root.winfo_exists():
            self.root.after(0, self._redraw_scan_trees)
            self.root.after(0, self._update_center_display)
            self.root.after(0, self._update_current_item_label)
            self.root.after(0, lambda: self.undo_button.config(state=tk.NORMAL))
        
        self._save_current_session_state()
        
        good_item_count = len(self.current_session.good_items)
        target_quantity = self.current_session.quantity
        
        if good_item_count >= target_quantity:
            self.complete_session()

    def record_rework_success(self, barcode: str):
        if self.success_sound: self.success_sound.play()
        
        reworked_data = {
            'barcode': barcode,
            'rework_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.reworked_items_today.insert(0, reworked_data)
        
        log_detail = {
            'barcode': barcode,
            'rework_time': reworked_data['rework_time']
        }
        self._log_event('REWORK_SUCCESS', detail=log_detail)
        
        self.rework_count_label.config(text=f"금일 리워크 완료: {len(self.reworked_items_today)}개")
        self.show_status_message(f"리워크 성공: {barcode}", self.COLOR_SUCCESS)
        
        self._populate_rework_trees()
        self._update_current_item_label()
        self._update_summary_title()

    def _redraw_scan_trees(self):
        if not hasattr(self, 'good_items_tree') or not self.good_items_tree.winfo_exists(): return
        for i in self.good_items_tree.get_children(): self.good_items_tree.delete(i)
        for i in self.defective_items_tree.get_children(): self.defective_items_tree.delete(i)
        for idx, item in enumerate(self.current_session.good_items):
            self.good_items_tree.insert('', 0, values=(idx + 1, item['barcode']))
        for idx, item in enumerate(self.current_session.defective_items):
            self.defective_items_tree.insert('', 0, values=(idx + 1, item['barcode']))

    def complete_session(self):
        session_to_complete = self.current_session
        
        if session_to_complete.consumed_remnant_ids:
            self._log_event('REMNANT_FILES_DELETION_START', detail={'ids': session_to_complete.consumed_remnant_ids})
            for remnant_id in session_to_complete.consumed_remnant_ids:
                try:
                    remnant_filepath_json = os.path.join(self.remnants_folder, f"{remnant_id}.json")
                    remnant_filepath_png = os.path.join(self.labels_folder, f"{remnant_id}.png")
                    if os.path.exists(remnant_filepath_json):
                        os.remove(remnant_filepath_json)
                    if os.path.exists(remnant_filepath_png):
                        os.remove(remnant_filepath_png)
                except Exception as e:
                    print(f"잔량 파일 삭제 중 오류 발생 (ID: {remnant_id}): {e}")
                    self._log_event('REMNANT_FILE_DELETION_ERROR', detail={'remnant_id': remnant_id, 'error': str(e)})

        self.current_session = InspectionSession()
        
        self._stop_stopwatch()
        self._stop_idle_checker()
        if self.root.winfo_exists():
            self.undo_button['state'] = tk.DISABLED
            
        self._complete_session_logic_only(session_to_complete)
        
        if self.root.winfo_exists():
            self.root.after(0, self._redraw_scan_trees)
            self.root.after(0, self._update_all_summaries)
            self.root.after(0, self._reset_ui_to_waiting_state)
            
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

    def _resume_submitted_session(self, master_label_code: str):
        """실수로 제출된 세션을 로그 파일에서 찾아 복원합니다."""

        log_details = self._find_last_tray_complete_log(master_label_code)

        if not log_details:
            messagebox.showerror("복원 실패", "이전 작업 기록을 로그 파일에서 찾을 수 없습니다.")
            return

        try:
            restored_session = InspectionSession()
            restored_session.master_label_code = log_details.get('master_label_code', '')
            restored_session.item_code = log_details.get('item_code', '')
            restored_session.item_name = log_details.get('item_name', '')
            restored_session.item_spec = log_details.get('item_spec', '')
            tray_size = config.get('inspection.tray_size', 60)
            restored_session.quantity = int(log_details.get('tray_capacity', tray_size))
            restored_session.stopwatch_seconds = float(log_details.get('work_time_sec', 0.0))
            
            good_barcodes = log_details.get('scanned_product_barcodes', [])
            defective_barcodes = log_details.get('defective_product_barcodes', [])
            
            restored_session.good_items = [{'barcode': bc, 'timestamp': datetime.datetime.now().isoformat(), 'status': 'Good'} for bc in good_barcodes]
            restored_session.defective_items = [{'barcode': bc, 'timestamp': datetime.datetime.now().isoformat(), 'status': 'Defective'} for bc in defective_barcodes]
            restored_session.scanned_barcodes = good_barcodes + defective_barcodes

            self.current_session = restored_session
            
            if master_label_code in self.completed_master_labels:
                self.completed_master_labels.remove(master_label_code)
            self._log_event('TRAY_RESUMED', detail={'master_label_code': master_label_code})

            self.show_status_message("이전 작업을 복원했습니다. 이어서 진행하세요.", self.COLOR_SUCCESS)
            self._update_current_item_label()
            self._redraw_scan_trees()
            self._update_center_display()
            self._start_stopwatch(resume=True)
            self.undo_button.config(state=tk.NORMAL if self.current_session.scanned_barcodes else tk.DISABLED)
            self._save_current_session_state()

        except Exception as e:
            messagebox.showerror("복원 오류", f"작업 복원 중 오류가 발생했습니다.\n{e}")
            self._log_event('TRAY_RESUME_FAILED', detail={'error': str(e)})


    def _find_last_tray_complete_log(self, master_label_code: str) -> Optional[Dict[str, Any]]:
        """로그 파일에서 특정 master_label_code의 마지막 TRAY_COMPLETE 이벤트를 찾습니다."""
        if not self.log_file_path or not os.path.exists(self.log_file_path):
            return None
        
        last_match = None
        try:
            with open(self.log_file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                all_rows = list(reader)
                for row in reversed(all_rows):
                    if row.get('event') == 'TRAY_COMPLETE':
                        details = json.loads(row.get('details', '{}'))
                        if details.get('master_label_code') == master_label_code:
                            last_match = details
                            break
            return last_match
        except (IOError, json.JSONDecodeError, KeyError) as e:
            print(f"로그 파일 검색 오류: {e}")
            return None

    def _add_remnant_to_current_session(self, remnant_id: str):
        remnant_filepath = os.path.join(self.remnants_folder, f"{remnant_id}.json")
        if not os.path.exists(remnant_filepath):
            self.show_fullscreen_warning("잔량표 없음", f"해당 잔량 ID({remnant_id})를 찾을 수 없습니다.", self.COLOR_DEFECT)
            return

        try:
            with open(remnant_filepath, 'r', encoding='utf-8') as f:
                remnant_data = json.load(f)

            if remnant_data.get('item_code') != self.current_session.item_code:
                self.show_fullscreen_warning("품목 불일치", "현재 작업과 다른 품목의 잔량표는 추가할 수 없습니다.", self.COLOR_DEFECT)
                return

            remnant_barcodes = remnant_data.get('remnant_barcodes', [])
            space_available = self.current_session.quantity - len(self.current_session.good_items)
            
            if space_available <= 0:
                self.show_status_message("이미 목표 수량을 모두 채웠습니다.", self.COLOR_IDLE)
                return

            remnant_quantity = len(remnant_barcodes)
            if remnant_quantity <= space_available:
                if messagebox.askyesno("잔량 추가", f"잔량 {remnant_quantity}개를 현재 작업에 추가하시겠습니까?"):
                    for barcode in remnant_barcodes:
                        self.record_inspection_result(barcode, 'Good')
                    
                    self.current_session.consumed_remnant_ids.append(remnant_id)
                    self._log_event('REMNANT_CONSUMED', detail={'remnant_id': remnant_id})
                    self.show_status_message(f"잔량 {remnant_quantity}개가 추가되었습니다.", self.COLOR_SUCCESS)
            else:
                items_to_leave = remnant_quantity - space_available
                self._prompt_remnant_fill_method(space_available, items_to_leave, remnant_id, remnant_data)

        except Exception as e:
            messagebox.showerror("잔량 추가 오류", f"잔량 데이터를 추가하는 중 오류가 발생했습니다:\n{e}")

    def _prompt_remnant_fill_method(self, items_needed, items_to_leave, remnant_id, remnant_data):
        popup = tk.Toplevel(self.root)
        popup.title("잔량 추가 방식 선택")
        popup.transient(self.root)
        popup.grab_set()
        popup.geometry("600x400")
        
        main_frame = ttk.Frame(popup, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = ttk.Label(main_frame, text="잔량 처리 방법을 선택하세요.", font=(self.DEFAULT_FONT, 16, 'bold'))
        title_label.pack(pady=(0, 20))

        info_text = (f"현재 현품표에 필요한 수량: {items_needed}개\n"
                     f"스캔한 잔량표의 총 수량: {items_needed + items_to_leave}개")
        info_label = ttk.Label(main_frame, text=info_text, font=(self.DEFAULT_FONT, 12))
        info_label.pack(pady=(0, 30))

        choice = tk.StringVar()

        def on_confirm():
            selected_choice = choice.get()
            popup.destroy()
            if selected_choice == 'scan_needed':
                self.show_status_message(f"필요한 {items_needed}개의 제품을 개별 스캔하세요.", self.COLOR_PRIMARY, duration=10000)
            elif selected_choice == 'scan_excluded':
                self.is_excluding_item = True
                self.exclusion_context = {
                    'remnant_id': remnant_id,
                    'remnant_data': remnant_data,
                    'items_to_exclude_count': items_to_leave,
                    'excluded_items': []
                }
                self.show_status_message(f" 제외할 {items_to_leave}개 제품을 스캔하세요.", self.COLOR_DEFECT, duration=15000)
        
        if items_needed <= items_to_leave:
            btn1_text = f"✅ 부족한 {items_needed}개 채우기 (개별 스캔)"
            btn1 = ttk.Button(main_frame, text=btn1_text, command=lambda: choice.set('scan_needed') or on_confirm())
            btn1.pack(pady=10, ipady=15, fill=tk.X)
            btn1.focus_set()
            
            btn2_text = f"남는 {items_to_leave}개 제외하기 (제외품 스캔)"
            btn2 = ttk.Button(main_frame, text=btn2_text, command=lambda: choice.set('scan_excluded') or on_confirm())
            btn2.pack(pady=10, ipady=15, fill=tk.X)
        else:
            btn1_text = f"✅ 남는 {items_to_leave}개 제외하기 (제외품 스캔)"
            btn1 = ttk.Button(main_frame, text=btn1_text, command=lambda: choice.set('scan_excluded') or on_confirm())
            btn1.pack(pady=10, ipady=15, fill=tk.X)
            btn1.focus_set()

            btn2_text = f"부족한 {items_needed}개 채우기 (개별 스캔)"
            btn2 = ttk.Button(main_frame, text=btn2_text, command=lambda: choice.set('scan_needed') or on_confirm())
            btn2.pack(pady=10, ipady=15, fill=tk.X)
            
        self.root.wait_window(popup)

    def _handle_exclusion_scan(self, excluded_barcode: str):
        ctx = self.exclusion_context
        remnant_barcodes = ctx['remnant_data'].get('remnant_barcodes', [])

        if excluded_barcode not in remnant_barcodes:
            self.show_fullscreen_warning("스캔 오류", "이 바코드는 원래 잔량표에 포함되지 않은 제품입니다.", self.COLOR_DEFECT)
            return

        if excluded_barcode in ctx['excluded_items']:
            self.show_status_message(f"이미 제외 목록에 추가된 바코드입니다: {excluded_barcode}", self.COLOR_IDLE)
            return
            
        if self.success_sound: self.success_sound.play()
        ctx['excluded_items'].append(excluded_barcode)
        
        remaining_to_exclude = ctx['items_to_exclude_count'] - len(ctx['excluded_items'])

        if remaining_to_exclude > 0:
            self.show_status_message(f"제외 완료. 남은 {remaining_to_exclude}개의 제외품을 스캔하세요.", self.COLOR_DEFECT, duration=15000)
        else:
            self.show_status_message("제외품 스캔 완료. 데이터를 처리합니다...", self.COLOR_SUCCESS)
            
            barcodes_to_add = [b for b in remnant_barcodes if b not in ctx['excluded_items']]
            for barcode in barcodes_to_add:
                self.record_inspection_result(barcode, 'Good')
            
            if ctx['excluded_items']:
                self._create_new_remnant_from_list(ctx['excluded_items'], ctx['remnant_data'])
            
            remnant_id = ctx['remnant_id']
            remnant_filepath_json = os.path.join(self.remnants_folder, f"{remnant_id}.json")
            remnant_filepath_png = os.path.join(self.labels_folder, f"{remnant_id}.png")
            
            if os.path.exists(remnant_filepath_json):
                os.remove(remnant_filepath_json)
            try:
                if os.path.exists(remnant_filepath_png):
                    os.remove(remnant_filepath_png)
            except FileNotFoundError:
                pass
            
            self.is_excluding_item = False
            self.exclusion_context = {}

    def _create_new_remnant_from_list(self, barcodes: List[str], original_remnant_data: Dict):
        """바코드 리스트로부터 새로운 잔량표를 생성하는 헬퍼 함수"""
        self.show_status_message(f"초과분 {len(barcodes)}개로 새 잔량표 생성 중...", self.COLOR_SPARE, 5000)
        
        now = datetime.datetime.now()
        new_remnant_id = f"SPARE-{now.strftime('%Y%m%d-%H%M%S%f')}"
        
        new_remnant_data = {
            "remnant_id": new_remnant_id,
            "creation_date": now.isoformat(),
            "worker": self.worker_name,
            "item_code": original_remnant_data['item_code'],
            "item_name": original_remnant_data['item_name'],
            "item_spec": original_remnant_data['item_spec'],
            "remnant_barcodes": barcodes
        }

        try:
            filepath = os.path.join(self.remnants_folder, f"{new_remnant_id}.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(new_remnant_data, f, ensure_ascii=False, indent=4)
            self._log_event('REMNANT_CREATED_FROM_OVERFLOW', detail=new_remnant_data)
        except Exception as e:
            messagebox.showerror("저장 실패", f"초과분 잔량 파일 저장 중 오류 발생: {e}")
            return
            
        try:
            image_path = self._generate_remnant_label_image(
                remnant_id=new_remnant_id,
                item_code=new_remnant_data['item_code'],
                item_name=new_remnant_data['item_name'],
                item_spec=new_remnant_data['item_spec'],
                quantity=len(new_remnant_data['remnant_barcodes']),
                worker_name=self.worker_name,
                creation_date=now.strftime('%Y-%m-%d %H:%M:%S')
            )
            if sys.platform == "win32":
                os.startfile(image_path)
            
            messagebox.showinfo("초과분 잔량 생성 완료", f"현품표 작업을 완료하고 남은 {len(barcodes)}개의 제품으로\n새로운 잔량표를 생성했습니다.\n\n신규 잔량 ID: {new_remnant_id}")

        except Exception as e:
            messagebox.showwarning("이미지 생성 실패", f"새 잔량 라벨 이미지 생성에 실패했습니다: {e}")

    def _add_defective_label_to_current_session(self, defect_qr_data: Dict[str, Any]):
        """불량표 QR 코드를 스캔했을 때 불량품 통합 세션에 추가하는 함수"""
        session = self.current_defective_merge_session
        defect_box_id = defect_qr_data.get('id')
        item_code = defect_qr_data.get('code')
        quantity = defect_qr_data.get('qty')

        if not defect_box_id or not item_code or not quantity:
            self.show_fullscreen_warning("불량표 QR 오류", "불량표 QR 코드의 형식이 올바르지 않습니다.", self.COLOR_DEFECT)
            return

        # 불량표 JSON 데이터 파일 찾기
        defect_filepath = self._find_defective_label_data_file(defect_box_id)
        if not defect_filepath:
            self.show_fullscreen_warning("불량표 데이터 없음", f"해당 불량표 ID({defect_box_id})의 데이터를 찾을 수 없습니다.", self.COLOR_DEFECT)
            return

        try:
            with open(defect_filepath, 'r', encoding='utf-8') as f:
                defect_data = json.load(f)
        except Exception as e:
            self.show_fullscreen_warning("파일 읽기 오류", f"불량표 데이터 파일을 읽는 중 오류가 발생했습니다: {e}", self.COLOR_DEFECT)
            return

        # 세션이 시작되지 않은 경우 자동 시작
        if not session.item_code:
            matched_item = next((item for item in self.items_data if item['Item Code'] == item_code), None)
            if not matched_item:
                self.show_fullscreen_warning("품목 없음", f"불량표의 품목코드 '{item_code}' 정보를 찾을 수 없습니다.", self.COLOR_DEFECT)
                return

            session.item_code = item_code
            session.item_name = matched_item.get('Item Name', '')
            session.item_spec = matched_item.get('Spec', '')
            session.target_quantity = 48  # 기본 목표 수량
            self.show_status_message(f"품목 '{session.item_name}' 불량품 통합 세션 자동 시작", self.COLOR_DEFECT, 3000)
            self._update_defective_mode_ui()

        # 품목 일치성 검사
        elif session.item_code != item_code:
            self.show_fullscreen_warning("품목 불일치", f"현재 처리 중인 품목({session.item_code})과 불량표의 품목({item_code})이 다릅니다.", self.COLOR_DEFECT)
            return

        # 불량표에서 바코드 목록 가져오기
        defect_barcodes = defect_data.get('barcodes', [])
        if not defect_barcodes:
            self.show_fullscreen_warning("빈 불량표", "불량표에 바코드 정보가 없습니다.", self.COLOR_DEFECT)
            return

        # 초과 수량 감지 및 처리
        current_count = len(session.scanned_defects)
        incoming_quantity = len(defect_barcodes)
        target_quantity = session.target_quantity

        if current_count + incoming_quantity > target_quantity:
            overflow = current_count + incoming_quantity - target_quantity
            self._handle_defective_overflow(defect_barcodes, overflow, session, defect_data)
            return

        # 중복 바코드 확인
        duplicate_barcodes = [b for b in defect_barcodes if b in session.scanned_defects]
        if duplicate_barcodes:
            self.show_fullscreen_warning("중복 불량품", f"이미 추가된 불량품이 {len(duplicate_barcodes)}개 포함되어 있습니다.", self.COLOR_DEFECT)
            return

        # 불량품 추가
        if self.success_sound:
            self.success_sound.play()

        session.scanned_defects.extend(defect_barcodes)
        self._update_defective_mode_ui()

        self.show_status_message(f"불량표 {defect_box_id}에서 {len(defect_barcodes)}개 불량품 추가됨", self.COLOR_SUCCESS, 3000)
        self._log_event('DEFECT_LABEL_SCANNED', detail={'defect_box_id': defect_box_id, 'item_code': item_code, 'quantity': len(defect_barcodes)})

        # 목표 수량 달성 시 자동 불량표 생성
        if len(session.scanned_defects) >= target_quantity:
            self.show_status_message(f"목표 수량({target_quantity}개)에 도달했습니다. 불량표를 생성합니다.", self.COLOR_SUCCESS)
            self.generate_defective_label()

    def _find_defective_label_data_file(self, defect_box_id: str) -> Optional[str]:
        """불량표 ID로 데이터 파일을 찾습니다"""
        try:
            # DEFECT-YYYYMMDD-HHMMSS... 형식에서 날짜 추출
            date_part = defect_box_id.split('-')[1]  # YYYYMMDD
            formatted_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"  # YYYY-MM-DD

            daily_folder = os.path.join(self.defects_data_folder, formatted_date)
            if not os.path.exists(daily_folder):
                return None

            filepath = os.path.join(daily_folder, f"{defect_box_id}.json")
            if os.path.exists(filepath):
                return filepath

        except (IndexError, ValueError):
            pass

        # 날짜별 폴더에서 찾지 못한 경우 전체 하위 폴더 탐색
        return self._find_file_in_subdirs(self.defects_data_folder, f"{defect_box_id}.json")

    def _handle_defective_overflow(self, defect_barcodes: List[str], overflow: int, session, defect_data: Dict[str, Any]):
        """불량표 스캔 시 초과 수량 처리"""
        items_to_add = len(defect_barcodes) - overflow

        self._prompt_overflow_item_code(overflow, defect_barcodes, items_to_add, session, defect_data)

    def _prompt_overflow_item_code(self, overflow: int, defect_barcodes: List[str], items_to_add: int, session, defect_data: Dict[str, Any]):
        """불량표 초과분 처리를 위한 품목코드 입력 UI"""
        popup = tk.Toplevel(self.root)
        popup.title("불량표 초과분 처리")
        popup.transient(self.root)
        popup.grab_set()
        popup.geometry("600x450")

        main_frame = ttk.Frame(popup, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(main_frame, text="불량표 초과분 처리", font=(self.DEFAULT_FONT, 16, 'bold'))
        title_label.pack(pady=(0, 20))

        info_text = (f"현재 불량 통합 세션 목표 수량: {session.target_quantity}개\n"
                     f"현재 세션에 있는 불량품 수량: {len(session.scanned_defects)}개\n"
                     f"스캔한 불량표의 총 수량: {len(defect_barcodes)}개\n"
                     f"초과되는 수량: {overflow}개")
        info_label = ttk.Label(main_frame, text=info_text, font=(self.DEFAULT_FONT, 12))
        info_label.pack(pady=(0, 20))

        option_label = ttk.Label(main_frame, text="초과된 불량품의 품목코드를 선택하세요:", font=(self.DEFAULT_FONT, 12, 'bold'))
        option_label.pack(pady=(10, 10))

        # 품목코드 선택 UI
        choice_frame = ttk.Frame(main_frame)
        choice_frame.pack(fill=tk.X, pady=10)

        choice = tk.StringVar(value="same_item")

        # 동일 품목 선택 (기본값)
        same_item_radio = ttk.Radiobutton(choice_frame, text=f"동일 품목으로 처리 ({session.item_code})",
                                         variable=choice, value="same_item")
        same_item_radio.pack(anchor=tk.W, pady=5)

        # 다른 품목 선택
        different_item_radio = ttk.Radiobutton(choice_frame, text="다른 품목코드 입력:",
                                              variable=choice, value="different_item")
        different_item_radio.pack(anchor=tk.W, pady=5)

        # 품목코드 입력 필드
        item_code_frame = ttk.Frame(choice_frame)
        item_code_frame.pack(fill=tk.X, pady=5, padx=20)

        item_code_entry = ttk.Entry(item_code_frame, font=(self.DEFAULT_FONT, 12))
        item_code_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 품목코드 검증 버튼
        validate_button = ttk.Button(item_code_frame, text="검증",
                                    command=lambda: self._validate_item_code(item_code_entry.get(), validate_result_label))
        validate_button.pack(side=tk.RIGHT, padx=(5, 0))

        validate_result_label = ttk.Label(choice_frame, text="", font=(self.DEFAULT_FONT, 10))
        validate_result_label.pack(anchor=tk.W, padx=20)

        def on_confirm():
            selected_choice = choice.get()

            if selected_choice == "same_item":
                overflow_item_code = session.item_code
            else:
                overflow_item_code = item_code_entry.get().strip()
                if not overflow_item_code:
                    messagebox.showwarning("입력 오류", "품목코드를 입력해주세요.")
                    return

                # 품목코드 유효성 검사
                if not any(item['Item Code'] == overflow_item_code for item in self.items_data):
                    messagebox.showwarning("품목코드 오류", f"품목코드 '{overflow_item_code}'를 찾을 수 없습니다.")
                    return

            popup.destroy()
            self._split_defective_overflow(defect_barcodes, items_to_add, overflow,
                                         session, defect_data, overflow_item_code)

        # 버튼 프레임
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=20)

        confirm_button = ttk.Button(button_frame, text="확인", command=on_confirm)
        confirm_button.pack(side=tk.RIGHT, padx=(5, 0))

        cancel_button = ttk.Button(button_frame, text="취소", command=popup.destroy)
        cancel_button.pack(side=tk.RIGHT)

        same_item_radio.focus_set()

    def _validate_item_code(self, item_code: str, result_label: ttk.Label):
        """품목코드 유효성 검증"""
        if not item_code:
            result_label.config(text="품목코드를 입력해주세요.", foreground="red")
            return

        matched_item = next((item for item in self.items_data if item['Item Code'] == item_code), None)
        if matched_item:
            result_label.config(text=f"✓ 유효: {matched_item.get('Item Name', '')}", foreground="green")
        else:
            result_label.config(text="✗ 유효하지 않은 품목코드", foreground="red")

    def _split_defective_overflow(self, defect_barcodes: List[str], items_to_add: int, overflow: int,
                                 session, defect_data: Dict[str, Any], overflow_item_code: str):
        """불량표 바코드를 메인/초과분으로 분할 처리"""
        main_barcodes = defect_barcodes[:items_to_add]
        overflow_barcodes = defect_barcodes[items_to_add:]

        # 메인 세션에 추가
        session.scanned_defects.extend(main_barcodes)
        self._update_defective_mode_ui()

        self.show_status_message(f"메인 세션에 {len(main_barcodes)}개 추가, 초과분 {len(overflow_barcodes)}개 처리 중...",
                               self.COLOR_SUCCESS, 3000)

        # 초과분으로 새 불량표 생성
        self._create_new_defective_from_list(overflow_barcodes, defect_data, overflow_item_code)

        # 메인 세션이 목표 수량에 도달했으면 불량표 생성
        if len(session.scanned_defects) >= session.target_quantity:
            self.show_status_message(f"목표 수량({session.target_quantity}개)에 도달했습니다. 불량표를 생성합니다.", self.COLOR_SUCCESS)
            self.generate_defective_label()

    def _create_new_defective_from_list(self, barcodes: List[str], original_defect_data: Dict[str, Any], item_code: str):
        """바코드 리스트로부터 새로운 불량표를 생성하는 헬퍼 함수"""
        if not barcodes:
            return

        self.show_status_message(f"초과분 {len(barcodes)}개로 새 불량표 생성 중...", self.COLOR_DEFECT, 5000)

        now = datetime.datetime.now()
        new_defect_box_id = f"DEFECT-{now.strftime('%Y%m%d-%H%M%S%f')}"

        # 품목 정보 가져오기
        matched_item = next((item for item in self.items_data if item['Item Code'] == item_code), None)
        if not matched_item:
            messagebox.showwarning("품목 오류", f"품목코드 '{item_code}' 정보를 찾을 수 없습니다.")
            return

        new_defect_data = {
            "defect_box_id": new_defect_box_id,
            "creation_date": now.isoformat(),
            "worker": self.worker_name,
            "item_code": item_code,
            "item_name": matched_item.get('Item Name', ''),
            "item_spec": matched_item.get('Spec', ''),
            "quantity": len(barcodes),
            "barcodes": barcodes,
            "created_from_overflow": True,
            "original_defect_box_id": original_defect_data.get('defect_box_id', '')
        }

        try:
            # JSON 데이터 파일 저장
            daily_data_path = self._get_daily_folder_path(self.defects_data_folder)
            filepath = os.path.join(daily_data_path, f"{new_defect_box_id}.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(new_defect_data, f, ensure_ascii=False, indent=4)

            # 불량표 이미지 생성
            image_path = self._generate_defective_label_image(
                defect_box_id=new_defect_box_id,
                item_code=item_code,
                item_name=matched_item.get('Item Name', ''),
                item_spec=matched_item.get('Spec', ''),
                quantity=len(barcodes),
                worker_name=self.worker_name,
                creation_date=now.strftime('%Y-%m-%d %H:%M:%S')
            )

            self._log_event('DEFECT_CREATED_FROM_OVERFLOW', detail=new_defect_data)

            messagebox.showinfo("초과분 불량표 생성 완료",
                              f"초과된 {len(barcodes)}개의 불량품으로\n새로운 불량표를 생성했습니다.\n\n"
                              f"신규 불량표 ID: {new_defect_box_id}\n품목: {matched_item.get('Item Name', '')}")

            if sys.platform == "win32":
                os.startfile(image_path)

        except Exception as e:
            messagebox.showwarning("불량표 생성 실패", f"새 불량표 생성에 실패했습니다: {e}")

    def _update_remnant_list(self):
        for i in self.remnant_items_tree.get_children():
            self.remnant_items_tree.delete(i)
        
        for idx, barcode in enumerate(self.current_remnant_session.scanned_barcodes):
            self.remnant_items_tree.insert('', 'end', values=(idx + 1, barcode))
        
        count = len(self.current_remnant_session.scanned_barcodes)
        self.remnant_count_label.config(text=f"수량: {count}")
    
    def _generate_remnant_label(self):
        if not self.current_remnant_session.scanned_barcodes:
            messagebox.showwarning("오류", "등록된 잔량 품목이 없습니다.", parent=self.root)
            return None

        now = datetime.datetime.now()
        remnant_id = f"SPARE-{now.strftime('%Y%m%d-%H%M%S%f')}"
        remnant_data = {
            "remnant_id": remnant_id,
            "creation_date": now.isoformat(),
            "worker": self.worker_name,
            "item_code": self.current_remnant_session.item_code,
            "item_name": self.current_remnant_session.item_name,
            "item_spec": self.current_remnant_session.item_spec,
            "remnant_barcodes": self.current_remnant_session.scanned_barcodes
        }

        try:
            filepath = os.path.join(self.remnants_folder, f"{remnant_id}.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(remnant_data, f, ensure_ascii=False, indent=4)
            self._log_event('REMNANT_CREATED', detail=remnant_data)
        except Exception as e:
            messagebox.showerror("저장 실패", f"잔량 파일 저장 중 오류 발생: {e}")
            return None
        
        try:
            image_path = self._generate_remnant_label_image(
                remnant_id=remnant_id,
                item_code=remnant_data['item_code'],
                item_name=remnant_data['item_name'],
                item_spec=remnant_data['item_spec'],
                quantity=len(remnant_data['remnant_barcodes']),
                worker_name=self.worker_name,
                creation_date=now.strftime('%Y-%m-%d %H:%M:%S')
            )
            if sys.platform == "win32":
                os.startfile(image_path)
        except Exception as e:
            messagebox.showwarning("이미지 생성 실패", f"라벨 이미지 생성에 실패했습니다: {e}")

        messagebox.showinfo("생성 완료", f"잔량표 생성이 완료되었습니다.\n\n잔량 ID: {remnant_id}\n\n라벨 이미지가 '{self.labels_folder}' 폴더에 저장되었습니다.")
        
        self.toggle_remnant_mode()
        return remnant_id

    def cancel_remnant_creation(self, force_clear=False):
        if not force_clear and self.current_remnant_session.scanned_barcodes:
            if not messagebox.askyesno("취소 확인", "진행중인 잔량 등록을 취소하시겠습니까?"):
                return
        
        self.current_remnant_session = RemnantCreationSession()
        self._update_remnant_list()
        self.remnant_item_label.config(text="등록할 품목: (첫 제품 스캔 대기)")
    
    def _generate_remnant_label_image(self, remnant_id, item_code, item_name, item_spec, quantity, worker_name, creation_date):
        config = {
            'size': (800, 400), 'bg_color': "white", 'text_color': "black", 'padding': 30,
            'font_path': "C:/Windows/Fonts/malgun.ttf",
            'font_sizes': {'title': 48, 'header': 20, 'body': 22, 'quantity': 40, 'unit': 20, 'footer': 16,},
            'qr_code': {'size': 220, 'box_size': 10, 'border': 4,},
            'layout': {
                'title_top_margin': 25, 'header_line_margin': 15, 'content_top_margin': 30,
                'table_line_height': 45, 'table_header_x': 50, 'table_value_x': 170,
                'footer_bottom_margin': 40, 'footer_line_margin': 15,
            }
        }
        W, H = config['size']

        fonts = {}
        try:
            for name, size in config['font_sizes'].items():
                fonts[name] = ImageFont.truetype(config['font_path'], size)
        except IOError:
            messagebox.showwarning("폰트 오류", f"{config['font_path']} 폰트를 찾을 수 없습니다. 기본 폰트로 생성합니다.")
            for name in config['font_sizes']:
                fonts[name] = ImageFont.load_default()

        qr_data = json.dumps({'id': remnant_id, 'code': item_code, 'qty': quantity})
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L,
                                             box_size=config['qr_code']['box_size'], border=config['qr_code']['border'])
        qr.add_data(qr_data)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color=config['text_color'], back_color=config['bg_color']).resize((config['qr_code']['size'], config['qr_code']['size']))

        img = Image.new('RGB', (W, H), config['bg_color'])
        draw = ImageDraw.Draw(img)

        def draw_header(draw_obj):
            title_text = "잔 량 표"
            title_bbox = draw_obj.textbbox((0, 0), title_text, font=fonts['title'])
            title_w, title_h = title_bbox[2] - title_bbox[0], title_bbox[3] - title_bbox[1]
            title_x, title_y = (W - title_w) / 2, config['layout']['title_top_margin']
            draw_obj.text((title_x, title_y), title_text, font=fonts['title'], fill=config['text_color'])
            
            line_y = title_y + title_h + config['layout']['header_line_margin']
            draw_obj.line([(config['padding'], line_y), (W - config['padding'], line_y)], fill=config['text_color'], width=3)
            return line_y

        def draw_info_table(draw_obj, start_y):
            info_items = [
                {'label': "품 목 명", 'value': f": {item_name}"},
                {'label': "품목코드", 'value': f": {item_code}"},
                {'label': "규      격", 'value': f": {item_spec}"},
            ]
            y_pos = start_y + config['layout']['content_top_margin']
            x_header, x_value = config['layout']['table_header_x'], config['layout']['table_value_x']

            for item in info_items:
                draw_obj.text((x_header, y_pos), item['label'], font=fonts['header'], fill=config['text_color'])
                draw_obj.text((x_value, y_pos), item['value'], font=fonts['body'], fill=config['text_color'])
                y_pos += config['layout']['table_line_height']
                
            draw_obj.text((x_header, y_pos), "수      량", font=fonts['header'], fill=config['text_color'])
            draw_obj.text((x_value, y_pos - 10), ": ", font=fonts['quantity'], fill=config['text_color'])
            qty_text = str(quantity)
            colon_w = draw_obj.textlength(": ", font=fonts['quantity'])
            qty_w = draw_obj.textlength(qty_text, font=fonts['quantity'])
            draw_obj.text((x_value + colon_w, y_pos - 10), qty_text, font=fonts['quantity'], fill=config['text_color'], stroke_width=1)
            draw_obj.text((x_value + colon_w + qty_w + 5, y_pos), "EA", font=fonts['unit'], fill=config['text_color'])

        def draw_footer(draw_obj):
            footer_y = H - config['layout']['footer_bottom_margin']
            line_y = footer_y - config['layout']['footer_line_margin']
            draw_obj.line([(config['padding'], line_y), (W - config['padding'], line_y)], fill=config['text_color'], width=1)
            footer_text = f"잔량 ID: {remnant_id}   |   생성일: {creation_date}   |   작업자: {worker_name}"
            draw_obj.text((config['padding'], footer_y), footer_text, font=fonts['footer'], fill=config['text_color'])

        content_start_y = draw_header(draw)
        draw_info_table(draw, content_start_y)
        draw_footer(draw)
        
        qr_x = W - config['qr_code']['size'] - config['padding']
        qr_y = content_start_y + config['layout']['content_top_margin']
        img.paste(qr_img, (qr_x, qr_y))

        daily_labels_path = self._get_daily_folder_path(self.remnant_labels_folder)
        filepath = os.path.join(daily_labels_path, f"잔량표_{remnant_id}.png")
        img.save(filepath)
        return filepath
        
    def _update_all_summaries(self):
        self._update_summary_title()
        self._update_summary_list()
        self._update_avg_time()
        self._update_best_time()
        self._update_center_display()
        
    def _update_summary_title(self):
        if hasattr(self, 'summary_title_label') and self.summary_title_label.winfo_exists():
            rework_text = f" / 리워크 {len(self.reworked_items_today)}개" if self.reworked_items_today else ""
            total_pallets = sum(d.get('pallet_count', 0) for d in self.work_summary.values())
            self.summary_title_label.config(text=f"금일 작업 현황 (총 {total_pallets} 파렛트{rework_text})")

    def _update_summary_list(self):
        if not (hasattr(self, 'good_summary_tree') and self.good_summary_tree.winfo_exists()): return

        for i in self.good_summary_tree.get_children(): self.good_summary_tree.delete(i)
        for i in self.defect_summary_tree.get_children(): self.defect_summary_tree.delete(i)
        
        for item_code, data in sorted(self.work_summary.items()):
            pallet_count = data.get('pallet_count', 0)
            if pallet_count > 0:
                count_display = f"{pallet_count} 파렛트"
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
            tray_size = config.get('inspection.tray_size', 60)
            self.main_progress_bar['maximum'] = tray_size

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
        idle_threshold = config.get('inspection.idle_threshold_sec', 420)
        if (datetime.datetime.now() - self.last_activity_time).total_seconds() > idle_threshold:
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

                # 로그 타입에 따라 저장 위치 결정
                if log_type == 'rework':
                    target_path = self.rework_log_file_path
                elif log_type == 'defect_merge':
                    target_path = self.defect_merge_log_file_path
                else:  # main 및 기타 모든 로그 타입
                    target_path = self.log_file_path

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

        if event_type.startswith('REWORK_'):
            log_type = 'rework'
        elif any(keyword in event_type for keyword in ['DEFECT_MERGE', 'DEFECTIVE_MERGE']):
            log_type = 'defect_merge'
        else:
            log_type = 'main'

        self.log_queue.put((log_type, log_entry))


    def show_status_message(self, message: str, color: Optional[str] = None, duration: int = 4000):
        if not self.root.winfo_exists(): return
        if self.status_message_job: self.root.after_cancel(self.status_message_job)
        self.status_label['text'], self.status_label['fg'] = message, color or self.COLOR_TEXT
        self.status_message_job = self.root.after(duration, self._reset_status_message)
    
    def _reset_status_message(self):
        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            self.status_label['text'], self.status_label['fg'] = "준비", self.COLOR_TEXT
            
    # ===================================================================
    # 현품표 교체 (완료된 작업 대상) 관련 신규/수정된 함수들
    # ===================================================================

    def initiate_master_label_replacement(self):
        """(1) 교체 프로세스를 시작합니다."""
        if self.current_session.master_label_code:
            messagebox.showwarning("작업 중 오류", "진행 중인 작업이 있을 때는 현품표를 교체할 수 없습니다.")
            return

        if self.master_label_replace_state:
            self.cancel_master_label_replacement()
        else:
            self.master_label_replace_state = 'awaiting_old_completed'
            self._log_event('HISTORICAL_REPLACE_START')
            self.show_status_message("교체할 '완료된' 현품표를 스캔하세요.", self.COLOR_PRIMARY)
            self._update_current_item_label()
            self._schedule_focus_return()

    def cancel_master_label_replacement(self):
        """(2) 교체 프로세스를 취소하고 상태와 컨텍스트를 초기화합니다."""
        if self.master_label_replace_state:
            self.master_label_replace_state = None
            self.replacement_context = {}  # 컨텍스트 초기화
            self._log_event('HISTORICAL_REPLACE_CANCEL')
            self.show_status_message("현품표 교체가 취소되었습니다.", self.COLOR_TEXT_SUBTLE)
            self._update_current_item_label()

    def _handle_historical_replacement_scan(self, barcode: str):
        """(3) 교체 프로세스의 초기 스캔(기존/신규 현품표)을 처리합니다."""
        if self.master_label_replace_state == 'awaiting_old_completed':
            self.replacement_context['old_label'] = barcode
            self.master_label_replace_state = 'awaiting_new_replacement'
            self.show_status_message("확인. 적용할 '새로운' 현품표를 스캔하세요.", self.COLOR_SUCCESS)
            self._update_current_item_label()

        elif self.master_label_replace_state == 'awaiting_new_replacement':
            new_data = self._parse_new_format_qr(barcode)
            if not new_data:
                self.show_fullscreen_warning("스캔 오류", "유효한 현품표 QR 형식이 아닙니다.", self.COLOR_DEFECT)
                self.cancel_master_label_replacement()
                return

            if barcode == self.replacement_context.get('old_label'):
                self.show_fullscreen_warning("스캔 오류", "기존과 동일한 현품표입니다.", self.COLOR_DEFECT)
                return

            self.replacement_context['new_label'] = barcode
            self.replacement_context['new_data'] = new_data
            self._perform_historical_master_label_swap()

    def _perform_historical_master_label_swap(self):
        """(4) [수정] 모든 로컬 로그 파일을 검색하여 교체할 기록을 찾습니다."""
        old_label = self.replacement_context.get('old_label')

        # 1. C:\Sync 폴더의 모든 로그 파일 목록을 가져옵니다.
        log_file_pattern = re.compile(r"검사작업이벤트로그_.*_(\d{8})\.csv")
        try:
            all_log_files = [os.path.join(self.save_folder, f) for f in os.listdir(self.save_folder) if log_file_pattern.match(f)]
            # 최신 파일부터 검색하기 위해 역순으로 정렬합니다.
            all_log_files.sort(reverse=True)
        except FileNotFoundError:
            if True:
                messagebox.showerror("오류", f"로그 폴더 '{self.save_folder}'를 찾을 수 없습니다.")
            self.cancel_master_label_replacement()
            return

        # 2. 각 로그 파일을 순회하며 old_label을 찾습니다.
        found_log_info = None
        for log_path in all_log_files:
            found_log_info = self._find_log_in_file(log_path, old_label)
            if found_log_info:
                break # 기록을 찾았으면 검색을 중단합니다.

        # 3. 검색 결과에 따라 다음 단계를 진행합니다.
        if found_log_info:
            self.replacement_context.update(found_log_info) # 찾은 파일 경로, 내용 등을 컨텍스트에 추가
            self._compare_quantities_and_proceed() # 수량 비교 및 추가/제외 스캔 단계로 이동
        else:
            if True:
                messagebox.showwarning("기록 없음", f"모든 로컬 로그 파일에서 해당 현품표({old_label})의 완료 기록을 찾을 수 없습니다.")
            self.cancel_master_label_replacement()


    def _find_log_in_file(self, file_path: str, old_label: str) -> Optional[Dict]:
        """[신규] 지정된 파일에서 old_label에 해당하는 로그를 찾아 관련 정보를 반환합니다."""
        try:
            with open(file_path, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                all_rows = list(reader)
                headers = reader.fieldnames
            
            # 파일의 마지막부터 역순으로 검색하여 가장 최근 기록을 찾습니다.
            for i, row in reversed(list(enumerate(all_rows))):
                if row.get('event') == 'TRAY_COMPLETE':
                    details = json.loads(row.get('details', '{}'))
                    if details.get('master_label_code') == old_label:
                        # 찾았다면 파일 경로, 전체 내용, 헤더, 인덱스, 상세 정보를 반환합니다.
                        return {
                            'found_log_path': file_path,
                            'all_rows': all_rows,
                            'headers': headers,
                            'found_row_index': i,
                            'original_details': details
                        }
        except Exception as e:
            print(f"로그 파일 '{os.path.basename(file_path)}' 검색 중 오류: {e}")
        return None

    def _compare_quantities_and_proceed(self):
        """[신규] 수량을 비교하고 다음 단계를 결정하는 로직입니다."""
        original_details = self.replacement_context['original_details']
        
        old_details_data = self._parse_new_format_qr(original_details.get('master_label_code', ''))
        old_qty = int(old_details_data.get('QT', -1)) if old_details_data else len(original_details.get('scanned_product_barcodes', []))
        new_qty = int(self.replacement_context['new_data'].get('QT', -2))

        self.replacement_context['old_qty'] = old_qty
        self.replacement_context['new_qty'] = new_qty
        
        if old_qty == new_qty:
            self._finalize_replacement()
        elif new_qty > old_qty:
            self.replacement_context['items_needed'] = new_qty - old_qty
            self.replacement_context['additional_items'] = []
            self.master_label_replace_state = 'awaiting_additional_items'
            self._update_current_item_label()
        else: # new_qty < old_qty
            self.replacement_context['items_to_remove_count'] = old_qty - new_qty
            self.replacement_context['removed_items'] = []
            self.master_label_replace_state = 'awaiting_removed_items'
            self._update_current_item_label()

    def _handle_additional_item_scan(self, barcode: str):
        """(5-A) 추가할 제품 스캔을 처리하는 함수"""
        ctx = self.replacement_context
        if barcode in ctx['original_details'].get('scanned_product_barcodes', []):
            self.show_fullscreen_warning("중복 스캔", "이미 기존 작업에 포함된 바코드입니다.", self.COLOR_DEFECT)
            return
        if barcode in ctx.get('additional_items', []):
            self.show_fullscreen_warning("중복 스캔", "이미 추가 목록에 스캔된 바코드입니다.", self.COLOR_DEFECT)
            return

        ctx['additional_items'].append(barcode)
        if self.success_sound: self.success_sound.play()
        
        if len(ctx['additional_items']) >= ctx['items_needed']:
            self._finalize_replacement()
        else:
            self._update_current_item_label()

    def _handle_removed_item_scan(self, barcode: str):
        """(5-B) 제외할 제품 스캔을 처리하는 함수"""
        ctx = self.replacement_context
        if barcode not in ctx['original_details'].get('scanned_product_barcodes', []):
            self.show_fullscreen_warning("스캔 오류", "기존 작업에 포함되지 않은 바코드입니다.", self.COLOR_DEFECT)
            return
        if barcode in ctx.get('removed_items', []):
            self.show_fullscreen_warning("중복 스캔", "이미 제외 목록에 스캔된 바코드입니다.", self.COLOR_DEFECT)
            return

        ctx['removed_items'].append(barcode)
        if self.success_sound: self.success_sound.play()

        if len(ctx['removed_items']) >= ctx['items_to_remove_count']:
            self._finalize_replacement()
        else:
            self._update_current_item_label()

    def _finalize_replacement(self):
        """(6) [수정] 모든 정보가 준비되면 최종적으로 '찾았던' 로그 파일을 수정하고 저장합니다."""
        ctx = self.replacement_context
        idx = ctx['found_row_index']
        details = ctx['original_details']
        
        # --- (기존의 details 딕셔너리 수정 로직은 동일합니다) ---
        details['master_label_code'] = ctx['new_label']
        details['phs'] = ctx['new_data'].get('PHS', details.get('phs'))
        details['outbound_date'] = ctx['new_data'].get('OBD', details.get('outbound_date'))
        details['tray_capacity'] = ctx['new_qty']

        good_barcodes = details.get('scanned_product_barcodes', [])
        if 'additional_items' in ctx:
            good_barcodes.extend(ctx['additional_items'])
        elif 'removed_items' in ctx:
            good_barcodes = [bc for bc in good_barcodes if bc not in ctx['removed_items']]

        details['scanned_product_barcodes'] = good_barcodes
        details['scan_count'] = len(good_barcodes) + len(details.get('defective_product_barcodes', []))
        
        ctx['all_rows'][idx]['details'] = json.dumps(details, ensure_ascii=False)

        # --- (파일 저장 로직 수정) ---
        try:
            # 컨텍스트에 저장된 '찾았던 파일의 경로'에 수정된 전체 내용을 다시 씁니다.
            with open(ctx['found_log_path'], 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=ctx['headers'])
                writer.writeheader()
                writer.writerows(ctx['all_rows'])

            # 성공 처리
            log_details = {'old_master_label': ctx['old_label'], 'new_master_label': ctx['new_label']}
            self._log_event('HISTORICAL_REPLACE_SUCCESS', detail=log_details)

            messagebox.showinfo("교체 완료", "현품표 정보가 성공적으로 교체 및 수정되었습니다.")

            self._load_session_state()
            self._update_all_summaries()

        except Exception as e:
            messagebox.showerror("파일 쓰기 오류", f"수정된 로그 저장 중 오류: {e}")
        finally:
            self.cancel_master_label_replacement()

    def run(self):
        self.root.mainloop()

    # ===================================================================
    # 완료 현황 보기 관련 함수들
    # ===================================================================
    def show_completion_summary_window(self):
        summary_win = tk.Toplevel(self.root)
        summary_win.title("작업 완료 현황")
        summary_win.geometry("1000x700")
        summary_win.configure(bg=self.COLOR_BG)

        top_frame = ttk.Frame(summary_win, style='Sidebar.TFrame', padding=10)
        top_frame.pack(fill=tk.X)
        
        ttk.Label(top_frame, text="완료된 작업 현황", style='Sidebar.TLabel', font=(self.DEFAULT_FONT, 14, 'bold')).pack(side=tk.LEFT, padx=(0, 20))

        today_str = datetime.date.today().strftime('%Y-%m-%d')
        start_date_var = tk.StringVar(value=today_str)
        end_date_var = tk.StringVar(value=today_str)

        ttk.Label(top_frame, text="시작일:", style='Sidebar.TLabel').pack(side=tk.LEFT)
        tk.Entry(top_frame, textvariable=start_date_var, width=12, font=(self.DEFAULT_FONT, 11)).pack(side=tk.LEFT, padx=(5, 10))
        
        ttk.Label(top_frame, text="종료일:", style='Sidebar.TLabel').pack(side=tk.LEFT)
        tk.Entry(top_frame, textvariable=end_date_var, width=12, font=(self.DEFAULT_FONT, 11)).pack(side=tk.LEFT, padx=(5, 15))

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
                start_date = datetime.datetime.strptime(start_date_var.get(), '%Y-%m-%d').date()
                end_date = datetime.datetime.strptime(end_date_var.get(), '%Y-%m-%d').date()
                if start_date > end_date:
                    messagebox.showerror("기간 오류", "시작일은 종료일보다 이전이어야 합니다.", parent=summary_win)
                    return

                summary_data = self._get_completion_summary_data(start_date, end_date)
                self._populate_summary_tree(tree, summary_data)
                self.show_status_message("완료 현황을 새로고침했습니다.", self.COLOR_SUCCESS)
            except ValueError:
                messagebox.showerror("날짜 형식 오류", "날짜를 'YYYY-MM-DD' 형식으로 입력해주세요.", parent=summary_win)
            except Exception as e:
                messagebox.showerror("오류", f"데이터를 불러오는 중 오류가 발생했습니다:\n{e}", parent=summary_win)
        
        ttk.Button(top_frame, text="조회", command=refresh_data, style='Secondary.TButton').pack(side=tk.LEFT)
        
        refresh_data() 
        summary_win.transient(self.root)
        summary_win.grab_set()
        self.root.wait_window(summary_win)

    def _get_completion_summary_data(self, start_date: datetime.date, end_date: datetime.date) -> Dict:
        """지정된 기간의 로그 파일을 읽어 날짜별, 차수별로 완료된 트레이를 집계합니다."""
        summary = {}
        log_file_pattern = re.compile(r"검사작업이벤트로그_.*_(\d{8})\.csv")
        
        try:
            all_log_files = [os.path.join(self.save_folder, f) for f in os.listdir(self.save_folder) if log_file_pattern.match(f)]
        except FileNotFoundError:
            return {}

        for log_path in all_log_files:
            try:
                match = log_file_pattern.search(os.path.basename(log_path))
                if not match: continue
                
                file_date = datetime.datetime.strptime(match.group(1), '%Y%m%d').date()
                if not (start_date <= file_date <= end_date):
                    continue

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

                            if not details.get('is_partial_submission', False):
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
            
    # ===================================================================
    # 작업 현황 상세 보기 관련 신규 함수들
    # ===================================================================
    def _on_summary_double_click(self, event):
        """작업 현황 Treeview에서 항목을 더블클릭했을 때 호출됩니다."""
        tree = event.widget
        if not tree.selection():
            return

        selected_item_id = tree.selection()[0]
        item_values = tree.item(selected_item_id, 'values')

        if item_values and len(item_values) > 1:
            item_code = item_values[1]

            # 불량 현황 트리뷰에서 더블클릭한 경우 불량표 연결
            if tree == self.defect_summary_tree:
                self._show_defect_labels_for_item_window(item_code)
            else:
                # 일반 작업 현황 트리뷰의 경우 기존 라벨 보기
                self._show_labels_for_item_window(item_code)

    def _get_todays_log_details(self) -> tuple[dict, dict]:
        """오늘 로그 파일을 읽어 TRAY_COMPLETE와 교체 이력을 반환합니다."""
        tray_logs = {}
        replacements = {}
        if not self.log_file_path or not os.path.exists(self.log_file_path):
            return tray_logs, replacements

        try:
            with open(self.log_file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    event = row.get('event')
                    details_str = row.get('details', '{}')
                    try:
                        details = json.loads(details_str)
                        if event == 'TRAY_COMPLETE':
                            master_code = details.get('master_label_code')
                            if master_code:
                                tray_logs[master_code] = details
                        elif event == 'HISTORICAL_REPLACE_SUCCESS':
                            old_label = details.get('old_master_label')
                            new_label = details.get('new_master_label')
                            if old_label and new_label:
                                replacements[old_label] = new_label
                    except (json.JSONDecodeError, AttributeError):
                        continue
        except Exception as e:
            print(f"오늘 로그 파일 분석 중 오류 발생: {e}")
            
        return tray_logs, replacements

    def _show_labels_for_item_window(self, item_code: str):
        """특정 품목의 완료된 현품표 목록을 새 창에 표시합니다."""
        logs_win = tk.Toplevel(self.root)
        logs_win.title(f"'{item_code}' 금일 완료 현품표 목록")
        logs_win.geometry("800x500")
        logs_win.transient(self.root)
        logs_win.grab_set()

        tray_logs, replacements = self._get_todays_log_details()
        
        new_to_old_map = {v: k for k, v in replacements.items()}

        item_specific_logs = {code: details for code, details in tray_logs.items() if details.get('item_code') == item_code}

        if not item_specific_logs:
            ttk.Label(logs_win, text="해당 품목의 금일 완료 기록이 없습니다.").pack(pady=20)
            return

        frame = ttk.Frame(logs_win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        cols = ('label_code', 'end_time', 'quantity', 'status')
        tree = ttk.Treeview(frame, columns=cols, show='headings')
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tree.heading('label_code', text='현품표 코드')
        tree.heading('end_time', text='완료 시간')
        tree.heading('quantity', text='수량')
        tree.heading('status', text='교체 여부')

        tree.column('label_code', width=350, anchor='w')
        tree.column('end_time', width=150, anchor='center')
        tree.column('quantity', width=80, anchor='center')
        tree.column('status', width=120, anchor='center')

        sorted_logs = sorted(item_specific_logs.items(), key=lambda item: item[1].get('end_time', ''), reverse=True)

        for code, details in sorted_logs:
            try:
                end_time_dt = datetime.datetime.fromisoformat(details.get('end_time', ''))
                end_time_str = end_time_dt.strftime('%H:%M:%S')
            except (ValueError, TypeError):
                end_time_str = "N/A"
            
            quantity = f"{len(details.get('scanned_product_barcodes', []))} / {details.get('tray_capacity')}"

            status = "X"
            if code in replacements:
                status = "O (교체됨)"
            elif code in new_to_old_map:
                status = f"신규 (이전: ...{new_to_old_map[code][-10:]})"

            tree.insert('', 'end', values=(code, end_time_str, quantity, status), iid=code)

        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscrollcommand=scrollbar.set)
        
        def on_label_double_click(event):
            if not tree.selection():
                return
            selected_iid = tree.selection()[0]
            if selected_iid in item_specific_logs:
                self._show_label_details_window(item_specific_logs[selected_iid])

        tree.bind("<Double-1>", on_label_double_click)

    def _show_defect_labels_for_item_window(self, item_code: str):
        """해당 품목의 불량표 목록을 새 창에 표시합니다."""
        detail_win = tk.Toplevel(self.root)
        detail_win.title(f"불량표 목록 - {item_code}")
        detail_win.geometry("800x600")
        detail_win.transient(self.root)
        detail_win.grab_set()

        main_frame = ttk.Frame(detail_win, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 제목
        title_label = ttk.Label(main_frame, text=f"품목 코드 '{item_code}'의 불량표 목록",
                               style='TLabel', font=(self.DEFAULT_FONT, int(14 * self.scale_factor), 'bold'))
        title_label.pack(pady=(0, 10))

        # 불량표 목록 프레임
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        # 트리뷰 생성
        columns = ('defect_id', 'creation_date', 'quantity', 'worker')
        tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)

        tree.heading('defect_id', text='불량상자 ID')
        tree.heading('creation_date', text='생성일시')
        tree.heading('quantity', text='수량')
        tree.heading('worker', text='작업자')

        tree.column('defect_id', width=200, anchor='center')
        tree.column('creation_date', width=150, anchor='center')
        tree.column('quantity', width=80, anchor='center')
        tree.column('worker', width=100, anchor='center')

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 스크롤바
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscrollcommand=scrollbar.set)

        # 불량표 데이터 로드
        defect_data = self._load_defect_labels_for_item(item_code)

        if not defect_data:
            # 데이터가 없는 경우
            tree.insert('', 'end', values=('데이터 없음', '해당 품목의 불량표가 없습니다', '', ''))
        else:
            # 데이터가 있는 경우 삽입
            for data in defect_data:
                tree.insert('', 'end', values=(
                    data.get('defect_box_id', 'N/A'),
                    data.get('creation_date', 'N/A'),
                    f"{data.get('quantity', 0)}개",
                    data.get('worker', 'N/A')
                ), tags=(data.get('file_path', ''),))

        # 버튼 프레임
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        def open_defect_label():
            """선택된 불량표를 열어봅니다."""
            if not tree.selection():
                messagebox.showwarning("선택 오류", "불량표를 선택해주세요.")
                return

            selected_item = tree.selection()[0]
            tags = tree.item(selected_item, 'tags')

            if tags and tags[0]:
                file_path = tags[0]
                try:
                    # JSON 파일에서 데이터 로드
                    with open(file_path, 'r', encoding='utf-8') as f:
                        defect_data = json.load(f)

                    # 불량표 상세 정보 창 표시
                    self._show_defect_label_details_window(defect_data, file_path)

                except Exception as e:
                    messagebox.showerror("파일 오류", f"불량표 파일을 열 수 없습니다: {e}")

        def open_defect_image():
            """선택된 불량표 이미지를 엽니다."""
            if not tree.selection():
                messagebox.showwarning("선택 오류", "불량표를 선택해주세요.")
                return

            selected_item = tree.selection()[0]
            values = tree.item(selected_item, 'values')
            defect_id = values[0]

            # 이미지 파일 경로 생성
            image_path = os.path.join(self.labels_folder, f"불량표_{defect_id}.png")

            if os.path.exists(image_path):
                try:
                    if sys.platform == "win32":
                        os.startfile(image_path)
                    else:
                        subprocess.run(['xdg-open', image_path])
                except Exception as e:
                    messagebox.showerror("파일 열기 오류", f"이미지를 열 수 없습니다: {e}")
            else:
                messagebox.showwarning("파일 없음", "해당 불량표 이미지 파일을 찾을 수 없습니다.")

        # 버튼들
        ttk.Button(button_frame, text="불량표 상세보기", command=open_defect_label).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="불량표 이미지 열기", command=open_defect_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="닫기", command=detail_win.destroy).pack(side=tk.RIGHT)

        # 더블클릭으로 상세보기
        tree.bind("<Double-1>", lambda e: open_defect_label())

    def _load_defect_labels_for_item(self, item_code: str) -> List[Dict]:
        """해당 품목의 불량표 데이터를 로드합니다."""
        defect_data = []

        if not hasattr(self, 'defects_data_folder') or not os.path.exists(self.defects_data_folder):
            return defect_data

        try:
            # 오늘 날짜의 폴더에서 검색
            today = datetime.datetime.now()
            daily_folder = self._get_daily_folder_path(self.defects_data_folder)

            if os.path.exists(daily_folder):
                for filename in os.listdir(daily_folder):
                    if filename.endswith('.json') and filename.startswith('DEFECT-'):
                        file_path = os.path.join(daily_folder, filename)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)

                            # 해당 품목의 불량표인지 확인
                            if data.get('item_code') == item_code:
                                # 생성일시 포맷팅
                                creation_date = data.get('creation_date', '')
                                if creation_date:
                                    try:
                                        dt = datetime.datetime.fromisoformat(creation_date.replace('Z', '+00:00'))
                                        data['creation_date'] = dt.strftime('%Y-%m-%d %H:%M:%S')
                                    except:
                                        pass

                                data['file_path'] = file_path
                                defect_data.append(data)

                        except Exception as e:
                            print(f"불량표 파일 로드 오류 ({filename}): {e}")
                            continue

            # 생성일시 기준 내림차순 정렬 (최신순)
            defect_data.sort(key=lambda x: x.get('creation_date', ''), reverse=True)

        except Exception as e:
            print(f"불량표 데이터 로드 오류: {e}")

        return defect_data

    def _show_defect_label_details_window(self, defect_data: Dict, file_path: str):
        """불량표의 상세 정보를 새 창에 표시합니다."""
        detail_win = tk.Toplevel(self.root)
        detail_win.title(f"불량표 상세 정보 - {defect_data.get('defect_box_id', 'N/A')}")
        detail_win.geometry("700x650")
        detail_win.transient(self.root)
        detail_win.grab_set()

        main_frame = ttk.Frame(detail_win, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.grid_columnconfigure(1, weight=1)

        # 기본 정보
        info_map = [
            ("불량상자 ID:", defect_data.get('defect_box_id', 'N/A')),
            ("품목명:", defect_data.get('item_name', 'N/A')),
            ("품목 코드:", defect_data.get('item_code', 'N/A')),
            ("품목 규격:", defect_data.get('item_spec', 'N/A')),
            ("생성일시:", defect_data.get('creation_date', 'N/A')),
            ("수량:", f"{defect_data.get('quantity', 0)}개"),
            ("작업자:", defect_data.get('worker', 'N/A')),
            ("파일 경로:", file_path),
        ]

        for i, (label, value) in enumerate(info_map):
            ttk.Label(main_frame, text=label, style='TLabel', font=(self.DEFAULT_FONT, int(10 * self.scale_factor), 'bold')).grid(row=i, column=0, sticky='w', pady=2, padx=(0, 10))
            ttk.Label(main_frame, text=str(value), style='TLabel').grid(row=i, column=1, sticky='w', pady=2)

        # 불량품 바코드 목록
        ttk.Label(main_frame, text="불량품 바코드 목록:", style='TLabel', font=(self.DEFAULT_FONT, int(10 * self.scale_factor), 'bold')).grid(row=len(info_map), column=0, sticky='nw', pady=(15, 5), padx=(0, 10))

        # 바코드 리스트박스
        listbox_frame = ttk.Frame(main_frame)
        listbox_frame.grid(row=len(info_map), column=1, sticky='nsew', pady=(15, 0))
        listbox_frame.grid_columnconfigure(0, weight=1)
        listbox_frame.grid_rowconfigure(0, weight=1)

        barcodes_listbox = tk.Listbox(listbox_frame, height=12, font=(self.DEFAULT_FONT, int(9 * self.scale_factor)))
        barcodes_listbox.grid(row=0, column=0, sticky='nsew')

        # 바코드 데이터 추가
        barcodes = defect_data.get('barcodes', [])
        for i, barcode in enumerate(barcodes, 1):
            barcodes_listbox.insert(tk.END, f"{i:2d}. {barcode}")

        # 스크롤바
        barcode_scrollbar = ttk.Scrollbar(listbox_frame, orient='vertical', command=barcodes_listbox.yview)
        barcode_scrollbar.grid(row=0, column=1, sticky='ns')
        barcodes_listbox.configure(yscrollcommand=barcode_scrollbar.set)

        # 하단 버튼
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=len(info_map)+1, column=0, columnspan=2, sticky='ew', pady=(15, 0))

        def open_image():
            """불량표 이미지를 엽니다."""
            defect_id = defect_data.get('defect_box_id', '')
            image_path = os.path.join(self.labels_folder, f"불량표_{defect_id}.png")

            if os.path.exists(image_path):
                try:
                    if sys.platform == "win32":
                        os.startfile(image_path)
                    else:
                        subprocess.run(['xdg-open', image_path])
                except Exception as e:
                    messagebox.showerror("파일 열기 오류", f"이미지를 열 수 없습니다: {e}")
            else:
                messagebox.showwarning("파일 없음", "해당 불량표 이미지 파일을 찾을 수 없습니다.")

        ttk.Button(button_frame, text="불량표 이미지 열기", command=open_image).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="닫기", command=detail_win.destroy).pack(side=tk.RIGHT)

        # 그리드 가중치 설정
        main_frame.grid_rowconfigure(len(info_map), weight=1)

    def _show_label_details_window(self, details: Dict):
        """현품표의 상세 정보를 새 창에 표시합니다."""
        detail_win = tk.Toplevel(self.root)
        detail_win.title("현품표 상세 정보")
        detail_win.geometry("700x600")
        detail_win.transient(self.root)
        detail_win.grab_set()

        main_frame = ttk.Frame(detail_win, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.grid_columnconfigure(1, weight=1)

        info_map = [
            ("현품표 코드:", details.get('master_label_code', 'N/A')),
            ("품목명:", details.get('item_name', 'N/A')),
            ("품목 코드:", details.get('item_code', 'N/A')),
            ("완료 시간:", details.get('end_time', 'N/A')),
            ("총 수량:", f"{details.get('scan_count', 0)} / {details.get('tray_capacity', 0)}"),
            ("양품 / 불량:", f"{len(details.get('scanned_product_barcodes', []))} / {len(details.get('defective_product_barcodes', []))}"),
            ("작업 시간:", f"{details.get('work_time_sec', 0.0):.1f} 초"),
        ]

        for i, (label, value) in enumerate(info_map):
            ttk.Label(main_frame, text=label, font=(self.DEFAULT_FONT, 10, 'bold')).grid(row=i, column=0, sticky='w', pady=2)
            ttk.Label(main_frame, text=value, wraplength=500).grid(row=i, column=1, sticky='w', pady=2)

        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=len(info_map), column=0, columnspan=2, sticky='nsew', pady=(15, 0))
        main_frame.grid_rowconfigure(len(info_map), weight=1)

        good_items = details.get('scanned_product_barcodes', [])
        defect_items = details.get('defective_product_barcodes', [])

        good_frame = ttk.Frame(notebook, padding=5)
        defect_frame = ttk.Frame(notebook, padding=5)
        notebook.add(good_frame, text=f"양품 목록 ({len(good_items)}개)")
        notebook.add(defect_frame, text=f"불량 목록 ({len(defect_items)}개)")

        good_text = tk.Text(good_frame, wrap=tk.WORD, font=(self.DEFAULT_FONT, 10), height=10)
        good_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        good_scroll = ttk.Scrollbar(good_frame, orient='vertical', command=good_text.yview)
        good_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        good_text.config(yscrollcommand=good_scroll.set, state=tk.DISABLED)
        good_text.config(state=tk.NORMAL)
        good_text.insert(tk.END, "\n".join(good_items))
        good_text.config(state=tk.DISABLED)
        
        defect_text = tk.Text(defect_frame, wrap=tk.WORD, font=(self.DEFAULT_FONT, 10), height=10, bg="#FFF0F0")
        defect_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        defect_scroll = ttk.Scrollbar(defect_frame, orient='vertical', command=defect_text.yview)
        defect_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        defect_text.config(yscrollcommand=defect_scroll.set, state=tk.DISABLED)
        defect_text.config(state=tk.NORMAL)
        defect_text.insert(tk.END, "\n".join(defect_items))
        defect_text.config(state=tk.DISABLED)


if __name__ == "__main__":
    app = InspectionProgram()
    threading.Thread(target=check_and_apply_updates, args=(app,), daemon=True).start()
    app.run()
