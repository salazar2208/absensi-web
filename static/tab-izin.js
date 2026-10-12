/* UNTUK APA: tab Izin saja (Izin / Sakit / Cuti / Pulang Cepat + ACC admin). */

/* --- Saran NIK: ketik NIK terdaftar -> nama & bagian terisi sendiri.
       NIK baru (belum pernah absen) tetap bisa diketik manual. --- */
function isiOtomatisIzin() {
  if (!ada("j-nik")) return;
  const nik = $("j-nik").value.trim();
  const cocok = (typeof _saran !== "undefined" ? _saran : []).find((p) => String(p.nik) === nik);
  if (!cocok) return;
  if (ada("j-nama")) $("j-nama").value = cocok.nama || "";
  if (ada("j-bagian") && cocok.bagian &&
      Array.from($("j-bagian").options).some((o) => o.value === cocok.bagian))
    $("j-bagian").value = cocok.bagian;
}

/* --- Izin / Sakit / Cuti / Pulang Cepat --- */
const LABEL_JENIS = { IZIN: "Izin", SAKIT: "Sakit", CUTI: "Cuti", PULANG_AWAL: "Pulang Cepat" };
async function aju() {
  const nik = ada("j-nik") ? $("j-nik").value.trim() : "";
  if (!nik) return alert("Isi NIK dulu.");
  const payload = { nik,
    nama: ada("j-nama") ? $("j-nama").value.trim() : "",
    bagian: ada("j-bagian") ? $("j-bagian").value.trim() : "",
    tanggal: $("j-tgl").value || today(), jenis: $("j-jenis").value, ket: $("j-ket").value };
  const j = await post("/api/pengajuan", payload);
  alert(j.pesan);
  if (ada("j-ket")) $("j-ket").value = "";
  listAju(); loadHari();
}
async function listAju() {
  try {
    if (!ada("j-tb")) return;
    const f = ada("j-f") ? $("j-f").value : "";
  const j = await get("/api/pengajuan" + (f ? "?status=" + f : ""));
  $("j-tb").innerHTML = j.map((a) => {
    const cls = a.status === "DISETUJUI" ? "p-ok" : a.status === "DITOLAK" ? "p-no" : "p-pending";
    const aksi = (SAYA_ADMIN && a.status === "PENDING")
      ? `<button class="btn sm" onclick="putus(${a.id},'SETUJU')">Setuju</button> ` +
        `<button class="btn sm red" onclick="putus(${a.id},'TOLAK')">Tolak</button>` : "";
    const kolAksi = SAYA_ADMIN ? `<td>${aksi}</td>` : "";
    return `<tr><td style="text-align:left"><b>${esc(a.nama || a.nik)}</b><br><small>NIK ${esc(a.nik)}${a.bagian ? " • " + esc(a.bagian) : ""}</small></td>` +
      `<td>${esc(LABEL_JENIS[a.jenis] || a.jenis)}<br><small>${esc(a.tanggal)}</small></td>` +
      `<td style="text-align:left"><small>${esc(a.ket || "-")}</small></td>` +
      `<td><span class="pill ${cls}">${esc(a.status)}</span></td>${kolAksi}</tr>`;
  }).join("") || `<tr><td colspan="5"><div class="empty">Belum ada pengajuan.</div></td></tr>`;
  } catch (e) { /* abaikan */ }
}
async function putus(id, aksi) {
  if (!SAYA_ADMIN) return alert("Hanya admin yang boleh memutuskan.");
  const j = await post("/api/pengajuan/putus", { id, aksi });
  alert(j.pesan); listAju(); loadHari();
}
/* --- Unduh laporan izin (Excel/CSV rapi, ikut filter status) --- */
function unduhIzinExcel() {
  const f = (ada("j-f") && $("j-f").value) || "";
  location.href = "/export/izin" + (f ? "?status=" + encodeURIComponent(f) : "");
}
function unduhIzinCSV() {
  const f = (ada("j-f") && $("j-f").value) || "";
  location.href = "/export/izin" + (f ? "?status=" + encodeURIComponent(f) + "&" : "?") + "format=csv";
}
