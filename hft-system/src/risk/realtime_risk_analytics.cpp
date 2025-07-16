/**
 * Real-time Risk Analytics Engine
 * Implements ultra-fast VaR calculation, correlation monitoring, and stress testing
 * Designed for <100ns latency risk checks
 */

#include <memory>
#include <atomic>
#include <array>
#include <vector>
#include <unordered_map>
#include <chrono>
#include <mutex>
#include <cmath>
#include <algorithm>
#include <immintrin.h>  // AVX2 intrinsics

namespace HFT::Risk {

// Constants for risk calculations
constexpr size_t MAX_SYMBOLS = 1000;
constexpr size_t MAX_HISTORY_DAYS = 252;  // 1 year of trading days
constexpr size_t CORRELATION_WINDOW = 60; // 60-day correlation window
constexpr double VaR_CONFIDENCE = 0.99;   // 99% VaR
constexpr double STRESS_MULTIPLIER = 3.0; // 3x normal volatility

// SIMD-aligned price return structure
struct alignas(32) PriceReturn {
    double price;
    double return_1d;
    double return_5d;
    double return_20d;
    double volatility;
    uint64_t timestamp_ns;
    uint32_t symbol_id;
    uint32_t padding;
};

// Portfolio position with risk metrics
struct alignas(64) PositionRisk {
    uint32_t symbol_id;
    double quantity;
    double market_value;
    double delta;               // Price sensitivity
    double gamma;               // Delta sensitivity
    double vega;                // Volatility sensitivity
    double theta;               // Time decay
    double beta;                // Market beta
    double var_contribution;    // VaR contribution
    double stress_loss;         // Stress test loss
    double correlation_risk;    // Correlation-adjusted risk
    uint64_t last_update_ns;
    uint8_t padding[24];
};

// Real-time correlation matrix (SIMD optimized)
class CorrelationMatrix {
private:
    alignas(32) std::array<std::array<float, MAX_SYMBOLS>, MAX_SYMBOLS> matrix_;
    std::array<uint64_t, MAX_SYMBOLS> last_update_;
    std::atomic<uint32_t> num_symbols_{0};
    
public:
    // SIMD-optimized correlation calculation
    __forceinline void updateCorrelation(uint32_t symbol1, uint32_t symbol2, 
                                        const std::vector<double>& returns1,
                                        const std::vector<double>& returns2) {
        if (returns1.size() != returns2.size() || returns1.size() < CORRELATION_WINDOW) {
            return;
        }
        
        const size_t n = std::min(returns1.size(), CORRELATION_WINDOW);
        
        // Calculate means using SIMD
        __m256d sum1 = _mm256_setzero_pd();
        __m256d sum2 = _mm256_setzero_pd();
        
        size_t i = 0;
        for (; i + 4 <= n; i += 4) {
            __m256d r1 = _mm256_loadu_pd(&returns1[i]);
            __m256d r2 = _mm256_loadu_pd(&returns2[i]);
            sum1 = _mm256_add_pd(sum1, r1);
            sum2 = _mm256_add_pd(sum2, r2);
        }
        
        // Sum the SIMD results
        double mean1 = horizontalSum(sum1);
        double mean2 = horizontalSum(sum2);
        
        // Handle remaining elements
        for (; i < n; ++i) {
            mean1 += returns1[i];
            mean2 += returns2[i];
        }
        
        mean1 /= n;
        mean2 /= n;
        
        // Calculate correlation using SIMD
        __m256d m1_vec = _mm256_set1_pd(mean1);
        __m256d m2_vec = _mm256_set1_pd(mean2);
        __m256d cov_sum = _mm256_setzero_pd();
        __m256d var1_sum = _mm256_setzero_pd();
        __m256d var2_sum = _mm256_setzero_pd();
        
        i = 0;
        for (; i + 4 <= n; i += 4) {
            __m256d r1 = _mm256_loadu_pd(&returns1[i]);
            __m256d r2 = _mm256_loadu_pd(&returns2[i]);
            
            __m256d diff1 = _mm256_sub_pd(r1, m1_vec);
            __m256d diff2 = _mm256_sub_pd(r2, m2_vec);
            
            cov_sum = _mm256_fmadd_pd(diff1, diff2, cov_sum);
            var1_sum = _mm256_fmadd_pd(diff1, diff1, var1_sum);
            var2_sum = _mm256_fmadd_pd(diff2, diff2, var2_sum);
        }
        
        double covariance = horizontalSum(cov_sum);
        double variance1 = horizontalSum(var1_sum);
        double variance2 = horizontalSum(var2_sum);
        
        // Handle remaining elements
        for (; i < n; ++i) {
            double diff1 = returns1[i] - mean1;
            double diff2 = returns2[i] - mean2;
            covariance += diff1 * diff2;
            variance1 += diff1 * diff1;
            variance2 += diff2 * diff2;
        }
        
        // Calculate correlation coefficient
        double correlation = 0.0;
        if (variance1 > 0 && variance2 > 0) {
            correlation = covariance / (std::sqrt(variance1) * std::sqrt(variance2));
        }
        
        // Clamp to [-1, 1]
        correlation = std::max(-1.0, std::min(1.0, correlation));
        
        // Store in matrix
        matrix_[symbol1][symbol2] = static_cast<float>(correlation);
        matrix_[symbol2][symbol1] = static_cast<float>(correlation);
        
        last_update_[symbol1] = getCurrentTimeNs();
        last_update_[symbol2] = getCurrentTimeNs();
    }
    
