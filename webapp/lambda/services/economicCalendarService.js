/**
 * Economic Calendar Service
 * Real implementation to replace mock economic calendar data
 * Integrates with multiple economic data providers
 */

const axios = require('axios');
const { getTimeout } = require('../utils/timeoutManager');

class EconomicCalendarService {
    constructor() {
        // Multiple data sources for economic calendar
        this.dataSources = {
            tradingeconomics: {
                baseUrl: 'https://api.tradingeconomics.com',
                apiKey: process.env.TRADING_ECONOMICS_API_KEY,
                available: !!process.env.TRADING_ECONOMICS_API_KEY
            },
            alphavantage: {
                baseUrl: 'https://www.alphavantage.co/query',
                apiKey: process.env.ALPHA_VANTAGE_API_KEY,
                available: !!process.env.ALPHA_VANTAGE_API_KEY
            },
            financialmodelingprep: {
                baseUrl: 'https://financialmodelingprep.com/api/v3',
                apiKey: process.env.FMP_API_KEY,
                available: !!process.env.FMP_API_KEY
            }
        };

        console.log('📅 Economic Calendar Service initialized');
        this.logAvailableServices();
    }

    /**
     * Log available data sources
     */
    logAvailableServices() {
        const available = Object.entries(this.dataSources)
            .filter(([name, config]) => config.available)
            .map(([name]) => name);
        
        if (available.length > 0) {
            console.log(`✅ Available economic data sources: ${available.join(', ')}`);
        } else {
            console.warn('⚠️ No economic data API keys configured, will use mock data');
        }
    }

    /**
     * Get economic calendar events
     */
    async getEconomicCalendar(startDate = null, endDate = null, country = 'US') {
        const start = startDate || new Date().toISOString().split('T')[0];
        const end = endDate || new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

        console.log(`📅 Getting economic calendar from ${start} to ${end} for ${country}...`);

        // Try data sources in order of preference
        for (const [sourceName, config] of Object.entries(this.dataSources)) {
            if (!config.available) continue;

            try {
                console.log(`📡 Trying ${sourceName} for economic calendar data...`);
                const events = await this.getCalendarFromSource(sourceName, start, end, country);
                
                if (events && events.length > 0) {
                    console.log(`✅ Got ${events.length} events from ${sourceName}`);
                    return {
                        events,
                        source: sourceName,
                        dateRange: { start, end },
                        country,
                        timestamp: new Date().toISOString()
                    };
                }
            } catch (error) {
                console.warn(`⚠️ ${sourceName} failed:`, error.message);
                continue;
            }
        }

        // Fallback to mock data if all sources fail
        console.log('📅 All data sources failed, generating mock economic calendar...');
        return this.generateMockCalendar(start, end, country);
    }

    /**
     * Get calendar data from specific source
     */
    async getCalendarFromSource(sourceName, startDate, endDate, country) {
        switch (sourceName) {
            case 'tradingeconomics':
                return await this.getTradingEconomicsCalendar(startDate, endDate, country);
            case 'alphavantage':
                return await this.getAlphaVantageCalendar(startDate, endDate, country);
            case 'financialmodelingprep':
                return await this.getFMPCalendar(startDate, endDate, country);
            default:
                throw new Error(`Unknown source: ${sourceName}`);
        }
    }

    /**
     * Get calendar from Trading Economics API
     */
    async getTradingEconomicsCalendar(startDate, endDate, country) {
        const config = this.dataSources.tradingeconomics;
        const url = `${config.baseUrl}/calendar/country/${country}/${startDate}/${endDate}`;

        try {
            const response = await axios.get(url, {
                params: { c: config.apiKey },
                timeout: getTimeout('market_data', 'calendar')
            });

            return response.data.map(event => ({
                id: event.CalendarId,
                event: event.Event,
                country: event.Country,
                date: event.Date,
                time: event.Time || '00:00',
                currency: this.getCurrencyFromCountry(event.Country),
                importance: this.mapImportance(event.Importance),
                category: this.categorizeEvent(event.Event),
                forecast: event.Forecast,
                previous: event.Previous,
                actual: event.Actual,
                unit: event.Unit,
                source: 'tradingeconomics'
            }));
        } catch (error) {
            throw new Error(`Trading Economics API error: ${error.message}`);
        }
    }

