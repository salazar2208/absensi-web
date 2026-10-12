"""UNTUK APA: ganti password akun (wajib sebelum web dibuka ke jaringan).
Cara pakai (dari folder absensi_web):
    .venv\\Scripts\\python ganti_password.py
Lalu ketik username + password baru 2x. Password lama tidak perlu."""
import getpass
from werkzeug.security import generate_password_hash
from database import db

print("=== Ganti password akun ===")
username = input("Username (cth: admin): ").strip()
if not username:
    print("Batal: username kosong.")
    raise SystemExit(1)
baru1 = getpass.getpass("Password baru (min 6 karakter): ")
baru2 = getpass.getpass("Ulangi password baru: ")
if baru1 != baru2:
    print("Batal: password tidak sama.")
    raise SystemExit(1)
if len(baru1) < 6:
    print("Batal: password minimal 6 karakter.")
    raise SystemExit(1)

c = db()
r = c.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
if not r:
    c.close()
    print(f"Batal: username '{username}' tidak ada.")
    raise SystemExit(1)
c.execute("UPDATE users SET password_hash=? WHERE username=?",
          (generate_password_hash(baru1), username))
c.commit()
c.close()
print(f"Berhasil: password '{username}' sudah diganti. Jangan ditempel di layar login.")
