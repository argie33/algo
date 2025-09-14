import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import RegisterForm from '../../../../components/auth/RegisterForm';

// Mock AuthContext
const mockRegister = vi.fn();
const mockClearError = vi.fn();

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    register: mockRegister,
    isLoading: false,
    error: '',
    clearError: mockClearError
  })
}));

describe('RegisterForm', () => {
  const defaultProps = {
    onSwitchToLogin: vi.fn(),
    onRegistrationSuccess: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockRegister.mockResolvedValue({ success: true });
  });

  describe('Basic Rendering', () => {
    test('renders register form with all elements', () => {
      render(<RegisterForm {...defaultProps} />);
      
      expect(screen.getByText('Create Account')).toBeInTheDocument();
      expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/last name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
      expect(screen.getAllByLabelText(/password/i)).toHaveLength(2);
      expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument();
    });

    test('has password visibility toggles', () => {
      render(<RegisterForm {...defaultProps} />);
      
      const toggleButtons = screen.getAllByLabelText('toggle password visibility');
      expect(toggleButtons).toHaveLength(2);
    });
  });

  describe('Form Interactions', () => {
    test('updates form fields', () => {
      render(<RegisterForm {...defaultProps} />);
      
      const firstNameField = screen.getByLabelText(/first name/i);
      fireEvent.change(firstNameField, { target: { value: 'John' } });
      
      expect(firstNameField.value).toBe('John');
    });

    test('toggles password visibility', () => {
      render(<RegisterForm {...defaultProps} />);
      
      const passwordField = screen.getAllByLabelText(/password/i)[0];
      const toggleButtons = screen.getAllByLabelText('toggle password visibility');
      
      expect(passwordField).toHaveAttribute('type', 'password');
      
      fireEvent.click(toggleButtons[0]);
      expect(passwordField).toHaveAttribute('type', 'text');
    });
  });

  describe('Form Validation', () => {
    test('shows error for empty required fields', async () => {
      render(<RegisterForm {...defaultProps} />);
      
      const submitButton = screen.getByRole('button', { name: /create account/i });
      fireEvent.click(submitButton);
      
      await waitFor(() => {
        expect(screen.getByText(/please fill in all required fields/i)).toBeInTheDocument();
      });
    });

    test('shows error for password mismatch', async () => {
      render(<RegisterForm {...defaultProps} />);
      
      fireEvent.change(screen.getByLabelText(/first name/i), { target: { value: 'John' } });
      fireEvent.change(screen.getByLabelText(/last name/i), { target: { value: 'Doe' } });
      fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'johndoe' } });
      fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'john@example.com' } });
      fireEvent.change(screen.getAllByLabelText(/password/i)[0], { target: { value: 'password123' } });
      fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: 'different' } });
      
      const submitButton = screen.getByRole('button', { name: /create account/i });
      fireEvent.click(submitButton);
      
      await waitFor(() => {
        expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
      });
    });

    test('shows error for invalid email', async () => {
      render(<RegisterForm {...defaultProps} />);
      
      fireEvent.change(screen.getByLabelText(/first name/i), { target: { value: 'John' } });
      fireEvent.change(screen.getByLabelText(/last name/i), { target: { value: 'Doe' } });
      fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'johndoe' } });
      fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'invalid-email' } });
      fireEvent.change(screen.getAllByLabelText(/password/i)[0], { target: { value: 'password123' } });
      fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: 'password123' } });
      
      const submitButton = screen.getByRole('button', { name: /create account/i });
      fireEvent.click(submitButton);
      
      await waitFor(() => {
        expect(screen.getByText(/please enter a valid email address/i)).toBeInTheDocument();
      });
    });
  });

  describe('Form Submission', () => {
    test('submits form with valid data', async () => {
      render(<RegisterForm {...defaultProps} />);
      
      fireEvent.change(screen.getByLabelText(/first name/i), { target: { value: 'John' } });
      fireEvent.change(screen.getByLabelText(/last name/i), { target: { value: 'Doe' } });
      fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'johndoe' } });
      fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'john@example.com' } });
      fireEvent.change(screen.getAllByLabelText(/password/i)[0], { target: { value: 'StrongPass123!' } });
      fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: 'StrongPass123!' } });
      
      const submitButton = screen.getByRole('button', { name: /create account/i });
      fireEvent.click(submitButton);
      
      await waitFor(() => {
        expect(mockRegister).toHaveBeenCalledWith(
          'johndoe',
          'StrongPass123!',
          'john@example.com',
          'John',
          'Doe'
        );
      });
    });

    test('calls onRegistrationSuccess on successful registration', async () => {
      const onRegistrationSuccess = vi.fn();
      mockRegister.mockResolvedValue({ success: true, nextStep: 'CONFIRM_SIGN_UP' });
      
      render(<RegisterForm {...defaultProps} onRegistrationSuccess={onRegistrationSuccess} />);
      
      fireEvent.change(screen.getByLabelText(/first name/i), { target: { value: 'John' } });
      fireEvent.change(screen.getByLabelText(/last name/i), { target: { value: 'Doe' } });
      fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'johndoe' } });
      fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'john@example.com' } });
      fireEvent.change(screen.getAllByLabelText(/password/i)[0], { target: { value: 'StrongPass123!' } });
      fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: 'StrongPass123!' } });
      
      const submitButton = screen.getByRole('button', { name: /create account/i });
      fireEvent.click(submitButton);
      
      await waitFor(() => {
        expect(onRegistrationSuccess).toHaveBeenCalledWith('johndoe', 'CONFIRM_SIGN_UP');
      });
    });
  });

  describe('Navigation', () => {
    test('switches to login form', () => {
      const onSwitchToLogin = vi.fn();
      render(<RegisterForm {...defaultProps} onSwitchToLogin={onSwitchToLogin} />);
      
      const loginLink = screen.getByText(/sign in here/i);
      fireEvent.click(loginLink);
      
      expect(onSwitchToLogin).toHaveBeenCalledTimes(1);
    });
  });

  describe('Loading State', () => {
    test('disables form when loading', async () => {
      // Override the AuthContext mock for this test
      const { useAuth } = await import('../../../../contexts/AuthContext');
      useAuth.mockReturnValue({
        register: mockRegister,
        isLoading: true,
        error: '',
        clearError: mockClearError
      });
      
      render(<RegisterForm {...defaultProps} />);
      
      expect(screen.getByLabelText(/first name/i)).toBeDisabled();
      expect(screen.getByRole('button', { name: /creating account.../i })).toBeDisabled();
    });
  });
});