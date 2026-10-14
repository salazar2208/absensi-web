' UNTUK APA: penjaga otomatis. Tiap 60 detik pastikan server + tunnel hidup,
' bila mati langsung dinyalakan lagi tanpa jendela/terminal. Dijalankan
' otomatis tiap komputer masuk Windows (via Startup) + bisa 2x klik manual.
Dim sh, wmi, folder
folder = "C:\Users\rafab\absensi_web\"
Set sh = CreateObject("WScript.Shell")
Set wmi = GetObject("winmgmts:\\.\root\cimv2")
Do
  Dim adaServer, adaTunnel, p
  adaServer = False
  adaTunnel = False
  For Each p In wmi.ExecQuery("SELECT CommandLine FROM Win32_Process WHERE Name='pythonw.exe'")
    If InStr(p.CommandLine, "app.py") > 0 Then adaServer = True
  Next
  For Each p In wmi.ExecQuery("SELECT Name FROM Win32_Process WHERE Name='cloudflared.exe'")
    adaTunnel = True
  Next
  If Not adaServer Then sh.Run """" & folder & "server_senyap.bat""", 0, False
  If Not adaTunnel Then sh.Run """" & folder & "cloudflared.exe"" tunnel --url http://localhost:5000 --protocol http2 --logfile """ & folder & "tunnel.log"" --loglevel info", 0, False
  WScript.Sleep 60000
Loop
