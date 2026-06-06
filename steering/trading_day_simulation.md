# Trading Day Simulation - End-to-End Testing

Simulate a complete trading day to verify the algo system works end-to-end with AWS data and Alpaca trading integration.

## Overview

The simulation script (`scripts/trading_day_simulation.py`) verifies:

1. **Credentials** - AWS, PostgreSQL, Alpaca API access
2. **Database** - Schema exists, tables accessible, config loaded
3. **AWS Data** - Price history, technicals, signals available
4. **Orchestrator** - All 7 trading phases execute
5. **Alpaca Trading** - Paper trading account connected, positions tracked
6. **P&L** - Trade execution, exits, and profit/loss calculated
7. **Position Status** - Open positions, market value, unrealized P&L

## Quick Start

### Dry-Run Mode (No Trades)
Test the entire system without executing any trades:
```bash
python scripts/trading_day_simulation.py --date 2026-05-15 --mode dry-run --verbose
```

### Paper Trading Mode (Simulated Real Trading)
Run full trading simulation in Alpaca paper account:
```bash
python scripts/trading_day_simulation.py --date 2026-05-14 --mode paper
```

### Skip Alpaca Verification
Faster runs that skip Alpaca account check:
```bash
python scripts/trading_day_simulation.py --date 2026-05-15 --mode paper --skip-alpaca-verify
```

## System Components Verified

### Database Schema
- `trades` - Execution history (symbol, side, quantity, price, date)
- `positions` - Open/closed positions (entry price, current P&L, status)
- `algo_config` - 134+ configuration parameters

### Orchestrator Phases
1. **Phase 1** - Data freshness checks (price, signals, technicals age)
2. **Phase 2** - Circuit breaker validation (drawdown, daily loss, win rate)
3. **Phase 3** - Position reconciliation (Alpaca ↔ database sync)
4. **Phase 4** - Exposure policy enforcement (sector, position size limits)
5. **Phase 5** - Exit execution (profit-takes, stop-losses)
6. **Phase 6** - Entry execution (new trades, position sizing)
7. **Phase 7** - Pyramid adds (additional entries on winning trades)

### Alpaca Integration
- Paper trading account verification
- Account status ($portfolio value, buying power)
- Position tracking (open positions list)
- Trade execution (buy/sell orders queued)

### AWS Integration
- S3 price history (daily OHLCV data)
- DynamoDB cache (market health, technicals, signals)
- ECS task monitoring (loader health checks)
- CloudWatch metrics (execution quality, performance)

## Output Interpretation

### Pre-Flight Checks
```
[SETUP] Execution mode: dry-run, Paper trading: true
[CREDENTIALS] All required credentials validated
[DATABASE] Connection verified
[STATE] Config parameters loaded: 134 entries
[STATE] No existing positions. Clean slate for simulation.
```

### Orchestrator Execution
```
[ORCHESTRATOR] Phase 0: Data freshness checks
[ORCHESTRATOR] Phase 1a: Circuit breaker checks
... (all 7 phases)
[ORCHESTRATOR] Completed: success=True, run_id=RUN-2026-05-15-123505
```

### Trade Results
```
Entry Execution:
  New trades:        5
  Shares entered:    150

Exit Execution:
  Total exits:       2

P&L:
  Daily P&L:         $234.50
  Realized P&L:      $234.50

Position Status:
  Open positions:    8
  Market value:      $45,230.00
  Unrealized P&L:    $2,100.00
```

### Alpaca Integration
```
[ALPACA] Account status: $74180.93 (buying power: $268049.62)
[ALPACA] Open positions in Alpaca: 9
```

## Failure Diagnosis

### Database Connection Failed
```
Error: [DATABASE] Failed: <error>
```
- Check `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` in PowerShell profile
- Verify PostgreSQL is running: `psql -h localhost -U postgres -d algo`
- Check RDS Proxy status if using AWS RDS

### Alpaca Credentials Invalid
```
Error: [CREDENTIALS] Failed: <error>
```
- Check `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` env vars
- Verify Alpaca API key is active (not revoked/expired)
- Confirm paper trading is enabled in Alpaca dashboard

### Orchestrator Phase Failed
```
[ORCHESTRATOR] Completed: success=False, run_id=RUN-2026-05-15-xxxxx
ERROR in phase X (<phase_name>): <error>
```
- Check CloudWatch logs for detailed error
- Verify data freshness (prices/signals recent enough)
- Check market calendar (weekend/holiday skips trading)

## Advanced Usage

### Verbose Logging
Enable debug output for detailed execution trace:
```bash
python scripts/trading_day_simulation.py --date 2026-05-15 --mode paper --verbose
```

### Historical Trading Day
Test against archived data from specific date:
```bash
python scripts/trading_day_simulation.py --date 2025-12-15 --mode paper
```

### Market Closed Day
Verify system correctly skips trading on weekends/holidays:
```bash
python scripts/trading_day_simulation.py --date 2026-05-16 --mode paper  # Saturday
```

## Performance Benchmarks

Typical execution times:
- Pre-flight checks: 0.5-1s
- Orchestrator phases: 2-5s (depends on dataset size)
- Trade result queries: 0.1-0.2s
- Alpaca verification: 2-3s
- **Total**: 5-10s for complete simulation

## Integration with CI/CD

To run as GitHub Actions workflow:

```yaml
- name: Run trading day simulation
  run: |
    python scripts/trading_day_simulation.py \
      --date $(date -d "yesterday" +%Y-%m-%d) \
      --mode paper \
      --skip-alpaca-verify
```

## Next Steps

After successful simulation:

1. **Deploy to AWS** - Push to `main` branch to trigger CI/CD
2. **Monitor Production** - Check CloudWatch dashboard for real trading execution
3. **Verify P&L** - Confirm trades executed match Alpaca account
4. **Rotate Credentials** - Refresh API keys quarterly

## Troubleshooting

### Script Exits Early
Add `--verbose` flag to see detailed logs of where it fails

### API Timeouts
- Check network connectivity to AWS, RDS, Alpaca
- Increase timeout: Edit `api_request_timeout_seconds` in algo_config table
- Try during market hours (data loads faster when markets active)

### Memory Issues
- Reduce dataset size by querying specific time ranges
- Use `--skip-alpaca-verify` to avoid unnecessary API calls
- Check system memory: `Get-Process | Measure-Object WorkingSet -Sum`
