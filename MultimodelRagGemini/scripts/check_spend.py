"""
Real-time spend estimate from usage_logs.

Usage:
    py scripts/check_spend.py

Gemini pricing used (as of June 2026):
  gemini-2.5-flash  input  : $0.15 / 1M tokens  (prompts ≤ 200K)
  gemini-2.5-flash  output : $0.60 / 1M tokens
  gemini-embedding-2        : $0.04 / 1M tokens
  gemini-embedding-001      : $0.04 / 1M tokens  (same tier)
"""

import os, sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, create_engine, text
engine = create_engine(os.environ["DATABASE_URL"], echo=False)

GEN_INPUT_PER_M  = 0.15   # $/1M prompt tokens
GEN_OUTPUT_PER_M = 0.60   # $/1M completion tokens
EMBED_PER_M      = 0.04   # $/1M embed tokens

with Session(engine) as db:
    rows = db.exec(text("""
        SELECT model, endpoint,
               COUNT(*)               AS calls,
               COALESCE(SUM(prompt_tokens), 0)     AS prompt_tok,
               COALESCE(SUM(completion_tokens), 0) AS compl_tok
        FROM usage_logs
        GROUP BY model, endpoint
        ORDER BY model, calls DESC
    """)).all()

    print(f"\n{'Model':<42} {'Endpoint':<26} {'Calls':>6} {'Prompt':>10} {'Compl':>10} {'Cost $':>9}")
    print("-" * 108)

    total_cost = 0.0
    for model, endpoint, calls, pt, ct in rows:
        if "embedding" in (model or "").lower():
            cost = (pt / 1_000_000) * EMBED_PER_M
        else:
            cost = (pt / 1_000_000) * GEN_INPUT_PER_M + (ct / 1_000_000) * GEN_OUTPUT_PER_M
        total_cost += cost
        print(f"{str(model):<42} {str(endpoint):<26} {calls:>6} {pt:>10,} {ct:>10,} {cost:>9.4f}")

    # Totals
    totals = db.exec(text("""
        SELECT
            COALESCE(SUM(CASE WHEN model NOT LIKE '%embedding%' THEN prompt_tokens     ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN model NOT LIKE '%embedding%' THEN completion_tokens ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN model     LIKE '%embedding%' THEN prompt_tokens     ELSE 0 END), 0)
        FROM usage_logs
    """)).one()
    gen_in, gen_out, emb = totals
    gen_in_cost  = (gen_in  / 1_000_000) * GEN_INPUT_PER_M
    gen_out_cost = (gen_out / 1_000_000) * GEN_OUTPUT_PER_M
    emb_cost     = (emb     / 1_000_000) * EMBED_PER_M

    print("-" * 108)
    print(f"\n  LLM input tokens  : {gen_in:>12,}   cost: ${gen_in_cost:.4f}")
    print(f"  LLM output tokens : {gen_out:>12,}   cost: ${gen_out_cost:.4f}")
    print(f"  Embed tokens      : {emb:>12,}   cost: ${emb_cost:.6f}")
    print(f"\n  {'TOTAL ESTIMATED SPEND':<30}        ${gen_in_cost + gen_out_cost + emb_cost:.4f}")
    print(f"  {'BUDGET REMAINING ($10)':<30}        ${10 - (gen_in_cost + gen_out_cost + emb_cost):.4f}")
    print()
    print("  NOTE: Only counts tokens logged AFTER the fix (new Celery run).")
    print("  Pre-fix runs had 0 logged — see Google AI Studio for full history.")
    print(f"  AI Studio: https://aistudio.google.com/app/apikey  -> 'View usage'")
