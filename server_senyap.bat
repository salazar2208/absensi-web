@echo off
REM UNTUK APA: jalankan server tanpa jendela (dipakai penjaga oto_jalan.vbs).
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "app.py"
) else if exist ".venv\Scripts\python.exe" (
  start "" ".venv\Scripts\python.exe" "app.py"
) else (
  start "" "pythonw.exe" "app.py"
)