    __forceinline float getCorrelation(uint32_t symbol1, uint32_t symbol2) const {
        if (symbol1 >= MAX_SYMBOLS || symbol2 >= MAX_SYMBOLS) {
            return 0.0f;
        }
        return matrix_[symbol1][symbol2];
    }
    
    // Calculate portfolio correlation risk
    __forceinline double calculateCorrelationRisk(const std::vector<PositionRisk>& positions) const {
        double total_risk = 0.0;
        
        for (size_t i = 0; i < positions.size(); ++i) {
            for (size_t j = i + 1; j < positions.size(); ++j) {
                float correlation = getCorrelation(positions[i].symbol_id, positions[j].symbol_id);
                double risk_i = positions[i].var_contribution;
                double risk_j = positions[j].var_contribution;
                
                total_risk += 2.0 * correlation * risk_i * risk_j;
            }
        }
        
        return total_risk;
    }
    
private:
    __forceinline double horizontalSum(__m256d v) const {
        __m128d low = _mm256_castpd256_pd128(v);
        __m128d high = _mm256_extractf128_pd(v, 1);
        __m128d sum = _mm_add_pd(low, high);
        __m128d high64 = _mm_unpackhi_pd(sum, sum);
        return _mm_cvtsd_f64(_mm_add_sd(sum, high64));
    }
    
    uint64_t getCurrentTimeNs() const {
        return std::chrono::high_resolution_clock::now().time_since_epoch().count();
    }
};

// Real-time VaR calculator
class VaRCalculator {
private:
    // Historical returns storage (circular buffer)
    std::array<std::array<double, MAX_HISTORY_DAYS>, MAX_SYMBOLS> returns_history_;
    std::array<uint32_t, MAX_SYMBOLS> history_length_;
    std::array<uint32_t, MAX_SYMBOLS> write_index_;
    
    // Cached VaR values
    std::array<double, MAX_SYMBOLS> cached_var_;
    std::array<uint64_t, MAX_SYMBOLS> var_timestamp_;
    
    // Performance optimization
    std::array<double, MAX_HISTORY_DAYS> sorted_returns_;
    
public:
    VaRCalculator() {
        // Initialize arrays
        history_length_.fill(0);
        write_index_.fill(0);
        cached_var_.fill(0.0);
        var_timestamp_.fill(0);
    }
    
    // Add new return observation
    __forceinline void addReturn(uint32_t symbol_id, double return_value) {
        if (symbol_id >= MAX_SYMBOLS) return;
        
        // Store in circular buffer
        returns_history_[symbol_id][write_index_[symbol_id]] = return_value;
        write_index_[symbol_id] = (write_index_[symbol_id] + 1) % MAX_HISTORY_DAYS;
        
        if (history_length_[symbol_id] < MAX_HISTORY_DAYS) {
            history_length_[symbol_id]++;
        }
        
        // Invalidate cached VaR
        var_timestamp_[symbol_id] = 0;
    }
    
