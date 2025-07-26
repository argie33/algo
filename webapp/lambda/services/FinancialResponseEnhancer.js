/**
 * Financial Response Enhancer
 * 
 * Enhances AI responses with:
 * - Financial expertise and accuracy
 * - Actionable investment insights
 * - Risk-appropriate recommendations
 * - Regulatory compliance
 * - Professional financial terminology
 */

class FinancialResponseEnhancer {
  constructor() {
    this.financialKeywords = new Map([
      // Investment Types
      ['stock', { category: 'equity', explanation: 'ownership share in a company' }],
      ['bond', { category: 'fixed_income', explanation: 'debt security that pays interest' }],
      ['etf', { category: 'fund', explanation: 'exchange-traded fund tracking an index' }],
      ['mutual fund', { category: 'fund', explanation: 'pooled investment vehicle' }],
      ['reit', { category: 'real_estate', explanation: 'real estate investment trust' }],
      
      // Financial Metrics
      ['pe ratio', { category: 'valuation', explanation: 'price-to-earnings ratio' }],
      ['dividend yield', { category: 'income', explanation: 'annual dividend as % of stock price' }],
      ['market cap', { category: 'size', explanation: 'total market value of company shares' }],
      ['beta', { category: 'risk', explanation: 'measure of stock volatility vs market' }],
      ['sharpe ratio', { category: 'performance', explanation: 'risk-adjusted return measure' }],
      
      // Risk Terms
      ['volatility', { category: 'risk', explanation: 'degree of price fluctuation' }],
      ['correlation', { category: 'risk', explanation: 'how assets move relative to each other' }],
      ['diversification', { category: 'risk', explanation: 'spreading investments to reduce risk' }],
      ['var', { category: 'risk', explanation: 'Value at Risk - potential loss estimate' }],
      
      // Market Terms
      ['bull market', { category: 'market', explanation: 'sustained period of rising prices' }],
      ['bear market', { category: 'market', explanation: 'sustained period of falling prices' }],
      ['market correction', { category: 'market', explanation: '10-20% decline from recent highs' }],
      ['recession', { category: 'economic', explanation: 'significant decline in economic activity' }]
    ]);

    this.complianceTemplates = {
      investment_advice: "This information is for educational purposes only and should not be considered personalized investment advice. Please consult with a qualified financial advisor before making investment decisions.",
      
      risk_warning: "All investments carry risk, including the potential loss of principal. Past performance does not guarantee future results.",
      
      diversification_reminder: "Diversification does not guarantee profits or protect against losses in declining markets.",
      
      tax_disclaimer: "Tax implications vary by individual circumstances. Consult a tax professional for personalized advice."
    };

    this.responsePatterns = {
      analysis: {
        structure: ['context', 'analysis', 'implications', 'recommendations', 'risks'],
        tone: 'analytical',
        evidenceRequired: true
      },
      
      recommendation: {
        structure: ['situation', 'recommendation', 'rationale', 'alternatives', 'disclaimer'],
        tone: 'advisory',
        evidenceRequired: true
      },
      
      educational: {
        structure: ['definition', 'explanation', 'examples', 'practical_application'],
        tone: 'educational',
        evidenceRequired: false
      },
      
      planning: {
        structure: ['current_state', 'goals', 'strategy', 'timeline', 'monitoring'],
        tone: 'planning',
        evidenceRequired: true
      }
    };
  }

