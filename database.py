"""UNTUK APA: urusan database saja.
- buka koneksi (db())
- bikin tabel kalau belum ada (pegawai, absen, mesin fingerprint, pengajuan, users)
- migrasi otomatis dari skema lama (user_id -> nik)
Jangan taruh logika laporan di sini."""
import sqlite3
from werkzeug.security import generate_password_hash
from config import DB


def _kolom(c, tabel):
    try:
        return {r[1] for r in c.execute(f"PRAGMA table_info({tabel})").fetchall()}
    except Exception:
        return set()


def _tabel_ada(c, nama):
    return any(r[0] == nama for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall())


def simpan_pegawai(c, nik, nama="", bagian=""):
    """Upsert 1 pegawai. Hanya kolom yang diisi yang ditulis,
    yang kosong tidak menimpa data lama."""
    nama = (nama or "").strip()[:100]
    bagian = (bagian or "").strip()[:60]
    if nama and bagian:
        c.execute("INSERT INTO pegawai(nik,nama,bagian) VALUES(?,?,?) "
                  "ON CONFLICT(nik) DO UPDATE SET nama=excluded.nama, bagian=excluded.bagian",
                  (nik, nama, bagian))
    elif nama:
        c.execute("INSERT INTO pegawai(nik,nama) VALUES(?,?) "
                  "ON CONFLICT(nik) DO UPDATE SET nama=excluded.nama",
                  (nik, nama))
    elif bagian:
        c.execute("INSERT INTO pegawai(nik,nama,bagian) VALUES(?,?,?) "
                  "ON CONFLICT(nik) DO UPDATE SET bagian=excluded.bagian",
                  (nik, nik, bagian))
    else:
        c.execute("INSERT OR IGNORE INTO pegawai(nik,nama) VALUES(?,?)", (nik, nik))


def db():
    c = sqlite3.connect(DB, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    # --- mode multi-pengguna: banyak HP/laptop absen bareng ---
    # WAL = baca & tulis bisa jalan bersamaan (tanpa ini: "database is locked").
    # Aman di volume Railway (/data) maupun lokal. Gagal -> abaikan (fallback lama).
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=30000")
    except Exception:
        pass

    # --- migrasi skema lama ke baru (jalan sekali, aman) ---
    if _tabel_ada(c, "pegawai") and "user_id" in _kolom(c, "pegawai"):
        c.execute("CREATE TABLE IF NOT EXISTS pegawai_new(nik TEXT PRIMARY KEY, nama TEXT)")
        c.execute("""INSERT OR IGNORE INTO pegawai_new(nik,nama)
            SELECT user_id, COALESCE(nama,user_id) FROM pegawai""")
        c.execute("DROP TABLE pegawai")
        c.execute("ALTER TABLE pegawai_new RENAME TO pegawai")

    if _tabel_ada(c, "absen") and "user_id" in _kolom(c, "absen"):
        c.execute("""CREATE TABLE IF NOT EXISTS absen_new(
            id INTEGER PRIMARY KEY AUTOINCREMENT, nik TEXT, waktu TEXT,
            tipe TEXT DEFAULT 'MASUK', cara TEXT DEFAULT 'aplikasi', UNIQUE(nik, waktu))""")
        c.execute("""INSERT OR IGNORE INTO absen_new(nik,waktu,tipe,cara)
            SELECT user_id, waktu,
            CASE WHEN status=1 THEN 'PULANG' ELSE 'MASUK' END,
            COALESCE(sumber,'aplikasi') FROM absen""")
        c.execute("DROP TABLE absen")
        c.execute("ALTER TABLE absen_new RENAME TO absen")

    if _tabel_ada(c, "pengajuan") and "user_id" in _kolom(c, "pengajuan"):
        c.execute("""CREATE TABLE IF NOT EXISTS pengajuan_new(
            id INTEGER PRIMARY KEY AUTOINCREMENT, nik TEXT, tanggal TEXT,
            jenis TEXT, ket TEXT DEFAULT '', status TEXT DEFAULT 'PENDING')""")
        try:
            c.execute("""INSERT INTO pengajuan_new(nik,tanggal,jenis,ket,status)
                SELECT user_id, substr(tanggal_mulai,1,10), jenis, ket, status FROM pengajuan""")
        except Exception:
            pass
        c.execute("DROP TABLE pengajuan")
        c.execute("ALTER TABLE pengajuan_new RENAME TO pengajuan")

    # --- skema: pegawai, absen, mesin fingerprint, pengajuan, users ---
    c.execute("CREATE TABLE IF NOT EXISTS pegawai(nik TEXT PRIMARY KEY, nama TEXT, bagian TEXT DEFAULT '')")
    if "bagian" not in _kolom(c, "pegawai"):
        c.execute("ALTER TABLE pegawai ADD COLUMN bagian TEXT DEFAULT ''")
    c.execute("""CREATE TABLE IF NOT EXISTS absen(
        id INTEGER PRIMARY KEY AUTOINCREMENT, nik TEXT, waktu TEXT,
        tipe TEXT DEFAULT 'MASUK', cara TEXT DEFAULT 'aplikasi', UNIQUE(nik, waktu))""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_absen_nik ON absen(nik)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_absen_waktu ON absen(waktu)")
    # satu-satunya mesin: fingerprint kantor (tarik via IP)
    c.execute("""CREATE TABLE IF NOT EXISTS mesin(
        id INTEGER PRIMARY KEY AUTOINCREMENT, nama TEXT DEFAULT 'Mesin Kantor',
        ip TEXT DEFAULT '', port INTEGER DEFAULT 4370, terakhir TEXT DEFAULT '')""")
    c.execute("""CREATE TABLE IF NOT EXISTS pengajuan(
        id INTEGER PRIMARY KEY AUTOINCREMENT, nik TEXT, tanggal TEXT,
        jenis TEXT, ket TEXT DEFAULT '', status TEXT DEFAULT 'PENDING')""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pengajuan_nik_tgl ON pengajuan(nik, tanggal)")
    c.execute("CREATE TABLE IF NOT EXISTS users("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "username TEXT UNIQUE, password_hash TEXT, "
              "role TEXT DEFAULT 'admin', nik TEXT DEFAULT '')")
    if "role" not in _kolom(c, "users"):
        c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'admin'")
    if "nik" not in _kolom(c, "users"):
        c.execute("ALTER TABLE users ADD COLUMN nik TEXT DEFAULT ''")
    if not c.execute("SELECT 1 FROM users WHERE username='admin'").fetchone():
        c.execute("INSERT INTO users(username,password_hash,role,nik) VALUES(?,?,?,?)",
                  ("admin", generate_password_hash("admin123"), "admin", ""))
    # akun contoh untuk karyawan (peran terbatas).
    if not c.execute("SELECT 1 FROM users WHERE username='user'").fetchone():
        c.execute("INSERT INTO users(username,password_hash,role,nik) VALUES(?,?,?,?)",
                  ("user", generate_password_hash("user123"), "user", ""))
    # Password awal via env (khusus hosting tanpa akses terminal).
    # Cara: set ABSENSI_ADMIN_PW / ABSENSI_USER_PW sekali, deploy, lalu HAPUS
    # lagi env-nya (password sudah tersimpan aman dalam bentuk hash di database).
    import os as _os
    for _u, _e in (("admin", "ABSENSI_ADMIN_PW"), ("user", "ABSENSI_USER_PW")):
        _pw = (_os.environ.get(_e) or "").strip()
        if len(_pw) >= 6:
            c.execute("UPDATE users SET password_hash=? WHERE username=?",
                      (generate_password_hash(_pw), _u))
    c.commit()
    return c
