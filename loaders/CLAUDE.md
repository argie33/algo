# Data Loaders

40 integrated loaders running in tier order (Tier 0→4) via `run-all-loaders.py`. Each must:

1. Extend `OptimalLoader` base class
2. Be integrated in tier assignment
3. Be deleted if one-time or diagnostic

## Tier System

- **Tier 0:** Symbols (no dependencies)
- **Tier 1:** Price data (depends on symbols)
- **Tier 2:** Reference data & financials (depends on tier 1)
- **Tier 3:** Signals (depends on prices)
- **Tier 4:** Aggregates & scores (depends on tier 3)

## Testing

- All loaders must pass `python3 run-all-loaders.py`
- No test files in loaders/ folder—tests go in tests/integration/

## Naming

Format: `load{source}{metric}.py` (e.g., `loadstockscores.py`, `loadecondata.py`)
