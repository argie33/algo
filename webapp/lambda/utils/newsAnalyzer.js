const axios = require('axios');
const { query } = require('./database');
const timeoutHelper = require('./timeoutHelper');

class NewsAnalyzer {
  constructor() {
    this.sources = {
      'Reuters': { reliability: 0.95, bias: 0.1 },
      'Bloomberg': { reliability: 0.92, bias: 0.15 },
      'Wall Street Journal': { reliability: 0.90, bias: 0.2 },
      'Financial Times': { reliability: 0.88, bias: 0.15 },
      'MarketWatch': { reliability: 0.85, bias: 0.25 },
      'Yahoo Finance': { reliability: 0.75, bias: 0.3 },
      'CNN Business': { reliability: 0.80, bias: 0.35 },
      'CNBC': { reliability: 0.82, bias: 0.3 },
      'Seeking Alpha': { reliability: 0.70, bias: 0.4 },
      'Benzinga': { reliability: 0.65, bias: 0.45 },
      'TradingView': { reliability: 0.60, bias: 0.5 },
      'Motley Fool': { reliability: 0.55, bias: 0.6 }
    };
    
    this.categories = {
      'earnings': ['earnings', 'quarterly', 'revenue', 'profit', 'eps'],
      'merger': ['merger', 'acquisition', 'takeover', 'buyout', 'deal'],
      'regulatory': ['regulatory', 'sec', 'fda', 'government', 'policy'],
      'analyst': ['analyst', 'rating', 'upgrade', 'downgrade', 'target'],
      'economic': ['economic', 'gdp', 'inflation', 'fed', 'interest'],
      'technology': ['technology', 'tech', 'software', 'hardware', 'ai'],
      'healthcare': ['healthcare', 'pharma', 'drug', 'medical', 'biotech'],
      'energy': ['energy', 'oil', 'gas', 'renewable', 'solar'],
      'finance': ['bank', 'financial', 'credit', 'loan', 'mortgage'],
      'retail': ['retail', 'consumer', 'sales', 'store', 'shopping']
    };
  }

  async fetchNewsFromSources() {
    const newsItems = [];
    
    try {
      // Try multiple free news sources
      const sources = [
        this.fetchFromAlphaVantage(),
        this.fetchFromPolygon(),
        this.fetchFromYahooFinance(),
        this.fetchFromMarketaux(),
        this.fetchFromNewsAPI()
      ];
      
      const results = await Promise.allSettled(sources);
      
      results.forEach((result, index) => {
        if (result.status === 'fulfilled' && result.value) {
          newsItems.push(...result.value);
        } else {
          console.warn(`News source ${index + 1} failed:`, result.reason);
        }
      });
      
      // If no sources work, return mock data
      if (newsItems.length === 0) {
        console.log('All news sources failed, using mock data');
        return this.getMockNewsData();
      }
      
      return newsItems;
    } catch (error) {
      console.error('Error fetching news:', error);
      return this.getMockNewsData();
    }
  }

  async fetchFromAlphaVantage() {
    try {
      // AlphaVantage has a free news API with improved timeout handling
      const response = await timeoutHelper.newsApiCall(async () => {
        return axios.get('https://www.alphavantage.co/query', {
          params: {
            function: 'NEWS_SENTIMENT',
            apikey: process.env.ALPHAVANTAGE_API_KEY || 'demo',
            limit: 50
          },
          timeout: 8000
        });
      }, {
        operation: 'alphavantage-news',
        retries: 1
      });
      
      if (response.data && response.data.feed) {
        return response.data.feed.map(item => ({
          title: item.title,
          content: item.summary,
          source: item.source,
          author: item.authors || 'Unknown',
          published_at: item.time_published,
          url: item.url,
          category: this.categorizeNews(item.title + ' ' + item.summary),
          symbol: this.extractSymbol(item.title + ' ' + item.summary),
          keywords: this.extractKeywords(item.title + ' ' + item.summary),
          summary: item.summary,
          source_type: 'alphavantage'
        }));
      }
      
      return [];
    } catch (error) {
      console.error('Error fetching from AlphaVantage:', error.message);
      return [];
    }
  }

