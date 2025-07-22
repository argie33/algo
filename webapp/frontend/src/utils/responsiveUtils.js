// Responsive utility functions - Non-React utilities only
// Device detection and responsive configuration utilities

// Breakpoint utilities
export const breakpoints = {
  xs: 0,
  sm: 600,
  md: 900,
  lg: 1200,
  xl: 1536
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
            maxTicksLimit: 4,
            font: {
              size: 10
            }
          }
        },
        y: {
          ticks: {
            maxTicksLimit: 5,
            font: {
              size: 10
            }
          }
        }
      },
      elements: {
        point: {
          radius: 2
        }
      }
    };
  }
  
  return {
    height: 400,
    maintainAspectRatio: true,
    legend: {
      display: true,
      position: 'top'
    },
    scales: {
      x: {
        ticks: {
          maxTicksLimit: 10,
          font: {
            size: 12
          }
        }
      },
      y: {
        ticks: {
          maxTicksLimit: 8,
          font: {
            size: 12
          }
        }
      }
    },
    elements: {
      point: {
        radius: 3
      }
    }
  };
};

// Mobile navigation configurations
export const getMobileNavConfig = () => {
  return {
    swipeThreshold: 50,
    tapTimeout: 300,
    doubleTapTimeout: 400,
    longPressTimeout: 500,
    animationDuration: 200
  };
};

// Mobile performance optimizations
export const getMobileOptimizations = () => {
  return {
    enableVirtualization: true,
    lazyLoadImages: true,
    reduceAnimations: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    enableTouchOptimizations: 'ontouchstart' in window,
    minTouchTarget: 44, // Minimum touch target size in pixels
    debounceDelay: 150,
    throttleDelay: 100
  };
};