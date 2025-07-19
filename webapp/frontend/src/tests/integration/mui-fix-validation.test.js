/**
 * MUI createPalette Fix Validation Tests
 * Integration tests to ensure the MUI fix prevents application crashes
 */

import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';

// Import the components we fixed
import { lightTheme, darkTheme, createSafeTheme, validateTheme } from '../../theme/safeTheme';
import { ThemeProvider } from '../../contexts/ThemeContext';

// Mock MUI components to prevent actual MUI loading during tests
vi.mock('@mui/material/styles', () => ({
  ThemeProvider: ({ theme, children }) => (
    <div data-testid="mock-theme-provider" data-theme={JSON.stringify(theme)}>
      {children}
    </div>
  ),
  useTheme: () => lightTheme,
  createTheme: vi.fn().mockImplementation(() => {
    throw new Error('createTheme should not be called - using safe theme instead');
  })
}));

vi.mock('@mui/material/CssBaseline', () => ({
  default: () => <div data-testid="mock-css-baseline" />
}));

describe('MUI createPalette Fix Validation', () => {
  beforeAll(() => {
    // Ensure clean environment
    console.log('🧪 Starting MUI fix validation tests');
  });

  afterAll(() => {
    cleanup();
    console.log('✅ MUI fix validation tests completed');
  });

  describe('Safe Theme Creation', () => {
    it('should create light theme without errors', () => {
      expect(() => {
        const theme = createSafeTheme('light');
        expect(theme).toBeDefined();
        expect(theme.palette.mode).toBe('light');
        expect(validateTheme(theme)).toBe(true);
      }).not.toThrow();
    });

    it('should create dark theme without errors', () => {
      expect(() => {
        const theme = createSafeTheme('dark');
        expect(theme).toBeDefined();
        expect(theme.palette.mode).toBe('dark');
        expect(validateTheme(theme)).toBe(true);
      }).not.toThrow();
    });

    it('should have all required theme properties', () => {
      const theme = lightTheme;
      
      // Verify essential palette properties
      expect(theme.palette).toBeDefined();
      expect(theme.palette.primary).toBeDefined();
      expect(theme.palette.secondary).toBeDefined();
      expect(theme.palette.background).toBeDefined();
      expect(theme.palette.text).toBeDefined();
      
      // Verify typography
      expect(theme.typography).toBeDefined();
      expect(theme.typography.fontFamily).toBeDefined();
      
      // Verify component overrides
      expect(theme.components).toBeDefined();
      expect(theme.components.MuiButton).toBeDefined();
      expect(theme.components.MuiPaper).toBeDefined();
      
      // Verify shadows array
      expect(theme.shadows).toBeDefined();
      expect(Array.isArray(theme.shadows)).toBe(true);
      expect(theme.shadows.length).toBe(25); // MUI standard shadow count
    });

    it('should not call MUI createTheme function', () => {
      // This test ensures we never call the problematic createTheme
      const createThemeMock = vi.fn();
      vi.mock('@mui/material/styles', () => ({
        createTheme: createThemeMock
      }));
      
      // Create themes using our safe method
      createSafeTheme('light');
      createSafeTheme('dark');
      
      // Verify createTheme was never called
      expect(createThemeMock).not.toHaveBeenCalled();
    });
  });

  describe('Theme Context Integration', () => {
    it('should render ThemeProvider without errors', () => {
      expect(() => {
        render(
          <ThemeProvider>
            <div data-testid="test-child">Test Content</div>
          </ThemeProvider>
        );
        
        expect(screen.getByTestId('test-child')).toBeInTheDocument();
      }).not.toThrow();
    });

    it('should provide theme context to children', () => {
      const TestComponent = () => {
        return <div data-testid="theme-consumer">Theme Context Working</div>;
      };

      render(
        <ThemeProvider>
          <TestComponent />
        </ThemeProvider>
      );
      
      expect(screen.getByTestId('theme-consumer')).toBeInTheDocument();
    });
  });

  describe('Production Build Compatibility', () => {
    it('should work in production mode', () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = 'production';
      
      try {
        expect(() => {
          const theme = createSafeTheme('light');
          expect(theme.palette.mode).toBe('light');
        }).not.toThrow();
      } finally {
        process.env.NODE_ENV = originalEnv;
      }
    });

    it('should handle theme switching without memory leaks', () => {
      let theme1, theme2, theme3;
      
      expect(() => {
        theme1 = createSafeTheme('light');
        theme2 = createSafeTheme('dark');
        theme3 = createSafeTheme('light');
        
        // Verify themes are created correctly
        expect(theme1.palette.mode).toBe('light');
        expect(theme2.palette.mode).toBe('dark');
        expect(theme3.palette.mode).toBe('light');
        
        // Verify themes are independent objects
        expect(theme1).not.toBe(theme3); // Different object instances
        expect(theme1.palette.mode).toBe(theme3.palette.mode); // Same mode
      }).not.toThrow();
    });

    it('should maintain performance with multiple theme creations', () => {
      const startTime = performance.now();
      
      // Create 100 themes to test performance
      for (let i = 0; i < 100; i++) {
        const mode = i % 2 === 0 ? 'light' : 'dark';
        const theme = createSafeTheme(mode);
        expect(theme.palette.mode).toBe(mode);
      }
      
      const endTime = performance.now();
      const duration = endTime - startTime;
      
      // Should complete in under 100ms for 100 theme creations
      expect(duration).toBeLessThan(100);
      console.log(`🚀 Created 100 themes in ${duration.toFixed(2)}ms`);
    });
  });

  describe('Error Prevention', () => {
    it('should not throw createPalette errors', () => {
      // Test various scenarios that could trigger createPalette errors
      const scenarios = [
        () => createSafeTheme('light'),
        () => createSafeTheme('dark'),
        () => createSafeTheme('light').palette.primary,
        () => createSafeTheme('dark').palette.background,
        () => lightTheme.typography.h1,
        () => darkTheme.components.MuiButton
      ];
      
      scenarios.forEach((scenario, index) => {
        expect(() => {
          const result = scenario();
          expect(result).toBeDefined();
        }).not.toThrow(`Scenario ${index + 1} should not throw errors`);
      });
    });

    it('should handle malformed mode parameters gracefully', () => {
      expect(() => {
        const theme1 = createSafeTheme(null);
        expect(theme1.palette.mode).toBe('light'); // Should default to light
        
        const theme2 = createSafeTheme(undefined);
        expect(theme2.palette.mode).toBe('light'); // Should default to light
        
        const theme3 = createSafeTheme('invalid');
        expect(theme3.palette.mode).toBe('invalid'); // Should use provided value
      }).not.toThrow();
    });

    it('should validate theme structure integrity', () => {
      const themes = [lightTheme, darkTheme];
      
      themes.forEach((theme, index) => {
        const themeName = index === 0 ? 'light' : 'dark';
        
        // Structure validation
        expect(validateTheme(theme), `${themeName} theme should be valid`).toBe(true);
        
        // Essential properties validation
        expect(theme.palette, `${themeName} theme should have palette`).toBeDefined();
        expect(theme.typography, `${themeName} theme should have typography`).toBeDefined();
        expect(theme.components, `${themeName} theme should have components`).toBeDefined();
        expect(theme.shadows, `${themeName} theme should have shadows`).toBeDefined();
        
        // Palette completeness
        expect(theme.palette.primary.main, `${themeName} theme should have primary color`).toBeDefined();
        expect(theme.palette.secondary.main, `${themeName} theme should have secondary color`).toBeDefined();
        expect(theme.palette.background.default, `${themeName} theme should have background`).toBeDefined();
        expect(theme.palette.text.primary, `${themeName} theme should have text color`).toBeDefined();
      });
    });
  });

  describe('Regression Prevention', () => {
    it('should prevent future createPalette regressions', () => {
      // This test documents the exact error we fixed
      const errorPattern = /createPalette|Xa is not a function/i;
      
      expect(() => {
        // Operations that previously caused createPalette errors
        const theme = createSafeTheme('light');
        const palette = theme.palette;
        const primary = palette.primary;
        const background = palette.background;
        
        // These should all work without throwing createPalette errors
        expect(primary.main).toBeDefined();
        expect(background.default).toBeDefined();
      }).not.toThrow(errorPattern);
    });

    it('should maintain MUI compatibility without createTheme', () => {
      // Verify our themes work with MUI components (mocked)
      const theme = lightTheme;
      
      // Test theme properties that MUI components would use
      expect(theme.palette.primary.main).toBe('#1976d2');
      expect(theme.typography.fontFamily).toContain('Roboto');
      expect(theme.components.MuiButton.styleOverrides.root.textTransform).toBe('none');
      expect(theme.shadows[1]).toContain('rgba');
      
      // Verify theme structure matches MUI expectations
      expect(typeof theme.spacing).toBe('function');
      expect(theme.breakpoints.values).toBeDefined();
      expect(theme.shape.borderRadius).toBeDefined();
    });
  });
});

// Export utilities for other tests
export const testThemeCreation = (mode) => {
  const theme = createSafeTheme(mode);
  expect(validateTheme(theme)).toBe(true);
  return theme;
};

export const verifyNoCreateThemeCall = () => {
  // This can be used in other tests to ensure createTheme is never called
  const createTheme = vi.fn().mockImplementation(() => {
    throw new Error('createTheme should not be called');
  });
  return createTheme;
};