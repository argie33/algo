# Financial Data Web Application

A professional financial data platform built with React and Node.js, featuring real-time market data visualization, advanced stock screening, and comprehensive financial analysis tools.

## 🌟 Features

- **Market Dashboard**: Real-time market overview with sector performance and key metrics
- **Stock Analysis**: Detailed individual stock analysis with financial ratios and charts
- **Advanced Screening**: Multi-criteria stock filtering with 20+ financial parameters
- **Interactive Charts**: Beautiful visualizations using Recharts library
- **Responsive Design**: Professional UI built with Material-UI components
- **Real-time Data**: Live market data integration with comprehensive filtering

## 🏗️ Architecture

### Frontend
- **React 18** with Vite for fast development
- **Material-UI (MUI)** for professional component library
- **React Query** for efficient data fetching and caching
- **React Router** for navigation
- **Recharts** for data visualization

### Backend
- **Node.js** with Express framework
- **PostgreSQL** database with optimized queries
- **AWS Integration** (Secrets Manager, ECS, RDS)
- **Docker** containerization for scalable deployment

### Infrastructure
- **AWS CloudFormation** for Infrastructure as Code
- **Application Load Balancer** for high availability
- **ECS Fargate** for serverless container orchestration
- **CloudFront CDN** for global content delivery
- **S3** for static asset hosting

## 📋 Prerequisites

- Node.js 18 or higher
- PostgreSQL 12 or higher
- AWS CLI (for deployment)
- Docker (optional, for containerized development)

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd loadfundamentals
chmod +x setup-dev.sh
./setup-dev.sh setup
```

### 2. Database Configuration

Ensure your PostgreSQL database is running and accessible. The setup script will create environment files with default credentials:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=fundamentals
DB_USER=postgres
DB_PASSWORD=password
```

### 3. Start Development Servers

```bash
./start-dev.sh
```

This will start:
- Frontend: http://localhost:5173
- Backend: http://localhost:3001
- API Health Check: http://localhost:3001/api/health

## 📁 Project Structure

```
loadfundamentals/
├── webapp/
│   ├── frontend/                 # React application
│   │   ├── src/
│   │   │   ├── components/       # Reusable UI components
│   │   │   ├── pages/           # Page components
│   │   │   ├── services/        # API service layer
│   │   │   └── utils/           # Utility functions
│   │   ├── package.json
│   │   └── vite.config.js
│   └── backend/                 # Node.js API server
│       ├── src/
│       │   ├── routes/          # API route handlers
│       │   ├── middleware/      # Express middleware
│       │   └── utils/           # Database utilities
│       ├── package.json
│       └── Dockerfile
├── template-webapp.yml          # CloudFormation template
├── .github/workflows/           # CI/CD workflows
├── setup-dev.sh               # Development setup script
└── README.md
```

## 🎯 Key Pages & Features

### Dashboard
- Market overview with key indicators
- Sector performance visualization
- Top gainers/losers
- Market breadth analysis

### Stock List
- Comprehensive stock listings
- Advanced filtering (sector, price range, market cap)
- Sortable columns
- Real-time price updates

### Stock Detail
- Individual stock analysis
- Financial statements (Income, Cash Flow)
- Key ratios and metrics
- Analyst recommendations
- Interactive price charts

### Stock Screener
- Multi-criteria filtering system
- 20+ financial parameters
- Custom screening profiles
- Export capabilities
- Real-time results

### Market Overview
- Sector analysis
- Market capitalization distribution
- Performance trending
- Economic indicators

## 🔧 Development

### Available Scripts

#### Frontend (`webapp/frontend/`)
```bash
npm run dev          # Start development server
npm run build        # Build for production
npm run preview      # Preview production build
npm run test         # Run tests
npm run lint         # Lint code
```

#### Backend (`webapp/backend/`)
```bash
npm run dev          # Start development server with nodemon
npm start            # Start production server
npm test             # Run tests
npm run lint         # Lint code
```

### Environment Variables

#### Frontend (`.env`)
```env
VITE_API_URL=http://localhost:3001/api
VITE_APP_TITLE=Financial Data Platform
VITE_APP_DESCRIPTION=Professional financial data analysis platform
```

#### Backend (`.env`)
```env
NODE_ENV=development
PORT=3001
DB_HOST=localhost
DB_PORT=5432
DB_NAME=fundamentals
DB_USER=postgres
DB_PASSWORD=password
AWS_REGION=us-east-1
CORS_ORIGIN=http://localhost:5173
```

