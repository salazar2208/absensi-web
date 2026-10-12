/* UNTUK APA: tab Daftar saja (daftar orang baru + NIK mesin belum terdaftar). */

/* --- Daftar orang baru (satu-satu) --- */

/* --- Daftar banyak sekaligus (satu baris: NIK, Nama, Bagian) --- */
async function imporDaftar() {
  if (!ada("f-massal") || !$("f-massal").value.trim()) { info("f-massal-msg", false, "Tempel dulu daftarnya."); return; }
  try {
    const j = await post("/api/pegawai/impor", { teks: $("f-massal").value });
    info("f-massal-msg", !!j.ok, j.pesan || "Selesai.");
    if (j.ok) $("f-massal").value = "";
  } catch (e) {
    if (String(e.message) === "login") return;
    info("f-massal-msg", false, "Gagal: " + e.message);
  }
  loadDaftar(); loadBelum(); loadHari();
}
/* --- NIK mesin belum terdaftar: centang banyak lalu salin --- */
function togglePilihDaftar(el) {
  document.querySelectorAll(".f-cek").forEach((x) => { x.checked = el.checked; });
  updatePilihDaftar();
}
function updatePilihDaftar() {
  if (ada("f-pilih")) $("f-pilih").textContent =
    document.querySelectorAll(".f-cek:checked").length;
}
function salinTerpilih() {
  const ids = Array.from(document.querySelectorAll(".f-cek:checked")).map((x) => x.value);
  if (!ids.length) return alert("Centang dulu NIK yang mau didaftarkan.");
  const tambah = ids.map((nik) => nik + ", ").join("\n") + "\n";
  const lama = ada("f-massal") ? $("f-massal").value.replace(/\s+$/, "") : "";
  $("f-massal").value = (lama ? lama + "\n" : "") + tambah;
  $("f-massal").scrollIntoView({ behavior: "smooth", block: "center" });
  $("f-massal").focus();
  alert(ids.length + " NIK tersalin. Lengkapi namanya lalu klik Daftarkan sekaligus.");
}
let _pilihOrang = new Set(); // ingat centang agar tidak hilang saat mengetik cari
async function loadDaftar() {
  try {
    if (!ada("f-tb")) return;
    document.querySelectorAll(".f-cek-orang:checked").forEach((x) => _pilihOrang.add(String(x.value)));
    const j = await get("/api/pegawai");
    const q = ((ada("f-cari") && $("f-cari").value) || "").toLowerCase();
    const saring = j.filter((p) => ((p.nik || "") + " " + (p.nama || "") + " " + (p.bagian || "")).toLowerCase().includes(q));
    if (ada("f-count")) $("f-count").textContent = saring.length + " dari " + j.length + " orang";
    $("f-tb").innerHTML = saring.map((p) => (
      `<tr><td><input type="checkbox" class="f-cek-orang" style="width:auto" value="${esc(p.nik)}"${_pilihOrang.has(String(p.nik)) ? " checked" : ""} onchange="updatePilihOrang()"></td>` +
      `<td><b>${esc(p.nik)}</b></td>` +
      `<td style="text-align:left"><b>${esc(p.nama)}</b><br><small>${esc(p.bagian || "-")}</small></td>` +
      `<td><button class="btn sm red" onclick="delDaftar('${esc(p.nik)}')">Hapus</button></td></tr>`
    )).join("") || `<tr><td colspan="4"><div class="empty">Belum ada orang terdaftar.</div></td></tr>`;
    const tampil = new Set(saring.map((p) => String(p.nik)));
    _pilihOrang.forEach((nik) => { if (!tampil.has(nik)) _pilihOrang.delete(nik); });
    if (ada("f-semua-orang")) $("f-semua-orang").checked = false;
    updatePilihOrang();
  } catch (e) { /* abaikan */ }
}
function togglePilihOrang(el) {
  document.querySelectorAll(".f-cek-orang").forEach((x) => { x.checked = el.checked; });
  updatePilihOrang();
}
function updatePilihOrang() {
  if (ada("f-pilih-hapus")) $("f-pilih-hapus").textContent =
    document.querySelectorAll(".f-cek-orang:checked").length;
}
async function hapusOrangDipilih() {
  const niks = Array.from(document.querySelectorAll(".f-cek-orang:checked")).map((x) => x.value);
  if (!niks.length) return alert("Centang dulu orang yang mau dihapus.");
  if (!confirm(`Hapus ${niks.length} orang dari daftar? (data absennya tetap ada)`)) return;
  try {
    const j = await post("/api/pegawai", { hapus: 1, niks });
    alert(j.pesan || "Selesai.");
    if (j.ok) _pilihOrang.clear();
  } catch (e) {
    if (String(e.message) === "login") return;
    alert("Gagal: " + e.message);
  }
  loadDaftar(); loadHari();
}
async function saveDaftar() {
  if (!ada("f-nik") || !$("f-nik").value.trim()) { info("f-msg", false, "Isi NIK dulu."); return; }
  const j = await post("/api/pegawai", { nik: $("f-nik").value.trim(),
    nama: $("f-nama").value.trim(), bagian: $("f-bagian").value.trim() });
  info("f-msg", j.ok, j.pesan || "Selesai.");
  if (j.ok) { $("f-nik").value = ""; $("f-nama").value = ""; $("f-bagian").value = ""; }
  loadDaftar(); loadBelum(); loadHari();
}
async function delDaftar(nik) {
  if (!confirm("Hapus " + nik + " dari daftar orang? (data absennya tetap ada)")) return;
  const j = await post("/api/pegawai", { nik, hapus: 1 });
  alert(j.pesan || "Selesai.");
  loadDaftar(); loadHari();
}
async function loadBelum() {
  try {
    if (!ada("f-belum-tb")) return;
    const j = await get("/api/pegawai/belum");
    $("f-belum-tb").innerHTML = j.map((x) => (
      `<tr><td><input type="checkbox" class="f-cek" style="width:auto" value="${esc(x.nik)}" onchange="updatePilihDaftar()"></td>` +
      `<td><b>${esc(x.nik)}</b></td><td>${esc(x.jml)}x</td>` +
      `<td><button class="btn sm" onclick="quickDaftar('${esc(x.nik)}')">Daftarkan</button></td></tr>`
    )).join("") || `<tr><td colspan="4"><div class="empty">Semua NIK mesin sudah terdaftar.</div></td></tr>`;
    if (ada("f-semua")) $("f-semua").checked = false;
    updatePilihDaftar();
  } catch (e) { /* abaikan */ }
}
async function quickDaftar(nik) {
  const nama = prompt("Nama untuk NIK " + nik + " (samakan persis dengan Excel ABSENSI OPERATOR):");
  if (nama === null || !nama.trim()) return;
  const bagian = prompt("Bagian untuk " + nama.trim() + ":\nPRODUCTION / QA/ QC / LOGISTIK / HR/GA / W/H / ENGINEERING\n(kosongkan bila belum tahu):") || "";
  const j = await post("/api/pegawai", { nik, nama: nama.trim(), bagian: bagian.trim() });
  alert(j.pesan || "Selesai.");
  loadDaftar(); loadBelum(); loadHari();
}
