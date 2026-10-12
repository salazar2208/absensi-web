@echo off
REM UNTUK APA: tampilkan link publik + alamat WiFi saat ini. 2x klik kapan saja.
cd /d "%~dp0"
echo === LINK PUBLIK (buka dari mana saja) ===
powershell -NoProfile -Command "Select-String -Path 'tunnel.log' -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -Last 1 | ForEach-Object { $_.Matches.Value }"
echo.
echo === ALAMAT WIFI KANTOR (satu WiFi saja) ===
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  set "ip=%%a"
  call echo    http://%%ip: =%%:5000
)
echo.
echo (Link publik GANTI tiap komputer restart. Habis restart, 2x klik file ini untuk link baru.)
pause
