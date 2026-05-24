# Steering Doc Checklist

Before committing changes to `steering/algo.md`, verify:

## Content ✅
- [ ] **No status keywords:** BLOCKED, blocker, FAILED, status, deployed, quota, error, disconnected, "as of", timestamps (May, 2026-), "running"
- [ ] **No incident logs:** Failed deploys, error messages, rate limit hits, connection timeouts
- [ ] **No timestamps:** Dates, times, "yesterday", "last week", "May 24"
- [ ] **Contains ONLY:** System map, credentials, deploy setup, resource names, schedule, key files, troubleshooting, local dev

## Brevity 📏
- [ ] **Line count:** < 150 lines (current: check `wc -l steering/algo.md`)
- [ ] **Terse language:** "data → DB" not "data goes to database", use abbreviations (4A ET, RSI, EMA)
- [ ] **No prose:** Only tables, bullets, one-liners. No paragraphs.

## Format 🎯
- [ ] **Tables for maps:** System components, credentials, resources, schedules
- [ ] **Bullets for lists:** Comma-separated scannable lists (RSI, SMA, EMA, ATR)
- [ ] **One-liner descriptions:** `algo/algo_orchestrator.py — 7-phase runner`
- [ ] **Commands are runnable:** Copy-paste ready, actual commands

## Red Flags 🚨
If steering mentions:
- Current deployment state (✗ Use GitHub Actions console instead)
- Active blockers (✗ Use GitHub Issues instead)
- Load test results (✗ Commit the result, not the status)
- "Fixed X" (✗ Status — put detail in commit message, fact in code)
- Any date/time (✗ Only static info, no temporal references)

Then it violates the commandments. Edit it out.

## Commit Message
```
docs: Update steering doc — [what changed]

Format: system map | credentials | deploy | resources | schedule | files | troubleshooting
Reason: [why this matters to future work]
```

Pre-commit enforcement blocks violations automatically. If blocked, reread this checklist.
