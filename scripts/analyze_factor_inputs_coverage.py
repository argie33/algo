#!/usr/bin/env python3
"""Factor score input coverage analysis.

Shows which factor inputs are populated vs NULL/unavailable across stock universe.
Identifies what loaders/data sources need work for scores page display.

Usage:
  python3 scripts/analyze_factor_inputs_coverage.py                  # All factors
  python3 scripts/analyze_factor_inputs_coverage.py --factor quality  # Single factor
"""

import sys
from utils.db.context import DatabaseContext

def main():
    factor_filter = None
    if len(sys.argv) > 2 and sys.argv[1] == "--factor":
        factor_filter = sys.argv[2]

    # Map field names to table column references
    quality_fields = {
        'ROE': ('qm.roe', 'quality_metrics'),
        'ROA': ('qm.roa', 'quality_metrics'),
        'ROIC': ('qm.roic_pct', 'quality_metrics'),
        'Gross Margin': ('qm.gross_margin', 'quality_metrics'),
        'Operating Margin': ('qm.operating_margin', 'quality_metrics'),
        'EBITDA Margin': ('qm.ebitda_margin', 'quality_metrics'),
        'Debt/Equity': ('qm.debt_to_equity', 'quality_metrics'),
        'Current Ratio': ('qm.current_ratio', 'quality_metrics'),
        'FCF/NI': ('qm.fcf_to_net_income', 'quality_metrics'),
    }

    growth_fields = {
        'Revenue Growth 1Y': ('gm.revenue_growth_1y', 'growth_metrics'),
        'EPS Growth 1Y': ('gm.eps_growth_1y', 'growth_metrics'),
        'Revenue CAGR 3Y': ('gm.revenue_growth_3y', 'growth_metrics'),
        'Gross Margin Trend': ('gm.gross_margin_trend', 'growth_metrics'),
        'Operating Margin Trend': ('gm.operating_margin_trend', 'growth_metrics'),
        'ROE Trend': ('gm.roe_trend', 'growth_metrics'),
        'Sustainable Growth': ('gm.sustainable_growth_rate', 'growth_metrics'),
        'FCF Growth YoY': ('gm.fcf_growth_yoy', 'growth_metrics'),
    }

    value_fields = {
        'P/E': ('vm.pe_ratio', 'value_metrics'),
        'Forward P/E': ('vm.forward_pe', 'value_metrics'),
        'P/B': ('vm.pb_ratio', 'value_metrics'),
        'P/S': ('vm.ps_ratio', 'value_metrics'),
        'PEG': ('vm.peg_ratio', 'value_metrics'),
        'EV/EBITDA': ('vm.ev_ebitda', 'value_metrics'),
        'FCF Yield': ('vm.fcf_yield', 'value_metrics'),
    }

    momentum_fields = {
        'Momentum 3M': ('mm.momentum_3m', 'momentum_metrics'),
        'Momentum 6M': ('mm.momentum_6m', 'momentum_metrics'),
        'RSI': ('tl.rsi_14', 'technical_data_daily'),
        'MACD': ('tl.macd', 'technical_data_daily'),
    }

    positioning_fields = {
        'Institutional Own %': ('pm.institutional_ownership_pct', 'positioning_metrics'),
        'Insider Own %': ('pm.insider_ownership_pct', 'positioning_metrics'),
        'Short Interest %': ('pm.short_interest_pct', 'positioning_metrics'),
        'Days to Cover': ('pm.short_ratio', 'positioning_metrics'),
    }

    stability_fields = {
        'Volatility 12M': ('sm.volatility_252d', 'stability_metrics'),
        'Volatility 60D': ('sm.volatility_60d', 'stability_metrics'),
        'Beta': ('sm.beta', 'stability_metrics'),
        'Debt/Assets': ('sm.debt_to_assets', 'stability_metrics'),
    }

    factors = {
        'quality': quality_fields,
        'growth': growth_fields,
        'value': value_fields,
        'momentum': momentum_fields,
        'positioning': positioning_fields,
        'stability': stability_fields,
    }

    if factor_filter and factor_filter not in factors:
        print(f"Unknown factor: {factor_filter}")
        print(f"Available: {', '.join(factors.keys())}")
        return 1

    to_analyze = {factor_filter: factors[factor_filter]} if factor_filter else factors

    with DatabaseContext("read") as cur:
        # Get total stock count
        cur.execute("SELECT COUNT(*) FROM stock_scores WHERE composite_score > 0")
        total = cur.fetchone()[0]

        print(f"\n📊 Factor Score Input Coverage Analysis")
        print(f"   Total ranked stocks: {total}\n")

        for factor_name, fields in to_analyze.items():
            print(f"{'=' * 70}")
            print(f"{factor_name.upper():20} INPUT COVERAGE")
            print(f"{'=' * 70}\n")

            results = []
            for label, (col, table) in fields.items():
                if 'tl.' in col:
                    col_name = col.split('.')[1]
                    query = f"SELECT COUNT(*) FILTER (WHERE {col_name} IS NOT NULL) FROM technical_data_daily WHERE symbol IN (SELECT DISTINCT symbol FROM stock_scores WHERE composite_score > 0)"
                elif 'mm.' in col:
                    col_name = col.split('.')[1]
                    query = f"SELECT COUNT(*) FILTER (WHERE {col_name} IS NOT NULL) FROM momentum_metrics WHERE symbol IN (SELECT DISTINCT symbol FROM stock_scores WHERE composite_score > 0)"
                elif 'qm.' in col:
                    col_name = col.split('.')[1]
                    query = f"SELECT COUNT(*) FILTER (WHERE {col_name} IS NOT NULL) FROM quality_metrics WHERE symbol IN (SELECT DISTINCT symbol FROM stock_scores WHERE composite_score > 0)"
                elif 'gm.' in col:
                    col_name = col.split('.')[1]
                    query = f"SELECT COUNT(*) FILTER (WHERE {col_name} IS NOT NULL) FROM growth_metrics WHERE symbol IN (SELECT DISTINCT symbol FROM stock_scores WHERE composite_score > 0)"
                elif 'vm.' in col:
                    col_name = col.split('.')[1]
                    query = f"SELECT COUNT(*) FILTER (WHERE {col_name} IS NOT NULL) FROM value_metrics WHERE symbol IN (SELECT DISTINCT symbol FROM stock_scores WHERE composite_score > 0)"
                elif 'pm.' in col:
                    col_name = col.split('.')[1]
                    query = f"SELECT COUNT(*) FILTER (WHERE {col_name} IS NOT NULL) FROM positioning_metrics WHERE symbol IN (SELECT DISTINCT symbol FROM stock_scores WHERE composite_score > 0)"
                elif 'sm.' in col:
                    col_name = col.split('.')[1]
                    query = f"SELECT COUNT(*) FILTER (WHERE {col_name} IS NOT NULL) FROM stability_metrics WHERE symbol IN (SELECT DISTINCT symbol FROM stock_scores WHERE composite_score > 0)"
                else:
                    print(f"  ❌ {label:30} [unmapped column]")
                    continue

                try:
                    cur.execute(query)
                    count = cur.fetchone()[0] or 0
                    pct = int((count / max(total, 1)) * 100)

                    if pct >= 80:
                        status = "✅ AVAILABLE"
                    elif pct >= 50:
                        status = "⚠️  PARTIAL"
                    else:
                        status = "❌ SPARSE"

                    results.append((label, count, pct, status))
                except Exception as e:
                    print(f"  ⚠️  {label:30} [ERROR: {str(e)[:30]}]")

            # Sort by coverage
            results.sort(key=lambda x: x[2], reverse=True)
            for label, count, pct, status in results:
                print(f"  {status:15} {label:30} {pct:3}% ({count:4}/{total})")
            print()

    return 0

if __name__ == "__main__":
    sys.exit(main())
