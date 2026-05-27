"""
Download appraisal.db from Github Release URL during build phase.

Run by Render build command:
    python scripts/download_appraisal.py

Environment variable required:
    APPRAISAL_DB_URL - URL of appraisal.db (Github Release asset)
"""
import os
import sys
from pathlib import Path
import urllib.request

DB_URL = os.getenv("APPRAISAL_DB_URL", "").strip()
DB_PATH = Path(os.getenv("APPRAISAL_DB_PATH", "./data/appraisal.db"))

if not DB_URL:
    print("❌ APPRAISAL_DB_URL environment variable ไม่ได้ตั้ง")
    print("   ตั้งใน Render Dashboard → Environment → Add Variable")
    sys.exit(1)

# Create data directory
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

if DB_PATH.exists():
    size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"✓ appraisal.db already exists ({size_mb:.1f} MB) — skip download")
    sys.exit(0)

print(f"📥 Downloading appraisal.db...")
print(f"   From: {DB_URL}")
print(f"   To:   {DB_PATH}")

try:
    # Download with progress
    def progress(block_num, block_size, total_size):
        if total_size > 0:
            pct = min(100, block_num * block_size * 100 / total_size)
            mb = block_num * block_size / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            print(f"\r   Progress: {pct:.1f}% ({mb:.1f}/{total_mb:.1f} MB)", end='', flush=True)

    urllib.request.urlretrieve(DB_URL, DB_PATH, reporthook=progress)
    print()

    size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"✅ Downloaded {size_mb:.1f} MB → {DB_PATH}")

except Exception as e:
    print(f"\n❌ Download failed: {e}")
    sys.exit(1)