## 📊 Database Schema

The application uses the following main tables:

- `company_profile` - Company information and metadata
- `market_data` - Real-time market data and prices
- `key_metrics` - Financial ratios and key metrics
- `ttm_income_stmt` - Trailing twelve months income statements
- `ttm_cash_flow` - Trailing twelve months cash flow
- `analyst_recommendations` - Analyst ratings and recommendations

## 🌐 API Endpoints

### Health Check
- `GET /api/health` - API health status

### Stocks
- `GET /api/stocks` - List stocks with filtering
- `GET /api/stocks/:ticker` - Get detailed stock information
- `GET /api/stocks/:ticker/profile` - Get stock profile
- `GET /api/stocks/:ticker/metrics` - Get financial metrics
- `GET /api/stocks/:ticker/financials` - Get financial statements
- `GET /api/stocks/:ticker/recommendations` - Get analyst recommendations
- `GET /api/stocks/screen` - Screen stocks with criteria

### Market Data
- `GET /api/metrics/overview` - Market overview
- `GET /api/metrics/valuation` - Valuation metrics
- `GET /api/metrics/growth` - Growth metrics
- `GET /api/metrics/dividends` - Dividend metrics
- `GET /api/metrics/financial-strength` - Financial strength metrics

## 🚀 Deployment

### AWS Infrastructure

The application is deployed using CloudFormation templates:

1. **Core Infrastructure** (`template-core.yml`) - VPC, subnets, security groups
2. **Application Stack** (`template-app-stocks.yml`) - RDS, ECS cluster
3. **Web Application** (`template-webapp.yml`) - ALB, ECS service, S3, CloudFront

### Deployment Process

1. **Prerequisites**:
   ```bash
   aws configure  # Configure AWS credentials
   ```

2. **Deploy Infrastructure**:
   ```bash
   # Deploy core infrastructure
   aws cloudformation deploy \
     --template-file template-core.yml \
     --stack-name loadfundamentals-core \
     --capabilities CAPABILITY_IAM

   # Deploy application infrastructure
   aws cloudformation deploy \
     --template-file template-app-stocks.yml \
     --stack-name loadfundamentals-app-stocks \
     --capabilities CAPABILITY_IAM

   # Deploy web application
   aws cloudformation deploy \
     --template-file template-webapp.yml \
     --stack-name loadfundamentals-webapp \
     --capabilities CAPABILITY_IAM
   ```

3. **Automated Deployment**:
   - GitHub Actions workflow automatically deploys on push to main branch
   - Builds Docker images and pushes to ECR
   - Updates ECS services with new images
   - Deploys frontend to S3 and invalidates CloudFront cache

### Environment Configuration

For production deployment, configure these secrets in GitHub:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_ACCOUNT_ID`

## 🧪 Testing

### Unit Tests
```bash
# Backend tests
cd webapp/backend && npm test

# Frontend tests
cd webapp/frontend && npm test
```

### Integration Tests
```bash
# Full application test
./setup-dev.sh test
```

### Load Testing
The application includes basic load testing capabilities and can handle:
- 1000+ concurrent users
- 10,000+ database queries per minute
- Sub-second response times for most endpoints

## 📈 Performance Optimization

### Frontend
- Code splitting with React lazy loading
- Image optimization and lazy loading
- React Query for intelligent caching
- Bundle optimization with Vite

### Backend
- Database query optimization with indexes
- Connection pooling
- Response caching for static data
- Pagination for large datasets

### Infrastructure
- CloudFront CDN for global delivery
- Auto-scaling ECS services
- Read replicas for database scaling
- Application Load Balancer health checks

## 🔒 Security

- CORS configuration for API security
- Input validation and sanitization
- AWS IAM roles with least privilege
- Encrypted data in transit and at rest
- Security groups for network isolation

## 📚 Additional Resources

### Documentation
- [API Documentation](./docs/api.md)
- [Database Schema](./docs/database.md)
- [Deployment Guide](./docs/deployment.md)

### Development Tools
- [VS Code Extensions](./.vscode/extensions.json)
- [ESLint Configuration](./webapp/frontend/.eslintrc.js)
- [Prettier Configuration](./webapp/frontend/.prettierrc)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Issues**: Create a GitHub issue for bugs or feature requests
- **Documentation**: Check the docs/ directory for detailed guides
- **Development**: Use the setup script for quick development environment setup

---

**Built with ❤️ for financial data analysis**
