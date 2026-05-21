# Steering System Documentation

## Purpose
This workspace supports multiple projects. The root `CLAUDE.md` is a minimal dispatcher that routes Claude to the appropriate project steering doc. This pattern keeps token burn low while ensuring Claude has the right context for each project.

## Structure

### Root CLAUDE.md (~40 lines)
- Project index table (what projects exist, where their steering docs live)
- Security policy reminder (no .env files)
- Pointer to this file

**What NEVER goes in root CLAUDE.md:**
- Credentials or credential values
- Deployment commands or workflows
- Troubleshooting details
- Architecture diagrams or system maps
- Any project-specific detail

### Per-Project Steering Doc (< 150 lines each)
Example: `steering/algo.md`

All details Claude needs to work on that project live here, ultra-terse:
- STATUS (2-4 bullets: what's working, current blocker, next steps)
- SYSTEM MAP (1-2 tables or brief prose: components + code paths)
- DB SCHEMA (if relevant; 3 lines max)
- CREDENTIALS (policy only, no values; paths to where secrets live)
- DEPLOY (key commands and workflow names)
- RESOURCE NAMES (AWS naming conventions, Terraform var values)
- SCHEDULE (if applicable; cron/EventBridge times)
- KEY FILES (5-7 critical files with one-word purpose)
- TROUBLESHOOTING (symptom → check, one-liners)
- LOCAL DEV (quick-start commands)
- DECISION RATIONALE (why X tech, one-liner per choice)

## Adding a New Project

1. **Create steering doc:** `steering/{project}.md` — copy template below
2. **Update root CLAUDE.md:** Add one row to project index table
3. **Commit:** Include both changes in same commit

### Steering Doc Template

```markdown
# {Project Name} — Steering

## STATUS
- Local: ✅/❌ {brief status}
- Deployment: ✅/❌ {brief status}
- Current blocker: {one item}
- Next: {3 bullet points}

## SYSTEM MAP
[Table or brief prose of key components + code paths]

## CREDENTIALS
[Policy only. Where creds live. What secret paths.]

## DEPLOY
[Key commands. Workflow names if applicable.]

## RESOURCE NAMES
[Project-specific naming conventions (AWS, Terraform, etc.)]

## KEY FILES
[5-7 critical files with one-word purpose]

## LOCAL DEV
[Quick-start commands]

## TROUBLESHOOTING
[3-5 symptom → check pairs]

## DECISION RATIONALE
[Why X tech, one-liner per major choice]
```

## Token Budget Targets
- **Root CLAUDE.md:** < 50 lines (~1.5K bytes)
- **Each steering doc:** < 150 lines (~4K bytes)
- **All steering docs combined:** < 1.2K lines (~30K bytes)

Rationale: Every steering doc is loaded when Claude starts. Keep them lean.

## Keeping Docs Current

**Rule:** Update steering doc in the same commit that changes the system.

Examples of when to update:
- AWS resource names change → update steering doc resource name table
- New key files added → update KEY FILES section
- Cron schedule changes → update SCHEDULE section
- New deployment workflow added → update DEPLOY section
- Decision rationale changes → update DECISION RATIONALE

Stale steering docs = wrong Claude behavior. Prevent it at commit time.

## What NOT to Put in Steering Docs

❌ Code patterns or style guidelines (read the code instead)  
❌ Git history or blame details (use `git log` / `git blame`)  
❌ Bug fixes or debugging solutions already in the codebase  
❌ Full deployment step-by-step walkthroughs (keep to command names + key steps)  
❌ Anything that could go in a subdirectory `.claude/CLAUDE.md` (those are for local-only, non-shared context)  
❌ Full code examples (link to file paths instead)

## What ALWAYS Goes in Steering Docs

✅ Current status (what's working, what's blocked)  
✅ System map (components + code paths)  
✅ Credentials policy (where they live, no values)  
✅ Deployment workflow names (not full details)  
✅ Resource naming conventions (critical for cross-project consistency)  
✅ Key file paths (the few files Claude must understand)  
✅ Quick-start commands (local dev, test, deploy)  
✅ One-liner troubleshooting (symptom → check)  
✅ Decision rationale (why X tech, prevents second-guessing)

## Example: Adding a Second Project

Scenario: You're adding a `web` project (a Next.js frontend + API).

1. Create `steering/web.md` (~100 lines) with:
   - STATUS: local dev ✅, Vercel staging ✅, prod pending
   - SYSTEM MAP: 2 components (Next.js API + frontend)
   - CREDENTIALS: GitHub Secrets for Vercel token
   - DEPLOY: `git push main` → Vercel auto-deploys
   - RESOURCE NAMES: Vercel project `web-prod` / `web-staging`
   - KEY FILES: `pages/api/`, `components/`, `lib/config.ts`
   - Etc.

2. Update root CLAUDE.md, add row:
   ```
   | web | `web/` | `steering/web.md` | Next.js frontend + REST API (Vercel) |
   ```

3. Commit: "docs: add web project steering + update root dispatcher"

4. Future Claude sessions in this repo: reads root CLAUDE.md, sees which project is relevant, reads `steering/web.md`

## Abbreviation Reference

Keep steering docs terse by using standard abbreviations:

**AWS:** Lambda = Λ (or just `Lambda`), RDS = `RDS`, S3 = `S3`, ECS = `ECS`, EventBridge = `EB`, VPC = `VPC`, IAM = `IAM`, SG = Security Group

**Time:** `4A ET` (4 AM ET), `9:30A ET`, `5:30P ET`

**Common Words:**
- Dir = Directory
- Cred = Credential  
- Auth = Authentication
- Env = Environment
- Config = Configuration
- CI/CD = CI/CD (already abbr.)
- Var = Variable

**Symbols:**
- `→` (right arrow) instead of "goes to", "leads to", "produces"
- `|` (pipe) for separators instead of commas in descriptions
- `/` for path separators
- `:` for ratio or relationship (`3:1 write/read`)

**Examples:**
- ✅ `Prices loaded → DB via yfinance` (14 chars, clear)
- ❌ `Prices are loaded into the database through yfinance` (51 chars, verbose)

---

## Questions Before Extending?

If you're about to add a new project or modify the steering system, check:
- **Is my change reflected in the root project index?** (New project? Add a row.)
- **Would a future Claude understand this without asking?** (If not, expand it.)
- **Is my steering doc < 150 lines?** (If not, cut prose; use bullet points + file paths instead.)
- **Did I update the steering doc in the same commit that changed the system?** (If not, do it now.)
- **Did I abbreviate aggressively?** (Every sentence should be scannable in < 2 seconds. Use tables + one-liners.)
