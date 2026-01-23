#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/stocks/algo')
from db_helper import get_db_connection

def audit_data_coverage():
    conn = get_db_connection()
    cur = conn.cursor()
    
    print("\n" + "="*70)
    print("COMPREHENSIVE DATA COVERAGE AUDIT - ALL METRICS")
    print("="*70)
    
    cur.execute("SELECT COUNT(DISTINCT ticker) FROM key_metrics")
    total_stocks = cur.fetchone()[0]
    print(f"\nTotal unique stocks in database: {total_stocks}\n")
    
    # Define all metrics to audit
    metrics_list = [
        ('QUALITY METRICS', [
            ('return_on_equity_pct', 'ROE'),
            ('return_on_assets_pct', 'ROA'),
            ('gross_margin_pct', 'Gross Margin'),
            ('operating_margin_pct', 'Operating Margin'),
            ('ebitda_margin_pct', 'EBITDA Margin'),
            ('profit_margin_pct', 'Net Profit Margin'),
            ('debt_to_equity', 'Debt/Equity'),
            ('current_ratio', 'Current Ratio'),
            ('quick_ratio', 'Quick Ratio'),
            ('free_cashflow', 'Free Cash Flow'),
            ('payout_ratio', 'Payout Ratio'),
            ('total_debt', 'Total Debt'),
            ('total_cash', 'Total Cash'),
            ('operating_cashflow', 'Operating Cash Flow'),
            ('ebitda', 'EBITDA'),
            ('net_income', 'Net Income'),
        ]),
        ('VALUATION METRICS', [
            ('trailing_pe', 'Trailing P/E'),
            ('forward_pe', 'Forward P/E'),
            ('price_to_book', 'Price/Book'),
            ('price_to_sales_ttm', 'Price/Sales'),
            ('peg_ratio', 'PEG Ratio'),
            ('dividend_yield', 'Dividend Yield'),
            ('last_annual_dividend_yield', 'Last Annual Div Yield'),
            ('five_year_avg_dividend_yield', '5-Year Avg Div Yield'),
            ('ev_to_ebitda', 'EV/EBITDA'),
            ('ev_to_revenue', 'EV/Revenue'),
        ]),
        ('GROWTH METRICS', [
            ('revenue_growth_pct', 'Revenue Growth'),
            ('earnings_growth_pct', 'Earnings Growth'),
            ('earnings_q_growth_pct', 'Quarterly Earnings Growth'),
        ]),
        ('PRICE & SHARES', [
            ('price_eps_current_year', 'Price/EPS Current Year'),
            ('eps_current_year', 'EPS Current Year'),
            ('eps_forward', 'EPS Forward'),
            ('eps_trailing', 'EPS Trailing'),
            ('implied_shares_outstanding', 'Implied Shares Out'),
            ('float_shares', 'Float Shares'),
            ('book_value', 'Book Value'),
            ('cash_per_share', 'Cash Per Share'),
        ]),
        ('OWNERSHIP METRICS', [
            ('held_percent_institutions', 'Institutional Ownership'),
            ('held_percent_insiders', 'Insider Ownership'),
            ('short_percent_of_float', 'Short % of Float'),
            ('shares_short', 'Shares Short'),
            ('short_ratio', 'Short Ratio'),
        ]),
    ]
    
    all_gaps = []
    
    for section_name, metrics in metrics_list:
        print("=" * 70)
        print(section_name)
        print("=" * 70)
        
        for col, name in metrics:
            cur.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN {col} IS NOT NULL AND {col} != 0 THEN 1 END) as with_data
                FROM key_metrics
            """)
            total, with_data = cur.fetchone()
            pct = (with_data / total * 100) if total > 0 else 0
            gap = total - with_data
            
            status = "✅" if pct >= 90 else "🟡" if pct >= 70 else "🔴"
            print(f"  {status} {name:30s}: {with_data:5d}/{total:5d} ({pct:5.1f}%) - {gap:5d} missing")
            
            if pct < 80:
                all_gaps.append((name, pct, gap))
    
    # Summary of actionable gaps
    print("\n" + "=" * 70)
    print("🎯 ACTIONABLE GAPS (< 80% coverage) - CAN BE FIXED")
    print("=" * 70)
    
    if all_gaps:
        all_gaps.sort(key=lambda x: x[1])  # Sort by coverage %
        for name, pct, missing in all_gaps:
            print(f"  {name:30s}: {pct:5.1f}% - {missing:5d} missing")
        
        print(f"\n  Total fixable data points: {sum(x[2] for x in all_gaps):,}")
    else:
        print("  ✅ All metrics at 80%+ coverage!")
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    audit_data_coverage()
