#!/usr/bin/env python3
"""Position-level risk scoring with safeguard integration.

Scores each position 0-10 based on:
- Safeguard violations
- Margin usage
- Concentration
- Volatility
- Time at risk

Provides early warning before issues become critical.
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import date
from typing import Dict, Any, Tuple
import logging
import math

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
}


class PositionRiskScorer:
    """Score individual positions for risk assessment."""

    def __init__(self, config=None):
        self.config = config or {}
        self.risk_threshold = float(self.config.get('risk_alert_threshold', 7.0))

    def score_position(self, symbol: str, entry_price: float, shares: int,
                       entry_date: date, current_price: float = None,
                       margin_usage_pct: float = None) -> Dict[str, Any]:
        """Score a single position for risk. Returns score 0-10 and breakdown."""

        scores = {}

        # 1. Earnings risk (0-3 points)
        earnings_risk = self._score_earnings_risk(symbol)
        scores['earnings_risk'] = earnings_risk

        # 2. Liquidity risk (0-2 points)
        liquidity_risk = self._score_liquidity_risk(symbol)
        scores['liquidity_risk'] = liquidity_risk

        # 3. Position sizing risk (0-2 points)
        sizing_risk = self._score_position_size_risk(shares, entry_price)
        scores['position_sizing_risk'] = sizing_risk

        # 4. Margin impact risk (0-2 points)
        margin_risk = self._score_margin_risk(entry_price, shares, margin_usage_pct)
        scores['margin_risk'] = margin_risk

        # 5. Time at risk (0-1 point)
        time_risk = self._score_time_risk(entry_date)
        scores['time_risk'] = time_risk

        # Calculate composite score (0-10)
        total_risk = sum(scores.values())
        composite_score = min(10.0, total_risk)

        # Determine risk level
        if composite_score < 3:
            risk_level = "LOW"
        elif composite_score < 6:
            risk_level = "MEDIUM"
        elif composite_score < 8:
            risk_level = "HIGH"
        else:
            risk_level = "CRITICAL"

        return {
            'symbol': symbol,
            'composite_risk_score': round(composite_score, 2),
            'risk_level': risk_level,
            'score_breakdown': {
                'earnings_risk': round(earnings_risk, 2),
                'liquidity_risk': round(liquidity_risk, 2),
                'position_sizing_risk': round(sizing_risk, 2),
                'margin_risk': round(margin_risk, 2),
                'time_risk': round(time_risk, 2),
            },
            'action_required': composite_score >= self.risk_threshold,
            'recommendation': self._get_recommendation(composite_score, scores),
        }

    def _score_earnings_risk(self, symbol: str) -> float:
        """Score earnings-related risk (0-3). Higher = riskier."""
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            cur.execute("""
                SELECT earnings_date FROM earnings_calendar
                WHERE symbol = %s
                AND earnings_date >= CURRENT_DATE
                AND earnings_date <= CURRENT_DATE + INTERVAL '30 days'
                LIMIT 1
            """, (symbol,))

            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row:
                return 0.0  # No earnings within 30 days

            earnings_date = row[0]
            days_until = (earnings_date - date.today()).days

            if days_until <= 3:
                return 3.0  # Critical: within 3 days
            elif days_until <= 7:
                return 2.0  # High: within 7 days
            elif days_until <= 14:
                return 1.0  # Medium: within 14 days
            else:
                return 0.5  # Low: tracked but not immediate

        except Exception as e:
            logger.warning(f"Failed to score earnings risk for {symbol}: {e}")
            return 0.0

    def _score_liquidity_risk(self, symbol: str) -> float:
        """Score liquidity risk (0-2). Higher = less liquid."""
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            cur.execute("""
                SELECT avg_volume FROM price_daily
                WHERE symbol = %s
                ORDER BY date DESC LIMIT 1
            """, (symbol,))

            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row or not row[0]:
                return 2.0  # No data = risky

            volume = float(row[0])

            if volume < 500000:
                return 2.0  # Low liquidity
            elif volume < 1000000:
                return 1.0  # Medium liquidity
            else:
                return 0.0  # High liquidity

        except Exception as e:
            logger.warning(f"Failed to score liquidity for {symbol}: {e}")
            return 0.0

    def _score_position_size_risk(self, shares: int, entry_price: float) -> float:
        """Score position sizing risk (0-2). Larger positions = higher risk."""
        position_value = shares * entry_price

        # Risk scale: $5K=0, $10K=1, $25K+=2
        if position_value < 5000:
            return 0.0
        elif position_value < 10000:
            return 0.5
        elif position_value < 25000:
            return 1.0
        else:
            return 2.0

    def _score_margin_risk(self, entry_price: float, shares: int,
                          margin_usage_pct: float = None) -> float:
        """Score margin-related risk (0-2)."""
        if margin_usage_pct is None:
            return 0.0

        # At 70%+ margin usage, positions become riskier
        if margin_usage_pct >= 80:
            return 2.0  # Critical
        elif margin_usage_pct >= 70:
            return 1.0  # Elevated
        else:
            return 0.0  # Healthy

    def _score_time_risk(self, entry_date: date) -> float:
        """Score time-at-risk (0-1). Older positions = higher risk."""
        days_held = (date.today() - entry_date).days

        # Risk increases with time held (drawdown probability)
        if days_held < 5:
            return 0.0
        elif days_held < 20:
            return 0.3
        elif days_held < 60:
            return 0.6
        else:
            return 1.0

    def _get_recommendation(self, score: float, components: Dict[str, float]) -> str:
        """Get action recommendation based on risk score."""
        if score < 3:
            return "Monitor normally"
        elif score < 6:
            return "Consider tightening stop loss or reducing size"
        elif score < 8:
            return "Review position urgently - consider partial exit or stop adjustment"
        else:
            return "CRITICAL: Evaluate immediate exit or emergency risk mitigation"


class PortfolioRiskAssessment:
    """Assess overall portfolio risk from safeguard perspective."""

    def __init__(self, config=None):
        self.scorer = PositionRiskScorer(config)
        self.config = config or {}

    def assess_portfolio(self, positions: list, margin_usage_pct: float = None) -> Dict[str, Any]:
        """Assess risk across all open positions."""
        position_risks = []
        high_risk_count = 0
        critical_count = 0

        for pos in positions:
            risk = self.scorer.score_position(
                symbol=pos['symbol'],
                entry_price=pos['entry_price'],
                shares=pos['shares'],
                entry_date=pos['entry_date'],
                current_price=pos.get('current_price'),
                margin_usage_pct=margin_usage_pct,
            )

            position_risks.append(risk)

            if risk['risk_level'] == 'CRITICAL':
                critical_count += 1
            elif risk['risk_level'] == 'HIGH':
                high_risk_count += 1

        # Portfolio-level risk
        avg_risk = sum(r['composite_risk_score'] for r in position_risks) / len(position_risks) if position_risks else 0

        portfolio_risk_level = (
            'CRITICAL' if critical_count > 0 else
            'HIGH' if high_risk_count >= 2 else
            'MEDIUM' if high_risk_count > 0 else
            'LOW'
        )

        return {
            'timestamp': date.today().isoformat(),
            'portfolio_risk_level': portfolio_risk_level,
            'average_position_risk': round(avg_risk, 2),
            'critical_positions': critical_count,
            'high_risk_positions': high_risk_count,
            'total_positions': len(positions),
            'positions': position_risks,
            'actions_required': critical_count + high_risk_count,
            'portfolio_recommendation': self._portfolio_recommendation(
                portfolio_risk_level, critical_count, high_risk_count
            ),
        }

    def _portfolio_recommendation(self, level: str, critical: int, high: int) -> str:
        """Get portfolio-level recommendation."""
        if critical > 0:
            return f"URGENT: {critical} critical position(s) - review immediately"
        elif high >= 2:
            return f"HIGH: {high} high-risk position(s) - review risk concentrations"
        elif high > 0:
            return f"MEDIUM: {high} high-risk position(s) - monitor closely"
        else:
            return "Portfolio risk is acceptable"


if __name__ == "__main__":
    scorer = PositionRiskScorer()

    # Test position scoring
    result = scorer.score_position(
        symbol='AAPL',
        entry_price=150.00,
        shares=100,
        entry_date=date.today(),
        current_price=152.00,
        margin_usage_pct=45.0
    )

    print("Position Risk Score:")
    print(f"  Score: {result['composite_risk_score']}/10")
    print(f"  Level: {result['risk_level']}")
    print(f"  Recommendation: {result['recommendation']}")
