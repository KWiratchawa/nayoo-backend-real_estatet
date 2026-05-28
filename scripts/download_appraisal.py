"""
Download appraisal.db from Github Release (รองรับ private repo).

Private repo ต้องใช้ GitHub API endpoint + token:
  - หา asset id จาก releases API
  - download ผ่าน assets API ด้วย header Accept: application/octet-stream

Environment variables:
  APPRAISAL_DB_URL   - browser URL ของ asset (ใช้ parse owner/repo/tag/filename)
  APPRAISAL_DB_PATH  - ที่เก็บไฟล์ (default ./data/appraisal.db)
  GITHUB_TOKEN       - Personal Access Token (scope: repo) สำหรับ private repo
"""
import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

DB_URL = os.getenv("APPRAISAL_DB_URL", "").strip()
DB_PATH = Path(os.getenv("APPRAISAL_DB_PATH", "./data/appraisal.db"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()

if not DB_URL:
    print("❌ APPRAISAL_DB_URL ไม่ได้ตั้ง")
    sys.exit(1)

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

if DB_PATH.exists():
    size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"✓ appraisal.db already exists ({size_mb:.1f} MB) — skip download")
    sys.exit(0)


def parse_release_url(url: str):
    """
    Parse:
      https://github.com/OWNER/REPO/releases/download/TAG/FILENAME
    Returns: (owner, repo, tag, filename)
    """
    parts = url.replace("https://github.com/", "").split("/")
    # [OWNER, REPO, 'releases', 'download', TAG, FILENAME]
    if len(parts) < 6 or parts[2] != "releases" or parts[3] != "download":
        raise ValueError(f"URL format ไม่ถูกต้อง: {url}")
    owner, repo = parts[0], parts[1]
    tag = parts[4]
    filename = parts[5]
    return owner, repo, tag, filename


def download_progress(block_num, block_size, total_size):
    if total_size > 0:
        pct = min(100, block_num * block_size * 100 / total_size)
        mb = block_num * block_size / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        print(f"\r   Progress: {pct:.1f}% ({mb:.1f}/{total_mb:.1f} MB)", end='', flush=True)


print(f"📥 Downloading appraisal.db...")
print(f"   To: {DB_PATH}")

try:
    if GITHUB_TOKEN:
        # ===== Private repo: ใช้ GitHub API =====
        owner, repo, tag, filename = parse_release_url(DB_URL)
        print(f"   Private repo mode: {owner}/{repo} tag={tag} file={filename}")

        # 1. หา release ตาม tag
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
        req = urllib.request.Request(api_url)
        req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "nayoo-backend")

        with urllib.request.urlopen(req) as resp:
            release_data = json.loads(resp.read().decode())

        # 2. หา asset id ตาม filename
        asset_id = None
        for asset in release_data.get("assets", []):
            if asset["name"] == filename:
                asset_id = asset["id"]
                break

        if not asset_id:
            print(f"❌ ไม่พบ asset '{filename}' ใน release {tag}")
            print(f"   Assets ที่มี: {[a['name'] for a in release_data.get('assets', [])]}")
            sys.exit(1)

        # 3. Download asset ผ่าน API (octet-stream)
        asset_url = f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{asset_id}"
        req = urllib.request.Request(asset_url)
        req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
        req.add_header("Accept", "application/octet-stream")
        req.add_header("User-Agent", "nayoo-backend")

        with urllib.request.urlopen(req) as resp:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 8192
            with open(DB_PATH, "wb") as f:
                while True:
                    chunk = resp.read(block_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = downloaded * 100 / total_size
                        mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        print(f"\r   Progress: {pct:.1f}% ({mb:.1f}/{total_mb:.1f} MB)", end='', flush=True)
        print()

    else:
        # ===== Public repo: download URL ตรงๆ =====
        print("   Public repo mode (no token)")
        urllib.request.urlretrieve(DB_URL, DB_PATH, reporthook=download_progress)
        print()

    size_mb = DB_PATH.stat().st_size / (1024 * 1024)
    print(f"✅ Downloaded {size_mb:.1f} MB → {DB_PATH}")

except urllib.error.HTTPError as e:
    print(f"\n❌ HTTP Error {e.code}: {e.reason}")
    if e.code == 404:
        print("   - เช็คว่า GITHUB_TOKEN มี scope 'repo'")
        print("   - เช็คว่า URL/tag/filename ถูกต้อง")
    elif e.code == 401:
        print("   - GITHUB_TOKEN ไม่ถูกต้องหรือหมดอายุ")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Download failed: {e}")
    sys.exit(1)
