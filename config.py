"""UNTUK APA: semua pengaturan aplikasi dalam 1 tempat.
Ubah jam masuk / jenis izin / lokasi DB cukup edit file ini."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Lokasi database bisa dipindah via env (wajib saat hosting: arahkan ke volume
# permanen, mis. ABSENSI_DB=/data/absensi.db agar data tidak hilang saat redeploy).
DB = os.environ.get("ABSENSI_DB", os.path.join(BASE_DIR, "absensi.db"))

SECRET = os.environ.get("ABSENSI_SECRET", "ganti-ini")

JAM_MASUK = "08:00"  # patokan telat. 1 shift saja biar simpel.
JENIS_IZIN = ("IZIN", "SAKIT", "CUTI", "PULANG_AWAL")

# Daftar bagian BAKU (sama persis seperti pilihan di web & Excel ABSENSI OPERATOR).
# Semua isian bagian dinormalisasi ke salah satunya agar report rapi.
BAGIAN = ("PRODUCTION", "QA/ QC", "LOGISTIK", "HR/GA", "W/H", "ENGINEERING(NPD)",
          "MARKETING", "FINANCE", "PURCHASING")
_ALIAS_BAGIAN = {
    "PRODUKSI": "PRODUCTION", "PROD": "PRODUCTION",
    "QA/QC": "QA/ QC", "QA QC": "QA/ QC", "QA": "QA/ QC", "QC": "QA/ QC",
    "LOGISTIC": "LOGISTIK",
    "HRGA": "HR/GA", "HR GA": "HR/GA", "HR-GA": "HR/GA", "HR / GA": "HR/GA",
    "WH": "W/H", "W H": "W/H", "W-H": "W/H",
    "ENGINEERING": "ENGINEERING(NPD)", "ENGINNERING": "ENGINEERING(NPD)",
    "ENGINEER": "ENGINEERING(NPD)",
}


def normal_bagian(teks):
    """Kembalikan nama bagian baku (atau '' bila kosong). Tak dikenal -> versi rapi apa adanya."""
    t = " ".join(str(teks or "").upper().split())
    if not t:
        return ""
    if t in BAGIAN:
        return t
    return _ALIAS_BAGIAN.get(t, t)[:60]
