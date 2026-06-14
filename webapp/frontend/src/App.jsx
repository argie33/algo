import React, { Suspense } from "react";
import { Routes, Route, useLocation, Navigate } from "react-router-dom";

// Dashboard pages - Lazy-loaded for code splitting
const MarketsHealth = React.lazy(() => import("./pages/MarketsHealth"));
const StockDetail = React.lazy(() => import("./pages/StockDetail"));
const DeepValueStocks = React.lazy(() => import("./pages/DeepValueStocks"));
const TradingSignals = React.lazy(() => import("./pages/TradingSignals"));
const SwingCandidates = React.lazy(() => import("./pages/SwingCandidates"));
const BacktestResults = React.lazy(() => import("./pages/BacktestResults"));
const EconomicDashboard = React.lazy(() => import("./pages/EconomicDashboard"));
const SectorAnalysis = React.lazy(() => import("./pages/SectorAnalysis"));
const Sentiment = React.lazy(() => import("./pages/Sentiment"));
const ScoresDashboard = React.lazy(() => import("./pages/ScoresDashboard"));
const TradeTracker = React.lazy(() => import("./pages/TradeTracker"));
const PortfolioDashboard = React.lazy(() => import("./pages/PortfolioDashboard"));
const ServiceHealth = React.lazy(() => import("./pages/ServiceHealth"));
const Settings = React.lazy(() => import("./pages/Settings"));
const AlgoTradingDashboard = React.lazy(() => import("./pages/AlgoTradingDashboard"));
const AuditViewer = React.lazy(() => import("./pages/AuditViewer"));
const NotificationCenter = React.lazy(() => import("./pages/NotificationCenter"));
const NotFound = React.lazy(() => import("./pages/NotFound"));
const SystemBlueprint = React.lazy(() => import("./pages/SystemBlueprint"));
const ConfigurationViewer = React.lazy(() => import("./pages/ConfigurationViewer"));
const PreTradeSimulator = React.lazy(() => import("./pages/PreTradeSimulator"));
const RiskAnalytics = React.lazy(() => import("./pages/RiskAnalytics"));
const ExposurePolicy = React.lazy(() => import("./pages/ExposurePolicy"));

import ProtectedRoute from "./components/auth/ProtectedRoute";
import ErrorBoundary from "./components/ErrorBoundary";
import { LoadingFallback } from "./components/LoadingFallback";

// Marketing pages
const Home = React.lazy(() => import("./pages/marketing/Home"));
const Firm = React.lazy(() => import("./pages/marketing/Firm"));
const Contact = React.lazy(() => import("./pages/marketing/Contact"));
const About = React.lazy(() => import("./pages/marketing/About"));
const OurTeam = React.lazy(() => import("./pages/marketing/OurTeam"));
const MissionValues = React.lazy(() => import("./pages/marketing/MissionValues"));
const ResearchInsights = React.lazy(() => import("./pages/marketing/ResearchInsights"));
const ArticleDetail = React.lazy(() => import("./pages/marketing/ArticleDetail"));
const Terms = React.lazy(() => import("./pages/marketing/Terms"));
const Privacy = React.lazy(() => import("./pages/marketing/Privacy"));
const InvestmentTools = React.lazy(() => import("./pages/marketing/InvestmentTools"));
const WealthManagement = React.lazy(() => import("./pages/marketing/WealthManagement"));
const LoginPage = React.lazy(() => import("./pages/LoginPage"));

// Layout component
import AppLayout from "./components/AppLayout";

const LOADING = <LoadingFallback />;

