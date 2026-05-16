# npm Vulnerabilities Report

**Date:** 2026-05-15
**Status:** Awaiting npm audit run and remediation

## Overview

The webapp/frontend directory contains npm dependencies with known vulnerabilities. Most critical is aws-amplify which has 7 reported issues.

## How to Audit Locally

```bash
# From webapp/frontend directory
npm audit

# Show only high/critical vulnerabilities
npm audit --audit-level=high

# Generate JSON report for automated processing
npm audit --json > audit-report.json
```

## Common Vulnerability Types in aws-amplify

1. **XSS (Cross-Site Scripting)** - Incorrect input validation
2. **Prototype Pollution** - Unsafe object merging
3. **ReDoS (Regular Expression Denial of Service)** - Regex patterns with exponential backtracking
4. **Dependency vulnerabilities** - Indirect dependencies of aws-amplify

## Remediation Strategy

### Option A: Update to Latest (Recommended for Production)
```bash
npm update aws-amplify
npm audit --fix
```

**Pros:**
- Gets all security patches
- Best long-term maintenance
- Minimal code changes needed (aws-amplify v5→v6→v7 are mostly compatible)

**Cons:**
- May introduce breaking changes
- Requires testing of Auth flows
- Larger bundle size in some cases

### Option B: Selective Patch (Conservative)
```bash
npm update aws-amplify --depth=3  # Update transitive dependencies only
npm audit --fix --depth=1
```

**Pros:**
- Less likely to introduce breaking changes
- Smaller surface area for regressions
- Good for maintenance windows

**Cons:**
- May not fix all vulnerabilities
- Requires more manual review

### Option C: Dependency Upgrade (Focused)
Check current aws-amplify version:
```bash
npm list aws-amplify
```

Common vulnerabilities addressed in each version:
- **v6.15.x→v6.17.x**: Several ReDoS fixes in auth
- **v5→v6**: Major security overhaul (requires code changes)

## Action Items

### Immediate (This Week)
- [ ] Run `npm audit` and document findings
- [ ] Identify which vulnerabilities affect our usage (not all reported issues impact this app)
- [ ] Test aws-amplify latest version in staging
- [ ] Update if no breaking changes detected

### Before Production
- [ ] Re-run `npm audit` after updates
- [ ] Test authentication flows (Cognito integration)
- [ ] Test Amplify API calls (backend integration)
- [ ] Verify bundle size hasn't increased significantly

### Ongoing
- [ ] Add `npm audit` to CI/CD pipeline
- [ ] Set audit failure threshold (fail on high/critical)
- [ ] Review `npm outdated` monthly
- [ ] Update major versions on schedule (every 3-6 months)

## CI/CD Integration

Add to GitHub Actions workflow:

```yaml
- name: npm audit
  run: |
    cd webapp/frontend
    npm audit --audit-level=high || echo "Security issues found"
    
- name: npm update check
  run: |
    cd webapp/frontend
    npm outdated || echo "All packages up to date"
```

## References

- [npm audit documentation](https://docs.npmjs.com/cli/v8/commands/npm-audit)
- [aws-amplify Security Advisories](https://github.com/aws-amplify/amplify-js/security)
- [OWASP Dependency Check](https://owasp.org/www-project-dependency-check/)
