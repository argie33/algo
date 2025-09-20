import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ApiKeyProvider from '../../../components/ApiKeyProvider';

describe('ApiKeyProvider', () => {
  it('renders children without modification', () => {
    const TestChild = () => <div data-testid="test-child">Test Content</div>;

    const { getByTestId } = render(
      <ApiKeyProvider>
        <TestChild />
      </ApiKeyProvider>
    );

    expect(getByTestId('test-child')).toBeInTheDocument();
    expect(getByTestId('test-child')).toHaveTextContent('Test Content');
  });

  it('renders multiple children correctly', () => {
    const { getByTestId } = render(
      <ApiKeyProvider>
        <div data-testid="child-1">Child 1</div>
        <div data-testid="child-2">Child 2</div>
      </ApiKeyProvider>
    );

    expect(getByTestId('child-1')).toBeInTheDocument();
    expect(getByTestId('child-2')).toBeInTheDocument();
  });

  it('renders nothing when no children provided', () => {
    const { container } = render(<ApiKeyProvider />);
    expect(container.firstChild).toBeNull();
  });
});