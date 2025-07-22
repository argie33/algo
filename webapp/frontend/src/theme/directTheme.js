/**
 * Direct Theme - Raw theme object without MUI createTheme wrapper
 * Prevents MUI createPalette errors by providing direct theme objects
 * Compatible with MUI components while avoiding theme creation issues
 */

import { createDirectTheme } from '../utils/themeUtils';

// Create theme instances using direct object creation
const lightThemeInstance = createDirectTheme('light');
const darkThemeInstance = createDirectTheme('dark');

// Export with multiple naming conventions for compatibility
export const directTheme = lightThemeInstance;
export const directDarkTheme = darkThemeInstance;

// Export with legacy names that components expect
export const lightTheme = lightThemeInstance;
export const darkTheme = darkThemeInstance;

// Export theme utilities
export { createDirectTheme } from '../utils/themeUtils';

// Default export (light theme)
export default lightThemeInstance;