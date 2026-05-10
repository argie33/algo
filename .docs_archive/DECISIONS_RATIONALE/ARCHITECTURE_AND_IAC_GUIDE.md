# Architecture & Infrastructure as Code (IaC) Guide

**Purpose**: Establish the RIGHT way to set up everything — locally and in AWS — following IaC best practices  
**Date**: 2026-05-06  
**Status**: Authoritative guide for environment setup

---

## Core Principles

### 1. Infrastructure as Code (IaC)
- **All infrastructure defined in code**, not manual AWS Console clicks
- **Version controlled** in git
- **Reproducible** — can recreate entire infrastructure from code
- **Auditable** — all changes are git commits

### 2. Environment Parity
- **Same database schema** everywhere (init_database.py)
- **Same environment variables** structure (local uses .env.local, AWS uses Secrets Manager)
- **Same code** runs in local, staging, and production
- **Only environment changes**, not code

### 3. Secrets Management
- **Never hardcode secrets** in code or CloudFormation
- **Local dev**: Use .env.local (git-ignored)
- **AWS**: Use AWS Secrets Manager (not environment variables, not CloudFormation parameters)
- **CI/CD**: Use GitHub Actions secrets (encrypted)

### 4. Single Source of Truth
- **database schema**: init_database.py (runs everywhere)
- **infrastructure**: CloudFormation templates (runs in AWS)
- **docker setup**: docker-compose.local.yml (runs locally)
- **configuration**: Environment variables (same names everywhere)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Application Code                        │
│  (algo_orchestrator.py, algo_trade_executor.py, etc.)       │
│                                                              │
│  Reads: ENVIRONMENT VARIABLES (same everywhere)             │
│  Connects: Via psycopg2 using DB_HOST, DB_USER, etc.       │
└─────────────────────────────────────────────────────────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
        ┌──────────────────┐     ┌──────────────────┐
        │  LOCAL DEV       │     │  AWS PRODUCTION  │
        ├──────────────────┤     ├──────────────────┤
        │ .env.local       │     │ Secrets Manager  │
        │ docker-compose   │     │ CloudFormation   │
        │ PostgreSQL 15    │     │ RDS PostgreSQL   │
        │ (localhost:5432) │     │ (RDS endpoint)   │
        └──────────────────┘     └──────────────────┘
```

The **application code doesn't care** which database it connects to — it only reads environment variables.

---

## Local Development Setup (The RIGHT Way)

### Files & Responsibilities

```
Repository Root
├── docker-compose.local.yml        ← IaC: Local infrastructure definition
├── .env.local.example              ← Template for local environment
├── .env.local                       ← ACTUAL values (git-ignored, not committed)
├── .gitignore                       ← Must include: .env.local
├── init_database.py                ← IaC: Database schema (used everywhere)
├── scripts/
│   └── init_db_local.sh            ← IaC: Local PostgreSQL setup
├── SETUP_LOCAL_DEVELOPMENT.md      ← Documentation (this process)
└── application code (algo_*.py)    ← Same code as AWS
```

### Workflow: Local Development

**Step 1: Get credentials**
```bash
cp .env.local.example .env.local
# Edit .env.local with:
#   - DB_PASSWORD=your-local-password
#   - APCA_API_KEY_ID=your-paper-key
#   - APCA_API_SECRET_KEY=your-paper-secret
```

**Step 2: Start infrastructure**
```bash
docker-compose -f docker-compose.local.yml up -d
```
This runs the IaC definition: PostgreSQL database with exact same config as AWS RDS

**Step 3: Initialize schema**
```bash
python init_database.py
```
Same script that runs when RDS is first created. Creates all algo tables, indexes, etc.

**Step 4: Run application**
```bash
python algo_orchestrator.py --dry-run
```
Application reads .env.local, connects to PostgreSQL via docker network, executes.

---

## AWS Production Setup (The RIGHT Way)

### Files & Responsibilities

```
Repository Root
├── .github/workflows/
│   ├── deploy-core.yml             ← IaC: Runs template-core.yml
│   ├── deploy-data-infrastructure.yml ← IaC: Runs template-data-infrastructure.yml
│   ├── deploy-algo.yml             ← IaC: Runs template-algo.yml
│   └── deploy-all-infrastructure.yml ← Orchestrator workflow
│
├── template-*.yml                  ← IaC: CloudFormation definitions
│   ├── template-core.yml           ← VPC, networking, security groups
│   ├── template-data-infrastructure.yml ← RDS, Secrets Manager, ECS cluster
│   └── template-algo.yml           ← Lambda, EventBridge, orchestrator
│
├── lambda/algo_orchestrator/
│   └── lambda_function.py          ← AWS Lambda entrypoint
│       Reads: AWS Lambda environment + Secrets Manager
│       Connects: Via RDS endpoint + secret credentials
│
├── init_database.py                ← SAME schema initialization (runs everywhere)
└── application code (algo_*.py)    ← SAME code as local
```

### Workflow: AWS Deployment

**Step 1: Commit code to main**
```bash
git add .
git commit -m "description"
git push origin main
```

**Step 2: Trigger deployment**
```bash
# Via GitHub UI: Actions → deploy-all-infrastructure.yml → Run workflow
# Or via CLI:
gh workflow run deploy-all-infrastructure.yml
```

**Step 3: CloudFormation deploys infrastructure**
- Creates VPC, subnets, security groups (template-core.yml)
- Creates RDS database, Secrets Manager (template-data-infrastructure.yml)
- Creates Lambda, EventBridge (template-algo.yml)

**Step 4: Lambda environment is configured**
- Lambda has environment variable: `DB_SECRET_ARN` pointing to Secrets Manager
- Lambda function reads DB credentials from Secrets Manager
- Same `init_database.py` runs to initialize schema on first run

**Step 5: Application code runs in Lambda**
- Lambda executes application code (algo_orchestrator.py, etc.)
- Code reads environment variables (DB_SECRET_ARN) — same pattern as local
- Code connects to RDS using credentials from Secrets Manager
- Code executes trading logic

---

## Environment Variables: Consistency Pattern

### Local Development (.env.local)
```env
DB_HOST=postgres              # Docker service name (NOT an IP)
DB_PORT=5432
DB_NAME=stocks
DB_USER=stocks
DB_PASSWORD=your-local-password

