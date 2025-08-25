import { screen } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { renderWithProviders } from '../../../test-utils';
import { Progress } from '../../../../components/ui/progress';

describe('Progress Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Functionality', () => {
    it('renders determinate progress bar with value', () => {
      renderWithProviders(<Progress value={50} />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toBeInTheDocument();
      expect(progressBar).toHaveAttribute('aria-valuenow', '50');
      expect(progressBar).toHaveClass('MuiLinearProgress-determinate');
    });

    it('renders indeterminate progress bar without value', () => {
      renderWithProviders(<Progress />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toBeInTheDocument();
      expect(progressBar).not.toHaveAttribute('aria-valuenow');
      expect(progressBar).toHaveClass('MuiLinearProgress-indeterminate');
    });

    it('handles zero value correctly', () => {
      renderWithProviders(<Progress value={0} />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-valuenow', '0');
    });

    it('handles maximum value correctly', () => {
      renderWithProviders(<Progress value={100} />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-valuenow', '100');
    });

    it('supports custom className', () => {
      renderWithProviders(<Progress value={50} className="custom-progress" />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveClass('custom-progress');
    });

    it('supports MUI color props', () => {
      renderWithProviders(<Progress value={50} color="secondary" />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveClass('MuiLinearProgress-colorSecondary');
    });

    it('forwards ref correctly', () => {
      const ref = vi.fn();
      renderWithProviders(<Progress value={50} ref={ref} />);
      
      expect(ref).toHaveBeenCalled();
    });
  });

  describe('Accessibility', () => {
    it('provides proper ARIA attributes for determinate progress', () => {
      renderWithProviders(<Progress value={75} />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('role', 'progressbar');
      expect(progressBar).toHaveAttribute('aria-valuenow', '75');
      expect(progressBar).toHaveAttribute('aria-valuemin', '0');
      expect(progressBar).toHaveAttribute('aria-valuemax', '100');
    });

    it('provides proper ARIA attributes for indeterminate progress', () => {
      renderWithProviders(<Progress />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('role', 'progressbar');
      expect(progressBar).not.toHaveAttribute('aria-valuenow');
    });

    it('supports custom ARIA labels', () => {
      renderWithProviders(<Progress value={50} aria-label="Loading content" />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveAttribute('aria-label', 'Loading content');
    });
  });

  describe('Component Structure', () => {
    it('uses MuiLinearProgress classes', () => {
      renderWithProviders(<Progress value={50} />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveClass('MuiLinearProgress-root');
    });

    it('applies determinate variant classes', () => {
      renderWithProviders(<Progress value={50} />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveClass('MuiLinearProgress-determinate');
    });

    it('applies indeterminate variant classes', () => {
      renderWithProviders(<Progress />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toHaveClass('MuiLinearProgress-indeterminate');
    });
  });

  describe('Error Handling', () => {
    it('handles invalid value gracefully', () => {
      renderWithProviders(<Progress value={-10} />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toBeInTheDocument();
    });

    it('handles value over 100 gracefully', () => {
      renderWithProviders(<Progress value={150} />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toBeInTheDocument();
    });

    it('handles non-numeric value gracefully', () => {
      renderWithProviders(<Progress value="invalid" />);
      
      const progressBar = screen.getByRole('progressbar');
      expect(progressBar).toBeInTheDocument();
    });
  });
});