"""UNTUK APA: absen via web + data live.
API:
- POST /api/checkin {nik, nama, bagian, tipe:MASUK/PULANG} -> absen via web (waktu server)
- POST /api/absen/hapus {id} -> hapus 1 baris scan (admin, untuk koreksi salah tap)
- GET  /api/hari?tgl=YYYY-MM-DD -> rekap 1 hari (dipakai internal)
- GET  /api/monitor -> 20 tap terakhir (live)
Rekap tampil di tab Laporan (/api/ringkas)."""
from datetime import datetime, date, timedelta
from flask import Blueprint, request, jsonify, session
from database import db, simpan_pegawai
from auth import perlu_login, wajib_admin
from config import JAM_MASUK, normal_bagian, wib_now, wib_today

bp_hadir = Blueprint("hadir", __name__)


@bp_hadir.route("/api/checkin", methods=["POST"])
@perlu_login
def checkin():
    import re
    j = request.get_json(force=True, silent=True) or {}
    terikat = (session.get("nik") or "").strip() if session.get("role") != "admin" else ""
    if session.get("role") != "admin" and terikat:
        # user terikat NIK: absen hanya untuk dirinya sendiri.
        # NIK/nama kiriman diabaikan agar saran dropdown tidak bisa
        # menimpa data orang lain.
        nik = terikat
        nama_kirim, bagian_kirim, kios = "", "", False
    else:
        # admin, atau user kios (akun user tanpa NIK terikat, mis. tablet lobi):
        # NIK dari form/saran.
        nik = str(j.get("nik") or "").strip()
        if not nik:
            if session.get("role") != "admin":
                return jsonify({"ok": False,
                                "pesan": "Pilih NIK pegawai dulu."}), 400
            return jsonify({"ok": False, "pesan": "NIK wajib"}), 400
        nama_kirim, bagian_kirim = str(j.get("nama") or "").strip()[:100], j.get("bagian")
        kios = session.get("role") != "admin"
    if not re.match(r"^[\w\-.]{1,30}$", nik):
        return jsonify({"ok": False, "pesan": "NIK tidak valid (maks 30 karakter huruf/angka/titik/strip)."}), 400
    tipe = "PULANG" if str(j.get("tipe", "")).upper() == "PULANG" else "MASUK"
    c = db()
    # Tahan dobel-klik saja: tolak bila tap terakhir < 10 detik DAN tipenya sama.
    # Beda tipe (cth. salah pilih MASUK lalu betulkan PULANG) langsung lolos,
    # dan NIK berbeda tidak saling menahan sehingga absen barengan tetap bisa.
    last = c.execute("SELECT waktu, tipe FROM absen WHERE nik=? ORDER BY waktu DESC LIMIT 1",
                     (nik,)).fetchone()
    if last:
        try:
            selisih = (wib_now() - datetime.strptime(last["waktu"], "%Y-%m-%d %H:%M:%S")).total_seconds()
            if selisih < 10 and (last["tipe"] or "MASUK") == tipe:
                c.close()
                return jsonify({"ok": False,
                                "pesan": f"Sudah tercatat {tipe} jam {last['waktu'][11:16]}. "
                                         f"Tunggu {int(10 - selisih)} detik lagi bila terketuk 2x."}), 429
        except Exception:
            pass
    w = wib_now().strftime("%Y-%m-%d %H:%M:%S")
    # Daftarkan pegawai DULU sebelum catat absen (wajib untuk foreign key MySQL).
    # User terikat: jangan timpa (cukup pastikan barisnya ada) agar saran
    # tidak merusak namanya sendiri. Admin/kios: simpan seperti biasa.
    if session.get("role") != "admin" and terikat:
        simpan_pegawai(c, nik)
        p = c.execute("SELECT nama FROM pegawai WHERE nik=?", (nik,)).fetchone()
        nama_tampil = (p["nama"] if p and p["nama"] else nik)
    else:
        nama = nama_kirim if session.get("role") != "admin" else str(j.get("nama") or "").strip()[:100]
        bagian_in = bagian_kirim if session.get("role") != "admin" else j.get("bagian")
        simpan_pegawai(c, nik, nama, normal_bagian(bagian_in))
        nama_tampil = nama or nik
    for _ in range(5):  # kunci unik (nik, waktu) per detik: geser bila detik ini sudah terisi
        cur = c.execute("INSERT OR IGNORE INTO absen(nik,waktu,tipe,cara) VALUES(?,?,?,?)",
                        (nik, w, tipe, "aplikasi"))
        if cur.rowcount:
            break
        w = (datetime.strptime(w, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
    c.commit()
    c.close()
    tampil = nama_tampil or nik
    return jsonify({"ok": True, "waktu": w, "pesan": f"{tipe} {tampil} jam {w[11:16]} tercatat."})


@bp_hadir.route("/api/saya")
@perlu_login
def saya():
    """Identitas pemilik akun: NIK yang terikat + nama/bagian bila sudah terdaftar.
    Dipakai form agar NIK/nama terisi sendiri (datalist = saran, ketik manual tetap bisa)."""
    nik = (session.get("nik") or "").strip()
    nama, bagian = "", ""
    if nik:
        c = db()
        p = c.execute("SELECT nama, COALESCE(bagian,'') bagian FROM pegawai WHERE nik=?",
                      (nik,)).fetchone()
        c.close()
        if p:
            nama, bagian = p["nama"] or "", p["bagian"] or ""
    return jsonify({"nik": nik, "nama": nama, "bagian": bagian,
                    "username": session.get("username") or "",
                    "role": session.get("role") or ""})


@bp_hadir.route("/api/absen/hapus", methods=["POST"])
@wajib_admin
def hapus_satu():
    """Hapus 1 baris scan untuk koreksi (mis. salah tap / data ganda)."""
    j = request.get_json(force=True, silent=True) or {}
    try:
        rid = int(j.get("id") or 0)
    except Exception:
        rid = 0
    if not rid:
        return jsonify({"ok": False, "pesan": "ID baris wajib."}), 400
    c = db()
    r = c.execute("SELECT nik, waktu FROM absen WHERE id=?", (rid,)).fetchone()
    if not r:
        c.close()
        return jsonify({"ok": False, "pesan": "Baris tidak ditemukan."}), 404
    c.execute("DELETE FROM absen WHERE id=?", (rid,))
    c.commit()
    c.close()
    return jsonify({"ok": True, "pesan": f"Scan {r['nik']} jam {r['waktu']} dihapus."})


@bp_hadir.route("/api/hari")
@perlu_login
def hari():
    tgl = request.args.get("tgl", wib_today().isoformat())[:10]
    c = db()
    nik_saya = (session.get("nik") or "").strip()
    if session.get("role") != "admin" and nik_saya:
        # user terikat NIK: hanya barisnya sendiri
        peg = [dict(r) for r in c.execute(
            "SELECT nik, nama, COALESCE(bagian,'') bagian FROM pegawai WHERE nik=?",
            (nik_saya,)).fetchall()]
    else:
        # admin, atau user kios (tablet lobi tanpa NIK terikat): semua orang
        # agar habis absen langsung terlihat di layar
        peg = [dict(r) for r in c.execute(
            "SELECT nik, nama, COALESCE(bagian,'') bagian FROM pegawai ORDER BY nik").fetchall()]
    absen = c.execute("""SELECT nik, MIN(waktu) masuk, MAX(waktu) pulang, COUNT(*) n
        FROM absen WHERE date(waktu)=date(?) GROUP BY nik""", (tgl,)).fetchall()
    a = {r["nik"]: dict(r) for r in absen}
    izin = {r["nik"]: r["jenis"] for r in c.execute(
        "SELECT nik,jenis FROM pengajuan WHERE tanggal=? AND status='DISETUJUI'",
        (tgl,)).fetchall()}
    pending = c.execute(
        "SELECT COUNT(*) c FROM pengajuan WHERE status='PENDING'").fetchone()["c"]
    c.close()
    data = []
    for p in peg:
        nik = p["nik"]
        bagian = p.get("bagian", "") or ""
        if nik in izin:
            data.append({"nik": nik, "nama": p["nama"], "bagian": bagian,
                         "masuk": "-", "pulang": "-", "status": izin[nik]})
        elif nik not in a:
            data.append({"nik": nik, "nama": p["nama"], "bagian": bagian,
                         "masuk": "-", "pulang": "-", "status": "Alpha"})
        else:
            m = a[nik]["masuk"][11:16]
            pl = a[nik]["pulang"][11:16] if a[nik]["n"] > 1 else "-"
            st = "Hadir" if m <= JAM_MASUK else f"Telat {m}"
            if a[nik]["n"] < 2:
                st += " (1x tap)"
            data.append({"nik": nik, "nama": p["nama"], "bagian": bagian,
                         "masuk": m, "pulang": pl, "status": st})
    return jsonify({"tanggal": tgl, "pending": pending, "data": data})


@bp_hadir.route("/api/monitor")
@perlu_login
def monitor():
    c = db()
    nik_saya = (session.get("nik") or "").strip()
    if session.get("role") != "admin" and nik_saya:
        # user terikat NIK: hanya tap miliknya
        rows = [dict(r) for r in c.execute(
            """SELECT a.id, a.waktu, a.nik, COALESCE(p.nama,a.nik) nama,
                      COALESCE(p.bagian,'') bagian, a.tipe, a.cara
               FROM absen a LEFT JOIN pegawai p ON p.nik=a.nik
               WHERE a.nik=? ORDER BY a.waktu DESC LIMIT 20""",
            (nik_saya,)).fetchall()]
        c.close()
        return jsonify(rows)
    # admin, atau user kios: 20 tap terakhir semua orang
    rows = [dict(r) for r in c.execute(
        """SELECT a.id, a.waktu, a.nik, COALESCE(p.nama,a.nik) nama,
                  COALESCE(p.bagian,'') bagian, a.tipe, a.cara
           FROM absen a LEFT JOIN pegawai p ON p.nik=a.nik
           ORDER BY a.waktu DESC LIMIT 20""").fetchall()]
    c.close()
    return jsonify(rows)
