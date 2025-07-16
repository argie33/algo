/**
 * Theme utilities with comprehensive error handling and version compatibility
 */

import { createTheme } from '@mui/material/styles';

/**
 * Check MUI version and compatibility
 */
export function checkMuiVersion() {
  try {
    // Try to access MUI version info
    const muiVersion = require('@mui/material/package.json').version;
    console.log('🔍 MUI Version detected:', muiVersion);
    return muiVersion;
  } catch (error) {
    console.warn('⚠️ Could not detect MUI version:', error);
    return 'unknown';
  }
}

/**
 * Create a safe theme with progressive enhancement
 */
export function createSafeTheme(mode = 'light') {
  console.log('🎨 Creating safe theme with mode:', mode);
  
  const isDark = mode === 'dark';
  
  // Level 1: Absolute minimum theme
  const level1Theme = () => {
    console.log('🎨 Creating Level 1 theme (absolute minimum)');
    return createTheme();
  };
  
  // Level 2: Basic palette
  const level2Theme = () => {
    console.log('🎨 Creating Level 2 theme (basic palette)');
    return createTheme({
      palette: {
        mode: mode,
      },
    });
  };
  
  // Level 3: Full palette with colors
  const level3Theme = () => {
    console.log('🎨 Creating Level 3 theme (full palette)');
    return createTheme({
      palette: {
        mode,
        primary: {
          main: '#1976d2',
        },
        secondary: {
          main: '#dc004e',
        },
        background: {
          default: isDark ? '#121212' : '#f5f5f5',
          paper: isDark ? '#1e1e1e' : '#ffffff',
        },
        text: {
          primary: isDark ? '#ffffff' : '#000000',
          secondary: isDark ? '#b3b3b3' : '#666666',
        },
      },
    });
  };
  
  // Level 4: Full theme with typography
  const level4Theme = () => {
    console.log('🎨 Creating Level 4 theme (with typography)');
    return createTheme({
      palette: {
        mode,
        primary: {
          main: '#1976d2',
          light: '#42a5f5',
          dark: '#1565c0',
        },
        secondary: {
          main: '#dc004e',
          light: '#ff5983',
          dark: '#9a0036',
        },
        background: {
          default: isDark ? '#121212' : '#f5f5f5',
          paper: isDark ? '#1e1e1e' : '#ffffff',
        },
        text: {
          primary: isDark ? '#ffffff' : '#000000',
          secondary: isDark ? '#b3b3b3' : '#666666',
        },
        success: {
          main: '#2e7d32',
          light: '#4caf50',
          dark: '#1b5e20',
        },
        error: {
          main: '#d32f2f',
          light: '#ef5350',
          dark: '#c62828',
        },
        warning: {
          main: '#ed6c02',
          light: '#ff9800',
          dark: '#e65100',
        },
        info: {
          main: '#0288d1',
          light: '#03a9f4',
          dark: '#01579b',
        },
      },
      typography: {
        fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif',
        h1: { fontWeight: 600 },
        h2: { fontWeight: 600 },
        h3: { fontWeight: 600 },
        h4: { fontWeight: 600 },
        h5: { fontWeight: 600 },
        h6: { fontWeight: 600 },
      },
    });
  };
  
  // Level 5: Full theme with components
  const level5Theme = () => {
    console.log('🎨 Creating Level 5 theme (with components)');
    return createTheme({
      palette: {
        mode,
        primary: {
          main: '#1976d2',
          light: '#42a5f5',
          dark: '#1565c0',
        },
        secondary: {
          main: '#dc004e',
          light: '#ff5983',
          dark: '#9a0036',
        },
        background: {
          default: isDark ? '#121212' : '#f5f5f5',
          paper: isDark ? '#1e1e1e' : '#ffffff',
        },
        text: {
          primary: isDark ? '#ffffff' : '#000000',
          secondary: isDark ? '#b3b3b3' : '#666666',
        },
        success: {
          main: '#2e7d32',
          light: '#4caf50',
          dark: '#1b5e20',
        },
        error: {
          main: '#d32f2f',
          light: '#ef5350',
          dark: '#c62828',
        },
        warning: {
          main: '#ed6c02',
          light: '#ff9800',
          dark: '#e65100',
        },
        info: {
          main: '#0288d1',
          light: '#03a9f4',
          dark: '#01579b',
        },
      },
      typography: {
        fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif',
        h1: { fontWeight: 600 },
        h2: { fontWeight: 600 },
        h3: { fontWeight: 600 },
        h4: { fontWeight: 600 },
        h5: { fontWeight: 600 },
        h6: { fontWeight: 600 },
      },
      components: {
        MuiButton: {
          styleOverrides: {
            root: {
              textTransform: 'none',
              fontWeight: 500,
            },
          },
        },
        MuiCard: {
          styleOverrides: {
            root: {
              boxShadow: isDark 
                ? '0 2px 8px rgba(0,0,0,0.3)' 
                : '0 2px 8px rgba(0,0,0,0.1)',
              borderRadius: 12,
              backgroundColor: isDark ? '#1e1e1e' : '#ffffff',
            },
          },
        },
        MuiPaper: {
          styleOverrides: {
            root: {
              backgroundColor: isDark ? '#1e1e1e' : '#ffffff',
            },
          },
        },
        MuiAppBar: {
          styleOverrides: {
            root: {
              backgroundColor: isDark ? '#1e1e1e' : '#1976d2',
            },
          },
        },
      },
    });
  };
  
  // Try each level progressively
  const levels = [level5Theme, level4Theme, level3Theme, level2Theme, level1Theme];
  
  for (let i = 0; i < levels.length; i++) {
    try {
      const theme = levels[i]();
      console.log(`✅ Successfully created theme at level ${5 - i}`);
      return theme;
    } catch (error) {
      console.error(`❌ Level ${5 - i} theme failed:`, error);
      if (i === levels.length - 1) {
        throw error; // If even level 1 fails, throw the error
      }
    }
  }
}

/**
 * Debug theme creation process
 */
export function debugThemeCreation() {
  console.log('🔍 Starting theme creation debug...');
  
  // Check MUI version
  checkMuiVersion();
  
  // Test basic createTheme function
  try {
    const basicTheme = createTheme();
    console.log('✅ Basic createTheme() works');
    console.log('🎨 Basic theme palette:', basicTheme.palette);
  } catch (error) {
    console.error('❌ Basic createTheme() failed:', error);
  }
  
  // Test palette mode
  try {
    const modeTheme = createTheme({ palette: { mode: 'light' } });
    console.log('✅ Palette mode works');
  } catch (error) {
    console.error('❌ Palette mode failed:', error);
  }
  
  // Test with colors
  try {
    const colorTheme = createTheme({
      palette: {
        mode: 'light',
        primary: { main: '#1976d2' }
      }
    });
    console.log('✅ Color palette works');
  } catch (error) {
    console.error('❌ Color palette failed:', error);
  }
}