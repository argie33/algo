import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../../../contexts/AuthContext';

/**
 * Test wrapper that provides both Router and Auth contexts
 * Use this to wrap test components that use useAuth() or Navigate
 */
export function TestWrapper({ children }) {
  return (
    <MemoryRouter>
      <AuthProvider>
        {children}
      </AuthProvider>
    </MemoryRouter>
  );
}

/**
 * Test render helper - automatically wraps components in TestWrapper
 * Usage: renderWithProviders(<Component />)
 */
export function renderWithProviders(component, options = {}) {
  const { render } = require('@testing-library/react');

  return render(
    <TestWrapper>
      {component}
    </TestWrapper>,
    options
  );
}
