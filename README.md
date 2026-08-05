# 🛰️ Etalase AI Opportunity Scan — siap deploy ke Render

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
| `/healthz` | cek hidup (dipakai Render) |

## Deploy ke Render (sekali saja, ~10 menit)

1. **Naikkan folder ini ke GitHub** (repo boleh private).
2. Buka **render.com** → *New* → *Web Service* → sambungkan repo-nya.
3. Render otomatis membaca `render.yaml`. Kalau diminta manual:
   - Runtime **Python**
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   - Health check: `/healthz`
4. **Environment** → isi:

| Key | Isi | Wajib? |
|---|---|---|
| `GEMINI_API_KEY` | key AI Studio (`AIzaSy…`, 39 karakter) | **wajib** |
| `GUMROAD_PRODUCT_ID` | product ID Gumroad | **sangat disarankan** |
| `GUMROAD_URL` | link produk Gumroad | perlu, biar tombol beli hidup |
| `GEMINI_MODEL` | `gemini-flash-latest` | opsional |
| `ORDER_PER_HOUR` | `5` | opsional |

5. Deploy. Alamatnya jadi `https://<nama>.onrender.com`.
6. Balik ke Gumroad → produk → **Redirect / Receipt** → tempel alamat itu.

## ⚠️ Yang wajib diingat

**Tanpa `GUMROAD_PRODUCT_ID`, tokomu MODE TERBUKA** — siapa pun yang nemu
alamatnya dapat laporan gratis, dan kuota Gemini-mu yang kebakar. Rem 5
laporan/jam per IP cuma memperlambat, bukan mencegah. Isi ID-nya sebelum
menyebar link.

**Key Gemini harus format `AIzaSy…` (39 karakter)** dari
[aistudio.google.com/apikey](https://aistudio.google.com/apikey).
Yang berawalan `AQ.Ab8…` itu token sementara — akan ditolak 403.

**Paket gratis Render tidur setelah 15 menit nganggur** → pengunjung pertama
menunggu ~50 detik. Cukup untuk validasi & pembeli pertama. Kalau trafik sudah
nyata, naik ke Starter $7/bulan.

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
