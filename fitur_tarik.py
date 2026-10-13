"""UNTUK APA: tarik data dari mesin fingerprint kantor via IP.
Cara pakai: masukkan IP mesin (mis. 192.168.1.201) -> Tes koneksi -> Tarik.
Hasil tarikan masuk ke tabel absen dan bisa dilihat di tab ini (Data tertarik)
atau di tab Hari Ini. Butuh: pip install pyzk.
API:
- GET  /api/mesin -> daftar mesin tersimpan (admin)
- POST /api/mesin {nama, ip, port} -> simpan, {id, hapus:1} -> hapus (admin)
- POST /api/mesin/tes {id} atau {ip, port} -> cek koneksi TCP (admin)
- POST /api/mesin/tarik {id} -> tarik semua sidik tap dari mesin (admin)
- POST /api/demo -> isi data contoh hari ini untuk latihan (admin)
- POST /api/data/hapus {ids:[...]} -> hapus baris terpilih (admin)
- POST /api/data/hapus {semua:true} -> hapus SEMUA isi database + backup otomatis (admin)
- GET  /api/data?q=&limit= -> isi database absen (hasil tarikan)"""
import os
import random
import socket
from flask import Blueprint, request, jsonify
from database import db, snapshot_db, pakai_mysql
from auth import perlu_login, wajib_admin
from config import DB, wib_now, wib_today

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(DB)), "backup")

bp_tarik = Blueprint("tarik", __name__)


def _jalan_di_cloud():
    """True bila kode jalan di server cloud (Railway/dll), bukan di PC kantor.
    Railway menyetel env RAILWAY_* / PORT. Di PC kantor env itu tidak ada."""
    return bool(os.environ.get("RAILWAY_ENVIRONMENT")
                or os.environ.get("RAILWAY_PROJECT_ID")
                or os.environ.get("RAILWAY_SERVICE_ID"))


def _ip_privat(ip):
    """True bila IP lokal (tidak bisa dijangkau dari internet/cloud)."""
    try:
        p = [int(x) for x in (ip or "").strip().split(".")]
        if len(p) != 4 or any(x < 0 or x > 255 for x in p):
            return False
        if p[0] == 10:
            return True
        if p[0] == 172 and 16 <= p[1] <= 31:
            return True
        if p[0] == 192 and p[1] == 168:
            return True
        if p[0] == 127:
            return True
        return False
    except Exception:
        return False


PESAN_CLOUD = ("Server cloud (Railway) TIDAK BISA menjangkau IP lokal seperti {ip}. "
               "Ping dari CMD itu dari PC kantor (satu LAN dengan mesin) — wajar OK. "
               "Tapi tombol Tes/Tarik ini jalan di server cloud, bukan di PC kamu. "
               "Solusi: di PC kantor (satu WiFi/LAN dengan mesin) jalankan mulai.bat / python app.py, "
               "buka http://127.0.0.1:5000 (JANGAN URL railway), simpan mesin {ip}, lalu Tes+Tarik di situ. "
               "Agar masuk ke database cloud juga, di PC kantor set env MYSQL_URL sama seperti di Railway dulu.")


def _pastikan_kolom_mesin(c):
    """Tambah kolom sandi (comm key / password mesin) bila DB lama belum punya.
    Jalan di SQLite & MySQL, aman dipanggil tiap request."""
    try:
        # MySQL backend (_ConnMy) -> cek information_schema
        if c.__class__.__name__ == "_ConnMy":
            ada = c.execute(
                "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
                "AND TABLE_NAME='mesin' AND COLUMN_NAME='sandi'").fetchone()
            if not ada:
                c.execute("ALTER TABLE mesin ADD COLUMN sandi INT DEFAULT 0")
                c.commit()
            return
    except Exception:
        pass
    try:
        cols = {r[1] for r in c.execute("PRAGMA table_info(mesin)").fetchall()}
        if "sandi" not in cols:
            c.execute("ALTER TABLE mesin ADD COLUMN sandi INTEGER DEFAULT 0")
            c.commit()
    except Exception:
        pass


