#!/usr/bin/env bash
# Render build script — pins PLAYWRIGHT_BROWSERS_PATH so the chromium binary
# downloaded here is at the same path engine.py looks at runtime.
set -euo pipefail

export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/render/project/src/.playwright}"

pip install -r requirements.txt
playwright install chromium

echo "Browser cache contents:"
ls -la "$PLAYWRIGHT_BROWSERS_PATH" || echo "  (path missing — install likely failed)"
