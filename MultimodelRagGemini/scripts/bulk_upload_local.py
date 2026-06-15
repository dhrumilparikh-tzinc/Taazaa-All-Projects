"""
Bulk upload all files from Dataset/scattered/ to the LOCAL API (localhost:8000).

Usage:
    py scripts/bulk_upload_local.py

Steps:
  1. Register admin user (ignored if already exists).
  2. Login to get JWT.
  3. Upload every file in Dataset/scattered/ via POST /v1/files/upload.
  4. Print live status as each file is queued.
"""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import urllib.request
import urllib.error
import json

API = "http://localhost:8000"
EMAIL = "admin@geminirag.com"
PASSWORD = "Admin1234"
SCATTER_DIR = ROOT / "Dataset" / "scattered"

MIME = {
    ".pdf":  "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv":  "text/csv",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".mp4":  "video/mp4",
    ".mp3":  "audio/mpeg",
    ".wav":  "audio/wav",
}


def api_json(path, method="GET", payload=None, token=None):
    url = f"{API}{path}"
    data = json.dumps(payload).encode() if payload else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def upload_file(file_path: Path, token: str) -> dict:
    """Multipart POST /v1/files/upload"""
    import http.client, mimetypes, email.generator, io
    suffix = file_path.suffix.lower()
    mime = MIME.get(suffix, "application/octet-stream")

    boundary = "------BoundaryXX1234"
    body = io.BytesIO()

    def write(s):
        body.write(s.encode() if isinstance(s, str) else s)

    write(f"--{boundary}\r\n")
    write(f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n')
    write(f"Content-Type: {mime}\r\n\r\n")
    body.write(file_path.read_bytes())
    write(f"\r\n--{boundary}--\r\n")

    payload = body.getvalue()
    url = f"{API}/v1/files/upload"
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(payload)),
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


# ── 1. health check ────────────────────────────────────────────────────────────
print("Checking API health...")
h = api_json("/health")
print(f"  {h}")
if h.get("status") != "ok":
    sys.exit("API not healthy, aborting.")

# ── 2. register admin (ignore 409 if already exists) ──────────────────────────
print(f"\nRegistering {EMAIL}...")
try:
    api_json("/auth/register", "POST", {"email": EMAIL, "password": PASSWORD, "role": "admin"})
    print("  Registered OK")
except urllib.error.HTTPError as e:
    if e.code == 409:
        print("  Already registered")
    else:
        raise

# ── 3. login ──────────────────────────────────────────────────────────────────
print("Logging in...")
login_resp = api_json("/auth/login", "POST", {"email": EMAIL, "password": PASSWORD})
token = login_resp["access_token"]
print(f"  Token obtained ({login_resp['role']})")

# ── 4. upload all files ────────────────────────────────────────────────────────
files = sorted(SCATTER_DIR.iterdir()) if SCATTER_DIR.exists() else []
print(f"\nFound {len(files)} files in {SCATTER_DIR}")
print("=" * 60)

ok = 0; failed = 0

for i, fp in enumerate(files, 1):
    if not fp.is_file():
        continue
    try:
        result = upload_file(fp, token)
        job_id = result.get("job_id", "?")
        ftype  = result.get("file_type", "?")
        print(f"  [{i:3}/{len(files)}] QUEUED  {fp.name}  ({ftype}) -> job {job_id}")
        ok += 1
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:120]
        print(f"  [{i:3}/{len(files)}] FAIL    {fp.name}  [{e.code}] {body}")
        failed += 1
    except Exception as exc:
        print(f"  [{i:3}/{len(files)}] ERROR   {fp.name}  {exc}")
        failed += 1
    # Respect Gemini rate limits — a short pause between uploads
    time.sleep(0.3)

print("=" * 60)
print(f"Done — {ok} queued, {failed} failed")
print(f"\nFiles are processing in Celery/Gemini. Watch progress at:")
print(f"  Frontend: http://localhost:5173")
print(f"  Jobs API: {API}/v1/jobs")
