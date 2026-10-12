/* UNTUK APA: tab Unduh Laporan saja.
   Isi 3 langkah: 1 tarik mesin -> 2 database -> 3 rekap + unduh Excel/CSV. */

/* --- Tarik mesin via IP (khusus admin) --- */
async function loadMesin() {
  if (!SAYA_ADMIN || !$("t-tb")) return;
  const j = await get("/api/mesin");
  if (!Array.isArray(j)) return;
  $("t-tb").innerHTML = j.map((m) => (
    `<tr><td style="text-align:left"><b>${esc(m.nama)}</b><br>` +
    `<span class="kode">${esc(m.ip)}:${esc(m.port)}</span><br>` +
    `<small>Tarik terakhir: ${esc(m.terakhir || "belum pernah")}</small></td>` +
    `<td><button class="btn sm dark" onclick="tesMesin(${m.id})">Tes</button> ` +
    `<button class="btn sm" onclick="tarikMesin(${m.id})">Tarik</button> ` +
    `<button class="btn sm red" onclick="delMesin(${m.id})">Hapus</button></td></tr>`
  )).join("") || `<tr><td colspan="2"><div class="empty">Belum ada mesin. Masukkan IP di atas lalu Simpan.</div></td></tr>`;
}
async function saveMesin() {
  if (!$("t-ip").value.trim()) { info("t-msg", false, "Isi IP mesin dulu, contoh: 192.168.1.201"); return; }
  const j = await post("/api/mesin", { nama: $("t-nama").value || "Mesin Kantor", ip: $("t-ip").value, port: $("t-port").value || 4370 });
  info("t-msg", j.ok, j.pesan);
  if (j.ok) { $("t-ip").value = ""; loadMesin(); }
}
async function delMesin(id) {
  if (!confirm("Hapus mesin ini?")) return;
  await post("/api/mesin", { id, hapus: 1 });
  loadMesin();
}
async function tesMesin(id) {
  info("t-msg", true, "Mengetes koneksi, mohon tunggu...");
  const j = await post("/api/mesin/tes", { id });
  info("t-msg", j.ok, j.pesan);
}
async function tarikMesin(id) {
  info("t-msg", true, "Menarik data dari mesin, mohon tunggu...");
  const j = await post("/api/mesin/tarik", { id });
  info("t-msg", j.ok, j.pesan);
  loadMesin(); loadData(); loadHari(); muatLaporan(true);
}
async function tarikSemua() {
  info("t-msg", true, "Menarik data dari semua mesin, mohon tunggu...");
  const j = await post("/api/mesin/tarik", {});
  info("t-msg", j.ok, j.pesan);
  loadMesin(); loadData(); loadHari();
}
let _timerOtomatis = null;
function aturOtomatis(el) {
  if (_timerOtomatis) { clearInterval(_timerOtomatis); _timerOtomatis = null; }
  if (el.checked) {
    _timerOtomatis = setInterval(async () => {
      try { await post("/api/mesin/tarik", {}); loadMesin(); loadData(); loadHari(); } catch (e) {}
    }, 60000);
    info("t-msg", true, "Tarik otomatis aktif: setiap 1 menit.");
  } else {
    info("t-msg", true, "Tarik otomatis dimatikan.");
  }
}