ENVIRONMENT=local
EXECUTION_MODE=paper
```

**Key principle**: DB_HOST=postgres is the service NAME in docker-compose, NOT an IP address.
Docker DNS automatically resolves `postgres` to the container's IP.

### AWS Lambda Environment Variables
```env
DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:stocks-db-secrets-NAME
ENVIRONMENT=production
EXECUTION_MODE=paper  # or 'live' after paper validation
```

**Key principle**: Lambda doesn't store credentials as env vars (too risky).
Instead, it gets `DB_SECRET_ARN` and fetches credentials from Secrets Manager at runtime.

### Code Pattern (Application)
```python
import os
from dotenv import load_dotenv
import psycopg2
import boto3
import json

# Load from .env.local in local dev, from Lambda environment in AWS
load_dotenv()

db_host = os.getenv('DB_HOST')
db_user = os.getenv('DB_USER')
db_name = os.getenv('DB_NAME')

# Local dev: get password from .env.local
# AWS: get credentials from Secrets Manager via ARN
if os.getenv('DB_SECRET_ARN'):
    # AWS: fetch from Secrets Manager
    secret_arn = os.getenv('DB_SECRET_ARN')
    sm = boto3.client('secretsmanager')
    secret = json.loads(sm.get_secret_value(SecretId=secret_arn)['SecretString'])
    db_host = secret['host']
    db_user = secret['username']
    db_password = secret['password']
else:
    # Local dev: from .env.local
    db_password = os.getenv('DB_PASSWORD')

# Same connection code everywhere
conn = psycopg2.connect(
    host=db_host,
    user=db_user,
    password=db_password,
    database=db_name
)
```

**Key principle**: Application code is IDENTICAL — environment changes, not code.

---

## Database Schema: Universal Pattern

### init_database.py
```python
import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

# Get connection info from environment
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "port": int(os.getenv("DB_PORT", 5432)),
}

# Connect and create schema
conn = psycopg2.connect(**db_config)
cur = conn.cursor()

# Define schema (CREATE TABLE IF NOT EXISTS — idempotent)
SCHEMA = """
    CREATE TABLE IF NOT EXISTS algo_tca (
        tca_id SERIAL PRIMARY KEY,
        trade_id INTEGER,
        ...
    );
"""