def _cek_tcp(ip, port, timeout=5):
    """Cek TCP ke port mesin. Beda dengan ping: ping OK (ICMP) belum tentu
    port 4370 (TCP) terbuka. Return (ok, pesan_singkat)."""
    try:
        s = socket.create_connection((ip, int(port)), timeout=timeout)
        s.close()
        return True, "Terhubung"
    except socket.timeout:
        return False, (f"Timeout {timeout} dtk ke {ip}:{port}. Mesin tidak menjawab TCP. "
                       "Cek: kabel/LAN satu subnet, firewall Windows, AP-isolation router.")
    except ConnectionRefusedError:
        return False, (f"Port {port} DITOLAK oleh {ip}. IP benar tapi bukan port mesin "
                       "(umumnya 4370). Cek menu mesin: COMM. > Port / PC Connection.")
    except OSError as e:
        msg = str(e).lower()
        if "unreachable" in msg or "10065" in msg or "101" in msg:
            return False, (f"Tidak ada rute ke {ip}. Beda subnet / gateway mesin belum diisi. "
                           f"Samakan 3 angka depan IP (mis. 192.168.1.x). Detail: {e}")
        if "timed out" in msg or "10060" in msg:
            return False, (f"Timeout ke {ip}:{port}. Kabel/router OK (ping bisa) tapi TCP diblokir. "
                           "Matikan firewall sebentar / buka outbound TCP 4370. "
                           f"Detail: {e}")
        return False, str(e)
    except Exception as e:
        return False, str(e)


def _artikan_error_zk(e):
    """Terjemahkan error pyzk ke bahasa + solusi praktis."""
    s = f"{type(e).__name__}: {e}"
    low = s.lower()
    if "password" in low or "unauthorized" in low or "comm key" in low:
        return (s + " | Mesin pakai Comm Key / password bukan 0. "
                "Cek di mesin: Menu > COMM. > Comm Key, lalu isi kolom Sandi di web dengan angka itu.")
    if "timeout" in low or "timed out" in low or "10060" in low:
        return (s + " | Mesin lambat / LOG MENUMPUK PULUHAN RIBU / jaringan WiFi padat. "
                "Solusi cepat: backup via flashdisk di mesin (USB Mngt > Download), lalu hapus log lama "
                "(Clear AttLog) agar tarik berikutnya cepat. Tarik via kabel LAN, bukan WiFi repeater, "
                "dan pastikan hanya 1 PC yang menarik.")
    if "refused" in low:
        return s + " | Port ditolak. Pastikan port 4370 dan tidak diganti di mesin."
    if "unreachable" in low or "10065" in low:
        return s + " | Beda subnet. Isi Gateway mesin = IP router (mis. 192.168.1.1)."
    if "decode" in low or "unpack" in low or "index" in low:
        return (s + " | Protokol tidak cocok (firmware baru / tipe baru). "
                "Coba update pyzk: pip install -U pyzk, atau tarik via USB/flashdisk sementara.")
    return s


def _coba_zk(ip, port, sandi=0, timeout=20):
    """Sambung ke mesin. Urutan penting di Windows: tanpa-ping dulu
    (test_ping pyzk di Windows bisa gantung), baru fallback lain.
    Return (conn, zk, nama_strategi). Raise bila semua gagal."""
    from zk import ZK
    strategi = [
        ("TCP-tanpa-ping", dict(force_udp=False, ommit_ping=True)),
        ("UDP", dict(force_udp=True, ommit_ping=True)),
        ("TCP", dict(force_udp=False, ommit_ping=False)),
    ]
    err_terakhir = None
    for nama, opt in strategi:
        try:
            zk = ZK(ip, port=port, timeout=timeout, password=int(sandi or 0), **opt)
            conn = zk.connect()
            return conn, zk, nama
        except Exception as e:
            err_terakhir = e
            continue
    raise RuntimeError(_artikan_error_zk(err_terakhir))


