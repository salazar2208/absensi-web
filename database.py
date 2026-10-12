"""UNTUK APA: urusan database saja.
- buka koneksi (db())
- Tanpa MYSQL_URL -> SQLite lokal seperti semula (laptop).
- Dengan MYSQL_URL (atau MYSQLHOST) -> MySQL (Railway + phpMyAdmin).
- bikin tabel kalau belum ada (pegawai, absen, mesin fingerprint, pengajuan, users)
- migrasi otomatis dari skema lama SQLite (user_id -> nik)
- Di MySQL ada FOREIGN KEY absen/pengajuan -> pegawai agar phpMyAdmin
  Designer menggambar diagram relasi (pohon) otomatis.
Jangan taruh logika laporan di sini."""
import os
import shutil
import sqlite3
from urllib.parse import urlparse, unquote

from werkzeug.security import generate_password_hash
from config import DB

try:
    import pymysql
    from pymysql.cursors import DictCursor
    _ADA_PYMYSQL = True
except ImportError:
    _ADA_PYMYSQL = False


def pakai_mysql():
    """True bila backend MySQL aktif (ada MYSQL_URL atau MYSQLHOST)."""
    return bool((os.environ.get("MYSQL_URL") or "").strip()
                or (os.environ.get("MYSQLHOST") or "").strip())


class Baris(dict):
    """Baris hasil yang bisa diakses gaya dict (r['nik']) MAUPUN
    gaya index (r[0]) seperti sqlite3.Row, agar semua fitur lama jalan
    tanpa diubah di kedua backend."""

    def __getitem__(self, k):
        if isinstance(k, int):
            try:
                return list(self.values())[k]
            except IndexError:
                raise KeyError(k)
        return super().__getitem__(k)


class _CurMy:
    """Cursor MySQL yang menerima placeholder '?' dan sintaks
    'INSERT OR IGNORE' gaya SQLite (diterjemahkan otomatis)."""

    def __init__(self, cur, conn):
        self._c = cur
        self._conn = conn
        self.rowcount = -1

    def execute(self, sql, params=()):
        sql2 = sql.replace("INSERT OR IGNORE INTO", "INSERT IGNORE INTO")
        sql2 = sql2.replace("AUTOINCREMENT", "AUTO_INCREMENT")
        sql2 = sql2.replace("?", "%s")
        self._c.execute(sql2, params if params else None)
        try:
            self._conn._tambah(self._c.rowcount or 0)
        except Exception:
            pass
        self.rowcount = self._c.rowcount
        return self

    def fetchone(self):
        r = self._c.fetchone()
        return Baris(r) if r is not None else None

    def fetchall(self):
        return [Baris(r) for r in self._c.fetchall()]


class _ConnMy:
    """Koneksi MySQL dengan rasa sqlite3 (execute/commit/close/total_changes)."""

    def __init__(self, raw):
        self._raw = raw
        self._n = 0

    def _tambah(self, n):
        try:
            self._n += int(n)
        except Exception:
            pass

    @property
    def total_changes(self):
        return self._n

    def execute(self, sql, params=()):
        return _CurMy(self._raw.cursor(), self).execute(sql, params)

    def commit(self):
        self._raw.commit()

    def close(self):
        try:
            self._raw.close()
        except Exception:
            pass


