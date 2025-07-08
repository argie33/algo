const express = require('express');
const router = express.Router();
const { query } = require('../utils/database');

/**
 * GET /sectors/analysis
 * Comprehensive sector analysis using live data from company_profile, price tables, and technical tables
 */
router.get('/analysis', async (req, res) => {
    try {
        console.log('📊 Fetching comprehensive sector analysis from live tables...');
        
        const { timeframe = 'daily' } = req.query;
        
        // Validate timeframe
        const validTimeframes = ['daily', 'weekly', 'monthly'];
        if (!validTimeframes.includes(timeframe)) {
            return res.status(400).json({
                success: false,
                error: 'Invalid timeframe. Must be daily, weekly, or monthly.'
            });
        }
        
        // Get sector analysis with current prices, momentum, and performance metrics
        const sectorAnalysisQuery = `
            WITH latest_prices AS (
                SELECT DISTINCT ON (symbol) 
                    symbol,
                    date,
                    close as current_price,
                    volume,
                    (close - LAG(close, 1) OVER (PARTITION BY symbol ORDER BY date)) / LAG(close, 1) OVER (PARTITION BY symbol ORDER BY date) * 100 as daily_change_pct,
                    (close - LAG(close, 5) OVER (PARTITION BY symbol ORDER BY date)) / LAG(close, 5) OVER (PARTITION BY symbol ORDER BY date) * 100 as weekly_change_pct,
                    (close - LAG(close, 22) OVER (PARTITION BY symbol ORDER BY date)) / LAG(close, 22) OVER (PARTITION BY symbol ORDER BY date) * 100 as monthly_change_pct
                FROM price_${timeframe}
                WHERE date >= CURRENT_DATE - INTERVAL '6 months'
                ORDER BY symbol, date DESC
            ),
            latest_technicals AS (
                SELECT DISTINCT ON (symbol)
                    symbol,
                    date,
                    rsi,
                    momentum,
                    macd,
                    macd_signal,
                    volume as tech_volume,
                    sma_20,
                    sma_50,
                    CASE 
                        WHEN close > sma_20 AND sma_20 > sma_50 THEN 'bullish'
                        WHEN close < sma_20 AND sma_20 < sma_50 THEN 'bearish'
                        ELSE 'neutral'
                    END as trend
                FROM technical_data_${timeframe}
                WHERE date >= CURRENT_DATE - INTERVAL '3 months'
                ORDER BY symbol, date DESC
            ),
            momentum_data AS (
                SELECT DISTINCT ON (symbol)
                    symbol,
                    jt_momentum_12_1,
                    momentum_3m,
                    momentum_6m,
                    risk_adjusted_momentum,
                    momentum_strength,
                    volume_weighted_momentum
                FROM momentum_metrics
                WHERE date >= CURRENT_DATE - INTERVAL '1 month'
                ORDER BY symbol, date DESC
            ),
            sector_summary AS (
                SELECT 
                    cp.sector,
                    cp.industry,
                    COUNT(*) as stock_count,
                    COUNT(lp.symbol) as priced_stocks,
                    AVG(lp.current_price) as avg_price,
                    AVG(lp.daily_change_pct) as avg_daily_change,
                    AVG(lp.weekly_change_pct) as avg_weekly_change,
                    AVG(lp.monthly_change_pct) as avg_monthly_change,
                    AVG(lp.volume) as avg_volume,
                    
                    -- Technical indicators
                    AVG(lt.rsi) as avg_rsi,
                    AVG(lt.momentum) as avg_momentum,
                    AVG(lt.macd) as avg_macd,
                    
                    -- Momentum metrics
                    AVG(md.jt_momentum_12_1) as avg_jt_momentum,
                    AVG(md.momentum_3m) as avg_momentum_3m,
                    AVG(md.momentum_6m) as avg_momentum_6m,
                    AVG(md.risk_adjusted_momentum) as avg_risk_adj_momentum,
                    AVG(md.momentum_strength) as avg_momentum_strength,
                    AVG(md.volume_weighted_momentum) as avg_volume_momentum,
                    
                    -- Trend analysis
                    COUNT(CASE WHEN lt.trend = 'bullish' THEN 1 END) as bullish_stocks,
                    COUNT(CASE WHEN lt.trend = 'bearish' THEN 1 END) as bearish_stocks,
                    COUNT(CASE WHEN lt.trend = 'neutral' THEN 1 END) as neutral_stocks,
                    
                    -- Market cap estimates (based on volume as proxy)
                    SUM(lp.current_price * lp.volume) as total_dollar_volume,
                    
                    -- Performance ranking
                    RANK() OVER (ORDER BY AVG(lp.monthly_change_pct) DESC) as performance_rank
                    
                FROM company_profile cp
                LEFT JOIN latest_prices lp ON cp.ticker = lp.symbol
                LEFT JOIN latest_technicals lt ON cp.ticker = lt.symbol  
                LEFT JOIN momentum_data md ON cp.ticker = md.symbol
                WHERE cp.sector IS NOT NULL 
                    AND cp.sector != ''
                    AND cp.industry IS NOT NULL
                    AND cp.industry != ''
                GROUP BY cp.sector, cp.industry
                HAVING COUNT(lp.symbol) >= 3  -- Only include sectors/industries with at least 3 priced stocks
            ),
            top_performers AS (
                SELECT 
                    cp.sector,
                    cp.ticker,
                    cp.short_name,
                    lp.current_price,
                    lp.monthly_change_pct,
                    lt.momentum as current_momentum,
                    md.jt_momentum_12_1,
                    ROW_NUMBER() OVER (PARTITION BY cp.sector ORDER BY lp.monthly_change_pct DESC) as sector_rank
                FROM company_profile cp
                INNER JOIN latest_prices lp ON cp.ticker = lp.symbol
                LEFT JOIN latest_technicals lt ON cp.ticker = lt.symbol
                LEFT JOIN momentum_data md ON cp.ticker = md.symbol
                WHERE cp.sector IS NOT NULL AND lp.monthly_change_pct IS NOT NULL
            ),
            bottom_performers AS (
                SELECT 
                    cp.sector,
                    cp.ticker,
                    cp.short_name,
                    lp.current_price,
                    lp.monthly_change_pct,
                    lt.momentum as current_momentum,
                    md.jt_momentum_12_1,
                    ROW_NUMBER() OVER (PARTITION BY cp.sector ORDER BY lp.monthly_change_pct ASC) as sector_rank
                FROM company_profile cp
                INNER JOIN latest_prices lp ON cp.ticker = lp.symbol
                LEFT JOIN latest_technicals lt ON cp.ticker = lt.symbol
                LEFT JOIN momentum_data md ON cp.ticker = md.symbol
                WHERE cp.sector IS NOT NULL AND lp.monthly_change_pct IS NOT NULL
            )
            
            SELECT 
                ss.*,
                
                -- Top 3 performers in each sector
                JSON_AGG(
                    CASE WHEN tp.sector_rank <= 3 THEN 
                        JSON_BUILD_OBJECT(
                            'symbol', tp.ticker,
                            'name', tp.short_name,
                            'price', tp.current_price,
                            'monthly_return', tp.monthly_change_pct,
                            'momentum', tp.current_momentum,
                            'jt_momentum', tp.jt_momentum_12_1
                        )
                    END
                ) FILTER (WHERE tp.sector_rank <= 3) as top_performers,
                
                -- Bottom 3 performers in each sector
                JSON_AGG(
                    CASE WHEN bp.sector_rank <= 3 THEN 
                        JSON_BUILD_OBJECT(
                            'symbol', bp.ticker,
                            'name', bp.short_name,
                            'price', bp.current_price,
                            'monthly_return', bp.monthly_change_pct,
                            'momentum', bp.current_momentum,
                            'jt_momentum', bp.jt_momentum_12_1
                        )
                    END
                ) FILTER (WHERE bp.sector_rank <= 3) as bottom_performers
                
            FROM sector_summary ss
            LEFT JOIN top_performers tp ON ss.sector = tp.sector
            LEFT JOIN bottom_performers bp ON ss.sector = bp.sector
            GROUP BY 
                ss.sector, ss.industry, ss.stock_count, ss.priced_stocks, 
                ss.avg_price, ss.avg_daily_change, ss.avg_weekly_change, ss.avg_monthly_change,
                ss.avg_volume, ss.avg_rsi, ss.avg_momentum, ss.avg_macd,
                ss.avg_jt_momentum, ss.avg_momentum_3m, ss.avg_momentum_6m, 
                ss.avg_risk_adj_momentum, ss.avg_momentum_strength, ss.avg_volume_momentum,
                ss.bullish_stocks, ss.bearish_stocks, ss.neutral_stocks,
                ss.total_dollar_volume, ss.performance_rank
            ORDER BY ss.avg_monthly_change DESC
        `;
        
        const sectorData = await query(sectorAnalysisQuery);
        
        console.log(`✅ Found ${sectorData.rows.length} sectors with live data`);
        
        // Calculate summary statistics
        const totalSectors = sectorData.rows.length;
        const totalStocks = sectorData.rows.reduce((sum, row) => sum + parseInt(row.priced_stocks || 0), 0);
        const avgMarketReturn = sectorData.rows.reduce((sum, row) => sum + parseFloat(row.avg_monthly_change || 0), 0) / totalSectors;
        
        // Identify sector trends
        const bullishSectors = sectorData.rows.filter(row => parseFloat(row.avg_monthly_change || 0) > 0).length;
        const bearishSectors = sectorData.rows.filter(row => parseFloat(row.avg_monthly_change || 0) < 0).length;
        
        const response = {
            success: true,
            data: {
                timeframe,
                summary: {
                    total_sectors: totalSectors,
                    total_stocks_analyzed: totalStocks,
                    avg_market_return: avgMarketReturn.toFixed(2),
                    bullish_sectors: bullishSectors,
                    bearish_sectors: bearishSectors,
                    neutral_sectors: totalSectors - bullishSectors - bearishSectors
                },
                sectors: sectorData.rows.map(row => ({
                    sector: row.sector,
                    industry: row.industry,
                    metrics: {
                        stock_count: parseInt(row.stock_count),
                        priced_stocks: parseInt(row.priced_stocks),
                        avg_price: parseFloat(row.avg_price || 0).toFixed(2),
                        performance: {
                            daily_change: parseFloat(row.avg_daily_change || 0).toFixed(2),
                            weekly_change: parseFloat(row.avg_weekly_change || 0).toFixed(2),
                            monthly_change: parseFloat(row.avg_monthly_change || 0).toFixed(2),
                            performance_rank: parseInt(row.performance_rank)
                        },
                        technicals: {
                            avg_rsi: parseFloat(row.avg_rsi || 0).toFixed(2),
                            avg_momentum: parseFloat(row.avg_momentum || 0).toFixed(2),
                            avg_macd: parseFloat(row.avg_macd || 0).toFixed(4),
                            trend_distribution: {
                                bullish: parseInt(row.bullish_stocks || 0),
                                bearish: parseInt(row.bearish_stocks || 0),
                                neutral: parseInt(row.neutral_stocks || 0)
                            }
                        },
                        momentum: {
                            jt_momentum_12_1: parseFloat(row.avg_jt_momentum || 0).toFixed(4),
                            momentum_3m: parseFloat(row.avg_momentum_3m || 0).toFixed(4),
                            momentum_6m: parseFloat(row.avg_momentum_6m || 0).toFixed(4),
                            risk_adjusted: parseFloat(row.avg_risk_adj_momentum || 0).toFixed(4),
                            momentum_strength: parseFloat(row.avg_momentum_strength || 0).toFixed(2),
                            volume_weighted: parseFloat(row.avg_volume_momentum || 0).toFixed(4)
                        },
                        volume: {
                            avg_volume: parseInt(row.avg_volume || 0),
                            total_dollar_volume: parseFloat(row.total_dollar_volume || 0)
                        }
                    },
                    top_performers: row.top_performers || [],
                    bottom_performers: row.bottom_performers || []
                }))
            },
            timestamp: new Date().toISOString()
        };
        
        res.json(response);
        
    } catch (error) {
        console.error('❌ Error in sector analysis:', error);
        res.status(500).json({
            success: false,
            error: error.message || 'Failed to fetch sector analysis'
        });
    }
});