@bp_tarik.route("/api/mesin", methods=["GET", "POST"])
@wajib_admin
def mesin():
    c = db()
    _pastikan_kolom_mesin(c)
    if request.method == "GET":
        try:
            rows = [dict(r) for r in c.execute("SELECT * FROM mesin ORDER BY id").fetchall()]
        except Exception:
            # DB lama tanpa kolom sandi -> fallback kolom dasar
            rows = [dict(r) for r in c.execute(
                "SELECT id, nama, ip, port, terakhir FROM mesin ORDER BY id").fetchall()]
            for r in rows:
                r.setdefault("sandi", 0)
        c.close()
        return jsonify(rows)
    j = request.get_json(force=True, silent=True) or {}
    if j.get("hapus"):
        c.execute("DELETE FROM mesin WHERE id=?", (j.get("id"),))
        c.commit()
        c.close()
        return jsonify({"ok": True, "pesan": "Mesin dihapus."})
    ip = (j.get("ip") or "").strip()
    nama = (j.get("nama") or "Mesin Kantor").strip()[:50] or "Mesin Kantor"
    try:
        port = int(j.get("port", 4370))
        assert 1 <= port <= 65535
    except Exception:
        c.close()
        return jsonify({"ok": False, "pesan": "Port harus 1-65535."}), 400
    try:
        sandi = int(j.get("sandi", 0) or 0)
        assert 0 <= sandi <= 999999999
    except Exception:
        c.close()
        return jsonify({"ok": False, "pesan": "Sandi/Comm Key harus angka 0-999999999 (0 = tanpa sandi)."}), 400
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        c.close()
        return jsonify({"ok": False, "pesan": "IP tidak valid. Contoh: 192.168.1.201"}), 400
    if j.get("id"):
        c.execute("UPDATE mesin SET nama=?, ip=?, port=?, sandi=? WHERE id=?",
                  (nama, ip, port, sandi, j.get("id")))
    else:
        c.execute("INSERT INTO mesin(nama, ip, port, sandi) VALUES(?,?,?,?)",
                  (nama, ip, port, sandi))
    c.commit()
    c.close()
    return jsonify({"ok": True, "pesan": f"Mesin {nama} ({ip}) tersimpan."})