def _mysql_conn():
    url = (os.environ.get("MYSQL_URL") or "").strip()
    if url:
        u = urlparse(url)
        host = u.hostname or "localhost"
        port = u.port or 3306
        user = unquote(u.username or "")
        pw = unquote(u.password or "")
        dbn = (u.path or "/").lstrip("/") or "railway"
    else:
        host = os.environ.get("MYSQLHOST", "localhost")
        port = int(os.environ.get("MYSQLPORT", "3306") or 3306)
        user = os.environ.get("MYSQLUSER", "root")
        pw = os.environ.get("MYSQLPASSWORD", "")
        dbn = os.environ.get("MYSQLDATABASE", "railway")
    raw = pymysql.connect(host=host, port=port, user=user, password=pw,
                          database=dbn, charset="utf8mb4",
                          cursorclass=DictCursor, connect_timeout=10,
                          autocommit=False)
    return _ConnMy(raw)


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
    yang kosong tidak menimpa data lama. Jalan di SQLite & MySQL."""
    nama = (nama or "").strip()[:100]
    bagian = (bagian or "").strip()[:60]
    mysql = isinstance(c, _ConnMy)
    if mysql:
        if nama and bagian:
            c.execute("INSERT INTO pegawai(nik,nama,bagian) VALUES(?,?,?) "
                      "ON DUPLICATE KEY UPDATE nama=VALUES(nama), bagian=VALUES(bagian)",
                      (nik, nama, bagian))
        elif nama:
            c.execute("INSERT INTO pegawai(nik,nama) VALUES(?,?) "
                      "ON DUPLICATE KEY UPDATE nama=VALUES(nama)",
                      (nik, nama))
        elif bagian:
            c.execute("INSERT INTO pegawai(nik,nama,bagian) VALUES(?,?,?) "
                      "ON DUPLICATE KEY UPDATE bagian=VALUES(bagian)",
                      (nik, nik, bagian))
        else:
            c.execute("INSERT IGNORE INTO pegawai(nik,nama) VALUES(?,?)", (nik, nik))
        return
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


def _seed(c):
    """Akun bawaan + password awal via env. SQL portabel (jalan di keduanya)."""
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
    for _u, _e in (("admin", "ABSENSI_ADMIN_PW"), ("user", "ABSENSI_USER_PW")):
        _pw = (os.environ.get(_e) or "").strip()
        if len(_pw) >= 6:
            c.execute("UPDATE users SET password_hash=? WHERE username=?",
                      (generate_password_hash(_pw), _u))


def _skema_mysql(c):
    """Skema MySQL (InnoDB + utf8mb4). Relasi absen/pengajuan -> pegawai
    dengan ON DELETE SET NULL agar phpMyAdmin Designer menggambar pohon
    relasi otomatis, tapi hapus pegawai TIDAK menghapus riwayat absen."""
    c.execute("""CREATE TABLE IF NOT EXISTS pegawai(
        nik VARCHAR(30) PRIMARY KEY, nama VARCHAR(100) DEFAULT '',
        bagian VARCHAR(60) DEFAULT '') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    c.execute("""CREATE TABLE IF NOT EXISTS absen(
        id INT AUTO_INCREMENT PRIMARY KEY, nik VARCHAR(30) NULL, waktu VARCHAR(19),
        tipe VARCHAR(10) DEFAULT 'MASUK', cara VARCHAR(60) DEFAULT 'aplikasi',
        UNIQUE KEY uq_absen (nik, waktu),
        KEY idx_absen_nik (nik), KEY idx_absen_waktu (waktu),
        CONSTRAINT fk_absen_pegawai FOREIGN KEY (nik) REFERENCES pegawai(nik)
        ON UPDATE CASCADE ON DELETE SET NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    c.execute("""CREATE TABLE IF NOT EXISTS mesin(
        id INT AUTO_INCREMENT PRIMARY KEY, nama VARCHAR(50) DEFAULT 'Mesin Kantor',
        ip VARCHAR(45) DEFAULT '', port INT DEFAULT 4370,
        terakhir VARCHAR(19) DEFAULT '') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    c.execute("""CREATE TABLE IF NOT EXISTS pengajuan(
        id INT AUTO_INCREMENT PRIMARY KEY, nik VARCHAR(30) NULL, tanggal VARCHAR(10),
        jenis VARCHAR(20) DEFAULT 'IZIN', ket VARCHAR(200) DEFAULT '',
        status VARCHAR(20) DEFAULT 'PENDING',
        KEY idx_pengajuan_nik_tgl (nik, tanggal),
        CONSTRAINT fk_pengajuan_pegawai FOREIGN KEY (nik) REFERENCES pegawai(nik)
        ON UPDATE CASCADE ON DELETE SET NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(60) UNIQUE,
        password_hash VARCHAR(255), role VARCHAR(20) DEFAULT 'admin',
        nik VARCHAR(30) DEFAULT '') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")


def _qsql(v):
    """Escape nilai Python menjadi literal SQL untuk dump."""
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")
    return "'" + s + "'"


def dump_sql():
    """Dump isi database sebagai teks .sql (dipakai tombol Backup saat MySQL)."""
    c = db()
    nama_db = os.environ.get("MYSQLDATABASE", "railway")
    baris = ["-- Backup Absensi Online IPP", "-- Format: MySQL"]
    try:
        for t in ("pegawai", "absen", "mesin", "pengajuan", "users"):
            try:
                rows = c.execute("SELECT * FROM %s" % t).fetchall()
            except Exception:
                continue
            if not rows:
                baris.append("-- tabel %s: kosong" % t)
                continue
            kolom = list(rows[0].keys())
            baris.append("-- tabel %s: %d baris" % (t, len(rows)))
            for r in rows:
                baris.append("INSERT INTO %s (%s) VALUES (%s);" % (
                    t, ", ".join(kolom),
                    ", ".join(_qsql(r[k]) for k in kolom)))
    finally:
        try:
            c.close()
        except Exception:
            pass
    return "-- database: %s\n" % nama_db + "\n".join(baris) + "\n"


def snapshot_db(path_tujuan):
    """Salinan pengaman database ke 1 file (dipakai sebelum hapus massal).
    SQLite -> salin file. MySQL -> tulis dump .sql."""
    d = os.path.dirname(path_tujuan)
    if d:
        os.makedirs(d, exist_ok=True)
    if pakai_mysql():
        with open(path_tujuan, "w", encoding="utf-8") as f:
            f.write(dump_sql())
    else:
        shutil.copy2(DB, path_tujuan)


def db():
    if pakai_mysql():
        if not _ADA_PYMYSQL:
            raise RuntimeError("Backend MySQL diminta (MYSQL_URL/MYSQLHOST) "
                               "tapi pymysql belum terpasang. Jalankan: pip install pymysql.")
        c = _mysql_conn()
        _skema_mysql(c)
        _seed(c)
        c.commit()
        return c

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
    _seed(c)
    c.commit()
    return c
