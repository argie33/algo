# Project Quick Reference

**Start here:** Read `steering/GOVERNANCE.md` then `steering/OPERATIONS.md` (covers 80% of needs).

## Core Steering Documents

| Purpose | File |
|---------|------|
| **Architecture & rules** | `steering/GOVERNANCE.md` |
| **Operations & CI/CD** | `steering/OPERATIONS.md` |
| **Data loading** | `steering/DATA_LOADERS.md` |
| **Code quality** | `steering/LINT_POLICY.md` |
| **Troubleshooting** | `steering/COMMON_OPERATIONS.md` |
| **Database setup** | `steering/DATABASE_AND_ENVIRONMENTS.md` |

## Instant Fixes

| Problem | Fix |
|---------|-----|
| AWS credential error | `scripts/refresh-aws-credentials.ps1` |
| Code fails pre-commit | `make format && make type-check` |
| Dashboard stale data | `pkill -9 python && python -m dashboard -w` |

## Non-Negotiable Rules

- ✅ Type safety: `mypy strict` enforced (pre-commit blocks all type errors)
- ✅ Code cleanliness: No `.env`, `pdb`, or `print()` in library code (pre-commit blocks)
- ✅ Data integrity: Explicit `data_unavailable` flags (no silent fallbacks)
- ✅ Safety: Circuit breakers enforce risk limits (see GOVERNANCE.md)

**All other rules, examples, and context:** See the steering docs above. This file stays thin.
