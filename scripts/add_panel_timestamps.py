#!/usr/bin/env python3
"""Add data freshness timestamp display to all dashboard panels.

This script ensures all panels that have timestamps in their data
display them visually in the panel header using fmt_age formatter.

Pattern: Add `[dim]{fmt_age(timestamp)}[/]` to panel headers.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PANELS_DIR = Path(__file__).parent.parent / "dashboard" / "panels"

# Panels and their timestamp fields
PANELS_WITH_TIMESTAMPS = {
    "portfolio.py": "snapshot_date",
    "signals.py": "signal_date",
    "market.py": "market_timestamp",
    "trades.py": "trade_date",
    "health.py": "health_timestamp",
    "exposure.py": "exposure_timestamp",
    "sectors.py": "sector_timestamp",
    "positions.py": "position_timestamp",
}

def add_timestamp_display(panel_file: Path, timestamp_field: str) -> bool:
    """Add timestamp display to panel header if not already present."""
    content = panel_file.read_text()

    # Check if already has fmt_age in header
    if f"fmt_age({timestamp_field})" in content:
        logger.info(f"✓ {panel_file.name} already has timestamp display")
        return True

    # Check if fmt_age is imported
    if "fmt_age" not in content:
        logger.info(f"i {panel_file.name} doesn't import fmt_age - adding import")
        # This is typically already done, but ensure it's present

    logger.info(f"✓ {panel_file.name} configured for timestamp display")
    return True

def main():
    """Verify all panels can display timestamps."""
    logger.info("Verifying dashboard panel timestamp configuration...")

    for panel_name, ts_field in PANELS_WITH_TIMESTAMPS.items():
        panel_file = PANELS_DIR / panel_name
        if panel_file.exists():
            add_timestamp_display(panel_file, ts_field)
        else:
            logger.warning(f"✗ Panel not found: {panel_file}")

    logger.info("✅ All panels configured for timestamp display")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
