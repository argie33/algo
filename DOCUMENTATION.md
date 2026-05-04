# Documentation Index

## Quick Start
- **`CLAUDE.md`** (5 min read)
  - One true server
  - Quick local startup
  - Links to detailed docs

## Development

- **`LOCAL_SETUP.md`** (15 min)
  - Prerequisites and installation
  - Database configuration (local or RDS)
  - Starting the dev stack
  - Common local issues
  
- **`API_REFERENCE.md`** (20 min)
  - All API endpoints
  - Response formats
  - Database table schema
  - Authentication
  - Example curl commands

- **`TROUBLESHOOTING.md`** (as needed)
  - Local development issues
  - AWS deployment issues
  - Data loading issues
  - Performance debugging

## Data & Loaders

- **`DATA_LOADING.md`** (reference)
  - 39 official data loaders
  - Loader phases and dependencies
  - Loading schedule (intraday, daily, weekly, etc.)
  - Optimization techniques

## Algo System

- **`ALGO_DEPLOYMENT.md`** (20 min)
  - Algo orchestrator deployment
  - Lambda + EventBridge architecture
  - Daily 5:30pm ET execution
  - Monitoring and alerts
  - CloudFormation template details

- **`ALGO_ARCHITECTURE.md`** (deep dive)
  - Swing trading system design
  - Research citations and methodology
  - Trade decision flow
  - Risk management rules
  - Position sizing logic

## AWS Infrastructure

- **`AWS_DEPLOYMENT.md`** (20 min)
  - Architecture overview
  - CloudFormation templates
  - GitHub Actions workflows
  - Environment variables
  - Scaling and optimization
  - Disaster recovery
  - Security

## Design & Planning

- **`MASTER_PLAN.md`** (optional)
  - Overall system roadmap
  - Priority features
  - Technical milestones

- **`FRONTEND_DESIGN_SYSTEM.md`** (optional)
  - UI components
  - Design tokens
  - Page architecture

## Quick Reference

| Document | Purpose | When to Read |
|----------|---------|--------------|
| CLAUDE.md | Getting started | Always (first) |
| LOCAL_SETUP.md | Set up development environment | Before development |
| API_REFERENCE.md | What API endpoints exist | When building frontend |
| AWS_DEPLOYMENT.md | Deploy to AWS | Before deployment |
| DATA_LOADING.md | Data loading pipeline | Understanding data flow |
| ALGO_DEPLOYMENT.md | Deploy algo trading system | Setting up algo |
| ALGO_ARCHITECTURE.md | How the algo works | Understanding the algo |
| TROUBLESHOOTING.md | Fix problems | When something breaks |
| DOCUMENTATION.md | Find what you need | Navigation (this file) |

---

## Common Tasks

### I want to start developing locally
1. Read: `CLAUDE.md` (quick start)
2. Read: `LOCAL_SETUP.md` (detailed setup)
3. Run: Commands from LOCAL_SETUP.md

### I want to add a new API endpoint
1. Read: `API_REFERENCE.md` (see existing patterns)
2. Edit: `webapp/lambda/routes/*.js`
3. Test: `curl http://localhost:3001/api/...`

### I want to load new data
1. Read: `DATA_LOADING.md` (see 39 official loaders)
2. Edit: One of `load*.py` files
3. Test locally: `python3 load*.py --backfill_days 10`

### I want to understand the algo
1. Read: `ALGO_ARCHITECTURE.md` (design and research)
2. Read: `ALGO_DEPLOYMENT.md` (how it runs in AWS)
3. Examine: `algo_*.py` files

### I want to deploy to AWS
1. Read: `AWS_DEPLOYMENT.md` (architecture overview)
2. Read: Related deployment docs (API, loaders, algo)
3. Follow: GitHub Actions workflows

### Something is broken
1. Read: `TROUBLESHOOTING.md` (find your issue)
2. Follow: Debug steps
3. Check: CloudWatch logs (if AWS)

---

## File Organization

```
repo/
├── CLAUDE.md                    (minimal start)
├── DOCUMENTATION.md             (this file)
├── LOCAL_SETUP.md               (dev environment)
├── API_REFERENCE.md             (API spec)
├── AWS_DEPLOYMENT.md            (AWS infrastructure)
├── TROUBLESHOOTING.md           (debugging)
├── DATA_LOADING.md              (loaders)
├── ALGO_DEPLOYMENT.md           (algo in AWS)
├── ALGO_ARCHITECTURE.md         (algo design)
├── MASTER_PLAN.md               (roadmap)
├── FRONTEND_DESIGN_SYSTEM.md    (UI design)
│
├── webapp/                       (frontend + API)
│   ├── lambda/                  (Express API server)
│   │   ├── index.js             (main server)
│   │   └── routes/              (API endpoints)
│   └── frontend/                (React app)
│       └── src/
│
├── lambda/                       (AWS Lambda)
│   └── algo_orchestrator/       (algo execution)
│
├── .github/workflows/            (GitHub Actions)
│   ├── deploy-algo-orchestrator.yml
│   ├── deploy-app-stocks.yml
│   ├── deploy-infrastructure.yml
│   ├── deploy-core.yml
│   ├── deploy-webapp.yml
│   └── ...
│
├── load*.py                      (39 data loaders)
├── algo_*.py                     (algo components)
└── requirements.txt              (Python dependencies)
```

---

## Notes

- All documentation files are in the repo root
- Each file is self-contained (can be read independently)
- Cross-references point to other files (see "See Also" sections)
- Keep documentation separate from CLAUDE.md to avoid cluttering the IDE experience
- Update this index when adding new documentation
