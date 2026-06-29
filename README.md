# Stock Analytics Platform: Algo

Advanced algorithmic trading system combining Minervini trend-following with fundamental analysis and market breadth filters.

## 🎯 Quick Start

### For Local Development

Get the site running on http://localhost:5173 in 10 minutes:

```powershell
# 1. Set up database and schema
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_PASSWORD = "stocks"
$env:DB_NAME = "stocks"
python scripts/apply-database-schema.py

# 2. Start backend (Terminal 1)
$env:LOCAL_MODE = "true"
cd lambda/api && python dev_server.py

# 3. Start frontend (Terminal 2)
cd webapp/frontend && npm install && npm run dev

# 4. Open http://localhost:5173 in browser ✓
```

For production setup and AWS credentials, see `CLAUDE.md` (Quick reference) and `steering/GOVERNANCE.md` (Architecture).

### For AWS Deployment

Deploy to production in one command:

```bash
git push main
# GitHub Actions automatically:
# 1. Creates AWS infrastructure (API Gateway, Lambda, RDS, etc.)
# 2. Deploys database schema
# 3. Builds and deploys frontend to CloudFront
# 4. Configures monitoring and alerts
```

See `steering/OPERATIONS.md` for deployment verification and troubleshooting.

## ✅ Code Quality & Testing (Before Commits)

Before pushing code, run quality checks locally (takes ~10 seconds with pre-commit hooks):

```bash
# First time: install pre-commit hooks (one-time setup)
make install-hooks

# Then: normal git workflow — hooks run automatically on commit
git add .
git commit -m "feat: new feature"
# ✓ Hooks run automatically: linting, formatting, type-check, security scan
```

**Manual quality checks anytime:**

```bash
# Code quality (matches CI)
make lint           # Ruff linter
make format         # Auto-format with ruff
make type-check     # MyPy type checking

# Testing
make test           # All tests (unit + edge + integration)
make coverage       # Tests with coverage report

# Security
make security       # Bandit + TruffleHog

# Run all CI checks locally
make ci-local
```

📖 **Full CI/CD info:** See [steering/ci.md](steering/ci.md)

---

## 📊 Project Overview

| Component | Technology | Status |
|-----------|-----------|--------|
| **Backend API** | Python 3.11 + FastAPI Lambda | ✅ Ready |
| **Frontend** | React 18 + Vite + TypeScript | ✅ Ready |
| **Database** | PostgreSQL 14+ (RDS in AWS) | ✅ Ready |
| **Scheduler** | EventBridge + Step Functions | ✅ Ready |
| **Authentication** | AWS Cognito | ✅ Ready |
| **Tests** | 169 tests, all passing | ✅ Ready |
| **Security** | API hardened, SQL injection prevention | ✅ Ready |

---

## 🏗️ System Architecture

```
Frontend (React)               API (Lambda)                Database (RDS)
http://localhost:5173  ←→   http://localhost:3001    ←→   stocks DB
     (Vite dev)              (dev_server.py)              (PostgreSQL)
         ↑                         ↑                            ↑
    Hot reload              Real API code                 Schema ready
```

### Production Deployment

```
GitHub          AWS                    Users
  ↓
main branch  →  GitHub Actions  →  Terraform  →  Lambda API  →  React App
(push)           workflow            apply        (AWS)        (CloudFront)
               (deploy-all-              ↓
                infrastructure)        RDS DB
```

---

## 📁 Directory Structure

