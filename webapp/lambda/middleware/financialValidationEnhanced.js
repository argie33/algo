/**
 * Enhanced Financial Validation Middleware
 * Provides comprehensive validation for financial trading operations
 * with advanced security checks and business rule enforcement
 */

const logger = require('../utils/logger');
const { financialValidator } = require('./advancedSecurityEnhancements');

/**
 * Enhanced financial parameter validation with business rules
 */
class EnhancedFinancialValidator {
    constructor() {
        // Market hours (US Eastern Time)
        this.marketHours = {
            preMarketStart: 4, // 4:00 AM ET
            marketOpen: 9.5,   // 9:30 AM ET
            marketClose: 16,   // 4:00 PM ET
            afterHoursEnd: 20  // 8:00 PM ET
        };
        
        // Trading limits for risk management
        this.tradingLimits = {
            maxPositionSize: 1000000,      // $1M max position
            maxOrderValue: 500000,         // $500k max single order
            maxDailyVolume: 2000000,       // $2M max daily volume
            minOrderValue: 100,            // $100 min order
            maxLeverage: 4.0,              // 4:1 max leverage
            maxSymbolsPerPortfolio: 50     // Max 50 symbols
        };
        
        // Volatility thresholds
        this.volatilityLimits = {
            maxVolatility: 0.50,           // 50% max annualized volatility
            warningVolatility: 0.30        // 30% warning threshold
        };
    }

    /**
     * Validate comprehensive trading order with business rules
     */
    validateTradingOrderEnhanced(order) {
        const errors = [];
        const warnings = [];
        
        try {
            // Basic validation first
            const basicValidation = financialValidator.validateTradingOrder(order);
            
            // Enhanced business rule validation
            if (order.quantity && order.price) {
                const orderValue = order.quantity * order.price;
                
                // Order value limits
                if (orderValue > this.tradingLimits.maxOrderValue) {
                    errors.push(`Order value $${orderValue.toLocaleString()} exceeds maximum allowed $${this.tradingLimits.maxOrderValue.toLocaleString()}`);
                }
                
                if (orderValue < this.tradingLimits.minOrderValue) {
                    errors.push(`Order value $${orderValue.toLocaleString()} below minimum required $${this.tradingLimits.minOrderValue.toLocaleString()}`);
                }
                
                // Large order warning
                if (orderValue > this.tradingLimits.maxOrderValue * 0.5) {
                    warnings.push(`Large order detected: $${orderValue.toLocaleString()}`);
                }
            }
            
            // Market hours validation
            if (order.orderType === 'market') {
                const now = new Date();
                const currentHour = now.getHours() + (now.getMinutes() / 60);
                
                if (currentHour < this.marketHours.preMarketStart || 
                    currentHour > this.marketHours.afterHoursEnd) {
                    warnings.push('Market order placed outside extended trading hours');
                }
                
                if (currentHour < this.marketHours.marketOpen || 
                    currentHour > this.marketHours.marketClose) {
                    warnings.push('Market order placed outside regular market hours');
                }
            }
            
            // Symbol validation enhancements
            if (order.symbol) {
                // Check for high-risk symbols
                const highRiskPatterns = [/^[A-Z]{1,2}[0-9]/]; // Leveraged ETFs pattern
                if (highRiskPatterns.some(pattern => pattern.test(order.symbol))) {
                    warnings.push(`High-risk instrument detected: ${order.symbol}`);
                }
                
                // Cryptocurrency detection
                if (order.symbol.includes('USD') || order.symbol.includes('BTC') || 
                    order.symbol.includes('ETH') || order.symbol.length > 5) {
                    warnings.push('Cryptocurrency or international symbol detected');
                }
            }
            
            // Risk validation
            if (order.stopLoss && order.price) {
                const riskPercent = Math.abs((order.price - order.stopLoss) / order.price);
                if (riskPercent > 0.20) { // 20% risk
                    warnings.push(`High risk per trade: ${(riskPercent * 100).toFixed(1)}%`);
                }
            }
            
            const result = {
                valid: errors.length === 0,
                errors,
                warnings,
                orderValue: order.quantity && order.price ? order.quantity * order.price : null,
                riskLevel: this.calculateRiskLevel(order),
                validatedOrder: errors.length === 0 ? basicValidation : order
            };
            
            if (warnings.length > 0 || errors.length > 0) {
                logger.warn('Enhanced trading order validation issues detected', {
                    symbol: order.symbol,
                    orderType: order.orderType,
                    errors,
                    warnings,
                    riskLevel: result.riskLevel
                });
            }
            
            return result;
            
        } catch (error) {
            logger.error('Enhanced trading order validation failed', {
                error,
                order: { ...order, apiKey: '***', apiSecret: '***' }
            });
            
            return {
                valid: false,
                errors: [`Validation error: ${error.message}`],
                warnings: [],
                riskLevel: 'UNKNOWN'
            };
        }
    }

