/**
 * Theme utilities WITHOUT MUI createTheme to prevent createPalette errors
 * Direct theme object creation to avoid MUI theme initialization
 */

/**
 * Check MUI version and compatibility
 */
export function checkMuiVersion() {
  try {
    // Try to access MUI version info
    const muiVersion = require('@mui/material/package.json').version;
    console.log('MUI Version detected:', muiVersion);
    return muiVersion;
  } catch (error) {
    console.warn('Could not detect MUI version:', error);
    return 'unknown';
  }
}

/**
 * Create a direct theme object without MUI createTheme to avoid createPalette errors
 */
export function createDirectTheme(mode = 'light') {
  console.log('Creating direct theme object (no MUI createTheme) with mode:', mode);
  
  const isDark = mode === 'dark';
  
  // Create theme object directly without MUI createTheme
  return {
    palette: {
      mode,
      primary: {
        main: '#1976d2',
        light: '#42a5f5',
        dark: '#1565c0',
        contrastText: '#fff'
      },
      secondary: {
        main: '#dc004e',
        light: '#ff5983',
        dark: '#9a0036',
        contrastText: '#fff'
      },
      background: {
        default: isDark ? '#121212' : '#f5f5f5',
        paper: isDark ? '#1e1e1e' : '#ffffff'
      },
      text: {
        primary: isDark ? '#ffffff' : '#000000',
        secondary: isDark ? '#b3b3b3' : '#666666'
      },
      success: {
        main: '#2e7d32',
        light: '#4caf50',
        dark: '#1b5e20'
      },
      error: {
        main: '#d32f2f',
        light: '#ef5350',
        dark: '#c62828'
      },
      warning: {
        main: '#ed6c02',
        light: '#ff9800',
        dark: '#e65100'
      },
      info: {
        main: '#0288d1',
        light: '#03a9f4',
        dark: '#01579b'
      }
    },
    typography: {
      fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif',
      h1: { fontSize: '2.5rem', fontWeight: 600 },
      h2: { fontSize: '2rem', fontWeight: 600 },
      h3: { fontSize: '1.75rem', fontWeight: 600 },
      h4: { fontSize: '1.5rem', fontWeight: 600 },
      h5: { fontSize: '1.25rem', fontWeight: 600 },
      h6: { fontSize: '1rem', fontWeight: 600 },
      body1: { fontSize: '1rem' },
      body2: { fontSize: '0.875rem' }
    },
    spacing: (factor) => factor * 8,
    breakpoints: {
      values: { xs: 0, sm: 600, md: 960, lg: 1280, xl: 1920 },
      up: (key) => `@media (min-width:${key === 'xs' ? 0 : key === 'sm' ? 600 : key === 'md' ? 960 : key === 'lg' ? 1280 : 1920}px)`,
      down: (key) => `@media (max-width:${key === 'xs' ? 599 : key === 'sm' ? 959 : key === 'md' ? 1279 : key === 'lg' ? 1919 : 2559}px)`
    },
    shape: {
      borderRadius: 4
    },
    transitions: {
      duration: {
        shortest: 150,
        shorter: 200,
        short: 250,
        standard: 300,
        complex: 375,
        enteringScreen: 225,
        leavingScreen: 195
      },
      easing: {
        easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
        easeOut: 'cubic-bezier(0.0, 0, 0.2, 1)',
        easeIn: 'cubic-bezier(0.4, 0, 1, 1)',
        sharp: 'cubic-bezier(0.4, 0, 0.6, 1)'
      }
    },
    zIndex: {
      mobileStepper: 1000,
      speedDial: 1050,
      appBar: 1100,
      drawer: 1200,
      modal: 1300,
      snackbar: 1400,
      tooltip: 1500
    }
  };
}

/**
 * Debug theme creation process - now without createTheme
 */
export function debugThemeCreation() {
  console.log('Starting theme debug (without MUI createTheme)...');
  
  // Check MUI version
  checkMuiVersion();
  
  // Test direct theme object creation
  try {
    const basicTheme = createDirectTheme('light');
    console.log('Direct theme object creation works');
    console.log('Theme palette:', basicTheme.palette);
    return basicTheme;
  } catch (error) {
    console.error('Direct theme object creation failed:', error);
    throw error;
  }
}

/**
 * Get CSS variables for theme colors
 */
export function getThemeCSSVariables(theme) {
  return {
    '--primary-main': theme.palette.primary.main,
    '--primary-light': theme.palette.primary.light,
    '--primary-dark': theme.palette.primary.dark,
    '--secondary-main': theme.palette.secondary.main,
    '--background-default': theme.palette.background.default,
    '--background-paper': theme.palette.background.paper,
    '--text-primary': theme.palette.text.primary,
    '--text-secondary': theme.palette.text.secondary,
    '--success-main': theme.palette.success.main,
    '--error-main': theme.palette.error.main,
    '--warning-main': theme.palette.warning.main,
    '--info-main': theme.palette.info.main
  };
}

/**
 * Apply theme CSS variables to document
 */
export function applyThemeToDocument(theme) {
  const variables = getThemeCSSVariables(theme);
  const root = document.documentElement;
  
  Object.entries(variables).forEach(([property, value]) => {
    root.style.setProperty(property, value);
  });
  
  console.log('Applied theme CSS variables to document');
}