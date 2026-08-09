#!/usr/bin/env python3
"""Debug the field copying logic."""

import os
os.environ.setdefault("LOCAL_MODE", "true")
os.environ.setdefault("ENVIRONMENT", "development")

from utils.dotenv_loader import load_env_local
load_env_local()

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader, _SHARED_TREND_FIELDS

print(f"_SHARED_TREND_FIELDS = {_SHARED_TREND_FIELDS}")
print(f"  consecutive_positive_quarters in list: {'consecutive_positive_quarters' in _SHARED_TREND_FIELDS}")
print(f"  earnings_growth_4q_avg in list: {'earnings_growth_4q_avg' in _SHARED_TREND_FIELDS}")
print(f"  eps_growth_stability in list: {'eps_growth_stability' in _SHARED_TREND_FIELDS}")

# Now test fetch_incremental
loader = ValueQualityGrowthMetricsLoader()
results = loader.fetch_incremental('AAPL', None)

if results:
    value_dict, quality_dict, growth_dict = results[0]
    print("\nAAPL Results from fetch_incremental:")
    print(f"  quality_dict consecutive_positive_quarters: {quality_dict.get('consecutive_positive_quarters')}")
    print(f"  growth_dict consecutive_positive_quarters: {growth_dict.get('consecutive_positive_quarters')}")
