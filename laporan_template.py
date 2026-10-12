"""UNTUK APA: isi file template Excel 'ABSENSI OPERATOR' dengan data database.
ATURAN KERAS (permintaan user: jangan ada yang dirubah dari excel ini):
- Format, rumus, header, sheet lain: DIBIARKAN 100% apa adanya.
- Yang ditulis HANYA sel kode harian + sel keterangan yang masih kosong.
- Sel rumus TIDAK PERNAH ditimpa (di-skip bila ketemu rumus).
- Aturan pewarnaan (conditional formatting) yang tidak bisa dibaca openpyxl
  disalin ulang mentah-mentah dari template (lihat _kembalikan_cf).
- Baris dicocokkan by NAMA (huruf besar, spasi dirapikan).
- Kode: SAKIT->S, IZIN/CUTI->I, PULANG_AWAL->PA, ada scan->kosong (hadir),
  tidak ada scan + sel kosong->A, sel sudah berisi (OFF/dll)->dibiarkan.
"""
import io
import re
import os
import zipfile
from datetime import date

import openpyxl

from config import DB
from database import db

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template_absensi.xlsx")

# bulan -> nama sheet di template (urutan = prioritas)
BULAN_SHEET = {
    1: ("JAN",), 2: ("FEB",), 3: ("MAR",), 4: ("APRIL",), 5: ("MEI",),
    6: ("JUNI",), 7: ("JULI",), 8: ("AGT",), 9: ("SEP", "sep"),
    10: ("OKT", "oct"), 11: ("nov", "NOV"), 12: ("DES",),
}

KODE_IZIN = {"SAKIT": "S", "IZIN": "I", "CUTI": "I", "PULANG_AWAL": "PA"}


def template_ada():
    return os.path.exists(TEMPLATE)


def _norm(nama):
    return " ".join(str(nama or "").upper().split())


def _cari_sheet(wb, bulan):
    for nama in BULAN_SHEET.get(bulan, ()):
        if nama in wb.sheetnames:
            return wb[nama]
    atas = [n.upper() for n in BULAN_SHEET.get(bulan, ())]
    for s in wb.sheetnames:
        if s.strip().upper() in atas:
            return wb[s]
    return None


def _petakan_sheet(ws):
    """Kembalikan {nama_col, tgl:[(col, hari)], total_col, awal} atau None."""
    for r in range(1, 25):
        for c in range(1, 8):
            v = ws.cell(r, c).value
            if isinstance(v, str) and v.strip().upper() == "NAMA":
                tgl = []
                for cc in range(1, ws.max_column + 1):
                    dv = ws.cell(r + 1, cc).value
                    if isinstance(dv, int) and 1 <= dv <= 31:
                        tgl.append((cc, dv))
                    elif isinstance(dv, float) and float(dv).is_integer() and 1 <= int(dv) <= 31:
                        tgl.append((cc, int(dv)))
                if not tgl:
                    return None
                total_col = None
                for cc in range(1, ws.max_column + 1):
                    hv = ws.cell(r, cc).value
                    if isinstance(hv, str) and hv.strip().upper() == "TOTAL":
                        total_col = cc
                        break
                return {"nama_col": c, "tgl": tgl, "total_col": total_col, "awal": r + 2}
    return None


def _urutan_sheet(path):
    """Urutan nama sheet sesuai workbook.xml (agar petak file sheetN.xml tepat)."""
    z = zipfile.ZipFile(path)
    x = z.read("xl/workbook.xml").decode("utf8", "ignore")
    return re.findall(r'<sheet[^>]* name="([^"]+)"', x)


def _kembalikan_cf(buf_out):
    """Salin ulang blok <conditionalFormatting> yang gugur saat dibaca openpyxl.
    openpyxl membuang aturan dgn sqref multi-range; blok aslinya disisipkan
    kembali mentah-mentah (dxfId tetap valid karena dxf ikut tersimpan)."""
    try:
        names_t = _urutan_sheet(TEMPLATE)
    except Exception:
        return buf_out
    try:
        z_out = zipfile.ZipFile(io.BytesIO(buf_out.getvalue()))
        names_o = re.findall(r'<sheet[^>]* name="([^"]+)"',
                             z_out.read("xl/workbook.xml").decode("utf8", "ignore"))
    except Exception:
        return buf_out
    if names_t != names_o:
        return buf_out  # jaga-jaga: urutan beda, jangan sentuh
    files = [f"xl/worksheets/sheet{i}.xml" for i in range(1, len(names_o) + 1)]
    try:
        z_tpl = zipfile.ZipFile(TEMPLATE)
    except Exception:
        return buf_out
    ganti = {}
    for f in files:
        try:
            asli = z_tpl.read(f).decode("utf8")
            hasil = z_out.read(f).decode("utf8")
        except KeyError:
            continue
        blok_asli = re.findall(r'<conditionalFormatting\s+sqref="([^"]+)".*?</conditionalFormatting>',
                               asli, re.S)
        # yang gugur = sqref multi-range yg tak bisa dibaca openpyxl -> tak ada di hasil
        hilang = []
        for m in re.finditer(r'<conditionalFormatting\s+sqref="([^"]+)".*?</conditionalFormatting>',
                             asli, re.S):
            if f'sqref="{m.group(1)}"' not in hasil:
                hilang.append(m.group(0))
        if not hilang:
            continue
        sisip = "".join(hilang)
        for jangkar in ("<dataValidations", "<printOptions", "<pageMargins", "</worksheet>"):
            if jangkar in hasil:
                hasil = hasil.replace(jangkar, sisip + jangkar, 1)
                break
        ganti[f] = hasil.encode("utf8")
    if not ganti:
        return buf_out
    baru = io.BytesIO()
    with zipfile.ZipFile(baru, "w", zipfile.ZIP_DEFLATED) as zw:
        for item in z_out.infolist():
            data = ganti.get(item.filename, z_out.read(item.filename))
            zw.writestr(item, data)
    baru.seek(0)
    return baru


