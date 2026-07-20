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
const PortfolioDashboard = React.lazy(
  () => import("./pages/PortfolioDashboard")
);
const ServiceHealth = React.lazy(() => import("./pages/ServiceHealth"));
const Settings = React.lazy(() => import("./pages/Settings"));
const AlgoTradingDashboard = React.lazy(
  () => import("./pages/AlgoTradingDashboard")
);
const AuditViewer = React.lazy(() => import("./pages/AuditViewer"));
const NotificationCenter = React.lazy(
  () => import("./pages/NotificationCenter")
);
const NotFound = React.lazy(() => import("./pages/NotFound"));
const SystemBlueprint = React.lazy(() => import("./pages/SystemBlueprint"));
const ConfigurationViewer = React.lazy(
  () => import("./pages/ConfigurationViewer")
);
const PreTradeSimulator = React.lazy(
  () => import("./pages/PreTradeSimulator")
);
const RiskAnalytics = React.lazy(() => import("./pages/RiskAnalytics"));
const EarningsCalendar = React.lazy(
  () => import("./pages/EarningsCalendar")
);

import ProtectedRoute from "./components/auth/ProtectedRoute";
import ErrorBoundary from "./components/ErrorBoundary";
import { LoadingFallback } from "./components/LoadingFallback";

// Marketing pages
const Home = React.lazy(() => import("./pages/marketing/Home"));
const Firm = React.lazy(() => import("./pages/marketing/Firm"));
const Contact = React.lazy(() => import("./pages/marketing/Contact"));
const About = React.lazy(() => import("./pages/marketing/About"));
const OurTeam = React.lazy(() => import("./pages/marketing/OurTeam"));
const MissionValues = React.lazy(
  () => import("./pages/marketing/MissionValues")
);
const ResearchInsights = React.lazy(
  () => import("./pages/marketing/ResearchInsights")
);
const ArticleDetail = React.lazy(
  () => import("./pages/marketing/ArticleDetail")
);
const Terms = React.lazy(() => import("./pages/marketing/Terms"));
const Privacy = React.lazy(() => import("./pages/marketing/Privacy"));
const InvestmentTools = React.lazy(
  () => import("./pages/marketing/InvestmentTools")
);
const WealthManagement = React.lazy(
  () => import("./pages/marketing/WealthManagement")
);
const LoginPage = React.lazy(() => import("./pages/LoginPage"));

// Layout component
import AppLayout from "./components/AppLayout";

const LOADING = <LoadingFallback />;

