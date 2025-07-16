import React, { createContext, useContext, useState, useEffect } from 'react';
import { createTheme } from '@mui/material/styles';
import { createSafeTheme, debugThemeCreation, checkMuiVersion } from '../utils/themeUtils';

const ThemeContext = createContext();

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

const createAppTheme = (mode) => {
  console.log('🎨 Creating theme with mode:', mode);
  
  // Run debug information
  console.log('📋 MUI Version:', checkMuiVersion());
  debugThemeCreation();
  
  try {
    // Use the safe theme creation utility
    const theme = createSafeTheme(mode);
    console.log('✅ Safe theme created successfully');
    console.log('🎨 Theme palette mode:', theme.palette.mode);
    console.log('🎨 Theme primary color:', theme.palette.primary.main);
    
    return theme;
    
  } catch (error) {
    console.error('❌ Safe theme creation failed:', error);
    console.error('❌ Error stack:', error.stack);
    console.error('❌ Error name:', error.name);
    console.error('❌ Error message:', error.message);
    
    // Last resort: create absolute minimal theme
    console.log('🔄 Attempting last resort theme...');
    try {
      const lastResortTheme = createTheme({
        palette: {
          primary: {
            main: '#1976d2',
          },
        },
      });
      console.log('✅ Last resort theme created successfully');
      return lastResortTheme;
    } catch (lastResortError) {
      console.error('❌ Even last resort theme failed:', lastResortError);
      throw lastResortError;
    }
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