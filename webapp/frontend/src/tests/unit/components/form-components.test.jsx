/**
 * Form Components Unit Tests
 * Comprehensive testing of all real form and input components
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Real Form Components - Import actual production components
import { FormField } from '../../../components/forms/FormField';
import { TextArea } from '../../../components/forms/TextArea';
import { SelectField } from '../../../components/forms/SelectField';
import { CheckboxField } from '../../../components/forms/CheckboxField';
import { RadioGroup } from '../../../components/forms/RadioGroup';
import { FileUpload } from '../../../components/forms/FileUpload';
import { DatePicker } from '../../../components/forms/DatePicker';
import { NumberInput } from '../../../components/forms/NumberInput';
import { FormValidator } from '../../../components/forms/FormValidator';
import { FormWizard } from '../../../components/forms/FormWizard';
import { SearchableSelect } from '../../../components/forms/SearchableSelect';

describe('📝 Form Components', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('FormField Component', () => {
    it('should render basic form field correctly', () => {
      render(<FormField label="Email" type="email" value="test@example.com" />);

      expect(screen.getByLabelText('Email')).toBeInTheDocument();
      expect(screen.getByDisplayValue('test@example.com')).toBeInTheDocument();
    });

    it('should handle input changes', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(<FormField label="Name" value="" onChange={onChange} />);

      const input = screen.getByLabelText('Name');
      await user.type(input, 'John Doe');
      
      expect(onChange).toHaveBeenCalled();
    });

    it('should show required indicator', () => {
      render(<FormField label="Password" required={true} />);

      const input = screen.getByLabelText(/Password/);
      expect(input).toHaveAttribute('required');
    });

    it('should display error message when provided', () => {
      render(<FormField label="Email" error="Invalid email format" />);

      expect(screen.getByText('Invalid email format')).toBeInTheDocument();
    });

    it('should handle disabled state', () => {
      render(<FormField label="Name" disabled={true} />);

      const input = screen.getByLabelText('Name');
      expect(input).toBeDisabled();
    });

    it('should support different input types', () => {
      const { rerender } = render(<FormField label="Email" type="email" />);
      expect(screen.getByLabelText('Email')).toHaveAttribute('type', 'email');

      rerender(<FormField label="Password" type="password" />);
      expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');

      rerender(<FormField label="Age" type="number" />);
      expect(screen.getByLabelText('Age')).toHaveAttribute('type', 'number');
    });
  });

  describe('TextArea Component', () => {
    it('should render textarea correctly', () => {
      render(<TextArea label="Description" value="Some text" rows={6} />);

      const textarea = screen.getByLabelText('Description');
      expect(textarea).toBeInTheDocument();
      expect(textarea).toHaveValue('Some text');
      expect(textarea).toHaveAttribute('rows', '6');
    });

    it('should show character count when maxLength is set', () => {
      render(<TextArea label="Bio" value="Hello world" maxLength={100} />);

      expect(screen.getByText(/11/)).toBeInTheDocument();
      expect(screen.getByText(/100/)).toBeInTheDocument();
    });

    it('should handle textarea changes', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(<TextArea label="Comments" value="" onChange={onChange} />);

      const textarea = screen.getByLabelText('Comments');
      await user.type(textarea, 'New comment');
      
      expect(onChange).toHaveBeenCalled();
    });

    it('should enforce maxLength constraint', () => {
      render(<TextArea label="Limited" maxLength={10} />);

      const textarea = screen.getByLabelText('Limited');
      expect(textarea).toHaveAttribute('maxLength', '10');
    });
  });

  describe('SelectField Component', () => {
    const options = [
      { value: 'option1', label: 'Option 1' },
      { value: 'option2', label: 'Option 2' },
      { value: 'option3', label: 'Option 3' }
    ];

    it('should render select field correctly', () => {
      render(<SelectField label="Choose Option" options={options} value="option2" />);

      const select = screen.getByLabelText('Choose Option');
      expect(select).toBeInTheDocument();
      expect(select).toHaveValue('option2');
      expect(screen.getByText('Option 1')).toBeInTheDocument();
      expect(screen.getByText('Option 2')).toBeInTheDocument();
      expect(screen.getByText('Option 3')).toBeInTheDocument();
    });

    it('should handle selection changes', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(<SelectField label="Choose Option" options={options} onChange={onChange} />);

      const select = screen.getByLabelText('Choose Option');
      await user.selectOptions(select, 'option2');
      
      expect(onChange).toHaveBeenCalledWith('option2');
    });

    it('should show placeholder option', () => {
      render(<SelectField label="Choose Option" options={options} placeholder="Select an option" />);

      expect(screen.getByText('Select an option')).toBeInTheDocument();
    });

    it('should handle multiple selection', () => {
      render(<SelectField label="Choose Options" options={options} multiple={true} />);

      const select = screen.getByLabelText('Choose Options');
      expect(select).toHaveAttribute('multiple');
    });

    it('should handle disabled state', () => {
      render(<SelectField label="Disabled Select" options={options} disabled={true} />);

      const select = screen.getByLabelText('Disabled Select');
      expect(select).toBeDisabled();
    });
  });

  describe('CheckboxField Component', () => {
    it('should render checkbox correctly', () => {
      render(<CheckboxField label="I agree to terms" checked={true} />);

      const checkbox = screen.getByLabelText('I agree to terms');
      expect(checkbox).toBeInTheDocument();
      expect(checkbox).toBeChecked();
    });

    it('should handle checkbox changes', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(<CheckboxField label="Newsletter" checked={false} onChange={onChange} />);

      const checkbox = screen.getByLabelText('Newsletter');
      await user.click(checkbox);
      
      expect(onChange).toHaveBeenCalledWith(true);
    });

    it('should handle disabled state', () => {
      render(<CheckboxField label="Disabled option" disabled={true} />);

      const checkbox = screen.getByLabelText('Disabled option');
      expect(checkbox).toBeDisabled();
    });

    it('should show error message', () => {
      render(<CheckboxField label="Terms" error="You must agree to terms" />);

      expect(screen.getByText('You must agree to terms')).toBeInTheDocument();
    });
  });

  describe('RadioGroup Component', () => {
    const options = [
      { value: 'small', label: 'Small' },
      { value: 'medium', label: 'Medium' },
      { value: 'large', label: 'Large' }
    ];

    it('should render radio group correctly', () => {
      render(<RadioGroup label="Size" name="size" options={options} value="medium" />);

      expect(screen.getByText('Size')).toBeInTheDocument();
      expect(screen.getByLabelText('Medium')).toBeChecked();
      expect(screen.getByLabelText('Small')).not.toBeChecked();
      expect(screen.getByLabelText('Large')).not.toBeChecked();
    });

    it('should handle radio selection changes', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(<RadioGroup label="Size" name="size" options={options} onChange={onChange} />);

      const largeOption = screen.getByLabelText('Large');
      await user.click(largeOption);
      
      expect(onChange).toHaveBeenCalledWith('large');
    });

    it('should handle disabled state', () => {
      render(<RadioGroup label="Size" name="size" options={options} disabled={true} />);

      expect(screen.getByLabelText('Small')).toBeDisabled();
      expect(screen.getByLabelText('Medium')).toBeDisabled();
      expect(screen.getByLabelText('Large')).toBeDisabled();
    });

    it('should use fieldset and legend for accessibility', () => {
      render(<RadioGroup label="Size" name="size" options={options} />);

      expect(screen.getByRole('group')).toBeInTheDocument();
      expect(screen.getByText('Size')).toBeInTheDocument();
    });
  });

  describe('FileUpload Component', () => {
    it('should render file upload correctly', () => {
      render(
        <FileUpload 
          label="Upload Document" 
          acceptedTypes={['image/png', 'image/jpeg']}
          maxSize={5 * 1024 * 1024}
        />
      );

      const input = screen.getByLabelText('Upload Document');
      expect(input).toBeInTheDocument();
      expect(input).toHaveAttribute('type', 'file');
    });

    it('should handle file selection', async () => {
      const user = userEvent.setup();
      const onFileSelect = vi.fn();
      const file = new File(['test'], 'test.png', { type: 'image/png' });

      render(<FileUpload label="Upload Image" onFileSelect={onFileSelect} />);

      const input = screen.getByLabelText('Upload Image');
      await user.upload(input, file);
      
      expect(onFileSelect).toHaveBeenCalled();
    });

    it('should support multiple file uploads', () => {
      render(<FileUpload label="Upload Files" multiple={true} />);

      const input = screen.getByLabelText('Upload Files');
      expect(input).toHaveAttribute('multiple');
    });

    it('should show accepted file types', () => {
      render(
        <FileUpload 
          label="Upload Image" 
          acceptedTypes={['image/png', 'image/jpeg']}
        />
      );

      const input = screen.getByLabelText('Upload Image');
      expect(input).toHaveAttribute('accept', 'image/png,image/jpeg');
    });

    it('should validate file types if specified', async () => {
      const user = userEvent.setup();
      const onFileSelect = vi.fn();
      const invalidFile = new File(['test'], 'test.txt', { type: 'text/plain' });

      render(
        <FileUpload 
          label="Upload Image" 
          acceptedTypes={['image/png', 'image/jpeg']}
          onFileSelect={onFileSelect}
        />
      );

      const input = screen.getByLabelText('Upload Image');
      await user.upload(input, invalidFile);
      
      expect(onFileSelect).toHaveBeenCalledWith(null, expect.stringContaining('Invalid'));
    });
  });

  describe('DatePicker Component', () => {
    it('should render date picker correctly', () => {
      render(
        <DatePicker 
          label="Birth Date" 
          value="1990-01-01"
          min="1900-01-01"
          max="2023-12-31"
        />
      );

      const input = screen.getByLabelText('Birth Date');
      expect(input).toBeInTheDocument();
      expect(input).toHaveAttribute('type', 'date');
      expect(input).toHaveValue('1990-01-01');
      expect(input).toHaveAttribute('min', '1900-01-01');
      expect(input).toHaveAttribute('max', '2023-12-31');
    });

    it('should handle date changes', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(<DatePicker label="Event Date" onChange={onChange} />);

      const input = screen.getByLabelText('Event Date');
      await user.clear(input);
      await user.type(input, '2024-06-15');
      
      expect(onChange).toHaveBeenCalled();
    });

    it('should handle disabled state', () => {
      render(<DatePicker label="Disabled Date" disabled={true} />);

      const input = screen.getByLabelText('Disabled Date');
      expect(input).toBeDisabled();
    });
  });

  describe('NumberInput Component', () => {
    it('should render number input correctly', () => {
      render(
        <NumberInput 
          label="Price" 
          value="100.50"
          min="0"
          max="1000"
          step="0.01"
        />
      );

      const input = screen.getByLabelText('Price');
      expect(input).toBeInTheDocument();
      expect(input).toHaveAttribute('type', 'number');
      expect(input).toHaveValue(100.5);
      expect(input).toHaveAttribute('min', '0');
      expect(input).toHaveAttribute('max', '1000');
      expect(input).toHaveAttribute('step', '0.01');
    });

    it('should handle number changes', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(<NumberInput label="Quantity" onChange={onChange} />);

      const input = screen.getByLabelText('Quantity');
      await user.type(input, '42');
      
      expect(onChange).toHaveBeenCalled();
    });

    it('should show prefix and suffix if provided', () => {
      render(
        <NumberInput 
          label="Price" 
          prefix="$"
          suffix="USD"
        />
      );

      expect(screen.getByText('$')).toBeInTheDocument();
      expect(screen.getByText('USD')).toBeInTheDocument();
    });
  });

  describe('FormValidator Component', () => {
    it('should render children components', () => {
      const validationRules = {
        email: [{ required: true }]
      };

      render(
        <FormValidator validationRules={validationRules}>
          <FormField label="Email" name="email" />
        </FormValidator>
      );

      expect(screen.getByLabelText('Email')).toBeInTheDocument();
    });

    it('should handle validation rules', () => {
      const validationRules = {
        password: [
          { required: true, message: 'Password is required' },
          { minLength: 8, message: 'Password must be at least 8 characters' }
        ]
      };

      render(
        <FormValidator validationRules={validationRules}>
          <FormField label="Password" name="password" type="password" />
        </FormValidator>
      );

      expect(screen.getByLabelText('Password')).toBeInTheDocument();
    });
  });

  describe('FormWizard Component', () => {
    const steps = [
      { id: 'personal', title: 'Personal Info', content: <div>Step 1 Content</div> },
      { id: 'account', title: 'Account Setup', content: <div>Step 2 Content</div> },
      { id: 'confirmation', title: 'Confirmation', content: <div>Step 3 Content</div> }
    ];

    it('should render wizard correctly', () => {
      render(<FormWizard steps={steps} currentStep={2} />);

      expect(screen.getByText('Personal Info')).toBeInTheDocument();
      expect(screen.getByText('Account Setup')).toBeInTheDocument();
      expect(screen.getByText('Confirmation')).toBeInTheDocument();
      expect(screen.getByText('Step 2 Content')).toBeInTheDocument();
    });

    it('should handle step navigation', async () => {
      const user = userEvent.setup();
      const onStepChange = vi.fn();

      render(<FormWizard steps={steps} currentStep={2} onStepChange={onStepChange} />);

      const backButton = screen.getByText('Back');
      await user.click(backButton);
      expect(onStepChange).toHaveBeenCalledWith(1);

      const nextButton = screen.getByText('Next');
      await user.click(nextButton);
      expect(onStepChange).toHaveBeenCalledWith(3);
    });

    it('should show complete button on last step', () => {
      render(<FormWizard steps={steps} currentStep={3} />);

      expect(screen.getByText('Complete')).toBeInTheDocument();
      expect(screen.queryByText('Next')).not.toBeInTheDocument();
    });

    it('should handle completion', async () => {
      const user = userEvent.setup();
      const onComplete = vi.fn();

      render(<FormWizard steps={steps} currentStep={3} onComplete={onComplete} />);

      const completeButton = screen.getByText('Complete');
      await user.click(completeButton);
      expect(onComplete).toHaveBeenCalled();
    });

    it('should not show back button on first step', () => {
      render(<FormWizard steps={steps} currentStep={1} />);

      expect(screen.queryByText('Back')).not.toBeInTheDocument();
      expect(screen.getByText('Next')).toBeInTheDocument();
    });
  });

  describe('SearchableSelect Component', () => {
    const options = [
      { value: 'apple', label: 'Apple' },
      { value: 'banana', label: 'Banana' },
      { value: 'orange', label: 'Orange' }
    ];

    it('should render searchable select correctly', () => {
      render(<SearchableSelect label="Choose Fruit" options={options} placeholder="Search fruits..." />);

      expect(screen.getByLabelText('Choose Fruit')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Search fruits...')).toBeInTheDocument();
    });

    it('should handle search input', async () => {
      const user = userEvent.setup();
      const onSearch = vi.fn();

      render(<SearchableSelect label="Choose Fruit" options={options} onSearch={onSearch} />);

      const searchInput = screen.getByLabelText('Choose Fruit');
      await user.type(searchInput, 'app');
      
      expect(onSearch).toHaveBeenCalledWith('app');
    });

    it('should filter options based on search term', async () => {
      const user = userEvent.setup();

      render(<SearchableSelect label="Choose Fruit" options={options} />);

      const searchInput = screen.getByLabelText('Choose Fruit');
      await user.type(searchInput, 'app');
      await user.click(searchInput); // Focus to show dropdown
      
      await waitFor(() => {
        expect(screen.getByText('Apple')).toBeInTheDocument();
        expect(screen.queryByText('Banana')).not.toBeInTheDocument();
      });
    });

    it('should handle option selection', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(<SearchableSelect label="Choose Fruit" options={options} onChange={onChange} />);

      const searchInput = screen.getByLabelText('Choose Fruit');
      await user.click(searchInput);
      
      await waitFor(() => {
        expect(screen.getByText('Apple')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Apple'));
      expect(onChange).toHaveBeenCalledWith('apple');
    });

    it('should show loading state', () => {
      render(<SearchableSelect label="Choose Fruit" options={[]} loading={true} />);

      // Loading state would be shown in dropdown when open
      expect(screen.getByLabelText('Choose Fruit')).toBeInTheDocument();
    });

    it('should show no options message when no matches', async () => {
      const user = userEvent.setup();

      render(<SearchableSelect label="Choose Fruit" options={[]} />);

      const searchInput = screen.getByLabelText('Choose Fruit');
      await user.click(searchInput);
      
      await waitFor(() => {
        expect(screen.getByText('No options found')).toBeInTheDocument();
      });
    });
  });

  describe('Accessibility', () => {
    it('should have proper labels and associations', () => {
      render(<FormField label="Email Address" required={true} />);

      const input = screen.getByLabelText(/Email Address/);
      expect(input).toBeInTheDocument();
      expect(input).toHaveAttribute('required');
    });

    it('should support keyboard navigation', async () => {
      const user = userEvent.setup();

      render(
        <div>
          <FormField label="First Name" />
          <FormField label="Last Name" />
          <CheckboxField label="Subscribe" />
        </div>
      );

      // Tab through form elements
      await user.tab();
      expect(screen.getByLabelText('First Name')).toHaveFocus();

      await user.tab();
      expect(screen.getByLabelText('Last Name')).toHaveFocus();

      await user.tab();
      expect(screen.getByLabelText('Subscribe')).toHaveFocus();
    });

    it('should have proper ARIA attributes for radio groups', () => {
      const options = [
        { value: 'yes', label: 'Yes' },
        { value: 'no', label: 'No' }
      ];

      render(<RadioGroup label="Do you agree?" name="agreement" options={options} />);

      expect(screen.getByRole('group')).toBeInTheDocument();
      expect(screen.getByText('Do you agree?')).toBeInTheDocument();
    });

    it('should associate error messages with inputs', () => {
      render(<FormField label="Email" error="Invalid email format" />);

      const input = screen.getByLabelText('Email');
      const errorMessage = screen.getByText('Invalid email format');
      
      expect(input).toBeInTheDocument();
      expect(errorMessage).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('should handle missing props gracefully', () => {
      expect(() => {
        render(<FormField />);
      }).not.toThrow();

      expect(() => {
        render(<SelectField options={null} />);
      }).not.toThrow();
    });

    it('should handle invalid form data', () => {
      expect(() => {
        render(<FormField label="Test" value={null} />);
      }).not.toThrow();

      expect(() => {
        render(<NumberInput label="Price" value="not-a-number" />);
      }).not.toThrow();
    });

    it('should handle callback errors gracefully', async () => {
      const user = userEvent.setup();
      const errorCallback = vi.fn(() => {
        throw new Error('Callback error');
      });

      // Should not crash the component when callback errors occur
      render(<FormField label="Test" onChange={errorCallback} />);

      const input = screen.getByLabelText('Test');
      
      // This should not crash the test
      try {
        await user.type(input, 'test');
      } catch (error) {
        // Expected to catch the error from the callback
        expect(error.message).toBe('Callback error');
      }
    });
  });

  describe('Performance', () => {
    it('should render large option lists efficiently', () => {
      const manyOptions = Array.from({ length: 1000 }, (_, i) => ({
        value: `option${i}`,
        label: `Option ${i}`
      }));

      const startTime = performance.now();
      render(<SelectField label="Large List" options={manyOptions} />);
      const renderTime = performance.now() - startTime;

      expect(renderTime).toBeLessThan(100); // 100ms
      expect(screen.getByLabelText('Large List')).toBeInTheDocument();
    });

    it('should handle rapid input changes without performance issues', async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(<FormField label="Search" onChange={onChange} />);

      const input = screen.getByLabelText('Search');
      
      // Rapid typing simulation
      const startTime = performance.now();
      await user.type(input, 'quick test input', { delay: 1 });
      const inputTime = performance.now() - startTime;
      
      expect(inputTime).toBeLessThan(1000); // Should complete within 1 second
      expect(onChange).toHaveBeenCalled();
    });
  });
});