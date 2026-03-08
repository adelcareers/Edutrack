#!/usr/bin/env python3
"""Quick DB connectivity check using Django's DB connection.

Usage:
  .venv/bin/python scripts/check_db.py

Exits 0 on success, non-zero on failure.
"""
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path (script lives in `scripts/`).
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'edutrack.settings')
import django

django.setup()
from django.db import connection

try:
    with connection.cursor() as cur:
        cur.execute('SELECT 1;')
        row = cur.fetchone()
    print('DB connectivity OK:', row)
    sys.exit(0)
except Exception as exc:
    print('DB connectivity FAILED:', repr(exc))
    sys.exit(2)
