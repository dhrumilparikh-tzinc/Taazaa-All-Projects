"""
RAGAS regression check — compare current live query scores to stored baseline.

Usage:
    py scripts/ragas_regression_check.py [--days 7] [--tolerance 0.05] [--baseline docs/ragas_baseline.json]

Exit codes:
    0  all metrics within tolerance of baseline
    1  one or more metrics have regressed beyond tolerance
    2  baseline file not found or no live data available
"""
import json
import sys
import argparse
import math
from pathlib import Path

# ── Load .env and app path ─────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
DATABASE_URL = os.environ["DATABASE_URL"]

from sqlmodel import Session, create_engine, select
engine = create_engine(DATABASE_URL, echo=False)


METRIC_KEYS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall", "answer_correctness"]
TARGETS = {
    "faithfulness": 0.80,
    "answer_relevancy": 0.70,
    "context_precision": 0.70,
    "context_recall": 0.70,
    "answer_correctness": 0.70,
}


def compute_live_averages(days: int) -> dict[str, float | None]:
    from app.models.db import QueryHistory
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(days=days)

    with Session(engine) as db:
        rows = db.exec(
            select(QueryHistory).where(
                QueryHistory.created_at >= since,
                QueryHistory.ragas_scores.is_not(None),
            )
        ).all()

    if not rows:
        return {}

    sums = {k: 0.0 for k in METRIC_KEYS}
    counts = {k: 0 for k in METRIC_KEYS}
    for row in rows:
        try:
            scores = json.loads(row.ragas_scores)
        except Exception:
            continue
        for k in METRIC_KEYS:
            v = scores.get(k)
            if isinstance(v, (int, float)) and not math.isnan(v):
                sums[k] += v
                counts[k] += 1

    return {k: round(sums[k] / counts[k], 4) if counts[k] else None for k in METRIC_KEYS}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="Window of live queries to average")
    parser.add_argument("--tolerance", type=float, default=0.05, help="Max allowed regression vs baseline")
    parser.add_argument("--baseline", default="docs/ragas_baseline.json", help="Path to baseline JSON file")
    args = parser.parse_args()

    baseline_path = Path(__file__).parent.parent / args.baseline
    if not baseline_path.exists():
        print(f"[ERROR] Baseline file not found: {baseline_path}")
        print("  Run: py scripts/ragas_baseline.py  then copy C:/tmp/ragas_baseline.json → docs/ragas_baseline.json")
        sys.exit(2)

    with open(baseline_path) as f:
        baseline_data = json.load(f)
    baseline_avgs: dict = baseline_data.get("averages", {})

    print(f"Loading live RAGAS scores from last {args.days} days...")
    live_avgs = compute_live_averages(args.days)

    if not live_avgs:
        print("[WARN] No live RAGAS scores found in the last {args.days} days. Nothing to compare.")
        sys.exit(2)

    col_w = 25
    print(f"\n{'Metric':<{col_w}} {'Baseline':>9} {'Live':>9} {'Delta':>8} {'Target':>7} {'Status'}")
    print("-" * (col_w + 46))

    regressions = []
    for k in METRIC_KEYS:
        baseline_v = baseline_avgs.get(k)
        live_v = live_avgs.get(k)
        target = TARGETS[k]

        if baseline_v is None or live_v is None:
            status = "NO_DATA"
            delta_str = "N/A"
        else:
            delta = live_v - baseline_v
            delta_str = f"{delta:+.4f}"
            if live_v < target:
                status = "BELOW_TARGET"
                regressions.append((k, baseline_v, live_v, delta))
            elif delta < -args.tolerance:
                status = f"REGRESSED (>{args.tolerance:.0%})"
                regressions.append((k, baseline_v, live_v, delta))
            else:
                status = "OK"

        b_str = f"{baseline_v:.4f}" if baseline_v is not None else "N/A"
        l_str = f"{live_v:.4f}" if live_v is not None else "N/A"
        print(f"  {k:<{col_w-2}} {b_str:>9} {l_str:>9} {delta_str:>8} {target:>7.2f}  {status}")

    print()
    if regressions:
        print(f"[FAIL] {len(regressions)} metric(s) have regressed or are below target:")
        for k, b, l, d in regressions:
            print(f"  {k}: baseline={b:.4f}, live={l:.4f}, delta={d:+.4f}")
        sys.exit(1)
    else:
        print("[PASS] All metrics within tolerance of baseline.")
        sys.exit(0)


if __name__ == "__main__":
    main()
