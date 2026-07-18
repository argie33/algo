#!/usr/bin/env python3
from algo.infrastructure.config.main import AlgoConfig

config = AlgoConfig()
print('Config loaded successfully!')
print(f'Total configs in memory: {len(config._config)}')

db_count = sum(1 for src in config._sources.values() if src == "database")
default_count = sum(1 for src in config._sources.values() if src == "default")

print(f'From database: {db_count}')
print(f'From defaults: {default_count}')

if db_count > 200:
    print('\n[OK] Config loading FIXED! Most configs now loaded from database.')
else:
    print('\n[FAIL] Config loading still failing - only few configs loaded from DB')

# Verify a few key configs
print(f'\nSample configs:')
print(f'  min_signal_quality_score: {config.get_field("min_signal_quality_score")}')
print(f'  execution_mode: {config.get_field("execution_mode")}')
print(f'  base_risk_pct: {config.get_field("base_risk_pct")}')
