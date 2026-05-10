# Development Workflows

## Local Testing Setup (Quick Iteration)

### Prerequisites
1. **WSL2 installed** (Windows): `wsl --install` (requires restart)
2. **Docker Desktop** running with WSL2 backend
3. **.env.local** configured with:
   ```
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=stocks
   DB_USER=stocks
   DB_PASSWORD=stocks_local_password
   APCA_API_KEY_ID=your_alpaca_key
   APCA_API_SECRET_KEY=your_alpaca_secret
   ALPACA_PAPER_TRADING=true
   ```

### Start Local Stack

In WSL terminal:
```bash
cd /mnt/c/Users/arger/code/algo
docker-compose up -d
docker-compose ps  # Wait for postgres to show "healthy"
```

Verify database:
```bash
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_symbols;"
```

### Run Algo Locally

```bash
python3 algo_run_daily.py
```

**What it does:**
1. Data freshness check
2. Circuit breakers (drawdown, VIX, daily loss limits)
3. Position monitor (P&L, trailing stops, health scores)
4. Exit execution (trim/exit positions)
5. Signal generation (new buy signals through 5-tier filter)
6. Entry execution (trade via Alpaca paper account)
7. Reconciliation (sync portfolio, calculate P&L)

**Expected output:** Trade logs, position updates, audit trail written to database

### Verify Everything Works
- ✅ Database connects without errors
- ✅ Finds trading signals (or correctly identifies none)
- ✅ Alpaca paper trading calls succeed (no auth errors)
- ✅ No unhandled exceptions in output
- ✅ Database entries in algo_trades and algo_positions

---

## Making Code Changes

### Algo Logic Changes (Python)

1. **Make your change** to the relevant module
   - Entry/exit logic? → `algo_exit_engine.py` or `algo_trade_executor.py`
   - Signal generation? → `algo_filter_pipeline.py` or `algo_advanced_filters.py`
   - Risk checks? → `algo_circuit_breaker.py`
   - Data quality? → `algo_data_freshness.py`

2. **Test locally** (before pushing):
   ```bash
   python3 algo_run_daily.py
   ```

3. **Commit and push**:
   ```bash
   git add <file>
   git commit -m "Description of change"
   git push origin main
   ```

4. **Verify tests pass** in GitHub (check Actions tab)

5. **Deploy to AWS** (automatic on push to main):
   ```bash
   gh workflow run deploy-algo-orchestrator.yml
   ```

### API/Frontend Changes (Node.js/React)

1. **Make your change** to `webapp/lambda/routes/*.js` or `webapp/frontend/src/pages/*.jsx`

2. **Test locally**:
   ```bash
   cd webapp
   npm install
   npm run dev  # Frontend dev server (port 5173)
   node lambda/index.js  # Or test API endpoint
   ```

3. **Commit and push**

4. **Deploy to AWS**:
   ```bash
   gh workflow run deploy-webapp.yml
   ```

### Data Loader Changes

**IMPORTANT:** Only fix existing loaders, never create new ones (see memory/loader_discipline.md)

If a loader is broken:
1. Fix the loader module
2. Test locally with Docker Compose
3. Commit and push
4. Data loader ECS tasks auto-update on next scheduled run

**Do NOT create:** `populate-*.py`, `patch-*.py`, or workaround scripts

### Infrastructure Changes (CloudFormation)

1. **Edit the appropriate template:**
   - VPC/networking? → `template-core.yml`
   - Database/ECS? → `template-app-stocks.yml`
   - Loaders? → `template-app-ecs-tasks.yml`
   - API? → `template-webapp-lambda.yml`
   - Algo? → `template-algo-orchestrator.yml`

2. **Validate syntax**:
   ```bash
   aws cloudformation validate-template --template-body file://template-X.yml
   ```

3. **Commit and push**

4. **Workflows auto-trigger** when templates change, or manually:
   ```bash
   gh workflow run deploy-core.yml  # If you changed template-core.yml
   ```