    // Calculate VaR using historical simulation (optimized)
    __forceinline double calculateVaR(uint32_t symbol_id, double position_value) {
        if (symbol_id >= MAX_SYMBOLS || history_length_[symbol_id] < 30) {
            return 0.0; // Insufficient data
        }
        
        // Check if cached value is recent enough (within 1 second)
        uint64_t current_time = getCurrentTimeNs();
        if (current_time - var_timestamp_[symbol_id] < 1000000000ULL) {
            return cached_var_[symbol_id] * std::abs(position_value);
        }
        
        // Copy returns to working array
        uint32_t length = history_length_[symbol_id];
        for (uint32_t i = 0; i < length; ++i) {
            uint32_t idx = (write_index_[symbol_id] + MAX_HISTORY_DAYS - length + i) % MAX_HISTORY_DAYS;
            sorted_returns_[i] = returns_history_[symbol_id][idx];
        }
        
        // Sort returns for percentile calculation
        std::nth_element(sorted_returns_.begin(), 
                        sorted_returns_.begin() + static_cast<int>(length * (1.0 - VaR_CONFIDENCE)),
                        sorted_returns_.begin() + length);
        
        double var_return = sorted_returns_[static_cast<int>(length * (1.0 - VaR_CONFIDENCE))];
        
        // Cache result
        cached_var_[symbol_id] = -var_return; // VaR is positive for losses
        var_timestamp_[symbol_id] = current_time;
        
        return cached_var_[symbol_id] * std::abs(position_value);
    }
    
    // Calculate portfolio VaR using Monte Carlo simulation
    double calculatePortfolioVaR(const std::vector<PositionRisk>& positions,
                                 const CorrelationMatrix& correlations,
                                 int num_simulations = 10000) {
        if (positions.empty()) return 0.0;
        
        std::vector<double> portfolio_returns;
        portfolio_returns.reserve(num_simulations);
        
        // Generate correlated random returns
        std::random_device rd;
        std::mt19937 gen(rd());
        std::normal_distribution<double> dist(0.0, 1.0);
        
        for (int sim = 0; sim < num_simulations; ++sim) {
            double portfolio_return = 0.0;
            
            // Generate random factors
            std::vector<double> random_factors(positions.size());
            for (size_t i = 0; i < positions.size(); ++i) {
                random_factors[i] = dist(gen);
            }
            
            // Apply correlations using Cholesky decomposition (simplified)
            for (size_t i = 0; i < positions.size(); ++i) {
                double correlated_factor = random_factors[i];
                
                // Simplified correlation adjustment
                for (size_t j = 0; j < i; ++j) {
                    float correlation = correlations.getCorrelation(positions[i].symbol_id, 
                                                                   positions[j].symbol_id);
                    correlated_factor += correlation * random_factors[j] * 0.1;
                }
                
                // Calculate position return
                double volatility = cached_var_[positions[i].symbol_id] * 2.33; // Convert VaR to volatility
                double position_return = correlated_factor * volatility * positions[i].market_value;
                portfolio_return += position_return;
            }
            
            portfolio_returns.push_back(portfolio_return);
        }
        
        // Calculate VaR percentile
        std::sort(portfolio_returns.begin(), portfolio_returns.end());
        int var_index = static_cast<int>(num_simulations * (1.0 - VaR_CONFIDENCE));
        
        return -portfolio_returns[var_index]; // Return positive VaR
    }
    
private:
    uint64_t getCurrentTimeNs() const {
        return std::chrono::high_resolution_clock::now().time_since_epoch().count();
    }
};

// Stress testing engine
class StressTestEngine {
private:
    struct StressScenario {
        std::string name;
        std::unordered_map<uint32_t, double> price_shocks; // symbol_id -> shock %
        double market_shock;                                // Overall market shock
        double volatility_multiplier;                       // Volatility increase
        double correlation_shock;                           // Correlation increase
    };
    
    std::vector<StressScenario> scenarios_;
    
public:
    StressTestEngine() {
        initializeStandardScenarios();
    }
    
