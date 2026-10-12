"""UNTUK APA: lokasi kantor + approval absen di luar radius.
Alur (mirip izin, tapi untuk LOKASI):
- Admin atur titik kantor (lat/lon/radius/nama) sekali via web.
- Karyawan absen via web WAJIB kirim GPS (browser).
- Di dalam radius -> langsung DISETUJUI (masuk rekap).
- Di luar radius / tanpa GPS -> PENDING, tidak masuk rekap sebelum admin ACC.
API:
- GET  /api/lokasi -> setting kantor (semua yg login, untuk hitung jarak di HP)
- POST /api/lokasi {lat, lon, radius_m, nama, wajib} -> simpan (admin)
- GET  /api/absen/pending -> daftar PENDING (admin: semua, user: miliknya)
- POST /api/absen/putus {id, aksi:SETUJU/TOLAK} -> putuskan (admin)
- GET  /api/absen/pending_count -> badge notif (seperti izin)"""
from flask import Blueprint, request, jsonify, session
from database import db, get_pengaturan
from auth import perlu_login, wajib_admin
from config import KANTOR_LAT, KANTOR_LON, KANTOR_RADIUS_M, KANTOR_NAMA, LOKASI_WAJIB

bp_lokasi = Blueprint("lokasi", __name__)


def _setting(c):
    """Baca setting kantor dari DB (fallback ke config.py)."""
    def ambil(k, cad):
        try:
            return get_pengaturan(c, k, str(cad))
        except Exception:
            return str(cad)
    try:
        lat = float(ambil("kantor_lat", KANTOR_LAT))
    except ValueError:
        lat = KANTOR_LAT
    try:
        lon = float(ambil("kantor_lon", KANTOR_LON))
    except ValueError:
        lon = KANTOR_LON
    try:
        radius = int(float(ambil("kantor_radius_m", KANTOR_RADIUS_M)))
    except ValueError:
        radius = KANTOR_RADIUS_M
    if radius > 150:
        radius = 150  # batas maksimal 150 m (nilai lama yang lebih besar dijepit)
    nama = ambil("kantor_nama", KANTOR_NAMA)
    wajib = ambil("lokasi_wajib", "1" if LOKASI_WAJIB else "0") == "1"
    return {"lat": lat, "lon": lon, "radius_m": radius, "nama": nama, "wajib": wajib}


@bp_lokasi.route("/api/lokasi")
@perlu_login
def lokasi_get():
    c = db()
    s = _setting(c)
    c.close()
    return jsonify({"ok": True, **s})


@bp_lokasi.route("/api/lokasi", methods=["POST"])
@wajib_admin
def lokasi_set():
    j = request.get_json(force=True, silent=True) or {}
    try:
        lat = float(j.get("lat"))
        lon = float(j.get("lon"))
        radius = int(float(j.get("radius_m", j.get("radius", 100))))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "pesan": "lat/lon/radius tidak valid."}), 400
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({"ok": False, "pesan": "lat -90..90, lon -180..180."}), 400
    if not 10 <= radius <= 150:
        return jsonify({"ok": False, "pesan": "Radius 10-150 meter (maksimal 150 m)."}), 400
    nama = str(j.get("nama") or "Kantor").strip()[:60] or "Kantor"
    wajib = "1" if str(j.get("wajib", "1")).lower() not in ("0", "false", "tidak") else "0"
    c = db()
    for k, v in (("kantor_lat", str(lat)), ("kantor_lon", str(lon)),
                 ("kantor_radius_m", str(radius)), ("kantor_nama", nama),
                 ("lokasi_wajib", wajib)):
        try:
            ada = c.execute("SELECT 1 FROM pengaturan WHERE kunci=?", (k,)).fetchone()
            if ada:
                c.execute("UPDATE pengaturan SET nilai=? WHERE kunci=?", (v, k))
            else:
                c.execute("INSERT INTO pengaturan(kunci,nilai) VALUES(?,?)", (k, v))
        except Exception:
            # tabel pengaturan belum ada (DB sangat lama): buat lalu ulangi
            try:
                c.execute("CREATE TABLE IF NOT EXISTS pengaturan(kunci TEXT PRIMARY KEY, nilai TEXT DEFAULT '')")
                c.execute("INSERT OR IGNORE INTO pengaturan(kunci,nilai) VALUES(?,?)", (k, v))
            except Exception:
                pass
    c.commit()
    c.close()
    return jsonify({"ok": True, "pesan": f"Titik {nama} tersimpan ({lat}, {lon}, radius {radius} m)."})


