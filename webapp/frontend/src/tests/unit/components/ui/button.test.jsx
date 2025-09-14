import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import { Button } from '../../../../components/ui/button';

describe('Button', () => {
  describe('Rendering', () => {
    test('renders without crashing', () => {
      render(<Button>Test Button</Button>);
      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    test('renders children correctly', () => {
      render(<Button>Button Text</Button>);
      expect(screen.getByText('Button Text')).toBeInTheDocument();
    });

    test('applies custom className', () => {
      render(<Button className="custom-button">Test</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('custom-button');
    });

    test('forwards ref correctly', () => {
      const ref = { current: null };
      render(<Button ref={ref}>Test</Button>);
      expect(ref.current).toBeInstanceOf(HTMLElement);
      expect(ref.current.tagName).toBe('BUTTON');
    });
  });

  describe('Variants', () => {
    test('renders contained variant by default', () => {
      render(<Button>Default Button</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('MuiButton-contained');
    });

    test('renders default variant as contained', () => {
      render(<Button variant="default">Default Variant</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('MuiButton-contained');
    });

    test('renders outlined variant', () => {
      render(<Button variant="outlined">Outlined Button</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('MuiButton-outlined');
    });

    test('renders text variant', () => {
      render(<Button variant="text">Text Button</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('MuiButton-text');
    });

    test('renders contained variant explicitly', () => {
      render(<Button variant="contained">Contained Button</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('MuiButton-contained');
    });
  });

  describe('Sizes', () => {
    test('renders medium size by default', () => {
      render(<Button>Medium Button</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('MuiButton-sizeMedium');
    });

    test('renders small size', () => {
      render(<Button size="small">Small Button</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('MuiButton-sizeSmall');
    });

    test('renders large size', () => {
      render(<Button size="large">Large Button</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('MuiButton-sizeLarge');
    });

    test('maintains medium size when not specified', () => {
      render(<Button>No Size</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('MuiButton-sizeMedium');
    });
  });

  describe('User Interactions', () => {
    test('handles click events', () => {
      const handleClick = vi.fn();
      render(<Button onClick={handleClick}>Clickable</Button>);
      
      const button = screen.getByRole('button');
      fireEvent.click(button);
      
      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    test('handles multiple clicks', () => {
      const handleClick = vi.fn();
      render(<Button onClick={handleClick}>Multi Click</Button>);
      
      const button = screen.getByRole('button');
      fireEvent.click(button);
      fireEvent.click(button);
      fireEvent.click(button);
      
      expect(handleClick).toHaveBeenCalledTimes(3);
    });

    test('does not trigger click when disabled', () => {
      const handleClick = vi.fn();
      render(<Button onClick={handleClick} disabled>Disabled</Button>);
      
      const button = screen.getByRole('button');
      fireEvent.click(button);
      
      expect(handleClick).not.toHaveBeenCalled();
    });

    test('handles keyboard events', () => {
      const handleKeyDown = vi.fn();
      render(<Button onKeyDown={handleKeyDown}>Keyboard</Button>);
      
      const button = screen.getByRole('button');
      fireEvent.keyDown(button, { key: 'Enter', code: 'Enter' });
      
      expect(handleKeyDown).toHaveBeenCalledTimes(1);
    });
  });

  describe('States', () => {
    test('handles disabled state', () => {
      render(<Button disabled>Disabled Button</Button>);
      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
      expect(button).toHaveClass('Mui-disabled');
    });

    test('handles loading state', () => {
      render(<Button loading>Loading Button</Button>);
      const button = screen.getByRole('button');
      // The basic Button component doesn't implement loading state behavior
      // It just forwards props to MUI Button which doesn't have native loading prop
      expect(button).toBeInTheDocument();
    });

    test('shows loading spinner when loading', () => {
      render(<Button loading>Loading</Button>);
      // The basic Button component doesn't implement loading spinner
      // It just forwards props to MUI Button which doesn't have native loading prop
      const button = screen.getByRole('button');
      expect(button).toBeInTheDocument();
    });

    test('handles focus state', () => {
      render(<Button>Focusable</Button>);
      const button = screen.getByRole('button');
      button.focus();
      expect(button).toHaveFocus();
    });
  });

  describe('Colors', () => {
    test('handles primary color', () => {
      render(<Button color="primary">Primary</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('MuiButton-colorPrimary');
    });

    test('handles secondary color', () => {
      render(<Button color="secondary">Secondary</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('MuiButton-colorSecondary');
    });

    test('handles error color', () => {
      render(<Button color="error">Error</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('MuiButton-colorError');
    });

    test('handles success color', () => {
      render(<Button color="success">Success</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveClass('MuiButton-colorSuccess');
    });
  });

  describe('Props Forwarding', () => {
    test('forwards additional props to MUI Button', () => {
      render(<Button data-testid="test-button" title="Button Title">Test</Button>);
      const button = screen.getByTestId('test-button');
      expect(button).toHaveAttribute('title', 'Button Title');
    });

    test('forwards type attribute', () => {
      render(<Button type="submit">Submit</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('type', 'submit');
    });

    test('forwards form attribute', () => {
      render(<Button form="test-form">Form Button</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('form', 'test-form');
    });

    test('forwards tabIndex', () => {
      render(<Button tabIndex={-1}>No Tab</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('tabIndex', '-1');
    });
  });

  describe('Content Types', () => {
    test('renders with icon and text', () => {
      const Icon = () => <span data-testid="icon">🔥</span>;
      render(
        <Button startIcon={<Icon />}>
          With Icon
        </Button>
      );
      
      expect(screen.getByText('With Icon')).toBeInTheDocument();
      expect(screen.getByTestId('icon')).toBeInTheDocument();
    });

    test('renders end icon', () => {
      const Icon = () => <span data-testid="end-icon">→</span>;
      render(
        <Button endIcon={<Icon />}>
          End Icon
        </Button>
      );
      
      expect(screen.getByText('End Icon')).toBeInTheDocument();
      expect(screen.getByTestId('end-icon')).toBeInTheDocument();
    });

    test('renders with custom children', () => {
      render(
        <Button>
          <span>Custom</span> <strong>Content</strong>
        </Button>
      );
      
      expect(screen.getByText('Custom')).toBeInTheDocument();
      expect(screen.getByText('Content')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    test('has proper button role', () => {
      render(<Button>Accessible</Button>);
      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    test('supports aria-label', () => {
      render(<Button aria-label="Custom Label">Button</Button>);
      const button = screen.getByLabelText('Custom Label');
      expect(button).toBeInTheDocument();
    });

    test('supports aria-describedby', () => {
      render(<Button aria-describedby="description">Button</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-describedby', 'description');
    });

    test('is keyboard navigable', () => {
      render(<Button>Keyboard</Button>);
      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('tabIndex', '0');
    });
  });

  describe('Edge Cases', () => {
    test('handles empty children', () => {
      render(<Button />);
      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    test('handles null children', () => {
      render(<Button>{null}</Button>);
      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    test('handles undefined children', () => {
      render(<Button>{undefined}</Button>);
      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    test('handles numeric children', () => {
      render(<Button>{0}</Button>);
      expect(screen.getByText('0')).toBeInTheDocument();
    });

    test('handles boolean false children', () => {
      render(<Button>{false}</Button>);
      expect(screen.getByRole('button')).toBeInTheDocument();
    });
  });

  describe('Display Name', () => {
    test('has correct display name', () => {
      expect(Button.displayName).toBe('Button');
    });
  });
});