  async fetchFromPolygon() {
    try {
      // Polygon has a free tier with improved timeout handling
      const response = await timeoutHelper.newsApiCall(async () => {
        return axios.get('https://api.polygon.io/v2/reference/news', {
          params: {
            apikey: process.env.POLYGON_API_KEY || 'demo',
            limit: 50
          },
          timeout: 8000
        });
      }, {
        operation: 'polygon-news',
        retries: 1
      });
      
      if (response.data && response.data.results) {
        return response.data.results.map(item => ({
          title: item.title,
          content: item.description,
          source: item.publisher.name,
          author: item.author || 'Unknown',
          published_at: item.published_utc,
          url: item.article_url,
          category: this.categorizeNews(item.title + ' ' + item.description),
          symbol: this.extractSymbol(item.title + ' ' + item.description),
          keywords: this.extractKeywords(item.title + ' ' + item.description),
          summary: item.description,
          source_type: 'polygon'
        }));
      }
      
      return [];
    } catch (error) {
      console.error('Error fetching from Polygon:', error.message);
      return [];
    }
  }

  async fetchFromYahooFinance() {
    try {
      // Yahoo Finance RSS feeds (free)
      const rssFeeds = [
        'https://feeds.finance.yahoo.com/rss/2.0/headline',
        'https://feeds.finance.yahoo.com/rss/2.0/topstories'
      ];
      
      const newsItems = [];
      
      for (const feed of rssFeeds) {
        try {
          const response = await timeoutHelper.newsApiCall(async () => {
            return axios.get(feed, { timeout: 8000 });
          }, {
            operation: 'yahoo-rss',
            retries: 0
          });
          // Parse RSS would require xml2js, for now return mock structure
          newsItems.push({
            title: 'Yahoo Finance Market Update',
            content: 'Latest market news from Yahoo Finance',
            source: 'Yahoo Finance',
            author: 'Yahoo Finance',
            published_at: new Date().toISOString(),
            url: 'https://finance.yahoo.com',
            category: 'market',
            symbol: null,
            keywords: ['market', 'update', 'finance'],
            summary: 'Latest market news from Yahoo Finance',
            source_type: 'yahoo'
          });
        } catch (feedError) {
          console.warn(`Failed to fetch Yahoo feed ${feed}:`, feedError.message);
        }
      }
      
      return newsItems;
    } catch (error) {
      console.error('Error fetching from Yahoo Finance:', error.message);
      return [];
    }
  }

  async fetchFromMarketaux() {
    try {
      // Marketaux has a free tier with improved timeout handling
      const response = await timeoutHelper.newsApiCall(async () => {
        return axios.get('https://api.marketaux.com/v1/news/all', {
          params: {
            api_token: process.env.MARKETAUX_API_KEY || 'demo',
            limit: 50,
            language: 'en'
          },
          timeout: 8000
        });
      }, {
        operation: 'marketaux-news',
        retries: 1
      });
      
      if (response.data && response.data.data) {
        return response.data.data.map(item => ({
          title: item.title,
          content: item.description,
          source: item.source,
          author: item.source,
          published_at: item.published_at,
          url: item.url,
          category: this.categorizeNews(item.title + ' ' + item.description),
          symbol: this.extractSymbol(item.title + ' ' + item.description),
          keywords: this.extractKeywords(item.title + ' ' + item.description),
          summary: item.snippet,
          source_type: 'marketaux'
        }));
      }
      
      return [];
    } catch (error) {
      console.error('Error fetching from Marketaux:', error.message);
      return [];
    }
  }

  async fetchFromNewsAPI() {
    try {
      // NewsAPI has a free tier with improved timeout handling
      const response = await timeoutHelper.newsApiCall(async () => {
        return axios.get('https://newsapi.org/v2/everything', {
          params: {
            apiKey: process.env.NEWS_API_KEY || 'demo',
            q: 'stocks OR trading OR market OR finance',
            language: 'en',
            sortBy: 'publishedAt',
            pageSize: 50
          },
          timeout: 8000
        });
      }, {
        operation: 'newsapi-news',
        retries: 1
      });
      
      if (response.data && response.data.articles) {
        return response.data.articles.map(item => ({
          title: item.title,
          content: item.description,
          source: item.source.name,
          author: item.author || 'Unknown',
          published_at: item.publishedAt,
          url: item.url,
          category: this.categorizeNews(item.title + ' ' + item.description),
          symbol: this.extractSymbol(item.title + ' ' + item.description),
          keywords: this.extractKeywords(item.title + ' ' + item.description),
          summary: item.description,
          source_type: 'newsapi'
        }));
      }
      
      return [];
    } catch (error) {
      console.error('Error fetching from NewsAPI:', error.message);
      return [];
    }
  }

