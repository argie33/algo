/**
 * COMPLETED: Safe Theme - Direct theme object without MUI createTheme
 * Prevents createPalette errors and provides consistent theming
 * Now exports both legacy names and new names for compatibility
 */

import { createSafeTheme } from '../utils/themeUtils';

// COMPLETED: Create theme instances
const lightThemeInstance = createSafeTheme('light');
const darkThemeInstance = createSafeTheme('dark');

// COMPLETED: Export with multiple naming conventions for compatibility
export const safeTheme = lightThemeInstance;
export const safeDarkTheme = darkThemeInstance;

// COMPLETED: Export with legacy names that components expect
export const lightTheme = lightThemeInstance;
export const darkTheme = darkThemeInstance;

// COMPLETED: Export theme utilities
export { createSafeTheme } from '../utils/themeUtils';

// COMPLETED: Default export (light theme)
export default lightThemeInstance;