@bp_lokasi.route("/api/absen/pending")
@perlu_login
def absen_pending():
    """Daftar absen PENDING lokasi. Admin: semua. User terikat: miliknya."""
    c = db()
    nik_saya = (session.get("nik") or "").strip()
    if session.get("role") != "admin" and nik_saya:
        rows = [dict(r) for r in c.execute(
            """SELECT a.id, a.waktu, a.nik, COALESCE(p.nama,a.nik) nama,
                      COALESCE(p.bagian,'') bagian, a.tipe, a.cara,
                      a.lat, a.lon, a.jarak_m, a.status, a.akurasi_m
               FROM absen a LEFT JOIN pegawai p ON p.nik=a.nik
               WHERE a.status='PENDING' AND a.nik=? ORDER BY a.waktu DESC LIMIT 200""",
            (nik_saya,)).fetchall()]
    else:
        rows = [dict(r) for r in c.execute(
            """SELECT a.id, a.waktu, a.nik, COALESCE(p.nama,a.nik) nama,
                      COALESCE(p.bagian,'') bagian, a.tipe, a.cara,
                      a.lat, a.lon, a.jarak_m, a.status, a.akurasi_m
               FROM absen a LEFT JOIN pegawai p ON p.nik=a.nik
               WHERE a.status='PENDING' ORDER BY a.waktu DESC LIMIT 200""").fetchall()]
    c.close()
    return jsonify(rows)


@bp_lokasi.route("/api/absen/pending_count")
@perlu_login
def absen_pending_count():
    """Jumlah PENDING lokasi untuk badge. Admin: total. User: miliknya."""
    nik_saya = (session.get("nik") or "").strip()
    c = db()
    try:
        if session.get("role") != "admin" and nik_saya:
            n = c.execute("SELECT COUNT(*) c FROM absen WHERE status='PENDING' AND nik=?",
                          (nik_saya,)).fetchone()["c"]
        else:
            n = c.execute("SELECT COUNT(*) c FROM absen WHERE status='PENDING'").fetchone()["c"]
    except Exception:
        n = 0
    c.close()
    return jsonify({"pending": n})


@bp_lokasi.route("/api/absen/putus", methods=["POST"])
@wajib_admin
def absen_putus():
    """SETUJU -> DISETUJUI (masuk rekap). TOLAK -> DITOLAK (tidak masuk rekap)."""
    j = request.get_json(force=True, silent=True) or {}
    aksi = str(j.get("aksi") or "").upper()
    st = {"SETUJU": "DISETUJUI", "TOLAK": "DITOLAK"}.get(aksi, aksi)
    if st not in ("DISETUJUI", "DITOLAK"):
        return jsonify({"ok": False, "pesan": "aksi: SETUJU / TOLAK"}), 400
    try:
        rid = int(j.get("id") or 0)
    except (TypeError, ValueError):
        rid = 0
    if not rid:
        return jsonify({"ok": False, "pesan": "ID baris wajib."}), 400
    c = db()
    r = c.execute("SELECT nik, waktu FROM absen WHERE id=?", (rid,)).fetchone()
    if not r:
        c.close()
        return jsonify({"ok": False, "pesan": "Baris tidak ditemukan."}), 404
    c.execute("UPDATE absen SET status=? WHERE id=?", (st, rid))
    c.commit()
    c.close()
    return jsonify({"ok": True, "pesan": f"Absen {r['nik']} jam {r['waktu']} jadi {st}."})
