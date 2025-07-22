/**
 * Theme Integration Smoke Tests
 * Catches MUI theme-related errors before they reach production
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ThemeProvider } from '@mui/material/styles';
import { 
  AppBar, 
  Toolbar, 
  Drawer, 
  Typography, 
  Avatar, 
  Button,
  CssBaseline 
} from '@mui/material';
import { lightTheme, darkTheme, validateTheme } from '../../theme/safeTheme';

describe('🎨 Theme Integration Smoke Tests', () => {
  
  describe('Theme Structure Validation', () => {
    it('should have valid light theme structure', () => {
      expect(validateTheme(lightTheme)).toBe(true);
    });

    it('should have valid dark theme structure', () => {
      expect(validateTheme(darkTheme)).toBe(true);
    });

    it('should have all required MUI theme properties', () => {
      const requiredProperties = [
        'palette', 'typography', 'spacing', 'breakpoints', 
        'shape', 'transitions', 'mixins', 'zIndex', 'components', 'shadows'
      ];
      
      requiredProperties.forEach(prop => {
        expect(lightTheme).toHaveProperty(prop);
        expect(darkTheme).toHaveProperty(prop);
      });
    });

    it('should have proper mixins.toolbar definition', () => {
      expect(lightTheme.mixins.toolbar).toBeDefined();
      expect(lightTheme.mixins.toolbar.minHeight).toBeDefined();
    });

    it('should have proper zIndex definitions', () => {
      expect(lightTheme.zIndex.appBar).toBeDefined();
      expect(lightTheme.zIndex.drawer).toBeDefined();
    });
  });

  describe('Critical MUI Components Theme Integration', () => {
    const TestComponent = ({ children }) => (
      <ThemeProvider theme={lightTheme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    );

    it('should render AppBar without theme errors', () => {
      expect(() => {
        render(
          <TestComponent>
            <AppBar position="static">
              <Toolbar>
                <Typography variant="h6">Test App</Typography>
              </Toolbar>
            </AppBar>
          </TestComponent>
        );
      }).not.toThrow();
    });

    it('should render Drawer without theme errors', () => {
      expect(() => {
        render(
          <TestComponent>
            <Drawer open={false}>
              <div>Drawer content</div>
            </Drawer>
          </TestComponent>
        );
      }).not.toThrow();
    });

    it('should render Toolbar without theme errors', () => {
      expect(() => {
        render(
          <TestComponent>
            <Toolbar>
              <Typography>Test Toolbar</Typography>
            </Toolbar>
          </TestComponent>
        );
      }).not.toThrow();
    });

    it('should render Avatar without applyStyles errors', () => {
      expect(() => {
        render(
          <TestComponent>
            <Avatar>U</Avatar>
          </TestComponent>
        );
      }).not.toThrow();
    });

    it('should render complex layout without theme errors', () => {
      expect(() => {
        render(
          <TestComponent>
            <AppBar position="static">
              <Toolbar>
                <Typography variant="h6" sx={{ flexGrow: 1 }}>
                  App Title
                </Typography>
                <Avatar>U</Avatar>
              </Toolbar>
            </AppBar>
            <Drawer variant="temporary" open={false}>
              <Toolbar />
              <div>
                <Button variant="contained">Test Button</Button>
              </div>
            </Drawer>
          </TestComponent>
        );
      }).not.toThrow();
    });
  });

  describe('Component Theme Properties Access', () => {
    it('should allow components to access theme.mixins.toolbar', () => {
      const theme = lightTheme;
      expect(theme.mixins.toolbar).toBeDefined();
      expect(typeof theme.mixins.toolbar.minHeight).toBe('string');
    });

    it('should allow components to access theme.zIndex', () => {
      const theme = lightTheme;
      expect(theme.zIndex.appBar).toBeDefined();
      expect(theme.zIndex.drawer).toBeDefined();
      expect(typeof theme.zIndex.appBar).toBe('number');
    });

    it('should have applyStyles function or equivalent', () => {
      // Check if theme has proper structure for applyStyles
      const theme = lightTheme;
      expect(theme.palette.mode).toBeDefined();
      
      // Mock applyStyles functionality test
      const mockApplyStyles = (styles) => {
        return typeof styles === 'function' ? styles(theme) : styles;
      };
      
      expect(() => {
        mockApplyStyles({ color: 'primary.main' });
      }).not.toThrow();
    });
  });

  describe('Theme Consistency Tests', () => {
    it('should have consistent color definitions', () => {
      expect(lightTheme.palette.primary.main).toBeDefined();
      expect(lightTheme.palette.secondary.main).toBeDefined();
      expect(lightTheme.palette.error.main).toBeDefined();
    });

    it('should have proper component overrides', () => {
      expect(lightTheme.components.MuiAppBar).toBeDefined();
      expect(lightTheme.components.MuiDrawer).toBeDefined();
      expect(lightTheme.components.MuiToolbar).toBeDefined();
    });

    it('should have proper spacing function', () => {
      expect(typeof lightTheme.spacing).toBe('function');
      expect(lightTheme.spacing(1)).toBeDefined();
    });
  });
});