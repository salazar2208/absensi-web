"""UNTUK APA: data pegawai (daftar orang). KHUSUS ADMIN.
API:
- GET  /api/pegawai -> list [{nik, nama, bagian}]
- POST /api/pegawai {nik, nama, bagian} -> daftarkan/ubah orang
- POST /api/pegawai {nik, hapus:1} -> hapus orang
- GET  /api/pegawai/belum -> NIK mesin yang belum terdaftar [{nik, jml}]
- GET  /api/pegawai/detail?nik=... -> detail 1 pegawai + riwayat"""
from flask import Blueprint, request, jsonify, session
from database import db, simpan_pegawai
from auth import wajib_admin
from config import normal_bagian

bp_pegawai = Blueprint("pegawai", __name__)


@bp_pegawai.route("/api/pegawai", methods=["GET", "POST"])
@wajib_admin
def pegawai():
    c = db()
    if request.method == "GET":
        rows = [dict(r) for r in c.execute(
            "SELECT nik, nama, COALESCE(bagian,'') bagian FROM pegawai ORDER BY nik").fetchall()]
        c.close()
        return jsonify(rows)
    # simpan/hapus: khusus admin (dipakai tab Daftar)
    j = request.get_json(force=True, silent=True) or {}
    if j.get("hapus") and isinstance(j.get("niks"), list):
        # hapus banyak sekaligus (data absen tidak ikut terhapus)
        niks = [str(x).strip()[:30] for x in j.get("niks") if str(x).strip()][:500]
        if not niks:
            c.close()
            return jsonify({"ok": False, "pesan": "Tidak ada baris yang dipilih."}), 400
        c.execute(f"DELETE FROM pegawai WHERE nik IN ({','.join('?' * len(niks))})", niks)
        n = c.total_changes
        c.commit()
        c.close()
        return jsonify({"ok": True, "hapus": n, "pesan": f"{n} orang dihapus dari daftar."})
    nik = (j.get("nik") or "").strip()[:30]
    nama = (j.get("nama") or nik).strip()[:100]
    bagian = normal_bagian(j.get("bagian"))
    if not nik:
        c.close()
        return jsonify({"ok": False, "pesan": "NIK wajib"}), 400
    if j.get("hapus"):
        c.execute("DELETE FROM pegawai WHERE nik=?", (nik,))
        c.commit()
        c.close()
        return jsonify({"ok": True, "pesan": f"{nik} dihapus dari daftar."})
    simpan_pegawai(c, nik, nama, bagian)
    c.commit()
    c.close()
    return jsonify({"ok": True, "pesan": f"{nama or nik} ({bagian or '-'}) terdaftar."})


@bp_pegawai.route("/api/pegawai/impor", methods=["POST"])
@wajib_admin
def pegawai_impor():
    """Daftar banyak orang sekaligus. Satu baris satu orang:
    'NIK, Nama, Bagian' (bagian boleh kosong). NIK yang sama memperbarui."""
    import re
    j = request.get_json(force=True, silent=True) or {}
    n = 0
    c = db()
    for baris in str(j.get("teks") or "").splitlines():
        baris = baris.strip()
        if not baris:
            continue
        pot = re.split(r"\s*[,;\t|]\s*", baris, maxsplit=2)
        if len(pot) >= 2 and pot[0].strip() and pot[1].strip():
            simpan_pegawai(c, pot[0].strip()[:30], pot[1].strip()[:100],
                           normal_bagian(pot[2] if len(pot) > 2 else ""))
            n += 1
    c.commit()
    c.close()
    return jsonify(ok=n > 0,
                   pesan=f"{n} orang terdaftar." if n else
                   "Tidak ada baris valid. Format satu baris: NIK, Nama, Bagian.")


@bp_pegawai.route("/api/pegawai/belum")
@wajib_admin
def pegawai_belum():
    """NIK yang ada di mesin/absen tapi belum didaftarkan (belum punya nama).
    Dipakai tab Daftar agar tinggal klik untuk mendaftarkan."""
    c = db()
    rows = [dict(r) for r in c.execute(
        """SELECT a.nik, COUNT(*) jml FROM absen a LEFT JOIN pegawai p ON p.nik=a.nik
           WHERE p.nik IS NULL GROUP BY a.nik ORDER BY jml DESC LIMIT 100""").fetchall()]
    c.close()
    return jsonify(rows)


@bp_pegawai.route("/api/pegawai/detail")
@wajib_admin
def pegawai_detail():
    """Detail 1 pegawai (khusus admin)."""
    nik = (request.args.get("nik") or "").strip()
    if session.get("role") != "admin":
        nik = session.get("nik") or ""
    if not nik:
        return jsonify({"ok": False, "pesan": "Akun ini belum terikat NIK. Hubungi admin."}), 400
    c = db()
    p = c.execute("SELECT nik, nama, COALESCE(bagian,'') bagian FROM pegawai WHERE nik=?",
                  (nik,)).fetchone()
    if not p:
        c.close()
        return jsonify({"ok": False, "pesan": "Pegawai tidak ditemukan."}), 404
    riwayat = [dict(r) for r in c.execute(
        "SELECT waktu, tipe, cara FROM absen WHERE nik=? ORDER BY waktu DESC LIMIT 10",
        (nik,)).fetchall()]
    total = c.execute("SELECT COUNT(*) c FROM absen WHERE nik=?", (nik,)).fetchone()["c"]
    hadir = c.execute("SELECT COUNT(DISTINCT substr(waktu,1,10)) c FROM absen WHERE nik=?",
                      (nik,)).fetchone()["c"]
    izin = [dict(r) for r in c.execute(
        "SELECT tanggal, jenis, status FROM pengajuan WHERE nik=? ORDER BY tanggal DESC LIMIT 10",
        (nik,)).fetchall()]
    c.close()
    return jsonify({"ok": True, "nik": p["nik"], "nama": p["nama"], "bagian": p["bagian"],
                    "total_tap": total, "total_hari": hadir,
                    "riwayat": riwayat, "pengajuan": izin})