@bp_tarik.route("/api/mesin/tes", methods=["POST"])
@wajib_admin
def mesin_tes():
    """Diagnosa 3 langkah: 1) TCP 4370, 2) handshake ZK, 3) baca info mesin.
    Ping OK saja tidak cukup — yang penting TCP + protokol ZK."""
    j = request.get_json(force=True, silent=True) or {}
    ip, port, sandi = (j.get("ip") or "").strip(), j.get("port", 4370), int(j.get("sandi", 0) or 0)
    if j.get("id"):
        c = db()
        _pastikan_kolom_mesin(c)
        r = c.execute("SELECT * FROM mesin WHERE id=?", (j.get("id"),)).fetchone()
        c.close()
        if not r:
            return jsonify({"ok": False, "pesan": "Mesin tidak ditemukan."}), 404
        try:
            d = dict(r)
        except Exception:
            d = {"ip": r["ip"], "port": r["port"], "sandi": 0}
        ip, port, sandi = d["ip"], d["port"], int(d.get("sandi", 0) or 0)
    try:
        port = int(port or 4370)
    except Exception:
        return jsonify({"ok": False, "pesan": "Port harus angka (umumnya 4370)."}), 400
    if _jalan_di_cloud() and _ip_privat(ip):
        return jsonify({"ok": False, "pesan": PESAN_CLOUD.format(ip=ip)})
    # Langkah 1: TCP (bukan ping). Ping pakai ICMP, mesin pakai TCP 4370.
    ok, msg_tcp = _cek_tcp(ip, port, timeout=5)
    if not ok:
        return jsonify({"ok": False,
                        "pesan": f"Langkah 1/3 GAGAL (TCP): {msg_tcp} | "
                                 "Solusi: pastikan PC & mesin satu router & satu subnet "
                                 "(cth. PC 192.168.1.10, mesin 192.168.1.201), isi Gateway mesin = IP router "
                                 "(cth. 192.168.1.1), matikan AP-Isolation di router, buka firewall TCP 4370."})
    # Langkah 2+3: handshake ZK + baca info
    try:
        from zk import ZK  # noqa: F401 (cek lib dulu biar pesan jelas)
    except ImportError:
        return jsonify({"ok": False,
                        "pesan": "Langkah 1/3 OK (TCP terbuka), tapi library pyzk belum terpasang. "
                                 "Jalankan: pip install pyzk lalu ulangi."}), 400
    try:
        conn, _zk, cara = _coba_zk(ip, port, sandi, timeout=15)
        try:
            info = ""
            try:
                fw = conn.get_firmware_version()
                fp = conn.get_fp_version() if hasattr(conn, "get_fp_version") else ""
                info = f"FW {fw} {fp}".strip()
            except Exception:
                pass
            try:
                n_user = len(conn.get_users())
            except Exception:
                n_user = -1
            try:
                n_log = len(conn.get_attendance())
            except Exception:
                n_log = -1
        finally:
            try:
                conn.disconnect()
            except Exception:
                pass
        detail = f"Langkah 3/3 OK via {cara}."
        if n_user >= 0 or n_log >= 0:
            detail += f" Pengguna: {n_user}, total log di mesin: {n_log}."
        if info:
            detail += f" ({info})"
        return jsonify({"ok": True,
                        "pesan": f"Terhubung ke {ip}:{port}. Langkah 1/3 TCP OK, 2/3 handshake ZK OK. {detail} "
                                 "Silakan klik Tarik."})
    except Exception as e:
        return jsonify({"ok": False,
                        "pesan": f"Langkah 1/3 OK (TCP {ip}:{port} terbuka), tapi 2/3 handshake ZK GAGAL: {e} | "
                                 "Penyebab umum: Comm Key mesin bukan 0 (isi kolom Sandi), "
                                 "kabel via WiFi-repeater lambat (pakai kabel LAN langsung), "
                                 "atau 2 PC menarik bersamaan."})


@bp_tarik.route("/api/mesin/info", methods=["POST"])
@wajib_admin
def mesin_info():
    """Cek cepat isi memori mesin (jumlah user & log) TANPA menarik semua data.
    Penting bila tarik gantung: log puluhan ribu = memori hampir penuh."""
    j = request.get_json(force=True, silent=True) or {}
    c = db()
    _pastikan_kolom_mesin(c)
    if j.get("id"):
        r = c.execute("SELECT * FROM mesin WHERE id=?", (j.get("id"),)).fetchone()
    else:
        r = c.execute("SELECT * FROM mesin ORDER BY id").fetchone()
    c.close()
    if not r:
        return jsonify({"ok": False, "pesan": "Belum ada mesin."}), 400
    m = dict(r)
    ip, port, sandi = m["ip"], int(m["port"] or 4370), int(m.get("sandi", 0) or 0)
    if _jalan_di_cloud() and _ip_privat(ip):
        return jsonify({"ok": False, "pesan": PESAN_CLOUD.format(ip=ip)})
    try:
        conn, _zk, cara = _coba_zk(ip, port, sandi, timeout=20)
        try:
            try:
                conn.read_sizes()
                n_user, u_cap = int(getattr(conn, "users", -1)), int(getattr(conn, "users_cap", 0))
                n_rec, r_cap = int(getattr(conn, "records", -1)), int(getattr(conn, "rec_cap", 0))
            except Exception:
                n_user, n_rec, u_cap, r_cap = -1, -1, 0, 0
            try:
                fw = conn.get_firmware_version()
                nama = conn.get_device_name()
            except Exception:
                fw, nama = "", ""
        finally:
            try:
                conn.disconnect()
            except Exception:
                pass
        saran = ""
        if n_rec > 20000:
            saran = (f" | MEMORI HAMPIR PENUH ({n_rec} log). Tarik penuh pasti lambat/gantung. "
                     "Backup via flashdisk (USB Mngt > Download) lalu Clear AttLog di mesin, "
                     "setelah itu tarik web jadi cepat.")
        return jsonify({"ok": True, "users": n_user, "records": n_rec,
                        "pesan": f"{nama or 'Mesin'} {ip} ({cara}) FW {fw}: {n_user}/{u_cap} user, "
                                 f"{n_rec}/{r_cap} log.{saran}"})
    except Exception as e:
        return jsonify({"ok": False, "pesan": f"Gagal baca info: {_artikan_error_zk(e)}"})


