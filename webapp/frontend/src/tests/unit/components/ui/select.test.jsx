import { screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { renderWithProviders } from '../../../test-utils';
import { Select, SelectItem } from '../../../../components/ui/select';

describe('Select Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Functionality', () => {
    it('renders select component', () => {
      renderWithProviders(
        <Select value="option1">
          <SelectItem value="option1">Option 1</SelectItem>
          <SelectItem value="option2">Option 2</SelectItem>
        </Select>
      );
      
      const select = screen.getByRole('combobox');
      expect(select).toBeInTheDocument();
      expect(select).toHaveTextContent('Option 1');
    });

    it('handles empty value correctly', () => {
      renderWithProviders(
        <Select value="">
          <SelectItem value="">Select an option</SelectItem>
          <SelectItem value="option1">Option 1</SelectItem>
        </Select>
      );
      
      const select = screen.getByRole('combobox');
      expect(select).toBeInTheDocument();
    });

    it('calls onValueChange when value changes', () => {
      const handleChange = vi.fn();
      renderWithProviders(
        <Select value="option1" onValueChange={handleChange}>
          <SelectItem value="option1">Option 1</SelectItem>
          <SelectItem value="option2">Option 2</SelectItem>
        </Select>
      );
      
      const selectElement = screen.getByRole('combobox');
      fireEvent.mouseDown(selectElement);
      
      const option2 = screen.getByRole('option', { name: 'Option 2' });
      fireEvent.click(option2);
      
      expect(handleChange).toHaveBeenCalledWith('option2');
    });

    it('supports custom className', () => {
      renderWithProviders(
        <Select value="option1" className="custom-select">
          <SelectItem value="option1">Option 1</SelectItem>
        </Select>
      );
      
      const formControl = screen.getByRole('combobox').closest('.MuiFormControl-root');
      expect(formControl).toHaveClass('custom-select');
    });
  });

  describe('SelectItem Component', () => {
    it('renders select items correctly', () => {
      renderWithProviders(
        <Select value="option1">
          <SelectItem value="option1">Option 1</SelectItem>
          <SelectItem value="option2">Option 2</SelectItem>
        </Select>
      );
      
      const selectElement = screen.getByRole('combobox');
      fireEvent.mouseDown(selectElement);
      
      expect(screen.getByRole('option', { name: 'Option 1' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'Option 2' })).toBeInTheDocument();
    });

    it('applies custom className to select items', () => {
      renderWithProviders(
        <Select value="option1">
          <SelectItem value="option1" className="custom-item">Option 1</SelectItem>
        </Select>
      );
      
      const selectElement = screen.getByRole('combobox');
      fireEvent.mouseDown(selectElement);
      
      const option = screen.getByRole('option', { name: 'Option 1' });
      expect(option).toHaveClass('custom-item');
    });
  });

  describe('Accessibility', () => {
    it('has proper ARIA attributes', () => {
      renderWithProviders(
        <Select value="option1">
          <SelectItem value="option1">Option 1</SelectItem>
        </Select>
      );
      
      const select = screen.getByRole('combobox');
      expect(select).toHaveAttribute('aria-haspopup', 'listbox');
      expect(select).toHaveAttribute('aria-expanded', 'false');
    });

    it('expands dropdown with proper ARIA states', () => {
      renderWithProviders(
        <Select value="option1">
          <SelectItem value="option1">Option 1</SelectItem>
          <SelectItem value="option2">Option 2</SelectItem>
        </Select>
      );
      
      const select = screen.getByRole('combobox');
      fireEvent.mouseDown(select);
      
      expect(select).toHaveAttribute('aria-expanded', 'true');
    });

    it('supports keyboard navigation', () => {
      renderWithProviders(
        <Select value="option1">
          <SelectItem value="option1">Option 1</SelectItem>
          <SelectItem value="option2">Option 2</SelectItem>
        </Select>
      );
      
      const select = screen.getByRole('combobox');
      fireEvent.keyDown(select, { key: 'ArrowDown' });
      
      expect(select).toHaveAttribute('aria-expanded', 'true');
    });
  });

  describe('Component Structure', () => {
    it('uses MUI FormControl wrapper', () => {
      renderWithProviders(
        <Select value="option1">
          <SelectItem value="option1">Option 1</SelectItem>
        </Select>
      );
      
      const formControl = screen.getByRole('combobox').closest('.MuiFormControl-root');
      expect(formControl).toBeInTheDocument();
      expect(formControl).toHaveClass('MuiFormControl-root');
    });

    it('uses MUI Select component', () => {
      renderWithProviders(
        <Select value="option1">
          <SelectItem value="option1">Option 1</SelectItem>
        </Select>
      );
      
      const select = screen.getByRole('combobox').closest('.MuiSelect-select');
      expect(select).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('handles undefined value gracefully', () => {
      renderWithProviders(
        <Select value={undefined}>
          <SelectItem value="option1">Option 1</SelectItem>
        </Select>
      );
      
      const select = screen.getByRole('combobox');
      expect(select).toBeInTheDocument();
    });

    it('handles null value gracefully', () => {
      renderWithProviders(
        <Select value={null}>
          <SelectItem value="option1">Option 1</SelectItem>
        </Select>
      );
      
      const select = screen.getByRole('combobox');
      expect(select).toBeInTheDocument();
    });

    it('handles missing onValueChange gracefully', () => {
      renderWithProviders(
        <Select value="option1">
          <SelectItem value="option1">Option 1</SelectItem>
          <SelectItem value="option2">Option 2</SelectItem>
        </Select>
      );
      
      const selectElement = screen.getByRole('combobox');
      fireEvent.mouseDown(selectElement);
      
      const option2 = screen.getByRole('option', { name: 'Option 2' });
      expect(() => fireEvent.click(option2)).not.toThrow();
    });
  });
});