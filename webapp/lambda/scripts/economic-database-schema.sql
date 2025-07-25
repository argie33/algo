-- ============================================================================
-- ECONOMIC DATA TABLES - Complete Schema for Economics Page
-- ============================================================================

-- Enhanced economic indicators table with proper fields
DROP TABLE IF EXISTS economic_indicators CASCADE;
CREATE TABLE economic_indicators (
    id SERIAL PRIMARY KEY,
    indicator_id VARCHAR(50) NOT NULL, -- FRED series ID (e.g., 'GDP', 'UNRATE')
    indicator_name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL, -- GDP, Employment, Inflation, etc.
    value DECIMAL(15,4) NOT NULL,
    date DATE NOT NULL,
    units VARCHAR(50), -- percent, billions, index, etc.
    frequency VARCHAR(20), -- daily, monthly, quarterly, annual
    source VARCHAR(100) DEFAULT 'FRED',
    description TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(indicator_id, date)
);

-- Create indexes for performance
CREATE INDEX idx_economic_indicators_id_date ON economic_indicators(indicator_id, date DESC);
CREATE INDEX idx_economic_indicators_category ON economic_indicators(category);
CREATE INDEX idx_economic_indicators_date ON economic_indicators(date DESC);

-- Economic calendar table for events
DROP TABLE IF EXISTS economic_calendar CASCADE;
CREATE TABLE economic_calendar (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(100),
    event_name VARCHAR(255) NOT NULL,
    event_date DATE NOT NULL,
    event_time TIME,
    country VARCHAR(3) DEFAULT 'US',
    importance VARCHAR(20) DEFAULT 'Medium', -- Low, Medium, High
    category VARCHAR(100), -- Employment, GDP, Inflation, etc.
    forecast_value VARCHAR(100),
    previous_value VARCHAR(100),
    actual_value VARCHAR(100),
    currency VARCHAR(3) DEFAULT 'USD',
    source VARCHAR(100) DEFAULT 'Economic Calendar API',
    description TEXT,
    impact_score INTEGER, -- 1-10 scale
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, event_date)
);

-- Create indexes for calendar
CREATE INDEX idx_economic_calendar_date ON economic_calendar(event_date DESC);
CREATE INDEX idx_economic_calendar_importance ON economic_calendar(importance);
CREATE INDEX idx_economic_calendar_country ON economic_calendar(country);

-- Market correlations table
DROP TABLE IF EXISTS market_correlations CASCADE;
CREATE TABLE market_correlations (
    id SERIAL PRIMARY KEY,
    indicator1 VARCHAR(50) NOT NULL,
    indicator2 VARCHAR(50) NOT NULL,
    correlation_value DECIMAL(6,4) NOT NULL, -- -1.0000 to 1.0000
    period_days INTEGER NOT NULL, -- lookback period
    calculation_date DATE NOT NULL,
    method VARCHAR(20) DEFAULT 'pearson', -- pearson, spearman
    significance_level DECIMAL(4,3), -- p-value
    sample_size INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(indicator1, indicator2, period_days, calculation_date)
);

-- Economic forecasts table
DROP TABLE IF EXISTS economic_forecasts CASCADE;
CREATE TABLE economic_forecasts (
    id SERIAL PRIMARY KEY,
    indicator_id VARCHAR(50) NOT NULL,
    model_name VARCHAR(100) NOT NULL,
    forecast_date DATE NOT NULL,
    forecast_value DECIMAL(15,4) NOT NULL,
    confidence_level DECIMAL(5,2), -- 0.00 to 100.00
    forecast_horizon_months INTEGER,
    methodology TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(indicator_id, model_name, forecast_date)
);

-- Recession probability model results
DROP TABLE IF EXISTS recession_probabilities CASCADE;
CREATE TABLE recession_probabilities (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    calculation_date DATE NOT NULL,
    probability_percentage DECIMAL(5,2) NOT NULL,
    time_horizon_months INTEGER NOT NULL,
    key_factors JSONB, -- Array of contributing factors
    confidence_score DECIMAL(5,2),
    methodology TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(model_name, calculation_date, time_horizon_months)
);

