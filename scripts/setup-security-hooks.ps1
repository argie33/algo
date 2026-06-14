# Install security pre-commit hooks for Windows PowerShell
# Usage: .\scripts\setup-security-hooks.ps1

param(
    [switch]$Force = $false
)

$GIT_ROOT = git rev-parse --show-toplevel 2>$null
if (-not $GIT_ROOT) {
    Write-Host "❌ Not in a git repository" -ForegroundColor Red
    exit 1
}

$HOOKS_DIR = Join-Path $GIT_ROOT ".git\hooks"

Write-Host "Installing security pre-commit hook..." -ForegroundColor Cyan

# Create hook content
$HOOK_CONTENT = @'
#!/bin/bash
# Security-focused pre-commit hook
# Prevents commits with:
# - DEV_BYPASS_AUTH, CORS wildcard, SQL injection, hardcoded secrets

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "[SECURITY] Running pre-commit security checks..."

STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.py$' || true)

if [ -z "$STAGED_FILES" ]; then
    exit 0
fi

ERRORS=0

# Check 1: DEV_BYPASS_AUTH
if echo "$STAGED_FILES" | xargs grep -l "DEV_BYPASS_AUTH.*true" 2>/dev/null || false; then
    echo -e "${RED}❌ DEV_BYPASS_AUTH=true is a CRITICAL security vulnerability${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check 2: CORS wildcard
if echo "$STAGED_FILES" | xargs grep -l "Access-Control-Allow-Origin.*\*" 2>/dev/null || false; then
    echo -e "${RED}❌ CORS wildcard allows any origin - use whitelist${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check 3: SQL injection (f-string execute)
SQL_ISSUES=$(
    echo "$STAGED_FILES" | grep -v migrations | xargs grep -n 'execute(f"' 2>/dev/null | \
    grep -E "SELECT|INSERT|UPDATE|DELETE" | \
    grep -v "assert_safe_table\|psycopg2.sql\|# SAFE:" || true
)
if [ -n "$SQL_ISSUES" ]; then
    echo -e "${RED}❌ SQL injection pattern (f-string execute):${NC}"
    echo "$SQL_ISSUES" | head -3 | sed 's/^/   /'
    ERRORS=$((ERRORS + 1))
fi

# Check 4: subprocess shell=True
if echo "$STAGED_FILES" | xargs grep -l "shell.*True\|Popen.*shell" 2>/dev/null || false; then
    echo -e "${RED}❌ subprocess shell=True is a command injection risk${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check 5: eval/exec/compile
if echo "$STAGED_FILES" | xargs grep -E "^[[:space:]]*(eval|exec|compile)\(" 2>/dev/null || false; then
    echo -e "${RED}❌ eval/exec/compile are security risks${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check 6: Hardcoded secrets (warning only)
CREDS=$(
    echo "$STAGED_FILES" | xargs grep -n -E "password\s*=\s*['\"]|secret\s*=\s*['\"]" 2>/dev/null | \
    grep -v "get_password\|get_secret\|credential_manager\|test" || true
)
if [ -n "$CREDS" ]; then
    echo -e "${YELLOW}⚠ Possible hardcoded credentials detected${NC}"
fi

echo ""
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✅ Security checks passed${NC}"
    exit 0
else
    echo -e "${RED}❌ $ERRORS security check(s) failed${NC}"
    echo "Fix the issues above before committing."
    exit 1
fi
'@

# Write hook file
$HOOK_PATH = Join-Path $HOOKS_DIR "pre-commit"

if (Test-Path $HOOK_PATH) {
    if (-not $Force) {
        Write-Host "Pre-commit hook already exists at $HOOK_PATH" -ForegroundColor Yellow
        $response = Read-Host "Overwrite? (y/N)"
        if ($response -ne 'y') {
            Write-Host "Cancelled" -ForegroundColor Yellow
            exit 0
        }
    }
}

$HOOK_CONTENT | Out-File -FilePath $HOOK_PATH -Encoding UTF8 -Force

# Make executable on Unix-like systems
if ($IsLinux -or $IsMacOS) {
    chmod +x $HOOK_PATH
}

Write-Host "✅ Security hook installed at $HOOK_PATH" -ForegroundColor Green
Write-Host ""
Write-Host "The hook will run automatically on 'git commit' and block:" -ForegroundColor Cyan
Write-Host "  • DEV_BYPASS_AUTH=true (authentication bypass)" -ForegroundColor Gray
Write-Host "  • CORS wildcard '*' (CSRF vulnerability)" -ForegroundColor Gray
Write-Host "  • SQL injection f-string patterns" -ForegroundColor Gray
Write-Host "  • subprocess with shell=True" -ForegroundColor Gray
Write-Host "  • eval/exec/compile statements" -ForegroundColor Gray
Write-Host ""
Write-Host "To bypass (NOT RECOMMENDED): git commit --no-verify" -ForegroundColor Yellow
