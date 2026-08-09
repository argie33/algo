#!/usr/bin/env python3
"""Test quarterly metrics computation directly."""

import os
os.environ.setdefault("LOCAL_MODE", "true")
os.environ.setdefault("ENVIRONMENT", "development")

from utils.dotenv_loader import load_env_local
load_env_local()

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader

# Create loader instance and test _compute_quarterly_metrics
loader = ValueQualityGrowthMetricsLoader()

# Test on AAPL
metrics = loader._compute_quarterly_metrics('AAPL')

print("Computed quarterly metrics for AAPL:")
for key, value in metrics.items():
    print(f"  {key}: {value}")

if not metrics:
    print("  (NO METRICS COMPUTED)")
