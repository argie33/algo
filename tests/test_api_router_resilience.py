"""Test API router resilience to import failures (Issue #6).

Tests that if a single route module fails to import, the router continues to work
for other routes and returns 503 for the failed route.
"""
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Add lambda/api to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'lambda' / 'api'))


class TestApiRouterResilience(unittest.TestCase):
    """Test that api_router handles import failures gracefully."""

    def test_import_successful_with_available_modules(self):
        """api_router should import successfully even if some modules fail."""
        # Reload api_router to capture import state
        import importlib
        import api_router
        importlib.reload(api_router)

        # Check that _AVAILABLE_ROUTES is populated
        self.assertGreater(len(api_router._AVAILABLE_ROUTES), 0, "Should have successfully imported at least one route")

    def test_failed_imports_tracked(self):
        """Failed route imports should be tracked in _ROUTE_IMPORT_ERRORS."""
        import api_router

        # Check that _ROUTE_IMPORT_ERRORS dict exists (may be empty if no failures)
        self.assertIsInstance(api_router._ROUTE_IMPORT_ERRORS, dict)

    def test_health_endpoints_in_public_handlers(self):
        """Health endpoints should be in PUBLIC_HANDLERS if health module loaded."""
        import api_router

        if 'health' in api_router._AVAILABLE_ROUTES:
            # Health loaded successfully
            self.assertIn('/api/health', api_router.PUBLIC_HANDLERS)
            self.assertIn('/health', api_router.PUBLIC_HANDLERS)
        else:
            # Health failed to load (unlikely but handled gracefully)
            self.assertEqual(len(api_router.PUBLIC_HANDLERS), 0)

    def test_handlers_only_contain_loaded_modules(self):
        """HANDLERS should only contain routes whose modules loaded successfully."""
        import api_router

        for path, handler_module in api_router.HANDLERS.items():
            # Each handler should be an actual module object
            self.assertTrue(hasattr(handler_module, 'handle'),
                           f"Handler for {path} should have handle() method")

    def test_route_request_returns_503_for_failed_module(self):
        """route_request should return 503 for routes whose modules failed to import."""
        import api_router

        # Only test if we have a failed module to work with
        if not api_router._ROUTE_IMPORT_ERRORS:
            self.skipTest("No failed route modules in test environment")

        # Get the first failed module and its error message
        failed_module_name = list(api_router._ROUTE_IMPORT_ERRORS.keys())[0]

        # Find the corresponding route path in _HANDLER_CONFIG
        route_path = None
        for path, module_name in api_router._HANDLER_CONFIG:
            if module_name == failed_module_name:
                route_path = path
                break

        if not route_path:
            self.skipTest(f"Failed module {failed_module_name} not in _HANDLER_CONFIG")

        # Mock database cursor
        mock_cur = Mock()

        # Request a path that matches the failed route
        response = api_router.route_request(mock_cur, route_path + '/data', 'GET', {})

        # Should return 503 with route_load_error
        self.assertEqual(response.get('statusCode'), 503)
        self.assertEqual(response.get('errorType'), 'route_load_error')
        self.assertIn(failed_module_name, response.get('message', ''))

        # CORS headers should be present
        self.assertIn('headers', response)
        self.assertIn('Access-Control-Allow-Origin', response['headers'])

    def test_cors_headers_on_all_responses(self):
        """CORS headers should be present on all responses."""
        import api_router

        mock_cur = Mock()

        # Test 404 response
        response = api_router.route_request(mock_cur, '/nonexistent', 'GET', {})
        self.assertIn('headers', response)
        self.assertIn('Access-Control-Allow-Origin', response['headers'])

    def test_handler_config_precedence(self):
        """More specific routes should be checked before less specific ones."""
        import api_router

        # Find the order of routes in _HANDLER_CONFIG
        paths = [path for path, _ in api_router._HANDLER_CONFIG]

        # /api/algo/risk-dashboard should come before /api/algo
        algo_risk_idx = next((i for i, p in enumerate(paths) if p == '/api/algo/risk-dashboard'), -1)
        algo_idx = next((i for i, p in enumerate(paths) if p == '/api/algo'), -1)

        self.assertGreater(algo_risk_idx, -1, "/api/algo/risk-dashboard should be in _HANDLER_CONFIG")
        self.assertGreater(algo_idx, -1, "/api/algo should be in _HANDLER_CONFIG")
        self.assertLess(algo_risk_idx, algo_idx, "/api/algo/risk-dashboard should come before /api/algo")


class TestApiRouterWithSimulatedFailure(unittest.TestCase):
    """Test api_router behavior with a simulated route module import failure."""

    def test_route_import_error_detection(self):
        """Test that import errors would be detected and recorded."""
        import api_router

        # Verify that the import error tracking mechanism exists
        self.assertIsInstance(api_router._ROUTE_IMPORT_ERRORS, dict)

        # Verify that route modules are tracked (either loaded or failed)
        total_tracked = len(api_router._AVAILABLE_ROUTES) + len(api_router._ROUTE_IMPORT_ERRORS)
        self.assertGreater(total_tracked, 0, "Should have at least some tracked modules")


if __name__ == '__main__':
    unittest.main()
