# Codebase Governance (Quick Reference)

See **`steering/GOVERNANCE.md`** for complete architecture, standards, and safety configuration.

See **`steering/OPERATIONS.md`** for CI/CD procedures, deployments, and troubleshooting.

## Quick Start

**AWS credential error?** Run: `scripts/refresh-aws-credentials.ps1`

## Key Rules (Enforced Pre-Commit)

1. **No `.env` files** — Use AWS Secrets Manager
2. **No debug code** — `pdb`, `ipdb`, `breakpoint()`
3. **Type-safe code** — `mypy` must pass
4. **Code cleanliness** — Linting + formatting enforced
5. **NEVER set safety thresholds to zero** — Doing so bypasses all guards

**All other governance rules are in `steering/GOVERNANCE.md`.**
