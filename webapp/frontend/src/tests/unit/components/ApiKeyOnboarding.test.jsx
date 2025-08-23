import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, test, beforeEach, expect } from 'vitest';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import ApiKeyOnboarding from '../../../components/ApiKeyOnboarding';

// Mock the API keys context
const mockUseApiKeys = {
  apiKeys: {},
  isLoading: false,
  error: null,
  addApiKey: vi.fn(),
  validateApiKey: vi.fn(),
  updateApiKey: vi.fn(),
  deleteApiKey: vi.fn(),
};

vi.mock('../../../components/ApiKeyProvider', () => ({
  useApiKeys: () => mockUseApiKeys,
}));

// Mock external link opening
Object.defineProperty(window, 'open', {
  writable: true,
  value: vi.fn(),
});

describe('ApiKeyOnboarding', () => {
  const mockOnComplete = vi.fn();
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseApiKeys.apiKeys = {};
    mockUseApiKeys.isLoading = false;
    mockUseApiKeys.error = null;
  });

  describe('Initial Render and Welcome Step', () => {
    test('renders welcome step initially', () => {
      render(<ApiKeyOnboarding onComplete={mockOnComplete} />);

      expect(screen.getByText(/welcome to your trading platform/i)).toBeInTheDocument();
      expect(screen.getByText(/get started/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /get started/i })).toBeInTheDocument();
    });

    test('shows progress indicator', () => {
      render(<ApiKeyOnboarding onComplete={mockOnComplete} />);

      expect(screen.getByText('Step 1 of 4')).toBeInTheDocument();
    });

    test('advances to Alpaca setup on Get Started click', async () => {
      render(<ApiKeyOnboarding onComplete={mockOnComplete} />);

      await user.click(screen.getByRole('button', { name: /get started/i }));

      expect(screen.getByText(/alpaca trading setup/i)).toBeInTheDocument();
      expect(screen.getByText('Step 2 of 4')).toBeInTheDocument();
    });
  });

  describe('Alpaca Setup Step', () => {
    beforeEach(async () => {
      render(<ApiKeyOnboarding onComplete={mockOnComplete} />);
      await user.click(screen.getByRole('button', { name: /get started/i }));
    });

    test('renders Alpaca setup form', () => {
      expect(screen.getByText(/alpaca trading setup/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/api key id/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/secret key/i)).toBeInTheDocument();
      expect(screen.getByRole('checkbox', { name: /paper trading/i })).toBeInTheDocument();
    });

    test('opens Alpaca API documentation when link clicked', async () => {
      await user.click(screen.getByText(/get your alpaca api keys/i));

      expect(window.open).toHaveBeenCalledWith(
        'https://app.alpaca.markets/paper/dashboard/overview',
        '_blank',
        'noopener,noreferrer'
      );
    });

    test('validates required fields before submission', async () => {
      await user.click(screen.getByRole('button', { name: /test connection/i }));

      expect(screen.getByText(/api key id is required/i)).toBeInTheDocument();
      expect(screen.getByText(/secret key is required/i)).toBeInTheDocument();
    });

    test('submits valid Alpaca credentials', async () => {
      mockUseApiKeys.validateApiKey.mockResolvedValue({ valid: true });

      await user.type(screen.getByLabelText(/api key id/i), 'test-key-id');
      await user.type(screen.getByLabelText(/secret key/i), 'test-secret-key');
      await user.click(screen.getByRole('button', { name: /test connection/i }));

      expect(mockUseApiKeys.addApiKey).toHaveBeenCalledWith('alpaca', {
        keyId: 'test-key-id',
        secret: 'test-secret-key',
        paper: true,
      });
    });

    test('handles validation errors', async () => {
      mockUseApiKeys.validateApiKey.mockResolvedValue({ 
        valid: false, 
        message: 'Invalid credentials' 
      });

      await user.type(screen.getByLabelText(/api key id/i), 'invalid-key');
      await user.type(screen.getByLabelText(/secret key/i), 'invalid-secret');
      await user.click(screen.getByRole('button', { name: /test connection/i }));

      await waitFor(() => {
        expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument();
      });
    });

    test('toggles between paper and live trading', async () => {
      const paperCheckbox = screen.getByRole('checkbox', { name: /paper trading/i });
      
      expect(paperCheckbox).toBeChecked();
      
      await user.click(paperCheckbox);
      
      expect(paperCheckbox).not.toBeChecked();
      expect(screen.getByText(/live trading environment/i)).toBeInTheDocument();
    });

    test('shows live trading warning', async () => {
      const paperCheckbox = screen.getByRole('checkbox', { name: /paper trading/i });
      await user.click(paperCheckbox);

      expect(screen.getByText(/warning.*live trading/i)).toBeInTheDocument();
    });
  });

  describe('Market Data Setup Step', () => {
    beforeEach(async () => {
      render(<ApiKeyOnboarding onComplete={mockOnComplete} />);
      await user.click(screen.getByRole('button', { name: /get started/i }));
      
      // Mock successful Alpaca setup
      mockUseApiKeys.validateApiKey.mockResolvedValue({ valid: true });
      await user.type(screen.getByLabelText(/api key id/i), 'test-key');
      await user.type(screen.getByLabelText(/secret key/i), 'test-secret');
      await user.click(screen.getByRole('button', { name: /test connection/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/market data apis/i)).toBeInTheDocument();
      });
    });

    test('renders market data provider options', () => {
      expect(screen.getByText(/polygon\.io/i)).toBeInTheDocument();
      expect(screen.getByText(/finnhub/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /skip this step/i })).toBeInTheDocument();
    });

    test('allows skipping market data setup', async () => {
      await user.click(screen.getByRole('button', { name: /skip this step/i }));

      expect(screen.getByText(/validate your setup/i)).toBeInTheDocument();
      expect(screen.getByText('Step 4 of 4')).toBeInTheDocument();
    });

    test('sets up Polygon.io API key', async () => {
      await user.click(screen.getByText(/set up polygon\.io/i));

      expect(screen.getByLabelText(/polygon api key/i)).toBeInTheDocument();
      
      await user.type(screen.getByLabelText(/polygon api key/i), 'polygon-test-key');
      await user.click(screen.getByRole('button', { name: /test polygon connection/i }));

      expect(mockUseApiKeys.addApiKey).toHaveBeenCalledWith('polygon', {
        apiKey: 'polygon-test-key',
      });
    });

    test('sets up Finnhub API key', async () => {
      await user.click(screen.getByText(/set up finnhub/i));

      expect(screen.getByLabelText(/finnhub api key/i)).toBeInTheDocument();
      
      await user.type(screen.getByLabelText(/finnhub api key/i), 'finnhub-test-key');
      await user.click(screen.getByRole('button', { name: /test finnhub connection/i }));

      expect(mockUseApiKeys.addApiKey).toHaveBeenCalledWith('finnhub', {
        apiKey: 'finnhub-test-key',
      });
    });
  });

  describe('Validation Step', () => {
    beforeEach(async () => {
      // Navigate to validation step
      render(<ApiKeyOnboarding onComplete={mockOnComplete} />);
      await user.click(screen.getByRole('button', { name: /get started/i }));
      
      // Complete Alpaca setup
      mockUseApiKeys.validateApiKey.mockResolvedValue({ valid: true });
      await user.type(screen.getByLabelText(/api key id/i), 'test-key');
      await user.type(screen.getByLabelText(/secret key/i), 'test-secret');
      await user.click(screen.getByRole('button', { name: /test connection/i }));
      
      // Skip market data setup
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /skip this step/i })).toBeInTheDocument();
      });
      await user.click(screen.getByRole('button', { name: /skip this step/i }));
    });

    test('renders validation step', () => {
      expect(screen.getByText(/validate your setup/i)).toBeInTheDocument();
      expect(screen.getByText('Step 4 of 4')).toBeInTheDocument();
    });

    test('shows API key status', () => {
      expect(screen.getByText(/alpaca trading/i)).toBeInTheDocument();
      expect(screen.getByText(/connected/i)).toBeInTheDocument();
    });

    test('completes onboarding successfully', async () => {
      await user.click(screen.getByRole('button', { name: /complete setup/i }));

      expect(mockOnComplete).toHaveBeenCalled();
    });

    test('allows going back to previous steps', async () => {
      await user.click(screen.getByRole('button', { name: /back/i }));

      expect(screen.getByText(/market data apis/i)).toBeInTheDocument();
    });
  });

  describe('Loading and Error States', () => {
    test('shows loading state during API operations', async () => {
      mockUseApiKeys.isLoading = true;
      
      render(<ApiKeyOnboarding onComplete={mockOnComplete} />);
      await user.click(screen.getByRole('button', { name: /get started/i }));

      expect(screen.getByText(/validating/i)).toBeInTheDocument();
    });

    test('displays API errors', async () => {
      mockUseApiKeys.error = 'Connection failed';
      
      render(<ApiKeyOnboarding onComplete={mockOnComplete} />);
      await user.click(screen.getByRole('button', { name: /get started/i }));

      expect(screen.getByText(/connection failed/i)).toBeInTheDocument();
    });

    test('allows retrying failed operations', async () => {
      mockUseApiKeys.validateApiKey.mockRejectedValueOnce(new Error('Network error'))
                                   .mockResolvedValueOnce({ valid: true });

      render(<ApiKeyOnboarding onComplete={mockOnComplete} />);
      await user.click(screen.getByRole('button', { name: /get started/i }));
      
      await user.type(screen.getByLabelText(/api key id/i), 'test-key');
      await user.type(screen.getByLabelText(/secret key/i), 'test-secret');
      await user.click(screen.getByRole('button', { name: /test connection/i }));

      await waitFor(() => {
        expect(screen.getByText(/retry/i)).toBeInTheDocument();
      });

      await user.click(screen.getByRole('button', { name: /retry/i }));

      await waitFor(() => {
        expect(screen.getByText(/market data apis/i)).toBeInTheDocument();
      });
    });
  });

  describe('Accessibility', () => {
    test('has proper ARIA labels and roles', () => {
      render(<ApiKeyOnboarding onComplete={mockOnComplete} />);

      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByRole('dialog')).toHaveAttribute('aria-labelledby');
    });

    test('supports keyboard navigation', async () => {
      render(<ApiKeyOnboarding onComplete={mockOnComplete} />);

      const getStartedButton = screen.getByRole('button', { name: /get started/i });
      getStartedButton.focus();
      
      expect(getStartedButton).toHaveFocus();
      
      await user.keyboard('{Enter}');
      
      expect(screen.getByText(/alpaca trading setup/i)).toBeInTheDocument();
    });
  });

  describe('Form Validation Edge Cases', () => {
    test('handles special characters in API keys', async () => {
      render(<ApiKeyOnboarding onComplete={mockOnComplete} />);
      await user.click(screen.getByRole('button', { name: /get started/i }));

      const specialKey = 'key-with-!@#$%^&*()';
      await user.type(screen.getByLabelText(/api key id/i), specialKey);
      await user.type(screen.getByLabelText(/secret key/i), 'secret-key');

      expect(screen.getByDisplayValue(specialKey)).toBeInTheDocument();
    });

    test('validates minimum key length requirements', async () => {
      render(<ApiKeyOnboarding onComplete={mockOnComplete} />);
      await user.click(screen.getByRole('button', { name: /get started/i }));

      await user.type(screen.getByLabelText(/api key id/i), 'short');
      await user.type(screen.getByLabelText(/secret key/i), 'abc');
      await user.click(screen.getByRole('button', { name: /test connection/i }));

      expect(screen.getByText(/api key must be at least/i)).toBeInTheDocument();
    });
  });
});