# Catatan: tarik butuh timeout panjang (log besar bisa menit, bukan detik).


@bp_tarik.route("/api/mesin/tarik", methods=["POST"])
@wajib_admin
def mesin_tarik():
    j = request.get_json(force=True, silent=True) or {}
    c = db()
    _pastikan_kolom_mesin(c)
    if j.get("id"):
        daftar = [dict(r) for r in c.execute("SELECT * FROM mesin WHERE id=?", (j.get("id"),)).fetchall()]
    else:
        daftar = [dict(r) for r in c.execute("SELECT * FROM mesin ORDER BY id").fetchall()]
    c.close()
    if not daftar:
        return jsonify({"ok": False, "pesan": "Belum ada mesin. Masukkan IP mesin dulu."}), 400
    try:
        from zk import ZK  # noqa: F401
    except ImportError:
        return jsonify({"ok": False,
                        "pesan": "Library pyzk belum terpasang. Jalankan: pip install pyzk lalu ulangi."}), 400
    hasil, total_baru = [], 0
    for m in daftar:
        ip, port = m["ip"], int(m["port"] or 4370)
        sandi = int(m.get("sandi", 0) or 0)
        if _jalan_di_cloud() and _ip_privat(ip):
            hasil.append(f"{m['nama']}: " + PESAN_CLOUD.format(ip=ip))
            continue
        ok, msg = _cek_tcp(ip, port, timeout=5)
        if not ok:
            hasil.append(f"{m['nama']}: tidak terhubung — {msg}")
            continue
        try:
            # Timeout 180 dtk: log puluhan ribu (F18: 99rb) butuh menit, bukan detik.
            # Kunci: ommit_ping=True dulu (bug ping Windows), disable_device agar tidak
            # ada scan baru saat baca, dan baca via kabel LAN (jangan WiFi repeater).
            conn, _zk, cara = _coba_zk(ip, port, sandi, timeout=180)
            try:
                try:
                    conn.disable_device()
                except Exception:
                    pass
                try:
                    conn.read_sizes()
                    n_rec = int(getattr(conn, "records", 0) or 0)
                except Exception:
                    n_rec = -1
                users = {}
                try:
                    users = {str(u.user_id): (u.name or str(u.user_id)) for u in conn.get_users()}
                except Exception:
                    pass
                att = conn.get_attendance()
            finally:
                try:
                    conn.enable_device()
                except Exception:
                    pass
                try:
                    conn.disconnect()
                except Exception:
                    pass
            if not att:
                hasil.append(f"{m['nama']}: terhubung ({cara}) tapi log di mesin kosong / sudah dihapus di mesin.")
                continue
            c = db()
            baru = 0
            for a in att:
                try:
                    nik = str(a.user_id)
                    w = a.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    # pegawai dulu, baru absen (wajib untuk foreign key MySQL)
                    c.execute("INSERT OR IGNORE INTO pegawai(nik,nama) VALUES(?,?)",
                              (nik, users.get(nik, nik)))
                    cur = c.execute(
                        "INSERT OR IGNORE INTO absen(nik,waktu,tipe,cara,status) VALUES(?,?,?,?,?)",
                        (nik, w, "MASUK", f"mesin:{m['nama']}", "DISETUJUI"))
                    baru += 1 if (cur.rowcount or 0) else 0
                except Exception:
                    continue
            # rapikan: tap pertama = MASUK, terakhir = PULANG per orang per hari
            for r in c.execute(
                    "SELECT nik, substr(waktu,1,10) t, MIN(waktu) mn, MAX(waktu) mx, COUNT(*) n "
                    "FROM absen GROUP BY nik, t").fetchall():
                nik, _t, mn, mx, n = r[0], r[1], r[2], r[3], r[4]
                if n > 1:
                    c.execute("UPDATE absen SET tipe='MASUK' WHERE nik=? AND waktu=?", (nik, mn))
                    c.execute("UPDATE absen SET tipe='PULANG' WHERE nik=? AND waktu=?", (nik, mx))
            c.execute("UPDATE mesin SET terakhir=? WHERE id=?",
                      (wib_now().strftime("%Y-%m-%d %H:%M:%S"), m["id"]))
            c.commit()
            c.close()
            total_baru += baru
            hasil.append(f"{m['nama']}: {baru} data baru dari {len(att)} log ({cara})")
        except Exception as e:
            try:
                c.close()
            except Exception:
                pass
            hasil.append(f"{m['nama']}: gagal — {_artikan_error_zk(e)}")
    return jsonify({"ok": True, "baru": total_baru, "pesan": " | ".join(hasil)})