  getMockNewsData() {
    const mockNews = [
      {
        title: 'Apple Reports Strong Q4 Earnings, Revenue Beats Expectations',
        content: 'Apple Inc. reported fourth-quarter earnings that exceeded analyst expectations, driven by strong iPhone sales and services revenue growth.',
        source: 'Reuters',
        author: 'Financial Reporter',
        published_at: new Date(Date.now() - 3600000).toISOString(),
        url: 'https://example.com/apple-earnings',
        category: 'earnings',
        symbol: 'AAPL',
        keywords: ['Apple', 'earnings', 'iPhone', 'revenue', 'Q4'],
        summary: 'Apple beats Q4 earnings expectations with strong iPhone sales',
        source_type: 'mock'
      },
      {
        title: 'Federal Reserve Signals Potential Rate Cut in 2024',
        content: 'The Federal Reserve indicated it may consider lowering interest rates in 2024 if inflation continues to moderate.',
        source: 'Bloomberg',
        author: 'Economics Team',
        published_at: new Date(Date.now() - 7200000).toISOString(),
        url: 'https://example.com/fed-rates',
        category: 'economic',
        symbol: null,
        keywords: ['Federal Reserve', 'interest rates', 'inflation', '2024'],
        summary: 'Fed signals potential rate cuts as inflation moderates',
        source_type: 'mock'
      },
      {
        title: 'Tesla Stock Surges on Strong China Sales Data',
        content: 'Tesla shares jumped 5% in pre-market trading after reporting stronger-than-expected vehicle deliveries in China.',
        source: 'MarketWatch',
        author: 'Auto Industry Reporter',
        published_at: new Date(Date.now() - 10800000).toISOString(),
        url: 'https://example.com/tesla-china',
        category: 'earnings',
        symbol: 'TSLA',
        keywords: ['Tesla', 'China', 'deliveries', 'stock'],
        summary: 'Tesla stock rises on strong China delivery numbers',
        source_type: 'mock'
      },
      {
        title: 'Microsoft Announces AI Partnership with OpenAI',
        content: 'Microsoft announced a deeper partnership with OpenAI to integrate advanced AI capabilities across its product suite.',
        source: 'Wall Street Journal',
        author: 'Technology Reporter',
        published_at: new Date(Date.now() - 14400000).toISOString(),
        url: 'https://example.com/microsoft-ai',
        category: 'technology',
        symbol: 'MSFT',
        keywords: ['Microsoft', 'AI', 'OpenAI', 'partnership'],
        summary: 'Microsoft deepens AI partnership with OpenAI',
        source_type: 'mock'
      },
      {
        title: 'Market Volatility Expected as Earnings Season Begins',
        content: 'Wall Street analysts predict increased market volatility as major companies begin reporting quarterly earnings.',
        source: 'CNBC',
        author: 'Market Analyst',
        published_at: new Date(Date.now() - 18000000).toISOString(),
        url: 'https://example.com/earnings-season',
        category: 'market',
        symbol: null,
        keywords: ['market', 'volatility', 'earnings', 'season'],
        summary: 'Analysts expect volatility during earnings season',
        source_type: 'mock'
      }
    ];
    
    return mockNews;
  }

  categorizeNews(text) {
    const lowerText = text.toLowerCase();
    
    for (const [category, keywords] of Object.entries(this.categories)) {
      if (keywords.some(keyword => lowerText.includes(keyword))) {
        return category;
      }
    }
    
    return 'general';
  }

