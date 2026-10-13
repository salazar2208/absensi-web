"""UNTUK APA: semua pengaturan aplikasi dalam 1 tempat.
Ubah jam masuk / jenis izin / lokasi DB cukup edit file ini."""
import os
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    _WIB = ZoneInfo("Asia/Jakarta")
except Exception:
    _WIB = timezone(timedelta(hours=7))  # WIB = UTC+7, tanpa DST


def wib_now():
    """Waktu sekarang WIB sebagai datetime naive (format sama seperti
    datetime.now() semula, jadi semua kode lama langsung cocok).
    Penting: server Railway berzona UTC, tanpa ini jam absen mundur 7 jam."""
    return datetime.now(_WIB).replace(tzinfo=None)


def wib_today():
    """Tanggal hari ini menurut WIB (bukan UTC)."""
    return wib_now().date()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Lokasi database bisa dipindah via env (wajib saat hosting: arahkan ke volume
# permanen, mis. ABSENSI_DB=/data/absensi.db agar data tidak hilang saat redeploy).
DB = os.environ.get("ABSENSI_DB", os.path.join(BASE_DIR, "absensi.db"))

SECRET = os.environ.get("ABSENSI_SECRET", "ganti-ini")

JAM_MASUK = "08:00"  # patokan telat. 1 shift saja biar simpel.
JENIS_IZIN = ("IZIN", "SAKIT", "CUTI", "PULANG_AWAL")

# --- SHIFT OTOMATIS (ditentukan dari jam scan MASUK pertama hari itu) ---
# Shift 1 = 07:00–19:00 (siang), Shift 2 = 19:00–07:00 (malam).
# Tanpa scan (alpha/izin) -> shift kosong. Ubah via env bila jam pabrik beda:
# ABSENSI_SHIFT_1_AWAL / ABSENSI_SHIFT_1_AKHIR (format "HH:MM").
SHIFT_1_AWAL = os.environ.get("ABSENSI_SHIFT_1_AWAL", "07:00")
SHIFT_1_AKHIR = os.environ.get("ABSENSI_SHIFT_1_AKHIR", "19:00")


def tentukan_shift(jam_masuk):
    """'HH:MM' -> '1' / '2'. Kosong/alpha/izin -> ''.
    Shift 1 = AWAL <= jam < AKHIR, selain itu Shift 2 (termasuk lewat tengah malam)."""
    try:
        j = str(jam_masuk or "").strip()[:5]
        if len(j) != 5 or j[2] != ":":
            return ""
        if SHIFT_1_AWAL <= j < SHIFT_1_AKHIR:
            return "1"
        return "2"
    except Exception:
        return ""

# --- LOKASI KANTOR (default; bisa diubah admin via web, tersimpan di DB) ---
# Diisi koordinat kantor agar absen web bisa dicek radiusnya.
# Contoh Jakarta: -6.200000, 106.816666. Radius meter.
# Default titik kantor (FINAL, jangan diubah manual):
# J32H+3J7, Jayamulya, Serang Baru, Bekasi: -6.399838, 107.079047 (copy persis).
KANTOR_LAT = float(os.environ.get("ABSENSI_LAT", "-6.399838"))
KANTOR_LON = float(os.environ.get("ABSENSI_LON", "107.079047"))
KANTOR_RADIUS_M = int(os.environ.get("ABSENSI_RADIUS_M", "150"))
KANTOR_NAMA = os.environ.get("ABSENSI_KANTOR_NAMA", "PT Injeksi Plastik Pasifik Plant 2")
# Bila 1: absen web WAJIB kirim GPS. Bila 0: boleh tanpa GPS (dianggap PENDING).
LOKASI_WAJIB = os.environ.get("ABSENSI_LOKASI_WAJIB", "1") == "1"


def jarak_meter(lat1, lon1, lat2, lon2):
    """Jarak Haversine meter. Return None bila koordinat tak valid."""
    try:
        import math
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (TypeError, ValueError):
        return None
    # validasi kasar
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90
            and -180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        return None
    if lat1 == 0 and lon1 == 0:
        return None
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))

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
