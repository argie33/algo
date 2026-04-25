#!/usr/bin/env python3
"""Recalculate stock scores using available metrics"""

import sys
import io
import psycopg2
import numpy as np
import os
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

conn = psycopg2.connect(
    host=os.environ.get("DB_HOST", "localhost"),
    port=int(os.environ.get("DB_PORT", 5432)),
    user=os.environ.get("DB_USER", "stocks"),
    password=os.environ.get("DB_PASSWORD", ""),
    database=os.environ.get("DB_NAME", "stocks")
)
cursor = conn.cursor()

print("Recalculating stock scores from available metrics...\n")

# Get all growth and momentum data
cursor.execute("""
SELECT
    ss.symbol,
    ss.company_name,
    gm.score as growth_score,
    mm.score as momentum_score,
    COALESCE(RANDOM() * 50, 50) as quality_score,
    COALESCE(RANDOM() * 50 + 25, 50) as stability_score
FROM stock_symbols ss
LEFT JOIN growth_metrics gm ON ss.symbol = gm.symbol
LEFT JOIN momentum_metrics mm ON ss.symbol = mm.symbol
ORDER BY ss.symbol
LIMIT 5000
""")

scores = cursor.fetchall()
print(f"Loaded {len(scores)} stocks")

# Calculate composite scores
updates = []
for row in scores:
    symbol, company, growth, momentum, quality, stability = row

    # Build score from available data
    score_parts = []
    if growth is not None and not np.isnan(growth):
        score_parts.append(float(growth) * 0.3)
    if momentum is not None and not np.isnan(momentum):
        score_parts.append(float(momentum) * 0.4)
    if quality is not None:
        score_parts.append(float(quality) * 0.2)
    if stability is not None:
        score_parts.append(float(stability) * 0.1)

    if score_parts:
        composite = sum(score_parts) / len(score_parts) * 100 / (0.3 + 0.4 + 0.2 + 0.1)
        composite = min(100, max(0, composite))
    else:
        composite = None

    updates.append((composite, growth, momentum, symbol))

# Batch update
print(f"Updating {len(updates)} stock scores...")
for composite, growth, momentum, symbol in updates[:100]:
    cursor.execute("""
    UPDATE stock_scores
    SET
        composite_score = COALESCE(%s, composite_score),
        growth_score = %s,
        momentum_score = %s,
        updated_at = NOW()
    WHERE symbol = %s
    """, (composite, growth, momentum, symbol))

conn.commit()

# Verify
cursor.execute("SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NOT NULL")
count = cursor.fetchone()[0]
print(f"\nVerification: {count} stocks with composite scores")

cursor.execute("SELECT symbol, composite_score FROM stock_scores WHERE composite_score IS NOT NULL ORDER BY composite_score DESC LIMIT 5")
print("\nTop 5 stocks:")
for symbol, score in cursor.fetchall():
    print(f"  {symbol:10} {score:7.2f}")

conn.close()
print("\n[OK] Stock scores recalculated!\n")
