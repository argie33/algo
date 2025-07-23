/**
 * Settings Component Unit Tests
 * Tests the actual Settings.jsx component functionality
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import { createTheme } from '@mui/material/styles';
import Settings from '../../../pages/Settings';
import { AuthContext } from '../../../contexts/AuthContext';

// Mock API service
vi.mock('../../../services/api', () => ({
  getApiConfig: () => ({ apiUrl: 'https://test-api.com' })
}));

// Mock SettingsApiKeys component
vi.mock('../../../pages/SettingsApiKeys', () => ({
  default: () => <div data-testid="api-keys-component">API Keys Settings</div>
}));

const theme = createTheme();

const TestWrapper = ({ children, isAuthenticated = true }) => {
  const mockAuthValue = {
    user: isAuthenticated ? { email: 'test@example.com' } : null,
    isAuthenticated,
    isLoading: false,
    logout: vi.fn(),
    checkAuthState: vi.fn(),
    retryCount: 0,
    maxRetries: 3
  };

  return (
    <ThemeProvider theme={theme}>
      <AuthContext.Provider value={mockAuthValue}>
        <BrowserRouter>
          {children}
        </BrowserRouter>
      </AuthContext.Provider>
    </ThemeProvider>
  );
};

describe('Settings Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the settings tabs', () => {
    render(
      <TestWrapper>
        <Settings />
      </TestWrapper>
    );

    // Check for tab labels based on actual Settings.jsx
    expect(screen.getByText('Profile')).toBeInTheDocument();
    expect(screen.getByText('API Keys')).toBeInTheDocument();
    expect(screen.getByText('Notifications')).toBeInTheDocument();
    expect(screen.getByText('Appearance')).toBeInTheDocument();
    expect(screen.getByText('Security')).toBeInTheDocument();
  });

  it('switches between tabs', async () => {
    render(
      <TestWrapper>
        <Settings />
      </TestWrapper>
    );

    const apiKeysTab = screen.getByText('API Keys');
    fireEvent.click(apiKeysTab);

    await waitFor(() => {
      expect(screen.getByTestId('api-keys-component')).toBeInTheDocument();
    });
  });

  it('shows loading state when authentication is loading', () => {
    const mockAuthValue = {
      user: null,
      isAuthenticated: false,
      isLoading: true,
      logout: vi.fn(),
      checkAuthState: vi.fn(),
      retryCount: 0,
      maxRetries: 3
    };

    render(
      <ThemeProvider theme={theme}>
        <AuthContext.Provider value={mockAuthValue}>
          <BrowserRouter>
            <Settings />
          </BrowserRouter>
        </AuthContext.Provider>
      </ThemeProvider>
    );

    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('handles unauthenticated state appropriately', () => {
    render(
      <TestWrapper isAuthenticated={false}>
        <Settings />
      </TestWrapper>
    );

    // Should still render the component structure
    expect(screen.getByText('Profile')).toBeInTheDocument();
  });

  it('maintains state when switching tabs', async () => {
    render(
      <TestWrapper>
        <Settings />
      </TestWrapper>
    );

    // Switch to API Keys tab
    const apiKeysTab = screen.getByText('API Keys');
    fireEvent.click(apiKeysTab);

    await waitFor(() => {
      expect(screen.getByTestId('api-keys-component')).toBeInTheDocument();
    });

    // Switch back to Profile tab
    const profileTab = screen.getByText('Profile');
    fireEvent.click(profileTab);

    // Should switch back without issues
    expect(profileTab).toHaveAttribute('aria-selected', 'true');
  });
});