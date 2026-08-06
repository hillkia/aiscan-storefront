---
title: AI Opportunity Scan
emoji: 🛰️
colorFrom: orange
colorTo: red
sdk: docker
app_port: 7860
pinned: false
short_description: 7 ranked opportunities in your industry, in 60 seconds.
---

# 🛰️ Etalase AI Opportunity Scan

Toko online yang **berdiri sendiri**. Laptop boleh mati.

## Isinya cuma jualan
Dashboard, panel sumber, swarm, neuralink, kuantum, memori — **tidak ada di sini**.
Itu disengaja: server utama punya endpoint tanpa penjaga, jadi tak boleh kena internet.
Semua rute selain jualan otomatis 404 (sudah diuji).

| Rute | Guna |
|---|---|
| `/` | halaman jual |
| `/r/{id}` | laporan pembeli (bisa Download PDF) |
| `/api/config` | link beli + status lisensi |
| `/api/order` | verifikasi lisensi → panggil Gemini → laporan |
| `/api/report/{id}` | ambil ulang laporan |
| `/healthz` | cek hidup |

## Jalan di Hugging Face Spaces (gratis, tanpa kartu)

Space ini pakai **Docker** (lihat `Dockerfile`), mendengar di port **7860**.

Rahasia diisi di **Settings → Variables and secrets** milik Space:

| Nama | Isi | Wajib? |
|---|---|---|
| `GEMINI_API_KEY` | key AI Studio (`AIzaSy…`, 39 karakter) | **wajib** — simpan sebagai *Secret* |
| `GUMROAD_PRODUCT_ID` | product ID Gumroad | **sangat disarankan** |
| `GUMROAD_URL` | link produk Gumroad | perlu, biar tombol beli hidup |
| `GEMINI_MODEL` | `gemini-flash-latest` | opsional |
| `ORDER_PER_HOUR` | `5` | opsional |

Setelah Space hidup, alamatnya `https://<user>-<space>.hf.space` — tempel alamat itu
ke isi produk Gumroad menggantikan `[SCAN_URL_HERE]`.

## ⚠️ Yang wajib diingat

**Tanpa `GUMROAD_PRODUCT_ID`, tokomu MODE TERBUKA** — siapa pun yang nemu
alamatnya dapat laporan gratis, dan kuota Gemini-mu yang kebakar. Rem 5
laporan/jam per IP cuma memperlambat, bukan mencegah. Isi ID-nya sebelum
menyebar link.

**Key Gemini harus format `AIzaSy…` (39 karakter)** dari
[aistudio.google.com/apikey](https://aistudio.google.com/apikey).
Yang berawalan `AQ.Ab8…` itu token sementara — akan ditolak 403.

**Space gratis tidur setelah ~48 jam nganggur** → pengunjung pertama menunggu
beberapa puluh detik sementara container bangun. Cukup untuk validasi & pembeli
pertama.

## Laporan tidak disimpan di disk — itu disengaja
Hosting gratis menghapus disk tiap restart. Jadi laporan ditaruh di memori
(3 hari) **dan** dikirim balik ke browser pembeli (sessionStorage). Kalau server
restart, pembeli tetap bisa buka laporannya. Hilang pun aman: license key sama
bisa dipakai membuat ulang.

## Tes lokal dulu
```bash
cd ~/shamar/deploy
export GEMINI_API_KEY=AIzaSy...
../.venv/bin/python -m uvicorn app:app --port 8320
```
Buka http://localhost:8320
