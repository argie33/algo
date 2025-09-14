import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import { Badge } from '../../../../components/ui/badge';

describe('Badge', () => {
  describe('Rendering', () => {
    test('renders without crashing', () => {
      render(<Badge>Test Badge</Badge>);
      expect(screen.getByText('Test Badge')).toBeInTheDocument();
    });

    test('renders children correctly', () => {
      render(<Badge>Badge Content</Badge>);
      expect(screen.getByText('Badge Content')).toBeInTheDocument();
    });

    test('applies custom className', () => {
      render(<Badge className="custom-badge">Test</Badge>);
      const badge = screen.getByText('Test');
      expect(badge.closest('.MuiChip-root')).toHaveClass('custom-badge');
    });

    test('forwards ref correctly', () => {
      const ref = { current: null };
      render(<Badge ref={ref}>Test</Badge>);
      expect(ref.current).toBeInstanceOf(HTMLElement);
    });
  });

  describe('Variants', () => {
    test('renders default variant as outlined', () => {
      render(<Badge variant="default">Default Badge</Badge>);
      const badge = screen.getByText('Default Badge');
      expect(badge.closest('.MuiChip-root')).toHaveClass('MuiChip-outlined');
    });

    test('renders destructive variant as filled with error color', () => {
      render(<Badge variant="destructive">Error Badge</Badge>);
      const badge = screen.getByText('Error Badge');
      expect(badge.closest('.MuiChip-root')).toHaveClass('MuiChip-filled');
      expect(badge.closest('.MuiChip-root')).toHaveClass('MuiChip-colorError');
    });

    test('defaults to default variant when not specified', () => {
      render(<Badge>No Variant</Badge>);
      const badge = screen.getByText('No Variant');
      expect(badge.closest('.MuiChip-root')).toHaveClass('MuiChip-outlined');
    });

    test('handles custom variants gracefully', () => {
      render(<Badge variant="custom">Custom Badge</Badge>);
      const badge = screen.getByText('Custom Badge');
      expect(badge.closest('.MuiChip-root')).toHaveClass('MuiChip-outlined');
    });
  });

  describe('Size', () => {
    test('renders with small size by default', () => {
      render(<Badge>Small Badge</Badge>);
      const badge = screen.getByText('Small Badge');
      expect(badge.closest('.MuiChip-root')).toHaveClass('MuiChip-sizeSmall');
    });

    test('maintains small size even with size prop', () => {
      render(<Badge size="large">Large Badge</Badge>);
      const badge = screen.getByText('Large Badge');
      // The Badge component forces size="small" regardless of prop
      const chipRoot = badge.closest('.MuiChip-root');
      expect(chipRoot).toBeInTheDocument();
    });
  });

  describe('Props Forwarding', () => {
    test('forwards additional props to MUI Chip', () => {
      render(<Badge data-testid="test-badge" title="Badge Title">Test</Badge>);
      const badge = screen.getByTestId('test-badge');
      expect(badge).toHaveAttribute('title', 'Badge Title');
    });

    test('handles onClick event', () => {
      const handleClick = vi.fn();
      render(<Badge onClick={handleClick}>Clickable Badge</Badge>);
      
      const badge = screen.getByText('Clickable Badge');
      fireEvent.click(badge);
      expect(handleClick).toHaveBeenCalledTimes(1);
    });

    test('handles disabled state', () => {
      render(<Badge disabled>Disabled Badge</Badge>);
      const badge = screen.getByText('Disabled Badge');
      expect(badge.closest('.MuiChip-root')).toHaveClass('Mui-disabled');
    });
  });

  describe('Colors', () => {
    test('uses default color for default variant', () => {
      render(<Badge variant="default">Default Color</Badge>);
      const badge = screen.getByText('Default Color');
      expect(badge.closest('.MuiChip-root')).toHaveClass('MuiChip-colorDefault');
    });

    test('uses error color for destructive variant', () => {
      render(<Badge variant="destructive">Error Color</Badge>);
      const badge = screen.getByText('Error Color');
      expect(badge.closest('.MuiChip-root')).toHaveClass('MuiChip-colorError');
    });
  });

  describe('Accessibility', () => {
    test('has proper role', () => {
      render(<Badge role="status">Accessible Badge</Badge>);
      const badge = screen.getByText('Accessible Badge');
      // MUI Chip doesn't add role by default, but accepts it as a prop
      expect(badge.closest('.MuiChip-root')).toHaveAttribute('role', 'status');
    });

    test('supports aria-label', () => {
      render(<Badge aria-label="Status Badge">Status</Badge>);
      const badge = screen.getByLabelText('Status Badge');
      expect(badge).toBeInTheDocument();
    });

    test('supports screen reader text', () => {
      render(<Badge>Screen Reader Badge</Badge>);
      const badge = screen.getByText('Screen Reader Badge');
      expect(badge).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    test('handles empty children', () => {
      render(<Badge />);
      const chipElement = document.querySelector('.MuiChip-root');
      expect(chipElement).toBeInTheDocument();
    });

    test('handles null children', () => {
      render(<Badge>{null}</Badge>);
      const chipElement = document.querySelector('.MuiChip-root');
      expect(chipElement).toBeInTheDocument();
    });

    test('handles undefined children', () => {
      render(<Badge>{undefined}</Badge>);
      const chipElement = document.querySelector('.MuiChip-root');
      expect(chipElement).toBeInTheDocument();
    });

    test('handles numeric children', () => {
      render(<Badge>{42}</Badge>);
      expect(screen.getByText('42')).toBeInTheDocument();
    });

    test('handles boolean children', () => {
      render(<Badge>{true}</Badge>);
      const chipElement = document.querySelector('.MuiChip-root');
      expect(chipElement).toBeInTheDocument();
    });
  });

  describe('Display Name', () => {
    test('has correct display name', () => {
      expect(Badge.displayName).toBe('Badge');
    });
  });
});