    /**
     * Get calendar from Alpha Vantage API
     */
    async getAlphaVantageCalendar(startDate, endDate, country) {
        const config = this.dataSources.alphavantage;
        
        try {
            const response = await axios.get(config.baseUrl, {
                params: {
                    function: 'ECONOMIC_CALENDAR',
                    apikey: config.apiKey,
                    horizon: '3month' // Alpha Vantage uses fixed horizons
                },
                timeout: getTimeout('market_data', 'calendar')
            });

            if (!response.data.data) {
                throw new Error('No calendar data in response');
            }

            // Filter by date range and country
            return response.data.data
                .filter(event => {
                    const eventDate = event.date;
                    const eventCountry = event.country;
                    return eventDate >= startDate && eventDate <= endDate && 
                           (country === 'ALL' || eventCountry === country);
                })
                .map(event => ({
                    id: event.event_id || Math.random().toString(36).substr(2, 9),
                    event: event.name,
                    country: event.country,
                    date: event.date,
                    time: event.time || '00:00',
                    currency: event.currency,
                    importance: this.mapImportance(event.importance),
                    category: this.categorizeEvent(event.name),
                    forecast: event.estimate,
                    previous: event.previous,
                    actual: event.actual,
                    unit: event.unit,
                    source: 'alphavantage'
                }));
        } catch (error) {
            throw new Error(`Alpha Vantage API error: ${error.message}`);
        }
    }

    /**
     * Get calendar from Financial Modeling Prep API
     */
    async getFMPCalendar(startDate, endDate, country) {
        const config = this.dataSources.financialmodelingprep;
        
        try {
            const response = await axios.get(`${config.baseUrl}/economic_calendar`, {
                params: {
                    from: startDate,
                    to: endDate,
                    apikey: config.apiKey
                },
                timeout: getTimeout('market_data', 'calendar')
            });

            if (!Array.isArray(response.data)) {
                throw new Error('Invalid response format');
            }

            return response.data
                .filter(event => country === 'ALL' || event.country === country)
                .map(event => ({
                    id: Math.random().toString(36).substr(2, 9),
                    event: event.event,
                    country: event.country,
                    date: event.date,
                    time: event.time || '00:00',
                    currency: event.currency,
                    importance: this.mapImportance(event.impact),
                    category: this.categorizeEvent(event.event),
                    forecast: event.estimate,
                    previous: event.previous,
                    actual: event.actual,
                    unit: event.unit,
                    source: 'financialmodelingprep'
                }));
        } catch (error) {
            throw new Error(`FMP API error: ${error.message}`);
        }
    }

    /**
     * Get high-impact events only
     */
    async getHighImpactEvents(days = 7, country = 'US') {
        try {
            const endDate = new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
            const calendar = await this.getEconomicCalendar(null, endDate, country);
            
            return {
                ...calendar,
                events: calendar.events.filter(event => event.importance === 'High')
            };
        } catch (error) {
            console.error('❌ Failed to get high-impact events:', error.message);
            throw error;
        }
    }

    /**
     * Get today's economic events
     */
    async getTodaysEvents(country = 'US') {
        try {
            const today = new Date().toISOString().split('T')[0];
            return await this.getEconomicCalendar(today, today, country);
        } catch (error) {
            console.error('❌ Failed to get today\'s events:', error.message);
            throw error;
        }
    }

    /**
     * Generate mock economic calendar data when APIs are unavailable
     */
    generateMockCalendar(startDate, endDate, country) {
        console.log('🎭 Generating mock economic calendar data...');
        
        const events = [];
        const start = new Date(startDate);
        const end = new Date(endDate);
        const days = Math.ceil((end - start) / (1000 * 60 * 60 * 24));

        // Generate realistic economic events
        const eventTemplates = [
            { name: 'FOMC Rate Decision', importance: 'High', category: 'monetary_policy' },
            { name: 'Non-Farm Payrolls', importance: 'High', category: 'employment' },
            { name: 'Consumer Price Index', importance: 'High', category: 'inflation' },
            { name: 'GDP Growth Rate', importance: 'High', category: 'economic_growth' },
            { name: 'Retail Sales', importance: 'Medium', category: 'economic_activity' },
            { name: 'Industrial Production', importance: 'Medium', category: 'economic_activity' },
            { name: 'Consumer Confidence', importance: 'Medium', category: 'sentiment' },
            { name: 'Initial Jobless Claims', importance: 'Medium', category: 'employment' },
            { name: 'Existing Home Sales', importance: 'Low', category: 'housing' },
            { name: 'Manufacturing PMI', importance: 'Medium', category: 'manufacturing' }
        ];

        for (let i = 0; i < Math.min(days * 2, 20); i++) {
            const template = eventTemplates[Math.floor(Math.random() * eventTemplates.length)];
            const eventDate = new Date(start.getTime() + Math.random() * (end.getTime() - start.getTime()));
            
            events.push({
                id: Math.random().toString(36).substr(2, 9),
                event: template.name,
                country: country,
                date: eventDate.toISOString().split('T')[0],
                time: ['08:30', '10:00', '14:00', '15:00'][Math.floor(Math.random() * 4)],
                currency: this.getCurrencyFromCountry(country),
                importance: template.importance,
                category: template.category,
                forecast: this.generateMockValue(template.name),
                previous: this.generateMockValue(template.name),
                actual: null,
                unit: this.getUnitForEvent(template.name),
                source: 'mock_data'
            });
        }

        return {
            events: events.sort((a, b) => new Date(a.date) - new Date(b.date)),
            source: 'mock_data',
            dateRange: { start: startDate, end: endDate },
            country,
            timestamp: new Date().toISOString()
        };
    }

