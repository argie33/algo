# Stock Analytics Platform - Production Trading System

**Status:** 🟢 Production Ready | **Version:** 1.0.0 | **Last Updated:** 2026-05-16

A comprehensive algorithmic trading platform with institutional-grade risk management, real-time market data analysis, and automated execution. Built with Python, PostgreSQL, AWS Lambda, and React.

---

## 🚀 Quick Start

### Local Development
```bash
# Install dependencies
pip3 install -r requirements.txt

# Start Docker services (PostgreSQL, Redis)
docker-compose up -d

# Run paper trading (simulation mode)
python3 algo_orchestrator.py --mode paper --dry-run

# Start frontend dev server
cd webapp/frontend
npm install
npm run dev
```

### Production Deployment
```bash
# All deployment is automated via GitHub Actions
# Just push to main branch:
git push origin main

# Monitor at: https://github.com/argie33/algo/actions
# Expected: 20-30 minutes for full deployment
```

---

## 📋 System Architecture

### Core Components

**1. Data Pipeline (36 Loaders)**
- Alpaca prices (EOD + intraday)
- Technical indicators (30+ metrics)
- Stock fundamentals (earnings, financials, news)
- Market breadth, sentiment, economic data
- EventBridge triggers daily at 4:05pm ET

**2. Calculation Engine (165 Modules)**
- **Minervini 8-point trend template** - Identifies strong uptrends
- **Swing trader score** - 7-factor composite (setup, trend, momentum, volatility, fundamentals, sector, multi-timeframe)
- **Market exposure** - 11-factor quantitative regime score (0-100%)
- **Value at Risk (VaR)** - Historical simulation with CVaR
- **Technical indicators** - MACD, RSI, stochastic, Bollinger Bands, etc.

**3. Risk Management (Circuit Breakers)**
- Position limits (max % of portfolio per trade)
- Exposure limits (max market participation percentage)
- Drawdown halts (stop trading if portfolio down > threshold)
- Daily loss limits (max daily P&L)
- VIX gates (reduce position size in high volatility)

**4. 7-Phase Orchestrator**
1. **Data Freshness** - Verify market data is recent (fail-closed if stale)
2. **Circuit Breakers** - Check all kill switches (halt if any fired)
3. **Position Monitor** - Evaluate open positions, compute stops, score health
4. **Exit Execution** - Apply exit signals (stops, profit targets, time-based exits)
5. **Signal Generation** - 5-tier filter pipeline → rank candidates
6. **Entry Execution** - Execute ranked entries with idempotency
7. **Reconciliation** - Sync with broker, update P&L, create audit trail

**5. API Layer (19 Endpoints)**
- `/api/stocks` - Stock screener with scores and prices
- `/api/signals` - Trading signals (BUY/SELL with quality scores)
- `/api/algo/status` - Orchestrator state, open positions, P&L
- `/api/scores` - Stock quality scores and rankings
- `/api/economic` - Economic indicators and market health
- `/api/market` - Market regime, breadth, sentiment
- `/api/sectors` - Sector analysis and rotation signals
- `/api/health` - API health and latency check

**6. Frontend (25 Pages)**
- **ScoresDashboard** - Stock screener with real-time scores
- **MetricsDashboard** - Performance metrics and analysis
- **AlgoTradingDashboard** - Live orchestrator state
- **PortfolioDashboard** - Position tracking and risk metrics
- **SectorAnalysis** - Sector performance and exposure
- **EconomicDashboard** - Economic indicators and regime
- **AuditViewer** - Trade audit log and history
- +18 more specialized pages

---

## 🔧 Configuration

### Environment Variables (Required)

```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_USER=stocks
DB_NAME=stocks
DB_PASSWORD=<from AWS Secrets Manager>

# Trading
ALPACA_API_KEY=<your alpaca key>
ALPACA_SECRET_KEY=<your alpaca secret>
ALPACA_PAPER=true  # Set to false for live trading

# AWS
AWS_REGION=us-east-1
DATABASE_SECRET_ARN=arn:aws:secretsmanager:...

# Optional
ALERT_EMAIL_TO=your@email.com
ALERT_SLACK_WEBHOOK=https://hooks.slack.com/...
```

### Key Config Files

- **algo_config.py** - Trading parameters (position size, limits, thresholds)
- **algo_market_calendar.py** - Trading hours and holidays
- **feature_flags.py** - Feature toggles for testing

---

## 📊 Data Flow

