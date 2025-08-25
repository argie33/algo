/**
 * Simple Test Verification
 * Ensures basic test setup is working
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { renderWithProviders } from './test-utils.jsx';

// Simple component for testing
const TestComponent = ({ message = 'Hello Test' }) => {
  return <div data-testid="test-component">{message}</div>;
};

describe('Simple Test Verification', () => {
  it('should run basic assertions', () => {
    expect(1 + 1).toBe(2);
    expect('test').toBe('test');
  });

  it('should render a simple component', () => {
    render(<TestComponent />);
    expect(screen.getByTestId('test-component')).toBeInTheDocument();
    expect(screen.getByText('Hello Test')).toBeInTheDocument();
  });

  it('should render with providers', () => {
    renderWithProviders(<TestComponent message="Provider Test" />);
    expect(screen.getByTestId('test-component')).toBeInTheDocument();
    expect(screen.getByText('Provider Test')).toBeInTheDocument();
  });

  it('should handle props correctly', () => {
    const customMessage = 'Custom Message';
    render(<TestComponent message={customMessage} />);
    expect(screen.getByText(customMessage)).toBeInTheDocument();
  });

  it('should work with vitest mocks', () => {
    const mockFn = vi.fn();
    mockFn('test');
    expect(mockFn).toHaveBeenCalledWith('test');
  });
});