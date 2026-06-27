# Codebase Governance

**AWS credential error?** Run: `scripts/refresh-aws-credentials.ps1`

## Pre-Commit Rules (Non-Negotiable)

1. No `.env` files — use AWS Secrets Manager
2. No `pdb`, `ipdb`, `breakpoint()` in code
3. `mypy` strict mode passes (type safety enforced)
4. No print in library code (logging only)
5. **NEVER set safety thresholds to zero** — bypasses all guards

See memory for extended guidance: architecture, safety rules, CI/CD procedures.
