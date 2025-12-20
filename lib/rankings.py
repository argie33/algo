"""
Ranking utilities - shared ranking and RS rating calculations
"""

import logging
from typing import List, Dict, Optional


def calculate_rs_rating(item_perf: float, all_performances: List[float]) -> Optional[int]:
    """
    Calculate IBD-style RS Rating (1-99)
    Compares item performance to all other items

    Args:
        item_perf: Performance of the item being ranked
        all_performances: List of all performances to compare against

    Returns:
        RS rating (1-99) or None if insufficient data
    """
    if not all_performances or len(all_performances) < 2:
        return None

    sorted_perf = sorted(all_performances)

    rank = 0
    for i, perf in enumerate(sorted_perf):
        if item_perf <= perf:
            rank = i
            break

    percentile = (rank / len(sorted_perf)) * 100
    rs_rating = min(99, max(1, int(percentile)))

    return rs_rating


def calculate_rankings(
    items: List[Dict], performance_key: str = "performance_20d"
) -> List[Dict]:
    """
    Calculate overall and sector rankings for a list of items.
    Only ranks items with REAL performance data (not fake 0 defaults).

    Args:
        items: List of item dicts with performance data
        performance_key: Key in dict to use for ranking (default: performance_20d)

    Returns:
        List of items with overall_rank and sector_rank added (None if no real data)
    """
    if not items:
        return items

    # Calculate overall ranking by performance - ONLY for items with REAL data
    items_with_data = [item for item in items if item.get(performance_key) is not None]
    sorted_overall = sorted(
        items_with_data, key=lambda x: x.get(performance_key), reverse=True
    )
    for rank, item in enumerate(sorted_overall, 1):
        item["overall_rank"] = rank

    # Items without real data get None rank
    for item in items:
        if item not in items_with_data:
            item["overall_rank"] = None

    # Calculate sector ranking - ONLY for items with REAL data
    by_sector = {}
    for item in items:
        sector = item.get("sector", "Unknown")
        if sector not in by_sector:
            by_sector[sector] = []
        by_sector[sector].append(item)

    for sector, sector_items in by_sector.items():
        items_with_sector_data = [item for item in sector_items if item.get(performance_key) is not None]
        sorted_sector = sorted(
            items_with_sector_data, key=lambda x: x.get(performance_key), reverse=True
        )
        for rank, item in enumerate(sorted_sector, 1):
            item["sector_rank"] = rank

        # Items without real data get None rank
        for item in sector_items:
            if item not in items_with_sector_data:
                item["sector_rank"] = None

    return items
