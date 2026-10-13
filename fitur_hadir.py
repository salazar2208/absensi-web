"""UNTUK APA: absen via web + data live + approval lokasi.
API:
- POST /api/checkin {nik, nama, bagian, tipe:MASUK/PULANG, lat, lon} -> absen via web
  (waktu server). Di dalam radius kantor -> DISETUJUI. Di luar / tanpa GPS ->
  PENDING (menunggu ACC admin, seperti izin). Tidak masuk rekap sebelum disetujui.
- POST /api/absen/hapus {id} -> hapus 1 baris scan (admin, untuk koreksi salah tap)
- GET  /api/hari?tgl=YYYY-MM-DD -> rekap 1 hari (hanya DISETUJUI) + pending_lokasi
- GET  /api/monitor -> 20 tap terakhir (live, beserta status lokasi)
Rekap tampil di tab Laporan (/api/ringkas). Approval ada di fitur_lokasi."""
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session
from database import db, simpan_pegawai, get_pengaturan
from auth import perlu_login, wajib_admin
from config import (JAM_MASUK, normal_bagian, wib_now, wib_today, jarak_meter,
                    KANTOR_LAT, KANTOR_LON, KANTOR_RADIUS_M, LOKASI_WAJIB)

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
    # --- LOKASI GPS (wajib bila pengaturan lokasi_wajib=1) ---
    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    lat, lon = _f(j.get("lat")), _f(j.get("lon"))
    akurasi = _f(j.get("akurasi", j.get("accuracy")))
    if akurasi is not None and not (0 <= akurasi <= 100000):
        akurasi = None
    c = db()
    try:
        k_lat = float(get_pengaturan(c, "kantor_lat", str(KANTOR_LAT)))
        k_lon = float(get_pengaturan(c, "kantor_lon", str(KANTOR_LON)))
        k_rad = int(float(get_pengaturan(c, "kantor_radius_m", str(KANTOR_RADIUS_M))))
        k_nama = get_pengaturan(c, "kantor_nama", "Kantor")
        wajib = get_pengaturan(c, "lokasi_wajib", "1" if LOKASI_WAJIB else "0") == "1"
    except Exception:
        k_lat, k_lon, k_rad, k_nama, wajib = KANTOR_LAT, KANTOR_LON, KANTOR_RADIUS_M, "Kantor", LOKASI_WAJIB
    if wajib and (lat is None or lon is None):
        c.close()
        return jsonify({"ok": False,
                        "pesan": "Lokasi GPS wajib. Aktifkan GPS di HP lalu tekan tombol lokasi sebelum kirim."}), 400
    jarak = jarak_meter(lat, lon, k_lat, k_lon) if (lat is not None and lon is not None) else None
    # Aturan akurasi (krusial, anti melenceng & anti curang): fix GPS dengan
    # ketidakpastian LEBIH BESAR dari radius tidak bisa membuktikan posisi
    # di dalam -> PENDING walau titiknya terlihat di dalam. Cth: ±169 m
    # dengan radius 150 m = belum cukup tepat, wajib approval admin.
    if jarak is None:
        status, ket_lok = "PENDING", "tanpa GPS"
    elif jarak > k_rad:
        status, ket_lok = "PENDING", f"{int(jarak)} m dari {k_nama} (radius {k_rad} m)"
    elif akurasi is not None and akurasi > k_rad:
        status, ket_lok = ("PENDING",
                           f"{int(jarak)} m dari {k_nama} tapi akurasi GPS ±{int(akurasi)} m "
                           f"melebihi radius {k_rad} m (fix kurang tepat)")
    else:
        ak_txt = f", ±{int(akurasi)} m" if akurasi is not None else ""
        status, ket_lok = "DISETUJUI", f"{int(jarak)} m dari {k_nama}{ak_txt}"
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
        cur = c.execute(
            "INSERT OR IGNORE INTO absen(nik,waktu,tipe,cara,lat,lon,jarak_m,status,akurasi_m) VALUES(?,?,?,?,?,?,?,?,?)",
            (nik, w, tipe, "aplikasi", lat, lon, jarak, status, akurasi))
        if cur.rowcount:
            break
        w = (datetime.strptime(w, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
    c.commit()
    c.close()
    tampil = nama_tampil or nik
    if status == "DISETUJUI":
        pesan = f"{tipe} {tampil} jam {w[11:16]} tercatat. Lokasi OK ({ket_lok})."
    else:
        saran = (" Coba ke luar ruangan / dekat jendela agar fix GPS tepat, lalu absen ulang."
                 if "akurasi" in ket_lok else "")
        pesan = (f"{tipe} {tampil} jam {w[11:16]} tercatat sebagai PENDING ({ket_lok}).{saran} "
                 f"Menunggu approval admin seperti izin.")
    return jsonify({"ok": True, "waktu": w, "status": status, "jarak_m": jarak,
                    "pesan": pesan})


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
    # Hanya DISETUJUI yang masuk rekap (PENDING lokasi menunggu ACC, DITOLAK diabaikan)
    absen = c.execute("""SELECT nik, MIN(waktu) masuk, MAX(waktu) pulang, COUNT(*) n
        FROM absen WHERE date(waktu)=date(?) AND COALESCE(status,'DISETUJUI')='DISETUJUI'
        GROUP BY nik""", (tgl,)).fetchall()
    a = {r["nik"]: dict(r) for r in absen}
    izin = {r["nik"]: r["jenis"] for r in c.execute(
        "SELECT nik,jenis FROM pengajuan WHERE tanggal=? AND status='DISETUJUI'",
        (tgl,)).fetchall()}
    pending = c.execute(
        "SELECT COUNT(*) c FROM pengajuan WHERE status='PENDING'").fetchone()["c"]
    try:
        if session.get("role") != "admin" and nik_saya:
            pending_lokasi = c.execute(
                "SELECT COUNT(*) c FROM absen WHERE COALESCE(status,'DISETUJUI')='PENDING' AND nik=?",
                (nik_saya,)).fetchone()["c"]
        else:
            pending_lokasi = c.execute(
                "SELECT COUNT(*) c FROM absen WHERE COALESCE(status,'DISETUJUI')='PENDING'").fetchone()["c"]
    except Exception:
        pending_lokasi = 0
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
    return jsonify({"tanggal": tgl, "pending": pending, "pending_lokasi": pending_lokasi,
                    "data": data})


@bp_hadir.route("/api/monitor")
@perlu_login
def monitor():
    c = db()
    nik_saya = (session.get("nik") or "").strip()
    if session.get("role") != "admin" and nik_saya:
        # user terikat NIK: hanya tap miliknya
        rows = [dict(r) for r in c.execute(
            """SELECT a.id, a.waktu, a.nik, COALESCE(p.nama,a.nik) nama,
                      COALESCE(p.bagian,'') bagian, a.tipe, a.cara,
                      a.lat, a.lon, a.jarak_m, a.akurasi_m,
                      COALESCE(a.status,'DISETUJUI') status
               FROM absen a LEFT JOIN pegawai p ON p.nik=a.nik
               WHERE a.nik=? ORDER BY a.waktu DESC LIMIT 20""",
            (nik_saya,)).fetchall()]
        c.close()
        return jsonify(rows)
    # admin, atau user kios: 20 tap terakhir semua orang
    rows = [dict(r) for r in c.execute(
        """SELECT a.id, a.waktu, a.nik, COALESCE(p.nama,a.nik) nama,
                  COALESCE(p.bagian,'') bagian, a.tipe, a.cara,
                  a.lat, a.lon, a.jarak_m, a.akurasi_m,
                  COALESCE(a.status,'DISETUJUI') status
           FROM absen a LEFT JOIN pegawai p ON p.nik=a.nik
           ORDER BY a.waktu DESC LIMIT 20""").fetchall()]
    c.close()
    return jsonify(rows)
