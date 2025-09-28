import React from 'react';
import { render, screen } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { describe, it, expect } from 'vitest';
import TradingSignal, { TradingSignalWithPerformance } from '../../../components/TradingSignal';

const theme = createTheme();

const renderWithTheme = (component) => {
  return render(
    <ThemeProvider theme={theme}>
      {component}
    </ThemeProvider>
  );
};

describe('TradingSignal Component', () => {
  describe('Basic Signal Display', () => {
    it('renders BUY signal with correct styling', () => {
      renderWithTheme(
        <TradingSignal
          signal="BUY"
          confidence={0.85}
          size="medium"
          variant="chip"
        />
      );

      expect(screen.getByText('BUY')).toBeInTheDocument();
    });

    it('renders SELL signal with correct styling', () => {
      renderWithTheme(
        <TradingSignal
          signal="SELL"
          confidence={0.75}
          size="medium"
          variant="chip"
        />
      );

      expect(screen.getByText('SELL')).toBeInTheDocument();
    });

    it('renders HOLD signal with correct styling', () => {
      renderWithTheme(
        <TradingSignal
          signal="HOLD"
          confidence={0.70}
          size="medium"
          variant="chip"
        />
      );

      expect(screen.getByText('HOLD')).toBeInTheDocument();
    });

    it('renders STRONG_BUY signal correctly', () => {
      renderWithTheme(
        <TradingSignal
          signal="STRONG_BUY"
          confidence={0.95}
          size="medium"
          variant="chip"
        />
      );

      expect(screen.getByText('STRONG BUY')).toBeInTheDocument();
    });

    it('renders STRONG_SELL signal correctly', () => {
      renderWithTheme(
        <TradingSignal
          signal="STRONG_SELL"
          confidence={0.90}
          size="medium"
          variant="chip"
        />
      );

      expect(screen.getByText('STRONG SELL')).toBeInTheDocument();
    });

    it('handles unknown signal types gracefully', () => {
      renderWithTheme(
        <TradingSignal
          signal="UNKNOWN"
          confidence={0.50}
          size="medium"
          variant="chip"
        />
      );

      expect(screen.getByText('N/A')).toBeInTheDocument();
    });
  });

  describe('Confidence Display', () => {
    it('shows confidence percentage when enabled', () => {
      renderWithTheme(
        <TradingSignal
          signal="BUY"
          confidence={0.85}
          size="medium"
          variant="chip"
          showConfidence={true}
        />
      );

      expect(screen.getByText('85%')).toBeInTheDocument();
    });

    it('hides confidence when disabled', () => {
      renderWithTheme(
        <TradingSignal
          signal="BUY"
          confidence={0.85}
          size="medium"
          variant="chip"
          showConfidence={false}
        />
      );

      expect(screen.queryByText('85%')).not.toBeInTheDocument();
    });
  });

  describe('Variant Display', () => {
    it('renders chip variant correctly', () => {
      const { container } = renderWithTheme(
        <TradingSignal
          signal="BUY"
          confidence={0.85}
          variant="chip"
        />
      );

      expect(container.querySelector('.MuiChip-root')).toBeInTheDocument();
    });

    it('renders badge variant correctly', () => {
      renderWithTheme(
        <TradingSignal
          signal="BUY"
          confidence={0.85}
          variant="badge"
        />
      );

      expect(screen.getByText('BUY')).toBeInTheDocument();
    });

    it('renders inline variant correctly', () => {
      renderWithTheme(
        <TradingSignal
          signal="BUY"
          confidence={0.85}
          variant="inline"
        />
      );

      expect(screen.getByText('BUY')).toBeInTheDocument();
    });
  });

  describe('Size Variations', () => {
    it('renders small size correctly', () => {
      renderWithTheme(
        <TradingSignal
          signal="BUY"
          confidence={0.85}
          size="small"
          variant="chip"
        />
      );

      expect(screen.getByText('BUY')).toBeInTheDocument();
    });

    it('renders medium size correctly', () => {
      renderWithTheme(
        <TradingSignal
          signal="BUY"
          confidence={0.85}
          size="medium"
          variant="chip"
        />
      );

      expect(screen.getByText('BUY')).toBeInTheDocument();
    });
  });

  describe('Edge Cases', () => {
    it('handles null signal gracefully', () => {
      renderWithTheme(
        <TradingSignal
          signal={null}
          confidence={0.85}
          size="medium"
          variant="chip"
        />
      );

      expect(screen.getByText('N/A')).toBeInTheDocument();
    });

    it('handles undefined signal gracefully', () => {
      renderWithTheme(
        <TradingSignal
          signal={undefined}
          confidence={0.85}
          size="medium"
          variant="chip"
        />
      );

      expect(screen.getByText('N/A')).toBeInTheDocument();
    });

    it('handles case-insensitive signals', () => {
      renderWithTheme(
        <TradingSignal
          signal="buy"
          confidence={0.85}
          size="medium"
          variant="chip"
        />
      );

      expect(screen.getByText('BUY')).toBeInTheDocument();
    });

    it('returns null for invalid variant', () => {
      const { container } = renderWithTheme(
        <TradingSignal
          signal="BUY"
          confidence={0.85}
          variant="invalid"
        />
      );

      expect(container.firstChild).toBeNull();
    });
  });
});

describe('TradingSignalWithPerformance Component', () => {
  it('renders signal with performance indicator', () => {
    renderWithTheme(
      <TradingSignalWithPerformance
        signal="BUY"
        confidence={0.85}
        performance={5.2}
        size="medium"
      />
    );

    expect(screen.getByText('BUY')).toBeInTheDocument();
    expect(screen.getByText('+5.2%')).toBeInTheDocument();
  });

  it('renders negative performance correctly', () => {
    renderWithTheme(
      <TradingSignalWithPerformance
        signal="SELL"
        confidence={0.75}
        performance={-3.1}
        size="medium"
      />
    );

    expect(screen.getByText('SELL')).toBeInTheDocument();
    expect(screen.getByText('-3.1%')).toBeInTheDocument();
  });

  it('handles null performance gracefully', () => {
    renderWithTheme(
      <TradingSignalWithPerformance
        signal="HOLD"
        confidence={0.70}
        performance={null}
        size="medium"
      />
    );

    expect(screen.getByText('HOLD')).toBeInTheDocument();
    expect(screen.queryByText('%')).not.toBeInTheDocument();
  });

  it('shows confidence when enabled', () => {
    renderWithTheme(
      <TradingSignalWithPerformance
        signal="BUY"
        confidence={0.85}
        performance={2.5}
        size="medium"
      />
    );

    expect(screen.getByText('85%')).toBeInTheDocument();
  });
});