@bp_tarik.route("/api/demo", methods=["POST"])
@wajib_admin
def demo():
    """Isi data contoh hari ini untuk latihan tanpa mesin.
    Pakai NIK 901-910 agar tidak campur dengan data asli."""
    hari = wib_today().isoformat()
    nama = ["Contoh Andi", "Contoh Ayu", "Contoh Citra", "Contoh Dedi", "Contoh Eka",
            "Contoh Fajar", "Contoh Gita", "Contoh Hendra", "Contoh Indah", "Contoh Joko"]
    c = db()
    for i, n in enumerate(nama, 901):
        c.execute("INSERT OR IGNORE INTO pegawai(nik,nama,bagian) VALUES(?,?,?)",
                  (str(i), n, "Contoh"))
    rows = []
    for i in range(901, 911):
        uid = str(i)
        rnd = random.Random(f"{hari}-{uid}")
        rows.append((uid, f"{hari} 0{rnd.choice([7, 8, 8, 8])}:{rnd.randint(0, 59):02d}:00", "MASUK"))
        if i != 904:  # satu orang sengaja lupa scan pulang
            rows.append((uid, f"{hari} 17:{rnd.randint(0, 59):02d}:00", "PULANG"))
    baru = 0
    for nik, w, tipe in rows:
        cur = c.execute("INSERT OR IGNORE INTO absen(nik,waktu,tipe,cara,status) VALUES(?,?,?,?,?)",
                        (nik, w, tipe, "demo", "DISETUJUI"))
        baru += 1 if (cur.rowcount or 0) else 0
    c.commit()
    c.close()
    return jsonify({"ok": True, "baru": baru,
                    "pesan": f"Mode demo: {baru} scan contoh masuk (klik berulang tidak menggandakan)."})


@bp_tarik.route("/api/demo/hapus", methods=["POST"])
@wajib_admin
def demo_hapus():
    """Hapus semua data contoh (NIK 901-910 + cara='demo') agar bisa mulai data asli."""
    c = db()
    n1 = c.execute("DELETE FROM absen WHERE cara='demo' OR nik BETWEEN '901' AND '910'").rowcount or 0
    c.execute("DELETE FROM pegawai WHERE nik BETWEEN '901' AND '910'")
    c.commit()
    c.close()
    return jsonify({"ok": True, "pesan": f"{n1} scan contoh dihapus. Database siap untuk data asli."})


