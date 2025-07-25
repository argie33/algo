/**
 * API URL Resolver - Intelligent Backend URL Detection
 * Resolves correct API Gateway URL with fallback mechanisms
 */

class ApiUrlResolver {
  constructor() {
    this.cachedUrl = null;
    this.testResults = new Map();
    this.lastUrlCheck = null;
  }

  /**
   * Get the best available API URL with intelligent detection
   */
  async getApiUrl() {
    // Return cached URL if recent and working
    if (this.cachedUrl && this.isRecentCheck()) {
      return this.cachedUrl;
    }

    // Try multiple URL resolution strategies
    const urlCandidates = this.getUrlCandidates();
    const workingUrl = await this.findWorkingUrl(urlCandidates);
    
    if (workingUrl) {
      this.cachedUrl = workingUrl;
      this.lastUrlCheck = Date.now();
      console.log(`✅ API URL resolved: ${workingUrl}`);
      return workingUrl;
    }

    // Fallback to best guess
    const fallbackUrl = urlCandidates[0];
    console.warn(`⚠️ No working API URL found, using fallback: ${fallbackUrl}`);
    return fallbackUrl;
  }

  /**
   * Get ordered list of URL candidates to try
   */
  getUrlCandidates() {
    const candidates = [];

    // 1. Environment variable (highest priority)
    if (process.env.REACT_APP_API_URL) {
      candidates.push(process.env.REACT_APP_API_URL);
    }

    // 2. CloudFormation config
    if (typeof window !== 'undefined' && window.__CLOUDFORMATION_CONFIG__) {
      const cfConfig = window.__CLOUDFORMATION_CONFIG__;
      if (cfConfig.ApiGatewayUrl) {
        candidates.push(cfConfig.ApiGatewayUrl);
      }
      if (cfConfig.ServiceUrl) {
        candidates.push(cfConfig.ServiceUrl);
      }
    }

    // 3. Runtime config
    if (typeof window !== 'undefined' && window.__CONFIG__) {
      const config = window.__CONFIG__;
      if (config.apiUrl) {
        candidates.push(config.apiUrl);
      }
      if (config.backendUrl) {
        candidates.push(config.backendUrl);
      }
    }

    // 4. Known working URLs (prioritize working Lambda URL)
    candidates.push(
      'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev',
      'http://localhost:3001/api'
    );

    // Remove duplicates and invalid URLs
    return [...new Set(candidates)].filter(url => url && typeof url === 'string' && url.length > 0);
  }

  /**
   * Test each URL candidate to find a working one
   */
  async findWorkingUrl(candidates) {
    const testPromises = candidates.map(url => this.testUrl(url));
    const results = await Promise.allSettled(testPromises);

    for (let i = 0; i < results.length; i++) {
      const result = results[i];
      const url = candidates[i];
      
      if (result.status === 'fulfilled' && result.value) {
        console.log(`✅ Working API URL found: ${url}`);
        return url;
      } else {
        console.log(`❌ API URL failed test: ${url} - ${result.reason || 'timeout'}`);
      }
    }

    return null;
  }

  /**
   * Test if a URL is working by making a health check request
   */
  async testUrl(baseUrl) {
    // Check cache first
    if (this.testResults.has(baseUrl)) {
      const cached = this.testResults.get(baseUrl);
      if (Date.now() - cached.timestamp < 60000) { // 1 minute cache
        return cached.working;
      }
    }

    try {
      const healthUrl = this.buildHealthUrl(baseUrl);
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout

      const response = await fetch(healthUrl, {
        method: 'GET',
        signal: controller.signal,
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      });

      clearTimeout(timeoutId);

      const isWorking = response.ok && response.status === 200;
      
      // Cache result
      this.testResults.set(baseUrl, {
        working: isWorking,
        timestamp: Date.now(),
        status: response.status
      });

      return isWorking;

    } catch (error) {
      // Cache failure
      this.testResults.set(baseUrl, {
        working: false,
        timestamp: Date.now(),
        error: error.message
      });

      return false;
    }
  }

  /**
   * Build health check URL from base URL
   */
  buildHealthUrl(baseUrl) {
    // Remove trailing slash
    const cleanUrl = baseUrl.replace(/\/$/, '');
    
    // Try different health endpoint patterns (fixed double /api issue)
    const healthPaths = ['/api/health/quick', '/health/quick', '/api/health', '/health'];
    
    // Use the first health path (most common)
    return `${cleanUrl}${healthPaths[0]}`;
  }

  /**
   * Check if the last URL check was recent enough
   */
  isRecentCheck() {
    return this.lastUrlCheck && (Date.now() - this.lastUrlCheck) < 300000; // 5 minutes
  }

  /**
   * Force refresh of cached URL
   */
  refresh() {
    this.cachedUrl = null;
    this.lastUrlCheck = null;
    this.testResults.clear();
  }

  /**
   * Get diagnostic information
   */
  getDiagnostics() {
    return {
      cachedUrl: this.cachedUrl,
      lastUrlCheck: this.lastUrlCheck,
      testResults: Object.fromEntries(this.testResults),
      urlCandidates: this.getUrlCandidates(),
      environment: {
        REACT_APP_API_URL: process.env.REACT_APP_API_URL,
        hasCloudFormationConfig: typeof window !== 'undefined' && !!window.__CLOUDFORMATION_CONFIG__,
        hasRuntimeConfig: typeof window !== 'undefined' && !!window.__CONFIG__
      }
    };
  }

  /**
   * Manual URL override for testing
   */
  setManualUrl(url) {
    this.cachedUrl = url;
    this.lastUrlCheck = Date.now();
    console.log(`🔧 Manual API URL override: ${url}`);
  }
}

// Create singleton instance
const apiUrlResolver = new ApiUrlResolver();

export default apiUrlResolver;