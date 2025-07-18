// CRITICAL FIX: Replace ALL MUI components with TailwindCSS to eliminate createPalette error
import React, { useState, useEffect } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { AppLayout } from './components/ui/layout'

// All real page imports
import Dashboard from './pages/Dashboard'
import MarketOverview from './pages/MarketOverview'
import StockExplorer from './pages/StockExplorer'
import StockDetail from './pages/StockDetail'
import MetricsDashboard from './pages/MetricsDashboard'
import TechnicalAnalysis from './pages/TechnicalAnalysis'
import AnalystInsights from './pages/AnalystInsights'
import EarningsCalendar from './pages/EarningsCalendar'
import FinancialData from './pages/FinancialData'
import ServiceHealth from './pages/ServiceHealth'
import TechnicalHistory from './pages/TechnicalHistory'
import Backtest from './pages/Backtest'
import TradingSignals from './pages/TradingSignals'
import Portfolio from './pages/Portfolio'
import PortfolioHoldings from './pages/PortfolioHoldings'
import PortfolioPerformance from './pages/PortfolioPerformance'
import PortfolioOptimization from './pages/PortfolioOptimization'
import TradeHistory from './pages/TradeHistory'
import SentimentAnalysis from './pages/SentimentAnalysis'
import AdvancedScreener from './pages/AdvancedScreener'
import EconomicModeling from './pages/EconomicModeling'
import Settings from './pages/Settings'
import ScoresDashboard from './pages/ScoresDashboard'
import { useAuth } from './contexts/AuthContext'
import AuthModal from './components/auth/AuthModal'
import AuthFallback from './components/AuthFallback'
import ProtectedRoute from './components/auth/ProtectedRoute'
import SectorAnalysis from './pages/SectorAnalysis'
import TestApiPage from './pages/TestApiPage'
import PortfolioPerformanceSimple from './pages/PortfolioPerformanceSimple'
import PortfolioPerformanceDebug from './pages/PortfolioPerformanceDebug'
import AuthTest from './pages/AuthTest'
import SocialMediaSentiment from './pages/SocialMediaSentiment'
import NewsSentiment from './pages/NewsSentiment'
import Watchlist from './pages/Watchlist'
import MarketCommentary from './pages/MarketCommentary'
import EducationalContent from './pages/EducationalContent'
import PatternRecognition from './pages/PatternRecognition'
import AIAssistant from './pages/AIAssistant'
import Commodities from './pages/Commodities'
import OptionsAnalytics from './pages/options/OptionsAnalytics'
import OptionsStrategies from './pages/options/OptionsStrategies'
import OptionsFlow from './pages/options/OptionsFlow'
import VolatilitySurface from './pages/options/VolatilitySurface'
import GreeksMonitor from './pages/options/GreeksMonitor'
import SimpleAlpacaData from './components/SimpleAlpacaData'
import CryptoMarketOverview from './pages/CryptoMarketOverview'
import CryptoAdvancedDashboard from './pages/CryptoAdvancedDashboard'
import LiveData from './pages/LiveData'
import LiveDataTailwind from './pages/LiveDataTailwind'
import UnifiedDataManagement from './pages/UnifiedDataManagement'
import SystemHealthMonitor from './components/SystemHealthMonitor'

