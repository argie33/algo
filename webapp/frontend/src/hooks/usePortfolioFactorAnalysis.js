import { useState, useEffect, useMemo } from 'react';

/**
 * Custom hook for institutional-grade portfolio factor analysis
 * @param {Object} portfolioData - Portfolio data with holdings
 * @param {Object} analyticsData - Analytics data from API
 * @returns {Object} Factor analysis data and functions
 */
export function usePortfolioFactorAnalysis(portfolioData, analyticsData) {
  const [factorLoadings, setFactorLoadings] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // Calculate factor exposures from holdings
  const factorExposures = useMemo(() => {
    if (!portfolioData?.holdings || !Array.isArray(portfolioData.holdings)) {
      return {
        quality: 0,
        growth: 0,
        value: 0,
        momentum: 0,
        size: 0,
        volatility: 0,
        dividend: 0,
        profitability: 0
      };
    }

    const holdings = portfolioData.holdings;
    const totalValue = holdings.reduce((sum, h) => sum + (h.marketValue || 0), 0);
    
    const exposures = {
      quality: 0,
      growth: 0,
      value: 0,
      momentum: 0,
      size: 0,
      volatility: 0,
      dividend: 0,
      profitability: 0
    };

    holdings.forEach(holding => {
      const weight = totalValue > 0 ? (holding.marketValue || 0) / totalValue : 0;
      const sector = holding.sector || 'Other';
      
      // Quality factor (based on sector and financial health)
      if (['Technology', 'Healthcare', 'Consumer Staples'].includes(sector)) {
        exposures.quality += weight * 0.8;
      } else if (['Utilities', 'Telecommunications'].includes(sector)) {
        exposures.quality += weight * 0.6;
      } else {
        exposures.quality += weight * 0.4;
      }
      
      // Growth factor
      if (['Technology', 'Consumer Discretionary'].includes(sector)) {
        exposures.growth += weight * 0.9;
      } else if (['Healthcare', 'Industrials'].includes(sector)) {
        exposures.growth += weight * 0.6;
      } else {
        exposures.growth += weight * 0.3;
      }
      
      // Value factor
      if (['Financials', 'Energy', 'Materials'].includes(sector)) {
        exposures.value += weight * 0.8;
      } else if (['Utilities', 'Real Estate'].includes(sector)) {
        exposures.value += weight * 0.6;
      } else {
        exposures.value += weight * 0.2;
      }
      
      // Momentum factor (based on recent performance)
      const recentReturn = holding.gainLossPercent || 0;
      if (recentReturn > 10) {
        exposures.momentum += weight * 0.8;
      } else if (recentReturn > 0) {
        exposures.momentum += weight * 0.5;
      } else {
        exposures.momentum += weight * 0.2;
      }
      
      // Size factor (based on market cap)
      const marketCap = holding.marketCap || 'large';
      if (marketCap === 'small') {
        exposures.size += weight * 0.9;
      } else if (marketCap === 'mid') {
        exposures.size += weight * 0.6;
      } else {
        exposures.size += weight * 0.3;
      }
      
      // Volatility factor (based on sector volatility)
      if (['Technology', 'Biotechnology'].includes(sector)) {
        exposures.volatility += weight * 0.9;
      } else if (['Energy', 'Materials'].includes(sector)) {
        exposures.volatility += weight * 0.7;
      } else {
        exposures.volatility += weight * 0.4;
      }
      
      // Dividend factor
      if (['Utilities', 'Real Estate', 'Consumer Staples'].includes(sector)) {
        exposures.dividend += weight * 0.8;
      } else if (['Financials', 'Telecommunications'].includes(sector)) {
        exposures.dividend += weight * 0.6;
      } else {
        exposures.dividend += weight * 0.2;
      }
      
      // Profitability factor
      if (['Technology', 'Healthcare', 'Consumer Staples'].includes(sector)) {
        exposures.profitability += weight * 0.8;
      } else if (['Financials', 'Industrials'].includes(sector)) {
        exposures.profitability += weight * 0.6;
      } else {
        exposures.profitability += weight * 0.4;
      }
    });

    return exposures;
  }, [portfolioData]);

  // Style analysis (Growth vs Value, Large vs Small Cap)
  const styleAnalysis = useMemo(() => {
    if (!portfolioData?.holdings || !Array.isArray(portfolioData.holdings)) {
      return {
        growthExposure: 0,
        valueExposure: 0,
        largeCapExposure: 0,
        midCapExposure: 0,
        smallCapExposure: 0,
        styleBox: {}
      };
    }

    const holdings = portfolioData.holdings;
    const totalValue = holdings.reduce((sum, h) => sum + (h.marketValue || 0), 0);
    
    let growthExposure = 0;
    let valueExposure = 0;
    let largeCapExposure = 0;
    let midCapExposure = 0;
    let smallCapExposure = 0;

    holdings.forEach(holding => {
      const weight = totalValue > 0 ? (holding.marketValue || 0) / totalValue : 0;
      const sector = holding.sector || 'Other';
      const marketCap = holding.marketCap || 'large';
      
      // Growth vs Value
      if (['Technology', 'Consumer Discretionary', 'Communication Services'].includes(sector)) {
        growthExposure += weight;
      } else if (['Financials', 'Energy', 'Materials', 'Utilities'].includes(sector)) {
        valueExposure += weight;
      } else {
        // Neutral sectors
        growthExposure += weight * 0.5;
        valueExposure += weight * 0.5;
      }
      
      // Market Cap
      if (marketCap === 'large') {
        largeCapExposure += weight;
      } else if (marketCap === 'mid') {
        midCapExposure += weight;
      } else {
        smallCapExposure += weight;
      }
    });

    return {
      growthExposure,
      valueExposure,
      largeCapExposure,
      midCapExposure,
      smallCapExposure,
      styleBox: {
        growthLarge: growthExposure * largeCapExposure,
        growthMid: growthExposure * midCapExposure,
        growthSmall: growthExposure * smallCapExposure,
        valueLarge: valueExposure * largeCapExposure,
        valueMid: valueExposure * midCapExposure,
        valueSmall: valueExposure * smallCapExposure
      }
    };
  }, [portfolioData]);

  // Risk attribution by factor
  const riskAttribution = useMemo(() => {
    if (!portfolioData?.holdings || !Array.isArray(portfolioData.holdings)) {
      return {
        sectorRiskContribution: {},
        totalPortfolioRisk: 0,
        diversificationRatio: 0,
        effectivePositions: 0
      };
    }

    const holdings = portfolioData.holdings;
    const totalValue = holdings.reduce((sum, h) => sum + (h.marketValue || 0), 0);
    const riskContribution = {};

    holdings.forEach(holding => {
      const weight = totalValue > 0 ? (holding.marketValue || 0) / totalValue : 0;
      const volatility = 0.2; // Default 20% volatility
      const contribution = weight * weight * volatility * volatility;
      
      const sector = holding.sector || 'Other';
      riskContribution[sector] = (riskContribution[sector] || 0) + contribution;
    });

    const totalRisk = Object.values(riskContribution).reduce((sum, risk) => sum + risk, 0);
    
    // Normalize to percentages
    Object.keys(riskContribution).forEach(sector => {
      riskContribution[sector] = totalRisk > 0 ? (riskContribution[sector] / totalRisk) * 100 : 0;
    });

    // Calculate diversification metrics
    let sumSquaredWeights = 0;
    let weightedAvgRisk = 0;

    holdings.forEach(holding => {
      const weight = totalValue > 0 ? (holding.marketValue || 0) / totalValue : 0;
      const volatility = 0.2;
      
      weightedAvgRisk += weight * volatility;
      sumSquaredWeights += weight * weight;
    });

    const effectivePositions = sumSquaredWeights > 0 ? 1 / sumSquaredWeights : 0;
    const avgCorrelation = 0.3;
    const portfolioRisk = Math.sqrt(sumSquaredWeights + (1 - sumSquaredWeights) * avgCorrelation) * weightedAvgRisk;
    const diversificationRatio = portfolioRisk > 0 ? weightedAvgRisk / portfolioRisk : 0;

    return {
      sectorRiskContribution: riskContribution,
      totalPortfolioRisk: Math.sqrt(totalRisk) * 100,
      diversificationRatio,
      effectivePositions,
      portfolioRisk: portfolioRisk * 100,
      weightedAvgRisk: weightedAvgRisk * 100
    };
  }, [portfolioData]);

  // Active exposures vs benchmark
  const activeExposures = useMemo(() => {
    // Benchmark factor exposures (e.g., S&P 500)
    const benchmarkExposures = {
      quality: 0.6,
      growth: 0.5,
      value: 0.5,
      momentum: 0.5,
      size: 0.3,
      volatility: 0.4,
      dividend: 0.4,
      profitability: 0.6
    };

    const activeExposures = {};
    
    Object.keys(factorExposures).forEach(factor => {
      const portfolioExposure = factorExposures[factor] || 0;
      const benchmarkExposure = benchmarkExposures[factor] || 0;
      activeExposures[factor] = portfolioExposure - benchmarkExposure;
    });

    return activeExposures;
  }, [factorExposures]);

  // Comprehensive factor analysis
  const factorAnalysis = useMemo(() => {
    return {
      factorExposures,
      styleAnalysis,
      riskAttribution,
      activeExposures,
      analysisDate: new Date().toISOString()
    };
  }, [factorExposures, styleAnalysis, riskAttribution, activeExposures]);

  return {
    factorAnalysis,
    factorExposures,
    styleAnalysis,
    riskAttribution,
    activeExposures,
    factorLoadings,
    isLoading,
    error,
    setFactorLoadings,
    setIsLoading,
    setError
  };
}

export default usePortfolioFactorAnalysis;