/**
 * Code Splitting & Lazy Loading - Performance optimization through dynamic imports
 * Provides intelligent code splitting and lazy loading capabilities
 */

import React, { Suspense, lazy } from 'react';

class CodeSplittingOptimizer {
  constructor() {
    this.loadedComponents = new Map();
    this.loadingComponents = new Set();
    this.preloadQueue = [];
    this.routeMetrics = new Map();
    
    this.initializeCodeSplitting();
  }

  /**
   * Initialize code splitting optimization
   */
  initializeCodeSplitting() {
    this.setupRoutePreloading();
    this.setupIntersectionObserver();
    this.monitorPerformance();
  }

  /**
   * Create lazy component with enhanced loading
   */
  createLazyComponent(importFn, options = {}) {
    const {
      fallback = <div className="loading-spinner">Loading...</div>,
      preload = false,
      retryAttempts = 3,
      chunkName
    } = options;

    const LazyComponent = lazy(() => 
      this.retryImport(importFn, retryAttempts, chunkName)
    );

    const WrappedComponent = (props) => (
      <Suspense fallback={fallback}>
        <LazyComponent {...props} />
      </Suspense>
    );

    // Preload if requested
    if (preload) {
      this.preloadComponent(importFn, chunkName);
    }

    return WrappedComponent;
  }

  /**
   * Retry import with exponential backoff
   */
  async retryImport(importFn, retryAttempts, chunkName) {
    const startTime = performance.now();
    
    for (let attempt = 1; attempt <= retryAttempts; attempt++) {
      try {
        const module = await importFn();
        
        // Record metrics
        const loadTime = performance.now() - startTime;
        this.recordLoadMetrics(chunkName, loadTime, attempt, true);
        
        return module;
      } catch (error) {
        console.warn(`Import attempt ${attempt} failed for ${chunkName}:`, error);
        
        if (attempt === retryAttempts) {
          this.recordLoadMetrics(chunkName, performance.now() - startTime, attempt, false);
          throw new Error(`Failed to load component ${chunkName} after ${retryAttempts} attempts`);
        }
        
        // Exponential backoff
        await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 1000));
      }
    }
  }

  /**
   * Preload component
   */
  async preloadComponent(importFn, chunkName) {
    if (this.loadedComponents.has(chunkName) || this.loadingComponents.has(chunkName)) {
      return;
    }

    this.loadingComponents.add(chunkName);
    
    try {
      const module = await importFn();
      this.loadedComponents.set(chunkName, module);
      console.log(`✅ Preloaded component: ${chunkName}`);
    } catch (error) {
      console.warn(`❌ Failed to preload component: ${chunkName}`, error);
    } finally {
      this.loadingComponents.delete(chunkName);
    }
  }

  /**
   * Setup route-based preloading
   */
  setupRoutePreloading() {
    // Define route components for preloading
    this.routeComponents = {
      '/portfolio': () => import('../pages/Portfolio'),
      '/live-data': () => import('../pages/LiveData'),
      '/market-overview': () => import('../pages/CryptoMarketOverview'),
      '/technical-analysis': () => import('../pages/TechnicalAnalysis'),
      '/settings': () => import('../pages/Settings'),
      '/news': () => import('../pages/News'),
      '/watchlist': () => import('../pages/Watchlist')
    };

    // Preload critical routes
    this.preloadCriticalRoutes();
    
    // Setup hover preloading for navigation
    this.setupHoverPreloading();
  }

  /**
   * Preload critical routes
   */
  preloadCriticalRoutes() {
    const criticalRoutes = ['/portfolio', '/live-data'];
    
    // Preload after initial page load
    setTimeout(() => {
      criticalRoutes.forEach(route => {
        if (this.routeComponents[route]) {
          this.preloadComponent(this.routeComponents[route], route);
        }
      });
    }, 2000);
  }

  /**
   * Setup hover preloading for navigation links
   */
  setupHoverPreloading() {
    document.addEventListener('mouseover', (e) => {
      const link = e.target.closest('a[href]');
      if (!link) return;

      const href = link.getAttribute('href');
      if (href && this.routeComponents[href]) {
        this.preloadComponent(this.routeComponents[href], href);
      }
    });
  }

  /**
   * Setup intersection observer for lazy loading
   */
  setupIntersectionObserver() {
    if (!('IntersectionObserver' in window)) return;

    this.observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const element = entry.target;
          const loadAction = element.dataset.lazyLoad;
          
          if (loadAction === 'component') {
            this.loadIntersectingComponent(element);
          } else if (loadAction === 'image') {
            this.loadIntersectingImage(element);
          }
          
          this.observer.unobserve(element);
        }
      });
    }, {
      rootMargin: '50px 0px',
      threshold: 0.1
    });
  }

  /**
   * Load component when it intersects viewport
   */
  loadIntersectingComponent(element) {
    const componentName = element.dataset.component;
    const importPath = element.dataset.importPath;
    
    if (importPath) {
      import(importPath)
        .then(module => {
          console.log(`📦 Lazy loaded component: ${componentName}`);
          element.dispatchEvent(new CustomEvent('componentLoaded', { 
            detail: { module, componentName } 
          }));
        })
        .catch(error => {
          console.error(`❌ Failed to lazy load component: ${componentName}`, error);
        });
    }
  }

  /**
   * Load image when it intersects viewport
   */
  loadIntersectingImage(element) {
    const src = element.dataset.src;
    if (src) {
      element.src = src;
      element.removeAttribute('data-src');
      element.classList.add('loaded');
    }
  }

  /**
   * Observe element for lazy loading
   */
  observeElement(element) {
    if (this.observer) {
      this.observer.observe(element);
    }
  }

  /**
   * Monitor performance metrics
   */
  monitorPerformance() {
    // Monitor chunk loading performance
    if ('PerformanceObserver' in window) {
      const observer = new PerformanceObserver((list) => {
        list.getEntries().forEach(entry => {
          if (entry.name.includes('chunk')) {
            this.recordChunkMetrics(entry);
          }
        });
      });

      observer.observe({ entryTypes: ['resource'] });
    }
  }

  /**
   * Record load metrics
   */
  recordLoadMetrics(chunkName, loadTime, attempts, success) {
    const metrics = {
      chunkName,
      loadTime,
      attempts,
      success,
      timestamp: Date.now()
    };

    this.routeMetrics.set(chunkName, metrics);
    
    if (loadTime > 3000) {
      console.warn(`🐌 Slow chunk loading: ${chunkName} took ${loadTime.toFixed(2)}ms`);
    }
  }

  /**
   * Record chunk metrics
   */
  recordChunkMetrics(entry) {
    console.log(`📊 Chunk loaded: ${entry.name} (${entry.duration.toFixed(2)}ms)`);
  }

  /**
   * Get bundle analysis
   */
  getBundleAnalysis() {
    const analysis = {
      totalChunks: this.loadedComponents.size,
      loadingChunks: this.loadingComponents.size,
      metrics: Object.fromEntries(this.routeMetrics),
      recommendations: this.getBundleRecommendations()
    };

    return analysis;
  }

  /**
   * Get bundle optimization recommendations
   */
  getBundleRecommendations() {
    const recommendations = [];
    
    // Analyze load times
    for (const [chunk, metrics] of this.routeMetrics) {
      if (metrics.loadTime > 2000) {
        recommendations.push(`Consider optimizing ${chunk} - load time: ${metrics.loadTime.toFixed(2)}ms`);
      }
      
      if (metrics.attempts > 1) {
        recommendations.push(`${chunk} required ${metrics.attempts} attempts to load - check network reliability`);
      }
    }

    return recommendations;
  }
}

