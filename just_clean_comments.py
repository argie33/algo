#!/usr/bin/env python3
"""Remove orphaned type: ignore comments."""

import re
from pathlib import Path

FILES_TO_FIX = [
    "lambda/api/routes/settings.py",
    "lambda/api/routes/research.py",
    "lambda/api/routes/logs.py",
    "lambda/api/routes/openapi_spec.py",
    "lambda/api/routes/audit.py",
    "lambda/api/routes/algo_handlers/orchestration.py",
    "lambda/api/routes/algo_handlers/external.py",
    "lambda/api/routes/algo_handlers/market.py",
    "lambda/api/routes/algo_handlers/dashboard.py",
    "lambda/api/routes/algo_handlers/sector.py",
    "lambda/api/routes/algo_handlers/signals.py",
    "lambda/api/routes/algo_handlers/config.py",
    "lambda/api/routes/algo_handlers/monitoring.py",
    "lambda/api/routes/algo.py",
    "lambda/api/routes/stocks.py",
    "lambda/api/routes/signals.py",
    "lambda/api/routes/sectors.py",
    "lambda/api/routes/scores.py",
    "lambda/api/routes/health.py",
    "lambda/api/routes/market.py",
    "lambda/api/routes/prices.py",
    "lambda/api/routes/positions.py",
    "lambda/api/routes/sentiment.py",
    "lambda/api/routes/earnings.py",
    "lambda/api/routes/economic.py",
    "lambda/api/routes/financials.py",
    "lambda/api/routes/data_coverage.py",
    "lambda/api/routes/contact.py",
    "lambda/api/routes/trades.py",
    "lambda/api/routes/risk_dashboard.py",
    "lambda/api/routes/admin.py",
    "lambda/api/routes/user_isolation.py",
    "lambda/api/api_router.py",
]

def clean_file(filepath: str) -> int:
    """Remove orphaned type: ignore comments."""
    path = Path(filepath)
    if not path.exists():
        return 0
    
    content = path.read_text()
    
    # Remove orphaned type: ignore comments that are after a closing paren
    # Pattern: ...something)\s*#\s*type:\s*ignore[...])
    # Should become: ...something)
    original_len = len(content)
    content = re.sub(
        r'(\))\s*#\s*type:\s*ignore\[no-any-return\]\)',
        r'\1',
        content
    )
    
    if len(content) < original_len:
        path.write_text(content)
        return 1
    return 0

if __name__ == '__main__':
    total = 0
    for file in FILES_TO_FIX:
        if clean_file(file):
            print(f"CLEANED: {file}")
            total += 1
    print(f"Total cleaned: {total}")
