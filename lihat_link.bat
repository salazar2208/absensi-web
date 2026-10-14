@echo off
REM UNTUK APA: tampilkan link publik + alamat WiFi saat ini. 2x klik kapan saja.
cd /d "%~dp0"
echo === LINK PUBLIK (buka dari mana saja, semua tombol work) ===
powershell -NoProfile -Command "$m=[regex]::Matches((Get-Content 'tunnel.log' -Raw -ErrorAction SilentlyContinue), 'https://[a-z0-9-]+\.trycloudflare\.com'); if($m.Count){$m[$m.Count-1].Value} else {'(belum ada - 2x klik online.bat dulu, tunggu 20 detik, lalu 2x klik file ini lagi)'}"
echo.
echo === ALAMAT WIFI KANTOR (satu WiFi saja, GPS HP terbatas) ===
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  set "ip=%%a"
  call echo    http://%%ip: =%%:5000
)
echo.
echo Login: admin / admin123
echo (Link publik GANTI tiap online.bat dijalankan ulang.)
pause
