/**
 * SEO Optimization - Meta tags, structured data, and search engine optimization
 * Provides comprehensive SEO features for the financial trading platform
 */

class SEOOptimization {
  constructor() {
    this.siteName = 'Financial Trading Platform';
    this.baseUrl = window.location.origin;
    this.defaultMeta = {
      description: 'Professional financial trading platform with real-time market data, portfolio management, and advanced analytics.',
      keywords: 'trading, finance, stocks, portfolio, market data, analytics, investment',
      author: 'Financial Trading Platform',
      robots: 'noindex, nofollow', // For financial data privacy
      viewport: 'width=device-width, initial-scale=1.0'
    };
    
    this.initializeSEO();
  }

  /**
   * Initialize SEO optimization
   */
  initializeSEO() {
    this.setupBasicMeta();
    this.setupOpenGraph();
    this.setupTwitterCard();
    this.setupStructuredData();
    this.setupCanonical();
  }

  /**
   * Setup basic meta tags
   */
  setupBasicMeta() {
    const metaTags = [
      { name: 'description', content: this.defaultMeta.description },
      { name: 'keywords', content: this.defaultMeta.keywords },
      { name: 'author', content: this.defaultMeta.author },
      { name: 'robots', content: this.defaultMeta.robots },
      { name: 'viewport', content: this.defaultMeta.viewport }
    ];

    metaTags.forEach(tag => {
      this.updateMetaTag(tag.name, tag.content);
    });
  }

  /**
   * Setup Open Graph meta tags
   */
  setupOpenGraph() {
    const ogTags = [
      { property: 'og:type', content: 'website' },
      { property: 'og:site_name', content: this.siteName },
      { property: 'og:title', content: document.title || this.siteName },
      { property: 'og:description', content: this.defaultMeta.description },
      { property: 'og:url', content: window.location.href },
      { property: 'og:locale', content: 'en_US' }
    ];

    ogTags.forEach(tag => {
      this.updateMetaProperty(tag.property, tag.content);
    });
  }

  /**
   * Setup Twitter Card meta tags
   */
  setupTwitterCard() {
    const twitterTags = [
      { name: 'twitter:card', content: 'summary' },
      { name: 'twitter:title', content: document.title || this.siteName },
      { name: 'twitter:description', content: this.defaultMeta.description }
    ];

    twitterTags.forEach(tag => {
      this.updateMetaTag(tag.name, tag.content);
    });
  }

  /**
   * Setup structured data (JSON-LD)
   */
  setupStructuredData() {
    const structuredData = {
      "@context": "https://schema.org",
      "@type": "WebApplication",
      "name": this.siteName,
      "description": this.defaultMeta.description,
      "url": this.baseUrl,
      "applicationCategory": "FinanceApplication",
      "operatingSystem": "Web Browser",
      "offers": {
        "@type": "Offer",
        "category": "Financial Services"
      },
      "provider": {
        "@type": "Organization",
        "name": this.siteName
      }
    };

    this.addStructuredData(structuredData);
  }

  /**
   * Setup canonical URL
   */
  setupCanonical() {
    let canonical = document.querySelector('link[rel="canonical"]');
    if (!canonical) {
      canonical = document.createElement('link');
      canonical.rel = 'canonical';
      document.head.appendChild(canonical);
    }
    canonical.href = window.location.href.split('?')[0]; // Remove query params
  }

  /**
   * Update page meta data for specific routes
   */
  updatePageMeta(pageData) {
    const { title, description, keywords, path } = pageData;
    
    // Update title
    document.title = title ? `${title} | ${this.siteName}` : this.siteName;
    
    // Update meta description
    if (description) {
      this.updateMetaTag('description', description);
      this.updateMetaProperty('og:description', description);
      this.updateMetaTag('twitter:description', description);
    }
    
    // Update keywords
    if (keywords) {
      this.updateMetaTag('keywords', keywords);
    }
    
    // Update Open Graph
    this.updateMetaProperty('og:title', document.title);
    this.updateMetaProperty('og:url', `${this.baseUrl}${path || window.location.pathname}`);
    
    // Update Twitter Card
    this.updateMetaTag('twitter:title', document.title);
    
    // Update canonical
    this.setupCanonical();
  }

