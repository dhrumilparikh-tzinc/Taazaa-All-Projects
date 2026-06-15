"""
Bulk upload all completed local jobs to the live cloud API.

Reads completed jobs from your LOCAL PostgreSQL, finds the original files
in C:/tmp/geminirag_uploads, and uploads each one to the HF Space API.

Usage:
    py scripts/bulk_upload_to_cloud.py

Requirements:
  - Local PostgreSQL must be running
  - Files must still exist in C:/tmp/geminirag_uploads
  - The HF Space must be up (health check runs first)
"""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import psycopg2
import requests

# ── Config ────────────────────────────────────────────────────────────────────
CLOUD_API = "https://dhrumilparikh-multimodel-rag.hf.space"
CLOUD_EMAIL = "admin@geminirag.com"
CLOUD_PASS = "Admin1234"
LOCAL_DB = os.getenv("DATABASE_URL", "postgresql://geminirag:geminirag@localhost:5432/geminirag")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "C:/tmp/geminirag_uploads"))

# ── Step 1: health check ──────────────────────────────────────────────────────
print("Checking cloud API health...")
r = requests.get(f"{CLOUD_API}/health", timeout=15)
health = r.json()
if health.get("status") != "ok":
    print(f"API not healthy: {health}")
    sys.exit(1)
print(f"  OK — {health}")

# ── Step 2: login ─────────────────────────────────────────────────────────────
print(f"\nLogging in as {CLOUD_EMAIL}...")
r = requests.post(
    f"{CLOUD_API}/auth/login", json={"email": CLOUD_EMAIL, "password": CLOUD_PASS}, timeout=15
)
if r.status_code != 200:
    print(f"Login failed: {r.text}")
    sys.exit(1)
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("  Logged in OK")

# ── Step 3: read completed jobs from local DB ─────────────────────────────────
print(f"\nQuerying local DB for completed jobs...")
conn = psycopg2.connect(LOCAL_DB)
cur = conn.cursor()
cur.execute("""
    SELECT id, filename, file_type, file_path
    FROM jobs
    WHERE status = 'completed'
    ORDER BY created_at
""")
jobs = cur.fetchall()
cur.close()
conn.close()
print(f"  Found {len(jobs)} completed jobs locally")

# ── Step 4: upload each file ──────────────────────────────────────────────────
MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "image": "image/jpeg",
    "audio": "audio/mpeg",
    "video": "video/mp4",
}

ok = 0
skipped = 0
failed = 0

print(f"\nUploading {len(jobs)} files to {CLOUD_API}...\n")

for i, (job_id, filename, file_type, file_path) in enumerate(jobs, 1):
    # Files live at UPLOAD_DIR/<job_id>/<filename>
    local_path = Path(file_path)
    if not local_path.exists():
        # Try reconstructing from UPLOAD_DIR
        local_path = UPLOAD_DIR / str(job_id) / filename

    if not local_path.exists():
        print(f"  [{i:3}/{len(jobs)}] SKIP  {filename}  (file not found on disk)")
        skipped += 1
        continue

    mime = MIME.get(file_type, "application/octet-stream")

    try:
        with open(local_path, "rb") as f:
            r = requests.post(
                f"{CLOUD_API}/v1/files/upload",
                headers=headers,
                files={"file": (filename, f, mime)},
                timeout=60,
            )

        if r.status_code in (200, 201, 202):
            job_id_cloud = r.json().get("job_id", "?")
            print(f"  [{i:3}/{len(jobs)}] OK    {filename}  → job {job_id_cloud}")
            ok += 1
        else:
            print(f"  [{i:3}/{len(jobs)}] FAIL  {filename}  [{r.status_code}] {r.text[:80]}")
            failed += 1

    except Exception as exc:
        print(f"  [{i:3}/{len(jobs)}] ERROR {filename}  {exc}")
        failed += 1

    # Small delay to avoid overwhelming the API
    time.sleep(0.5)

print(f"\n{'='*55}")
print(f"Done — {ok} uploaded, {skipped} skipped (missing files), {failed} failed")
print(f"\nFiles are now processing in the cloud (Celery queue).")
print(f"Check progress at: {CLOUD_API}/v1/jobs")
print(f"Or watch the Jobs tab in the frontend.")
