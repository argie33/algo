// Responsive utilities for mobile optimization
// Handles viewport detection, touch events, and mobile-specific UI adaptations

import { useTheme } from '@mui/material/styles';
import { useMediaQuery } from '@mui/material';
import { useState, useEffect } from 'react';

// Breakpoint utilities
export const breakpoints = {
  xs: 0,
  sm: 600,
  md: 900,
  lg: 1200,
  xl: 1536
};

// Custom hook for responsive design
export const useResponsive = () => {
  const theme = useTheme();
  
  const isXs = useMediaQuery(theme.breakpoints.only('xs'));
  const isSm = useMediaQuery(theme.breakpoints.only('sm'));
  const isMd = useMediaQuery(theme.breakpoints.only('md'));
  const isLg = useMediaQuery(theme.breakpoints.only('lg'));
  const isXl = useMediaQuery(theme.breakpoints.only('xl'));
  
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const isTablet = useMediaQuery(theme.breakpoints.between('md', 'lg'));
  const isDesktop = useMediaQuery(theme.breakpoints.up('lg'));
  
  const isSmallScreen = useMediaQuery(theme.breakpoints.down('sm'));
  const isLargeScreen = useMediaQuery(theme.breakpoints.up('xl'));
  
  return {
    isXs,
    isSm,
    isMd,
    isLg,
    isXl,
    isMobile,
    isTablet,
    isDesktop,
    isSmallScreen,
    isLargeScreen,
    width: window.innerWidth,
    height: window.innerHeight
  };
};

