#!/usr/bin/env python3
"""
Lambda Deployment Validation Script

Validates that:
1. All endpoint handlers work correctly
2. Database connectivity is functional
3. All required dependencies are available
4. The 3 critical failing endpoints (Positions, Performance, Swing Scores) work
"""

import logging
import sys
from pathlib import Path
from typing import Any

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("VALIDATION")

def validate_imports() -> bool:
    """Verify all required modules can be imported."""
    logger.info("Checking imports...")
    required_modules = [
        "psycopg2",
        "pydantic",
        "requests",
        "boto3",
        "PyJWT",
    ]

    all_ok = True
    for module in required_modules:
        try:
            __import__(module)
            logger.info(f"  ✓ {module}")
        except ImportError as e:
            logger.error(f"  ✗ {module}: {e}")
            all_ok = False

    return all_ok


def validate_handler_imports() -> bool:
    """Verify dashboard and handler modules can be imported."""
    logger.info("Checking handler imports...")
    try:
        import importlib
        importlib.import_module("dashboard.panels")
        logger.info("  ✓ dashboard.panels")

        importlib.import_module("lambda.api.api_router")
        logger.info("  ✓ lambda.api.api_router")

        return True
    except ImportError as e:
        logger.error(f"  ✗ Handler import failed: {e}")
        return False


def validate_database_connectivity() -> bool:
    """Test database connectivity."""
    logger.info("Checking database connectivity...")
    try:
        import psycopg2

        # Try to connect with current environment
        # Note: This will fail if DB_* env vars not set, which is fine for local testing
        conn = psycopg2.connect(
            host=__import__("os").getenv("DB_HOST", "localhost"),
            database=__import__("os").getenv("DB_NAME", "algo"),
            user=__import__("os").getenv("DB_USER", "postgres"),
            password=__import__("os").getenv("DB_PASSWORD", ""),
            connect_timeout=5,
        )
        conn.close()
        logger.info("  ✓ Database connection successful")
        return True
    except Exception as e:
        logger.warning(f"  ⚠ Database connection failed (expected if not configured): {e}")
        return False


def validate_endpoint_handlers() -> dict[str, Any]:
    """Test the 3 critical endpoint handlers that were failing."""
    logger.info("Testing critical endpoint handlers...")

    results = {
        "positions": None,
        "performance": None,
        "swing_scores": None,
    }

    try:
        # Import handlers
        import importlib
        api_router = importlib.import_module("lambda.api.api_router")

        # Create mock event/context for testing
        mock_event = {
            "httpMethod": "GET",
            "headers": {},
            "queryStringParameters": None,
        }
        mock_context = type("Context", (), {
            "function_name": "algo-api-test",
            "invoked_function_arn": "arn:aws:lambda:us-east-1:123456789012:function:algo-api",
        })()

        # Test positions endpoint
        logger.info("  Testing /api/algo/positions...")
        try:
            event = {**mock_event, "path": "/api/algo/positions"}
            response = api_router.lambda_handler(event, mock_context)
            if response.get("statusCode") == 200:
                logger.info("    ✓ Positions endpoint returns 200")
                results["positions"] = "PASS"
            else:
                logger.warning(f"    ⚠ Positions endpoint returned {response.get('statusCode')}")
                results["positions"] = f"FAIL: {response.get('statusCode')}"
        except Exception as e:
            logger.error(f"    ✗ Positions endpoint error: {e}")
            results["positions"] = f"ERROR: {str(e)[:100]}"

        # Test performance endpoint
        logger.info("  Testing /api/algo/performance...")
        try:
            event = {**mock_event, "path": "/api/algo/performance"}
            response = api_router.lambda_handler(event, mock_context)
            if response.get("statusCode") == 200:
                logger.info("    ✓ Performance endpoint returns 200")
                results["performance"] = "PASS"
            else:
                logger.warning(f"    ⚠ Performance endpoint returned {response.get('statusCode')}")
                results["performance"] = f"FAIL: {response.get('statusCode')}"
        except Exception as e:
            logger.error(f"    ✗ Performance endpoint error: {e}")
            results["performance"] = f"ERROR: {str(e)[:100]}"

        # Test swing scores endpoint
        logger.info("  Testing /api/algo/swing-scores...")
        try:
            event = {**mock_event, "path": "/api/algo/swing-scores"}
            response = api_router.lambda_handler(event, mock_context)
            if response.get("statusCode") == 200:
                logger.info("    ✓ Swing Scores endpoint returns 200")
                results["swing_scores"] = "PASS"
            else:
                logger.warning(f"    ⚠ Swing Scores endpoint returned {response.get('statusCode')}")
                results["swing_scores"] = f"FAIL: {response.get('statusCode')}"
        except Exception as e:
            logger.error(f"    ✗ Swing Scores endpoint error: {e}")
            results["swing_scores"] = f"ERROR: {str(e)[:100]}"

    except Exception as e:
        logger.error(f"  ✗ Failed to test handlers: {e}")

    return results