  /**
   * Update meta tag by name
   */
  updateMetaTag(name, content) {
    let meta = document.querySelector(`meta[name="${name}"]`);
    if (!meta) {
      meta = document.createElement('meta');
      meta.name = name;
      document.head.appendChild(meta);
    }
    meta.content = content;
  }

  /**
   * Update meta tag by property
   */
  updateMetaProperty(property, content) {
    let meta = document.querySelector(`meta[property="${property}"]`);
    if (!meta) {
      meta = document.createElement('meta');
      meta.property = property;
      document.head.appendChild(meta);
    }
    meta.content = content;
  }

  /**
   * Add structured data to page
   */
  addStructuredData(data) {
    const existingScript = document.querySelector('script[type="application/ld+json"]');
    if (existingScript) {
      existingScript.remove();
    }

    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.textContent = JSON.stringify(data);
    document.head.appendChild(script);
  }

  /**
   * Generate page-specific meta data
   */
  getPageMeta(routePath) {
    const pageMetaMap = {
      '/': {
        title: 'Dashboard',
        description: 'Real-time trading dashboard with portfolio overview, market data, and performance analytics.',
        keywords: 'dashboard, portfolio, real-time, trading, overview'
      },
      '/portfolio': {
        title: 'Portfolio Management',
        description: 'Comprehensive portfolio tracking with performance analytics, risk assessment, and asset allocation.',
        keywords: 'portfolio, management, tracking, performance, risk, assets'
      },
      '/live-data': {
        title: 'Live Market Data',
        description: 'Real-time market data streaming with live prices, charts, and market indicators.',
        keywords: 'live data, real-time, market, streaming, prices, charts'
      },
      '/settings': {
        title: 'Account Settings',
        description: 'Manage your account settings, API keys, and trading preferences.',
        keywords: 'settings, account, API keys, preferences, configuration'
      },
      '/market-overview': {
        title: 'Market Overview',
        description: 'Comprehensive market overview with sector performance, market movers, and economic indicators.',
        keywords: 'market overview, sectors, movers, indicators, analysis'
      },
      '/technical-analysis': {
        title: 'Technical Analysis',
        description: 'Advanced technical analysis tools with charts, indicators, and trading signals.',
        keywords: 'technical analysis, charts, indicators, signals, trading'
      },
      '/news': {
        title: 'Financial News',
        description: 'Latest financial news, market updates, and economic reports.',
        keywords: 'financial news, market updates, economics, reports'
      },
      '/watchlist': {
        title: 'Watchlist',
        description: 'Monitor your favorite stocks and securities with real-time updates.',
        keywords: 'watchlist, stocks, monitoring, favorites, tracking'
      }
    };

    return pageMetaMap[routePath] || {
      title: 'Financial Trading Platform',
      description: this.defaultMeta.description,
      keywords: this.defaultMeta.keywords
    };
  }

  /**
   * Generate sitemap data
   */
  generateSitemap() {
    const routes = [
      { path: '/', priority: 1.0, changefreq: 'daily' },
      { path: '/portfolio', priority: 0.9, changefreq: 'daily' },
      { path: '/live-data', priority: 0.8, changefreq: 'always' },
      { path: '/market-overview', priority: 0.7, changefreq: 'hourly' },
      { path: '/technical-analysis', priority: 0.7, changefreq: 'daily' },
      { path: '/news', priority: 0.6, changefreq: 'hourly' },
      { path: '/watchlist', priority: 0.6, changefreq: 'daily' },
      { path: '/settings', priority: 0.4, changefreq: 'weekly' }
    ];

    return routes.map(route => ({
      ...route,
      url: `${this.baseUrl}${route.path}`,
      lastmod: new Date().toISOString()
    }));
  }

  /**
   * Optimize images for SEO
   */
  optimizeImages() {
    const images = document.querySelectorAll('img:not([alt])');
    images.forEach(img => {
      // Add alt text based on context
      const altText = this.generateAltText(img);
      if (altText) {
        img.alt = altText;
      }
    });
  }

