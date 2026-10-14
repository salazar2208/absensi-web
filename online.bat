@echo off
REM UNTUK APA: 1x klik -> web absen ONLINE, bisa dibuka ORANG LAIN dari mana saja via link https://...
REM Semua tombol & tools tetap work (HTTPS, bukan http WiFi saja).
REM Syarat: laptop ini + WiFi tetap NYALA selama dipakai.
cd /d "%~dp0"

echo [1/4] Menutup tunnel lama yang mati...
taskkill /F /IM cloudflared.exe 2>nul >nul
timeout /t 2 /nobreak >nul
if exist tunnel.log del tunnel.log

echo [2/4] Menyiapkan Python...
if not exist .venv (python -m venv .venv && .venv\Scripts\pip install -r requirements.txt)
if not exist .venv\Scripts\python.exe (
  echo GAGAL: .venv rusak. Hapus folder .venv lalu 2x klik lagi file ini.
  pause
  exit /b 1
)

echo [3/4] Membuka port firewall (sekali saja, abaikan bila gagal)...
netsh advfirewall firewall delete rule name="Absensi Web" >nul 2>&1
netsh advfirewall firewall add rule name="Absensi Web" dir=in action=allow protocol=TCP localport=5000 >nul 2>&1

echo [4/4] Menyalakan server absen...
REM Matikan server lama di port 5000 biar tidak dobel
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do taskkill /F /PID %%p 2>nul >nul
timeout /t 1 /nobreak >nul
start "Absensi Server - JANGAN DITUTUP" .venv\Scripts\python app.py

echo Menunggu server siap...
for /L %%i in (1,1,30) do (
  .venv\Scripts\python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/login', timeout=2); print('siap')" 2>nul | findstr siap >nul
  if not errorlevel 1 goto server_ok
  timeout /t 1 /nobreak >nul
)
:server_ok
echo Server jalan. Menyalakan link publik...
echo.
echo ============================================================
echo  TUNGGU 10-20 DETIK, lalu CATAT LINK https://... DI BAWAH:
echo  Link itu yang dibagikan ke orang lain (WA/QR).
echo  Laptop ini JANGAN dimatikan / sleep selama dipakai.
echo  GPS & semua tombol HANYA work penuh via link https ini.
echo  (Via http WiFi saja, GPS Chrome diblokir browser.)
echo ============================================================
echo.
REM --protocol http2 = anti putus di WiFi kantor (QUIC/UDP sering diblokir).
REM Link GANTI tiap file ini dijalankan ulang. Cek link kapan saja via lihat_link.bat
cloudflared.exe tunnel --url http://localhost:5000 --protocol http2 --logfile tunnel.log --loglevel info
pause
