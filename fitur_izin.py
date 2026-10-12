"""UNTUK APA: izin/sakit/cuti/pulang-cepat.
Alur: isi NIK + nama -> pilih jenis -> kirim alasan -> PENDING -> admin klik SETUJU/TOLAK.
API:
- GET  /api/pengajuan?status=PENDING -> list
- POST /api/pengajuan {nik, nama, bagian, tanggal, jenis, ket} -> ajukan
- POST /api/pengajuan/putus {id, aksi:SETUJU/TOLAK} -> putuskan (admin)"""
from datetime import date
from flask import Blueprint, request, jsonify, session
from database import db, simpan_pegawai
from auth import perlu_login, wajib_admin
from config import JENIS_IZIN, normal_bagian

bp_izin = Blueprint("izin", __name__)


@bp_izin.route("/api/pengajuan", methods=["GET", "POST"])
@perlu_login
def pengajuan():
    c = db()
    if request.method == "GET":
        st = (request.args.get("status") or "").upper()
        if session.get("role") != "admin":
            # user biasa hanya lihat pengajuannya sendiri
            rows = [dict(r) for r in c.execute(
                "SELECT p.*, COALESCE(g.nama,p.nik) nama, COALESCE(g.bagian,'') bagian "
                "FROM pengajuan p LEFT JOIN pegawai g ON g.nik=p.nik "
                "WHERE p.nik=? ORDER BY id DESC LIMIT 200",
                (session.get("nik") or "",)).fetchall()]
            c.close()
            if st in ("PENDING", "DISETUJUI", "DITOLAK"):
                rows = [r for r in rows if r["status"] == st]
            return jsonify(rows)
        q = ("SELECT p.*, COALESCE(g.nama,p.nik) nama, COALESCE(g.bagian,'') bagian "
             "FROM pengajuan p LEFT JOIN pegawai g ON g.nik=p.nik")
        args = []
        if st in ("PENDING", "DISETUJUI", "DITOLAK"):
            q += " WHERE status=?"
            args.append(st)
        q += " ORDER BY id DESC LIMIT 200"
        rows = [dict(r) for r in c.execute(q, args).fetchall()]
        c.close()
        return jsonify(rows)
    j = request.get_json(force=True)
    if session.get("role") != "admin":
        # user biasa hanya boleh mengajukan untuk dirinya sendiri
        nik = (session.get("nik") or "").strip()
        if not nik:
            c.close()
            return jsonify({"ok": False,
                            "pesan": "Akun ini belum terikat NIK. Hubungi admin."}), 400
    else:
        nik = str(j.get("nik") or "").strip()
    tgl = str(j.get("tanggal") or date.today().isoformat())[:10]
    jenis = str(j.get("jenis") or "IZIN").upper()
    nama = str(j.get("nama") or "").strip()[:100]
    if not nik:
        c.close()
        return jsonify({"ok": False, "pesan": "NIK wajib"}), 400
    if jenis not in JENIS_IZIN:
        jenis = "IZIN"
    c.execute("INSERT INTO pengajuan(nik,tanggal,jenis,ket) VALUES(?,?,?,?)",
              (nik, tgl, jenis, str(j.get("ket") or "")[:200]))
    # simpan nama + bagian ke data pegawai agar tampil di rekap
    simpan_pegawai(c, nik, nama, normal_bagian(j.get("bagian")))
    c.commit()
    c.close()
    tampil = nama or nik
    return jsonify({"ok": True, "pesan": f"{jenis} {tampil} tgl {tgl} terkirim, tunggu ACC."})


@bp_izin.route("/api/pengajuan/putus", methods=["POST"])
@wajib_admin
def putus():
    j = request.get_json(force=True)
    aksi = str(j.get("aksi") or "").upper()
    st = {"SETUJU": "DISETUJUI", "TOLAK": "DITOLAK"}.get(aksi, aksi)
    if st not in ("DISETUJUI", "DITOLAK"):
        return jsonify({"ok": False, "pesan": "aksi: SETUJU / TOLAK"}), 400
    c = db()
    c.execute("UPDATE pengajuan SET status=? WHERE id=?", (st, j.get("id")))
    c.commit()
    c.close()
    return jsonify({"ok": True, "pesan": f"Jadi {st}."})
