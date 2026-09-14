#!/usr/bin/env python3
"""Penjaga awan — dijalankan GitHub Actions tiap hari, walau laptop mati.

Memeriksa isi repo ini dengan 7+1 blok keamanan Perisai Ocklu, menulis
`PERISAI-LAPORAN.md`, dan membuka/memperbarui satu laporan (issue) di repo
yang sama supaya bisa dibaca dari HP.
"""
from __future__ import annotations
import json, os, sys, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pindai  # noqa: E402

REPO = Path(os.environ.get("GITHUB_WORKSPACE", ".")).resolve()
JUDUL_ISSUE = "Perisai: hasil pemeriksaan keamanan harian"


def kirim_github(metode, jalur, data=None):
    tok = os.environ.get("GITHUB_TOKEN")
    if not tok:
        return None
    r = urllib.request.Request(
        "https://api.github.com" + jalur, method=metode,
        data=json.dumps(data).encode() if data else None,
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json", "User-Agent": "perisai-ocklu"})
    try:
        with urllib.request.urlopen(r, timeout=30) as f:
            return json.loads(f.read().decode())
    except urllib.error.HTTPError as e:
        print(f"[perisai] github {e.code}: {e.read()[:200]!r}")
        return None


def main() -> int:
    h = pindai.periksa_proyek(REPO, cepat=False)
    t = h["temuan"]
    total = sum(len(v) for v in t.values())
    pasti = sum(1 for v in t.values() for x in v if x["yakin"] == "PASTI")

    b = [f"# Perisai — {REPO.name}", "",
         f"{h['berkas_diperiksa']} berkas diperiksa · **{total} temuan** ({pasti} pasti).", "",
         "| Blok | Jumlah |", "|---|---|"]
    for k, j in pindai.JUDUL.items():
        b.append(f"| {j} | {len(t[k])} |")
    for k, j in pindai.JUDUL.items():
        if not t[k]:
            continue
        b += ["", f"### {j}", ""]
        for x in t[k][:25]:
            lok = f"`{x['berkas']}`" + (f":{x['baris']}" if x["baris"] else "")
            b.append(f"- **[{x['yakin']}]** {lok} — {x['jenis']} — `{x['cuplik']}`")
        if len(t[k]) > 25:
            b.append(f"- …dan {len(t[k]) - 25} lagi")
    isi = "\n".join(b)
    (REPO / "PERISAI-LAPORAN.md").write_text(isi + "\n", encoding="utf-8")

    ringkas = os.environ.get("GITHUB_STEP_SUMMARY")
    if ringkas:
        Path(ringkas).write_text(isi[:60000], encoding="utf-8")

    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo and total:
        ada = kirim_github("GET", f"/repos/{repo}/issues?state=open&per_page=50") or []
        punya = next((i for i in ada if i.get("title") == JUDUL_ISSUE), None)
        badan = isi[:60000] + f"\n\n_diperbarui otomatis oleh Perisai Ocklu_"
        if punya:
            kirim_github("PATCH", f"/repos/{repo}/issues/{punya['number']}", {"body": badan})
            print(f"[perisai] laporan diperbarui: #{punya['number']}")
        else:
            r = kirim_github("POST", f"/repos/{repo}/issues", {"title": JUDUL_ISSUE, "body": badan})
            print(f"[perisai] laporan dibuat: #{(r or {}).get('number')}")
    print(f"[perisai] {REPO.name}: {total} temuan ({pasti} pasti) di {h['berkas_diperiksa']} berkas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
