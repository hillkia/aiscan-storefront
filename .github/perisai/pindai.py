#!/usr/bin/env python3
"""PINDAI — periksa semua aplikasi Hillkia, cari 7 lubang keamanan yang nyata.

    python3 pindai.py                 # periksa semua folder di ~
    python3 pindai.py ~/ocklu-jarvis  # periksa satu folder
    python3 pindai.py --cepat         # lewati penelusuran riwayat git

Hasil -> data/temuan.json  dan  LAPORAN.md
Semua temuan menyebut berkas dan nomor baris yang sebenarnya. Tidak ada angka karangan.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from perisai import cari_rahasia, samar  # noqa: E402

AKAR = Path(__file__).resolve().parent
DATA = AKAR / "data"
DATA.mkdir(exist_ok=True)
RUMAH = Path.home()

LEWATI_DIR = {".git", "node_modules", "venv", ".venv", "env", "__pycache__", "site-packages",
              "dist", "build", ".next", ".cache", "Library", "Applications", "Music",
              "Movies", "Pictures", "Public", "Downloads", ".Trash", "vendor", ".astro",
              "coverage", "target", ".pytest_cache", ".mypy_cache", "ocklu-perisai"}
EKST_KODE = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".html", ".htm",
             ".php", ".rb", ".go", ".java", ".sh", ".yml", ".yaml", ".json", ".env",
             ".txt", ".md", ".sql", ".toml", ".ini", ".cfg"}
MAX_BERKAS = 1_500_000          # 1.5 MB per berkas
MAX_RIWAYAT = 30_000_000        # 30 MB riwayat git per proyek

# --------------------------------------------------------------- pola periksa
RX = {
    "sql": re.compile(r"""(?ix)
        (?:\.execute|\.executemany|\.executescript|\.raw|read_sql)\s*\(\s*
        (?: f["'] | ["'][^"']*["']\s*%\s* | ["'][^"']*["']\s*\+ | ["'][^"']*["']\s*\.format\b )
    """),
    "sql_var": re.compile(r"""(?ix)\.execute\w*\s*\(\s*[A-Za-z_]\w*\s*%\s*"""),
    "xss_py": re.compile(r"""(?ix)
        (?: wfile\.write | \.send_response | return\s+ | \+= )?[^\n]*
        f["']{1,3}[^"'\n]*<\s*(?:div|span|p|td|li|h[1-6]|a|table|script|body)[^"'\n]*\{[a-z_][\w.\[\]()]*\}
    """),
    "xss_js": re.compile(r"(?i)\.innerHTML\s*(?:\+)?=\s*(?!['\"`]\s*['\"`])[^;\n]*(?:\$\{|\+\s*[A-Za-z_])"),
    "xss_js2": re.compile(r"(?i)(?:document\.write|insertAdjacentHTML)\s*\(\s*[^)'\"]*(?:\$\{|\+)"),
    "ai_prompt": re.compile(r"""(?ix)
        (?: prompt | messages | system | user_msg | pesan ) \s* (?: = | : ) \s*
        f["']{1,3}[^\n]{0,200}\{ [a-z_][\w.\[\]()]* \}
    """),
    "login": re.compile(r"(?i)\b(?:password|passwd|sandi|kata_sandi)\b\s*(?:==|!=|\.lower\(\)\s*==)|check_password|verify_password|compare_digest\s*\([^)]*(?:sandi|password)"),
    "kunci_pintu": re.compile(r"(?i)\b(?:lockout|brute|percobaan|gagal_login|rate_?limit|too_many|gerbang|attempt)\w*"),
    "post": re.compile(r"(?i)def\s+do_POST|@app\.(?:route|post)\([^)]*(?:POST|methods)|methods\s*=\s*\[[^\]]*POST"),
    "csrf": re.compile(r"(?i)csrf|xsrf|same_?site|samesite|token\.sah|anti_forgery"),
    "idor": re.compile(r"""(?ix)
        (?: params?|query|args|form|qs|get )\s*(?:\.get\s*\(|\[)\s*['"](?:id|user_?id|order_?id|pesanan|nomor|no)['"]
    """),
    "milik_cek": re.compile(r"(?i)\bmilik\b|owner|user_id\s*==|pemilik|wajib_milik|belongs_to|current_user"),
    "biner": re.compile(rb"\x00"),
}
JUDUL = {
    "rahasia": "1. Kunci/sandi bocor di kode",
    "gerbang": "2. Pintu login tanpa kunci otomatis",
    "sql": "3. Query database disambung dari ketikan orang",
    "milik": "4. Data orang lain bisa dibuka",
    "teks": "5. Ketikan orang bisa jalan sebagai perintah di browser",
    "token": "6. Situs lain bisa menyuruh aplikasi kita",
    "saring_ai": "7. Perintah AI bisa dibajak",
    "berkas": "8. Berkas rahasia terbuka / ikut tersimpan di git",
}


def proyek_proyek(argv: list[str]) -> list[Path]:
    if argv:
        return [Path(a).expanduser().resolve() for a in argv]
    out = []
    for d in sorted(RUMAH.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or d.name in LEWATI_DIR:
            continue
        if d.name in {"Documents", "Desktop"}:
            continue
        out.append(d)
    return out


def berkas_kode(akar: Path):
    for dirpath, dirnames, filenames in os.walk(akar):
        dirnames[:] = [d for d in dirnames if d not in LEWATI_DIR and not d.startswith(".git")]
        for fn in filenames:
            p = Path(dirpath) / fn
            if fn.startswith(".env") or p.suffix.lower() in EKST_KODE:
                try:
                    if p.stat().st_size > MAX_BERKAS or p.is_symlink():
                        continue
                except OSError:
                    continue
                if ".min." in fn or fn.endswith((".lock", "-lock.json")):
                    continue
                yield p


def baca(p: Path) -> str | None:
    try:
        b = p.read_bytes()
        if RX["biner"].search(b[:4000]):
            return None
        return b.decode("utf-8", "replace")
    except Exception:
        return None


def git_terlacak(akar: Path, berkas: Path) -> bool:
    try:
        r = subprocess.run(["git", "-C", str(akar), "ls-files", "--error-unmatch", str(berkas)],
                           capture_output=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def riwayat_git(akar: Path) -> list[dict]:
    """Cari kunci yang pernah ada di versi lama (video: git ingat semua versi)."""
    if not (akar / ".git").exists():
        return []
    temuan, terbaca = [], 0
    try:
        pr = subprocess.Popen(
            ["git", "-C", str(akar), "log", "-p", "--all", "-U0", "--no-color",
             "--pickaxe-all", "--", "."],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="replace")
    except Exception:
        return []
    komit = ""
    sudah = set()
    try:
        for baris in pr.stdout:
            terbaca += len(baris)
            if terbaca > MAX_RIWAYAT:
                break
            if baris.startswith("commit "):
                komit = baris.split()[1][:8]
            elif baris.startswith("+") and not baris.startswith("+++"):
                for jenis, cuplik in cari_rahasia(baris[1:]):
                    k = (jenis, cuplik)
                    if k in sudah:
                        continue
                    sudah.add(k)
                    temuan.append({"jenis": jenis, "cuplik": cuplik, "komit": komit})
                    if len(temuan) >= 40:
                        raise StopIteration
    except StopIteration:
        pass
    finally:
        try:
            pr.kill()
        except Exception:
            pass
    return temuan


def periksa_proyek(akar: Path, cepat: bool = False) -> dict:
    t = {k: [] for k in JUDUL}
    n_berkas = 0
    punya_login = punya_kunci_pintu = punya_post = punya_csrf = False
    berkas_login: list[str] = []

    for p in berkas_kode(akar):
        isi = baca(p)
        if isi is None:
            continue
        n_berkas += 1
        rel = str(p.relative_to(akar))
        baris_semua = isi.split("\n")
        nama = p.name.lower()
        contoh = nama.endswith((".example", ".sample", ".template", ".contoh")) or ".example" in nama
        env_like = (nama.startswith(".env") or nama in {"secrets.json", "credentials.json", "config.json"}) and not contoh

        # --- 1 & 8. rahasia
        for i, b in enumerate(baris_semua, 1):
            if len(b) > 4000:
                continue
            for jenis, cuplik in cari_rahasia(b):
                sasaran = "berkas" if (env_like or contoh) else "rahasia"
                t[sasaran].append({"berkas": rel, "baris": i, "jenis": jenis,
                                   "cuplik": cuplik, "yakin": "PASTI"})
        if env_like:
            try:
                mode = oct(p.stat().st_mode)[-3:]
            except OSError:
                mode = "?"
            if mode not in ("600", "400"):
                t["berkas"].append({"berkas": rel, "baris": 0, "jenis": "Berkas rahasia bisa dibaca akun lain",
                                    "cuplik": f"izin {mode}, seharusnya 600", "yakin": "PASTI"})
            if git_terlacak(akar, p):
                t["berkas"].append({"berkas": rel, "baris": 0, "jenis": "Berkas rahasia ikut tersimpan di git",
                                    "cuplik": "harus dikeluarkan dari git + ganti semua kunci", "yakin": "PASTI"})

        # --- 3. sql
        for i, b in enumerate(baris_semua, 1):
            if RX["sql"].search(b) or RX["sql_var"].search(b):
                t["sql"].append({"berkas": rel, "baris": i, "jenis": "Query disambung dari teks",
                                 "cuplik": b.strip()[:120], "yakin": "PASTI"})

        # --- 5. teks (XSS)
        for i, b in enumerate(baris_semua, 1):
            if RX["xss_js"].search(b) or RX["xss_js2"].search(b):
                t["teks"].append({"berkas": rel, "baris": i, "jenis": "Isi halaman ditulis mentah dari variabel",
                                  "cuplik": b.strip()[:120], "yakin": "PERLU DICEK"})
            elif p.suffix == ".py" and RX["xss_py"].search(b):
                t["teks"].append({"berkas": rel, "baris": i, "jenis": "HTML dirangkai dengan isi variabel",
                                  "cuplik": b.strip()[:120], "yakin": "PERLU DICEK"})

        # --- 7. saring_ai
        if re.search(r"(?i)openai|anthropic|groq|gemini|ollama|llm|chat\.completions|generate_content", isi):
            for i, b in enumerate(baris_semua, 1):
                if RX["ai_prompt"].search(b):
                    t["saring_ai"].append({"berkas": rel, "baris": i,
                                           "jenis": "Ketikan orang masuk langsung ke perintah AI",
                                           "cuplik": b.strip()[:120], "yakin": "PERLU DICEK"})

        # --- 4. milik (data orang lain)
        if RX["idor"].search(isi) and not RX["milik_cek"].search(isi):
            for i, b in enumerate(baris_semua, 1):
                if RX["idor"].search(b):
                    t["milik"].append({"berkas": rel, "baris": i,
                                       "jenis": "Nomor data diambil dari alamat, pemiliknya tidak dicek",
                                       "cuplik": b.strip()[:120], "yakin": "PERLU DICEK"})
                    break

        # --- 2 & 6. penanda tingkat proyek
        if RX["login"].search(isi):
            punya_login = True
            berkas_login.append(rel)
        if RX["kunci_pintu"].search(isi):
            punya_kunci_pintu = True
        if RX["post"].search(isi):
            punya_post = True
        if RX["csrf"].search(isi):
            punya_csrf = True

    if punya_login and not punya_kunci_pintu:
        t["gerbang"].append({"berkas": berkas_login[0] if berkas_login else "?", "baris": 0,
                             "jenis": "Ada login, tapi tidak ada penguncian setelah salah berkali-kali",
                             "cuplik": f"{len(berkas_login)} berkas memeriksa sandi", "yakin": "PASTI"})
    if punya_post and not punya_csrf:
        t["token"].append({"berkas": "(seluruh proyek)", "baris": 0,
                           "jenis": "Ada halaman yang mengubah data, tanpa tanda pengenal rahasia",
                           "cuplik": "belum ada CSRF / SameSite", "yakin": "PERLU DICEK"})

    if not cepat:
        for r in riwayat_git(akar):
            t["rahasia"].append({"berkas": f"(riwayat git, komit {r['komit']})", "baris": 0,
                                 "jenis": r["jenis"] + " — pernah tersimpan di versi lama",
                                 "cuplik": r["cuplik"], "yakin": "PASTI"})

    return {"proyek": akar.name, "jalur": str(akar), "berkas_diperiksa": n_berkas, "temuan": t}


def main() -> int:
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    cepat = "--cepat" in sys.argv
    mulai = time.time()
    daftar = proyek_proyek(argv)
    print(f"[perisai] memeriksa {len(daftar)} folder…", flush=True)

    semua, ringkas = [], {k: 0 for k in JUDUL}
    for i, d in enumerate(daftar, 1):
        try:
            h = periksa_proyek(d, cepat)
        except Exception as e:
            print(f"  ! {d.name}: {e}", flush=True)
            continue
        n = sum(len(v) for v in h["temuan"].values())
        for k, v in h["temuan"].items():
            ringkas[k] += len(v)
        semua.append(h)
        print(f"  [{i}/{len(daftar)}] {d.name:<34} {h['berkas_diperiksa']:>5} berkas  {n:>4} temuan", flush=True)

    hasil = {
        "waktu": time.strftime("%Y-%m-%d %H:%M:%S"),
        "detik": round(time.time() - mulai, 1),
        "jumlah_proyek": len(semua),
        "jumlah_berkas": sum(h["berkas_diperiksa"] for h in semua),
        "ringkas": ringkas,
        "total": sum(ringkas.values()),
        "judul": JUDUL,
        "proyek": semua,
    }
    (DATA / "temuan.json").write_text(json.dumps(hasil, ensure_ascii=False, indent=1), encoding="utf-8")
    tulis_laporan(hasil)
    print(f"\n[perisai] selesai {hasil['detik']}s — {hasil['total']} temuan "
          f"di {hasil['jumlah_berkas']} berkas. Lihat LAPORAN.md")
    return 0


def tulis_laporan(h: dict) -> None:
    b = [f"# Laporan Perisai Ocklu\n", f"Diperiksa {h['waktu']} — {h['jumlah_proyek']} folder, "
         f"{h['jumlah_berkas']} berkas, {h['detik']} detik.\n",
         f"**Total temuan: {h['total']}**\n", "| Jenis | Jumlah |", "|---|---|"]
    for k, judul in h["judul"].items():
        b.append(f"| {judul} | {h['ringkas'][k]} |")
    b.append("\n---\n")
    urut = sorted(h["proyek"], key=lambda p: -sum(len(v) for v in p["temuan"].values()))
    for p in urut:
        n = sum(len(v) for v in p["temuan"].values())
        if not n:
            continue
        b.append(f"## {p['proyek']} — {n} temuan")
        for k, judul in h["judul"].items():
            v = p["temuan"][k]
            if not v:
                continue
            b.append(f"\n**{judul}** ({len(v)})\n")
            for x in v[:15]:
                lok = f"`{x['berkas']}`" + (f":{x['baris']}" if x["baris"] else "")
                b.append(f"- [{x['yakin']}] {lok} — {x['jenis']} — `{x['cuplik']}`")
            if len(v) > 15:
                b.append(f"- …dan {len(v)-15} lagi")
        b.append("")
    (AKAR / "LAPORAN.md").write_text("\n".join(b), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
