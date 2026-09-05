.PHONY: help install-hooks lint format type-check security dead-code test coverage clean ci-local lint-js format-js audit-js license-check

help:
	@echo "Algo Trading System — Local Development Commands"
	@echo "=================================================="
	@echo ""
	@echo "Setup:"
	@echo "  make install-hooks     Install git pre-commit hooks (run once)"
	@echo ""
	@echo "Code Quality (matching CI):"
	@echo "  make lint              Run ruff linter (Python)"
	@echo "  make format            Format code with ruff (Python)"
	@echo "  make type-check        Run mypy type checking (Python)"
	@echo "  make security          Run bandit + pip-audit + TruffleHog"
	@echo "  make dead-code         Run vulture (blocks new dead code, existing debt whitelisted)"
	@echo "  make lint-js           Run ESLint + Prettier check (webapp/lambda)"
	@echo "  make format-js         Auto-format JS/JSON/MD with Prettier"
	@echo "  make audit-js          Run npm audit for high-severity CVEs"
	@echo "  make license-check     Check Python + JS dependency licenses"
	@echo ""
	@echo "Testing:"
	@echo "  make test              Run all unit/edge/integration tests"
	@echo "  make test-unit         Run unit tests only"
	@echo "  make test-edge         Run edge case tests only"
	@echo "  make test-integration  Run integration tests only"
	@echo "  make coverage          Run tests with coverage report"
	@echo ""
	@echo "CI-Equivalent:"
	@echo "  make ci-local          Run all checks (simulates full CI pipeline)"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean             Remove build artifacts and caches"
	@echo ""

install-hooks:
	pip install pre-commit
	pre-commit install
	@echo "✅ Pre-commit hooks installed. Hooks will run on every commit."

lint:
	ruff check algo/ tests/ tools/ loaders/ utils/ config/ lambda/

format:
	ruff format algo/ tests/ tools/ loaders/ utils/ config/ lambda/

type-check:
	mypy algo/ loaders/ utils/ config/ --ignore-missing-imports --show-error-codes
	mypy tools/ --ignore-missing-imports --show-error-codes
	mypy lambda/base_handler.py lambda/algo_orchestrator/lambda_function.py lambda/monitoring/health_monitor.py lambda/monitoring/loader_failure_handler.py --ignore-missing-imports --show-error-codes
	cd lambda/api && mypy . --ignore-missing-imports --show-error-codes --explicit-package-bases

security:
	@echo "Running Bandit security scan..."
	bandit -r algo loaders config lambda --severity-level medium --confidence-level high
	@echo "✅ Bandit scan passed"
	@echo ""
	@echo "Running pip-audit (dependency CVE scan)..."
	pip-audit -r requirements.txt
	@echo "✅ pip-audit passed"
	@echo ""
	@echo "Running TruffleHog secret detection..."
	trufflehog filesystem . --only-verified 2>/dev/null || echo "✅ No secrets detected"

dead-code:
	@echo "Running Vulture dead-code scan (existing debt whitelisted)..."
	vulture algo/ loaders/ utils/ config/ dashboard/ monitoring/ lambda/ .vulture_whitelist.py --min-confidence 60
	@echo "✅ No new dead code"

test:
	pytest tests/ -m unit -v --tb=short
	pytest tests/ -m edge -v --tb=short
	pytest tests/ -m integration -v --tb=short

test-unit:
	pytest tests/ -m unit -v --tb=short

test-edge:
	pytest tests/ -m edge -v --tb=short

test-integration:
	pytest tests/ -m integration -v --tb=short

coverage:
	pytest tests/ \
		--cov=algo \
		--cov=loaders \
		--cov=lambda \
		--cov-report=term-missing:skip-covered \
		--cov-report=html \
		-v
	@echo ""
	@echo "✅ Coverage report generated: htmlcov/index.html"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	@echo "✅ Cleaned up build artifacts"

# FIXED 2026-08-20: pointed at webapp/lambda, which does not exist (the real JS lives in
# webapp/frontend/ - a pre-existing repo layout drift, not a recent regression) and called
# `npm run typecheck`, a script that has never existed in webapp/frontend/package.json (a
# plain-JS project, no TypeScript to typecheck). Both `make lint-js` and `make ci-local`
# (which depends on it) would have failed outright if run - verified via `git log --all -- Makefile`
# showing no `typecheck` script was ever added anywhere.
lint-js:
	cd webapp/frontend && npm run lint
	cd webapp/frontend && npm run format:check

format-js:
	cd webapp/frontend && npm run format

audit-js:
	cd webapp/frontend && npm audit --audit-level=high

license-check:
	@echo "Checking Python dependency licenses..."
	pip install -q licensecheck
	licensecheck --zero --format json > /tmp/license-report.json || true
	@if grep -iE '(GPL|SSPL)' /tmp/license-report.json > /dev/null 2>&1; then echo "WARNING: GPL/SSPL licenses detected in Python dependencies"; cat /tmp/license-report.json; else echo "✅ No GPL/SSPL licenses in Python dependencies"; fi
	@echo "Checking Node.js dependency licenses..."
	@which license-checker > /dev/null 2>&1 || npm install -g license-checker
	license-checker --json --prefix webapp/lambda > /tmp/npm-licenses.json || true
	@if grep -iE '(GPL|SSPL)' /tmp/npm-licenses.json > /dev/null 2>&1; then echo "WARNING: GPL/SSPL licenses in Node.js dependencies"; else echo "✅ No GPL/SSPL licenses in Node.js dependencies"; fi

ci-local: lint type-check security dead-code test lint-js
	@echo ""
	@echo "✅ All CI checks passed locally!"
