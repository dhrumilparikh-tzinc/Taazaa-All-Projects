"""
Check current Gemini API spend estimate from the usage_logs table.

Usage:
    py scripts/check_budget.py

Gemini 2.5 Flash pricing:
    Input:  $0.075 / 1M tokens
    Output: $0.30  / 1M tokens
    Embedding (gemini-embedding-001): ~$0.00001 / 1K tokens (negligible)
"""

import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2, os, json

BUDGET_USD = 10.00
INPUT_PRICE  = 0.075 / 1_000_000   # per token
OUTPUT_PRICE = 0.30  / 1_000_000   # per token

# File API PDF cost estimates (tokens not captured in usage_logs)
# ~6K input + 9K output per PDF processed via File API
PDF_INPUT_PER_FILE  = 6_000
PDF_OUTPUT_PER_FILE = 9_000

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur  = conn.cursor()

# Logged token usage (text LLM calls)
cur.execute("""
    SELECT COALESCE(SUM(prompt_tokens),0),
           COALESCE(SUM(completion_tokens),0),
           COUNT(*)
    FROM usage_logs
""")
logged_in, logged_out, log_calls = cur.fetchone()

# Count completed PDFs (File API calls — tokens not in usage_logs)
cur.execute("SELECT COUNT(*) FROM jobs WHERE status = 'completed' AND file_type = 'pdf'")
pdf_done = cur.fetchone()[0]

# Job stats
cur.execute("SELECT status, COUNT(*), COALESCE(SUM(chunk_count),0) FROM jobs GROUP BY status")
job_stats = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

# Query history (RAGAS evaluations done)
cur.execute("SELECT COUNT(*) FROM query_history WHERE ragas_scores IS NOT NULL")
ragas_done = cur.fetchone()[0]

cur.close(); conn.close()

# ── Cost calculation ───────────────────────────────────────────────────────────
# Logged LLM calls (DOCX/XLSX/Image summary + RAG queries)
cost_logged = logged_in * INPUT_PRICE + logged_out * OUTPUT_PRICE

# PDF File API calls (unlogged — estimated)
pdf_in  = pdf_done * PDF_INPUT_PER_FILE
pdf_out = pdf_done * PDF_OUTPUT_PER_FILE
cost_pdf = pdf_in * INPUT_PRICE + pdf_out * OUTPUT_PRICE

total_spent = cost_logged + cost_pdf

# ── Remaining work estimate ────────────────────────────────────────────────────
pending = job_stats.get("pending", (0,0))[0]
processing = job_stats.get("processing", (0,0))[0]
completed  = job_stats.get("completed", (0,0))[0]
total_jobs = sum(v[0] for v in job_stats.values())

remaining_jobs = pending + processing
# Estimate 3K input + 2K output per remaining non-PDF file (conservative)
est_remaining_cost = remaining_jobs * (3_000 * INPUT_PRICE + 2_000 * OUTPUT_PRICE)

# RAGAS: ~30K input + 10K output per question (faithfulness + relevancy via LLM)
RAGAS_RUNS_PLANNED = 3
RAGAS_QUESTIONS    = 12
ragas_remaining = max(0, RAGAS_RUNS_PLANNED - (ragas_done // RAGAS_QUESTIONS))
est_ragas_cost  = ragas_remaining * RAGAS_QUESTIONS * (30_000 * INPUT_PRICE + 10_000 * OUTPUT_PRICE)

est_total = total_spent + est_remaining_cost + est_ragas_cost

# ── Report ─────────────────────────────────────────────────────────────────────
print("=" * 55)
print("  GEMINI API BUDGET TRACKER")
print("=" * 55)
print(f"  Budget cap:          ${BUDGET_USD:.2f}")
print()
print(f"  === SPENT SO FAR ===")
print(f"  Text LLM calls:      ${cost_logged:.4f}  ({log_calls} calls, {logged_in:,} in / {logged_out:,} out tokens)")
print(f"  PDF File API est:    ${cost_pdf:.4f}  ({pdf_done} PDFs × ~15K tokens each)")
print(f"  Total spent est:     ${total_spent:.4f}")
print()
print(f"  === JOBS ===")
print(f"  Completed:           {completed}/{total_jobs}")
print(f"  Remaining (queue):   {remaining_jobs}")
total_chunks = sum(v[1] for v in job_stats.values())
print(f"  Total chunks indexed:{total_chunks:,}")
print()
print(f"  === PROJECTIONS ===")
print(f"  Remaining processing:~${est_remaining_cost:.4f}  ({remaining_jobs} jobs)")
print(f"  RAGAS ({ragas_remaining} more runs):  ~${est_ragas_cost:.4f}  ({RAGAS_QUESTIONS} questions/run)")
print(f"  Projected total:     ~${est_total:.4f}")
print(f"  Budget remaining:    ~${BUDGET_USD - est_total:.4f}")
print()
pct = (est_total / BUDGET_USD) * 100
bar_len = int(pct / 2)
bar = "#" * bar_len + "-" * (50 - bar_len)
print(f"  [{bar}] {pct:.1f}% of $10")
if est_total < BUDGET_USD * 0.7:
    print(f"  STATUS: SAFE - well within budget")
elif est_total < BUDGET_USD:
    print(f"  STATUS: OK - within budget")
else:
    print(f"  STATUS: WARNING - projected to exceed budget!")
print("=" * 55)