### Workflow Changes

1. **Edit** `.github/workflows/deploy-*.yml`

2. **Test locally** (dry-run check):
   ```bash
   gh workflow run deploy-core.yml --dry-run
   ```

3. **Commit and push**

4. **Re-run manually** if needed:
   ```bash
   gh workflow run deploy-core.yml
   ```

---

## Running Tests

### Unit Tests (Fast)
```bash
pytest tests/ -v  # All tests
pytest tests/test_algo_*.py -v  # Algo tests only
```

### Linting
```bash
black . --check  # Code formatting
flake8 . --max-line-length=120  # Style guide
```

### Integration Tests (Medium)
```bash
pytest tests/integration/ -v  # Uses docker-compose database
```

### Backtest Regression (Slow, Optional)
```bash
python3 algo_backtest.py --validate  # Full backtest suite
```

Automated in CI: `ci-backtest-regression.yml` (runs on push to main)

---

## Debugging

### Check Algo Logs Locally
```bash
python3 algo_run_daily.py 2>&1 | grep -i "error\|warn\|trade"
```

### Check AWS Lambda Logs
```bash
aws logs tail /aws/lambda/algo-orchestrator --follow --region us-east-1
```

### Check ECS Loader Logs
```bash
# Find the task
aws ecs list-tasks --cluster stocks-data-cluster --region us-east-1

# Get logs
aws logs tail /ecs/stocks-data-cluster --follow --region us-east-1
```

### Database Inspection
```bash
# Connect to AWS RDS from Bastion (see tools-and-access.md)
psql -h <RDS_ENDPOINT> -U stocks -d stocks

# Or locally:
psql -h localhost -U stocks -d stocks

# Useful queries:
SELECT * FROM algo_trades WHERE created_at > NOW() - INTERVAL '1 day' ORDER BY created_at DESC;
SELECT symbol, quantity, entry_price, current_price FROM algo_positions WHERE active = true;
SELECT COUNT(*) FROM buy_sell_daily WHERE date = CURRENT_DATE;
```

### Check Alpaca Account
```bash
python3 -c "
from alpaca_trade_api import REST
import os
api = REST(os.getenv('APCA_API_KEY_ID'), os.getenv('APCA_API_SECRET_KEY'), base_url=os.getenv('APCA_API_BASE_URL'))
print(f'Account: {api.get_account()}')
print(f'Positions: {api.list_positions()}')
"
```

---

## Common Development Tasks

### Add a New Signal Filter
1. Edit `algo_filter_pipeline.py` (add to tier 1-5)
2. Test: `python3 algo_run_daily.py`
3. Commit and push

### Adjust Position Sizing
1. Edit `algo_governance.py` (kelly_criterion or max_position_size)
2. Test locally
3. Push to main
4. Deploy: `gh workflow run deploy-algo-orchestrator.yml`

### Change Market Hours or Trading Window
1. Edit `algo_market_calendar.py` or `algo_config.py`
2. Test locally
3. Push and deploy

### Add New Database Column to Track Something
1. Edit `algo_orchestrator.py` (ALTER TABLE in Phase 7 reconciliation)
2. Or edit `init_db.sql` for new tables
3. Test locally with Docker Compose
4. Commit and push
5. Deploy: `gh workflow run deploy-algo-orchestrator.yml` (Lambda runs init on first invocation)

---

## Deployment to AWS (After Local Verification)

**Never** push untested changes directly to main. Always:
1. ✅ Test locally with `python3 algo_run_daily.py`
2. ✅ Run linting: `black . && flake8 .`
3. ✅ Run unit tests: `pytest tests/ -v`
4. ✅ Then commit and push
5. ✅ Watch CI in GitHub Actions
6. ✅ If tests pass, auto-deploy begins

---

**Remember:** Local iteration is 10x faster than AWS iteration. Always test here first.