# Execute
cur.execute(SCHEMA)
conn.commit()
```

**Key principle**: 
- Uses environment variables for connection
- `CREATE TABLE IF NOT EXISTS` — idempotent, safe to run multiple times
- Works locally (.env.local) AND in AWS (Secrets Manager)
- Same script runs everywhere

---

## The RIGHT Way: Checklist

### Local Development Setup ✓
- [ ] docker-compose.local.yml defined and versioned
- [ ] .env.local.example created (template)
- [ ] .env.local in .gitignore (not committed)
- [ ] Database credentials in .env.local (local only)
- [ ] init_database.py uses environment variables
- [ ] Documentation: SETUP_LOCAL_DEVELOPMENT.md

### AWS Infrastructure Setup ✓
- [ ] CloudFormation templates for all infrastructure
- [ ] Secrets Manager for sensitive data (NOT env vars)
- [ ] GitHub Actions workflows for deployment
- [ ] Stack dependency order documented
- [ ] Output exports for inter-stack references

### Code Setup ✓
- [ ] Application reads environment variables (not hardcoded)
- [ ] Secrets Manager pattern for AWS (boto3 client)
- [ ] .env.local pattern for local dev (dotenv)
- [ ] Same code runs everywhere
- [ ] No CloudFormation parameters for secrets

### Documentation ✓
- [ ] SETUP_LOCAL_DEVELOPMENT.md (step-by-step local setup)
- [ ] ARCHITECTURE_AND_IAC_GUIDE.md (this file)
- [ ] CLAUDE.md (deployment overview)
- [ ] Comments in code explaining choices

---

## Common Mistakes (Avoid These!)

### ❌ WRONG: Hardcoding secrets
```python
DB_PASSWORD = "prod_password_in_code"  # NO!
APCA_KEY = "key_here"                   # NO!
```

### ✓ RIGHT: Environment variables
```python
DB_PASSWORD = os.getenv('DB_PASSWORD')
APCA_KEY = os.getenv('APCA_API_KEY_ID')
```

---

### ❌ WRONG: CloudFormation parameters for secrets
```yaml
Parameters:
  DBPassword:
    Type: String
    Default: "password"  # Visible in CloudFormation!
```

### ✓ RIGHT: Secrets Manager
```yaml
DBCredentialsSecret:
  Type: AWS::SecretsManager::Secret
  Properties:
    SecretString: !Sub |
      {
        "password": "${MasterUserPassword}"
      }
```

---

### ❌ WRONG: Different setup for local vs AWS
```
Local: SQLite
AWS: PostgreSQL
```

### ✓ RIGHT: Same database everywhere
```
Local: PostgreSQL 15 (via docker-compose)
AWS: PostgreSQL 15 (via RDS)
```

---

### ❌ WRONG: Manual setup steps
```
"Follow these 10 steps to set up..."
"Remember to update this manually in AWS Console..."
```

### ✓ RIGHT: IaC-driven setup
```
"docker-compose up -d" (all infrastructure defined)
"python init_database.py" (schema created)
"gh workflow run deploy-all-infrastructure.yml" (AWS deployed)
```

---

## Verification Checklist

After setup, verify everything is the RIGHT way:

### ✓ Code Consistency
```bash
# Same code works locally and in AWS
python algo_orchestrator.py --dry-run  # Works locally
# (Same code runs in Lambda in AWS)
```

### ✓ Environment Variables
```bash
# Local
cat .env.local | grep DB_HOST  # postgres (docker)

# AWS (in Lambda environment)
# echo $DB_SECRET_ARN  # arn:aws:secretsmanager:...
```

### ✓ Database Schema
```bash
# Local
psql -h localhost -U stocks -d stocks -c "\dt algo_*"

# AWS (via Bastion or Lambda)
# psql -h rds-endpoint.aws -U stocks -c "\dt algo_*"

# Should see SAME tables in both!
```

### ✓ Documentation
```bash
ls -la | grep -E "SETUP_LOCAL|ARCHITECTURE_AND_IAC|CLAUDE.md"
```

---

## Summary: The RIGHT Way

| Aspect | Local | AWS | Common |
|--------|-------|-----|--------|
| **Infrastructure** | docker-compose.local.yml | CloudFormation templates | IaC-driven |
| **Secrets** | .env.local (git-ignored) | Secrets Manager | Never hardcoded |
| **Database** | PostgreSQL 15 (docker) | RDS PostgreSQL 15 | Same schema |
| **Code** | algo_orchestrator.py | Lambda runs algo_orchestrator.py | IDENTICAL |
| **Env Vars** | .env.local file | Lambda environment | Same names |
| **Connection** | psycopg2 + .env.local | psycopg2 + Secrets Manager | Same driver |
| **Schema Init** | init_database.py (local) | init_database.py (Lambda) | SAME script |

---

## Next Steps

1. **Local Setup**: Follow SETUP_LOCAL_DEVELOPMENT.md
2. **Verify Locally**: Run orchestrator, check database
3. **AWS Deployment**: Use CloudFormation workflows
4. **Verify in AWS**: Check that Lambda runs same code
5. **Monitor**: CloudWatch logs for both environments

---

**Status**: Complete IaC Architecture Guide  
**Last Updated**: 2026-05-06  
**Maintained by**: Infrastructure Team
