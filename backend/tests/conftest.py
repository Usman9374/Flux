"""Pytest configuration shared across the test suite.

Makes the `app` package importable without requiring an installed `flux`
package, and stubs the env vars the FastAPI app reads at import time.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Database URL is required to import app.config — set a harmless dummy so the
# pure-Python tests in this suite don't actually need Postgres.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/flux_test")
