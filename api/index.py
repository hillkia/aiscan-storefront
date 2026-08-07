"""Pintu masuk Vercel — semua permintaan diarahkan ke sini.

Vercel menjalankan berkas di folder /api sebagai fungsi. Aplikasi aslinya tetap
di app.py di akar repo, jadi kode yang sudah teruji tidak perlu diubah.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402,F401  (dipakai Vercel sebagai handler ASGI)
