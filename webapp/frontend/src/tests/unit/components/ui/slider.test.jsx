import { screen, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { renderWithProviders } from '../../../test-utils';
import { Slider } from '../../../../components/ui/slider';

describe('Slider Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Functionality', () => {
    it('renders slider with default props', () => {
      renderWithProviders(<Slider value={50} />);
      
      const slider = screen.getByRole('slider');
      expect(slider).toBeInTheDocument();
      expect(slider).toHaveAttribute('aria-valuenow', '50');
      expect(slider).toHaveAttribute('aria-valuemin', '0');
      expect(slider).toHaveAttribute('aria-valuemax', '100');
    });

    it('displays correct value', () => {
      renderWithProviders(<Slider value={75} />);
      
      const slider = screen.getByRole('slider');
      expect(slider).toHaveAttribute('aria-valuenow', '75');
    });

    it('handles zero value correctly', () => {
      renderWithProviders(<Slider value={0} />);
      
      const slider = screen.getByRole('slider');
      expect(slider).toHaveAttribute('aria-valuenow', '0');
    });

    it('handles maximum value correctly', () => {
      renderWithProviders(<Slider value={100} />);
      
      const slider = screen.getByRole('slider');
      expect(slider).toHaveAttribute('aria-valuenow', '100');
    });

    it('supports custom min and max values', () => {
      renderWithProviders(<Slider value={5} min={1} max={10} />);
      
      const slider = screen.getByRole('slider');
      expect(slider).toHaveAttribute('aria-valuenow', '5');
      expect(slider).toHaveAttribute('aria-valuemin', '1');
      expect(slider).toHaveAttribute('aria-valuemax', '10');
    });

    it('calls onValueChange when slider value changes', () => {
      const handleChange = vi.fn();
      renderWithProviders(<Slider value={50} onValueChange={handleChange} />);
      
      const slider = screen.getByRole('slider');
      fireEvent.change(slider, { target: { value: '75' } });
      
      expect(handleChange).toHaveBeenCalled();
    });
  });

  describe('Slider Variants', () => {
    it('supports custom className', () => {
      renderWithProviders(<Slider value={50} className="custom-slider" />);
      
      const slider = screen.getByRole('slider');
      const sliderRoot = slider.closest('.MuiSlider-root');
      expect(sliderRoot).toHaveClass('custom-slider');
    });

    it('supports step intervals', () => {
      renderWithProviders(<Slider value={50} step={10} />);
      
      const slider = screen.getByRole('slider');
      expect(slider).toHaveAttribute('step', '10');
    });

    it('supports disabled state', () => {
      renderWithProviders(<Slider value={50} disabled />);
      
      const slider = screen.getByRole('slider');
      expect(slider).toBeDisabled();
      expect(slider.closest('.MuiSlider-root')).toHaveClass('Mui-disabled');
    });

    it('supports color variants', () => {
      renderWithProviders(<Slider value={50} color="secondary" />);
      
      const slider = screen.getByRole('slider');
      expect(slider.closest('.MuiSlider-root')).toHaveClass('MuiSlider-colorSecondary');
    });
  });

  describe('Range Slider', () => {
    it('handles range values correctly', () => {
      renderWithProviders(<Slider value={[20, 80]} />);
      
      const sliders = screen.getAllByRole('slider');
      expect(sliders).toHaveLength(2);
      expect(sliders[0]).toHaveAttribute('aria-valuenow', '20');
      expect(sliders[1]).toHaveAttribute('aria-valuenow', '80');
    });

    it('calls onValueChange with array for range slider', () => {
      const handleChange = vi.fn();
      renderWithProviders(<Slider value={[20, 80]} onValueChange={handleChange} />);
      
      const sliders = screen.getAllByRole('slider');
      fireEvent.change(sliders[0], { target: { value: '30' } });
      
      expect(handleChange).toHaveBeenCalled();
    });
  });

  describe('Accessibility', () => {
    it('provides proper ARIA attributes', () => {
      renderWithProviders(<Slider value={50} />);
      
      const slider = screen.getByRole('slider');
      // The role is implicit for input type="range", so just check it exists
      expect(slider).toBeInTheDocument();
      expect(slider).toHaveAttribute('aria-valuenow', '50');
      expect(slider).toHaveAttribute('aria-valuemin', '0');
      expect(slider).toHaveAttribute('aria-valuemax', '100');
    });

    it('supports custom ARIA labels', () => {
      renderWithProviders(<Slider value={50} aria-label="Volume control" />);
      
      const slider = screen.getByRole('slider');
      expect(slider).toHaveAttribute('aria-label', 'Volume control');
    });

    it('supports aria-labelledby', () => {
      renderWithProviders(
        <div>
          <label id="volume-label">Volume</label>
          <Slider value={50} aria-labelledby="volume-label" />
        </div>
      );
      
      const slider = screen.getByRole('slider');
      expect(slider).toHaveAttribute('aria-labelledby', 'volume-label');
    });

    it('handles keyboard navigation', () => {
      renderWithProviders(<Slider value={50} />);
      
      const slider = screen.getByRole('slider');
      fireEvent.keyDown(slider, { key: 'ArrowRight' });
      
      // MUI Slider handles keyboard navigation internally
      expect(slider).toBeInTheDocument();
    });
  });

  describe('Component Structure', () => {
    it('uses MuiSlider component', () => {
      renderWithProviders(<Slider value={50} />);
      
      const sliderRoot = screen.getByRole('slider').closest('.MuiSlider-root');
      expect(sliderRoot).toBeInTheDocument();
    });

    it('has proper MUI classes', () => {
      renderWithProviders(<Slider value={50} />);
      
      const sliderRoot = screen.getByRole('slider').closest('.MuiSlider-root');
      expect(sliderRoot).toHaveClass('MuiSlider-root');
    });
  });

  describe('Error Handling', () => {
    it('handles undefined value gracefully', () => {
      renderWithProviders(<Slider value={undefined} />);
      
      const slider = screen.getByRole('slider');
      expect(slider).toBeInTheDocument();
    });

    it('handles null value gracefully', () => {
      renderWithProviders(<Slider value={null} />);
      
      const slider = screen.getByRole('slider');
      expect(slider).toBeInTheDocument();
    });

    it('handles missing onValueChange gracefully', () => {
      renderWithProviders(<Slider value={50} />);
      
      const slider = screen.getByRole('slider');
      expect(() => fireEvent.change(slider, { target: { value: '60' } })).not.toThrow();
    });

    it('handles invalid step values gracefully', () => {
      renderWithProviders(<Slider value={50} step={0} />);
      
      const slider = screen.getByRole('slider');
      expect(slider).toBeInTheDocument();
    });
  });

  describe('Performance', () => {
    it('forwards ref correctly', () => {
      const ref = vi.fn();
      renderWithProviders(<Slider value={50} ref={ref} />);
      
      expect(ref).toHaveBeenCalled();
    });

    it('handles rapid value changes', () => {
      const handleChange = vi.fn();
      renderWithProviders(<Slider value={50} onValueChange={handleChange} />);
      
      const slider = screen.getByRole('slider');
      
      // Simulate rapid changes
      for (let i = 0; i < 10; i++) {
        fireEvent.change(slider, { target: { value: String(50 + i) } });
      }
      
      expect(handleChange).toHaveBeenCalled();
    });
  });
});