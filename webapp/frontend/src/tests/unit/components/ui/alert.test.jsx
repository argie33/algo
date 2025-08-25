import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect } from 'vitest';
import { Alert, AlertDescription } from '../../../components/ui/alert';

describe('Alert Component', () => {
  it('renders with default variant', () => {
    render(
      <Alert>
        <AlertDescription>Test alert message</AlertDescription>
      </Alert>
    );
    
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Test alert message')).toBeInTheDocument();
  });

  it('applies correct styling for different variants', () => {
    const { rerender } = render(
      <Alert variant="destructive">
        <AlertDescription>Error message</AlertDescription>
      </Alert>
    );
    
    const alertElement = screen.getByRole('alert');
    expect(alertElement).toHaveClass('border-red-200');
    
    rerender(
      <Alert variant="default">
        <AlertDescription>Info message</AlertDescription>
      </Alert>
    );
    
    expect(alertElement).toHaveClass('border-gray-200');
  });

  it('supports success variant styling', () => {
    render(
      <Alert variant="success">
        <AlertDescription>Success message</AlertDescription>
      </Alert>
    );
    
    const alertElement = screen.getByRole('alert');
    expect(alertElement).toHaveClass('border-green-200');
  });

  it('supports warning variant styling', () => {
    render(
      <Alert variant="warning">
        <AlertDescription>Warning message</AlertDescription>
      </Alert>
    );
    
    const alertElement = screen.getByRole('alert');
    expect(alertElement).toHaveClass('border-yellow-200');
  });

  it('renders with custom className', () => {
    render(
      <Alert className="custom-alert">
        <AlertDescription>Custom styled alert</AlertDescription>
      </Alert>
    );
    
    const alertElement = screen.getByRole('alert');
    expect(alertElement).toHaveClass('custom-alert');
  });

  it('supports dismissible alerts', () => {
    const mockOnDismiss = vi.fn();
    
    render(
      <Alert dismissible onDismiss={mockOnDismiss}>
        <AlertDescription>Dismissible alert</AlertDescription>
      </Alert>
    );
    
    const dismissButton = screen.getByRole('button', { name: /dismiss/i });
    expect(dismissButton).toBeInTheDocument();
    
    fireEvent.click(dismissButton);
    expect(mockOnDismiss).toHaveBeenCalled();
  });

  it('renders with icon when provided', () => {
    const TestIcon = () => <svg data-testid="test-icon">Icon</svg>;
    
    render(
      <Alert>
        <TestIcon />
        <AlertDescription>Alert with icon</AlertDescription>
      </Alert>
    );
    
    expect(screen.getByTestId('test-icon')).toBeInTheDocument();
    expect(screen.getByText('Alert with icon')).toBeInTheDocument();
  });

  it('supports multiple children', () => {
    render(
      <Alert>
        <h4>Alert Title</h4>
        <AlertDescription>Alert description</AlertDescription>
        <p>Additional content</p>
      </Alert>
    );
    
    expect(screen.getByText('Alert Title')).toBeInTheDocument();
    expect(screen.getByText('Alert description')).toBeInTheDocument();
    expect(screen.getByText('Additional content')).toBeInTheDocument();
  });

  it('applies proper ARIA attributes', () => {
    render(
      <Alert>
        <AlertDescription>Accessible alert</AlertDescription>
      </Alert>
    );
    
    const alertElement = screen.getByRole('alert');
    expect(alertElement).toHaveAttribute('role', 'alert');
  });

  it('forwards ref correctly', () => {
    const ref = React.createRef();
    
    render(
      <Alert ref={ref}>
        <AlertDescription>Ref forwarded</AlertDescription>
      </Alert>
    );
    
    expect(ref.current).toBeInstanceOf(HTMLDivElement);
  });

  describe('AlertDescription', () => {
    it('renders description text', () => {
      render(<AlertDescription>Description text</AlertDescription>);
      
      expect(screen.getByText('Description text')).toBeInTheDocument();
    });

    it('applies correct styling classes', () => {
      render(<AlertDescription>Styled description</AlertDescription>);
      
      const description = screen.getByText('Styled description');
      expect(description).toHaveClass('text-sm');
    });

    it('supports custom className', () => {
      render(<AlertDescription className="custom-description">Custom description</AlertDescription>);
      
      const description = screen.getByText('Custom description');
      expect(description).toHaveClass('custom-description');
    });

    it('forwards ref correctly', () => {
      const ref = React.createRef();
      
      render(<AlertDescription ref={ref}>Ref description</AlertDescription>);
      
      expect(ref.current).toBeInstanceOf(HTMLParagraphElement);
    });
  });

  describe('Accessibility', () => {
    it('provides proper screen reader support', () => {
      render(
        <Alert>
          <AlertDescription>Screen reader accessible</AlertDescription>
        </Alert>
      );
      
      const alertElement = screen.getByRole('alert');
      expect(alertElement).toBeInTheDocument();
    });

    it('supports custom ARIA labels', () => {
      render(
        <Alert aria-label="Custom alert label">
          <AlertDescription>Custom labeled alert</AlertDescription>
        </Alert>
      );
      
      const alertElement = screen.getByLabelText('Custom alert label');
      expect(alertElement).toBeInTheDocument();
    });

    it('maintains focus management for dismissible alerts', () => {
      const mockOnDismiss = vi.fn();
      
      render(
        <Alert dismissible onDismiss={mockOnDismiss}>
          <AlertDescription>Focus test</AlertDescription>
        </Alert>
      );
      
      const dismissButton = screen.getByRole('button', { name: /dismiss/i });
      dismissButton.focus();
      
      fireEvent.keyDown(dismissButton, { key: 'Enter' });
      expect(mockOnDismiss).toHaveBeenCalled();
    });
  });

  describe('Animation and Transitions', () => {
    it('supports fade-in animation', () => {
      render(
        <Alert animate>
          <AlertDescription>Animated alert</AlertDescription>
        </Alert>
      );
      
      const alertElement = screen.getByRole('alert');
      expect(alertElement).toHaveClass('animate-fade-in');
    });

    it('supports slide-in animation', () => {
      render(
        <Alert animate="slide">
          <AlertDescription>Slide animated alert</AlertDescription>
        </Alert>
      );
      
      const alertElement = screen.getByRole('alert');
      expect(alertElement).toHaveClass('animate-slide-in');
    });
  });

  describe('Integration with Toast System', () => {
    it('works with toast notifications', () => {
      const mockToast = {
        id: '1',
        title: 'Toast Alert',
        description: 'Toast description',
        variant: 'success',
      };
      
      render(
        <Alert variant={mockToast.variant} data-toast-id={mockToast.id}>
          <AlertDescription>{mockToast.description}</AlertDescription>
        </Alert>
      );
      
      const alertElement = screen.getByRole('alert');
      expect(alertElement).toHaveAttribute('data-toast-id', '1');
      expect(screen.getByText('Toast description')).toBeInTheDocument();
    });
  });
});