    /**
     * Helper methods for data normalization
     */
    mapImportance(importance) {
        if (!importance) return 'Low';
        const imp = importance.toString().toLowerCase();
        if (imp.includes('high') || imp.includes('3')) return 'High';
        if (imp.includes('medium') || imp.includes('2')) return 'Medium';
        return 'Low';
    }

    categorizeEvent(eventName) {
        const name = eventName.toLowerCase();
        if (name.includes('rate') || name.includes('fomc')) return 'monetary_policy';
        if (name.includes('payroll') || name.includes('unemployment') || name.includes('jobless')) return 'employment';
        if (name.includes('cpi') || name.includes('inflation')) return 'inflation';
        if (name.includes('gdp') || name.includes('growth')) return 'economic_growth';
        if (name.includes('retail') || name.includes('sales')) return 'economic_activity';
        if (name.includes('housing') || name.includes('home')) return 'housing';
        if (name.includes('confidence') || name.includes('sentiment')) return 'sentiment';
        if (name.includes('manufacturing') || name.includes('pmi')) return 'manufacturing';
        return 'other';
    }

    getCurrencyFromCountry(country) {
        const currencyMap = {
            'US': 'USD', 'USA': 'USD', 'United States': 'USD',
            'EU': 'EUR', 'Germany': 'EUR', 'France': 'EUR',
            'UK': 'GBP', 'United Kingdom': 'GBP',
            'JP': 'JPY', 'Japan': 'JPY',
            'CA': 'CAD', 'Canada': 'CAD',
            'AU': 'AUD', 'Australia': 'AUD',
            'CH': 'CHF', 'Switzerland': 'CHF'
        };
        return currencyMap[country] || 'USD';
    }

    generateMockValue(eventName) {
        const name = eventName.toLowerCase();
        if (name.includes('rate') || name.includes('fomc')) return `${(Math.random() * 2 + 4).toFixed(2)}%`;
        if (name.includes('payroll')) return `${Math.floor(Math.random() * 300 + 100)}K`;
        if (name.includes('cpi')) return `${(Math.random() * 2 + 2).toFixed(1)}%`;
        if (name.includes('gdp')) return `${(Math.random() * 2 + 1).toFixed(1)}%`;
        return `${(Math.random() * 10).toFixed(1)}`;
    }

    getUnitForEvent(eventName) {
        const name = eventName.toLowerCase();
        if (name.includes('rate') || name.includes('cpi') || name.includes('gdp')) return '%';
        if (name.includes('payroll') || name.includes('claims')) return 'K';
        if (name.includes('sales') || name.includes('production')) return '$B';
        return '';
    }

    /**
     * Validate API keys
     */
    async validateApiKeys() {
        const results = {};
        
        for (const [sourceName, config] of Object.entries(this.dataSources)) {
            if (!config.available) {
                results[sourceName] = { valid: false, message: 'API key not configured' };
                continue;
            }

            try {
                await this.getCalendarFromSource(sourceName, 
                    new Date().toISOString().split('T')[0], 
                    new Date().toISOString().split('T')[0], 
                    'US'
                );
                results[sourceName] = { valid: true, message: 'API key validated' };
            } catch (error) {
                results[sourceName] = { valid: false, message: error.message };
            }
        }

        return results;
    }
}

module.exports = EconomicCalendarService;