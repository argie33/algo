import React, { createContext, useContext, useState, useEffect } from 'react';
import { createTheme } from '@mui/material/styles';

const ThemeContext = createContext();

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

const createAppTheme = (mode) => {
  console.log('🎨 Creating MUI theme for mode:', mode);
  
  try {
    const theme = createTheme({
      palette: {
        mode,
        primary: {
          main: '#1976d2',
          light: '#42a5f5',
          dark: '#1565c0',
          contrastText: '#ffffff',
        },
        secondary: {
          main: '#dc004e',
          light: '#ff5983',
          dark: '#9a0036',
          contrastText: '#ffffff',
        },
        error: {
          main: '#f44336',
          light: '#e57373',
          dark: '#d32f2f',
          contrastText: '#ffffff',
        },
        warning: {
          main: '#ff9800',
          light: '#ffb74d',
          dark: '#f57c00',
          contrastText: 'rgba(0, 0, 0, 0.87)',
        },
        info: {
          main: '#2196f3',
          light: '#64b5f6',
          dark: '#1976d2',
          contrastText: '#ffffff',
        },
        success: {
          main: '#4caf50',
          light: '#81c784',
          dark: '#388e3c',
          contrastText: 'rgba(0, 0, 0, 0.87)',
        },
        background: {
          default: mode === 'dark' ? '#121212' : '#fafafa',
          paper: mode === 'dark' ? '#1e1e1e' : '#ffffff',
        },
        text: {
          primary: mode === 'dark' ? 'rgba(255, 255, 255, 0.87)' : 'rgba(0, 0, 0, 0.87)',
          secondary: mode === 'dark' ? 'rgba(255, 255, 255, 0.6)' : 'rgba(0, 0, 0, 0.6)',
          disabled: mode === 'dark' ? 'rgba(255, 255, 255, 0.38)' : 'rgba(0, 0, 0, 0.38)',
        },
        divider: mode === 'dark' ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.12)',
        action: {
          active: mode === 'dark' ? 'rgba(255, 255, 255, 0.54)' : 'rgba(0, 0, 0, 0.54)',
          hover: mode === 'dark' ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.04)',
          selected: mode === 'dark' ? 'rgba(255, 255, 255, 0.16)' : 'rgba(0, 0, 0, 0.08)',
          disabled: mode === 'dark' ? 'rgba(255, 255, 255, 0.26)' : 'rgba(0, 0, 0, 0.26)',
          disabledBackground: mode === 'dark' ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.12)',
        },
      },
      typography: {
        fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
        fontWeightLight: 300,
        fontWeightRegular: 400,
        fontWeightMedium: 500,
        fontWeightBold: 700,
      },
      shape: {
        borderRadius: 4,
      },
      components: {
        MuiButton: {
          styleOverrides: {
            root: {
              textTransform: 'none',
              borderRadius: 8,
              fontWeight: 500,
            },
          },
        },
        MuiPaper: {
          styleOverrides: {
            root: {
              borderRadius: 12,
            },
          },
        },
        MuiCard: {
          styleOverrides: {
            root: {
              borderRadius: 12,
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
            },
          },
        },
      },
    });
    
    console.log('✅ MUI theme created successfully');
    return theme;
  } catch (error) {
    console.error('❌ Error creating MUI theme:', error);
    // Fallback to minimal theme if createTheme fails
    return {
      palette: {
        mode,
        primary: { main: '#1976d2' },
        secondary: { main: '#dc004e' },
        background: {
          default: mode === 'dark' ? '#121212' : '#fafafa',
          paper: mode === 'dark' ? '#1e1e1e' : '#ffffff',
        },
        text: {
          primary: mode === 'dark' ? '#ffffff' : '#000000',
        },
      },
      typography: {
        fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
      },
    };
  }
};

export const ThemeProvider = ({ children }) => {
  console.log('🚀 ThemeProvider rendering...');
  
  // Get initial theme from localStorage or default to light
  const [isDarkMode, setIsDarkMode] = useState(() => {
    try {
      const saved = localStorage.getItem('darkMode');
      const result = saved ? JSON.parse(saved) : false;
      console.log('💾 Loaded theme from localStorage:', result);
      return result;
    } catch (error) {
      console.error('❌ Error loading theme from localStorage:', error);
      return false;
    }
  });

  // Update localStorage when theme changes
  useEffect(() => {
    try {
      localStorage.setItem('darkMode', JSON.stringify(isDarkMode));
      console.log('💾 Saved theme to localStorage:', isDarkMode);
    } catch (error) {
      console.error('❌ Error saving theme to localStorage:', error);
    }
  }, [isDarkMode]);

  const toggleDarkMode = () => {
    console.log('🔄 Toggling dark mode from:', isDarkMode, 'to:', !isDarkMode);
    setIsDarkMode(!isDarkMode);
  };

  console.log('🎨 About to create theme with isDarkMode:', isDarkMode);
  const theme = createAppTheme(isDarkMode ? 'dark' : 'light');

  const value = {
    isDarkMode,
    toggleDarkMode,
    theme,
  };

  console.log('✅ ThemeProvider value created successfully');

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
};