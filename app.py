"""AI Opportunity Scan — etalase MANDIRI, siap deploy ke Render.

Beda dari etalase lokal (shamar/storefront.py) yang cuma meneruskan ke laptop:
app ini berdiri sendiri — panggil Gemini langsung, verifikasi lisensi Gumroad
sendiri. Laptop boleh mati.

Yang SENGAJA tidak ada di sini: dashboard, panel sumber, swarm, neuralink,
kuantum, memori. Hanya rute jualan. Itu batas keamanannya.

Penyimpanan laporan: di MEMORI dengan masa simpan, bukan file — hosting gratis
menghapus disk tiap restart. Pembeli tetap aman: laporan dikirim balik langsung
ke browser (disimpan di sessionStorage), dan selalu bisa dibuat ulang pakai
license key yang sama.

Env yang dibaca:
  GEMINI_API_KEY        (wajib)  kunci Google AI Studio
  GUMROAD_PRODUCT_ID    (sangat disarankan) tanpa ini = siapa pun dapat gratis
  GUMROAD_URL           link produk, untuk tombol beli
  GEMINI_MODEL          default gemini-flash-latest
  ORDER_PER_HOUR        default 5, rem anti-spam per alamat IP
"""
from __future__ import annotations

import json
import os
import re
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path

import requests
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

WEB = Path(__file__).resolve().parent / "web"

# Terima beberapa nama: pemilik sempat menamainya "gemini" di Vercel.
GEMINI_KEY = (os.environ.get("GEMINI_API_KEY")
              or os.environ.get("gemini")
              or os.environ.get("GEMINI_KEY") or "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest").strip()
GUMROAD_PRODUCT_ID = os.environ.get("GUMROAD_PRODUCT_ID", "1R1k0nEz7zSmriLHBHp3FA==").strip()
GUMROAD_URL = os.environ.get("GUMROAD_URL", "https://hillkia.gumroad.com/l/aiscan").strip()
ORDER_PER_HOUR = int(os.environ.get("ORDER_PER_HOUR", "5"))

REPORT_TTL = 60 * 60 * 24 * 3      # 3 hari cukup; pembeli sudah unduh PDF-nya
_reports: dict = {}                 # sid -> (kadaluarsa, data)
_hits: dict = defaultdict(deque)    # ip -> waktu order
_used_licenses: dict = {}           # license -> jumlah pakai (rem penyalahgunaan)

app = FastAPI(title="AI Opportunity Scan", docs_url=None, redoc_url=None, openapi_url=None)


# ----------------------------------------------------------------- util
def _ip(req: Request) -> str:
    fwd = req.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (req.client.host if req.client else "?")


