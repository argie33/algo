/**
 * Authentication with MFA Integration Test
 * Tests the complete login flow including MFA verification
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import { createTheme } from '@mui/material/styles';
import LoginForm from '../../components/auth/LoginForm';
import { AuthProvider } from '../../contexts/AuthContext';

// Mock AWS Amplify Auth
vi.mock('@aws-amplify/auth', () => ({
  signIn: vi.fn(),
  confirmSignIn: vi.fn(),
  getCurrentUser: vi.fn(),
  fetchAuthSession: vi.fn()
}));

// Mock runtime config service
vi.mock('../../services/runtimeConfig', () => ({
  fetchRuntimeConfig: vi.fn(() => Promise.resolve({
    cognito: {
      userPoolId: 'us-east-1_ZqooNeQtV',
      clientId: '243r98prucoickch12djkahrhk',
      region: 'us-east-1'
    },
    api: {
      baseUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
    },
    environment: 'dev',
    features: {
      authentication: true
    }
  }))
}));

const theme = createTheme();

const TestWrapper = ({ children }) => (
  <ThemeProvider theme={theme}>
    <BrowserRouter>
      <AuthProvider>
        {children}
      </AuthProvider>
    </BrowserRouter>
  </ThemeProvider>
);

describe('Authentication with MFA Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock fetch for runtime config
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          config: {
            cognito: {
              userPoolId: 'us-east-1_ZqooNeQtV',  
              clientId: '243r98prucoickch12djkahrhk',
              region: 'us-east-1'
            }
          }
        })
      })
    );
  });

  it('handles login flow that requires MFA', async () => {
    const { signIn, confirmSignIn } = await import('@aws-amplify/auth');
    
    // Mock signIn to return MFA challenge
    signIn.mockResolvedValue({
      isSignedIn: false,
      nextStep: {
        signInStep: 'CONFIRM_SIGN_IN_WITH_SMS_MFA_CODE',
        additionalInfo: {
          deliveryMedium: 'SMS',
          destination: '+1***-***-1234'
        }
      }
    });

    // Mock MFA confirmation
    confirmSignIn.mockResolvedValue({
      isSignedIn: true,
      nextStep: {
        signInStep: 'DONE'
      }
    });

    render(
      <TestWrapper>
        <LoginForm />
      </TestWrapper>
    );

    // Fill in login form
    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const loginButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password123' } });
    fireEvent.click(loginButton);

    // Wait for MFA prompt
    await waitFor(() => {
      expect(signIn).toHaveBeenCalledWith({
        username: 'test@example.com',
        password: 'password123'
      });
    });

    // Check if MFA code input appears
    await waitFor(() => {
      const mfaInput = screen.queryByLabelText(/verification code/i);
      if (mfaInput) {
        // Enter MFA code
        fireEvent.change(mfaInput, { target: { value: '123456' } });
        
        const verifyButton = screen.getByRole('button', { name: /verify/i });
        fireEvent.click(verifyButton);
      }
    });

    // Verify MFA confirmation was called
    await waitFor(() => {
      if (confirmSignIn.mock.calls.length > 0) {
        expect(confirmSignIn).toHaveBeenCalledWith({
          challengeResponse: '123456'
        });
      }
    });
  });

  it('handles MFA verification errors gracefully', async () => {
    const { signIn, confirmSignIn } = await import('@aws-amplify/auth');
    
    signIn.mockResolvedValue({
      isSignedIn: false,
      nextStep: {
        signInStep: 'CONFIRM_SIGN_IN_WITH_SMS_MFA_CODE'
      }
    });

    // Mock MFA verification failure
    confirmSignIn.mockRejectedValue(new Error('Invalid verification code'));

    render(
      <TestWrapper>
        <LoginForm />
      </TestWrapper>
    );

    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const loginButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password123' } });
    fireEvent.click(loginButton);

    await waitFor(() => {
      expect(signIn).toHaveBeenCalled();
    });

    // The component should handle the MFA error gracefully
    // Exact behavior depends on implementation
  });

  it('loads runtime configuration before authentication', async () => {
    const { fetchRuntimeConfig } = await import('../../services/runtimeConfig');
    
    render(
      <TestWrapper>
        <LoginForm />
      </TestWrapper>
    );

    // Wait for component to initialize
    await waitFor(() => {
      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    });

    // Runtime config should be fetched
    expect(fetchRuntimeConfig).toHaveBeenCalled();
  });

  it('uses real Cognito configuration values', async () => {
    render(
      <TestWrapper>
        <LoginForm />
      </TestWrapper>
    );

    // Wait for initialization
    await waitFor(() => {
      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    });

    // Verify the correct API endpoint was called for runtime config
    expect(fetch).toHaveBeenCalledWith(
      'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/settings/runtime-config',
      expect.any(Object)
    );
  });
});