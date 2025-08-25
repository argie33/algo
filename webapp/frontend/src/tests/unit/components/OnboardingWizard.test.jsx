import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import OnboardingWizard from '../../../components/onboarding/OnboardingWizard';

// Mock the auth context
const mockAuthContext = {
  isAuthenticated: true,
  user: { id: '1', username: 'testuser' },
  loading: false,
};

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext,
}));

describe('OnboardingWizard', () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    onComplete: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders welcome step by default', () => {
    render(<OnboardingWizard {...defaultProps} />);
    
    expect(screen.getByText(/welcome/i)).toBeInTheDocument();
    expect(screen.getByText(/getting started/i)).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    render(<OnboardingWizard {...defaultProps} open={false} />);
    
    expect(screen.queryByText(/welcome/i)).not.toBeInTheDocument();
  });

  it('navigates through steps correctly', async () => {
    render(<OnboardingWizard {...defaultProps} />);
    
    // Should start at step 1
    expect(screen.getByText(/step 1/i)).toBeInTheDocument();
    
    // Click next to go to step 2
    const nextButton = screen.getByRole('button', { name: /next/i });
    fireEvent.click(nextButton);
    
    await waitFor(() => {
      expect(screen.getByText(/step 2/i)).toBeInTheDocument();
    });
  });

  it('allows going back to previous steps', async () => {
    render(<OnboardingWizard {...defaultProps} />);
    
    // Navigate to step 2
    const nextButton = screen.getByRole('button', { name: /next/i });
    fireEvent.click(nextButton);
    
    await waitFor(() => {
      expect(screen.getByText(/step 2/i)).toBeInTheDocument();
    });
    
    // Go back to step 1
    const backButton = screen.getByRole('button', { name: /back/i });
    fireEvent.click(backButton);
    
    await waitFor(() => {
      expect(screen.getByText(/step 1/i)).toBeInTheDocument();
    });
  });

  it('shows progress indicator', () => {
    render(<OnboardingWizard {...defaultProps} />);
    
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('displays API key setup step', async () => {
    render(<OnboardingWizard {...defaultProps} />);
    
    // Navigate to API key step
    const nextButton = screen.getByRole('button', { name: /next/i });
    fireEvent.click(nextButton);
    fireEvent.click(nextButton);
    
    await waitFor(() => {
      expect(screen.getByText(/api keys/i)).toBeInTheDocument();
    });
  });

  it('validates required fields before proceeding', async () => {
    render(<OnboardingWizard {...defaultProps} />);
    
    // Try to proceed without filling required fields
    const nextButton = screen.getByRole('button', { name: /next/i });
    fireEvent.click(nextButton);
    
    // Should show validation errors
    await waitFor(() => {
      expect(screen.getByText(/required/i)).toBeInTheDocument();
    });
  });

  it('calls onComplete when finished', async () => {
    render(<OnboardingWizard {...defaultProps} />);
    
    // Navigate through all steps
    const nextButton = screen.getByRole('button', { name: /next/i });
    
    // Skip through steps (this would normally require filling forms)
    for (let i = 0; i < 3; i++) {
      fireEvent.click(nextButton);
      await waitFor(() => {});
    }
    
    // Complete the wizard
    const completeButton = screen.getByRole('button', { name: /complete/i });
    fireEvent.click(completeButton);
    
    expect(defaultProps.onComplete).toHaveBeenCalled();
  });

  it('allows skipping optional steps', async () => {
    render(<OnboardingWizard {...defaultProps} />);
    
    const skipButton = screen.getByRole('button', { name: /skip/i });
    fireEvent.click(skipButton);
    
    await waitFor(() => {
      expect(screen.queryByText(/step 1/i)).not.toBeInTheDocument();
    });
  });

  it('saves progress between steps', async () => {
    render(<OnboardingWizard {...defaultProps} />);
    
    // Fill out a form field
    const input = screen.getByLabelText(/name/i);
    fireEvent.change(input, { target: { value: 'Test User' } });
    
    // Navigate away and back
    const nextButton = screen.getByRole('button', { name: /next/i });
    fireEvent.click(nextButton);
    
    const backButton = screen.getByRole('button', { name: /back/i });
    fireEvent.click(backButton);
    
    // Value should be preserved
    await waitFor(() => {
      expect(screen.getByDisplayValue('Test User')).toBeInTheDocument();
    });
  });

  it('handles API key validation', async () => {
    render(<OnboardingWizard {...defaultProps} />);
    
    // Navigate to API key step
    const nextButton = screen.getByRole('button', { name: /next/i });
    fireEvent.click(nextButton);
    fireEvent.click(nextButton);
    
    await waitFor(() => {
      const apiKeyInput = screen.getByLabelText(/api key/i);
      fireEvent.change(apiKeyInput, { target: { value: 'test-api-key' } });
      
      const validateButton = screen.getByRole('button', { name: /validate/i });
      fireEvent.click(validateButton);
    });
    
    // Should show validation status
    await waitFor(() => {
      expect(screen.getByText(/validating/i)).toBeInTheDocument();
    });
  });

  it('closes when onClose is called', () => {
    render(<OnboardingWizard {...defaultProps} />);
    
    const closeButton = screen.getByRole('button', { name: /close/i });
    fireEvent.click(closeButton);
    
    expect(defaultProps.onClose).toHaveBeenCalled();
  });
});