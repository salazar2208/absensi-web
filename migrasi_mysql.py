"""SEKALI PAKAI: pindahkan isi absensi.db (SQLite) ke MySQL Railway.

Cara pakai (dari folder absensi_web):
  1. Di Railway: service MySQL -> tab Connect/Networking -> copy PUBLIC URL
     (bentuk mysql://user:pass@host:port/railway).
  2. Di laptop, jalankan salah satu:
       set MYSQL_URL=mysql://... (Windows CMD)
       $env:MYSQL_URL='mysql://...' (PowerShell)
       python migrasi_mysql.py "C:\\Users\\rafab\\Downloads\\absensi_backup_XXXX.db"
     Tanpa argumen: memakai absensi.db di folder ini.
  3. Skrip membuat skema MySQL dulu (pakai kode aplikasi), lalu menyalin
     semua tabel. Aman diulang (INSERT IGNORE, tidak menggandakan).

Butuh: pip install pymysql
"""
import os
import sqlite3
import sys

TABEL = ("pegawai", "mesin", "users", "absen", "pengajuan")  # induk dulu (FK)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "absensi.db")
    if not os.path.exists(src):
        print("Batal: file SQLite tidak ada:", src)
        raise SystemExit(1)
    if not (os.environ.get("MYSQL_URL") or "").strip():
        print("Batal: set MYSQL_URL dulu ke PUBLIC URL MySQL Railway.")
        raise SystemExit(1)
    try:
        import pymysql
    except ImportError:
        print("Batal: pymysql belum terpasang. Jalankan: pip install pymysql")
        raise SystemExit(1)

    # 1. pastikan skema MySQL sudah ada (pakai kode aplikasi sendiri)
    import database
    c = database.db()
    c.close()
    print("Skema MySQL siap.")

    # 2. baca SQLite
    lite = sqlite3.connect(src)
    lite.row_factory = sqlite3.Row
    data = {}
    for t in TABEL:
        try:
            data[t] = [dict(r) for r in lite.execute("SELECT * FROM %s" % t).fetchall()]
        except Exception as e:
            print("Lewati tabel %s (%s)" % (t, e))
            data[t] = []
    lite.close()

    # 3. tulis ke MySQL
    from urllib.parse import urlparse, unquote
    u = urlparse(os.environ["MYSQL_URL"])
    raw = pymysql.connect(host=u.hostname, port=u.port or 3306,
                          user=unquote(u.username or ""), password=unquote(u.password or ""),
                          database=(u.path or "/").lstrip("/") or "railway",
                          charset="utf8mb4", connect_timeout=15)
    cur = raw.cursor()
    total = 0
    for t in TABEL:
        rows = data.get(t, [])
        if not rows:
            print("%-10s: kosong, dilewati" % t)
            continue
        kolom = list(rows[0].keys())
        sql = "INSERT IGNORE INTO %s (%s) VALUES (%s)" % (
            t, ", ".join(kolom), ", ".join(["%s"] * len(kolom)))
        n = cur.executemany(sql, [[r[k] for k in kolom] for r in rows])
        print("%-10s: %d baris dibaca, %d baru masuk" % (t, len(rows), n or 0))
        total += n or 0
    raw.commit()
    raw.close()
    print("Selesai: %d baris baru di MySQL." % total)


if __name__ == "__main__":
    main()
