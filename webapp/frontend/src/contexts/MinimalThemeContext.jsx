import React, { createContext, useContext, useState } from 'react';
// REMOVED MUI imports - causes createPalette error
// import { createTheme, ThemeProvider as MuiThemeProvider } from '@mui/material/styles';

const ThemeContext = createContext();

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

export const MinimalThemeProvider = ({ children }) => {
  console.log('🎨 MinimalThemeProvider rendering...');
  
  const [isDarkMode, setIsDarkMode] = useState(false);

  // Create minimal theme object without MUI createTheme
  const theme = {
    palette: {
      mode: isDarkMode ? 'dark' : 'light',
      primary: { main: '#1976d2' },
      secondary: { main: '#dc004e' },
      background: {
        default: isDarkMode ? '#121212' : '#ffffff',
        paper: isDarkMode ? '#1e1e1e' : '#ffffff'
      },
      text: {
        primary: isDarkMode ? '#ffffff' : '#000000',
        secondary: isDarkMode ? '#b3b3b3' : '#666666'
      }
    }
  };

  const toggleDarkMode = () => {
    setIsDarkMode(!isDarkMode);
  };

  const value = {
    isDarkMode,
    toggleDarkMode,
    theme,
  };

  console.log('✅ MinimalThemeProvider theme created successfully');

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
};