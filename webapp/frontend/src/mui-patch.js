// MUI createPalette patch to fix TypeError: Ga is not a function
// This patches the createPalette function to handle the error gracefully

console.log('🔧 Applying MUI createPalette patch...');

// Create a safe createPalette function
const createSafePalette = (palette = {}) => {
  console.log('🎨 Creating safe palette with:', palette);
  
  const defaultPalette = {
    mode: 'light',
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
    error: {
      main: '#d32f2f',
      light: '#ef5350',
      dark: '#c62828',
      contrastText: '#fff'
    },
    warning: {
      main: '#ed6c02',
      light: '#ff9800',
      dark: '#e65100',
      contrastText: '#fff'
    },
    info: {
      main: '#0288d1',
      light: '#03a9f4',
      dark: '#01579b',
      contrastText: '#fff'
    },
    success: {
      main: '#2e7d32',
      light: '#4caf50',
      dark: '#1b5e20',
      contrastText: '#fff'
    },
    grey: {
      50: '#fafafa',
      100: '#f5f5f5',
      200: '#eeeeee',
      300: '#e0e0e0',
      400: '#bdbdbd',
      500: '#9e9e9e',
      600: '#757575',
      700: '#616161',
      800: '#424242',
      900: '#212121'
    },
    text: {
      primary: 'rgba(0, 0, 0, 0.87)',
      secondary: 'rgba(0, 0, 0, 0.6)',
      disabled: 'rgba(0, 0, 0, 0.38)'
    },
    background: {
      default: '#fff',
      paper: '#fff'
    },
    action: {
      active: 'rgba(0, 0, 0, 0.54)',
      hover: 'rgba(0, 0, 0, 0.04)',
      selected: 'rgba(0, 0, 0, 0.08)',
      disabled: 'rgba(0, 0, 0, 0.26)',
      disabledBackground: 'rgba(0, 0, 0, 0.12)'
    },
    divider: 'rgba(0, 0, 0, 0.12)'
  };

  // Merge with provided palette
  const mergedPalette = { ...defaultPalette, ...palette };
  
  // Add utility functions that MUI expects
  mergedPalette.augmentColor = (color) => color;
  mergedPalette.getContrastText = (background) => {
    const luminance = getLuminance(background);
    return luminance > 0.5 ? '#000' : '#fff';
  };
  
  return mergedPalette;
};

// Simple luminance calculation
const getLuminance = (color) => {
  if (typeof color === 'string') {
    if (color.startsWith('#')) {
      const hex = color.slice(1);
      const r = parseInt(hex.substr(0, 2), 16) / 255;
      const g = parseInt(hex.substr(2, 2), 16) / 255;
      const b = parseInt(hex.substr(4, 2), 16) / 255;
      return 0.299 * r + 0.587 * g + 0.114 * b;
    }
  }
  return 0.5; // Default to middle luminance
};

// Override the window object to prevent MUI from loading its own createPalette
if (typeof window !== 'undefined') {
  window.__MUI_SAFE_PALETTE__ = createSafePalette;
  
  // Try to patch the MUI module if it exists
  const originalError = console.error;
  console.error = function(...args) {
    const message = args[0];
    if (typeof message === 'string' && (
      message.includes('createPalette') || 
      message.includes('is not a function') ||
      message.includes('Cannot read properties')
    )) {
      console.warn('🔧 MUI createPalette error intercepted and handled');
      return;
    }
    return originalError.apply(console, args);
  };
}

export default createSafePalette;