  extractSymbol(text) {
    // Look for stock symbols in text (3-5 uppercase letters)
    const symbolRegex = /\b[A-Z]{3,5}\b/g;
    const matches = text.match(symbolRegex);
    
    if (matches) {
      // Filter out common words that might match the pattern
      const commonWords = ['THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'CAN', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'DAY', 'GET', 'HAS', 'HIM', 'HIS', 'HOW', 'ITS', 'NEW', 'NOW', 'OLD', 'SEE', 'TWO', 'WHO', 'BOY', 'DID', 'HAS', 'LET', 'PUT', 'SAY', 'SHE', 'TOO', 'USE'];
      const filteredSymbols = matches.filter(symbol => !commonWords.includes(symbol));
      
      if (filteredSymbols.length > 0) {
        return filteredSymbols[0]; // Return first potential symbol
      }
    }
    
    return null;
  }

  extractKeywords(text) {
    // Simple keyword extraction
    const words = text.toLowerCase()
      .replace(/[^\w\s]/g, '')
      .split(/\s+/)
      .filter(word => word.length > 3);
    
    // Remove common stop words
    const stopWords = ['this', 'that', 'with', 'have', 'will', 'been', 'from', 'they', 'know', 'want', 'been', 'good', 'much', 'some', 'time', 'very', 'when', 'come', 'here', 'just', 'like', 'long', 'make', 'many', 'over', 'such', 'take', 'than', 'them', 'well', 'were'];
    
    const filteredWords = words.filter(word => !stopWords.includes(word));
    
    // Get word frequency
    const wordFreq = {};
    filteredWords.forEach(word => {
      wordFreq[word] = (wordFreq[word] || 0) + 1;
    });
    
    // Sort by frequency and return top keywords
    return Object.entries(wordFreq)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([word]) => word);
  }

  calculateReliabilityScore(sourceName) {
    const source = this.sources[sourceName];
    if (source) {
      return source.reliability;
    }
    
    // Default reliability for unknown sources
    return 0.5;
  }

  calculateImpactScore(article) {
    let score = 0.5; // Base score
    
    // Source reliability
    score += this.calculateReliabilityScore(article.source) * 0.3;
    
    // Category impact
    const categoryWeights = {
      'earnings': 0.9,
      'merger': 0.8,
      'regulatory': 0.7,
      'analyst': 0.6,
      'economic': 0.8,
      'technology': 0.6,
      'healthcare': 0.7,
      'energy': 0.6,
      'finance': 0.7,
      'retail': 0.5
    };
    
    score += (categoryWeights[article.category] || 0.5) * 0.3;
    
    // Symbol mention
    if (article.symbol) {
      score += 0.2;
    }
    
    // Title keywords
    const impactKeywords = ['earnings', 'merger', 'acquisition', 'bankruptcy', 'lawsuit', 'fda', 'approval'];
    const titleLower = article.title.toLowerCase();
    const keywordCount = impactKeywords.filter(keyword => titleLower.includes(keyword)).length;
    score += Math.min(keywordCount * 0.1, 0.2);
    
    return Math.min(score, 1.0);
  }

  calculateRelevanceScore(article, userSymbols = []) {
    let score = 0.5; // Base score
    
    // User symbol relevance
    if (article.symbol && userSymbols.includes(article.symbol)) {
      score += 0.3;
    }
    
    // Category relevance
    const categoryRelevance = {
      'earnings': 0.9,
      'analyst': 0.8,
      'merger': 0.7,
      'regulatory': 0.6,
      'economic': 0.7,
      'technology': 0.6,
      'healthcare': 0.6,
      'energy': 0.5,
      'finance': 0.6,
      'retail': 0.5
    };
    
    score += (categoryRelevance[article.category] || 0.5) * 0.2;
    
    // Recency bonus
    const hoursSincePublished = (Date.now() - new Date(article.published_at).getTime()) / (1000 * 60 * 60);
    if (hoursSincePublished < 24) {
      score += 0.1 * (1 - hoursSincePublished / 24);
    }
    
    return Math.min(score, 1.0);
  }

  async processAndStoreNews(newsItems, userSymbols = []) {
    const processedNews = [];
    
    for (const item of newsItems) {
      try {
        const processedItem = {
          title: item.title,
          content: item.content || '',
          source: item.source,
          author: item.author || 'Unknown',
          published_at: item.published_at,
          url: item.url,
          category: item.category,
          symbol: item.symbol,
          keywords: item.keywords || [],
          summary: item.summary || item.content?.substring(0, 200) + '...',
          impact_score: this.calculateImpactScore(item),
          relevance_score: this.calculateRelevanceScore(item, userSymbols),
          source_type: item.source_type || 'unknown'
        };
        
        processedNews.push(processedItem);
      } catch (error) {
        console.error('Error processing news item:', error);
      }
    }
    
    return processedNews;
  }
}

module.exports = NewsAnalyzer;