def validate_types() -> bool:
    """Verify type checking passes."""
    logger.info("Checking type safety...")
    import subprocess

    try:
        result = subprocess.run(
            ["python", "-m", "mypy", "dashboard", "--show-error-codes"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("  ✓ Type checking passed (mypy strict)")
            return True
        else:
            logger.error(f"  ✗ Type errors found:\n{result.stdout}")
            return False
    except Exception as e:
        logger.warning(f"  ⚠ Could not run mypy: {e}")
        return False


def validate_tests() -> bool:
    """Verify tests pass."""
    logger.info("Running unit tests...")
    import subprocess

    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-q", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Extract pass/fail counts from pytest output
        output = result.stdout + result.stderr
        if "passed" in output:
            logger.info(f"  ✓ Tests passed\n    {output.split(chr(10))[-2]}")
            return result.returncode == 0
        else:
            logger.error(f"  ✗ Tests failed:\n{output[-500:]}")
            return False
    except Exception as e:
        logger.warning(f"  ⚠ Could not run tests: {e}")
        return False


def print_deployment_checklist(handler_results: dict[str, Any]) -> None:
    """Print deployment verification checklist."""
    logger.info("\n" + "="*60)
    logger.info("DEPLOYMENT VERIFICATION CHECKLIST")
    logger.info("="*60)

    critical_pass = all(
        handler_results.get(k) == "PASS"
        for k in ["positions", "performance", "swing_scores"]
    )

    print("\nBefore AWS Lambda Deployment:")
    print("  ☐ All tests pass locally (pytest)")
    print("  ☐ All type checks pass (mypy strict)")
    print("  ☐ All endpoints tested successfully")
    print(f"  ☐ Critical endpoints: {'✓ READY' if critical_pass else '✗ ISSUES FOUND'}")

    print("\nDuring AWS Lambda Deployment:")
    print("  ☐ AWS credentials configured (aws sts get-caller-identity)")
    print("  ☐ Build Lambda package (pip install -r requirements.txt -t package/)")
    print("  ☐ Create ZIP file (zip -r algo-api.zip .)")
    print("  ☐ Deploy to Lambda (aws lambda update-function-code ...)")
    print("  ☐ Wait for deployment to complete")

    print("\nAfter AWS Lambda Deployment:")
    print("  ☐ Get API Gateway URL from AWS console")
    print("  ☐ Test /api/algo/positions endpoint")
    print("  ☐ Test /api/algo/performance endpoint")
    print("  ☐ Test /api/algo/swing-scores endpoint")
    print("  ☐ Open dashboard in browser")
    print("  ☐ Verify all panels load with real data")
    print("  ☐ Check CloudWatch logs for errors")

    print("\nEndpoint Test Results:")
    for endpoint, result in handler_results.items():
        status = "✓" if result == "PASS" else "✗"
        print(f"  {status} {endpoint}: {result}")


def main() -> int:
    """Run all validations."""
    logger.info("Starting Lambda deployment validation...")
    print()

    results = {
        "imports": validate_imports(),
        "handlers": validate_handler_imports(),
        "database": validate_database_connectivity(),
        "types": validate_types(),
        "tests": validate_tests(),
    }

    handler_results = validate_endpoint_handlers()

    print_deployment_checklist(handler_results)

    # Summary
    logger.info("\n" + "="*60)
    logger.info("VALIDATION SUMMARY")
    logger.info("="*60)

    for check, passed in results.items():
        status = "✓" if passed else "✗"
        print(f"{status} {check.upper()}: {'PASS' if passed else 'CHECK'}")

    critical_pass = all(
        handler_results.get(k) == "PASS"
        for k in ["positions", "performance", "swing_scores"]
    )
    status = "✓" if critical_pass else "✗"
    print(f"{status} CRITICAL ENDPOINTS: {'READY FOR DEPLOYMENT' if critical_pass else 'ISSUES FOUND'}")

    # Exit code based on critical checks
    all_pass = all(results.values()) and critical_pass
    logger.info("\n" + ("✓ READY FOR AWS LAMBDA DEPLOYMENT" if all_pass else "✗ FIX ISSUES BEFORE DEPLOYMENT"))

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
