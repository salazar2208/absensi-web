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
from datetime import datetime, date
from flask import Blueprint, request, jsonify
from database import db, snapshot_db, pakai_mysql
from auth import perlu_login, wajib_admin
from config import DB, wib_now, wib_today

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(DB)), "backup")

bp_tarik = Blueprint("tarik", __name__)


def _cek_tcp(ip, port, timeout=4):
    try:
        s = socket.create_connection((ip, int(port)), timeout=timeout)
        s.close()
        return True, "Terhubung"
    except Exception as e:
        return False, str(e)


@bp_tarik.route("/api/mesin", methods=["GET", "POST"])
@wajib_admin
def mesin():
    c = db()
    if request.method == "GET":
        rows = [dict(r) for r in c.execute("SELECT * FROM mesin ORDER BY id").fetchall()]
        c.close()
        return jsonify(rows)
    j = request.get_json(force=True)
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
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        c.close()
        return jsonify({"ok": False, "pesan": "IP tidak valid. Contoh: 192.168.1.201"}), 400
    if j.get("id"):
        c.execute("UPDATE mesin SET nama=?, ip=?, port=? WHERE id=?", (nama, ip, port, j.get("id")))
    else:
        c.execute("INSERT INTO mesin(nama, ip, port) VALUES(?,?,?)", (nama, ip, port))
    c.commit()
    c.close()
    return jsonify({"ok": True, "pesan": f"Mesin {nama} ({ip}) tersimpan."})


@bp_tarik.route("/api/mesin/tes", methods=["POST"])
@wajib_admin
def mesin_tes():
    j = request.get_json(force=True, silent=True) or {}
    ip, port = (j.get("ip") or "").strip(), j.get("port", 4370)
    if j.get("id"):
        c = db()
        r = c.execute("SELECT * FROM mesin WHERE id=?", (j.get("id"),)).fetchone()
        c.close()
        if not r:
            return jsonify({"ok": False, "pesan": "Mesin tidak ditemukan."}), 404
        ip, port = r["ip"], r["port"]
    ok, msg = _cek_tcp(ip, port)
    return jsonify({"ok": ok, "pesan": f"{'Terhubung' if ok else 'Tidak terhubung'} ke {ip}:{port}. {'' if ok else msg}"})


@bp_tarik.route("/api/mesin/tarik", methods=["POST"])
@wajib_admin
def mesin_tarik():
    j = request.get_json(force=True, silent=True) or {}
    c = db()
    if j.get("id"):
        daftar = [dict(r) for r in c.execute("SELECT * FROM mesin WHERE id=?", (j.get("id"),)).fetchall()]
    else:
        daftar = [dict(r) for r in c.execute("SELECT * FROM mesin ORDER BY id").fetchall()]
    c.close()
    if not daftar:
        return jsonify({"ok": False, "pesan": "Belum ada mesin. Masukkan IP mesin dulu."}), 400
    try:
        from zk import ZK
    except ImportError:
        return jsonify({"ok": False,
                        "pesan": "Library pyzk belum terpasang. Jalankan: pip install pyzk lalu ulangi."}), 400
    hasil, total_baru = [], 0
    for m in daftar:
        ip, port = m["ip"], int(m["port"] or 4370)
        ok, msg = _cek_tcp(ip, port)
        if not ok:
            hasil.append(f"{m['nama']}: tidak terhubung ({msg})")
            continue
        try:
            zk = ZK(ip, port=port, timeout=10)
            conn = zk.connect()
            try:
                users = {}
                try:
                    users = {str(u.user_id): (u.name or str(u.user_id)) for u in conn.get_users()}
                except Exception:
                    pass
                att = conn.get_attendance()
            finally:
                try:
                    conn.disconnect()
                except Exception:
                    pass
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
                        "INSERT OR IGNORE INTO absen(nik,waktu,tipe,cara) VALUES(?,?,?,?)",
                        (nik, w, "MASUK", f"mesin:{m['nama']}"))
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
            hasil.append(f"{m['nama']}: {baru} data baru")
        except Exception as e:
            hasil.append(f"{m['nama']}: gagal ({e})")
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
        cur = c.execute("INSERT OR IGNORE INTO absen(nik,waktu,tipe,cara) VALUES(?,?,?,?)",
                        (nik, w, tipe, "demo"))
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
                      COALESCE(p.bagian,'') bagian, a.tipe, a.cara
               FROM absen a LEFT JOIN pegawai p ON p.nik=a.nik
               WHERE a.nik=?
               ORDER BY a.waktu DESC LIMIT ?""", (sendiri, limit)).fetchall()]
        total = c.execute("SELECT COUNT(*) c FROM absen WHERE nik=?", (sendiri,)).fetchone()["c"]
        c.close()
        return jsonify({"total": total, "data": rows})
    if q:
        rows = [dict(r) for r in c.execute(
            """SELECT a.id, a.waktu, a.nik, COALESCE(p.nama, a.nik) nama,
                      COALESCE(p.bagian,'') bagian, a.tipe, a.cara
               FROM absen a LEFT JOIN pegawai p ON p.nik=a.nik
               WHERE a.nik LIKE ? OR p.nama LIKE ? OR p.bagian LIKE ? OR a.waktu LIKE ?
               ORDER BY a.waktu DESC LIMIT ?""",
            (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%", limit)).fetchall()]
    else:
        rows = [dict(r) for r in c.execute(
            """SELECT a.id, a.waktu, a.nik, COALESCE(p.nama, a.nik) nama,
                      COALESCE(p.bagian,'') bagian, a.tipe, a.cara
               FROM absen a LEFT JOIN pegawai p ON p.nik=a.nik
               ORDER BY a.waktu DESC LIMIT ?""", (limit,)).fetchall()]
    total = c.execute("SELECT COUNT(*) c FROM absen").fetchone()["c"]
    c.close()
    return jsonify({"total": total, "data": rows})
