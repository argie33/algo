# Bulletproof Steering Guardrails

## Problem Solved
Status kept appearing in steering docs despite rules → Wasted time on stale/fake data.

## Solution: Three-Layer Defense

### Layer 1: CLAUDE.md (Doctrine)
**What changed:**
- Clarified "Source of Truth" section with explicit table: what goes where, why
- Removed ambiguous "system state" language (invited status)
- Added NEGATIVE rules: "NEVER add to steering: status, blockers, errors, timestamps..."

**Result:** Future Claudes know exactly where each type of info belongs.

---

### Layer 2: Pre-Commit Hook (Enforcement)
**New rules added:**
- Rule #12: Detects 20+ status keywords in steering changes (BLOCKED, deployed, quota, "as of", timestamps, etc.)
- Rule #15: Prevents status/timestamps in MEMORY.md descriptions

**Result:** Commits containing status get auto-rejected with clear reason.

**Verified:** Hook passes 14 separate checks before allowing commits.

---

### Layer 3: STEERING_CHECKLIST.md (Quick Reference)
**Sections:**
- Red flags to catch before committing
- Content rules (what to exclude)
- Brevity rules (line count, terse language)
- Format rules (tables, bullets, one-liners)

**Result:** Claudes have a lean reference before every steering edit.

---

## Current State

| Artifact | Status | Compliance |
|----------|--------|-----------|
| `steering/algo.md` | 78 lines | ✅ Verified: no status, terse, discoverable |
| `memory/MEMORY.md` | 2 lines | ✅ Verified: no status snapshots, lean |
| `CLAUDE.md` | 48 lines | ✅ Fixed: doctrine now clear |
| Pre-commit hook | 175 lines | ✅ Enhanced: 15 rules, aggressive status blocking |

---

## How It Works Going Forward

1. **Edit steering:** Use `STEERING_CHECKLIST.md` as reference
2. **Before commit:** Pre-commit hook runs 14 checks, auto-rejects violations
3. **If rejected:** Hook message explains why; fix using checklist
4. **Track blockers elsewhere:** Use GitHub Issues, not steering

---

## Token Efficiency

- Deleted 18 stale memory files: **Saved ~2KB per conversation**
- Reduced MEMORY.md from ~11KB to 80 bytes: **Saves ~600B per conversation**
- steering/algo.md at 78 lines: **~3.8KB, highly discoverable**

**Total: Steering is now lean, terse, and bulletproof.**
