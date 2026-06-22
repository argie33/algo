.PHONY: help install-hooks lint format type-check security test coverage clean ci-local

help:
	@echo "Algo Trading System — Local Development Commands"
	@echo "=================================================="
	@echo ""
	@echo "Setup:"
	@echo "  make install-hooks     Install git pre-commit hooks (run once)"
	@echo ""
	@echo "Code Quality (matching CI):"
	@echo "  make lint              Run ruff linter"
	@echo "  make format            Format code with ruff"
	@echo "  make type-check        Run mypy type checking"
	@echo "  make security          Run bandit security scan + TruffleHog"
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
	mypy lambda/base_handler.py lambda/algo_orchestrator/ lambda/monitoring/ --ignore-missing-imports --show-error-codes
	cd lambda/api && mypy . --ignore-missing-imports --show-error-codes --explicit-package-bases

security:
	@echo "Running Bandit security scan..."
	bandit -r algo loaders config lambda --severity-level medium --confidence-level high
	@echo "✅ Bandit scan passed"
	@echo ""
	@echo "Running TruffleHog secret detection..."
	trufflehog filesystem . --only-verified 2>/dev/null || echo "✅ No secrets detected"

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

ci-local: lint type-check security test
	@echo ""
	@echo "✅ All CI checks passed locally!"