    /**
     * Calculate risk level based on order parameters
     */
    calculateRiskLevel(order) {
        let riskScore = 0;
        
        // Order size risk
        if (order.quantity && order.price) {
            const orderValue = order.quantity * order.price;
            if (orderValue > 100000) riskScore += 2;
            else if (orderValue > 50000) riskScore += 1;
        }
        
        // Order type risk
        if (order.orderType === 'market') riskScore += 1;
        if (order.orderType === 'stop') riskScore += 2;
        
        // Leverage risk
        if (order.leverage && order.leverage > 2) riskScore += 3;
        
        // Time risk (after hours)
        const now = new Date();
        const currentHour = now.getHours() + (now.getMinutes() / 60);
        if (currentHour < this.marketHours.marketOpen || 
            currentHour > this.marketHours.marketClose) {
            riskScore += 1;
        }
        
        if (riskScore >= 5) return 'HIGH';
        if (riskScore >= 3) return 'MEDIUM';
        if (riskScore >= 1) return 'LOW';
        return 'MINIMAL';
    }

    /**
     * Validate portfolio composition with diversification rules
     */
    validatePortfolioComposition(holdings) {
        const warnings = [];
        const errors = [];
        
        try {
            const totalValue = holdings.reduce((sum, holding) => 
                sum + (holding.quantity * holding.currentPrice), 0);
            
            // Concentration risk analysis
            holdings.forEach(holding => {
                const positionValue = holding.quantity * holding.currentPrice;
                const concentration = positionValue / totalValue;
                
                if (concentration > 0.25) { // 25% concentration limit
                    warnings.push(`High concentration in ${holding.symbol}: ${(concentration * 100).toFixed(1)}%`);
                }
                
                if (positionValue > this.tradingLimits.maxPositionSize) {
                    errors.push(`Position size in ${holding.symbol} exceeds limit: $${positionValue.toLocaleString()}`);
                }
            });
            
            // Diversification analysis
            const numPositions = holdings.length;
            if (numPositions < 5) {
                warnings.push(`Low diversification: only ${numPositions} positions`);
            }
            
            if (numPositions > this.tradingLimits.maxSymbolsPerPortfolio) {
                warnings.push(`Over-diversification: ${numPositions} positions (max recommended: ${this.tradingLimits.maxSymbolsPerPortfolio})`);
            }
            
            // Sector concentration (simplified)
            const techSymbols = holdings.filter(h => 
                ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META'].includes(h.symbol));
            const techConcentration = techSymbols.reduce((sum, h) => 
                sum + (h.quantity * h.currentPrice), 0) / totalValue;
            
            if (techConcentration > 0.50) {
                warnings.push(`High technology sector concentration: ${(techConcentration * 100).toFixed(1)}%`);
            }
            
            return {
                valid: errors.length === 0,
                errors,
                warnings,
                totalValue,
                numPositions,
                riskLevel: this.calculatePortfolioRisk(holdings, totalValue),
                recommendations: this.generatePortfolioRecommendations(holdings, totalValue)
            };
            
        } catch (error) {
            logger.error('Portfolio composition validation failed', { error, holdingsCount: holdings.length });
            return {
                valid: false,
                errors: [`Portfolio validation error: ${error.message}`],
                warnings: [],
                riskLevel: 'UNKNOWN'
            };
        }
    }

    /**
     * Calculate overall portfolio risk
     */
    calculatePortfolioRisk(holdings, totalValue) {
        let riskScore = 0;
        
        // Concentration risk
        const maxPosition = Math.max(...holdings.map(h => 
            (h.quantity * h.currentPrice) / totalValue));
        if (maxPosition > 0.30) riskScore += 3;
        else if (maxPosition > 0.20) riskScore += 2;
        else if (maxPosition > 0.15) riskScore += 1;
        
        // Diversification risk
        if (holdings.length < 5) riskScore += 2;
        else if (holdings.length < 10) riskScore += 1;
        
        // Total value risk
        if (totalValue > 1000000) riskScore += 1; // Higher stakes = higher risk
        
        if (riskScore >= 5) return 'HIGH';
        if (riskScore >= 3) return 'MEDIUM';
        if (riskScore >= 1) return 'LOW';
        return 'MINIMAL';
    }

    /**
     * Generate portfolio improvement recommendations
     */
    generatePortfolioRecommendations(holdings, totalValue) {
        const recommendations = [];
        
        // Diversification recommendations
        if (holdings.length < 8) {
            recommendations.push({
                type: 'diversification',
                priority: 'medium',
                message: 'Consider adding more positions to improve diversification'
            });
        }
        
        // Rebalancing recommendations
        holdings.forEach(holding => {
            const weight = (holding.quantity * holding.currentPrice) / totalValue;
            if (weight > 0.20) {
                recommendations.push({
                    type: 'rebalancing',
                    priority: 'high',
                    message: `Consider reducing position in ${holding.symbol} (currently ${(weight * 100).toFixed(1)}% of portfolio)`
                });
            }
        });
        
        // Risk management recommendations
        if (totalValue > 500000) {
            recommendations.push({
                type: 'risk_management',
                priority: 'medium',
                message: 'Consider implementing systematic risk management with stop losses'
            });
        }
        
        return recommendations;
    }
}

/**
 * Enhanced financial validation middleware
 */
const createEnhancedFinancialValidation = (options = {}) => {
    const validator = new EnhancedFinancialValidator();
    const {
        validateOrders = true,
        validatePortfolio = false,
        strictMode = false
    } = options;
    
    return async (req, res, next) => {
        try {
            const validationResults = {};
            
            // Validate trading orders
            if (validateOrders && req.body && 
                (req.body.symbol || req.body.orderType || req.body.quantity)) {
                
                const orderValidation = validator.validateTradingOrderEnhanced(req.body);
                validationResults.order = orderValidation;
                
                if (!orderValidation.valid) {
                    return res.status(400).json({
                        success: false,
                        error: 'Enhanced order validation failed',
                        details: orderValidation.errors,
                        warnings: orderValidation.warnings,
                        code: 'ENHANCED_ORDER_VALIDATION_FAILED'
                    });
                }
                
                // Strict mode blocks high-risk orders
                if (strictMode && orderValidation.riskLevel === 'HIGH') {
                    return res.status(403).json({
                        success: false,
                        error: 'High-risk order blocked in strict mode',
                        riskLevel: orderValidation.riskLevel,
                        warnings: orderValidation.warnings,
                        code: 'HIGH_RISK_ORDER_BLOCKED'
                    });
                }
            }
            
            // Validate portfolio composition
            if (validatePortfolio && req.body && req.body.holdings) {
                const portfolioValidation = validator.validatePortfolioComposition(req.body.holdings);
                validationResults.portfolio = portfolioValidation;
                
                if (!portfolioValidation.valid) {
                    return res.status(400).json({
                        success: false,
                        error: 'Portfolio composition validation failed',
                        details: portfolioValidation.errors,
                        warnings: portfolioValidation.warnings,
                        code: 'PORTFOLIO_VALIDATION_FAILED'
                    });
                }
            }
            
            // Add validation results to request for downstream use
            req.enhancedValidation = validationResults;
            
            next();
            
        } catch (error) {
            logger.error('Enhanced financial validation middleware error', {
                error,
                path: req.path,
                method: req.method
            });
            
            return res.status(500).json({
                success: false,
                error: 'Financial validation system error',
                code: 'VALIDATION_SYSTEM_ERROR'
            });
        }
    };
};

module.exports = {
    EnhancedFinancialValidator,
    createEnhancedFinancialValidation
};