@bp_tarik.route("/api/data/hapus", methods=["POST"])
@wajib_admin
def data_hapus():
    """Hapus database hasil tarikan. {ids:[...]} = baris terpilih,
    {semua:true} = KOSONGKAN semua (backup otomatis dulu)."""
    j = request.get_json(force=True, silent=True) or {}
    if j.get("semua"):
        c = db()
        n = c.execute("SELECT COUNT(*) FROM absen").fetchone()[0]
        c.close()
        if not n:
            return jsonify({"ok": True, "hapus": 0, "pesan": "Database sudah kosong."})
        os.makedirs(BACKUP_DIR, exist_ok=True)
        snapshot_db(os.path.join(
            BACKUP_DIR, f"absensi_sebelum_kosongkan_{wib_now():%Y%m%d_%H%M%S}" + (".sql" if pakai_mysql() else ".db")))
        c = db()
        c.execute("DELETE FROM absen")
        c.commit()
        c.close()
        return jsonify({"ok": True, "hapus": n,
                        "pesan": f"{n} baris dihapus, database dikosongkan. Backup tersimpan di folder backup."})
    try:
        ids = [int(x) for x in (j.get("ids") or [])]
    except Exception:
        return jsonify({"ok": False, "pesan": "ID tidak valid."}), 400
    if not ids:
        return jsonify({"ok": False, "pesan": "Tidak ada baris yang dipilih."}), 400
    ids = ids[:500]
    c = db()
    c.execute(f"DELETE FROM absen WHERE id IN ({','.join('?' * len(ids))})", ids)
    n = c.total_changes
    c.commit()
    c.close()
    return jsonify({"ok": True, "hapus": n, "pesan": f"{n} baris terpilih dihapus."})


@bp_tarik.route("/api/data")
@perlu_login
def data_tarik():
    """Isi database absen. Admin & user kios lihat semua, user terikat hanya datanya sendiri."""
    from flask import session
    q = (request.args.get("q") or "").strip()
    try:
        limit = min(500, max(20, int(request.args.get("limit", 100))))
    except Exception:
        limit = 100
    c = db()
    sendiri = (session.get("nik") or "").strip()
    if session.get("role") != "admin" and sendiri:
        # user terikat NIK: hanya datanya sendiri
        rows = [dict(r) for r in c.execute(
            """SELECT a.id, a.waktu, a.nik, COALESCE(p.nama, a.nik) nama,
                      COALESCE(p.bagian,'') bagian, a.tipe, a.cara,
                      a.lat, a.lon, a.jarak_m, a.akurasi_m, COALESCE(a.status,'DISETUJUI') status
               FROM absen a LEFT JOIN pegawai p ON p.nik=a.nik
               WHERE a.nik=?
               ORDER BY a.waktu DESC LIMIT ?""", (sendiri, limit)).fetchall()]
        total = c.execute("SELECT COUNT(*) c FROM absen WHERE nik=?", (sendiri,)).fetchone()["c"]
        c.close()
        return jsonify({"total": total, "data": rows})
    if q:
        rows = [dict(r) for r in c.execute(
            """SELECT a.id, a.waktu, a.nik, COALESCE(p.nama, a.nik) nama,
                      COALESCE(p.bagian,'') bagian, a.tipe, a.cara,
                      a.lat, a.lon, a.jarak_m, a.akurasi_m, COALESCE(a.status,'DISETUJUI') status
               FROM absen a LEFT JOIN pegawai p ON p.nik=a.nik
               WHERE a.nik LIKE ? OR p.nama LIKE ? OR p.bagian LIKE ? OR a.waktu LIKE ?
               ORDER BY a.waktu DESC LIMIT ?""",
            (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", limit)).fetchall()]
    else:
        rows = [dict(r) for r in c.execute(
            """SELECT a.id, a.waktu, a.nik, COALESCE(p.nama, a.nik) nama,
                      COALESCE(p.bagian,'') bagian, a.tipe, a.cara,
                      a.lat, a.lon, a.jarak_m, a.akurasi_m, COALESCE(a.status,'DISETUJUI') status
               FROM absen a LEFT JOIN pegawai p ON p.nik=a.nik
               ORDER BY a.waktu DESC LIMIT ?""", (limit,)).fetchall()]
    total = c.execute("SELECT COUNT(*) c FROM absen").fetchone()["c"]
    c.close()
    return jsonify({"total": total, "data": rows})
