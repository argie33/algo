import { createTheme, alpha } from '@mui/material/styles';

/**
 * REFINED PROFESSIONAL FINANCIAL PLATFORM THEME
 *
 * Design Philosophy:
 * - Clean, minimal, and sophisticated
 * - Subtle color palette - not too colorful
 * - Sharp typography and spacing
 * - Enhanced depth with better shadows
 * - Professional financial aesthetic
 */

// ============================================================
// REFINED COLOR PALETTE - Subtle & Professional
// ============================================================

const colors = {
  // Primary - Refined Professional Blue (less saturated)
  primary: {
    50: '#F0F4F8',
    100: '#D9E2EC',
    200: '#BCCCDC',
    300: '#9FB3C8',
    400: '#829AB1',
    500: '#627D98',  // Main - muted professional blue
    600: '#486581',
    700: '#334E68',
    800: '#243B53',
    900: '#102A43',
  },

  // Secondary - Subtle Slate (neutral, professional)
  secondary: {
    50: '#F8F9FA',
    100: '#E9ECEF',
    200: '#DEE2E6',
    300: '#CED4DA',
    400: '#ADB5BD',
    500: '#6C757D',  // Main - professional gray
    600: '#495057',
    700: '#343A40',
    800: '#212529',
    900: '#1A1D20',
  },

  // Success - Subtle Green
  success: {
    main: '#10B981',
    light: '#34D399',
    dark: '#059669',
  },

  // Error - Subtle Red
  error: {
    main: '#EF4444',
    light: '#F87171',
    dark: '#DC2626',
  },

  // Warning - Subtle Amber
  warning: {
    main: '#F59E0B',
    light: '#FBBF24',
    dark: '#D97706',
  },

  // Info - Subtle Blue
  info: {
    main: '#3B82F6',
    light: '#60A5FA',
    dark: '#2563EB',
  },

  // Backgrounds - Clean, light, professional
  background: {
    default: '#F8F9FA',      // Very light gray - softer than white
    paper: '#FFFFFF',        // Pure white for cards
    elevated: '#FAFBFC',     // Slightly off-white for elevated elements
  },

  // Text - High readability
  text: {
    primary: '#1A202C',      // Near black
    secondary: '#4A5568',    // Medium gray
    disabled: '#A0AEC0',     // Light gray
  },

  // Borders & Dividers
  divider: 'rgba(0, 0, 0, 0.08)',
  border: 'rgba(0, 0, 0, 0.12)',
};

// ============================================================
// CREATE THEME
// ============================================================