def _periode(sheet_bulan, tahun, hari):
    try:
        if hari > 20:
            b = sheet_bulan - 1 or 12
            t = tahun - 1 if sheet_bulan == 1 else tahun
        else:
            b, t = sheet_bulan, tahun
        return date(t, b, hari)
    except ValueError:
        return None  # mis. tgl 31 di bulan 30 hari: kolom dilewati


def isi_template(dari, sampai, q="", nik_sendiri=None):
    """Isi template, kembalikan (BytesIO, nama_sheet, jml_sel_terisi, jml_orang_cocok).
    nik_sendiri: bila bukan admin, hanya NIK itu yang diisi."""
    if not template_ada():
        raise FileNotFoundError("template_absensi.xlsx tidak ditemukan.")
    bulan = sampai.month
    wb = openpyxl.load_workbook(TEMPLATE)
    ws = _cari_sheet(wb, bulan)
    if ws is None:
        raise ValueError(f"Sheet bulan {sampai:%B} tidak ada di template.")
    peta = _petakan_sheet(ws)
    if peta is None:
        raise ValueError(f"Struktur sheet {ws.title} tidak dikenali.")

    a, b = dari.isoformat(), sampai.isoformat()
    c = db()
    if nik_sendiri:
        peg = [dict(r) for r in c.execute(
            "SELECT nik, nama, COALESCE(bagian,'') bagian FROM pegawai WHERE nik=?",
            (nik_sendiri,)).fetchall()]
        hadir = {(r["nik"], r["t"]) for r in c.execute(
            "SELECT nik, substr(waktu,1,10) t FROM absen "
            "WHERE nik=? AND date(waktu) BETWEEN ? AND ? GROUP BY nik, t",
            (nik_sendiri, a, b)).fetchall()}
        cuti = {(r["nik"], r["tanggal"]): (r["jenis"], r["ket"] or "") for r in c.execute(
            "SELECT nik, tanggal, jenis, ket FROM pengajuan "
            "WHERE status='DISETUJUI' AND nik=? AND tanggal BETWEEN ? AND ?",
            (nik_sendiri, a, b)).fetchall()}
    else:
        like = f"%{q}%"
        peg = [dict(r) for r in c.execute(
            "SELECT nik, nama, COALESCE(bagian,'') bagian FROM pegawai "
            "WHERE ?='' OR nik LIKE ? OR nama LIKE ? OR bagian LIKE ? ORDER BY nik",
            (q, like, like, like)).fetchall()]
        hadir = {(r["nik"], r["t"]) for r in c.execute(
            "SELECT a.nik, substr(a.waktu,1,10) t FROM absen a "
            "LEFT JOIN pegawai p ON p.nik=a.nik "
            "WHERE date(a.waktu) BETWEEN ? AND ? "
            "AND (?='' OR a.nik LIKE ? OR COALESCE(p.nama,'') LIKE ? OR COALESCE(p.bagian,'') LIKE ?) "
            "GROUP BY a.nik, t",
            (a, b, q, like, like, like)).fetchall()}
        cuti = {(r["nik"], r["tanggal"]): (r["jenis"], r["ket"] or "") for r in c.execute(
            "SELECT nik, tanggal, jenis, ket FROM pengajuan "
            "WHERE status='DISETUJUI' AND tanggal BETWEEN ? AND ?",
            (a, b)).fetchall()}
    c.close()

    nama_ke_nik = {}
    for p in peg:
        nm = _norm(p["nama"] or p["nik"])
        nama_ke_nik.setdefault(nm, p["nik"])

    # cocokkan baris template -> nik
    baris = {}
    for r in range(peta["awal"], ws.max_row + 1):
        nm = _norm(ws.cell(r, peta["nama_col"]).value)
        if nm and nm in nama_ke_nik and nama_ke_nik[nm] not in baris:
            baris[nama_ke_nik[nm]] = r

    ket_col = (peta["total_col"] + 1) if peta["total_col"] else None
    n_sel = 0
    for nik, r in baris.items():
        kets = []
        for cc, hari in peta["tgl"]:
            p = _periode(bulan, sampai.year, hari)
            if p is None:
                continue
            tgl = p.isoformat()
            if tgl < a or tgl > b:
                continue
            sel = ws.cell(r, cc)
            if sel.data_type == "f":
                continue  # jangan pernah timpa rumus
            key = (nik, tgl)
            if key in cuti:
                sel.value = KODE_IZIN.get(cuti[key][0], "I")
                if cuti[key][1].strip():
                    kets.append(cuti[key][1].strip())
                n_sel += 1
            elif key in hadir:
                if sel.value not in (None, ""):
                    sel.value = None  # hadir = kosong
                n_sel += 1
            elif sel.value in (None, ""):
                sel.value = "A"
                n_sel += 1
        if kets and ket_col:
            ksel = ws.cell(r, ket_col)
            if ksel.data_type != "f" and ksel.value in (None, ""):
                ksel.value = "; ".join(dict.fromkeys(kets))[:200]

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf = _kembalikan_cf(buf)
    return buf, ws.title, n_sel, len(baris)