```
algo/
├── lambda/                      # AWS Lambda functions
│   ├── api/                     # REST API endpoints
│   │   ├── routes/              # API route handlers
│   │   ├── models/              # Request/response schemas
│   │   └── dev_server.py        # Local dev server (port 3001)
│   ├── db-init/                 # Database schema
│   │   └── schema.sql           # Table definitions + indexes
│   └── orchestrator/            # Trading logic (runs 4x daily)
│
├── webapp/frontend/             # React frontend
│   ├── src/                     # React components
│   ├── public/                  # Static assets
│   └── package.json
│
├── algo/                        # Trading algorithm
│   ├── orchestration/           # Phase orchestration
│   ├── signals/                 # Signal generation
│   └── scoring/                 # Stock scoring
│
├── loaders/                     # Data loaders
│   ├── load_prices.py           # OHLCV data
│   ├── load_sectors.py          # Sector allocations
│   ├── load_earnings.py         # Earnings data
│   └── load_*.py                # 6 core loaders + supporting
│
├── utils/                       # Shared utilities
│   ├── db/                      # Database connection pooling
│   ├── validation/              # Data validation
│   └── rate_limiting.py         # API rate limiting
│
├── terraform/                   # Infrastructure as Code
│   ├── main.tf                  # Main AWS resources
│   ├── modules/                 # Modular Terraform components
│   └── DEPLOYMENT_GUIDE.md      # How to deploy
│
├── scripts/                     # Utility scripts
│   ├── apply-database-schema.py # Initialize database
│   ├── refresh-aws-credentials.ps1 # Sync AWS credentials
│   └── verify_safety_thresholds.py # Pre-deployment checklist
│
├── tests/                       # Automated test suite
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
│   └── conftest.py              # Pytest configuration
│
├── CLAUDE.md                    # Project governance & rules
├── README.md                    # ← You are here
└── steering/                    # Core documentation
    ├── GOVERNANCE.md            # Architecture & safety
    ├── LINT_POLICY.md           # Code quality
    └── OPERATIONS.md            # CI/CD & diagnostics
```

---

## 🚀 Commands Reference

### Local Development

```powershell
# Setup (one time)
python scripts/apply-database-schema.py  # Initialize database schema

# Development (2 terminals)
cd lambda/api && python dev_server.py  # Terminal 1: Start backend on port 3001
cd webapp/frontend && npm install && npm run dev  # Terminal 2: Start frontend on port 5173

# Database
psql -h localhost -U stocks -d stocks    # Connect to database
```

### Testing

```powershell
pytest tests/ -v                    # Run all tests
pytest tests/unit -v                # Unit tests only
pytest tests/integration -v         # Integration tests

cd webapp/frontend
npm test                            # Frontend tests
npm run test:coverage               # Coverage report
```

### Database

```powershell
# Initialize schema
python scripts/apply-database-schema.py

# Load sample data
cd loaders
python load_prices.py --sample-mode

# Load specific symbols
python load_prices.py --symbols "AAPL,MSFT,GOOGL"

# Check data freshness
python scripts/check_price_data_freshness.py
```

### Deployment

```bash
# Automatic deployment (triggered by git push main)
git push main
# → GitHub Actions automatically deploys infrastructure

# Manual verification
cd terraform
terraform init
terraform plan
terraform apply

# Check deployment status
aws cloudformation describe-stacks --stack-name algo-main
```

---

## ✅ Verification Checklist

### Local Development

```powershell
# All these should succeed
python scripts/apply-database-schema.py     # ✓ Database ready
cd lambda/api && python dev_server.py       # ✓ Backend starts
cd webapp/frontend && npm install           # ✓ Dependencies installed
npm run build                                # ✓ Production build works
pytest tests/ -q                             # ✓ All tests pass
```

### Before Pushing to Main

```bash
git status                                   # ✓ All changes committed
git log -1                                   # ✓ Last commit looks good
pytest tests/ -v                             # ✓ All tests passing
cd webapp/frontend && npm run build          # ✓ Frontend builds
terraform validate                           # ✓ Terraform valid
```

### After AWS Deployment

```bash
curl https://{api-endpoint}/health          # ✓ API responding
terraform output cloudfront_domain           # ✓ Frontend URL
aws rds describe-db-instances --query       # ✓ Database ready
aws lambda list-functions                    # ✓ Lambda functions deployed
```

