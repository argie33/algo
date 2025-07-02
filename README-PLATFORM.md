# Financial Platform - Institutional-Grade AI-Driven Analysis

A comprehensive financial analysis platform implementing institutional-grade methodologies with AI-powered insights, based on proven academic research and industry best practices.

## Overview

This platform provides the analytical rigor of hedge funds and investment banks using cost-effective data sources, delivering professional-level analysis democratized for individual investors.

## Core Components

### 1. Economic Modeling Framework (`economic_modeling.py`)
- **Recession Prediction Model** based on academic research
- **Market Regime Detection** (Bull/Bear/Normal)
- Incorporates yield curve, credit spreads, employment indicators
- Research foundation: Estrella & Mishkin (1998), Gilchrist & Zakrajšek (2012)

### 2. Sentiment Analysis Pipeline (`sentiment_analysis.py`)
- **Multi-source sentiment analysis** with financial domain adaptation
- News sentiment using financial NLP
- Social media sentiment from Reddit communities
- Analyst sentiment from recommendation changes
- Composite scoring with confidence weighting

### 3. Technical Pattern Recognition (`pattern_recognition.py`)
- **AI-powered pattern detection** for classic chart formations
- Head & Shoulders, Double Tops, Triangle patterns
- Confidence scoring and probability estimation
- Price targets and stop-loss recommendations

### 4. Portfolio Management System (`portfolio_management.py`)
- **Modern Portfolio Theory optimization**
- Performance attribution analysis (Brinson model)
- Risk management and diversification metrics
- Portfolio rebalancing recommendations

### 5. Data Quality Validation (`data_quality_validation.py`)
- **Comprehensive data validation framework**
- Price data anomaly detection
- Financial statement consistency checks
- Data freshness and quality scoring

### 6. Monitoring & Alerting (`monitoring_alerting.py`)
- **Real-time system monitoring**
- Performance tracking and health metrics
- Automated alerting with severity levels
- Email/SMS notifications for critical events

## Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Setup
```bash
# Install dependencies
pip install -r requirements-platform.txt

# For TA-Lib (technical analysis library)
# On Ubuntu/Debian:
sudo apt-get install libta-lib-dev

# On macOS:
brew install ta-lib

# On Windows:
# Download TA-Lib from https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib
```

## Quick Start

### Run the Complete Demo
```python
python financial_platform_demo.py
```

This demonstrates all platform components working together.

### Individual Component Usage

#### Economic Analysis
```python
from economic_modeling import RecessionPredictor, MarketRegimeDetector

# Recession prediction
predictor = RecessionPredictor()
result = predictor.calculate_recession_probability()
print(f"Recession Probability: {result['probability']:.1%}")

# Market regime detection
detector = MarketRegimeDetector()
regime = detector.detect_regime()
print(f"Market Regime: {regime['regime']}")
```

#### Sentiment Analysis
```python
from sentiment_analysis import SentimentAnalyzer

analyzer = SentimentAnalyzer()
sentiment = analyzer.analyze_comprehensive_sentiment('AAPL')
print(f"Sentiment Score: {sentiment['composite_score']:.3f}")
```

#### Pattern Recognition
```python
from pattern_recognition import TechnicalPatternRecognizer

recognizer = TechnicalPatternRecognizer()
patterns = recognizer.detect_patterns('AAPL')
print(f"Patterns Found: {patterns['patterns_found']}")
```

#### Portfolio Management
```python
from portfolio_management import Portfolio

portfolio = Portfolio(cash=100000.0)
portfolio.add_position("AAPL", 100, 150.0)
metrics = portfolio.get_portfolio_metrics()
print(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
```

#### Data Quality Validation
```python
from data_quality_validation import DataQualityFramework

dq = DataQualityFramework()
result = dq.validate_symbol_data('AAPL')
print(f"Data Quality Score: {result['summary']['overall_score']:.1f}")
```

#### Monitoring System
```python
from monitoring_alerting import MonitoringSystem

monitor = MonitoringSystem()
monitor.start_monitoring()
status = monitor.get_system_status()
print(f"System Health: {status['monitoring_active']}")
```