/* --- Database hasil tarikan --- */
let _pilih = new Set(); // ingat centang agar tidak hilang saat refresh otomatis
async function loadData() {
  try {
    if (!ada("d-tb")) return;
    document.querySelectorAll(".d-cek:checked").forEach((x) => _pilih.add(String(x.value)));
    const q = ada("d-cari") ? $("d-cari").value : "";
    const j = await get("/api/data?q=" + encodeURIComponent(q) + "&limit=100");
    if ($("d-total")) $("d-total").textContent = `Total ${j.total} baris di database.`;
    $("d-tb").innerHTML = j.data.map((x) => {
      const cek = (SAYA_ADMIN && x.id)
        ? `<td><input type="checkbox" class="d-cek" style="width:auto" value="${x.id}"${_pilih.has(String(x.id)) ? " checked" : ""} onchange="updatePilihInfo()"></td>` : "";
      const del = (SAYA_ADMIN && x.id)
        ? `<br><a href="#" onclick="hapusAbsen(${x.id});return false" style="color:#dc2626;font-size:11px">hapus</a>` : "";
      const st = x.status || "DISETUJUI";
      const badge = st === "DISETUJUI" ? "" :
        (st === "PENDING" ? `<br><span class="pill p-pending">PENDING</span>` : `<br><span class="pill p-no">DITOLAK</span>`);
      const jarak = (x.jarak_m != null) ? `<br><small>${Math.round(x.jarak_m)} m dari kantor</small>` : "";
      const ak = (x.akurasi_m != null) ? `<br><small>±${Math.round(x.akurasi_m)} m</small>` : "";
      const peta = (x.lat != null && x.lon != null)
        ? `<br><small>${esc(Number(x.lat).toFixed(6))}, ${esc(Number(x.lon).toFixed(6))}</small>` +
          `<br><a href="https://www.google.com/maps?q=${encodeURIComponent(x.lat + "," + x.lon)}" target="_blank" rel="noopener" style="font-size:11px">Lihat peta</a>`
        : (String(x.cara || "").startsWith("aplikasi") ? `<br><small>tanpa GPS</small>` : "");
      return `<tr>` + cek + `<td><small>${esc(x.waktu)}</small>${badge}</td>` +
      `<td style="text-align:left"><b>${esc(x.nama)}</b><br><small>NIK ${esc(x.nik)}${x.bagian ? " • " + esc(x.bagian) : ""}</small></td>` +
      `<td>${esc(x.tipe)}${jarak}${ak}${peta}</td><td><small>${esc(x.cara || "")}</small>${del}</td></tr>`;
    }).join("") || `<tr><td colspan="${SAYA_ADMIN ? 5 : 4}"><div class="empty">Database masih kosong.</div></td></tr>`;
    const tampil = new Set(j.data.map((x) => String(x.id)));
    _pilih.forEach((id) => { if (!tampil.has(id)) _pilih.delete(id); });
    if (ada("d-semua")) $("d-semua").checked = false;
    updatePilihInfo();
  } catch (e) { /* abaikan */ }
}

/* --- Hapus database hasil tarikan (khusus admin) --- */
function _terpilih() {
  return Array.from(document.querySelectorAll(".d-cek:checked")).map((x) => parseInt(x.value, 10)).filter((x) => x);
}
function togglePilihSemua(el) {
  document.querySelectorAll(".d-cek").forEach((x) => { x.checked = el.checked; });
  updatePilihInfo();
}
function updatePilihInfo() {
  if (ada("d-pilih")) $("d-pilih").textContent = _terpilih().length;
}
async function hapusDipilih() {
  if (!SAYA_ADMIN) return alert("Hanya admin yang boleh menghapus.");
  const ids = _terpilih();
  if (!ids.length) return alert("Centang dulu baris yang mau dihapus.");
  if (!confirm(`Hapus ${ids.length} baris terpilih?`)) return;
  if (ada("d-hapus-msg")) info("d-hapus-msg", true, "Menghapus " + ids.length + " baris...");
  try {
    const j = await post("/api/data/hapus", { ids });
    if (ada("d-hapus-msg")) info("d-hapus-msg", !!j.ok, j.pesan || "Selesai.");
    else alert(j.pesan || "Selesai.");
    if (j.ok) _pilih.clear();
  } catch (e) {
    if (String(e.message) === "login") return;
    if (ada("d-hapus-msg")) info("d-hapus-msg", false, "Gagal: " + e.message);
    else alert("Gagal: " + e.message);
  }
  loadData(); loadHari(); muatLaporan(true);
}
async function hapusSemuaData() {
  if (!SAYA_ADMIN) return alert("Hanya admin yang boleh menghapus.");
  if (!confirm("KOSONGKAN seluruh database hasil tarikan?\n\nBackup otomatis dibuat dulu. Unduh laporan Excel dulu bila datanya masih perlu.")) return;
  if (!confirm("Yakin? Tindakan ini menghapus SEMUA baris.")) return;
  if (ada("d-hapus-msg")) info("d-hapus-msg", true, "Mengosongkan database...");
  try {
    const j = await post("/api/data/hapus", { semua: true });
    if (ada("d-hapus-msg")) info("d-hapus-msg", !!j.ok, j.pesan || "Selesai.");
    else alert(j.pesan || "Selesai.");
    if (j.ok) _pilih.clear();
  } catch (e) {
    if (String(e.message) === "login") return;
    if (ada("d-hapus-msg")) info("d-hapus-msg", false, "Gagal: " + e.message);
    else alert("Gagal: " + e.message);
  }
  loadData(); loadHari(); muatLaporan(true);
}

