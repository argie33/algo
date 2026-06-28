import { MemoryRouter } from "react-router-dom";
import { Suspense } from "react";

/**
 * Test wrapper that provides Router context
 * Safely handles cases where AuthProvider might be mocked
 * Use this to wrap test components that use Navigate or might use useAuth()
 */
export function TestWrapper({ children }) {
  return (
    <MemoryRouter>
      <Suspense fallback={<div>Loading...</div>}>{children}</Suspense>
    </MemoryRouter>
  );
}

/**
 * Test render helper - automatically wraps components in TestWrapper (Router only)
 * Safe for use with mocked AuthContext
 * Usage: renderWithProviders(<Component />)
 */
export function renderWithProviders(component, options = {}) {
  const { render } = require("@testing-library/react");
  return render(<TestWrapper>{component}</TestWrapper>, options);
}

/**
 * Test render helper - wraps components in Router + Auth contexts
 * Only use when AuthProvider is actually available (not mocked)
 * Usage: renderWithAuth(<Component />)
 */
export function renderWithAuth(component, options = {}) {
  const { render } = require("@testing-library/react");
  let AuthProvider;
  try {
    AuthProvider = require("../../../contexts/AuthContext").AuthProvider;
  } catch (e) {
    // AuthProvider not available, fall back to renderWithProviders
    return renderWithProviders(component, options);
  }

  return render(
    <MemoryRouter>
      <AuthProvider>{component}</AuthProvider>
    </MemoryRouter>,
    options
  );
}
