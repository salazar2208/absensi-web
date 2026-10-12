/* UNTUK APA: lokasi GPS + approval absen luar radius (mirip izin).
   - ambilLokasi(): isi #a-lat/#a-lon dari GPS browser sebelum checkin.
   - checkin() di tab-hari.js otomatis menyertakan lat/lon ini.
   - listPendingLokasi(): daftar PENDING (admin: semua, user: miliknya).
   - putusLokasi(id, aksi): SETUJU/TOLAK oleh admin.
   - loadLokasiSetting(): tampilkan titik kantor + isi form admin. */

let _lokasi = { lat: null, lon: null, akurasi: null };
let _kantor = null;

function _fmtJarak(m) {
  if (m == null || isNaN(m)) return "-";
  m = Number(m);
  if (m < 1000) return Math.round(m) + " m";
  return (m / 1000).toFixed(2) + " km";
}

async function loadLokasiSetting() {
  try {
    const s = await get("/api/lokasi");
    if (!s || !s.ok) return;
    _kantor = s;
    if (ada("lok-info")) {
      $("lok-info").innerHTML =
        `Titik <b>${esc(s.nama || "Kantor")}</b> · radius <b>${esc(s.radius_m)} m</b>` +
        (s.wajib ? ` · <span class="pill p-pending">GPS wajib</span>`
                 : ` · <span class="pill p-izin">GPS opsional</span>`);
    }
    // isi form admin (tab Unduh Laporan) bila ada
    if (ada("lok-lat") && document.activeElement !== $("lok-lat")) $("lok-lat").value = s.lat ?? "";
    if (ada("lok-lon") && document.activeElement !== $("lok-lon")) $("lok-lon").value = s.lon ?? "";
    if (ada("lok-radius")) $("lok-radius").value = s.radius_m ?? 100;
    if (ada("lok-nama") && !$("lok-nama").value) $("lok-nama").value = s.nama || "";
    if (ada("lok-wajib")) $("lok-wajib").checked = !!s.wajib;
    if (ada("lok-admin-info")) {
      $("lok-admin-info").innerHTML =
        `Aktif: <b>${esc(s.nama)}</b> (<span class="kode">${esc(s.lat)}, ${esc(s.lon)}</span>) radius ${esc(s.radius_m)} m. ` +
        `<a href="https://www.google.com/maps?q=${encodeURIComponent(s.lat + "," + s.lon)}" target="_blank" rel="noopener">Buka di Maps</a>`;
    }
  } catch (e) { /* abaikan */ }
}

function bukaMapsKantor() {
  if (_kantor && _kantor.lat != null) {
    window.open("https://www.google.com/maps?q=" + encodeURIComponent(_kantor.lat + "," + _kantor.lon), "_blank");
  } else {
    alert("Titik kantor belum dimuat. Tunggu sebentar lalu coba lagi.");
  }
}

/* Minta posisi GPS PALING TEPAT, kembalikan Promise.
   Dipakai tombol absen agar klik absen = langsung share lokasi user
   di mana dia berada, setepat mungkin.
   Cara: pantau GPS s/d 8 detik, simpan fix dengan akurasi terkecil.
   Fix <= 15 m langsung dipakai tanpa menunggu. maximumAge: 0 agar
   selalu fix segar (bukan cache lama yang meleset). */
function mintaLokasiSekali() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Browser tidak mendukung GPS. Pakai Chrome di HP."));
      return;
    }
    let terbaik = null, selesai = false, id = null;
    const tutup = () => { try { if (id != null) navigator.geolocation.clearWatch(id); } catch (e) {} };
    id = navigator.geolocation.watchPosition(
      (pos) => {
        if (selesai) return;
        const p = { lat: pos.coords.latitude, lon: pos.coords.longitude,
                    akurasi: pos.coords.accuracy };
        if (!terbaik || (p.akurasi || 99999) < (terbaik.akurasi || 99999)) terbaik = p;
        if ((p.akurasi || 99999) <= 15) {
          selesai = true; tutup(); resolve(terbaik);
        }
      },
      (err) => {
        if (selesai) return;
        selesai = true; tutup();
        if (terbaik) resolve(terbaik);
        else reject(new Error(err.message || ("kode " + err.code)));
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
    setTimeout(() => {
      if (selesai) return;
      selesai = true; tutup();
      if (terbaik) resolve(terbaik);
      else reject(new Error("GPS timeout. Coba di luar ruangan / dekat jendela lalu ulangi."));
    }, 8000);
  });
}

