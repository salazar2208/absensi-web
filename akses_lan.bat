@echo off
REM UNTUK APA: jalankan web agar bisa dibuka HP/komputer lain satu WiFi kantor.
REM 1) 2x klik file ini di komputer yang adayarn file absensi_web.
REM 2) Catat alamat http://192.168.x.x:5000 yang tampil, bagikan ke yang lain.
REM 3) Komputer ini jangan dimatikan selama web dipakai.
cd /d "%~dp0"
if not exist .venv (python -m venv .venv && .venv\Scripts\pip install -r requirements.txt)
echo.
echo ============================================================
echo  BAGIKAN ALAMAT INI ke HP/komputer lain (satu WiFi):
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  set "ip=%%a"
  call echo    http://%%ip: =%%:5000
)
echo ============================================================
echo  Kalau dari HP lain tidak bisa dibuka: jalankan 1x sebagai
echo  Administrator perintah ini untuk buka port 5000:
echo    netsh advfirewall firewall add rule name="Absensi Web" dir=in action=allow protocol=TCP localport=5000
echo ============================================================
echo.
.venv\Scripts\python app.py
pause
