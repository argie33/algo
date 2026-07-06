#!/usr/bin/env python3
"""DEPRECATED: Swing Trader Scores Loader

This loader is NO LONGER USED. The trading system has migrated to composite_score only.

REASON FOR DEPRECATION:
- swing_trader_scores table is not queried by Phase 7 signal generation
- Composite score (from stock_scores) is used for all trading decisions
- swing_score/swing_grade fields were always NULL in production
- This loader is dead code consuming resources

MIGRATION STATUS: Complete - use stock_scores.composite_score for all signal ranking.

WHAT TO DO:
1. Remove from Step Functions trigger (terraform/modules/pipeline/main.tf)
2. Archive swing_trader_scores table if you need historical data
3. Query stock_scores.composite_score instead
"""

import logging

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    logger.warning(
        "[SWING_TRADER_SCORES_LOADER] This loader is deprecated. "
        "Do not run it. The trading system uses stock_scores.composite_score instead."
    )