/* Tampilkan info jarak di bawah form (keputusan resmi tetap di server). */
function _tampilkanLokasi() {
  if (_lokasi.lat == null || _lokasi.lon == null) return;
  if (ada("a-lat")) $("a-lat").value = _lokasi.lat;
  if (ada("a-lon")) $("a-lon").value = _lokasi.lon;
  let jarakTxt = "";
  if (_kantor) {
    const R = 6371000, toRad = (d) => d * Math.PI / 180;
    const a = Math.sin(toRad(_kantor.lat - _lokasi.lat) / 2) ** 2 +
      Math.cos(toRad(_lokasi.lat)) * Math.cos(toRad(_kantor.lat)) *
      Math.sin(toRad(_kantor.lon - _lokasi.lon) / 2) ** 2;
    const j = 2 * R * Math.asin(Math.sqrt(a));
    const dalam = j <= _kantor.radius_m;
    jarakTxt = ` · ±${Math.round(_lokasi.akurasi || 0)} m · ${Math.round(j)} m dari ${_kantor.nama} — ` +
      (dalam ? "DI DALAM radius (langsung disetujui)" : "DI LUAR radius (jadi PENDING, perlu approval)");
  }
  if (ada("lok-status")) info("lok-status", true,
    `Lokasi terkunci: ${Number(_lokasi.lat).toFixed(6)}, ${Number(_lokasi.lon).toFixed(6)}${jarakTxt}`);
}

function ambilLokasi() {
  const btn = $("lok-btn");
  if (!navigator.geolocation) {
    if (ada("lok-status")) info("lok-status", false, "Browser tidak mendukung GPS. Pakai Chrome di HP.");
    return;
  }
  if (btn) { btn.disabled = true; btn.textContent = "Mencari GPS..."; }
  if (ada("lok-status")) info("lok-status", true, "Mencari sinyal GPS... (izinkan akses lokasi bila diminta)");
  mintaLokasiSekali().then(
    (p) => {
      _lokasi = p;
      _tampilkanLokasi();
      if (btn) { btn.disabled = false; btn.textContent = "Perbarui lokasi GPS"; }
    },
    (err) => {
      if (ada("lok-status")) info("lok-status", false,
        "Gagal ambil GPS: " + err.message + ". Aktifkan GPS + izin lokasi di browser.");
      if (btn) { btn.disabled = false; btn.textContent = "Aktifkan lokasi GPS"; }
    }
  );
}

/* --- Admin: simpan titik kantor --- */
function ambilTitikKantor() {
  if (!navigator.geolocation) return alert("Browser tidak mendukung GPS.");
  if (ada("lok-admin-msg")) info("lok-admin-msg", true,
    "Mencari titik PALING TEPAT... diam di titik kantor s/d 8 detik.");
  mintaLokasiSekali().then(
    (pos) => {
      if (ada("lok-lat")) $("lok-lat").value = pos.lat.toFixed(6);
      if (ada("lok-lon")) $("lok-lon").value = pos.lon.toFixed(6);
      if (ada("lok-admin-msg")) info("lok-admin-msg", true,
        `Titik terkunci: ${pos.lat.toFixed(6)}, ${pos.lon.toFixed(6)} (±${Math.round(pos.akurasi || 0)} m). Tekan Simpan.`);
    },
    (err) => {
      if (ada("lok-admin-msg")) info("lok-admin-msg", false, "Gagal: " + err.message);
    }
  );
}

