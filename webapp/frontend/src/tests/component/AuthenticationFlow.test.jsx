import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { BrowserRouter } from 'react-router-dom';
import AuthModal from '../../components/auth/AuthModal';
import LoginForm from '../../components/auth/LoginForm';

// Mock AWS Cognito
vi.mock('aws-amplify', () => ({
  Auth: {
    signIn: vi.fn(),
    signUp: vi.fn(),
    confirmSignUp: vi.fn(),
    resendSignUp: vi.fn(),
    forgotPassword: vi.fn(),
    forgotPasswordSubmit: vi.fn(),
    signOut: vi.fn(),
    currentSession: vi.fn(),
    currentAuthenticatedUser: vi.fn(),
  },
  configure: vi.fn(),
}));

// Mock AuthContext
const mockAuthContext = {
  user: null,
  token: null,
  isAuthenticated: false,
  login: vi.fn(),
  logout: vi.fn(),
  loading: false,
  error: null,
};

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext,
  AuthProvider: ({ children }) => children,
}));

// Import after mocking
import { Auth } from 'aws-amplify';

const renderWithRouter = (component) => {
  return render(
    <BrowserRouter>
      {component}
    </BrowserRouter>
  );
};

describe('Authentication Flow Components', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('AuthModal Component', () => {
    it('should render login form by default', () => {
      renderWithRouter(<AuthModal isOpen={true} onClose={() => {}} />);
      
      expect(screen.getByText(/Sign In/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Password/i)).toBeInTheDocument();
    });

    it('should switch to signup form when requested', () => {
      renderWithRouter(<AuthModal isOpen={true} onClose={() => {}} />);
      
      fireEvent.click(screen.getByText(/Create Account/i));
      
      expect(screen.getByText(/Sign Up/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Confirm Password/i)).toBeInTheDocument();
    });

    it('should close modal when close button is clicked', () => {
      const onClose = vi.fn();
      renderWithRouter(<AuthModal isOpen={true} onClose={onClose} />);
      
      fireEvent.click(screen.getByLabelText(/Close/i));
      
      expect(onClose).toHaveBeenCalled();
    });

    it('should close modal when clicking outside', () => {
      const onClose = vi.fn();
      renderWithRouter(<AuthModal isOpen={true} onClose={onClose} />);
      
      fireEvent.click(screen.getByTestId('modal-backdrop'));
      
      expect(onClose).toHaveBeenCalled();
    });

    it('should not render when isOpen is false', () => {
      renderWithRouter(<AuthModal isOpen={false} onClose={() => {}} />);
      
      expect(screen.queryByText(/Sign In/i)).not.toBeInTheDocument();
    });
  });

  describe('LoginForm Component', () => {
    it('should render login form fields', () => {
      renderWithRouter(<LoginForm onSuccess={() => {}} />);
      
      expect(screen.getByLabelText(/Email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Password/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Sign In/i })).toBeInTheDocument();
    });

    it('should validate required fields', async () => {
      renderWithRouter(<LoginForm onSuccess={() => {}} />);
      
      fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/Email is required/i)).toBeInTheDocument();
        expect(screen.getByText(/Password is required/i)).toBeInTheDocument();
      });
    });

    it('should validate email format', async () => {
      renderWithRouter(<LoginForm onSuccess={() => {}} />);
      
      fireEvent.change(screen.getByLabelText(/Email/i), {
        target: { value: 'invalid-email' }
      });
      
      fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/Please enter a valid email/i)).toBeInTheDocument();
      });
    });

    it('should handle successful login', async () => {
      const onSuccess = vi.fn();
      const mockUser = {
        username: 'testuser',
        attributes: {
          email: 'test@example.com'
        }
      };
      
      Auth.signIn.mockResolvedValue({
        signInUserSession: {
          idToken: { jwtToken: 'mock-token' }
        },
        attributes: mockUser.attributes,
        username: mockUser.username
      });
      
      mockAuthContext.login.mockResolvedValue();
      
      renderWithRouter(<LoginForm onSuccess={onSuccess} />);
      
      fireEvent.change(screen.getByLabelText(/Email/i), {
        target: { value: 'test@example.com' }
      });
      fireEvent.change(screen.getByLabelText(/Password/i), {
        target: { value: 'password123' }
      });
      
      fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));
      
      await waitFor(() => {
        expect(Auth.signIn).toHaveBeenCalledWith('test@example.com', 'password123');
        expect(onSuccess).toHaveBeenCalled();
      });
    });

    it('should handle login errors', async () => {
      Auth.signIn.mockRejectedValue({
        code: 'NotAuthorizedException',
        message: 'Incorrect username or password.'
      });
      
      renderWithRouter(<LoginForm onSuccess={() => {}} />);
      
      fireEvent.change(screen.getByLabelText(/Email/i), {
        target: { value: 'test@example.com' }
      });
      fireEvent.change(screen.getByLabelText(/Password/i), {
        target: { value: 'wrongpassword' }
      });
      
      fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/Incorrect username or password/i)).toBeInTheDocument();
      });
    });

    it('should handle user not confirmed error', async () => {
      Auth.signIn.mockRejectedValue({
        code: 'UserNotConfirmedException',
        message: 'User is not confirmed.'
      });
      
      renderWithRouter(<LoginForm onSuccess={() => {}} />);
      
      fireEvent.change(screen.getByLabelText(/Email/i), {
        target: { value: 'test@example.com' }
      });
      fireEvent.change(screen.getByLabelText(/Password/i), {
        target: { value: 'password123' }
      });
      
      fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/Please check your email to confirm your account/i)).toBeInTheDocument();
        expect(screen.getByText(/Resend Confirmation/i)).toBeInTheDocument();
      });
    });

    it('should handle MFA challenge', async () => {
      Auth.signIn.mockResolvedValue({
        challengeName: 'SMS_MFA',
        challengeParam: {
          CODE_DELIVERY_DELIVERY_MEDIUM: 'SMS',
          CODE_DELIVERY_DESTINATION: '+1***-***-1234'
        }
      });
      
      renderWithRouter(<LoginForm onSuccess={() => {}} />);
      
      fireEvent.change(screen.getByLabelText(/Email/i), {
        target: { value: 'test@example.com' }
      });
      fireEvent.change(screen.getByLabelText(/Password/i), {
        target: { value: 'password123' }
      });
      
      fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/Enter the verification code/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/Verification Code/i)).toBeInTheDocument();
      });
    });

    it('should show loading state during login', async () => {
      Auth.signIn.mockImplementation(() => 
        new Promise(resolve => setTimeout(() => resolve({
          signInUserSession: { idToken: { jwtToken: 'mock-token' } }
        }), 100))
      );
      
      renderWithRouter(<LoginForm onSuccess={() => {}} />);
      
      fireEvent.change(screen.getByLabelText(/Email/i), {
        target: { value: 'test@example.com' }
      });
      fireEvent.change(screen.getByLabelText(/Password/i), {
        target: { value: 'password123' }
      });
      
      fireEvent.click(screen.getByRole('button', { name: /Sign In/i }));
      
      expect(screen.getByText(/Signing in/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Signing in/i })).toBeDisabled();
      
      await waitFor(() => {
        expect(screen.queryByText(/Signing in/i)).not.toBeInTheDocument();
      }, { timeout: 200 });
    });

    it('should toggle password visibility', () => {
      renderWithRouter(<LoginForm onSuccess={() => {}} />);
      
      const passwordField = screen.getByLabelText(/Password/i);
      const toggleButton = screen.getByLabelText(/Toggle password visibility/i);
      
      expect(passwordField).toHaveAttribute('type', 'password');
      
      fireEvent.click(toggleButton);
      expect(passwordField).toHaveAttribute('type', 'text');
      
      fireEvent.click(toggleButton);
      expect(passwordField).toHaveAttribute('type', 'password');
    });
  });

  describe('Signup Flow', () => {
    it('should render signup form', () => {
      renderWithRouter(<AuthModal isOpen={true} initialMode="signup" onClose={() => {}} />);
      
      expect(screen.getByText(/Sign Up/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Password/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Confirm Password/i)).toBeInTheDocument();
    });

    it('should validate password confirmation', async () => {
      renderWithRouter(<AuthModal isOpen={true} initialMode="signup" onClose={() => {}} />);
      
      fireEvent.change(screen.getByLabelText(/^Password$/i), {
        target: { value: 'password123' }
      });
      fireEvent.change(screen.getByLabelText(/Confirm Password/i), {
        target: { value: 'differentpassword' }
      });
      
      fireEvent.click(screen.getByRole('button', { name: /Sign Up/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/Passwords do not match/i)).toBeInTheDocument();
      });
    });

    it('should validate password strength', async () => {
      renderWithRouter(<AuthModal isOpen={true} initialMode="signup" onClose={() => {}} />);
      
      fireEvent.change(screen.getByLabelText(/^Password$/i), {
        target: { value: 'weak' }
      });
      
      fireEvent.blur(screen.getByLabelText(/^Password$/i));
      
      await waitFor(() => {
        expect(screen.getByText(/Password must be at least 8 characters/i)).toBeInTheDocument();
      });
    });

    it('should handle successful signup', async () => {
      Auth.signUp.mockResolvedValue({
        user: {
          username: 'testuser'
        },
        userConfirmed: false
      });
      
      renderWithRouter(<AuthModal isOpen={true} initialMode="signup" onClose={() => {}} />);
      
      fireEvent.change(screen.getByLabelText(/Email/i), {
        target: { value: 'test@example.com' }
      });
      fireEvent.change(screen.getByLabelText(/^Password$/i), {
        target: { value: 'Password123!' }
      });
      fireEvent.change(screen.getByLabelText(/Confirm Password/i), {
        target: { value: 'Password123!' }
      });
      
      fireEvent.click(screen.getByRole('button', { name: /Sign Up/i }));
      
      await waitFor(() => {
        expect(Auth.signUp).toHaveBeenCalledWith({
          username: 'test@example.com',
          password: 'Password123!',
          attributes: {
            email: 'test@example.com'
          }
        });
        expect(screen.getByText(/Please check your email/i)).toBeInTheDocument();
      });
    });

    it('should handle signup errors', async () => {
      Auth.signUp.mockRejectedValue({
        code: 'UsernameExistsException',
        message: 'An account with the given email already exists.'
      });
      
      renderWithRouter(<AuthModal isOpen={true} initialMode="signup" onClose={() => {}} />);
      
      fireEvent.change(screen.getByLabelText(/Email/i), {
        target: { value: 'existing@example.com' }
      });
      fireEvent.change(screen.getByLabelText(/^Password$/i), {
        target: { value: 'Password123!' }
      });
      fireEvent.change(screen.getByLabelText(/Confirm Password/i), {
        target: { value: 'Password123!' }
      });
      
      fireEvent.click(screen.getByRole('button', { name: /Sign Up/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/An account with the given email already exists/i)).toBeInTheDocument();
      });
    });
  });

  describe('Email Confirmation', () => {
    it('should render confirmation code form', async () => {
      Auth.signUp.mockResolvedValue({
        user: { username: 'testuser' },
        userConfirmed: false
      });
      
      renderWithRouter(<AuthModal isOpen={true} initialMode="signup" onClose={() => {}} />);
      
      // Complete signup first
      fireEvent.change(screen.getByLabelText(/Email/i), {
        target: { value: 'test@example.com' }
      });
      fireEvent.change(screen.getByLabelText(/^Password$/i), {
        target: { value: 'Password123!' }
      });
      fireEvent.change(screen.getByLabelText(/Confirm Password/i), {
        target: { value: 'Password123!' }
      });
      
      fireEvent.click(screen.getByRole('button', { name: /Sign Up/i }));
      
      await waitFor(() => {
        expect(screen.getByLabelText(/Confirmation Code/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Confirm Account/i })).toBeInTheDocument();
      });
    });

    it('should handle successful email confirmation', async () => {
      const onSuccess = vi.fn();
      
      Auth.confirmSignUp.mockResolvedValue({});
      Auth.signIn.mockResolvedValue({
        signInUserSession: {
          idToken: { jwtToken: 'mock-token' }
        }
      });
      
      renderWithRouter(<AuthModal isOpen={true} onClose={() => {}} onSuccess={onSuccess} />);
      
      // Simulate being in confirmation state
      fireEvent.change(screen.getByLabelText(/Confirmation Code/i), {
        target: { value: '123456' }
      });
      
      fireEvent.click(screen.getByRole('button', { name: /Confirm Account/i }));
      
      await waitFor(() => {
        expect(Auth.confirmSignUp).toHaveBeenCalledWith('test@example.com', '123456');
        expect(onSuccess).toHaveBeenCalled();
      });
    });

    it('should handle resend confirmation code', async () => {
      Auth.resendSignUp.mockResolvedValue({});
      
      renderWithRouter(<AuthModal isOpen={true} initialMode="confirmation" email="test@example.com" onClose={() => {}} />);
      
      fireEvent.click(screen.getByText(/Resend Code/i));
      
      await waitFor(() => {
        expect(Auth.resendSignUp).toHaveBeenCalledWith('test@example.com');
        expect(screen.getByText(/Confirmation code sent/i)).toBeInTheDocument();
      });
    });
  });

  describe('Forgot Password Flow', () => {
    it('should render forgot password form', () => {
      renderWithRouter(<AuthModal isOpen={true} initialMode="forgotPassword" onClose={() => {}} />);
      
      expect(screen.getByText(/Reset Password/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Email/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Send Reset Code/i })).toBeInTheDocument();
    });

    it('should handle forgot password request', async () => {
      Auth.forgotPassword.mockResolvedValue({
        CodeDeliveryDetails: {
          DeliveryMedium: 'EMAIL',
          Destination: 't***@example.com'
        }
      });
      
      renderWithRouter(<AuthModal isOpen={true} initialMode="forgotPassword" onClose={() => {}} />);
      
      fireEvent.change(screen.getByLabelText(/Email/i), {
        target: { value: 'test@example.com' }
      });
      
      fireEvent.click(screen.getByRole('button', { name: /Send Reset Code/i }));
      
      await waitFor(() => {
        expect(Auth.forgotPassword).toHaveBeenCalledWith('test@example.com');
        expect(screen.getByText(/Reset code sent to/i)).toBeInTheDocument();
      });
    });

    it('should handle password reset confirmation', async () => {
      const onSuccess = vi.fn();
      
      Auth.forgotPasswordSubmit.mockResolvedValue({});
      
      renderWithRouter(<AuthModal isOpen={true} initialMode="resetPassword" email="test@example.com" onClose={() => {}} onSuccess={onSuccess} />);
      
      fireEvent.change(screen.getByLabelText(/Reset Code/i), {
        target: { value: '123456' }
      });
      fireEvent.change(screen.getByLabelText(/New Password/i), {
        target: { value: 'NewPassword123!' }
      });
      
      fireEvent.click(screen.getByRole('button', { name: /Reset Password/i }));
      
      await waitFor(() => {
        expect(Auth.forgotPasswordSubmit).toHaveBeenCalledWith(
          'test@example.com',
          '123456',
          'NewPassword123!'
        );
        expect(onSuccess).toHaveBeenCalled();
      });
    });
  });

  describe('Accessibility', () => {
    it('should have proper ARIA labels and roles', () => {
      renderWithRouter(<AuthModal isOpen={true} onClose={() => {}} />);
      
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByLabelText(/Email/i)).toHaveAttribute('aria-required', 'true');
      expect(screen.getByLabelText(/Password/i)).toHaveAttribute('aria-required', 'true');
    });

    it('should trap focus within modal', () => {
      renderWithRouter(<AuthModal isOpen={true} onClose={() => {}} />);
      
      const _modal = screen.getByRole('dialog');
      const firstFocusable = screen.getByLabelText(/Email/i);
      const lastFocusable = screen.getByRole('button', { name: /Sign In/i });
      
      // Focus should start on first element
      expect(firstFocusable).toHaveFocus();
      
      // Tab to last element
      fireEvent.keyDown(lastFocusable, { key: 'Tab' });
      expect(firstFocusable).toHaveFocus();
      
      // Shift+Tab from first element should go to last
      fireEvent.keyDown(firstFocusable, { key: 'Tab', shiftKey: true });
      expect(lastFocusable).toHaveFocus();
    });

    it('should close modal on Escape key', () => {
      const onClose = vi.fn();
      renderWithRouter(<AuthModal isOpen={true} onClose={onClose} />);
      
      fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
      
      expect(onClose).toHaveBeenCalled();
    });
  });

  describe('Form Persistence', () => {
    it('should preserve form data when switching modes', () => {
      renderWithRouter(<AuthModal isOpen={true} onClose={() => {}} />);
      
      // Enter email in login form
      fireEvent.change(screen.getByLabelText(/Email/i), {
        target: { value: 'test@example.com' }
      });
      
      // Switch to signup
      fireEvent.click(screen.getByText(/Create Account/i));
      
      // Email should be preserved
      expect(screen.getByDisplayValue('test@example.com')).toBeInTheDocument();
    });

    it('should clear sensitive fields when switching modes', () => {
      renderWithRouter(<AuthModal isOpen={true} onClose={() => {}} />);
      
      // Enter password in login form
      fireEvent.change(screen.getByLabelText(/Password/i), {
        target: { value: 'password123' }
      });
      
      // Switch to signup
      fireEvent.click(screen.getByText(/Create Account/i));
      
      // Password should be cleared
      expect(screen.getByLabelText(/^Password$/i)).toHaveValue('');
    });
  });
});