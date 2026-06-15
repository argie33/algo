#!/usr/bin/env python3
"""Signal Data Source Hierarchy and Unified Query Builder (Issue #7)

Signal data sources with defined priority hierarchy:

PRIMARY: buy_sell_daily — stock trading signals
SUPPLEMENTARY: signal_quality_scores, company_profile — enrichment  
CONTEXT: algo_performance_daily, algo_portfolio_snapshots — strategy performance
"""

from typing import List, Any


class SignalQueryBuilder:
    """Build consistent signal queries with documented source hierarchy."""

    SOURCES = {
        'buy_sell_daily': {
            'type': 'primary',
            'table': 'buy_sell_daily',
            'description': 'Stock trading signals (buy/sell events)',
        },
        'buy_sell_daily_etf': {
            'type': 'primary',
            'table': 'buy_sell_daily_etf',
            'description': 'ETF trading signals (buy/sell events)',
        },
        'signal_quality_scores': {
            'type': 'supplementary',
            'table': 'signal_quality_scores',
            'description': 'Signal quality confidence scores',
        },
        'company_profile': {
            'type': 'supplementary',
            'table': 'company_profile',
            'description': 'Company metadata (sector, industry)',
        },
        'algo_performance_daily': {
            'type': 'context',
            'table': 'algo_performance_daily',
            'description': 'Portfolio performance metrics (Sharpe, win rate)',
        },
        'algo_portfolio_snapshots': {
            'type': 'context',
            'table': 'algo_portfolio_snapshots',
            'description': 'Portfolio equity curve and current state',
        },
    }

    def __init__(self, source: str = 'stocks', alias: str = 'bsd'):
        """Initialize with primary source: 'stocks' or 'etf'."""
        self.primary_source = 'buy_sell_daily' if source == 'stocks' else 'buy_sell_daily_etf'
        self.alias = alias
        self.supplementary_sources: List[str] = []
        self.context_sources: List[str] = []
        self.filters: List[tuple] = []

    def add_supplementary(self, sources: List[str]) -> 'SignalQueryBuilder':
        """Add supplementary data sources."""
        self.supplementary_sources.extend(sources)
        return self

    def add_context(self, sources: List[str]) -> 'SignalQueryBuilder':
        """Add context sources."""
        self.context_sources.extend(sources)
        return self

    def add_filter(self, clause: str, params: List[Any] = None) -> 'SignalQueryBuilder':
        """Add WHERE clause filter."""
        self.filters.append((clause, params or []))
        return self

    def source_hierarchy(self) -> str:
        """Return description of source hierarchy."""
        lines = [
            "SIGNAL DATA SOURCES (Issue #7: Unified Query)",
            f"PRIMARY: {self.primary_source}",
        ]
        if self.supplementary_sources:
            lines.append(f"SUPPLEMENTARY: {', '.join(self.supplementary_sources)}")
        if self.context_sources:
            lines.append(f"CONTEXT: {', '.join(self.context_sources)}")
        return "\n".join(lines)
