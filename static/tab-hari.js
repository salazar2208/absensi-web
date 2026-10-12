/* UNTUK APA: tab Hari Ini saja (absen via web + data live).
   Rekap ada di tab Unduh Laporan. */

/* --- Saran NIK terdaftar (ketik NIK -> nama terisi sendiri) --- */
let _saran = [];
async function loadSaran() {
  try {
    if (!ada("a-saran")) return;
    _saran = await get("/api/pegawai/saran");
    const opsi = _saran.map((p) => `<option value="${esc(p.nik)}">${esc(p.nama)}${p.bagian ? " • " + esc(p.bagian) : ""}</option>`
    ).join("");
    $("a-saran").innerHTML = opsi;
    if (ada("j-saran")) $("j-saran").innerHTML = opsi; // saran NIK form izin juga
    // dropdown pilih pegawai (seperti dropdown Bagian): pilihan tidak hilang saat refresh
    const opsiPilih = `<option value="">— atau ketik NIK manual di bawah —</option>` + _saran.map((p) =>
      `<option value="${esc(p.nik)}">${esc(p.nik)} — ${esc(p.nama)}${p.bagian ? " • " + esc(p.bagian) : ""}</option>`
    ).join("");
    ["a-pilih", "j-pilih"].forEach((id) => {
      if (!ada(id)) return;
      const cur = $(id).value;
      $(id).innerHTML = opsiPilih;
      if (cur && Array.from($(id).options).some((o) => o.value === cur)) $(id).value = cur;
    });
  } catch (e) { /* abaikan */ }
}
/* --- Pilih dari dropdown pegawai -> NIK + nama + bagian terisi (tetap bisa diubah manual) --- */
function pilihSaran(awalan) {
  const sel = $(awalan + "-pilih");
  if (!sel || !sel.value) return;
  const cocok = _saran.find((p) => String(p.nik) === sel.value);
  const iNik = $(awalan + "-nik"), iNama = $(awalan + "-nama"), iBag = $(awalan + "-bagian");
  if (iNik) iNik.value = sel.value;
  if (!cocok) return;
  if (iNama) iNama.value = cocok.nama || "";
  if (iBag && cocok.bagian &&
      Array.from(iBag.options).some((o) => o.value === cocok.bagian)) iBag.value = cocok.bagian;
}
function isiOtomatis() {
  if (!ada("a-nik")) return;
  const nik = $("a-nik").value.trim();
  const cocok = _saran.find((p) => String(p.nik) === nik);
  if (!cocok) return;
  if (ada("a-nama")) $("a-nama").value = cocok.nama || "";
  if (ada("a-bagian") && cocok.bagian &&
      Array.from($("a-bagian").options).some((o) => o.value === cocok.bagian))
    $("a-bagian").value = cocok.bagian;
}

/* --- Identitas pemilik akun: NIK+nama terisi otomatis sebagai saran (tetap bisa diubah) --- */
async function isiIdentitasSaya() {
  if (SAYA_ADMIN) return;
  try {
    const s = await get("/api/saya");
    if (!s || !s.nik) return; // NIK belum diikat admin: biarkan manual, server akan menolak dgn pesan
    [["a-nik", "a-nama"], ["j-nik", "j-nama"]].forEach(([iNik, iNama]) => {
      if (ada(iNik) && !$(iNik).value) $(iNik).value = s.nik;
      if (ada(iNama) && !$(iNama).value) $(iNama).value = s.nama || "";
    });
    ["a-bagian", "j-bagian"].forEach((id) => {
      if (ada(id) && s.bagian &&
          Array.from($(id).options).some((o) => o.value === s.bagian)) $(id).value = s.bagian;
    });
  } catch (e) { /* abaikan */ }
}

/* --- Hari ini: absen web + data live (rekap ada di tab Unduh Laporan) --- */
async function loadHari() {
  try {
    if (!ada("m-tb")) return;
    const m = await get("/api/monitor");
    $("m-tb").innerHTML = m.map((x) => {
      const del = (SAYA_ADMIN && x.id)
        ? ` <a href="#" onclick="hapusAbsen(${x.id});return false" title="Hapus baris ini" style="color:#dc2626">x</a>` : "";
      const st = x.status || "DISETUJUI";
      const badge = st === "DISETUJUI" ? "" :
        (st === "PENDING" ? ` <span class="pill p-pending">PENDING</span>` : ` <span class="pill p-no">DITOLAK</span>`);
      const jarak = (x.jarak_m != null) ? `<br><small>${Math.round(x.jarak_m)} m dari kantor</small>` : "";
      const ak = (x.akurasi_m != null) ? `<br><small>±${Math.round(x.akurasi_m)} m</small>` : "";
      // lokasi langsung terlihat user & admin: koordinat + link buka di Maps
      const peta = (x.lat != null && x.lon != null)
        ? `<br><small>${esc(Number(x.lat).toFixed(6))}, ${esc(Number(x.lon).toFixed(6))}</small>` +
          `<br><a href="https://www.google.com/maps?q=${encodeURIComponent(x.lat + "," + x.lon)}" target="_blank" rel="noopener" style="font-size:11px">Lihat peta</a>`
        : (String(x.cara || "").startsWith("aplikasi") ? `<br><small>tanpa GPS</small>` : "");
      return `<tr><td><small>${esc(x.waktu)}</small>${badge}</td>` +
      `<td style="text-align:left"><b>${esc(x.nama || x.nik)}</b><br><small>NIK ${esc(x.nik)}${x.bagian ? " • " + esc(x.bagian) : ""}</small></td>` +
      `<td>${esc(x.tipe)}${jarak}${ak}${peta}</td><td><small>${esc(x.cara || "")}</small>${del}</td></tr>`;
    }).join("") || `<tr><td colspan="4"><div class="empty">Belum ada data masuk.</div></td></tr>`;
  } catch (e) { /* abaikan saat refresh otomatis */ }
}

