import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect } from 'vitest';
import { Input } from '../../../components/ui/input';

describe('Input Component', () => {
  it('renders basic input element', () => {
    render(<Input placeholder="Test input" />);
    
    const input = screen.getByPlaceholderText('Test input');
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute('type', 'text');
  });

  it('supports different input types', () => {
    const { rerender } = render(<Input type="email" />);
    expect(screen.getByRole('textbox')).toHaveAttribute('type', 'email');
    
    rerender(<Input type="password" />);
    expect(screen.getByLabelText(/password/i)).toHaveAttribute('type', 'password');
    
    rerender(<Input type="number" />);
    expect(screen.getByRole('spinbutton')).toHaveAttribute('type', 'number');
  });

  it('handles value changes', async () => {
    const user = userEvent.setup();
    const mockOnChange = vi.fn();
    
    render(<Input onChange={mockOnChange} />);
    
    const input = screen.getByRole('textbox');
    await user.type(input, 'test value');
    
    expect(mockOnChange).toHaveBeenCalledTimes(10); // 'test value' is 10 characters
    expect(input).toHaveValue('test value');
  });

  it('supports controlled input with value prop', () => {
    const { rerender } = render(<Input value="initial" onChange={() => {}} />);
    
    const input = screen.getByRole('textbox');
    expect(input).toHaveValue('initial');
    
    rerender(<Input value="updated" onChange={() => {}} />);
    expect(input).toHaveValue('updated');
  });

  it('applies disabled state correctly', () => {
    render(<Input disabled />);
    
    const input = screen.getByRole('textbox');
    expect(input).toBeDisabled();
    expect(input).toHaveClass('disabled:cursor-not-allowed');
  });

  it('applies error styling when invalid', () => {
    render(<Input invalid />);
    
    const input = screen.getByRole('textbox');
    expect(input).toHaveClass('border-red-500');
  });

  it('supports custom className', () => {
    render(<Input className="custom-input" />);
    
    const input = screen.getByRole('textbox');
    expect(input).toHaveClass('custom-input');
  });

  it('forwards ref correctly', () => {
    const ref = React.createRef();
    render(<Input ref={ref} />);
    
    expect(ref.current).toBeInstanceOf(HTMLInputElement);
  });

  it('supports all HTML input attributes', () => {
    render(
      <Input
        id="test-input"
        name="test-name"
        required
        maxLength={10}
        minLength={2}
        pattern="[A-Za-z]+"
      />
    );
    
    const input = screen.getByRole('textbox');
    expect(input).toHaveAttribute('id', 'test-input');
    expect(input).toHaveAttribute('name', 'test-name');
    expect(input).toBeRequired();
    expect(input).toHaveAttribute('maxlength', '10');
    expect(input).toHaveAttribute('minlength', '2');
    expect(input).toHaveAttribute('pattern', '[A-Za-z]+');
  });

  describe('Accessibility', () => {
    it('supports ARIA attributes', () => {
      render(
        <Input
          aria-label="Custom input label"
          aria-describedby="input-help"
          aria-invalid="true"
        />
      );
      
      const input = screen.getByLabelText('Custom input label');
      expect(input).toHaveAttribute('aria-describedby', 'input-help');
      expect(input).toHaveAttribute('aria-invalid', 'true');
    });

    it('associates with form labels correctly', () => {
      render(
        <>
          <label htmlFor="labeled-input">Input Label</label>
          <Input id="labeled-input" />
        </>
      );
      
      const input = screen.getByLabelText('Input Label');
      expect(input).toHaveAttribute('id', 'labeled-input');
    });

    it('provides proper focus management', async () => {
      const user = userEvent.setup();
      render(<Input />);
      
      const input = screen.getByRole('textbox');
      await user.tab();
      
      expect(input).toHaveFocus();
    });

    it('supports keyboard navigation', async () => {
      const user = userEvent.setup();
      const mockOnKeyDown = vi.fn();
      
      render(<Input onKeyDown={mockOnKeyDown} />);
      
      const input = screen.getByRole('textbox');
      await user.type(input, '{enter}');
      
      expect(mockOnKeyDown).toHaveBeenCalledWith(
        expect.objectContaining({ key: 'Enter' })
      );
    });
  });

  describe('Form Integration', () => {
    it('integrates with form validation', async () => {
      const mockOnSubmit = vi.fn(e => e.preventDefault());
      
      render(
        <form onSubmit={mockOnSubmit}>
          <Input name="required-field" required />
          <button type="submit">Submit</button>
        </form>
      );
      
      const submitButton = screen.getByRole('button', { name: 'Submit' });
      fireEvent.click(submitButton);
      
      const input = screen.getByRole('textbox');
      expect(input).toBeInvalid();
    });

    it('supports form reset', () => {
      render(
        <form>
          <Input defaultValue="initial" />
          <button type="reset">Reset</button>
        </form>
      );
      
      const input = screen.getByRole('textbox');
      const resetButton = screen.getByRole('button', { name: 'Reset' });
      
      fireEvent.change(input, { target: { value: 'changed' } });
      expect(input).toHaveValue('changed');
      
      fireEvent.click(resetButton);
      expect(input).toHaveValue('initial');
    });
  });

  describe('Input Variants and Sizes', () => {
    it('applies size variants correctly', () => {
      const { rerender } = render(<Input size="sm" />);
      let input = screen.getByRole('textbox');
      expect(input).toHaveClass('h-8');
      
      rerender(<Input size="lg" />);
      input = screen.getByRole('textbox');
      expect(input).toHaveClass('h-12');
    });

    it('supports different visual variants', () => {
      const { rerender } = render(<Input variant="outline" />);
      let input = screen.getByRole('textbox');
      expect(input).toHaveClass('border');
      
      rerender(<Input variant="filled" />);
      input = screen.getByRole('textbox');
      expect(input).toHaveClass('bg-gray-100');
    });
  });

  describe('Input Groups and Addons', () => {
    it('supports left addon', () => {
      render(
        <div className="input-group">
          <span className="input-addon-left">$</span>
          <Input />
        </div>
      );
      
      expect(screen.getByText('$')).toBeInTheDocument();
      expect(screen.getByRole('textbox')).toBeInTheDocument();
    });

    it('supports right addon', () => {
      render(
        <div className="input-group">
          <Input />
          <span className="input-addon-right">.com</span>
        </div>
      );
      
      expect(screen.getByText('.com')).toBeInTheDocument();
      expect(screen.getByRole('textbox')).toBeInTheDocument();
    });
  });

  describe('Special Input Types', () => {
    it('handles number inputs correctly', async () => {
      const user = userEvent.setup();
      const mockOnChange = vi.fn();
      
      render(<Input type="number" min="0" max="100" step="1" onChange={mockOnChange} />);
      
      const input = screen.getByRole('spinbutton');
      await user.type(input, '50');
      
      expect(input).toHaveValue(50);
      expect(input).toHaveAttribute('min', '0');
      expect(input).toHaveAttribute('max', '100');
      expect(input).toHaveAttribute('step', '1');
    });

    it('handles date inputs correctly', () => {
      render(<Input type="date" />);
      
      const input = screen.getByDisplayValue('');
      expect(input).toHaveAttribute('type', 'date');
    });

    it('handles file inputs correctly', () => {
      const mockOnChange = vi.fn();
      render(<Input type="file" onChange={mockOnChange} accept=".jpg,.png" />);
      
      const input = screen.getByLabelText(/choose file/i) || screen.getByRole('button');
      expect(input).toHaveAttribute('type', 'file');
      expect(input).toHaveAttribute('accept', '.jpg,.png');
    });
  });

  describe('Performance', () => {
    it('debounces onChange calls when specified', async () => {
      const user = userEvent.setup();
      const mockOnChange = vi.fn();
      
      render(<Input onChange={mockOnChange} debounce={300} />);
      
      const input = screen.getByRole('textbox');
      await user.type(input, 'fast typing');
      
      // Should only call onChange once after debounce delay
      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledTimes(1);
      }, { timeout: 500 });
    });

    it('optimizes re-renders with React.memo', () => {
      const renderSpy = vi.fn();
      
      const TestInput = React.memo((props) => {
        renderSpy();
        return <Input {...props} />;
      });
      
      const { rerender } = render(<TestInput value="test" />);
      rerender(<TestInput value="test" />); // Same props
      
      expect(renderSpy).toHaveBeenCalledTimes(1);
    });
  });

  describe('Error States and Validation', () => {
    it('displays validation messages', () => {
      render(
        <div>
          <Input invalid aria-describedby="error-message" />
          <span id="error-message">This field is required</span>
        </div>
      );
      
      const input = screen.getByRole('textbox');
      const errorMessage = screen.getByText('This field is required');
      
      expect(input).toHaveAttribute('aria-describedby', 'error-message');
      expect(errorMessage).toBeInTheDocument();
    });

    it('handles custom validation', async () => {
      const user = userEvent.setup();
      const mockValidate = vi.fn((value) => value.length < 5 ? 'Too short' : null);
      
      const ValidationInput = () => {
        const [value, setValue] = React.useState('');
        const [error, setError] = React.useState(null);
        
        const handleChange = (e) => {
          const newValue = e.target.value;
          setValue(newValue);
          setError(mockValidate(newValue));
        };
        
        return (
          <div>
            <Input value={value} onChange={handleChange} invalid={!!error} />
            {error && <span role="alert">{error}</span>}
          </div>
        );
      };
      
      render(<ValidationInput />);
      
      const input = screen.getByRole('textbox');
      await user.type(input, 'abc');
      
      expect(screen.getByText('Too short')).toBeInTheDocument();
      expect(mockValidate).toHaveBeenCalledWith('abc');
    });
  });
});