```
Data Loaders (36)
    ↓
Database (PostgreSQL, 110+ tables)
    ↓
Calculation Modules (165)
    ↓
Orchestrator (7 phases)
    ↓
Trading Signals
    ↓
API Layer (19 endpoints)
    ↓
Frontend (25 pages)
```

---

## ✅ Pre-Deployment Verification

See `DEPLOYMENT_CHECKLIST_FINAL.md` for complete pre/post-deployment verification steps.

Quick checklist:
- [ ] All Python files compile (225+ files)
- [ ] Credentials are secure (using credential_helper.py)
- [ ] Database tables are defined (110+ tables)
- [ ] API endpoints respond
- [ ] Frontend pages load
- [ ] Data loaders populate fresh data (daily at 4:05pm ET)

---

## 🚀 Deployment

### GitHub Actions Workflow
1. **Terraform** - Create/update AWS infrastructure (Lambda, RDS, EventBridge)
2. **Docker** - Build and deploy ECS tasks for data loaders
3. **Lambda API** - Deploy API Gateway + Lambda functions
4. **Lambda Orchestrator** - Deploy orchestrator Lambda
5. **Frontend** - Build React and deploy to CloudFront
6. **Database** - Initialize schema from init_database.py

**Time:** 20-30 minutes  
**Status:** Watch at https://github.com/argie33/algo/actions

---

## 📈 Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| API response | < 1s | With connection pooling |
| Frontend load | < 2s | First paint |
| Lambda execution | < 30s | 7-phase orchestrator |
| Database query | < 500ms | With composite indexes |
| Data freshness | Daily EOD | EventBridge trigger 4:05pm ET |

---

## 🔐 Security

- **Credentials:** AWS Secrets Manager (encrypted at rest)
- **Database:** Encrypted, private subnet, no public access
- **API:** HTTPS only, CORS configured, rate limiting enabled
- **SQL:** Parameterized queries, whitelist validation (algo_sql_safety.py)
- **Code:** Credential helper with environment-aware fallbacks

---

## 📚 Documentation

- **DEPLOYMENT_GUIDE.md** - How to deploy via GitHub Actions
- **DEPLOYMENT_CHECKLIST_FINAL.md** - Pre/post-deployment verification
- **SESSION_COMPLETE_SUMMARY.md** - System status and readiness
- **COMPREHENSIVE_AUDIT_REPORT_2026_05_15.md** - Detailed audit findings
- **STATUS.md** - Current session status and fixes applied

---

## 🧪 Testing

### Unit Tests
```bash
python3 -m pytest tests/unit/ -v
```

### Integration Tests
```bash
python3 -m pytest tests/integration/ -v
```

### Paper Trading (Simulation)
```bash
python3 algo_orchestrator.py --mode paper --dry-run
```

### Live Data Verification
```bash
python3 verify_system_comprehensive.py
```

---

## 🐛 Troubleshooting

### GitHub Actions Deployment Fails
1. Check credentials are set in GitHub Secrets
2. Verify Terraform files are valid
3. Check CloudWatch logs in AWS console
4. See troubleshooting-guide.md

### API Returns 401 Unauthorized
1. Verify Cognito is disabled (cognito_enabled = false)
2. Redeploy API Gateway via Terraform
3. Check API Gateway logs in CloudWatch

### No Fresh Data in Database
1. Verify EventBridge rule is enabled
2. Check ECS task logs
3. Verify data loaders have fresh Alpaca credentials
4. Manually trigger loader: `python3 load_eod_bulk.py`

### Trading Not Starting
1. Verify circuit breakers aren't halting
2. Check Phase 1 data freshness gate
3. Verify sufficient portfolio value for minimum position size
4. Check CloudWatch logs for orchestrator errors

---

## 📞 Support

- **Status Checks:** `python3 verify_system_comprehensive.py`
- **Logs:** CloudWatch → /aws/lambda/algo-orchestrator, /aws/ecs/data-loaders
- **Metrics:** CloudWatch → Dashboards → algo-system-metrics
- **GitHub Issues:** https://github.com/argie33/algo/issues

---

## 📄 License

Private | Proprietary Trading System

---

## 🎯 Next Steps

1. **Deploy:** `git push origin main` (automated via GitHub Actions)
2. **Verify:** Follow `DEPLOYMENT_CHECKLIST_FINAL.md`
3. **Paper Test:** Run `python3 algo_orchestrator.py --mode paper --dry-run`
4. **Go Live:** Get approval, then set `ALPACA_PAPER=false`

**Expected Time to Production:** ~2 hours after deployment