  /**
   * Enhance AI response with financial expertise
   */
  enhanceFinancialResponse(aiResponse, context = {}) {
    try {
      const {
        portfolioContext,
        marketContext,
        userProfile = {},
        responseType = 'analysis'
      } = context;

      console.log(`💡 Enhancing AI response with financial expertise (type: ${responseType})`);

      let enhancedResponse = aiResponse;

      // 1. Add financial context and data
      enhancedResponse = this.addFinancialContext(enhancedResponse, portfolioContext, marketContext);

      // 2. Enhance with professional terminology
      enhancedResponse = this.enhanceTerminology(enhancedResponse);

      // 3. Add specific numerical insights
      enhancedResponse = this.addNumericalInsights(enhancedResponse, portfolioContext, marketContext);

      // 4. Structure response professionally
      enhancedResponse = this.structureResponse(enhancedResponse, responseType);

      // 5. Add actionable recommendations
      enhancedResponse = this.addActionableRecommendations(enhancedResponse, portfolioContext);

      // 6. Include risk considerations
      enhancedResponse = this.addRiskConsiderations(enhancedResponse, portfolioContext);

      // 7. Add compliance disclaimers
      enhancedResponse = this.addComplianceDisclaimers(enhancedResponse, responseType);

      // 8. Generate enhanced suggestions
      const enhancedSuggestions = this.generateEnhancedSuggestions(aiResponse, portfolioContext, marketContext);

      return {
        content: enhancedResponse,
        suggestions: enhancedSuggestions,
        enhanced: true,
        financialAnalysis: this.generateFinancialAnalysisSummary(portfolioContext, marketContext),
        metadata: {
          responseType,
          enhancementApplied: true,
          financialTermsExplained: this.extractFinancialTerms(enhancedResponse),
          complianceLevel: 'standard'
        }
      };

    } catch (error) {
      console.error('❌ Error enhancing financial response:', error);
      return {
        content: aiResponse,
        suggestions: [],
        enhanced: false,
        error: 'Enhancement failed'
      };
    }
  }

  /**
   * Add financial context and real data
   */
  addFinancialContext(response, portfolioContext, marketContext) {
    if (!portfolioContext || !marketContext) return response;

    let contextualResponse = response;

    // Add portfolio-specific insights
    if (portfolioContext.totalValue) {
      const valueInsight = `\n\n📊 **Your Portfolio Context:**\n` +
        `• Total Value: $${portfolioContext.totalValue.toLocaleString()}\n` +
        `• Total Return: ${portfolioContext.totalReturn?.toFixed(2) || 'N/A'}%\n` +
        `• Holdings: ${portfolioContext.holdingsCount} positions\n` +
        `• Top Sector: ${this.getTopSector(portfolioContext.sectorAllocation)}`;
      
      contextualResponse = contextualResponse + valueInsight;
    }

    // Add market context
    if (marketContext.sentiment) {
      const marketInsight = `\n\n📈 **Current Market Environment:**\n` +
        `• Market Sentiment: ${marketContext.sentiment.level}\n` +
        `• VIX Level: ${marketContext.sentiment.factors.volatility || 'N/A'}\n` +
        `• Fear & Greed Index: ${marketContext.sentiment.factors.fearGreedIndex || 'N/A'}\n` +
        `• Market Implication: ${marketContext.sentiment.description}`;
      
      contextualResponse = contextualResponse + marketInsight;
    }

    return contextualResponse;
  }

  /**
   * Enhance with professional financial terminology
   */
  enhanceTerminology(response) {
    let enhancedResponse = response;

    // Replace basic terms with professional equivalents
    const termReplacements = {
      'stock price went up': 'equity appreciated',
      'stock price went down': 'equity declined',
      'lost money': 'experienced unrealized losses',
      'made money': 'generated unrealized gains',
      'risky investment': 'high-volatility investment',
      'safe investment': 'conservative investment',
      'good stock': 'fundamentally strong equity',
      'bad stock': 'underperforming equity'
    };

    Object.entries(termReplacements).forEach(([basic, professional]) => {
      enhancedResponse = enhancedResponse.replace(new RegExp(basic, 'gi'), professional);
    });

    return enhancedResponse;
  }

  /**
   * Add specific numerical insights
   */
  addNumericalInsights(response, portfolioContext, marketContext) {
    if (!portfolioContext) return response;

    let insights = response;

    // Add specific portfolio metrics
    if (portfolioContext.riskMetrics) {
      const riskInsight = `\n\n🎯 **Portfolio Risk Analysis:**\n` +
        `• Portfolio Beta: ${portfolioContext.riskMetrics.beta?.toFixed(2) || 'N/A'}\n` +
        `• Estimated Volatility: ${portfolioContext.riskMetrics.volatility?.toFixed(1) || 'N/A'}%\n` +
        `• Sharpe Ratio: ${portfolioContext.riskMetrics.sharpeRatio?.toFixed(2) || 'N/A'}\n` +
        `• Risk Rating: ${portfolioContext.riskMetrics.riskRating}`;
      
      insights = insights + riskInsight;
    }

    // Add diversification insights
    if (portfolioContext.diversificationMetrics) {
      const divMetrics = portfolioContext.diversificationMetrics;
      const diversificationInsight = `\n\n🔄 **Diversification Analysis:**\n` +
        `• Diversification Score: ${divMetrics.score}/100\n` +
        `• Concentration Risk: ${divMetrics.concentrationRatio?.toFixed(1) || 'N/A'}%\n` +
        `• Effective Positions: ${divMetrics.effectiveStocks?.toFixed(1) || 'N/A'}\n` +
        `• Sector Count: ${divMetrics.sectorCount}\n` +
        `• Recommendation: ${divMetrics.recommendation}`;
      
      insights = insights + diversificationInsight;
    }

    return insights;
  }