## Architecture

### Data Sources
- **yfinance**: Historical prices, financial statements, company info
- **FRED API**: Economic indicators, Treasury rates
- **NewsAPI**: Financial news sentiment
- **Reddit API**: Social sentiment analysis
- **SEC EDGAR**: Regulatory filings

### Scoring Methodology
Based on the **Financial Platform Blueprint**, the system implements:

1. **Quality Score** (Piotroski F-Score, Altman Z-Score, ROIC)
2. **Growth Score** (Sustainable growth, earnings quality)
3. **Value Score** (DCF, relative valuation, intrinsic value)
4. **Momentum Score** (Price momentum, fundamental momentum)
5. **Sentiment Score** (News, social, analyst sentiment)
6. **Positioning Score** (Institutional holdings, insider activity)

### Research Foundation
- Fama-French Five-Factor Model (2015)
- Behavioral Finance Research (Baker & Wurgler, 2006)
- Technical Analysis Validation (Lo et al., 2000)
- Modern Portfolio Theory (Markowitz, 1952)

## Configuration

### Environment Variables
Create a `.env` file:
```
# API Keys
NEWS_API_KEY=your_newsapi_key
ALPHA_VANTAGE_KEY=your_alpha_vantage_key
FRED_API_KEY=your_fred_api_key

# Email Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_USER=your_email@gmail.com
EMAIL_PASS=your_app_password

# Database
DATABASE_URL=postgresql://user:pass@localhost/financial_db
```

### Alert Configuration
```python
email_config = {
    'smtp_server': 'smtp.gmail.com',
    'smtp_port': 587,
    'username': 'your_email@gmail.com',
    'password': 'your_app_password',
    'from': 'alerts@yourplatform.com',
    'to': ['admin@yourplatform.com']
}
```

## Performance Targets

- **Stock quote lookup**: <500ms
- **Score calculation**: <2 seconds
- **Pattern recognition**: <10 seconds
- **Portfolio optimization**: <30 seconds

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=.

# Run specific component tests
pytest test_economic_modeling.py
```

## Production Deployment

### Docker Deployment
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements-platform.txt .
RUN pip install -r requirements-platform.txt

COPY . .
CMD ["python", "financial_platform_demo.py"]
```

### Kubernetes Deployment
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: financial-platform
spec:
  replicas: 3
  selector:
    matchLabels:
      app: financial-platform
  template:
    metadata:
      labels:
        app: financial-platform
    spec:
      containers:
      - name: platform
        image: financial-platform:latest
        ports:
        - containerPort: 5000
```

## Monitoring and Alerts

The platform includes comprehensive monitoring:

- **System Health**: CPU, memory, disk usage
- **Data Quality**: Freshness, accuracy, completeness
- **Performance**: Response times, throughput
- **Portfolio**: Risk metrics, drawdowns
- **Trading Signals**: Pattern alerts, regime changes

## API Integration

### REST API Endpoints
```
GET /api/recession-probability
GET /api/sentiment/{symbol}
GET /api/patterns/{symbol}
GET /api/portfolio/metrics
GET /api/data-quality/{symbol}
```

### WebSocket Streams
```
ws://localhost:5000/alerts
ws://localhost:5000/market-data
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Research Citations

- Estrella, A., & Mishkin, F. S. (1998). Predicting US recessions
- Fama, E. F., & French, K. R. (2015). A five-factor asset pricing model
- Baker, M., & Wurgler, J. (2006). Investor sentiment and the cross-section of stock returns
- Lo, A. W., Mamaysky, H., & Wang, J. (2000). Foundations of technical analysis
- Piotroski, J. D. (2000). Value investing: The use of historical financial statement information

## Support

For questions and support:
- Create an issue on GitHub
- Email: support@financialplatform.com
- Documentation: https://docs.financialplatform.com

---

**Disclaimer**: This platform is for educational and research purposes. Past performance does not guarantee future results. Always consult with a qualified financial advisor before making investment decisions.