/**
 * GET /sectors/list
 * Get list of all available sectors and industries
 */
router.get('/list', async (req, res) => {
    try {
        console.log('📋 Fetching sector and industry list...');
        
        const sectorsQuery = `
            SELECT 
                sector,
                industry,
                COUNT(*) as company_count,
                COUNT(CASE WHEN ticker IN (
                    SELECT DISTINCT symbol FROM price_daily 
                    WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                ) THEN 1 END) as active_companies
            FROM company_profile 
            WHERE sector IS NOT NULL 
                AND sector != ''
                AND industry IS NOT NULL 
                AND industry != ''
            GROUP BY sector, industry
            ORDER BY sector, industry
        `;
        
        const result = await query(sectorsQuery);
        
        // Group by sector
        const sectorMap = {};
        result.rows.forEach(row => {
            if (!sectorMap[row.sector]) {
                sectorMap[row.sector] = {
                    sector: row.sector,
                    industries: [],
                    total_companies: 0,
                    active_companies: 0
                };
            }
            
            sectorMap[row.sector].industries.push({
                industry: row.industry,
                company_count: parseInt(row.company_count),
                active_companies: parseInt(row.active_companies)
            });
            
            sectorMap[row.sector].total_companies += parseInt(row.company_count);
            sectorMap[row.sector].active_companies += parseInt(row.active_companies);
        });
        
        const sectors = Object.values(sectorMap);
        
        console.log(`✅ Found ${sectors.length} sectors with ${result.rows.length} industries`);
        
        res.json({
            success: true,
            data: {
                sectors,
                summary: {
                    total_sectors: sectors.length,
                    total_industries: result.rows.length,
                    total_companies: sectors.reduce((sum, s) => sum + s.total_companies, 0),
                    active_companies: sectors.reduce((sum, s) => sum + s.active_companies, 0)
                }
            },
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        console.error('❌ Error fetching sector list:', error);
        res.status(500).json({
            success: false,
            error: error.message || 'Failed to fetch sector list'
        });
    }
});

/**
 * GET /sectors/:sector/details
 * Get detailed analysis for a specific sector
 */
router.get('/:sector/details', async (req, res) => {
    try {
        const { sector } = req.params;
        const { limit = 50 } = req.query;
        
        console.log(`📊 Fetching detailed analysis for sector: ${sector}`);
        
        const sectorDetailQuery = `
            WITH latest_data AS (
                SELECT DISTINCT ON (cp.ticker)
                    cp.ticker,
                    cp.short_name,
                    cp.long_name,
                    cp.industry,
                    cp.market,
                    cp.country,
                    pd.close as current_price,
                    pd.volume,
                    pd.date as price_date,
                    
                    -- Performance metrics
                    (pd.close - LAG(pd.close, 1) OVER (PARTITION BY cp.ticker ORDER BY pd.date)) / LAG(pd.close, 1) OVER (PARTITION BY cp.ticker ORDER BY pd.date) * 100 as daily_change,
                    (pd.close - LAG(pd.close, 5) OVER (PARTITION BY cp.ticker ORDER BY pd.date)) / LAG(pd.close, 5) OVER (PARTITION BY cp.ticker ORDER BY pd.date) * 100 as weekly_change,
                    (pd.close - LAG(pd.close, 22) OVER (PARTITION BY cp.ticker ORDER BY pd.date)) / LAG(pd.close, 22) OVER (PARTITION BY cp.ticker ORDER BY pd.date) * 100 as monthly_change,
                    
                    -- Technical indicators
                    td.rsi,
                    td.momentum,
                    td.macd,
                    td.macd_signal,
                    td.sma_20,
                    td.sma_50,
                    
                    -- Momentum data
                    mm.jt_momentum_12_1,
                    mm.momentum_3m,
                    mm.momentum_6m,
                    mm.risk_adjusted_momentum,
                    mm.momentum_strength,
                    
                    -- Market cap estimate (price * volume as proxy)
                    pd.close * pd.volume as dollar_volume
                    
                FROM company_profile cp
                LEFT JOIN price_daily pd ON cp.ticker = pd.symbol
                LEFT JOIN technical_data_daily td ON cp.ticker = td.symbol AND td.date = pd.date
                LEFT JOIN momentum_metrics mm ON cp.ticker = mm.symbol
                WHERE cp.sector = $1
                    AND pd.date >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY cp.ticker, pd.date DESC
            )
            
            SELECT *,
                CASE 
                    WHEN current_price > sma_20 AND sma_20 > sma_50 THEN 'bullish'
                    WHEN current_price < sma_20 AND sma_20 < sma_50 THEN 'bearish'
                    ELSE 'neutral'
                END as trend,
                
                CASE 
                    WHEN rsi > 70 THEN 'overbought'
                    WHEN rsi < 30 THEN 'oversold'
                    ELSE 'neutral'
                END as rsi_signal,
                
                CASE 
                    WHEN macd > macd_signal THEN 'bullish'
                    WHEN macd < macd_signal THEN 'bearish'
                    ELSE 'neutral'
                END as macd_signal_type
                
            FROM latest_data
            WHERE current_price IS NOT NULL
            ORDER BY monthly_change DESC NULLS LAST
            LIMIT $2
        `;
        
        const result = await query(sectorDetailQuery, [sector, limit]);
        
        if (result.rows.length === 0) {
            return res.status(404).json({
                success: false,
                error: `Sector '${sector}' not found or has no current price data`
            });
        }
        
        // Calculate sector statistics
        const stocks = result.rows;
        const avgReturn = stocks.reduce((sum, stock) => sum + (parseFloat(stock.monthly_change) || 0), 0) / stocks.length;
        const totalVolume = stocks.reduce((sum, stock) => sum + (parseInt(stock.volume) || 0), 0);
        const avgMomentum = stocks.reduce((sum, stock) => sum + (parseFloat(stock.jt_momentum_12_1) || 0), 0) / stocks.length;
        
        // Trend distribution
        const trendCounts = stocks.reduce((counts, stock) => {
            counts[stock.trend] = (counts[stock.trend] || 0) + 1;
            return counts;
        }, {});
        
        // Industry breakdown
        const industryBreakdown = stocks.reduce((industries, stock) => {
            if (!industries[stock.industry]) {
                industries[stock.industry] = {
                    industry: stock.industry,
                    count: 0,
                    avg_return: 0,
                    stocks: []
                };
            }
            industries[stock.industry].count += 1;
            industries[stock.industry].stocks.push(stock.ticker);
            return industries;
        }, {});
        
        // Calculate industry averages
        Object.values(industryBreakdown).forEach(industry => {
            const industryStocks = stocks.filter(s => s.industry === industry.industry);
            industry.avg_return = industryStocks.reduce((sum, s) => sum + (parseFloat(s.monthly_change) || 0), 0) / industryStocks.length;
        });
        
        console.log(`✅ Found ${stocks.length} stocks in ${sector} sector`);
        
        res.json({
            success: true,
            data: {
                sector,
                summary: {
                    stock_count: stocks.length,
                    avg_monthly_return: avgReturn.toFixed(2),
                    total_volume: totalVolume,
                    avg_jt_momentum: avgMomentum.toFixed(4),
                    trend_distribution: trendCounts,
                    industry_count: Object.keys(industryBreakdown).length
                },
                industries: Object.values(industryBreakdown).sort((a, b) => b.avg_return - a.avg_return),
                stocks: stocks.map(stock => ({
                    symbol: stock.ticker,
                    name: stock.short_name,
                    industry: stock.industry,
                    current_price: parseFloat(stock.current_price || 0).toFixed(2),
                    volume: parseInt(stock.volume || 0),
                    performance: {
                        daily_change: parseFloat(stock.daily_change || 0).toFixed(2),
                        weekly_change: parseFloat(stock.weekly_change || 0).toFixed(2),
                        monthly_change: parseFloat(stock.monthly_change || 0).toFixed(2)
                    },
                    technicals: {
                        rsi: parseFloat(stock.rsi || 0).toFixed(2),
                        momentum: parseFloat(stock.momentum || 0).toFixed(2),
                        macd: parseFloat(stock.macd || 0).toFixed(4),
                        trend: stock.trend,
                        rsi_signal: stock.rsi_signal,
                        macd_signal: stock.macd_signal_type
                    },
                    momentum: {
                        jt_momentum_12_1: parseFloat(stock.jt_momentum_12_1 || 0).toFixed(4),
                        momentum_3m: parseFloat(stock.momentum_3m || 0).toFixed(4),
                        momentum_6m: parseFloat(stock.momentum_6m || 0).toFixed(4),
                        risk_adjusted: parseFloat(stock.risk_adjusted_momentum || 0).toFixed(4),
                        strength: parseFloat(stock.momentum_strength || 0).toFixed(2)
                    }
                }))
            },
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        console.error(`❌ Error fetching details for sector ${req.params.sector}:`, error);
        res.status(500).json({
            success: false,
            error: error.message || 'Failed to fetch sector details'
        });
    }
});

module.exports = router;