function App() {
  const location = useLocation();
  const isMarketingPage = !location.pathname.startsWith('/app');

  if (isMarketingPage) {
    return (
      <ErrorBoundary>
        <Suspense fallback={LOADING}>
          <Routes>
          {/* Root goes directly to the app */}
          <Route path="/" element={<Navigate to="/app/markets" replace />} />

          {/* Marketing Pages */}
          <Route path="/home" element={<ErrorBoundary><Home /></ErrorBoundary>} />
          <Route path="/firm" element={<ErrorBoundary><Firm /></ErrorBoundary>} />
          <Route path="/contact" element={<ErrorBoundary><Contact /></ErrorBoundary>} />
          <Route path="/about" element={<ErrorBoundary><About /></ErrorBoundary>} />
          <Route path="/our-team" element={<ErrorBoundary><OurTeam /></ErrorBoundary>} />
          <Route path="/mission-values" element={<ErrorBoundary><MissionValues /></ErrorBoundary>} />
          <Route path="/research-insights" element={<ErrorBoundary><ResearchInsights /></ErrorBoundary>} />
          <Route path="/articles/:articleId" element={<ErrorBoundary><ArticleDetail /></ErrorBoundary>} />
          <Route path="/investment-tools" element={<ErrorBoundary><InvestmentTools /></ErrorBoundary>} />
          <Route path="/wealth-management" element={<ErrorBoundary><WealthManagement /></ErrorBoundary>} />
          <Route path="/terms" element={<ErrorBoundary><Terms /></ErrorBoundary>} />
          <Route path="/privacy" element={<ErrorBoundary><Privacy /></ErrorBoundary>} />
          <Route path="/login" element={<ErrorBoundary><LoginPage /></ErrorBoundary>} />

          {/* Legacy route redirects to /app/* equivalents */}
          <Route path="/stocks" element={<Navigate to="/app/deep-value" replace />} />
          <Route path="/dashboard" element={<Navigate to="/app/markets" replace />} />
          <Route path="/markets-health" element={<Navigate to="/app/markets" replace />} />
          <Route path="/economic" element={<Navigate to="/app/economic" replace />} />
          <Route path="/signals" element={<Navigate to="/app/trading-signals" replace />} />
          <Route path="/swing-candidates" element={<Navigate to="/app/swing" replace />} />
          <Route path="/sectors" element={<Navigate to="/app/sectors" replace />} />
          <Route path="/sentiment" element={<Navigate to="/app/sentiment" replace />} />
          <Route path="/scores" element={<Navigate to="/app/scores" replace />} />
          <Route path="/portfolio" element={<Navigate to="/app/portfolio" replace />} />
          <Route path="/positions" element={<Navigate to="/app/portfolio" replace />} />
          <Route path="/trades" element={<Navigate to="/app/trades" replace />} />
          <Route path="/health" element={<Navigate to="/app/health" replace />} />

          <Route path="*" element={<ErrorBoundary><NotFound /></ErrorBoundary>} />
        </Routes>
        </Suspense>
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary>
      <AppLayout>
        <Suspense fallback={LOADING}>
          <Routes>
            {/* Default /app route */}
            <Route path="/app" element={<Navigate to="/app/markets" replace />} />

            {/* Markets & Analysis */}
            <Route path="/app/markets" element={<ErrorBoundary><MarketsHealth /></ErrorBoundary>} />
            <Route path="/app/economic" element={<ErrorBoundary><EconomicDashboard /></ErrorBoundary>} />
            <Route path="/app/sectors" element={<ErrorBoundary><SectorAnalysis /></ErrorBoundary>} />
            <Route path="/app/sentiment" element={<ErrorBoundary><Sentiment /></ErrorBoundary>} />

            {/* Stocks Analysis & Signals */}
            <Route path="/app/deep-value" element={<ErrorBoundary><DeepValueStocks /></ErrorBoundary>} />
            <Route path="/app/trading-signals" element={<ErrorBoundary><ProtectedRoute requireAuth><TradingSignals /></ProtectedRoute></ErrorBoundary>} />
            <Route path="/app/swing" element={<ErrorBoundary><ProtectedRoute requireAuth><SwingCandidates /></ProtectedRoute></ErrorBoundary>} />
            <Route path="/app/scores" element={<ErrorBoundary><ProtectedRoute requireAuth><ScoresDashboard /></ProtectedRoute></ErrorBoundary>} />
            <Route path="/app/stock/:symbol" element={<ErrorBoundary><ProtectedRoute requireAuth><StockDetail /></ProtectedRoute></ErrorBoundary>} />

            {/* Portfolio & Trading */}
            <Route path="/app/portfolio" element={<ErrorBoundary><ProtectedRoute requireAuth><PortfolioDashboard /></ProtectedRoute></ErrorBoundary>} />
            <Route path="/app/trades" element={<ErrorBoundary><ProtectedRoute requireAuth><TradeTracker /></ProtectedRoute></ErrorBoundary>} />
            <Route path="/app/pre-trade-impact" element={<ErrorBoundary><ProtectedRoute requireAuth><PreTradeSimulator /></ProtectedRoute></ErrorBoundary>} />
            <Route path="/app/risk-analytics" element={<ErrorBoundary><ProtectedRoute requireAuth><RiskAnalytics /></ProtectedRoute></ErrorBoundary>} />
            <Route path="/app/exposure-policy" element={<ErrorBoundary><ProtectedRoute requireAuth><ExposurePolicy /></ProtectedRoute></ErrorBoundary>} />

            {/* Algo */}
            <Route path="/app/algo-dashboard" element={<ErrorBoundary><ProtectedRoute requireAuth><AlgoTradingDashboard /></ProtectedRoute></ErrorBoundary>} />
            <Route path="/app/backtests" element={<ErrorBoundary><ProtectedRoute requireAuth><BacktestResults /></ProtectedRoute></ErrorBoundary>} />

            {/* Admin & Settings */}
            <Route path="/app/configuration" element={<ErrorBoundary><ProtectedRoute requireAuth requireRole="admin"><ConfigurationViewer /></ProtectedRoute></ErrorBoundary>} />
            <Route path="/app/health" element={<ErrorBoundary><ProtectedRoute requireAuth requireRole="admin"><ServiceHealth /></ProtectedRoute></ErrorBoundary>} />
            <Route path="/app/notifications" element={<ErrorBoundary><ProtectedRoute requireAuth requireRole="admin"><NotificationCenter /></ProtectedRoute></ErrorBoundary>} />
            <Route path="/app/audit" element={<ErrorBoundary><ProtectedRoute requireAuth requireRole="admin"><AuditViewer /></ProtectedRoute></ErrorBoundary>} />
            <Route path="/app/blueprint" element={<ErrorBoundary><ProtectedRoute requireAuth requireRole="admin"><SystemBlueprint /></ProtectedRoute></ErrorBoundary>} />
            <Route path="/app/settings" element={<ErrorBoundary><ProtectedRoute requireAuth><Settings /></ProtectedRoute></ErrorBoundary>} />

            <Route path="*" element={<ErrorBoundary><NotFound /></ErrorBoundary>} />
          </Routes>
        </Suspense>
      </AppLayout>
    </ErrorBoundary>
  );
}

export default App;