---

## 📋 Status Report

**Last Updated:** June 14, 2026

### Code & Tests ✅
- 169 unit tests passing
- 33 API security tests passing
- All critical vulnerabilities fixed
- Type checking complete
- Code cleanup done

### Infrastructure ✅
- Terraform configurations complete
- Database schema finalized
- GitHub Actions workflow ready
- AWS OIDC configured
- Secrets Manager ready

### Deployment 🟢
- **Status:** READY
- **Next Step:** `git push main` (June 15)
- **Estimated Time:** 20-30 minutes
- **Automated:** Yes (full auto-deployment)

---

## 🔗 Documentation

| Document | Purpose |
|----------|---------|
| [CLAUDE.md](CLAUDE.md) | Project governance & constraints |
| [steering/GOVERNANCE.md](steering/GOVERNANCE.md) | Architecture, safety rules, fail-fast patterns |
| [steering/LINT_POLICY.md](steering/LINT_POLICY.md) | Code quality & type safety enforcement |
| [steering/OPERATIONS.md](steering/OPERATIONS.md) | CI/CD pipeline, diagnostics, troubleshooting |
| [terraform/](terraform/) | Infrastructure as Code (AWS resources) |

---

## 🛠️ Development Tips

### Frontend Development
- Changes auto-reload (Vite hot module replacement)
- Use `npm run dev` to start dev server
- Use `npm test` to watch tests
- Use `F12` to debug in browser

### Backend Development
- Changes require server restart (manual or auto-detected)
- Use `LOCAL_MODE=true` to use localhost database
- Use `ENVIRONMENT=development` for verbose logging

### Database Development
- Schema changes go in `lambda/db-init/`
- Run `apply-database-schema.py` to apply migrations
- Views are in migration files (e.g., `001_create_positions_view.sql`)
- Test with: `psql -h localhost -U stocks -d stocks`

### Deployment Preparation
- Before deploying: Run full test suite and build check
- Terraform validates automatically in GitHub Actions
- No manual infrastructure changes needed
- All credentials managed via Secrets Manager

---

## 🚨 Troubleshooting

### Site won't load on http://localhost:5173

```powershell
# 1. Is the frontend dev server running?
netstat -ano | Select-String 5173

# 2. Is the backend running?
netstat -ano | Select-String 3001

# 3. Check browser console (F12) for errors

# 4. Restart both servers:
# Terminal 1: Kill dev_server.py and restart
# Terminal 2: Kill npm dev and restart
```

### API returns 503 or 504 errors

```powershell
# Check database connectivity
psql -h localhost -U stocks -d stocks -c "SELECT 1;"

# Check if tables exist
psql -h localhost -U stocks -d stocks -c "\dt"

# Re-apply schema if needed
python scripts/apply-database-schema.py
```

### Tests failing

```powershell
# Run with verbose output
pytest tests/ -v --tb=short

# Run specific test
pytest tests/unit/test_api.py::test_name -v

# Check imports
python -c "import lambda.api; print('OK')"
```

---

## 📚 Learning Resources

- **Trading Algorithm:** See `algo/algo_orchestrator.py` for phase logic
- **API Documentation:** OpenAPI spec at `/api/openapi.json` (when running)
- **Database Schema:** `lambda/db-init/schema.sql` with comments
- **Tests:** `tests/` directory for examples of how things work

---

## 📞 Support

- **Setup issues?** Check local requirements: Node.js, Python 3.11+, PostgreSQL 14+, AWS CLI
- **Deployment/Infrastructure?** See [steering/OPERATIONS.md](steering/OPERATIONS.md) and [steering/GOVERNANCE.md](steering/GOVERNANCE.md)
- **Code quality?** Check [steering/LINT_POLICY.md](steering/LINT_POLICY.md)
- **Project rules?** Read [CLAUDE.md](CLAUDE.md)

---

## 📄 License

Proprietary - All rights reserved
