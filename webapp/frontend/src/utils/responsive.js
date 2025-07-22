// Responsive utilities for React components
// Provides hooks and utilities for responsive design and mobile optimization

import { useState, useEffect } from 'react';

// Breakpoint definitions
export const breakpoints = {
  xs: 0,
  sm: 600,
  md: 960,
  lg: 1280,
  xl: 1920
};

// Main responsive hook
export const useResponsive = () => {
  const [windowSize, setWindowSize] = useState({
    width: typeof window !== 'undefined' ? window.innerWidth : 1024,
    height: typeof window !== 'undefined' ? window.innerHeight : 768
  });

  useEffect(() => {
    const handleResize = () => {
      setWindowSize({
        width: window.innerWidth,
        height: window.innerHeight
      });
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const getBreakpoint = () => {
    const width = windowSize.width;
    if (width >= breakpoints.xl) return 'xl';
    if (width >= breakpoints.lg) return 'lg';
    if (width >= breakpoints.md) return 'md';
    if (width >= breakpoints.sm) return 'sm';
    return 'xs';
  };

  return {
    ...windowSize,
    breakpoint: getBreakpoint(),
    isMobile: windowSize.width < breakpoints.md,
    isTablet: windowSize.width >= breakpoints.sm && windowSize.width < breakpoints.lg,
    isDesktop: windowSize.width >= breakpoints.lg
  };
};

// Viewport hook
export const useViewport = () => {
  const [viewport, setViewport] = useState({
    width: typeof window !== 'undefined' ? window.innerWidth : 1024,
    height: typeof window !== 'undefined' ? window.innerHeight : 768,
    isLandscape: typeof window !== 'undefined' ? window.innerWidth > window.innerHeight : true
  });

  useEffect(() => {
    const handleResize = () => {
      setViewport({
        width: window.innerWidth,
        height: window.innerHeight,
        isLandscape: window.innerWidth > window.innerHeight
      });
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return viewport;
};

// Touch events hook
export const useTouchEvents = () => {
  const [touchStart, setTouchStart] = useState(null);
  const [touchEnd, setTouchEnd] = useState(null);

  const handleTouchStart = (e) => {
    setTouchEnd(null);
    setTouchStart(e.targetTouches[0].clientX);
  };

  const handleTouchMove = (e) => {
    setTouchEnd(e.targetTouches[0].clientX);
  };

  const handleTouchEnd = () => {
    if (!touchStart || !touchEnd) return null;
    
    const distance = touchStart - touchEnd;
    const isLeftSwipe = distance > 50;
    const isRightSwipe = distance < -50;

    if (isLeftSwipe) return 'left';
    if (isRightSwipe) return 'right';
    return null;
  };

  return {
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
    touchStart,
    touchEnd
  };
};

// Device detection utility
export const detectDevice = () => {
  const userAgent = navigator.userAgent.toLowerCase();
  const isMobile = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/.test(userAgent);
  const isTablet = /ipad|android(?!.*mobile)/.test(userAgent);
  const isDesktop = !isMobile && !isTablet;
  
  return {
    isMobile,
    isTablet,
    isDesktop,
    isIOS: /iphone|ipad|ipod/.test(userAgent),
    isAndroid: /android/.test(userAgent),
    isTouchDevice: 'ontouchstart' in window || navigator.maxTouchPoints > 0,
    screenWidth: window.innerWidth,
    screenHeight: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio || 1
  };
};

// Responsive table configuration utility
export const getResponsiveTableConfig = (size = 'md') => {
  const configs = {
    xs: { rowsPerPage: 5, showHeader: false, stickyHeader: false },
    sm: { rowsPerPage: 10, showHeader: true, stickyHeader: false },
    md: { rowsPerPage: 15, showHeader: true, stickyHeader: true },
    lg: { rowsPerPage: 25, showHeader: true, stickyHeader: true },
    xl: { rowsPerPage: 50, showHeader: true, stickyHeader: true }
  };
  return configs[size] || configs.md;
};

// Responsive chart configuration utility
export const getResponsiveChartConfig = (size = 'md') => {
  const configs = {
    xs: { height: 200, showLegend: false, showAxis: false },
    sm: { height: 250, showLegend: false, showAxis: true },
    md: { height: 350, showLegend: true, showAxis: true },
    lg: { height: 450, showLegend: true, showAxis: true },
    xl: { height: 600, showLegend: true, showAxis: true }
  };
  return configs[size] || configs.md;
};

// Responsive grid configuration utility
export const getResponsiveGridConfig = (size = 'md') => {
  const configs = {
    xs: { columns: 1, spacing: 1, showSearch: false },
    sm: { columns: 2, spacing: 2, showSearch: true },
    md: { columns: 3, spacing: 2, showSearch: true },
    lg: { columns: 4, spacing: 3, showSearch: true },
    xl: { columns: 6, spacing: 3, showSearch: true }
  };
  return configs[size] || configs.md;
};

// Mobile optimized props utility
export const getMobileProps = (baseProps = {}) => {
  const device = detectDevice();
  if (device.isMobile) {
    return {
      ...baseProps,
      size: 'small',
      dense: true,
      disableRipple: true
    };
  }
  return baseProps;
};

// Mobile performance optimizations
export const getMobileOptimizations = () => {
  const device = detectDevice();
  return {
    virtualizeRows: device.isMobile,
    lazyLoad: device.isMobile,
    maxCacheSize: device.isMobile ? 50 : 200,
    enableAnimations: !device.isMobile || device.devicePixelRatio >= 2
  };
};

// Mobile accessibility props
export const getMobileA11yProps = (baseProps = {}) => {
  const device = detectDevice();
  if (device.isMobile) {
    return {
      ...baseProps,
      'aria-label': baseProps['aria-label'] || 'Mobile optimized component',
      tabIndex: 0,
      role: baseProps.role || 'button'
    };
  }
  return baseProps;
};

// Responsive drawer configuration
export const getResponsiveDrawerConfig = (size = 'md') => {
  const configs = {
    xs: { variant: 'temporary', width: '100%', anchor: 'bottom' },
    sm: { variant: 'temporary', width: 300, anchor: 'left' },
    md: { variant: 'permanent', width: 240, anchor: 'left' },
    lg: { variant: 'permanent', width: 280, anchor: 'left' },
    xl: { variant: 'permanent', width: 320, anchor: 'left' }
  };
  return configs[size] || configs.md;
};

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