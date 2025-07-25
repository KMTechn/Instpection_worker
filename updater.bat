@echo off
chcp 65001 > nul
echo.
echo ==========================================================
echo  프로그램을 업데이트합니다. 이 창을 닫지 마세요.
echo ==========================================================
echo.
echo 잠시 후 프로그램이 자동으로 종료됩니다...
timeout /t 3 /nobreak > nul
taskkill /F /IM "python.exe" > nul
echo.
echo 기존 파일을 백업하고 새 파일로 교체합니다...
xcopy "C:\Users\repla\AppData\Local\Temp\temp_update\Inspection_worker" "c:\KMTECH Program\Instpection_worker.py" /E /H /C /I /Y > nul
echo.
echo 임시 업데이트 파일을 삭제합니다...
rmdir /s /q "C:\Users\repla\AppData\Local\Temp\temp_update"
echo.
echo ========================================
echo  업데이트 완료!
echo ========================================
echo.
echo 3초 후에 프로그램을 다시 시작합니다.
timeout /t 3 /nobreak > nul
start "" "c:\KMTECH Program\Instpection_worker.py\python.exe"
del "%~f0"
            