async function hapusAbsen(id) {
  if (!SAYA_ADMIN) return alert("Hanya admin yang boleh menghapus.");
  if (!confirm("Hapus 1 baris scan ini? (untuk koreksi salah tap)")) return;
  try {
    const j = await post("/api/absen/hapus", { id });
    alert(j.pesan || "Selesai.");
  } catch (e) {
    if (String(e.message) === "login") return;
    alert("Gagal: " + e.message);
  }
  loadHari(); loadData(); muatLaporan(true);
}

/* --- Absen via web (tombol dikunci selama terkirim agar tak terketuk 2x) --- */
/* --- Unduh laporan harian (Excel/CSV rapi) --- */
function unduhHariExcel() {
  const t = (ada("m-tgl") && $("m-tgl").value) || today();
  location.href = "/export/hari?tgl=" + encodeURIComponent(t);
}
function unduhHariCSV() {
  const t = (ada("m-tgl") && $("m-tgl").value) || today();
  location.href = "/export/hari?tgl=" + encodeURIComponent(t) + "&format=csv";
}
function unduhHariPDF() {
  const t = (ada("m-tgl") && $("m-tgl").value) || today();
  location.href = "/export/hari?tgl=" + encodeURIComponent(t) + "&format=pdf";
}
/* Klik absen = langsung share lokasi user di mana dia berada.
   GPS diambil otomatis saat tombol ditekan (tak perlu tombol lokasi dulu).
   Tombol lokasi terpisah tetap ada hanya untuk cek/refresh posisi. */
async function checkin(btn) {
  if (!ada("a-tipe") || !ada("a-msg")) return;
  const nik = ada("a-nik") ? $("a-nik").value.trim() : "";
  if (!nik) { info("a-msg", false, "Isi NIK dulu."); return; }
  const tombol = btn || $("a-kirim");
  if (tombol) { tombol.disabled = true; tombol.textContent = "Mengambil lokasi..."; }
  // 1. Ambil GPS otomatis (fresh setiap klik absen, beserta akurasinya)
  let lat = null, lon = null, akurasi = null;
  try {
    if (typeof mintaLokasiSekali === "function") {
      if (ada("a-msg")) info("a-msg", true, "Mengambil lokasi paling tepat... (diam sebentar, izinkan akses lokasi bila diminta)");
      const p = await mintaLokasiSekali();
      lat = p.lat; lon = p.lon; akurasi = p.akurasi;
      try {
        _lokasi = p;
        _tampilkanLokasi();
      } catch (e) { /* tab-lokasi belum termuat, abaikan tampilan */ }
    } else {
      // fallback: pakai simpanan terakhir bila helper belum ada
      lat = ada("a-lat") && $("a-lat").value !== "" ? parseFloat($("a-lat").value) : null;
      lon = ada("a-lon") && $("a-lon").value !== "" ? parseFloat($("a-lon").value) : null;
    }
  } catch (e) {
    // GPS gagal: bila kantor mengizinkan tanpa GPS, tetap kirim (jadi PENDING).
    // Bila GPS wajib (default), berhenti dan minta user mengaktifkan GPS.
    let bolehTanpaGPS = false;
    try { bolehTanpaGPS = (typeof _kantor !== "undefined" && _kantor && !_kantor.wajib); } catch (err) {}
    if (!bolehTanpaGPS) {
      if (tombol) { tombol.disabled = false; tombol.textContent = "Kirim absen sekarang"; }
      info("a-msg", false, "Lokasi gagal diambil: " + e.message +
        ". Aktifkan GPS + izinkan lokasi di browser, lalu klik absen lagi.");
      return;
    }
    lat = null; lon = null; akurasi = null;
  }
  // 2. Kirim absen + lokasi + akurasi (server menolak fix yang melenceng)
  if (tombol) { tombol.textContent = "Mengirim..."; }
  try {
    const payload = { nik, tipe: $("a-tipe").value,
      nama: ada("a-nama") ? $("a-nama").value.trim() : "",
      bagian: ada("a-bagian") ? $("a-bagian").value.trim() : "",
      lat, lon, akurasi };
    const j = await post("/api/checkin", payload);
    info("a-msg", j.ok, j.pesan);
    if (j.ok && typeof listPendingLokasi === "function") listPendingLokasi();
    if (j.ok && typeof updateLokasiBadge === "function") updateLokasiBadge();
  } catch (e) {
    if (String(e.message) === "login") return;
    info("a-msg", false, "Gagal: " + e.message);
  } finally {
    if (tombol) { tombol.disabled = false; tombol.textContent = "Kirim absen sekarang"; }
  }
  loadHari(); loadData(); muatLaporan(true);
}
