# Steering Documentation Index

**Master reference for all project documentation.** Use this to find the right guide for your task.

---

## Quick Start By Task

| Task | Document | TL;DR |
|------|----------|-------|
| **Understand system architecture** | [GOVERNANCE.md](GOVERNANCE.md) | Live trading, Minervini strategy, 5 pipelines |
| **Am I on AWS or local?** | [DATABASE_AND_ENVIRONMENTS.md](DATABASE_AND_ENVIRONMENTS.md) | Run verification query, see host |
| **Data pipeline details** | [DATA_LOADERS.md](DATA_LOADERS.md) | 40+ loaders, 5 Step Functions, timing |
| **Run loaders locally** | [DATA_LOADERS.md](DATA_LOADERS.md) | `python3 loaders/load_*.py` |
| **Deploy Lambda changes** | [OPERATIONS.md](OPERATIONS.md#aws-deployment-via-github-actions) | GitHub Actions workflows |
| **Check code quality** | [LINT_POLICY.md](LINT_POLICY.md) | `make lint`, `make type-check`, pre-commit hooks |
| **Common problems** | [COMMON_OPERATIONS.md](COMMON_OPERATIONS.md) | Troubleshooting, debugging, verification |

---

## Document Organization

### Core Steering (Always Read These)
- **[GOVERNANCE.md](GOVERNANCE.md)** — System architecture, safety rules, data contracts, trading strategy
- **[OPERATIONS.md](OPERATIONS.md)** — CI/CD pipeline, GitHub Actions, Lambda deployment, monitoring
- **[DATA_LOADERS.md](DATA_LOADERS.md)** — Loader orchestration, 5 pipelines, parallelism, timing
- **[LINT_POLICY.md](LINT_POLICY.md)** — Type checking, linting, strict validation testing

### Infrastructure & Configuration
- **[DATABASE_AND_ENVIRONMENTS.md](DATABASE_AND_ENVIRONMENTS.md)** — Database config, AWS/local selection, credentials
- **[COMMON_OPERATIONS.md](COMMON_OPERATIONS.md)** — Runbook: common problems, debugging, verification queries

### Detailed References (Optional)
- **[FACTOR_SCORES_DATA_FLOW.md](FACTOR_SCORES_DATA_FLOW.md)** — Deep dive: how data flows into factor scores

---

## Critical Rules

### Data Integrity
- ✓ Always verify which database you're on before making changes
- ✓ Local changes don't reach production users
- ✓ Production changes are live immediately
- ✓ No `.env` files with secrets — use AWS Secrets Manager

### Code Quality
- ✓ All code must pass `mypy` (type checking)
- ✓ All code must pass `ruff` (linting)
- ✓ Pre-commit hooks enforce this automatically
- ✓ `make ci-local` simulates full CI pipeline

### Data Contracts
- ✓ Optional data returns explicit `data_unavailable: True` markers
- ✓ Missing critical data logged at ERROR/WARNING level
- ✓ No silent failures with empty defaults

**Full rules:** [GOVERNANCE.md](GOVERNANCE.md)

---

## When to Update Steering

Add/update steering docs when:
- ✓ You discover something that takes 5+ minutes to explain verbally
- ✓ The same question gets asked twice
- ✓ A procedure or infrastructure change requires updates
- ✓ New environment variables, endpoints, or credentials are added
- ✓ A debugging technique worked and should be saved for future use

**Keep it clean:** Delete incident-specific guides (dated 2026-XX-XX) after the incident is resolved. Steering is for ongoing reference, not historical record.

---

## Document Maintenance

- **Trust GOVERNANCE.md first** — It contains architecture rules and constraints
- **OPERATIONS.md is authoritative** — For deployment, CI/CD, monitoring
- **Follow links** — Docs reference each other; read the related sections
- **When you find a gap** — Update the relevant steering doc before moving on

---

Last Updated: 2026-07-01  
Cleaned up: Removed 13 incident-specific docs (2026-07-01). Core steering reduced from 20 files to 8.
