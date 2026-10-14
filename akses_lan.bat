@echo off
REM UNTUK APA: jalankan web agar bisa dibuka HP/komputer lain satu WiFi kantor.
REM 1) 2x klik file ini di komputer yang ada file absensi_web.
REM 2) Catat alamat http://192.168.x.x:5000 yang tampil, bagikan ke yang lain.
REM 3) Komputer ini jangan dimatikan selama web dipakai.
REM CATATAN: via WiFi http saja, tombol GPS Chrome di-HP DIBLOKIR browser.
REM Untuk semua tools work penuh (termasuk GPS), pakai online.bat (link https).
cd /d "%~dp0"
if not exist .venv (python -m venv .venv && .venv\Scripts\pip install -r requirements.txt)
netsh advfirewall firewall delete rule name="Absensi Web" >nul 2>&1
netsh advfirewall firewall add rule name="Absensi Web" dir=in action=allow protocol=TCP localport=5000 >nul 2>&1
echo.
echo ============================================================
echo  BAGIKAN ALAMAT INI ke HP/komputer lain (satu WiFi):
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  set "ip=%%a"
  call echo    http://%%ip: =%%:5000
)
echo ============================================================
echo  Login: admin / admin123
echo  Kalau HP lain tidak bisa dibuka, klik kanan file ini
echo  -^> Run as Administrator 1x untuk buka port 5000.
echo  BUTUH GPS + AKSES DARI LUAR WIFI? Tutup ini, 2x klik online.bat
echo ============================================================
echo.
.venv\Scripts\python app.py
pause
