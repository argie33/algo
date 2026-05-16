# Dependabot Audit & Remediation Plan

**Date:** 2026-05-15  
**Total Issues:** 123 reported  
**Status:** Pending detailed analysis  

## What is Dependabot?

GitHub's automated tool that:
- Scans all dependencies (Python, npm, npm transitive, Ruby, Java, etc.)
- Identifies known vulnerabilities from security advisories
- Creates pull requests automatically for patches
- Can be configured to auto-merge low-risk updates

## Issue Breakdown (Estimated)

Based on typical projects, these 123 issues likely consist of:

**By Severity:**
- 🔴 Critical: 2-5 issues (requires immediate action)
- 🟠 High: 15-25 issues (address within sprint)
- 🟡 Medium: 40-60 issues (track for next release)
- 🔵 Low: 40-50 issues (keep in backlog)

**By Type:**
- **Transitive Dependencies** (~50%): Indirect dependencies that Dependabot found
- **Python Backend** (~30%): psycopg2, pandas, numpy, etc.
- **Frontend (npm)** (~15%): React, libraries, aws-amplify
- **Dev Tools** (~5%): pytest, linters, CI/CD tools

## How to Review in GitHub

1. Go to **Settings → Security → Dependabot**
2. View **Dependabot alerts** tab to see all issues
3. Click each alert to see:
   - Vulnerability description and CVSS score
   - Affected versions and fixed versions
   - Dependabot's recommendation
   - Auto-merge eligibility

## Remediation Strategy

### Phase 1: Critical/High (This Week)
```bash
# Show high-severity issues only
# These must be patched before production deployment
```

Steps:
1. Filter Dependabot to show **Critical + High** only
2. For each alert:
   - Read the CVE/advisory description
   - Check if we actually use the affected code
   - Test the suggested patch version
   - Merge the Dependabot PR if safe
3. Re-run tests after each merge

### Phase 2: Medium (Next Sprint)
```bash
# Medium severity issues
# Group by library and batch updates
# Example: Update all psycopg2 related at once
```

Steps:
1. Group by affected library
2. Batch update related issues (reduces merge overhead)
3. Run integration tests
4. Schedule merging (don't merge on Friday evening)

### Phase 3: Low/Info (Ongoing)
```bash
# Low severity and informational updates
# Safe to auto-merge if:
# - Patch version only (X.Y.Z → X.Y.Z+1)
# - No breaking changes in release notes
```

## Configuration

### Current Dependabot Setup (Recommended)

Add/update `.github/dependabot.yml`:

```yaml
version: 2
updates:
  # Python dependencies
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    allow:
      - dependency-type: "direct"  # Only direct deps (ignore transitive noise)
    reviewers: ["@team"]
    auto-merge: false  # Review before merging

  # Frontend npm dependencies
  - package-ecosystem: "npm"
    directory: "/webapp/frontend"
    schedule:
      interval: "weekly"
      day: "tuesday"
    allow:
      - dependency-type: "direct"
    reviewers: ["@team"]
    auto-merge: false

  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    auto-merge: true  # Safe to auto-merge GitHub Actions
```

### Strategies to Reduce Noise

1. **Focus on direct dependencies only**
   - Current: Dependabot reporting all transitive deps (123 issues)
   - Better: Filter to direct deps that we control (15-20 issues)
   - How: Add `allow: [{dependency-type: "direct"}]` in config

2. **Group related updates**
   - Current: 1 PR per dependency update
   - Better: 1 PR per library family
   - How: Dependabot → PR grouping settings

3. **Auto-merge safe updates**
   - Patch versions (X.Y.1 → X.Y.2)
   - No breaking changes
   - Passing CI tests

## Action Items

### Immediate (This Week)
- [ ] Review **Critical** Dependabot alerts (should be 0-5)
- [ ] Merge critical patches
- [ ] Update Dependabot configuration to reduce noise
- [ ] Document which libraries we actually use

### Short-term (This Sprint)
- [ ] Review **High** severity alerts
- [ ] Create plan for each High issue:
  - Can we upgrade safely?
  - Do we need this dependency?
  - Is there a workaround?
- [ ] Batch-merge safe updates
- [ ] Run full test suite

### Medium-term (Next Sprint)
- [ ] Address **Medium** severity issues
- [ ] Consider alternative libraries for high-maintenance deps
- [ ] Evaluate obsolete dependencies for removal

### Ongoing
- [ ] Review Dependabot alerts weekly
- [ ] Keep 1-2 week old alerts < 10
- [ ] Auto-merge patch versions on schedule
- [ ] Quarterly dependency health review

## Known Problematic Dependencies (Common)

These often have many reported vulnerabilities:

- **lodash** (transitive) - Very old, rarely needs update
- **axios** - XSS protection issues, update regularly
- **psycopg2** - Keep relatively current
- **numpy/pandas** - Update with caution (binary builds)

## How to Investigate an Alert

When you see a Dependabot PR:

1. **Check if affected code is used:**
   ```bash
   # Search for the vulnerable function
   grep -r "vulnerable_function_name" .
   
   # If no results, probably safe to merge
   ```

2. **Check release notes:**
   - Breaking changes?
   - New major version?
   - Compatibility notes?

3. **Run affected tests:**
   ```bash
   # For auth-related library updates
   pytest tests/test_auth.py
   
   # For API library updates
   pytest tests/test_api.py
   ```

4. **Merge or request changes:**
   - If safe: ✅ Approve + merge
   - If breaking: Request changes (ask maintainers to update)
   - If unused: Close as won't fix

## References

- [Dependabot Documentation](https://docs.github.com/en/code-security/dependabot)
- [CVE Database](https://cve.mitre.org/)
- [Snyk Vulnerability Database](https://snyk.io/vulnerability-scanner/)
- [GitHub Security Advisories](https://github.com/advisories)
