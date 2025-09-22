"""로깅 유틸리티 모듈"""

import csv
import json
import datetime
import os
import queue
import threading
from typing import Dict, Any, Optional, List


class EventLogger:
    """이벤트 로깅을 담당하는 클래스"""

    def __init__(self, log_file_path: str):
        self.log_file_path = log_file_path
        self.log_queue = queue.Queue()
        self.log_writer_running = True
        self._start_log_writer_thread()

    def _start_log_writer_thread(self):
        """로그 작성 스레드를 시작합니다."""
        log_thread = threading.Thread(target=self._event_log_writer, daemon=True)
        log_thread.start()

    def _event_log_writer(self):
        """이벤트 로그를 파일에 작성하는 스레드 함수"""
        while self.log_writer_running:
            try:
                log_entry = self.log_queue.get(timeout=1)
                if log_entry is None:
                    break

                file_exists = os.path.exists(self.log_file_path)
                with open(self.log_file_path, mode='a', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['timestamp', 'event_type', 'detail']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                    if not file_exists:
                        writer.writeheader()

                    writer.writerow(log_entry)
                    csvfile.flush()

                self.log_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                print(f"로그 작성 오류: {e}")

    def log_event(self, event_type: str, detail: Optional[Dict] = None):
        """이벤트를 로그에 기록합니다."""
        log_entry = {
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': event_type,
            'detail': json.dumps(detail, ensure_ascii=False) if detail else ""
        }
        self.log_queue.put(log_entry)

    def find_log_in_file(self, file_path: str, search_key: str) -> Optional[Dict]:
        """파일에서 특정 로그를 찾습니다."""
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, mode='r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if search_key in row.get('detail', ''):
                        try:
                            detail = json.loads(row['detail']) if row['detail'] else {}
                            return {
                                'timestamp': row['timestamp'],
                                'event_type': row['event_type'],
                                'detail': detail
                            }
                        except json.JSONDecodeError:
                            continue
            return None
        except Exception as e:
            print(f"로그 파일 읽기 오류: {e}")
            return None

    def get_todays_logs(self) -> List[Dict[str, Any]]:
        """오늘 날짜의 모든 로그를 반환합니다."""
        today = datetime.date.today().strftime('%Y-%m-%d')
        logs = []

        if not os.path.exists(self.log_file_path):
            return logs

        try:
            with open(self.log_file_path, mode='r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if row['timestamp'].startswith(today):
                        try:
                            detail = json.loads(row['detail']) if row['detail'] else {}
                            logs.append({
                                'timestamp': row['timestamp'],
                                'event_type': row['event_type'],
                                'detail': detail
                            })
                        except json.JSONDecodeError:
                            continue
            return logs
        except Exception as e:
            print(f"로그 파일 읽기 오류: {e}")
            return logs

    def stop_logger(self):
        """로깅을 중지합니다."""
        self.log_writer_running = False
        self.log_queue.put(None)  # 종료 신호