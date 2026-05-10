# Experimental Loaders — Future Phases

This directory contains data loaders that are **not part of the current production pipeline** but may be integrated in future phases.

These loaders are:
- **Not scheduled** in Terraform
- **Not tested** against live market conditions
- **Not validated** by the trading algo
- **Provided as reference** for future development

## Phase 2 Features (Next Priority)

- **Market Health Metrics** (`load_market_health_daily.py`) — Market breadth, distribution days, market regime
- **Performance Analytics** (`loadbenchmark.py`) — Benchmark comparison and performance analytics
- **Signal Enhancement** (`loadmeanreversionsignals.py`, `loadrangesignals.py`, `loadswingscores.py`) — Alternative signal approaches
- **Content Integration** (`loadnews.py`) — News-based sentiment (complements official social sentiment)
- **Industry Analysis** (`loadindustryranking.py`) — Industry-level momentum ranking

## Phase 3+ Features (Later)

- **Options Trading** (`loadoptionschains.py`, `loadcoveredcallopportunities.py`) — Derivatives, covered calls, spreads
- **Commodity Integration** (`loadcommodities.py`) — Macro hedge strategies
- **Fundamental Events** (`loadsecfilings.py`) — SEC filing-based trading signals
- **Company Data** (`loaddailycompanydata.py`) — Daily company metrics
- **Earnings Analysis** (`loadforwardeps.py`) — Forward earnings integration
- **Account Integration** (`loadalpacaportfolio.py`) — Real-time Alpaca dashboard sync

## To Integrate a Loader

1. Move loader from `experimental/loaders/` back to root
2. Add to `terraform/modules/loaders/main.tf`:
   - Add to `loader_file_map`
   - Add schedule to `scheduled_loaders`
   - Add CPU/memory to `all_loaders`
   - Add to `critical_loaders` if needed
3. Test against live data
4. Commit with phase justification

## Questions?

See `LOADER_CLEANUP_DECISIONS.md` for detailed rationale on each loader.
