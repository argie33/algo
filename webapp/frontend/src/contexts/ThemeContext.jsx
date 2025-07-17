import React, { createContext, useContext, useState, useEffect } from 'react';
import { createSafeTheme } from '../utils/themeUtils';

const ThemeContext = createContext();

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

const createAppTheme = (mode) => {
  console.log('🎨 Creating theme with safe theme utility for mode:', mode);
  
  try {
    const safeTheme = createSafeTheme(mode || 'light');
    console.log('✅ Safe theme created successfully');
    return safeTheme;
  } catch (error) {
    console.error('❌ Safe theme creation failed, using fallback:', error);
    
    // Ultra-minimal fallback theme
    return {
      palette: {
        mode: mode || 'light',
        primary: { main: '#1976d2' },
        secondary: { main: '#dc004e' },
        background: { default: '#ffffff', paper: '#ffffff' },
        text: { primary: '#000000' }
      },
      typography: { fontFamily: 'Arial, sans-serif' },
      spacing: 8,
      breakpoints: { values: { xs: 0, sm: 600, md: 960, lg: 1280, xl: 1920 } }
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