// Create singleton instance
const codeSplittingOptimizer = new CodeSplittingOptimizer();

/**
 * Higher-order component for lazy loading
 */
export const withLazyLoading = (importFn, options = {}) => {
  return codeSplittingOptimizer.createLazyComponent(importFn, options);
};

/**
 * Lazy image component
 */
export const LazyImage = ({ src, alt, className, placeholder, ...props }) => {
  const [loaded, setLoaded] = React.useState(false);
  const [inView, setInView] = React.useState(false);
  const imgRef = React.useRef();

  React.useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.disconnect();
        }
      },
      { threshold: 0.1 }
    );

    if (imgRef.current) {
      observer.observe(imgRef.current);
    }

    return () => observer.disconnect();
  }, []);

  const handleLoad = () => {
    setLoaded(true);
  };

  return (
    <div ref={imgRef} className={`lazy-image-container ${className || ''}`}>
      {inView && (
        <img
          src={src}
          alt={alt}
          onLoad={handleLoad}
          className={`lazy-image ${loaded ? 'loaded' : 'loading'}`}
          {...props}
        />
      )}
      {!loaded && placeholder && (
        <div className="lazy-image-placeholder">{placeholder}</div>
      )}
    </div>
  );
};

/**
 * Lazy section component for below-the-fold content
 */
export const LazySection = ({ children, fallback, threshold = 0.1 }) => {
  const [inView, setInView] = React.useState(false);
  const sectionRef = React.useRef();

  React.useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.disconnect();
        }
      },
      { threshold }
    );

    if (sectionRef.current) {
      observer.observe(sectionRef.current);
    }

    return () => observer.disconnect();
  }, [threshold]);

  return (
    <div ref={sectionRef} className="lazy-section">
      {inView ? children : (fallback || <div className="section-placeholder">Loading...</div>)}
    </div>
  );
};

/**
 * React hook for code splitting
 */
export const useCodeSplitting = () => {
  const preloadRoute = React.useCallback((route) => {
    const importFn = codeSplittingOptimizer.routeComponents[route];
    if (importFn) {
      codeSplittingOptimizer.preloadComponent(importFn, route);
    }
  }, []);

  const observeElement = React.useCallback((element) => {
    codeSplittingOptimizer.observeElement(element);
  }, []);

  return {
    preloadRoute,
    observeElement,
    analysis: codeSplittingOptimizer.getBundleAnalysis.bind(codeSplittingOptimizer)
  };
};

// Route components with lazy loading
export const LazyPortfolio = withLazyLoading(
  () => import('../pages/Portfolio'),
  { chunkName: 'portfolio', preload: true }
);

export const LazyLiveData = withLazyLoading(
  () => import('../pages/LiveData'),
  { chunkName: 'live-data', preload: true }
);

export const LazyMarketOverview = withLazyLoading(
  () => import('../pages/CryptoMarketOverview'),
  { chunkName: 'market-overview' }
);

export const LazyTechnicalAnalysis = withLazyLoading(
  () => import('../pages/TechnicalAnalysis'),
  { chunkName: 'technical-analysis' }
);

export const LazySettings = withLazyLoading(
  () => import('../pages/Settings'),
  { chunkName: 'settings' }
);

export const LazyNews = withLazyLoading(
  () => import('../pages/News'),
  { chunkName: 'news' }
);

export const LazyWatchlist = withLazyLoading(
  () => import('../pages/Watchlist'),
  { chunkName: 'watchlist' }
);

export default codeSplittingOptimizer;
export { CodeSplittingOptimizer };