export const modernTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: colors.primary[500],
      light: colors.primary[400],
      dark: colors.primary[700],
      contrastText: '#FFFFFF',
    },
    secondary: {
      main: colors.secondary[500],
      light: colors.secondary[400],
      dark: colors.secondary[700],
      contrastText: '#FFFFFF',
    },
    success: {
      main: colors.success.main,
      light: colors.success.light,
      dark: colors.success.dark,
      contrastText: '#FFFFFF',
    },
    error: {
      main: colors.error.main,
      light: colors.error.light,
      dark: colors.error.dark,
      contrastText: '#FFFFFF',
    },
    warning: {
      main: colors.warning.main,
      light: colors.warning.light,
      dark: colors.warning.dark,
      contrastText: '#000000',
    },
    info: {
      main: colors.info.main,
      light: colors.info.light,
      dark: colors.info.dark,
      contrastText: '#FFFFFF',
    },
    background: {
      default: colors.background.default,
      paper: colors.background.paper,
    },
    text: {
      primary: colors.text.primary,
      secondary: colors.text.secondary,
      disabled: colors.text.disabled,
    },
    divider: colors.divider,
    action: {
      active: colors.primary[600],
      hover: alpha(colors.primary[500], 0.04),
      selected: alpha(colors.primary[500], 0.08),
      disabled: colors.text.disabled,
      disabledBackground: alpha(colors.text.disabled, 0.12),
    },
  },

  // ============================================================
  // TYPOGRAPHY - Sharp and Professional
  // ============================================================
  typography: {
    fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Cantarell", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif',

    h1: {
      fontWeight: 700,
      fontSize: '2.5rem',
      lineHeight: 1.2,
      letterSpacing: '-0.02em',
      color: colors.text.primary,
    },
    h2: {
      fontWeight: 700,
      fontSize: '2rem',
      lineHeight: 1.3,
      letterSpacing: '-0.01em',
      color: colors.text.primary,
    },
    h3: {
      fontWeight: 600,
      fontSize: '1.75rem',
      lineHeight: 1.3,
      letterSpacing: '-0.01em',
      color: colors.text.primary,
    },
    h4: {
      fontWeight: 600,
      fontSize: '1.5rem',
      lineHeight: 1.4,
      letterSpacing: '0em',
      color: colors.text.primary,
    },
    h5: {
      fontWeight: 600,
      fontSize: '1.25rem',
      lineHeight: 1.4,
      letterSpacing: '0em',
      color: colors.text.primary,
    },
    h6: {
      fontWeight: 600,
      fontSize: '1rem',
      lineHeight: 1.5,
      letterSpacing: '0em',
      color: colors.text.primary,
    },
    subtitle1: {
      fontWeight: 500,
      fontSize: '1rem',
      lineHeight: 1.5,
      color: colors.text.secondary,
    },
    subtitle2: {
      fontWeight: 500,
      fontSize: '0.875rem',
      lineHeight: 1.5,
      color: colors.text.secondary,
    },
    body1: {
      fontWeight: 400,
      fontSize: '1rem',
      lineHeight: 1.6,
      color: colors.text.primary,
    },
    body2: {
      fontWeight: 400,
      fontSize: '0.875rem',
      lineHeight: 1.6,
      color: colors.text.primary,
    },
    button: {
      fontWeight: 600,
      fontSize: '0.875rem',
      lineHeight: 1.75,
      letterSpacing: '0.01em',
      textTransform: 'none',
    },
    caption: {
      fontWeight: 400,
      fontSize: '0.75rem',
      lineHeight: 1.6,
      color: colors.text.secondary,
    },
    overline: {
      fontWeight: 600,
      fontSize: '0.75rem',
      lineHeight: 2,
      letterSpacing: '0.08em',
      textTransform: 'uppercase',
      color: colors.text.secondary,
    },
  },

  // ============================================================
  // SHAPE & SPACING
  // ============================================================
  shape: {
    borderRadius: 12,  // Rounded but not too much
  },

  spacing: 8,

  // ============================================================
  // SHADOWS - Enhanced but subtle depth
  // ============================================================
  shadows: [
    'none',
    '0px 1px 2px rgba(0, 0, 0, 0.04), 0px 1px 3px rgba(0, 0, 0, 0.06)',
    '0px 2px 4px rgba(0, 0, 0, 0.04), 0px 3px 6px rgba(0, 0, 0, 0.08)',
    '0px 3px 6px rgba(0, 0, 0, 0.04), 0px 4px 8px rgba(0, 0, 0, 0.08)',
    '0px 4px 8px rgba(0, 0, 0, 0.04), 0px 6px 12px rgba(0, 0, 0, 0.08)',
    '0px 6px 12px rgba(0, 0, 0, 0.06), 0px 8px 16px rgba(0, 0, 0, 0.1)',
    '0px 8px 16px rgba(0, 0, 0, 0.06), 0px 12px 24px rgba(0, 0, 0, 0.1)',
    '0px 10px 20px rgba(0, 0, 0, 0.08), 0px 16px 32px rgba(0, 0, 0, 0.12)',
    '0px 12px 24px rgba(0, 0, 0, 0.08), 0px 20px 40px rgba(0, 0, 0, 0.12)',
    '0px 16px 32px rgba(0, 0, 0, 0.1), 0px 24px 48px rgba(0, 0, 0, 0.14)',
    '0px 20px 40px rgba(0, 0, 0, 0.1), 0px 28px 56px rgba(0, 0, 0, 0.14)',
    '0px 24px 48px rgba(0, 0, 0, 0.12), 0px 32px 64px rgba(0, 0, 0, 0.16)',
    '0px 28px 56px rgba(0, 0, 0, 0.12), 0px 36px 72px rgba(0, 0, 0, 0.16)',
    '0px 32px 64px rgba(0, 0, 0, 0.14), 0px 40px 80px rgba(0, 0, 0, 0.18)',
    '0px 36px 72px rgba(0, 0, 0, 0.14), 0px 44px 88px rgba(0, 0, 0, 0.18)',
    '0px 40px 80px rgba(0, 0, 0, 0.16), 0px 48px 96px rgba(0, 0, 0, 0.2)',
    '0px 44px 88px rgba(0, 0, 0, 0.16), 0px 52px 104px rgba(0, 0, 0, 0.2)',
    '0px 48px 96px rgba(0, 0, 0, 0.18), 0px 56px 112px rgba(0, 0, 0, 0.22)',
    '0px 52px 104px rgba(0, 0, 0, 0.18), 0px 60px 120px rgba(0, 0, 0, 0.22)',
    '0px 56px 112px rgba(0, 0, 0, 0.2), 0px 64px 128px rgba(0, 0, 0, 0.24)',
    '0px 60px 120px rgba(0, 0, 0, 0.2), 0px 68px 136px rgba(0, 0, 0, 0.24)',
    '0px 64px 128px rgba(0, 0, 0, 0.22), 0px 72px 144px rgba(0, 0, 0, 0.26)',
    '0px 68px 136px rgba(0, 0, 0, 0.22), 0px 76px 152px rgba(0, 0, 0, 0.26)',
    '0px 72px 144px rgba(0, 0, 0, 0.24), 0px 80px 160px rgba(0, 0, 0, 0.28)',
    '0px 76px 152px rgba(0, 0, 0, 0.24), 0px 84px 168px rgba(0, 0, 0, 0.28)',
  ],

  // ============================================================
  // COMPONENT OVERRIDES - Subtle improvements
  // ============================================================
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          scrollbarColor: `${colors.primary[300]} ${colors.background.default}`,
          '&::-webkit-scrollbar': {
            width: '10px',
            height: '10px',
          },
          '&::-webkit-scrollbar-track': {
            background: colors.background.default,
          },
          '&::-webkit-scrollbar-thumb': {
            backgroundColor: colors.primary[300],
            borderRadius: '5px',
            border: `2px solid ${colors.background.default}`,
            '&:hover': {
              backgroundColor: colors.primary[400],
            },
          },
        },
      },
    },

    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          padding: '10px 24px',
          fontWeight: 600,
          textTransform: 'none',
          minHeight: 44,
          minWidth: 44,
          boxShadow: 'none',
          transition: 'all 0.2s ease',
          '&:hover': {
            boxShadow: '0px 4px 12px rgba(0, 0, 0, 0.12)',
            transform: 'translateY(-1px)',
          },
          '&:active': {
            transform: 'translateY(0)',
          },
        },
        contained: {
          '&:hover': {
            boxShadow: '0px 6px 16px rgba(0, 0, 0, 0.16)',
          },
        },
        outlined: {
          borderWidth: '1.5px',
          '&:hover': {
            borderWidth: '1.5px',
            backgroundColor: alpha(colors.primary[500], 0.04),
          },
        },
      },
    },

    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          backgroundColor: colors.background.paper,
          border: `1px solid ${colors.divider}`,
          boxShadow: '0px 2px 8px rgba(0, 0, 0, 0.04), 0px 4px 16px rgba(0, 0, 0, 0.06)',
          transition: 'all 0.3s ease',
          '&:hover': {
            boxShadow: '0px 4px 12px rgba(0, 0, 0, 0.08), 0px 8px 24px rgba(0, 0, 0, 0.1)',
            transform: 'translateY(-2px)',
            borderColor: alpha(colors.primary[500], 0.2),
          },
        },
      },
    },

    MuiPaper: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          backgroundColor: colors.background.paper,
          border: `1px solid ${colors.divider}`,
        },
        elevation1: {
          boxShadow: '0px 2px 4px rgba(0, 0, 0, 0.04), 0px 3px 6px rgba(0, 0, 0, 0.06)',
        },
        elevation2: {
          boxShadow: '0px 3px 6px rgba(0, 0, 0, 0.04), 0px 4px 8px rgba(0, 0, 0, 0.08)',
        },
        elevation3: {
          boxShadow: '0px 4px 8px rgba(0, 0, 0, 0.06), 0px 6px 12px rgba(0, 0, 0, 0.08)',
        },
      },
    },

    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: colors.background.paper,
          color: colors.text.primary,
          borderBottom: `1px solid ${colors.divider}`,
          boxShadow: '0px 1px 3px rgba(0, 0, 0, 0.04), 0px 2px 6px rgba(0, 0, 0, 0.06)',
        },
      },
    },

    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: colors.background.paper,
          borderRight: `1px solid ${colors.divider}`,
        },
      },
    },

    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          fontWeight: 500,
          height: 32,
        },
        filled: {
          backgroundColor: alpha(colors.primary[500], 0.1),
          color: colors.primary[700],
          border: `1px solid ${alpha(colors.primary[500], 0.2)}`,
          '&:hover': {
            backgroundColor: alpha(colors.primary[500], 0.15),
          },
        },
      },
    },

    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            borderRadius: 10,
            backgroundColor: colors.background.default,
            transition: 'all 0.2s ease',
            '& fieldset': {
              borderColor: colors.border,
              borderWidth: '1.5px',
            },
            '&:hover fieldset': {
              borderColor: colors.primary[400],
            },
            '&.Mui-focused': {
              backgroundColor: colors.background.paper,
              '& fieldset': {
                borderColor: colors.primary[500],
                borderWidth: '2px',
              },
            },
          },
        },
      },
    },

    MuiTable: {
      styleOverrides: {
        root: {
          '& .MuiTableCell-head': {
            fontWeight: 700,
            backgroundColor: colors.background.default,
            borderBottom: `2px solid ${colors.divider}`,
            textTransform: 'uppercase',
            fontSize: '0.75rem',
            letterSpacing: '0.05em',
            color: colors.text.secondary,
            padding: '16px',
          },
          '& .MuiTableRow-root': {
            transition: 'background-color 0.2s ease',
            '&:hover': {
              backgroundColor: alpha(colors.primary[500], 0.02),
            },
          },
          '& .MuiTableCell-body': {
            borderBottom: `1px solid ${colors.divider}`,
            padding: '16px',
          },
        },
      },
    },

    MuiLinearProgress: {
      styleOverrides: {
        root: {
          borderRadius: 4,
          height: 6,
          backgroundColor: colors.background.default,
        },
        bar: {
          borderRadius: 4,
        },
      },
    },

    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: colors.secondary[800],
          borderRadius: 8,
          padding: '8px 12px',
          fontSize: '0.875rem',
          fontWeight: 500,
          boxShadow: '0px 4px 12px rgba(0, 0, 0, 0.15)',
        },
        arrow: {
          color: colors.secondary[800],
        },
      },
    },

    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          border: '1px solid',
          fontWeight: 500,
        },
        standardSuccess: {
          backgroundColor: alpha(colors.success.main, 0.1),
          borderColor: alpha(colors.success.main, 0.3),
          color: colors.success.dark,
        },
        standardError: {
          backgroundColor: alpha(colors.error.main, 0.1),
          borderColor: alpha(colors.error.main, 0.3),
          color: colors.error.dark,
        },
        standardWarning: {
          backgroundColor: alpha(colors.warning.main, 0.1),
          borderColor: alpha(colors.warning.main, 0.3),
          color: colors.warning.dark,
        },
        standardInfo: {
          backgroundColor: alpha(colors.info.main, 0.1),
          borderColor: alpha(colors.info.main, 0.3),
          color: colors.info.dark,
        },
      },
    },

    MuiTabs: {
      styleOverrides: {
        root: {
          minHeight: 48,
          borderBottom: `1px solid ${colors.divider}`,
        },
        indicator: {
          height: 3,
          borderRadius: '3px 3px 0 0',
          backgroundColor: colors.primary[600],
        },
      },
    },

    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
          fontSize: '0.9375rem',
          minHeight: 48,
          color: colors.text.secondary,
          transition: 'all 0.2s ease',
          '&:hover': {
            color: colors.primary[600],
            backgroundColor: alpha(colors.primary[500], 0.04),
          },
          '&.Mui-selected': {
            color: colors.primary[600],
          },
        },
      },
    },

    MuiIconButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          transition: 'all 0.2s ease',
          '&:hover': {
            backgroundColor: alpha(colors.primary[500], 0.06),
          },
        },
      },
    },

    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          marginBottom: 2,
          transition: 'all 0.2s ease',
          '&:hover': {
            backgroundColor: alpha(colors.primary[500], 0.06),
          },
          '&.Mui-selected': {
            backgroundColor: alpha(colors.primary[500], 0.1),
            borderLeft: `3px solid ${colors.primary[600]}`,
            '&:hover': {
              backgroundColor: alpha(colors.primary[500], 0.14),
            },
            '& .MuiListItemIcon-root': {
              color: colors.primary[600],
            },
            '& .MuiListItemText-primary': {
              color: colors.primary[700],
              fontWeight: 600,
            },
          },
        },
      },
    },

    MuiDivider: {
      styleOverrides: {
        root: {
          borderColor: colors.divider,
        },
      },
    },
  },
});

// Export colors for use in components
export { colors };

export default modernTheme;
