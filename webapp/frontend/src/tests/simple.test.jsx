import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

// Simple component test
function SimpleComponent({ message }) {
  return <div data-testid="simple">{message}</div>;
}

describe('Simple Test Suite', () => {
  it('should render a simple component', () => {
    render(<SimpleComponent message="Hello Test" />);
    expect(screen.getByTestId('simple')).toBeInTheDocument();
    expect(screen.getByText('Hello Test')).toBeInTheDocument();
  });

  it('should handle async operations', async () => {
    const result = await Promise.resolve('async test');
    expect(result).toBe('async test');
  });

  it('should work with basic math', () => {
    expect(2 + 2).toBe(4);
  });
});