  /**
   * Generate alt text for images
   */
  generateAltText(img) {
    const src = img.src;
    const context = img.closest('[data-symbol], [data-chart-type], [data-component]');
    
    if (src.includes('chart')) {
      const symbol = context?.dataset?.symbol || 'stock';
      const chartType = context?.dataset?.chartType || 'price';
      return `${symbol} ${chartType} chart`;
    }
    
    if (src.includes('logo')) {
      return 'Company logo';
    }
    
    if (src.includes('icon')) {
      return 'Icon';
    }
    
    return 'Financial data visualization';
  }

  /**
   * Add breadcrumb structured data
   */
  addBreadcrumbData(breadcrumbs) {
    const breadcrumbData = {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      "itemListElement": breadcrumbs.map((crumb, index) => ({
        "@type": "ListItem",
        "position": index + 1,
        "name": crumb.name,
        "item": `${this.baseUrl}${crumb.path}`
      }))
    };

    this.addStructuredData(breadcrumbData);
  }

  /**
   * Monitor and fix SEO issues
   */
  runSEOAudit() {
    const issues = [];

    // Check title
    if (!document.title || document.title.length > 60) {
      issues.push('Page title missing or too long (>60 chars)');
    }

    // Check meta description
    const description = document.querySelector('meta[name="description"]');
    if (!description || description.content.length > 160) {
      issues.push('Meta description missing or too long (>160 chars)');
    }

    // Check headings
    const h1s = document.querySelectorAll('h1');
    if (h1s.length === 0) {
      issues.push('No H1 heading found');
    } else if (h1s.length > 1) {
      issues.push('Multiple H1 headings found');
    }

    // Check images without alt text
    const imagesWithoutAlt = document.querySelectorAll('img:not([alt])');
    if (imagesWithoutAlt.length > 0) {
      issues.push(`${imagesWithoutAlt.length} images missing alt text`);
    }

    // Check internal links
    const internalLinks = document.querySelectorAll('a[href^="/"], a[href^="./"], a[href^="../"]');
    const brokenLinks = Array.from(internalLinks).filter(link => !link.textContent.trim());
    if (brokenLinks.length > 0) {
      issues.push(`${brokenLinks.length} links missing anchor text`);
    }

    return {
      timestamp: new Date().toISOString(),
      issuesFound: issues.length,
      issues,
      score: Math.max(0, 100 - (issues.length * 10))
    };
  }

  /**
   * Get SEO recommendations
   */
  getSEORecommendations() {
    return [
      'Keep page titles under 60 characters',
      'Write compelling meta descriptions under 160 characters',
      'Use one H1 heading per page with target keywords',
      'Add alt text to all images describing their content',
      'Use semantic HTML structure with proper heading hierarchy',
      'Implement breadcrumb navigation for better user experience',
      'Optimize page loading speed for better search rankings',
      'Use HTTPS for all pages (security ranking factor)',
      'Create XML sitemap for search engine crawlers',
      'Monitor Core Web Vitals for page experience metrics'
    ];
  }
}

// Create singleton instance
const seoOptimization = new SEOOptimization();

// React hook for SEO optimization
export const useSEO = () => {
  const updatePageMeta = React.useCallback((pageData) => {
    seoOptimization.updatePageMeta(pageData);
  }, []);

  const addBreadcrumbs = React.useCallback((breadcrumbs) => {
    seoOptimization.addBreadcrumbData(breadcrumbs);
  }, []);

  return {
    updatePageMeta,
    addBreadcrumbs,
    audit: seoOptimization.runSEOAudit.bind(seoOptimization),
    recommendations: seoOptimization.getSEORecommendations.bind(seoOptimization)
  };
};

// Add to React import
const React = require('react');

export default seoOptimization;
export { SEOOptimization };

// Export utilities
export const updatePageMeta = (pageData) => 
  seoOptimization.updatePageMeta(pageData);

export const runSEOAudit = () => 
  seoOptimization.runSEOAudit();

export const getSEORecommendations = () => 
  seoOptimization.getSEORecommendations();