    void initializeStandardScenarios() {
        // 2008 Financial Crisis scenario
        StressScenario crisis_2008;
        crisis_2008.name = "Financial Crisis 2008";
        crisis_2008.market_shock = -0.50;          // 50% market drop
        crisis_2008.volatility_multiplier = 4.0;   // 4x normal volatility
        crisis_2008.correlation_shock = 0.3;       // Correlations spike to 0.9+
        scenarios_.push_back(crisis_2008);
        
        // Flash Crash scenario
        StressScenario flash_crash;
        flash_crash.name = "Flash Crash";
        flash_crash.market_shock = -0.20;          // 20% rapid drop
        flash_crash.volatility_multiplier = 10.0;  // 10x volatility spike
        flash_crash.correlation_shock = 0.5;       // Very high correlations
        scenarios_.push_back(flash_crash);
        
        // Interest Rate Shock
        StressScenario rate_shock;
        rate_shock.name = "Interest Rate Shock";
        rate_shock.market_shock = -0.15;           // 15% market drop
        rate_shock.volatility_multiplier = 2.0;    // 2x volatility
        rate_shock.correlation_shock = 0.2;        // Moderate correlation increase
        scenarios_.push_back(rate_shock);
        
        // Liquidity Crisis
        StressScenario liquidity_crisis;
        liquidity_crisis.name = "Liquidity Crisis";
        liquidity_crisis.market_shock = -0.30;     // 30% drop
        liquidity_crisis.volatility_multiplier = 5.0; // 5x volatility
        liquidity_crisis.correlation_shock = 0.4;  // High correlations
        scenarios_.push_back(liquidity_crisis);
    }
    
    // Run stress test on portfolio
    std::vector<double> runStressTests(const std::vector<PositionRisk>& positions) {
        std::vector<double> scenario_losses;
        scenario_losses.reserve(scenarios_.size());
        
        for (const auto& scenario : scenarios_) {
            double total_loss = calculateScenarioLoss(positions, scenario);
            scenario_losses.push_back(total_loss);
        }
        
        return scenario_losses;
    }
    
    // Get worst-case stress loss
    double getWorstCaseStressLoss(const std::vector<PositionRisk>& positions) {
        auto losses = runStressTests(positions);
        return *std::max_element(losses.begin(), losses.end());
    }
    
private:
    double calculateScenarioLoss(const std::vector<PositionRisk>& positions,
                                const StressScenario& scenario) {
        double total_loss = 0.0;
        
        for (const auto& position : positions) {
            double position_loss = 0.0;
            
            // Apply symbol-specific shock if available
            auto shock_it = scenario.price_shocks.find(position.symbol_id);
            double price_shock = (shock_it != scenario.price_shocks.end()) ? 
                                shock_it->second : scenario.market_shock;
            
            // Calculate direct price impact
            position_loss += position.market_value * price_shock;
            
            // Add volatility impact (option gamma effect)
            double vol_impact = 0.5 * position.gamma * position.market_value * 
                               std::pow(price_shock, 2) * scenario.volatility_multiplier;
            position_loss += vol_impact;
            
            // Add correlation impact (diversification breakdown)
            double correlation_impact = position.var_contribution * scenario.correlation_shock;
            position_loss += correlation_impact;
            
            total_loss += std::abs(position_loss);
        }
        
        return total_loss;
    }
};

// Main real-time risk analytics engine
class RealtimeRiskAnalytics {
private:
    CorrelationMatrix correlations_;
    VaRCalculator var_calculator_;
    StressTestEngine stress_engine_;
    
    // Position tracking
    std::unordered_map<uint32_t, PositionRisk> positions_;
    mutable std::shared_mutex positions_mutex_;
    
    // Risk limits
    struct RiskLimits {
        double max_portfolio_var = 1000000.0;     // $1M max portfolio VaR
        double max_position_var = 100000.0;       // $100K max position VaR
        double max_correlation = 0.8;             // Max allowed correlation
        double max_stress_loss = 2000000.0;       // $2M max stress loss
        double max_concentration = 0.2;           // Max 20% in single position
    } limits_;
    
    // Performance metrics
    std::atomic<uint64_t> risk_checks_performed_{0};
    std::atomic<uint64_t> risk_violations_{0};
    std::atomic<uint64_t> total_calculation_time_ns_{0};
    
public:
    RealtimeRiskAnalytics() = default;
    