def _rate_ok(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= ORDER_PER_HOUR:
        return False
    q.append(now)
    return True


def _sweep() -> None:
    now = time.time()
    for sid in [k for k, (exp, _) in _reports.items() if exp < now]:
        _reports.pop(sid, None)


def _extract_json(text: str) -> dict | None:
    """Ambil objek JSON pertama yang utuh — model kadang membungkusnya
    dengan ```fence atau menambah kalimat pembuka."""
    if not text:
        return None
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start = t.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(t[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _verify_license(key: str) -> tuple[bool, str]:
    """True kalau lisensi sah. Tanpa GUMROAD_PRODUCT_ID = mode terbuka (gratis)."""
    if not GUMROAD_PRODUCT_ID:
        return True, "open"                      # belum dikunci — pemilik sadar
    key = (key or "").strip()
    if not key:
        return False, "License key required. Get one by purchasing the scan."
    try:
        r = requests.post("https://api.gumroad.com/v2/licenses/verify",
                          data={"product_id": GUMROAD_PRODUCT_ID,
                                "license_key": key,
                                "increment_uses_count": "false"},
                          timeout=20)
        d = r.json()
    except Exception:                            # noqa: BLE001
        return False, "Could not reach the license server. Please try again."
    if not d.get("success"):
        return False, "That license key isn't valid for this product."
    if (d.get("purchase") or {}).get("refunded"):
        return False, "This purchase was refunded."
    used = _used_licenses.get(key, 0)
    if used >= 25:                               # wajar untuk 1 pembeli; blokir penyalahgunaan
        return False, "This key has been used many times. Contact support."
    _used_licenses[key] = used + 1
    return True, "ok"


PROMPT = """You are a top-tier strategy analyst (McKinsey/BCG caliber).

Analyse this industry or idea: "{industry}"

Identify the 7 strongest OPPORTUNITIES available right now. Be specific and
commercially useful — no generic "AI will transform everything" filler.

Return ONLY valid JSON, no prose, in exactly this shape:
{{
  "topic": "<short title of the scan>",
  "summary": "<2 sentences: the core thesis of where value is moving>",
  "sectors": [
    {{
      "name": "<opportunity name, max 4 words>",
      "score": <integer 0-100, how attractive right now>,
      "trend": "<up|flat|down>",
      "insight": "<one sentence: the specific shift that makes this viable NOW>",
      "peluang": "<one sentence: a concrete entry play someone could start this week>"
    }}
  ]
}}
Exactly 7 items in "sectors", ordered by score descending."""


def _generate(industry: str) -> tuple[dict | None, str]:
    if not GEMINI_KEY:
        return None, "Server is missing its AI key. The owner needs to set GEMINI_API_KEY."
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent")
    body = {"contents": [{"parts": [{"text": PROMPT.format(industry=industry)}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 8192}}
    try:
        r = requests.post(url, json=body, headers={"x-goog-api-key": GEMINI_KEY}, timeout=170)
    except requests.RequestException as e:
        return None, f"Could not reach the AI service ({type(e).__name__}). Try again."
    if r.status_code != 200:
        msg = "The AI service is busy right now. Please try again in a minute."
        if r.status_code in (401, 403):
            msg = "Server AI credentials rejected. The owner needs to check the key."
        return None, msg
    try:
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError):
        return None, "The AI returned an unexpected response. Please try again."
    data = _extract_json(text)
    if not data or not data.get("sectors"):
        return None, "Could not build a clean report this time. Please try again."
    return data, "ok"


# --------------------------------------------------------------- halaman
@app.get("/")
def index():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/r/{sid}")
def report_page(sid: str):
    return FileResponse(WEB / "report.html", headers={"Cache-Control": "no-cache"})


@app.get("/healthz")
def healthz():
    return {"ok": True, "ai": bool(GEMINI_KEY), "licensed": bool(GUMROAD_PRODUCT_ID)}


# ------------------------------------------------------------------- API
@app.get("/api/config")
def config():
    return {"buy_url": GUMROAD_URL, "live": bool(GUMROAD_URL),
            "licensed": bool(GUMROAD_PRODUCT_ID)}


@app.get("/api/report/{sid}")
def get_report(sid: str):
    _sweep()
    hit = _reports.get(sid)
    if not hit:
        return JSONResponse({"error": "not_found"}, status_code=404)
    return hit[1]


@app.post("/api/order")
async def order(request: Request):
    if not _rate_ok(_ip(request)):
        return JSONResponse({"ok": False, "message":
                             "Too many scans from your address. Please try again later."},
                            status_code=429)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "message": "Bad request."}, status_code=400)

    industry = str(body.get("industry", "")).strip()[:300]
    if len(industry) < 3:
        return {"ok": False, "message": "Please describe your industry or idea."}

    ok, why = _verify_license(str(body.get("license", "")))
    if not ok:
        return JSONResponse({"ok": False, "message": why}, status_code=402)

    data, msg = _generate(industry)
    if not data:
        return JSONResponse({"ok": False, "message": msg}, status_code=503)

    sid = secrets.token_hex(6)
    data["at"] = time.time()
    _sweep()
    _reports[sid] = (time.time() + REPORT_TTL, data)
    # Kirim laporannya sekalian: kalau server restart, browser tetap punya salinan.
    return {"ok": True, "id": sid, "report_url": f"/r/{sid}", "report": data}
