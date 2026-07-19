# Algo Trading System

Production-ready algorithmic trading system with Alpaca paper trading, event-driven orchestration, and real-time dashboard.

## Quick Start

### Local Development (Recommended)

```bash
# Terminal 1: Start API server
python3 lambda/api/dev_server.py

# Terminal 2: Start dashboard (in another terminal)
python3 -m dashboard --local -w 30
```

**Dashboard will open in TUI mode with live market data and positions.**

See [QUICKSTART_LOCAL.md](QUICKSTART_LOCAL.md) for detailed instructions.

### One-Command Startup (Linux/macOS)

```bash
./start_system_local.sh
```

This starts both dev server and dashboard automatically.

---

## System Status

✅ **Production Ready**
- Database: PostgreSQL with 8.6M+ price records
- Orchestrator: Running 2x daily (9:30 AM + 5:30 PM ET)
- Data loaders: 21 loaders operational
- API: Lambda-based with provisioned concurrency (5 units)
- Trading: Alpaca paper trading fully operational
- Dashboard: Real-time TUI with 26 data panels

---

## Features

### Core Trading
- **Entry signals** based on Minervini/Weinstein price/volume patterns
- **Position sizing** based on market regime and volatility
- **Risk management** with circuit breakers and stop-loss enforcement
- **Paper trading** via Alpaca (0% slippage for testing)

### Real-Time Monitoring
- 26-panel dashboard showing portfolio, positions, signals, and market data
- Live updates every 30 seconds
- Sector rotation analysis
- Economic calendar and sentiment data

### Data Pipeline
- 21 specialized loaders for prices, fundamentals, technical data, sentiment
- Automatic data freshness monitoring
- Stale data alerts via SNS
- Consolidated orchestrator with 9 execution phases

---

## Troubleshooting

### Dashboard Shows "Data Not Available"

**Cause:** Dashboard not using `--local` flag or dev server not running.

**Solution:**
1. Make sure dev server is running in another terminal:
   ```bash
   python3 lambda/api/dev_server.py
   ```

2. Always use `--local` flag when developing:
   ```bash
   python3 -m dashboard --local
   ```

### System Status Check

Verify all systems are operational:

```bash
python3 scripts/diagnose_system.py
```

### AWS Deployment Issues

See [steering/OPERATIONS.md](steering/OPERATIONS.md) for:
- Lambda configuration
- Cognito authentication setup
- AWS credential configuration
- CloudWatch monitoring

---

## Documentation

- [QUICKSTART_LOCAL.md](QUICKSTART_LOCAL.md) - Local development setup and debugging
- [DASHBOARD_TROUBLESHOOTING.md](DASHBOARD_TROUBLESHOOTING.md) - Dashboard issues and fixes
- [steering/GOVERNANCE.md](steering/GOVERNANCE.md) - System architecture and design decisions
- [steering/DATA_LOADERS.md](steering/DATA_LOADERS.md) - Data loading pipeline
- [steering/OPERATIONS.md](steering/OPERATIONS.md) - AWS deployment and operations
- [steering/AWS_LAMBDA_503_FIX.md](steering/AWS_LAMBDA_503_FIX.md) - Lambda troubleshooting

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│ Dashboard (TUI)                                  │
│ ├─ 26 real-time data panels                     │
│ └─ Auto-connects to localhost:3001 (--local)    │
└──────────────┬──────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────┐
│ API Server (Dev: localhost:3001, AWS: Lambda)   │
│ ├─ /api/algo/portfolio    - Current positions  │
│ ├─ /api/algo/positions    - Portfolio details  │
│ ├─ /api/algo/signals      - Trading signals    │
│ ├─ /api/algo/trades       - Execution history  │
│ └─ /api/algo/health       - System status      │
└──────────────┬──────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────┐
│ Orchestrator (Step Functions / ECS Fargate)     │
│ ├─ Phase 1: Data freshness check                │
│ ├─ Phase 2: Circuit breaker status              │
│ ├─ Phase 3: Position monitoring                 │
│ ├─ Phase 4: Account reconciliation              │
│ ├─ Phase 5: Exposure policy enforcement         │
│ ├─ Phase 6: Exit signal execution               │
│ ├─ Phase 7: Signal generation                   │
│ ├─ Phase 8: Entry order execution               │
│ └─ Phase 9: Post-execution reconciliation       │
└──────────────┬──────────────────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
    ▼          ▼          ▼
  PostgreSQL  Alpaca   S3/SNS
  (pricing)  (orders)  (alerts)
```

---

## Trading Modes

### Paper Trading (Default)
- 100% simulated with real Alpaca APIs
- Uses paper trading account (0 slippage)
- Perfect for testing and development
- Alpaca credentials: Set via AWS Secrets Manager

### Live Trading (Production Only)
- Requires explicit enable via IaC
- Uses live Alpaca account with real money
- Requires additional compliance verification
- See `steering/OPERATIONS.md` for setup

---

## Development

### Required Setup

```bash
# Python 3.9+
python3 --version

# PostgreSQL running locally
psql -U stocks stocks -c "SELECT 1"

# Install dependencies
pip install -r requirements.txt

# Type checking
make type-check

# Run tests
make test
```

### Code Quality

```bash
# Format code
make format

# Check types (enforced in CI/CD)
make type-check

# Run tests
make test
```

---

## Deployment

### Automatic (Recommended)

Push to `main` branch - GitHub Actions automatically:
1. Runs tests and type checking
2. Builds Lambda functions and Docker images
3. Deploys via Terraform to AWS
4. Updates Step Functions orchestrator
5. Runs smoke tests

### Manual Deployment

```bash
cd terraform
terraform init
terraform plan -var-file=dev.tfvars
terraform apply -var-file=dev.tfvars
```

See [steering/OPERATIONS.md](steering/OPERATIONS.md) for AWS credential setup and CI/CD configuration.

---

## Support

### Common Issues

1. **Dashboard shows "data not available"**
   - Solution: Use `--local` flag + ensure dev_server is running
   - See: [QUICKSTART_LOCAL.md](QUICKSTART_LOCAL.md)

2. **Lambda 503 errors**
   - Solution: Provisioned concurrency is enabled (5 units)
   - See: [steering/AWS_LAMBDA_503_FIX.md](steering/AWS_LAMBDA_503_FIX.md)

3. **Stale data warnings**
   - Solution: Orchestrator runs 2x daily; can manually trigger via `scripts/trigger_orchestrator.py`
   - See: [steering/COMMON_OPERATIONS.md](steering/COMMON_OPERATIONS.md)

### Running Diagnostics

```bash
python3 scripts/diagnose_system.py
python3 scripts/audit_system.py
```

---

## System Status (Current)

- **Last Update:** 2026-07-12
- **Data Freshness:** Prices current through yesterday's market close
- **Orchestrator:** Running successfully (all recent runs successful)
- **Data Loaders:** All 21 operational and completing successfully
- **Dashboard:** 26/26 fetchers loading in local mode
- **Live Trading:** Ready (paper mode enabled by default)

---

## License

Proprietary - Internal Use Only

---

## Questions?

See:
- Local troubleshooting: [QUICKSTART_LOCAL.md](QUICKSTART_LOCAL.md)
- Dashboard issues: [DASHBOARD_TROUBLESHOOTING.md](DASHBOARD_TROUBLESHOOTING.md)
- Architecture: [steering/GOVERNANCE.md](steering/GOVERNANCE.md)
- Operations: [steering/OPERATIONS.md](steering/OPERATIONS.md)