  /**
   * Structure response professionally
   */
  structureResponse(response, responseType) {
    const pattern = this.responsePatterns[responseType] || this.responsePatterns.analysis;
    
    // Add professional structure markers
    let structuredResponse = response;

    // Add executive summary if response is long
    if (response.length > 500) {
      const summary = this.generateExecutiveSummary(response);
      structuredResponse = `**Executive Summary:**\n${summary}\n\n**Detailed Analysis:**\n${response}`;
    }

    return structuredResponse;
  }

  /**
   * Generate executive summary
   */
  generateExecutiveSummary(response) {
    // Extract key points (simplified)
    const sentences = response.split(/[.!?]+/).filter(s => s.trim().length > 20);
    const keyPoints = sentences.slice(0, 3);
    
    return keyPoints.map(point => `• ${point.trim()}`).join('\n');
  }

  /**
   * Add actionable recommendations
   */
  addActionableRecommendations(response, portfolioContext) {
    if (!portfolioContext) return response;

    const recommendations = [];

    // Portfolio-specific recommendations
    if (portfolioContext.diversificationMetrics?.score < 60) {
      recommendations.push('Consider adding positions in underrepresented sectors');
    }

    if (portfolioContext.riskMetrics?.beta > 1.3) {
      recommendations.push('Evaluate adding defensive positions to reduce portfolio beta');
    }

    if (portfolioContext.topHoldings?.some(h => h.weight > 20)) {
      recommendations.push('Consider reducing concentration in largest positions');
    }

    // General financial planning recommendations
    recommendations.push('Review and rebalance portfolio quarterly');
    recommendations.push('Consider tax-loss harvesting opportunities');

    if (recommendations.length > 0) {
      const actionSection = `\n\n🎯 **Actionable Recommendations:**\n` +
        recommendations.map((rec, i) => `${i + 1}. ${rec}`).join('\n');
      
      return response + actionSection;
    }

    return response;
  }

  /**
   * Add risk considerations
   */
  addRiskConsiderations(response, portfolioContext) {
    const riskFactors = [];

    if (portfolioContext?.riskMetrics?.volatility > 20) {
      riskFactors.push('High portfolio volatility increases short-term risk');
    }

    if (portfolioContext?.diversificationMetrics?.concentrationRatio > 25) {
      riskFactors.push('High concentration risk in individual positions');
    }

    // Market-wide risks
    riskFactors.push('Market conditions can change rapidly affecting all investments');
    riskFactors.push('Interest rate changes may impact different sectors differently');

    if (riskFactors.length > 0) {
      const riskSection = `\n\n⚠️ **Risk Considerations:**\n` +
        riskFactors.map(risk => `• ${risk}`).join('\n');
      
      return response + riskSection;
    }

    return response;
  }

  /**
   * Add compliance disclaimers
   */
  addComplianceDisclaimers(response, responseType) {
    const disclaimers = [];

    // Always include investment advice disclaimer
    disclaimers.push(this.complianceTemplates.investment_advice);

    // Add specific disclaimers based on content
    if (response.toLowerCase().includes('recommend') || response.toLowerCase().includes('should')) {
      disclaimers.push(this.complianceTemplates.risk_warning);
    }

    if (response.toLowerCase().includes('diversif')) {
      disclaimers.push(this.complianceTemplates.diversification_reminder);
    }

    if (response.toLowerCase().includes('tax')) {
      disclaimers.push(this.complianceTemplates.tax_disclaimer);
    }

    if (disclaimers.length > 0) {
      const disclaimerSection = `\n\n📋 **Important Disclaimers:**\n` +
        disclaimers.map(disclaimer => `• ${disclaimer}`).join('\n\n• ');
      
      return response + disclaimerSection;
    }

    return response;
  }

