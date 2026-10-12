/* FONDASI semua tab: helper + pindah tab + theme + jam hero + jalan pertama. */
const $ = (id) => document.getElementById(id);
const ROLE = window.APP_ROLE || "admin";
const SAYA_ADMIN = ROLE === "admin";
const esc = (s) => String(s ?? "").replace(/[<>&"']/g, (c) => (
  { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&#39;" }[c]));
const today = () => new Date().toISOString().slice(0, 10);

async function post(u, d) {
  const r = await fetch(u, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(d) });
  if (r.status === 401) { location.href = "/login"; throw new Error("login"); }
  try {
    return await r.json();
  } catch (e) {
    throw new Error("Server error HTTP " + r.status + ". Tutup server (jendela mulai.bat) lalu jalankan lagi.");
  }
}
async function get(u) {
  const r = await fetch(u);
  if (r.status === 401) { location.href = "/login"; throw new Error("login"); }
  return r.json();
}
function tab(nama, el) {
  const target = $("page-" + nama);
  if (!target) return;
  document.querySelectorAll("[data-page]").forEach((x) => x.classList.add("hide"));
  target.classList.remove("hide");
  target.style.animation = "none"; void target.offsetHeight; target.style.animation = "";
  document.querySelectorAll(".nav button").forEach((b) => b.classList.remove("on"));
  const btn = el || document.querySelector(`.nav button[data-tab="${nama}"]`);
  if (btn) btn.classList.add("on");
  try { localStorage.setItem("abs_tab", nama); } catch (e) {}
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (nama === "tarik") { loadMesin(); loadData(); muatLaporan(true); try { loadLokasiSetting(); } catch (e) {} }
  if (nama === "hari") { loadHari(); loadSaran(); try { loadLokasiSetting(); listPendingLokasi(); } catch (e) {} }
  if (nama === "daftar") { loadDaftar(); loadBelum(); }
  if (nama === "izin") { loadSaran(); }
}
function ada(id) { return !!document.getElementById(id); }
/* --- Notif izin: badge di nav + bunyi saat ada pengajuan baru (admin) --- */
let _pendingTerakhir = -1;
async function updateIzinBadge() {
  try {
    if (!ada("nav-izin-badge")) return;
    const j = await get("/api/pengajuan/pending");
    const n = j.pending || 0;
    const b = $("nav-izin-badge");
    b.style.display = n > 0 ? "" : "none";
    b.textContent = n;
    if (SAYA_ADMIN && _pendingTerakhir >= 0 && n > _pendingTerakhir) beep();
    _pendingTerakhir = n;
  } catch (e) { /* abaikan */ }
}
function beep() {
  try {
    const C = window.AudioContext || window.webkitAudioContext;
    if (!C) return;
    const x = new C();
    const o = x.createOscillator(), g = x.createGain();
    o.connect(g); g.connect(x.destination);
    o.frequency.value = 880; g.gain.value = 0.07;
    o.start(); o.stop(x.currentTime + 0.3);
    setTimeout(() => { try { x.close(); } catch (e) {} }, 600);
  } catch (e) { /* abaikan */ }
}
function info(el, ok, teks) {
  $(el).innerHTML = `<div class="msg ${ok ? "ok" : "no"}">${esc(teks)}</div>`;
}

/* --- Mode gelap / terang --- */
function toggleTheme() {
  const h = document.documentElement;
  const next = h.getAttribute("data-theme") === "dark" ? "" : "dark";
  if (next) h.setAttribute("data-theme", next); else h.removeAttribute("data-theme");
  try { localStorage.setItem("abs_theme", next); } catch (e) {}
  const b = $("theme-btn"); if (b) b.textContent = next ? "Terang" : "Gelap";
}
function initTheme() {
  let t = "";
  try { t = localStorage.getItem("abs_theme") || ""; } catch (e) {}
  if (t === "dark") document.documentElement.setAttribute("data-theme", "dark");
  const b = $("theme-btn"); if (b) b.textContent = t === "dark" ? "Terang" : "Gelap";
}

/* --- Jam hero + header --- */
function tickClock() {
  const n = new Date();
  const jam = n.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).replace(/\./g, ":");
  if (ada("jam-live")) $("jam-live").textContent = n.toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  if (ada("hero-clock")) $("hero-clock").textContent = jam;
  if (ada("hero-day")) $("hero-day").textContent = n.toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  if (ada("hero-date")) $("hero-date").textContent = n.toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "short", year: "numeric" }).toUpperCase();
}

/* --- Jalan pertama --- */
window.addEventListener("DOMContentLoaded", () => {
  initTheme();
  if (ada("j-tgl")) $("j-tgl").value = today();
  if ($("r-dari")) $("r-dari").value = today();
  if ($("r-sampai")) $("r-sampai").value = today();
  if ($("x-tgl")) $("x-tgl").value = today();
  if (ada("m-tgl")) $("m-tgl").value = today();
  tickClock(); setInterval(tickClock, 1000);
  let awal = "";
  try { awal = localStorage.getItem("abs_tab") || ""; } catch (e) {}
  if (SAYA_ADMIN) {
    loadHari(); loadSaran(); loadMesin(); loadData(); listAju(); loadDaftar(); loadBelum(); muatLaporan(true); updateIzinBadge();
    try { loadLokasiSetting(); listPendingLokasi(); updateLokasiBadge(); } catch (e) {}
  } else {
    loadHari(); loadSaran(); listAju(); isiIdentitasSaya(); updateIzinBadge(); // user: saran NIK tampil, tapi NIK terkunci ikut akun di server
    try { loadLokasiSetting(); listPendingLokasi(); updateLokasiBadge(); } catch (e) {}
  }
  if (awal && document.querySelector(`.nav button[data-tab="${awal}"]`)) {
    tab(awal, document.querySelector(`.nav button[data-tab="${awal}"]`));
  }
  /* Real-time: refresh tiap 10 detik */
  setInterval(() => {
    try {
      loadHari(); loadData(); updateIzinBadge();
      if (typeof updateLokasiBadge === "function") updateLokasiBadge();
      if (ada("page-tarik") && !$("page-tarik").classList.contains("hide")) muatLaporan(true);
      if (ada("page-izin") && !$("page-izin").classList.contains("hide")) listAju();
      if (typeof listPendingLokasi === "function" &&
          ada("card-approval-lokasi") && !$("page-hari").classList.contains("hide")) listPendingLokasi();
    } catch (e) {}
  }, 10000);
});
