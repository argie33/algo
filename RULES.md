# Codebase Cleanliness Rules

**ENFORCED BY GIT HOOKS — These rules are NOT optional.**

## Rule 1: NO SESSION-SPECIFIC DOCUMENTATION

❌ **BLOCKED:**
- `AWS_TROUBLESHOOTING_*.md`
- `EXECUTION_*.md`, `BLOCKERS_*.md`
- `*_STATUS.md`, `*_SUMMARY.md`, `*_REPORT.md`
- `CURRENT_SESSION_*.md`
- Any temporary analysis/status files

✅ **ALLOWED:**
- Use `memory/status_current.md` (rotate weekly, max 50 lines)
- All project docs: `CLAUDE.md`, `DEPLOYMENT_GUIDE.md`, `LOCAL_CRED_SETUP.md`

---

## Rule 2: NO ONE-TIME / SETUP / UTILITY SCRIPTS AT ROOT

❌ **BLOCKED:**
- `setup-*.sh`, `setup-*.ps1`, `setup-*.bat`
- `verify-*.sh`, `check-*.sh`, `debug-*.sh`
- `trigger-*.sh`, `sync-*.sh`, `bootstrap-*.sh`
- `test-*.js`, `*-test.py`
- Any root-level `.bat` or `.ps1` files

✅ **ALLOWED:**
- `scripts/` directory for legitimate utility scripts
- Core scripts: `start-dev.sh`, `entrypoint.sh`, `build-docker.sh`, `trigger-loader-ecs.sh`

**Why:** Each script loads into context. 1 unnecessary script = 150+ wasted tokens per conversation.

---

## Rule 3: NO DUPLICATE TEST/CONFIG FILES

❌ **BLOCKED:**
- Multiple `playwright.*.config.js` files (keep only `playwright.config.js`)
- Multiple `jest.*.config.js` files (keep only `jest.config.js`)
- Multiple `setup.js` files across different directories
- Test configs for specific browsers/environments (use ONE canonical config)

✅ **ALLOWED:**
- `playwright.config.js` (single source of truth)
- `jest.config.js` (single source of truth)

**Why:** Each duplicate = extra files loaded, confusing which is authoritative.

---

## Rule 4: NO GENERATED / ARTIFACT FILES

❌ **BLOCKED:**
- `schema_mapping.json`, `*_schema.json`
- Generated dumps, reports, output files
- Build artifacts (use `.gitignore` instead)

✅ **ALLOWED:**
- Source code configuration files
- Infrastructure-as-code (`.tf` files)

---

## Rule 5: NO EXPERIMENTAL / DEMO / WIP CODE

❌ **BLOCKED:**
- `demo-*.js`, `example-*.js`, `*-demo.py`
- `draft-*.js`, `*-draft.py`
- `wip-*.js`, `*-wip.py`
- `quick-test.js`, `temp-*.py`

✅ **ALLOWED:**
- Finalized, production-ready code only
- If it's experimental → DELETE it, don't commit it

**Why:** Incomplete code confuses future readers and adds maintenance burden.

---

## Rule 6: NO .ENV FILES (EVER)

❌ **ABSOLUTELY BLOCKED:**
- `.env`, `.env.local`, `.env.*`
- Hardcoded credentials anywhere

✅ **REQUIRED:**
- Use AWS Secrets Manager (see `LOCAL_CRED_SETUP.md`)
- Environment variables only in CI/GitHub Actions

---

## Rule 7: NO LARGE FILES (>1MB)

❌ **BLOCKED:**
- Images, binaries, executables
- Large data dumps
- Compiled artifacts

✅ **ALLOWED:**
- Source code, configuration files
- Terraform files, Lambda code

---

## Rule 8: MEMORY FILES MUST BE SMALL

❌ **BLOCKED:**
- Memory files > 150 lines

✅ **REQUIRED:**
- Split large memories or archive old content
- Keep each file focused and concise

---

## Enforcement

**Pre-commit hook** (`/.git/hooks/pre-commit`) automatically blocks violations.

If you try to commit junk, you'll see:
```
❌ BLOCKED: Session-specific .md files not allowed in root
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚫 COMMIT REJECTED - Codebase cleanliness rules enforced
```

**To fix:** Delete the file or move it to the appropriate directory.

---

## Token Costs of Junk

Each file type loaded per conversation:

| Type | Lines | Tokens | Annual Cost |
|------|-------|--------|-------------|
| Setup script | 100 | 150 | $0.50 |
| Session doc | 150 | 225 | $0.75 |
| Duplicate config | 80 | 120 | $0.40 |
| Demo/WIP code | 200 | 300 | $1.00 |

**With 10 junk files:** 1,650 tokens/session = **$60/year**

---

## Summary

- **DO:** Commit source code, tests, infrastructure, documentation
- **DON'T:** Commit one-time scripts, session docs, experimental code, duplicates, generated files
- **RESULT:** Lean, fast, token-efficient codebase
