#!/usr/bin/env python3

"""Filter Tier 1 & 2 implementations — data quality and market health checks."""

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class FilterTiers12Mixin:
    """Tier 1 & 2 filtering logic."""

    def _tier1_data_quality(self, symbol) -> Dict[str, Any]:
        try:
            self.cur.execute(
                """
                SELECT composite_completeness_pct, is_tradeable
                FROM data_completeness_scores WHERE symbol = %s
                """,
                (symbol,),
            )
            row = self.cur.fetchone()
            completeness = 0
            if row and row[0] is not None:
                completeness = float(row[0])
                min_required = float(self.config.get('min_completeness_score', 70))
                if completeness < min_required:
                    return {
                        'pass': False,
                        'reason': f'Completeness {completeness:.0f}% < {min_required:.0f}%',
                        'completeness_pct': completeness,
                    }

            self.cur.execute(
                "SELECT close, date FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1",
                (symbol,),
            )
            price_row = self.cur.fetchone()
            if not price_row or price_row[0] is None:
                return {'pass': False, 'reason': 'No price data', 'completeness_pct': completeness}

            price = float(price_row[0])
            min_price = float(self.config.get('min_stock_price', 5.0))
            if price < min_price:
                return {
                    'pass': False,
                    'reason': f'Price ${price:.2f} < ${min_price:.2f}',
                    'completeness_pct': completeness,
                }

            return {
                'pass': True,
                'reason': f'Completeness {completeness:.0f}%, Price ${price:.2f}',
                'completeness_pct': completeness,
            }
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}', 'completeness_pct': 0}

    def _tier2_market_health(self, signal_date) -> Dict[str, Any]:
        """Market health for the signal's date, with 5-day fallback."""
        try:
            if self._market_health_date == signal_date:
                row = self._market_health_cache
            else:
                self.cur.execute(
                    """
                    SELECT date, market_stage, distribution_days_4w, vix_level, market_trend
                    FROM market_health_daily
                    WHERE date <= %s AND date >= %s::date - INTERVAL '5 days'
                    ORDER BY date DESC LIMIT 1
                    """,
                    (signal_date, signal_date),
                )
                row = self.cur.fetchone()
                self._market_health_cache = row
                self._market_health_date = signal_date

            if not row:
                return {'pass': False, 'reason': 'No market health data near signal date'}

            _d, stage, dist_days, vix, trend = row
            stage = stage or 0
            dist_days = dist_days or 0
            vix = float(vix) if vix is not None else None

            max_vix = float(self.config.get('vix_max_threshold', 35.0))
            if vix is not None and vix > max_vix:
                return {'pass': False, 'reason': f'VIX {vix:.1f} > {max_vix:.1f}'}
            elif vix is None:
                # VIX missing from market_health_daily — circuit breaker CB5 handles this
                # with a proper fallback (SPY volatility proxy). Don't block here on None.
                logger.warning(f'VIX unavailable for {signal_date} — skipping VIX check (CB5 covers it)')

            max_dd = int(self.config.get('max_distribution_days', 4))
            if dist_days > max_dd:
                return {'pass': False, 'reason': f'Distribution days {dist_days} > {max_dd}'}

            require_stage_2 = bool(self.config.get('require_stage_2_market', True))
            if require_stage_2 and stage != 2:
                return {'pass': False, 'reason': f'Market Stage {stage} != 2 (trend={trend})'}

            vix_str = f'VIX {vix:.1f}' if vix is not None else 'VIX N/A'
            return {
                'pass': True,
                'reason': f'Stage {stage}, DD {dist_days}, {vix_str}, {trend}',
            }
        except Exception as e:
            return {'pass': False, 'reason': f'Error: {e}'}