function App() {
  const [authModalOpen, setAuthModalOpen] = useState(false)
  const { isAuthenticated, user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  
  // Check if Cognito is misconfigured
  const cognitoConfig = window.__CONFIG__?.COGNITO;
  const isCognitoMisconfigured = !cognitoConfig?.USER_POOL_ID || 
                                cognitoConfig.USER_POOL_ID.includes('MISSING') ||
                                cognitoConfig.CLIENT_ID.includes('missing');
  
  // Show auth fallback if Cognito is broken and user not authenticated
  if (isCognitoMisconfigured && !isAuthenticated) {
    return <AuthFallback onLogin={(user) => {
      // This would trigger the auth context to update
      window.location.reload();
    }} />;
  }

  const handleLogout = async () => {
    await logout()
  }

  const handleNotificationClick = () => {
    // Handle notifications
    console.log('Notifications clicked');
  }

  const handleProfileClick = () => {
    navigate('/settings');
  }

  const headerChildren = (
    <div className="flex items-center space-x-4">
      <SystemHealthMonitor compact={true} showDetails={false} />
      {!isAuthenticated && (
        <button
          onClick={() => setAuthModalOpen(true)}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white focus:outline-none focus:ring-2 focus:ring-offset-2"
          style={{ backgroundColor: '#3b82f6' }}
          onMouseEnter={(e) => e.target.style.backgroundColor = '#2563eb'}
          onMouseLeave={(e) => e.target.style.backgroundColor = '#3b82f6'}
        >
          Sign In
        </button>
      )}
    </div>
  );

  return (
    <AppLayout
      headerTitle="Financial Platform"
      user={user}
      notifications={0}
      onNotificationClick={handleNotificationClick}
      onProfileClick={handleProfileClick}
      showSearch={true}
      headerChildren={headerChildren}
    >
      <div className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/portfolio/trade-history" element={<TradeHistory />} />
          <Route path="/portfolio/performance" element={<PortfolioPerformance />} />
          <Route path="/portfolio/optimize" element={<PortfolioOptimization />} />
          <Route path="/market" element={<MarketOverview />} />
          <Route path="/screener-advanced" element={<AdvancedScreener />} />
          <Route path="/scores" element={<ScoresDashboard />} />
          <Route path="/sentiment" element={<SentimentAnalysis />} />
          <Route path="/economic" element={<EconomicModeling />} />
          <Route path="/metrics" element={<MetricsDashboard />} />
          <Route path="/stocks" element={<StockExplorer />} />
          <Route path="/stocks/:ticker" element={<StockDetail />} />
          <Route path="/screener" element={<StockExplorer />} />
          <Route path="/trading" element={<TradingSignals />} />
          <Route path="/technical" element={<TechnicalAnalysis />} />
          <Route path="/analysts" element={<AnalystInsights />} />
          <Route path="/earnings" element={<EarningsCalendar />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/financial-data" element={<FinancialData />} />
          <Route path="/service-health" element={<ServiceHealth />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/test-api" element={<TestApiPage />} />
          <Route path="/portfolio/performance-simple" element={<PortfolioPerformanceSimple />} />
          <Route path="/portfolio/performance-debug" element={<PortfolioPerformanceDebug />} />
          <Route path="/auth-test" element={<AuthTest />} />
          <Route path="/technical-history/:symbol" element={<TechnicalHistory />} />
          
          {/* Sector Analysis */}
          <Route path="/sectors" element={<SectorAnalysis />} />
          <Route path="/commodities" element={<Commodities />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/sentiment/social" element={<SocialMediaSentiment />} />
          <Route path="/sentiment/news" element={<NewsSentiment />} />
          <Route path="/sentiment/analysts" element={<AnalystInsights />} />
          <Route path="/research/commentary" element={<MarketCommentary />} />
          <Route path="/research/education" element={<EducationalContent />} />
          <Route path="/research/reports" element={<AnalystInsights />} />
          <Route path="/stocks/patterns" element={<PatternRecognition />} />
          <Route path="/tools/ai" element={<AIAssistant />} />
          
          {/* Options Trading Routes */}
          <Route path="/options" element={<OptionsAnalytics />} />
          <Route path="/options/strategies" element={<OptionsStrategies />} />
          <Route path="/options/flow" element={<OptionsFlow />} />
          <Route path="/options/volatility" element={<VolatilitySurface />} />
          <Route path="/options/greeks" element={<GreeksMonitor />} />
          
          {/* Data Management Routes */}
          <Route path="/data-management" element={<UnifiedDataManagement />} />
          <Route path="/live-data" element={<LiveDataTailwind />} />
          <Route path="/live-data-mui" element={<LiveData />} />
          
          {/* Cryptocurrency Routes */}
          <Route path="/crypto" element={<CryptoMarketOverview />} />
          <Route path="/crypto/advanced" element={<CryptoAdvancedDashboard />} />
        </Routes>
      </div>
      
      {/* Authentication Modal */}
      <AuthModal
        open={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
      />
    </AppLayout>
  )
}

export default App