/* --- Laporan rentang tanggal + Excel + hapus data --- */
const LABEL_LAP = { tepat: "Tepat waktu", telat: "Terlambat", satu: "Hanya 1 scan", belum: "Belum hadir", izin: "Izin/Cuti" };
let _tmLap = null;
function paramLaporan() {
  const dari = ada("r-dari") ? $("r-dari").value : today();
  const sampai = ada("r-sampai") ? $("r-sampai").value : dari;
  const p = new URLSearchParams({ dari: dari || today(),
    sampai: sampai || dari || today(),
    batas: ($("r-batas") && $("r-batas").value) || "08:15" });
  if (SAYA_ADMIN && $("r-cari")) p.set("q", $("r-cari").value.trim());
  return p;
}
function muatLaporan(segera) {
  if (!ada("page-tarik") || !ada("r-tb")) return;
  clearTimeout(_tmLap);
  _tmLap = setTimeout(async () => {
    try {
      const d = await get("/api/ringkas?" + paramLaporan());
      const n = { tepat: 0, telat: 0, satu: 0, belum: 0, izin: 0 };
      d.forEach((r) => { if (n[r.status] === undefined) n[r.status] = 0; n[r.status]++; });
      ["tepat", "telat", "satu", "belum", "izin"].forEach((k) => { if (ada("g-" + k)) $(("g-" + k)).textContent = n[k] || 0; });
      $("r-tb").innerHTML = d.map((r) => {
        const dur = r.menit == null ? "-" : Math.floor(r.menit / 60) + "j " + String(r.menit % 60).padStart(2, "0") + "m";
        return `<tr><td><small>${esc(r.tanggal)}</small></td>` +
          `<td style="text-align:left"><b>${esc(r.nama || r.nik)}</b><br><small>NIK ${esc(r.nik)}${r.bagian ? " • " + esc(r.bagian) : ""}</small></td>` +
          `<td>${esc(r.masuk || "-")}</td><td>${esc(r.pulang || "-")}</td><td>${dur}</td>` +
          `<td>${pillLap(r.status)}</td></tr>`;
      }).join("") || `<tr><td colspan="6"><div class="empty">Belum ada scan pada periode ini.</div></td></tr>`;
    } catch (e) { /* abaikan saat refresh */ }
  }, segera ? 0 : 200);
}
function pillLap(st) {
  const cls = { tepat: "p-hadir", telat: "p-telat", satu: "p-izin", belum: "p-alpha", izin: "p-izin" }[st] || "p-izin";
  return `<span class="pill ${cls}">${esc(LABEL_LAP[st] || st)}</span>`;
}
function unduhExcel() {
  location.href = "/export?" + paramLaporan();
}
function unduhCSV() {
  location.href = "/export?" + paramLaporan() + "&format=csv";
}
function unduhPDF() {
  location.href = "/export?" + paramLaporan() + "&format=pdf";
}
function cetakLaporan() { window.print(); }
async function hapusData() {
  if (!SAYA_ADMIN) return;
  const body = { scope: $("x-scope").value, date: $("x-tgl").value || today() };
  const h = await post("/api/reset", { ...body, dry: true });
  if (!h.jumlah) { alert("Tidak ada scan pada " + h.rentang + "."); return; }
  if (!confirm(`Hapus ${h.jumlah} scan pada ${h.rentang}?\n\nBackup otomatis dibuat sebelum dihapus.`)) return;
  const j = await post("/api/reset", body);
  alert(j.pesan);
  loadHari(); loadData(); muatLaporan(true);
}

/* --- Demo + contoh (khusus admin) --- */
async function isiDemo() {
  if (!confirm("Isi data contoh hari ini (NIK 901-910)? Aman, tidak campur data asli.")) return;
  info("t-msg", true, "Mengisi data contoh...");
  const j = await post("/api/demo", {});
  info("t-msg", j.ok, j.pesan);
  loadMesin(); loadData(); loadHari(); muatLaporan(true);
}
async function hapusDemo() {
  if (!confirm("Hapus SEMUA data contoh (NIK 901-910)? Data asli tidak ikut terhapus.")) return;
  const j = await post("/api/demo/hapus", {});
  info("t-msg", j.ok, j.pesan);
  loadMesin(); loadData(); loadHari(); muatLaporan(true);
}
