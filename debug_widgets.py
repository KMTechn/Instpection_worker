#!/usr/bin/env python3
"""
Debug widget structure to find the scan entry
"""
import sys
import os
import time
import tkinter as tk

# Add the project root to the path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def debug_widget_structure():
    """Debug widget structure to find scan entry"""
    print("위젯 구조 디버깅")

    from Inspection_worker import InspectionProgram

    def run_app():
        app = InspectionProgram()
        root = app.root

        # Wait for initialization
        time.sleep(3)

        print("애플리케이션 초기화 완료")

        try:
            # Set worker name
            app.worker_name = "TEST"
            if hasattr(app, 'current_mode'):
                app.current_mode = 'standard'
            if hasattr(app, '_apply_mode_ui'):
                app._apply_mode_ui()
            root.update()

            print(f"현재 모드: {getattr(app, 'current_mode', 'unknown')}")

            # Debug scan entry attributes
            print("\n=== 스캔 엔트리 관련 속성들 ===")
            entry_attrs = [attr for attr in dir(app) if 'entry' in attr.lower()]
            for attr in entry_attrs:
                value = getattr(app, attr, None)
                print(f"{attr}: {type(value)} - {value}")

            print("\n=== scan_entry 상세 정보 ===")
            if hasattr(app, 'scan_entry') and app.scan_entry:
                scan_entry = app.scan_entry
                print(f"타입: {type(scan_entry)}")
                print(f"위젯 존재: {scan_entry.winfo_exists()}")
                print(f"위젯 매니저: {scan_entry.winfo_manager()}")
                print(f"위젯 상태: {scan_entry['state'] if hasattr(scan_entry, '__getitem__') else 'unknown'}")

                # Try to get current value
                try:
                    current_val = scan_entry.get()
                    print(f"현재 값: '{current_val}'")
                except Exception as e:
                    print(f"값 읽기 실패: {e}")

                # Test input
                print("\n테스트 입력 시도...")
                test_text = "TEST123"
                try:
                    scan_entry.delete(0, tk.END)
                    scan_entry.insert(0, test_text)
                    actual_val = scan_entry.get()
                    print(f"입력 테스트: 예상='{test_text}', 실제='{actual_val}'")

                    if actual_val == test_text:
                        print("입력 성공! Enter 키 이벤트 테스트...")
                        scan_entry.event_generate('<Return>')
                        print("Enter 키 이벤트 전송됨")
                    else:
                        print("입력 실패")
                except Exception as e:
                    print(f"입력 테스트 실패: {e}")

            else:
                print("scan_entry가 없거나 None입니다")

            print("\n=== 모든 Entry 위젯 찾기 ===")
            all_entries = []

            def find_entries(widget):
                if isinstance(widget, tk.Entry):
                    all_entries.append(widget)
                for child in widget.winfo_children():
                    find_entries(child)

            find_entries(root)
            print(f"총 {len(all_entries)}개의 Entry 위젯 발견:")
            for i, entry in enumerate(all_entries):
                try:
                    print(f"  Entry {i}: 값='{entry.get()}', 상태='{entry['state']}'")
                except:
                    print(f"  Entry {i}: 접근 불가")

        except Exception as e:
            print(f"디버깅 중 오류: {e}")
            import traceback
            traceback.print_exc()

        # Keep running for manual testing
        print("\n30초간 실행됩니다. 수동으로 테스트 가능합니다.")
        root.after(30000, root.quit)
        root.mainloop()

    return run_app()

if __name__ == "__main__":
    try:
        debug_widget_structure()
        print("디버깅 완료")
    except Exception as e:
        print(f"디버깅 실패: {e}")
        import traceback
        traceback.print_exc()