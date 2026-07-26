#!/usr/bin/env python3
"""Quick check of stock_scores data availability."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.db.context import DatabaseContext

try:
    with DatabaseContext("read") as cur:
        # Check total scores
        cur.execute("SELECT COUNT(*) as cnt FROM stock_scores")
        total_scores = cur.fetchone()[0]
        print(f"[OK] Total stock_scores: {total_scores}")

        # Check if scores have composite_score values
        cur.execute("SELECT COUNT(*) as cnt FROM stock_scores WHERE composite_score IS NOT NULL")
        scores_with_composite = cur.fetchone()[0]
        print(f"[OK] Scores with composite_score: {scores_with_composite}")

        # Check if scores have required factors
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE momentum_score IS NOT NULL) as momentum,
                COUNT(*) FILTER (WHERE quality_score IS NOT NULL) as quality,
                COUNT(*) FILTER (WHERE value_score IS NOT NULL) as value,
                COUNT(*) FILTER (WHERE growth_score IS NOT NULL) as growth,
                COUNT(*) FILTER (WHERE stability_score IS NOT NULL) as stability,
                COUNT(*) FILTER (WHERE positioning_score IS NOT NULL) as positioning
            FROM stock_scores
        """)
        row = cur.fetchone()
        print(f"[OK] Factor coverage:")
        print(f"   Total: {row[0]}")
        print(f"   Momentum: {row[1]} ({100*row[1]//row[0] if row[0] else 0}%)")
        print(f"   Quality: {row[2]} ({100*row[2]//row[0] if row[0] else 0}%)")
        print(f"   Value: {row[3]} ({100*row[3]//row[0] if row[0] else 0}%)")
        print(f"   Growth: {row[4]} ({100*row[4]//row[0] if row[0] else 0}%)")
        print(f"   Stability: {row[5]} ({100*row[5]//row[0] if row[0] else 0}%)")
        print(f"   Positioning: {row[6]} ({100*row[6]//row[0] if row[0] else 0}%)")

        # Check data freshness
        cur.execute("SELECT MAX(updated_at) FROM stock_scores")
        latest = cur.fetchone()[0]
        print(f"[OK] Latest update: {latest}")

        # Sample a few scores
        cur.execute("""
            SELECT symbol, composite_score, momentum_score, quality_score, value_score, growth_score
            FROM stock_scores
            WHERE composite_score IS NOT NULL
            LIMIT 5
        """)
        print(f"[OK] Sample scores:")
        for row in cur.fetchall():
            print(f"   {row[0]}: {row[1]:.1f} (M:{row[2]} Q:{row[3]} V:{row[4]} G:{row[5]})")

except Exception as e:
    print(f"[ERROR] {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)
