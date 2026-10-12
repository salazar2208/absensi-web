"""UNTUK APA: pintu masuk aplikasi. Jalankan file ini (atau 2x klik mulai.bat).
- daftarkan semua modul fitur (auth, halaman, pegawai, hadir, izin, tarik mesin, laporan)
- $ python app.py -> buka http://127.0.0.1:5000 (admin/admin123)"""
from flask import Flask
from datetime import timedelta
import os
from config import SECRET
from database import db
from auth import bp_auth
from halaman import bp_halaman
from fitur_pegawai import bp_pegawai
from fitur_hadir import bp_hadir
from fitur_izin import bp_izin
from fitur_tarik import bp_tarik
from fitur_laporan import bp_laporan
from fitur_lokasi import bp_lokasi

app = Flask(__name__)
app.secret_key = SECRET
app.permanent_session_lifetime = timedelta(hours=12)
# Otomatis terbaru saat refresh Chrome: template selalu dibaca ulang,
# file static tidak di-cache lama, dan versi ?v= berubah ikut waktu ubah file.
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.context_processor
def _static_ver():
    """Versi otomatis dari waktu ubah file static. Dipakai ?v= di template."""
    try:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
        m = 0
        for nama in os.listdir(base):
            try:
                m = max(m, int(os.path.getmtime(os.path.join(base, nama))))
            except OSError:
                pass
        return {"static_ver": m}
    except Exception:
        return {"static_ver": 0}


@app.after_request
def _tanpa_cache(resp):
    """Cegah Chrome menyajikan HTML/API/JS/CSS basi. Refresh = selalu terbaru."""
    try:
        ct = resp.content_type or ""
        if ("text/html" in ct or "application/json" in ct
                or "javascript" in ct or "text/css" in ct):
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
    except Exception:
        pass
    return resp

app.register_blueprint(bp_auth)
app.register_blueprint(bp_halaman)
app.register_blueprint(bp_pegawai)
app.register_blueprint(bp_hadir)
app.register_blueprint(bp_izin)
app.register_blueprint(bp_tarik)
app.register_blueprint(bp_laporan)
app.register_blueprint(bp_lokasi)

if __name__ == "__main__":
    db().close()
    if SECRET == "ganti-ini":
        print("PERINGATAN: SECRET masih bawaan. Set env ABSENSI_SECRET untuk produksi.")
    port = int(os.environ.get("PORT", "5000"))
    print(f"Buka http://127.0.0.1:{port}  (admin/admin123)")
    print("Tips: ubah koding -> simpan -> refresh Chrome, otomatis terbaru.")
    print("      (server restart sendiri bila file .py berubah)")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True, use_reloader=True)
