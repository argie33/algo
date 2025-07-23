/**
 * Complete MFA Authentication Flow Integration Test
 * Tests the full login flow including MFA challenges
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
  fetchAuthSession: vi.fn(),
  signOut: vi.fn(),
  signUp: vi.fn(),
  confirmSignUp: vi.fn(),
  resetPassword: vi.fn(),
  confirmResetPassword: vi.fn()
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
  })),
  initializeRuntimeConfig: vi.fn(() => Promise.resolve(true)),
  getRuntimeConfig: vi.fn(() => null),
  clearRuntimeConfig: vi.fn()
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

describe('Complete MFA Authentication Flow Integration', () => {
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
            },
            api: {
              baseUrl: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
            },
            environment: 'dev'
          }
        })
      })
    );
  });

  it('handles complete SMS MFA login flow', async () => {
    const { signIn, confirmSignIn } = await import('@aws-amplify/auth');
    
    // Mock signIn to return SMS MFA challenge
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

    // Mock successful MFA confirmation
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

    // Step 1: Fill in login form
    const emailInput = screen.getByLabelText(/username or email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const loginButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password123' } });
    fireEvent.click(loginButton);

    // Step 2: Verify login attempt
    await waitFor(() => {
      expect(signIn).toHaveBeenCalledWith({
        username: 'test@example.com',
        password: 'password123'
      });
    });

    // Step 3: MFA challenge should appear
    await waitFor(() => {
      expect(screen.getByText('SMS Verification')).toBeInTheDocument();
      expect(screen.getByText(/Enter the verification code sent to/)).toBeInTheDocument();
    });

    // Step 4: Enter MFA code
    const mfaInput = screen.getByLabelText(/verification code/i);
    const verifyButton = screen.getByRole('button', { name: /verify code/i });

    fireEvent.change(mfaInput, { target: { value: '123456' } });
    
    await waitFor(() => {
      expect(verifyButton).not.toBeDisabled();
    });

    fireEvent.click(verifyButton);

    // Step 5: Verify MFA confirmation
    await waitFor(() => {
      expect(confirmSignIn).toHaveBeenCalledWith({
        challengeResponse: '123456'
      });
    });

    // Step 6: Login should complete successfully
    // The component should handle successful authentication
  }, 10000);

  it('handles complete TOTP MFA login flow', async () => {
    const { signIn, confirmSignIn } = await import('@aws-amplify/auth');
    
    // Mock signIn to return TOTP MFA challenge
    signIn.mockResolvedValue({
      isSignedIn: false,
      nextStep: {
        signInStep: 'CONFIRM_SIGN_IN_WITH_TOTP_MFA_CODE'
      }
    });

    // Mock successful MFA confirmation
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

    // Step 1: Fill in login form
    const emailInput = screen.getByLabelText(/username or email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const loginButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password123' } });
    fireEvent.click(loginButton);

    // Step 2: TOTP MFA challenge should appear
    await waitFor(() => {
      expect(screen.getByText('Authenticator App')).toBeInTheDocument();
      expect(screen.getByText(/Enter the code from your authenticator app/)).toBeInTheDocument();
    });

    // Step 3: Enter TOTP code
    const mfaInput = screen.getByLabelText(/verification code/i);
    const verifyButton = screen.getByRole('button', { name: /verify code/i });

    fireEvent.change(mfaInput, { target: { value: '654321' } });
    fireEvent.click(verifyButton);

    // Step 4: Verify TOTP confirmation
    await waitFor(() => {
      expect(confirmSignIn).toHaveBeenCalledWith({
        challengeResponse: '654321'
      });
    });
  });

  it('handles MFA verification errors gracefully', async () => {
    const { signIn, confirmSignIn } = await import('@aws-amplify/auth');
    
    signIn.mockResolvedValue({
      isSignedIn: false,
      nextStep: {
        signInStep: 'CONFIRM_SIGN_IN_WITH_SMS_MFA_CODE',
        additionalInfo: {
          destination: '+1***-***-1234'
        }
      }
    });

    // Mock MFA verification failure
    confirmSignIn.mockRejectedValue(new Error('Invalid verification code'));

    render(
      <TestWrapper>
        <LoginForm />
      </TestWrapper>
    );

    // Login and trigger MFA challenge
    const emailInput = screen.getByLabelText(/username or email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const loginButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password123' } });
    fireEvent.click(loginButton);

    // Wait for MFA challenge
    await waitFor(() => {
      expect(screen.getByText('SMS Verification')).toBeInTheDocument();
    });

    // Enter wrong code
    const mfaInput = screen.getByLabelText(/verification code/i);
    const verifyButton = screen.getByRole('button', { name: /verify code/i });

    fireEvent.change(mfaInput, { target: { value: '000000' } });
    fireEvent.click(verifyButton);

    // Should show error
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText(/verification failed/i)).toBeInTheDocument();
    });
  });

  it('allows canceling MFA challenge', async () => {
    const { signIn } = await import('@aws-amplify/auth');
    
    signIn.mockResolvedValue({
      isSignedIn: false,
      nextStep: {
        signInStep: 'CONFIRM_SIGN_IN_WITH_SMS_MFA_CODE',
        additionalInfo: {
          destination: '+1***-***-1234'
        }
      }
    });

    render(
      <TestWrapper>
        <LoginForm />
      </TestWrapper>
    );

    // Login and trigger MFA challenge
    const emailInput = screen.getByLabelText(/username or email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const loginButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password123' } });
    fireEvent.click(loginButton);

    // Wait for MFA challenge
    await waitFor(() => {
      expect(screen.getByText('SMS Verification')).toBeInTheDocument();
    });

    // Cancel MFA
    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    fireEvent.click(cancelButton);

    // Should return to login form
    await waitFor(() => {
      expect(screen.getByText('Sign In')).toBeInTheDocument();
      expect(screen.getByLabelText(/username or email/i)).toBeInTheDocument();
    });
  });

  it('validates runtime configuration during authentication', async () => {
    render(
      <TestWrapper>
        <LoginForm />
      </TestWrapper>
    );

    // Wait for component to initialize
    await waitFor(() => {
      expect(screen.getByLabelText(/username or email/i)).toBeInTheDocument();
    });

    // Verify the correct API endpoint was called for runtime config
    expect(fetch).toHaveBeenCalledWith(
      'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/api/settings/runtime-config',
      expect.objectContaining({
        method: 'GET',
        credentials: 'omit'
      })
    );
  });
});