async function simpanLokasi() {
  try {
    const j = await post("/api/lokasi", {
      lat: ada("lok-lat") ? $("lok-lat").value : "",
      lon: ada("lok-lon") ? $("lok-lon").value : "",
      radius_m: ada("lok-radius") ? $("lok-radius").value : 100,
      nama: ada("lok-nama") ? $("lok-nama").value : "Kantor",
      wajib: ada("lok-wajib") && $("lok-wajib").checked ? "1" : "0",
    });
    if (ada("lok-admin-msg")) info("lok-admin-msg", !!j.ok, j.pesan || "Selesai.");
    else alert(j.pesan || "Selesai.");
    loadLokasiSetting();
  } catch (e) {
    if (String(e.message) === "login") return;
    if (ada("lok-admin-msg")) info("lok-admin-msg", false, "Gagal: " + e.message);
    else alert("Gagal: " + e.message);
  }
}

/* --- Daftar approval lokasi (mirip daftar pengajuan izin) --- */
async function listPendingLokasi() {
  try {
    if (!ada("lok-tb")) return;
    const j = await get("/api/absen/pending");
    const badge = $("lok-pending-badge");
    if (badge) {
      badge.style.display = j.length ? "" : "none";
      badge.textContent = j.length;
    }
    $("lok-tb").innerHTML = j.map((a) => {
      const maps = (a.lat != null && a.lon != null)
        ? `<br><a href="https://www.google.com/maps?q=${encodeURIComponent(a.lat + "," + a.lon)}" target="_blank" rel="noopener" style="font-size:11px">lihat peta</a>` : "";
      const aksi = SAYA_ADMIN
        ? `<button class="btn sm" onclick="putusLokasi(${a.id},'SETUJU')">Setuju</button> ` +
          `<button class="btn sm red" onclick="putusLokasi(${a.id},'TOLAK')">Tolak</button>`
        : `<small style="color:var(--mut)">menunggu admin</small>`;
      return `<tr><td style="text-align:left"><small>${esc(a.waktu)}</small><br>` +
        `<b>${esc(a.nama || a.nik)}</b><br><small>NIK ${esc(a.nik)} · ${esc(a.tipe || "")}</small></td>` +
        `<td><b>${esc(_fmtJarak(a.jarak_m))}</b><br><small>${a.lat != null ? esc(Number(a.lat).toFixed(5) + ", " + Number(a.lon).toFixed(5)) : "tanpa GPS"}</small>${maps}</td>` +
        `<td><span class="pill p-pending">PENDING</span></td><td>${aksi}</td></tr>`;
    }).join("") || `<tr><td colspan="4"><div class="empty">Tidak ada absen menunggu approval lokasi.</div></td></tr>`;
    if (ada("lok-approval-info") && j.length) {
      $("lok-approval-info").innerHTML = SAYA_ADMIN
        ? `<b>${j.length} absen</b> di luar radius menunggu keputusanmu. Tekan <b>Setuju / Tolak</b>. Yang disetujui masuk rekap.`
        : `<b>${j.length} absenmu</b> sedang diproses admin, tunggu ACC ya.`;
    }
  } catch (e) { /* abaikan */ }
}

async function putusLokasi(id, aksi) {
  if (!SAYA_ADMIN) return alert("Hanya admin yang boleh memutuskan.");
  try {
    const j = await post("/api/absen/putus", { id, aksi });
    alert(j.pesan);
  } catch (e) {
    if (String(e.message) === "login") return;
    alert("Gagal: " + e.message);
  }
  listPendingLokasi(); loadHari(); loadData(); updateLokasiBadge();
  try { if (typeof muatLaporan === "function") muatLaporan(true); } catch (e) {}
}

async function updateLokasiBadge() {
  try {
    const j = await get("/api/absen/pending_count");
    const n = j.pending || 0;
    const b = $("lok-pending-badge");
    if (b) { b.style.display = n > 0 ? "" : "none"; b.textContent = n; }
    const nav = $("nav-lokasi-badge");
    if (nav) { nav.style.display = n > 0 ? "" : "none"; nav.textContent = n; }
  } catch (e) { /* abaikan */ }
}
