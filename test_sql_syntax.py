#!/usr/bin/env python3
import os
os.environ.setdefault("LOCAL_MODE", "true")
os.environ.setdefault("ENVIRONMENT", "development")

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db.context import DatabaseContext

# Test the INSERT statement
sql = """
INSERT INTO growth_metrics
(symbol, revenue_growth_1y, revenue_growth_3y, revenue_growth_5y, eps_growth_1y, eps_growth_3y, eps_growth_5y,
 net_income_growth_yoy, operating_income_growth_yoy, gross_margin_trend, operating_margin_trend, net_margin_trend,
 roe_trend, sustainable_growth_rate, quarterly_growth_momentum, fcf_growth_yoy, ocf_growth_yoy, asset_growth_yoy,
 consecutive_positive_quarters, earnings_growth_4q_avg, eps_growth_stability,
 data_unavailable, reason, data_source, updated_at,
 revenue_growth_1y_unavailable_reason, revenue_growth_3y_unavailable_reason, revenue_growth_5y_unavailable_reason,
 eps_growth_1y_unavailable_reason, eps_growth_3y_unavailable_reason, eps_growth_5y_unavailable_reason,
 net_income_growth_yoy_unavailable_reason, operating_income_growth_yoy_unavailable_reason, gross_margin_trend_unavailable_reason,
 operating_margin_trend_unavailable_reason, net_margin_trend_unavailable_reason, roe_trend_unavailable_reason,
 sustainable_growth_rate_unavailable_reason, quarterly_growth_momentum_unavailable_reason, fcf_growth_yoy_unavailable_reason,
 ocf_growth_yoy_unavailable_reason, asset_growth_yoy_unavailable_reason,
 consecutive_positive_quarters_unavailable_reason, earnings_growth_4q_avg_unavailable_reason, eps_growth_stability_unavailable_reason)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

params = (
    'TEST',  # symbol
    None, None, None, None, None, None,  # growth rates
    None, None, None, None, None,  # trends
    None, None, None, None, None, None,  # more trends
    4, 28.9, 65.7,  # quarterly metrics
    False, None, 'sec_audited', '2026-08-09',  # meta
    None, None, None, None, None, None, None, None, None,  # reasons
    None, None, None, None, None, None, None, None, None,  # more reasons
    None, None, None,  # quarterly reasons
)

print(f"SQL placeholders: {sql.count('%s')}")
print(f"Params count: {len(params)}")
print(f"Match: {sql.count('%s') == len(params)}")

# Try executing
try:
    with DatabaseContext("write") as cur:
        cur.execute(sql, params)
    print("Success!")
except Exception as e:
    print(f"Error: {e}")