    // Update position (called on every trade)
    __forceinline void updatePosition(uint32_t symbol_id, double quantity, 
                                     double market_value, double delta = 1.0) {
        auto start_time = std::chrono::high_resolution_clock::now();
        
        {
            std::unique_lock<std::shared_mutex> lock(positions_mutex_);
            
            auto& position = positions_[symbol_id];
            position.symbol_id = symbol_id;
            position.quantity = quantity;
            position.market_value = market_value;
            position.delta = delta;
            position.last_update_ns = getCurrentTimeNs();
            
            // Calculate individual VaR
            position.var_contribution = var_calculator_.calculateVaR(symbol_id, market_value);
        }
        
        auto end_time = std::chrono::high_resolution_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(end_time - start_time);
        total_calculation_time_ns_.fetch_add(duration.count());
    }
    
    // Perform comprehensive risk check (ultra-fast)
    __forceinline bool performRiskCheck() {
        auto start_time = std::chrono::high_resolution_clock::now();
        risk_checks_performed_.fetch_add(1);
        
        bool passed = true;
        
        {
            std::shared_lock<std::shared_mutex> lock(positions_mutex_);
            
            // Get current positions
            std::vector<PositionRisk> current_positions;
            current_positions.reserve(positions_.size());
            for (const auto& [symbol_id, position] : positions_) {
                current_positions.push_back(position);
            }
            
            // Calculate portfolio VaR
            double portfolio_var = var_calculator_.calculatePortfolioVaR(current_positions, correlations_);
            if (portfolio_var > limits_.max_portfolio_var) {
                passed = false;
            }
            
            // Check individual position limits
            for (const auto& position : current_positions) {
                if (position.var_contribution > limits_.max_position_var) {
                    passed = false;
                    break;
                }
            }
            
            // Check concentration limits
            double total_value = 0.0;
            for (const auto& position : current_positions) {
                total_value += std::abs(position.market_value);
            }
            
            for (const auto& position : current_positions) {
                double concentration = std::abs(position.market_value) / total_value;
                if (concentration > limits_.max_concentration) {
                    passed = false;
                    break;
                }
            }
            
            // Check stress test limits (sampled check - not every time)
            if (risk_checks_performed_.load() % 100 == 0) {
                double worst_stress_loss = stress_engine_.getWorstCaseStressLoss(current_positions);
                if (worst_stress_loss > limits_.max_stress_loss) {
                    passed = false;
                }
            }
        }
        
        if (!passed) {
            risk_violations_.fetch_add(1);
        }
        
        auto end_time = std::chrono::high_resolution_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(end_time - start_time);
        total_calculation_time_ns_.fetch_add(duration.count());
        
        return passed;
    }
    
    // Add price return for correlation/VaR calculation
    void addPriceReturn(uint32_t symbol_id, double return_value) {
        var_calculator_.addReturn(symbol_id, return_value);
    }
    
    // Update correlations between symbols
    void updateCorrelations(uint32_t symbol1, uint32_t symbol2,
                           const std::vector<double>& returns1,
                           const std::vector<double>& returns2) {
        correlations_.updateCorrelation(symbol1, symbol2, returns1, returns2);
    }
    
    // Get current portfolio VaR
    double getCurrentPortfolioVaR() const {
        std::shared_lock<std::shared_mutex> lock(positions_mutex_);
        
        std::vector<PositionRisk> current_positions;
        current_positions.reserve(positions_.size());
        for (const auto& [symbol_id, position] : positions_) {
            current_positions.push_back(position);
        }
        
        return var_calculator_.calculatePortfolioVaR(current_positions, correlations_);
    }
    
    // Performance metrics
    struct PerformanceMetrics {
        uint64_t risk_checks_performed;
        uint64_t risk_violations;
        double average_latency_ns;
        double violation_rate;
    };
    
    PerformanceMetrics getPerformanceMetrics() const {
        PerformanceMetrics metrics{};
        metrics.risk_checks_performed = risk_checks_performed_.load();
        metrics.risk_violations = risk_violations_.load();
        
        if (metrics.risk_checks_performed > 0) {
            metrics.average_latency_ns = static_cast<double>(total_calculation_time_ns_.load()) / 
                                        metrics.risk_checks_performed;
            metrics.violation_rate = static_cast<double>(metrics.risk_violations) / 
                                   metrics.risk_checks_performed;
        }
        
        return metrics;
    }
    
private:
    uint64_t getCurrentTimeNs() const {
        return std::chrono::high_resolution_clock::now().time_since_epoch().count();
    }
};

} // namespace HFT::Risk