-- Economic scenarios analysis
DROP TABLE IF EXISTS economic_scenarios CASCADE;
CREATE TABLE economic_scenarios (
    id SERIAL PRIMARY KEY,
    scenario_name VARCHAR(100) NOT NULL,
    scenario_type VARCHAR(50) NOT NULL, -- bull, base, bear
    probability_percentage DECIMAL(5,2),
    gdp_growth_forecast DECIMAL(6,2),
    unemployment_forecast DECIMAL(5,2),
    inflation_forecast DECIMAL(5,2),
    fed_rate_forecast DECIMAL(5,2),
    time_horizon_months INTEGER,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- SEED DATA - Essential Economic Indicators
-- ============================================================================

-- Insert key economic indicators metadata
INSERT INTO economic_indicators (indicator_id, indicator_name, category, value, date, units, frequency, description) VALUES
-- GDP Indicators
('GDP', 'Gross Domestic Product', 'GDP', 27000.0, '2024-01-01', 'billions', 'quarterly', 'Total value of goods and services produced'),
('A191RL1Q225SBEA', 'GDP Growth Rate', 'GDP', 2.1, '2024-01-01', 'percent', 'quarterly', 'Real GDP growth rate annualized'),

-- Employment Indicators  
('UNRATE', 'Unemployment Rate', 'Employment', 3.7, '2024-01-01', 'percent', 'monthly', 'Civilian unemployment rate'),
('PAYEMS', 'Nonfarm Payrolls', 'Employment', 157000.0, '2024-01-01', 'thousands', 'monthly', 'Total nonfarm employees'),
('JTSJOL', 'Job Openings', 'Employment', 8800.0, '2024-01-01', 'thousands', 'monthly', 'Job openings and labor turnover'),

-- Inflation Indicators
('CPIAUCSL', 'Consumer Price Index', 'Inflation', 310.5, '2024-01-01', 'index', 'monthly', 'Consumer Price Index for All Urban Consumers'),
('CPILFESL', 'Core CPI', 'Inflation', 3.2, '2024-01-01', 'percent', 'monthly', 'Core CPI less food and energy'),
('PCEPI', 'PCE Price Index', 'Inflation', 270.8, '2024-01-01', 'index', 'monthly', 'Personal Consumption Expenditures Price Index'),

-- Interest Rates
('DFF', 'Federal Funds Rate', 'Interest Rates', 5.25, '2024-01-01', 'percent', 'daily', 'Effective federal funds rate'),
('DGS10', '10-Year Treasury Rate', 'Interest Rates', 4.5, '2024-01-01', 'percent', 'daily', '10-Year Treasury Constant Maturity Rate'),
('DGS2', '2-Year Treasury Rate', 'Interest Rates', 4.3, '2024-01-01', 'percent', 'daily', '2-Year Treasury Constant Maturity Rate'),

-- Consumer Indicators
('RSXFS', 'Retail Sales', 'Consumer', 710.5, '2024-01-01', 'millions', 'monthly', 'Advance retail sales excluding food services'),
('UMCSENT', 'Consumer Sentiment', 'Consumer', 76.5, '2024-01-01', 'index', 'monthly', 'University of Michigan Consumer Sentiment'),

-- Housing Indicators  
('HOUST', 'Housing Starts', 'Housing', 1450.0, '2024-01-01', 'thousands', 'monthly', 'New privately-owned housing units started'),
('CSUSHPISA', 'Case-Shiller Home Price Index', 'Housing', 315.2, '2024-01-01', 'index', 'monthly', 'S&P/Case-Shiller U.S. National Home Price Index'),

-- Manufacturing
('INDPRO', 'Industrial Production', 'Manufacturing', 102.8, '2024-01-01', 'index', 'monthly', 'Industrial production index'),

-- Market Indicators
('VIXCLS', 'VIX Volatility Index', 'Market', 18.5, '2024-01-01', 'index', 'daily', 'CBOE Volatility Index'),
('DTWEXBGS', 'US Dollar Index', 'Market', 102.1, '2024-01-01', 'index', 'daily', 'Trade Weighted U.S. Dollar Index')

ON CONFLICT (indicator_id, date) DO UPDATE SET
    value = EXCLUDED.value,
    last_updated = CURRENT_TIMESTAMP;

-- Insert sample economic calendar events
INSERT INTO economic_calendar (event_id, event_name, event_date, event_time, importance, category, forecast_value, previous_value, description) VALUES
('FOMC_2024_03', 'FOMC Meeting', '2024-03-20', '14:00', 'High', 'Monetary Policy', '5.25%', '5.25%', 'Federal Open Market Committee interest rate decision'),
('CPI_2024_03', 'Consumer Price Index', '2024-03-12', '08:30', 'High', 'Inflation', '3.1% Y/Y', '3.2% Y/Y', 'Monthly CPI inflation report'),
('NFP_2024_03', 'Nonfarm Payrolls', '2024-03-08', '08:30', 'High', 'Employment', '200K', '275K', 'Monthly employment report'),
('GDP_2024_Q1', 'GDP Advance Estimate', '2024-03-28', '08:30', 'High', 'GDP', '2.0% SAAR', '3.2% SAAR', 'Quarterly GDP growth estimate'),
('RETAIL_2024_03', 'Retail Sales', '2024-03-14', '08:30', 'Medium', 'Consumer', '0.3% M/M', '0.6% M/M', 'Monthly retail sales report'),
('CLAIMS_2024_03_1', 'Initial Jobless Claims', '2024-03-07', '08:30', 'Medium', 'Employment', '220K', '215K', 'Weekly unemployment insurance claims'),
('PPI_2024_03', 'Producer Price Index', '2024-03-13', '08:30', 'Medium', 'Inflation', '2.8% Y/Y', '3.0% Y/Y', 'Producer price inflation measure'),
('HOUSING_2024_02', 'Housing Starts', '2024-03-19', '08:30', 'Medium', 'Housing', '1.44M SAAR', '1.33M SAAR', 'New residential construction starts')

ON CONFLICT (event_id, event_date) DO UPDATE SET
    forecast_value = EXCLUDED.forecast_value,
    last_updated = CURRENT_TIMESTAMP;

-- Insert sample recession probability models
INSERT INTO recession_probabilities (model_name, calculation_date, probability_percentage, time_horizon_months, key_factors, confidence_score, methodology) VALUES
('NY Fed Yield Curve Model', '2024-01-01', 32.5, 12, '["Yield Curve Inversion", "Term Structure"]', 78.0, 'Probit model based on yield curve slope'),
('FRED-Sam Model', '2024-01-01', 28.0, 12, '["Employment", "GDP Growth", "Industrial Production"]', 72.0, 'Sahm Rule and employment-based indicators'),
('Goldman Sachs Model', '2024-01-01', 35.0, 12, '["Financial Conditions", "Labor Market", "Inflation"]', 71.0, 'Multi-factor econometric model'),
('JPMorgan Model', '2024-01-01', 40.0, 18, '["Credit Spreads", "Yield Curve", "Leading Indicators"]', 68.0, 'Credit conditions and leading economic indicators'),
('AI Ensemble Model', '2024-01-01', 38.0, 12, '["Machine Learning", "50+ Indicators", "Real-time Analysis"]', 82.0, 'Ensemble of machine learning models with 50+ economic indicators')

ON CONFLICT (model_name, calculation_date, time_horizon_months) DO UPDATE SET
    probability_percentage = EXCLUDED.probability_percentage,
    confidence_score = EXCLUDED.confidence_score;

-- Insert economic scenarios
INSERT INTO economic_scenarios (scenario_name, scenario_type, probability_percentage, gdp_growth_forecast, unemployment_forecast, inflation_forecast, fed_rate_forecast, time_horizon_months, description) VALUES
('Soft Landing', 'bull', 25.0, 2.5, 3.8, 2.5, 4.0, 12, 'Economic growth slows but avoids recession with declining inflation'),
('Moderate Slowdown', 'base', 50.0, 1.2, 4.5, 2.8, 3.5, 12, 'Below-trend growth with modest labor market cooling'),
('Mild Recession', 'bear', 25.0, -0.8, 5.2, 2.2, 2.5, 12, 'Shallow recession with policy response and recovery within 12 months');

COMMIT;