function App() {
  const location = useLocation();
  const isMarketingPage = !location.pathname.startsWith("/app");

  if (isMarketingPage) {
    return (
      <ErrorBoundary>
        <Suspense fallback={LOADING}>
          <Routes>
            {/* Root goes directly to the app */}
            <Route path="/" element={<Navigate to="/app/markets" replace />} />

            {/* Marketing Pages */}
            <Route path="/home" element={<Home />} />
            <Route path="/firm" element={<Firm />} />
            <Route path="/contact" element={<Contact />} />
            <Route path="/about" element={<About />} />
            <Route path="/our-team" element={<OurTeam />} />
            <Route path="/mission-values" element={<MissionValues />} />
            <Route path="/research-insights" element={<ResearchInsights />} />
            <Route path="/articles/:articleId" element={<ArticleDetail />} />
            <Route path="/investment-tools" element={<InvestmentTools />} />
            <Route path="/wealth-management" element={<WealthManagement />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/login" element={<LoginPage />} />

            {/* Legacy route redirects to /app/* equivalents */}
            <Route
              path="/stocks"
              element={<Navigate to="/app/deep-value" replace />}
            />
            <Route
              path="/dashboard"
              element={<Navigate to="/app/markets" replace />}
            />
            <Route
              path="/markets-health"
              element={<Navigate to="/app/markets" replace />}
            />
            <Route
              path="/economic"
              element={<Navigate to="/app/economic" replace />}
            />
            <Route
              path="/signals"
              element={<Navigate to="/app/trading-signals" replace />}
            />
            <Route
              path="/swing-candidates"
              element={<Navigate to="/app/swing" replace />}
            />
            <Route
              path="/sectors"
              element={<Navigate to="/app/sectors" replace />}
            />
            <Route
              path="/sentiment"
              element={<Navigate to="/app/sentiment" replace />}
            />
            <Route
              path="/scores"
              element={<Navigate to="/app/scores" replace />}
            />
            <Route
              path="/portfolio"
              element={<Navigate to="/app/portfolio" replace />}
            />
            <Route
              path="/positions"
              element={<Navigate to="/app/portfolio" replace />}
            />
            <Route
              path="/trades"
              element={<Navigate to="/app/trades" replace />}
            />
            <Route
              path="/health"
              element={<Navigate to="/app/health" replace />}
            />

            <Route
              path="*"
              element={
                <ErrorBoundary>
                  <NotFound />
                </ErrorBoundary>
              }
            />
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
            <Route
              path="/app"
              element={<Navigate to="/app/markets" replace />}
            />

            {/* Markets & Analysis */}
            <Route path="/app/markets" element={<MarketsHealth />} />
            <Route path="/app/economic" element={<EconomicDashboard />} />
            <Route path="/app/sectors" element={<SectorAnalysis />} />
            <Route path="/app/sentiment" element={<Sentiment />} />

            {/* Stocks Analysis & Signals */}
            <Route path="/app/deep-value" element={<DeepValueStocks />} />
            <Route
              path="/app/earnings"
              element={
                <ProtectedRoute requireAuth>
                  <EarningsCalendar />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/trading-signals"
              element={
                <ProtectedRoute requireAuth>
                  <TradingSignals />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/swing"
              element={
                <ProtectedRoute requireAuth>
                  <SwingCandidates />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/scores"
              element={
                <ProtectedRoute requireAuth>
                  <ScoresDashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/stock/:symbol"
              element={
                <ProtectedRoute requireAuth>
                  <StockDetail />
                </ProtectedRoute>
              }
            />

            {/* Portfolio & Trading */}
            <Route
              path="/app/portfolio"
              element={
                <ProtectedRoute requireAuth>
                  <PortfolioDashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/trades"
              element={
                <ProtectedRoute requireAuth>
                  <TradeTracker />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/pre-trade-impact"
              element={
                <ProtectedRoute requireAuth>
                  <PreTradeSimulator />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/risk-analytics"
              element={
                <ProtectedRoute requireAuth>
                  <RiskAnalytics />
                </ProtectedRoute>
              }
            />

            {/* Algo */}
            <Route
              path="/app/algo-dashboard"
              element={
                <ProtectedRoute requireAuth requireRole="admin">
                  <AlgoTradingDashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/backtests"
              element={
                <ProtectedRoute requireAuth>
                  <BacktestResults />
                </ProtectedRoute>
              }
            />

            {/* Admin & Settings */}
            <Route
              path="/app/configuration"
              element={
                <ProtectedRoute requireAuth requireRole="admin">
                  <ConfigurationViewer />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/health"
              element={
                <ProtectedRoute requireAuth requireRole="admin">
                  <ServiceHealth />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/notifications"
              element={
                <ProtectedRoute requireAuth requireRole="admin">
                  <NotificationCenter />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/audit"
              element={
                <ProtectedRoute requireAuth requireRole="admin">
                  <AuditViewer />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/blueprint"
              element={
                <ProtectedRoute requireAuth requireRole="admin">
                  <SystemBlueprint />
                </ProtectedRoute>
              }
            />
            <Route
              path="/app/settings"
              element={
                <ProtectedRoute requireAuth>
                  <Settings />
                </ProtectedRoute>
              }
            />

            <Route
              path="*"
              element={
                <ErrorBoundary>
                  <NotFound />
                </ErrorBoundary>
              }
            />
          </Routes>
        </Suspense>
      </AppLayout>
    </ErrorBoundary>
  );
}

export default App;