// Custom hook for viewport size
export const useViewport = () => {
  const [viewport, setViewport] = useState({
    width: typeof window !== 'undefined' ? window.innerWidth : 0,
    height: typeof window !== 'undefined' ? window.innerHeight : 0
  });

  useEffect(() => {
    const handleResize = () => {
      setViewport({
        width: window.innerWidth,
        height: window.innerHeight
      });
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return viewport;
};

// Touch event utilities
export const useTouchEvents = () => {
  const [touchStart, setTouchStart] = useState(null);
  const [touchEnd, setTouchEnd] = useState(null);
  const [swipeDirection, setSwipeDirection] = useState(null);
  
  const minSwipeDistance = 50;

  const onTouchStart = (e) => {
    setTouchEnd(null);
    setTouchStart(e.targetTouches[0].clientX);
  };

  const onTouchMove = (e) => {
    setTouchEnd(e.targetTouches[0].clientX);
  };

  const onTouchEnd = () => {
    if (!touchStart || !touchEnd) return;
    
    const distance = touchStart - touchEnd;
    const isLeftSwipe = distance > minSwipeDistance;
    const isRightSwipe = distance < -minSwipeDistance;
    
    if (isLeftSwipe) {
      setSwipeDirection('left');
    } else if (isRightSwipe) {
      setSwipeDirection('right');
    }
    
    // Reset after a short delay
    setTimeout(() => setSwipeDirection(null), 100);
  };

  return {
    onTouchStart,
    onTouchMove,
    onTouchEnd,
    swipeDirection,
    touchStart,
    touchEnd
  };
};

// Device detection
export const detectDevice = () => {
  const userAgent = navigator.userAgent || navigator.vendor || window.opera;
  
  const isIOS = /iPad|iPhone|iPod/.test(userAgent) && !window.MSStream;
  const isAndroid = /android/i.test(userAgent);
  const isMobile = /Mobi|Android/i.test(userAgent);
  const isTablet = /iPad|Android(?!.*Mobile)/i.test(userAgent);
  
  const isChrome = /Chrome/.test(userAgent) && /Google Inc/.test(navigator.vendor);
  const isFirefox = /Firefox/.test(userAgent);
  const isSafari = /Safari/.test(userAgent) && /Apple Computer/.test(navigator.vendor);
  const isEdge = /Edg/.test(userAgent);
  
  return {
    isIOS,
    isAndroid,
    isMobile,
    isTablet,
    isChrome,
    isFirefox,
    isSafari,
    isEdge,
    hasTouch: 'ontouchstart' in window || navigator.maxTouchPoints > 0,
    standalone: window.navigator.standalone || window.matchMedia('(display-mode: standalone)').matches
  };
};

// Responsive table configurations
export const getResponsiveTableConfig = (isMobile) => {
  if (isMobile) {
    return {
      size: 'small',
      stickyHeader: true,
      dense: true,
      hideColumns: ['volume', 'change_percent', 'market_cap'], // Hide less important columns
      maxVisibleColumns: 4,
      cellPadding: 8,
      fontSize: '0.75rem'
    };
  }
  
  return {
    size: 'medium',
    stickyHeader: false,
    dense: false,
    hideColumns: [],
    maxVisibleColumns: 10,
    cellPadding: 16,
    fontSize: '0.875rem'
  };
};

// Responsive chart configurations
export const getResponsiveChartConfig = (isMobile) => {
  if (isMobile) {
    return {
      height: 250,
      maintainAspectRatio: false,
      legend: {
        display: false
      },
      scales: {
        x: {
          ticks: {
            maxTicksLimit: 5,
            fontSize: 10
          }
        },
        y: {
          ticks: {
            maxTicksLimit: 5,
            fontSize: 10
          }
        }
      },
      plugins: {
        tooltip: {
          enabled: false // Disable on mobile for performance
        }
      }
    };
  }
  
  return {
    height: 400,
    maintainAspectRatio: false,
    legend: {
      display: true
    },
    scales: {
      x: {
        ticks: {
          maxTicksLimit: 10,
          fontSize: 12
        }
      },
      y: {
        ticks: {
          maxTicksLimit: 8,
          fontSize: 12
        }
      }
    },
    plugins: {
      tooltip: {
        enabled: true
      }
    }
  };
};

// Responsive grid configurations
export const getResponsiveGridConfig = (isMobile) => {
  if (isMobile) {
    return {
      xs: 12,
      sm: 12,
      md: 6,
      lg: 4,
      xl: 3,
      spacing: 2
    };
  }
  
  return {
    xs: 12,
    sm: 6,
    md: 4,
    lg: 3,
    xl: 2,
    spacing: 3
  };
};

// Mobile-optimized component props
export const getMobileProps = (isMobile) => ({
  // Material-UI component props optimized for mobile
  Card: {
    elevation: isMobile ? 1 : 2,
    sx: {
      borderRadius: isMobile ? 1 : 2,
      margin: isMobile ? 1 : 2
    }
  },
  
  Button: {
    size: isMobile ? 'small' : 'medium',
    variant: isMobile ? 'outlined' : 'contained',
    fullWidth: isMobile
  },
  
  TextField: {
    size: isMobile ? 'small' : 'medium',
    margin: isMobile ? 'dense' : 'normal',
    fullWidth: true
  },
  
  Typography: {
    variant: isMobile ? 'body2' : 'body1',
    sx: {
      fontSize: isMobile ? '0.875rem' : '1rem'
    }
  },
  
  IconButton: {
    size: isMobile ? 'small' : 'medium',
    sx: {
      padding: isMobile ? 0.5 : 1
    }
  },
  
  Chip: {
    size: 'small',
    variant: isMobile ? 'outlined' : 'filled'
  },
  
  Dialog: {
    fullScreen: isMobile,
    maxWidth: isMobile ? false : 'md',
    fullWidth: true
  },
  
  Menu: {
    anchorOrigin: {
      vertical: isMobile ? 'bottom' : 'top',
      horizontal: isMobile ? 'center' : 'left'
    },
    transformOrigin: {
      vertical: isMobile ? 'top' : 'top',
      horizontal: isMobile ? 'center' : 'left'
    }
  }
});

// Performance optimizations for mobile
export const getMobileOptimizations = (isMobile) => ({
  // Reduce animations on mobile
  reduceAnimations: isMobile,
  
  // Debounce search inputs
  searchDebounce: isMobile ? 500 : 300,
  
  // Reduce polling frequency
  pollingInterval: isMobile ? 5000 : 1000,
  
  // Limit concurrent requests
  maxConcurrentRequests: isMobile ? 2 : 5,
  
  // Cache settings
  cacheSize: isMobile ? 50 : 100,
  cacheTTL: isMobile ? 300000 : 180000, // 5 minutes vs 3 minutes
  
  // Virtual scrolling thresholds
  virtualScrollThreshold: isMobile ? 20 : 50,
  
  // Image loading
  lazyLoadImages: isMobile,
  
  // Bundle splitting
  loadChunksOnDemand: isMobile
});

// Accessibility enhancements for mobile
export const getMobileA11yProps = (isMobile) => ({
  // Touch target size
  minTouchTarget: isMobile ? 44 : 32,
  
  // Focus management
  focusRipple: !isMobile,
  
  // Keyboard navigation
  enableKeyboardNavigation: !isMobile,
  
  // Screen reader optimizations
  announceChanges: isMobile,
  
  // High contrast mode
  highContrastMode: false,
  
  // Reduced motion
  respectReducedMotion: true
});

// Responsive drawer configuration
export const getResponsiveDrawerConfig = (isMobile) => ({
  variant: isMobile ? 'temporary' : 'permanent',
  anchor: 'left',
  width: isMobile ? 240 : 280,
  keepMounted: isMobile, // Better mobile performance
  ModalProps: {
    keepMounted: isMobile
  },
  PaperProps: {
    sx: {
      width: isMobile ? 240 : 280,
      flexShrink: 0
    }
  }
});

// Export all utilities
export default {
  useResponsive,
  useViewport,
  useTouchEvents,
  detectDevice,
  getResponsiveTableConfig,
  getResponsiveChartConfig,
  getResponsiveGridConfig,
  getMobileProps,
  getMobileOptimizations,
  getMobileA11yProps,
  getResponsiveDrawerConfig,
  breakpoints
};