  /**
   * Generate enhanced suggestions
   */
  generateEnhancedSuggestions(response, portfolioContext, marketContext) {
    const suggestions = [];

    // Portfolio-specific suggestions
    if (portfolioContext?.totalValue) {
      suggestions.push('Analyze my portfolio risk-adjusted returns');
      suggestions.push('Show me sector allocation optimization opportunities');
      suggestions.push('Calculate my portfolio\'s correlation with major indices');
    }

    // Market-specific suggestions
    if (marketContext?.sentiment) {
      if (marketContext.sentiment.level.includes('Bearish')) {
        suggestions.push('Identify defensive investment opportunities');
        suggestions.push('Review my portfolio\'s downside protection');
      } else if (marketContext.sentiment.level.includes('Bullish')) {
        suggestions.push('Explore growth opportunities in current market');
        suggestions.push('Analyze momentum indicators for my holdings');
      }
    }

    // General financial planning suggestions
    suggestions.push('Review my investment strategy for current market conditions');
    suggestions.push('Analyze tax-loss harvesting opportunities');
    suggestions.push('Calculate optimal portfolio rebalancing frequency');
    suggestions.push('Evaluate my emergency fund adequacy');

    // Advanced analysis suggestions
    suggestions.push('Perform Monte Carlo analysis on my portfolio');
    suggestions.push('Analyze factor exposure of my investments');
    suggestions.push('Review my asset allocation vs target allocation');

    return suggestions.slice(0, 6); // Return top 6 suggestions
  }

  /**
   * Generate financial analysis summary
   */
  generateFinancialAnalysisSummary(portfolioContext, marketContext) {
    const summary = {
      portfolioHealth: 'Good',
      riskLevel: 'Moderate',
      diversificationStatus: 'Adequate',
      marketAlignment: 'Neutral',
      keyInsights: []
    };

    if (portfolioContext) {
      // Assess portfolio health
      if (portfolioContext.totalReturn > 10) {
        summary.portfolioHealth = 'Excellent';
        summary.keyInsights.push('Strong portfolio performance');
      } else if (portfolioContext.totalReturn < -10) {
        summary.portfolioHealth = 'Needs Attention';
        summary.keyInsights.push('Underperforming portfolio requires review');
      }

      // Assess risk level
      if (portfolioContext.riskMetrics?.riskRating) {
        summary.riskLevel = portfolioContext.riskMetrics.riskRating;
      }

      // Assess diversification
      if (portfolioContext.diversificationMetrics?.score > 80) {
        summary.diversificationStatus = 'Excellent';
      } else if (portfolioContext.diversificationMetrics?.score < 40) {
        summary.diversificationStatus = 'Poor';
        summary.keyInsights.push('Diversification improvement needed');
      }
    }

    if (marketContext?.sentiment) {
      summary.marketAlignment = marketContext.sentiment.level;
      if (marketContext.sentiment.level.includes('Bearish')) {
        summary.keyInsights.push('Defensive positioning may be warranted');
      }
    }

    return summary;
  }

  /**
   * Extract financial terms from response
   */
  extractFinancialTerms(response) {
    const foundTerms = [];
    
    for (const [term, info] of this.financialKeywords) {
      if (response.toLowerCase().includes(term)) {
        foundTerms.push({
          term,
          category: info.category,
          explanation: info.explanation
        });
      }
    }

    return foundTerms;
  }

  /**
   * Get top sector from allocation
   */
  getTopSector(sectorAllocation) {
    if (!sectorAllocation || Object.keys(sectorAllocation).length === 0) {
      return 'N/A';
    }

    const topSector = Object.entries(sectorAllocation)
      .sort(([,a], [,b]) => b.percentage - a.percentage)[0];

    return `${topSector[0]} (${topSector[1].percentage.toFixed(1)}%)`;
  }

  /**
   * Assess opportunity risk
   */
  assessOpportunityRisk(stock) {
    const pe = parseFloat(stock.pe_ratio || 0);
    const marketCap = parseInt(stock.market_cap || 0);
    const change = parseFloat(stock.change_percent || 0);

    if (marketCap > 50000000000 && pe < 20) return 'Low';
    if (marketCap > 10000000000 && pe < 25) return 'Moderate';
    if (change < -15 || pe > 30) return 'High';
    return 'Moderate';
  }
}

// Export singleton instance
module.exports = new FinancialResponseEnhancer();