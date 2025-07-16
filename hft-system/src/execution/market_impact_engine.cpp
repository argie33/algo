/**
 * Market Impact and Slippage Analysis Engine
 * Implements real-time market impact prediction and transaction cost analysis
 * Based on academic models: Almgren-Chriss, Kyle's Lambda, and machine learning
 */

#include <memory>
#include <atomic>
#include <vector>
#include <unordered_map>
#include <chrono>
#include <cmath>
#include <algorithm>
#include <numeric>
#include <deque>

namespace HFT::Execution {

// Market microstructure data point
struct alignas(64) MarketMicrostructure {
    uint32_t symbol_id;
    uint64_t timestamp_ns;
    
    // Order book metrics
    double bid_price;
    double ask_price;
    double bid_size;
    double ask_size;
    double spread;
    double mid_price;
    
    // Volume metrics
    double volume_10s;          // Volume in last 10 seconds
    double volume_1m;           // Volume in last 1 minute
    double volume_5m;           // Volume in last 5 minutes
    double avg_daily_volume;    // Average daily volume
    
    // Volatility metrics
    double realized_vol_1m;     // 1-minute realized volatility
    double realized_vol_5m;     // 5-minute realized volatility
    
    // Liquidity metrics
    double effective_spread;    // Effective spread from recent trades
    double price_impact_1k;     // Price impact of $1K order
    double price_impact_10k;    // Price impact of $10K order
    double kyle_lambda;         // Kyle's lambda (permanent impact)
    
    // Market regime indicators
    double trend_strength;      // Trending vs mean-reverting
    double volatility_regime;   // High/low volatility regime
    double liquidity_regime;    // High/low liquidity regime
    
    uint8_t padding[8];
};

// Transaction cost components
struct TransactionCost {
    double bid_ask_spread;      // Half-spread cost
    double market_impact;       // Temporary market impact
    double permanent_impact;    // Permanent price impact
    double timing_risk;         // Risk of adverse price movement
    double opportunity_cost;    // Cost of not trading immediately
    double total_cost;          // Total expected cost
};

// Order execution record
struct ExecutionRecord {
    uint64_t order_id;
    uint32_t symbol_id;
    uint64_t timestamp_ns;
    
    double order_size;
    double order_value;
    double benchmark_price;     // Price when order was submitted
    double average_fill_price;  // Volume-weighted average fill price
    double slippage;           // Actual slippage (bps)
    double predicted_impact;    // Predicted market impact
    double actual_impact;      // Actual market impact
    
    uint32_t fill_count;       // Number of fills
    uint64_t total_fill_time_ms; // Total time to complete
    
    bool is_aggressive;        // Market order vs limit order
    bool crossed_spread;       // Whether order crossed bid-ask spread
};

// Kyle's Lambda calculator (permanent market impact)
class KyleLambdaCalculator {
private:
    struct TradeData {
        double price_change;
        double signed_volume;   // Positive for buys, negative for sells
        uint64_t timestamp_ns;
    };
    
    std::unordered_map<uint32_t, std::deque<TradeData>> trade_history_;
    std::unordered_map<uint32_t, double> cached_lambda_;
    std::unordered_map<uint32_t, uint64_t> cache_timestamp_;
    
    static constexpr size_t MAX_TRADE_HISTORY = 1000;
    static constexpr uint64_t CACHE_LIFETIME_NS = 60000000000ULL; // 60 seconds
    
public:
    // Add trade observation
    void addTrade(uint32_t symbol_id, double price_change, double signed_volume) {
        auto& history = trade_history_[symbol_id];
        
        TradeData trade;
        trade.price_change = price_change;
        trade.signed_volume = signed_volume;
        trade.timestamp_ns = getCurrentTimeNs();
        
        history.push_back(trade);
        
        // Keep only recent history
        if (history.size() > MAX_TRADE_HISTORY) {
            history.pop_front();
        }
        
        // Invalidate cache
        cache_timestamp_[symbol_id] = 0;
    }
    
    // Calculate Kyle's lambda (price impact per unit volume)
    double calculateLambda(uint32_t symbol_id) {
        // Check cache
        uint64_t current_time = getCurrentTimeNs();
        if (current_time - cache_timestamp_[symbol_id] < CACHE_LIFETIME_NS) {
            return cached_lambda_[symbol_id];
        }
        
        auto& history = trade_history_[symbol_id];
        if (history.size() < 50) {
            return 0.0; // Insufficient data
        }
        
        // Calculate regression: price_change = lambda * signed_volume + epsilon
        double sum_volume = 0.0;
        double sum_price_change = 0.0;
        double sum_volume_sq = 0.0;
        double sum_volume_price = 0.0;
        
        for (const auto& trade : history) {
            sum_volume += trade.signed_volume;
            sum_price_change += trade.price_change;
            sum_volume_sq += trade.signed_volume * trade.signed_volume;
            sum_volume_price += trade.signed_volume * trade.price_change;
        }
        
        size_t n = history.size();
        double mean_volume = sum_volume / n;
        double mean_price_change = sum_price_change / n;
        
        // Calculate lambda using least squares
        double numerator = sum_volume_price - n * mean_volume * mean_price_change;
        double denominator = sum_volume_sq - n * mean_volume * mean_volume;
        
        double lambda = (denominator != 0.0) ? numerator / denominator : 0.0;
        
        // Cache result
        cached_lambda_[symbol_id] = lambda;
        cache_timestamp_[symbol_id] = current_time;
        
        return lambda;
    }
    
private:
    uint64_t getCurrentTimeNs() const {
        return std::chrono::high_resolution_clock::now().time_since_epoch().count();
    }
};

// Almgren-Chriss optimal execution model
class AlmgrenChrissModel {
private:
    struct ModelParameters {
        double sigma;           // Volatility
        double gamma;           // Risk aversion parameter
        double eta;             // Temporary impact parameter
        double epsilon;         // Permanent impact parameter
        double tau;             // Trading horizon
    };
    
    std::unordered_map<uint32_t, ModelParameters> symbol_params_;
    
public:
    // Calibrate model parameters for a symbol
    void calibrateSymbol(uint32_t symbol_id, 
                        const std::vector<ExecutionRecord>& execution_history,
                        double risk_aversion = 1e-6) {
        if (execution_history.size() < 20) {
            return; // Insufficient data
        }
        
        ModelParameters params{};
        
        // Estimate volatility from price changes
        std::vector<double> returns;
        for (size_t i = 1; i < execution_history.size(); ++i) {
            double ret = (execution_history[i].benchmark_price - 
                         execution_history[i-1].benchmark_price) / 
                         execution_history[i-1].benchmark_price;
            returns.push_back(ret);
        }
        
        double mean_return = std::accumulate(returns.begin(), returns.end(), 0.0) / returns.size();
        double variance = 0.0;
        for (double ret : returns) {
            variance += (ret - mean_return) * (ret - mean_return);
        }
        params.sigma = std::sqrt(variance / returns.size()) * std::sqrt(252 * 24 * 60); // Annualized
        
        // Estimate temporary impact parameter
        double sum_temp_impact = 0.0;
        double sum_volume_sq = 0.0;
        for (const auto& record : execution_history) {
            if (record.is_aggressive) {
                double temp_impact = std::abs(record.slippage) / 10000.0; // Convert bps to decimal
                double volume_rate = record.order_size / (record.total_fill_time_ms / 1000.0);
                sum_temp_impact += temp_impact;
                sum_volume_sq += volume_rate * volume_rate;
            }
        }
        params.eta = (sum_volume_sq > 0) ? sum_temp_impact / sum_volume_sq : 1e-6;
        
        // Estimate permanent impact parameter (simplified)
        params.epsilon = params.eta * 0.1; // Typically 10% of temporary impact
        
        params.gamma = risk_aversion;
        params.tau = 300.0; // 5 minutes default trading horizon
        
        symbol_params_[symbol_id] = params;
    }
    
    // Calculate optimal trading trajectory
    std::vector<double> calculateOptimalTrajectory(uint32_t symbol_id, 
                                                  double total_shares,
                                                  double time_horizon_seconds,
                                                  int num_intervals = 10) {
        auto it = symbol_params_.find(symbol_id);
        if (it == symbol_params_.end()) {
            // Default uniform execution
            std::vector<double> uniform(num_intervals, total_shares / num_intervals);
            return uniform;
        }
        
        const auto& params = it->second;
        double T = time_horizon_seconds;
        double dt = T / num_intervals;
        
        // Almgren-Chriss optimal execution rate
        double kappa = std::sqrt(params.gamma * params.sigma * params.sigma / params.eta);
        double sinh_term = std::sinh(kappa * T);
        double cosh_term = std::cosh(kappa * T);
        
        std::vector<double> trajectory(num_intervals);
        
        for (int i = 0; i < num_intervals; ++i) {
            double t = i * dt;
            double remaining_time = T - t;
            
            // Optimal shares to trade in this interval
            double optimal_rate = total_shares * kappa * 
                                 std::sinh(kappa * remaining_time) / sinh_term;
            
            trajectory[i] = optimal_rate * dt;
        }
        
        return trajectory;
    }
    
    // Calculate expected transaction costs
    TransactionCost calculateExpectedCost(uint32_t symbol_id,
                                        double shares,
                                        double time_horizon_seconds,
                                        const MarketMicrostructure& market_data) {
        TransactionCost cost{};
        
        // Bid-ask spread cost
        cost.bid_ask_spread = market_data.spread * 0.5 * std::abs(shares);
        
        auto it = symbol_params_.find(symbol_id);
        if (it == symbol_params_.end()) {
            // Use simple estimates
            cost.market_impact = market_data.price_impact_10k * (std::abs(shares) / 10000.0);
            cost.permanent_impact = cost.market_impact * 0.3;
            cost.timing_risk = market_data.realized_vol_1m * std::abs(shares) * 
                              std::sqrt(time_horizon_seconds / 60.0);
            cost.opportunity_cost = 0.0;
        } else {
            const auto& params = it->second;
            
            // Calculate Almgren-Chriss costs
            double X = std::abs(shares);
            double T = time_horizon_seconds;
            
            // Permanent impact cost
            cost.permanent_impact = params.epsilon * X;
            
            // Temporary impact cost (depends on execution strategy)
            double kappa = std::sqrt(params.gamma * params.sigma * params.sigma / params.eta);
            double temp_factor = (kappa * T) / std::tanh(kappa * T);
            cost.market_impact = params.eta * X * X * temp_factor / T;
            
            // Timing risk (volatility cost)
            cost.timing_risk = 0.5 * params.gamma * params.sigma * params.sigma * X * X * T;
            
            // Opportunity cost (cost of waiting)
            cost.opportunity_cost = market_data.trend_strength * std::abs(shares) * 
                                   (time_horizon_seconds / 3600.0); // Hourly drift
        }
        
        cost.total_cost = cost.bid_ask_spread + cost.market_impact + 
                         cost.permanent_impact + cost.timing_risk + cost.opportunity_cost;
        
        return cost;
    }
};

// Machine learning-based impact predictor
class MLImpactPredictor {
private:
    struct FeatureVector {
        // Order characteristics
        double order_size_pct;      // Order size as % of daily volume
        double order_value;         // Dollar value of order
        double urgency_score;       // How urgent the order is
        
        // Market characteristics
        double spread_bps;          // Bid-ask spread in basis points
        double volume_rate;         // Current volume rate vs average
        double volatility_percentile; // Current vol vs historical
        double liquidity_score;     // Overall liquidity score
        
        // Microstructure features
        double kyle_lambda;
        double effective_spread;
        double price_impact_curve; // Shape of impact curve
        double order_book_imbalance;
        
        // Time features
        double time_of_day;        // Normalized time of day
        double day_of_week;        // Day of week effect
        double time_to_close;      // Time until market close
        
        // Regime features
        double trend_strength;
        double volatility_regime;
        double market_stress;      // Overall market stress indicator
    };
    
    struct PredictionModel {
        std::vector<double> weights;
        double bias;
        double r_squared;
        uint64_t last_training_time;
    };
    
    std::unordered_map<uint32_t, PredictionModel> symbol_models_;
    std::vector<ExecutionRecord> training_data_;
    
    static constexpr size_t MAX_TRAINING_DATA = 10000;
    static constexpr uint64_t RETRAIN_INTERVAL_NS = 3600000000000ULL; // 1 hour
    
public:
    // Add execution record for training
    void addExecutionRecord(const ExecutionRecord& record) {
        training_data_.push_back(record);
        
        // Keep only recent data
        if (training_data_.size() > MAX_TRAINING_DATA) {
            training_data_.erase(training_data_.begin());
        }
        
        // Retrain models periodically
        uint64_t current_time = getCurrentTimeNs();
        auto& model = symbol_models_[record.symbol_id];
        if (current_time - model.last_training_time > RETRAIN_INTERVAL_NS) {
            trainModel(record.symbol_id);
        }
    }
    
    // Predict market impact for an order
    double predictImpact(uint32_t symbol_id,
                        double order_size,
                        const MarketMicrostructure& market_data) {
        auto it = symbol_models_.find(symbol_id);
        if (it == symbol_models_.end() || it->second.weights.empty()) {
            // Use simple baseline model
            return market_data.price_impact_10k * (order_size / 10000.0);
        }
        
        // Extract features
        FeatureVector features = extractFeatures(order_size, market_data);
        
        // Make prediction using trained model
        const auto& model = it->second;
        double prediction = model.bias;
        
        const double* feature_data = reinterpret_cast<const double*>(&features);
        size_t num_features = sizeof(FeatureVector) / sizeof(double);
        
        for (size_t i = 0; i < std::min(num_features, model.weights.size()); ++i) {
            prediction += model.weights[i] * feature_data[i];
        }
        
        // Apply bounds to prevent unrealistic predictions
        double max_impact = market_data.spread * 5.0; // Max 5x spread
        return std::max(0.0, std::min(prediction, max_impact));
    }
    
    // Get model quality metrics
    double getModelQuality(uint32_t symbol_id) const {
        auto it = symbol_models_.find(symbol_id);
        return (it != symbol_models_.end()) ? it->second.r_squared : 0.0;
    }
    
private:
    FeatureVector extractFeatures(double order_size, 
                                 const MarketMicrostructure& market_data) {
        FeatureVector features{};
        
        // Order characteristics
        features.order_size_pct = order_size / market_data.avg_daily_volume;
        features.order_value = order_size * market_data.mid_price;
        features.urgency_score = 1.0; // Default urgency
        
        // Market characteristics
        features.spread_bps = market_data.spread / market_data.mid_price * 10000.0;
        features.volume_rate = market_data.volume_1m / (market_data.avg_daily_volume / (6.5 * 60));
        features.volatility_percentile = 0.5; // Simplified
        features.liquidity_score = 1.0 / (market_data.spread / market_data.mid_price);
        
        // Microstructure features
        features.kyle_lambda = market_data.kyle_lambda;
        features.effective_spread = market_data.effective_spread;
        features.price_impact_curve = market_data.price_impact_10k / market_data.price_impact_1k;
        features.order_book_imbalance = (market_data.bid_size - market_data.ask_size) / 
                                       (market_data.bid_size + market_data.ask_size);
        
        // Time features (simplified)
        auto now = std::chrono::system_clock::now();
        auto time_t = std::chrono::system_clock::to_time_t(now);
        auto tm = *std::localtime(&time_t);
        features.time_of_day = (tm.tm_hour * 60 + tm.tm_min) / (24.0 * 60.0);
        features.day_of_week = tm.tm_wday / 7.0;
        features.time_to_close = 1.0; // Simplified
        
        // Regime features
        features.trend_strength = market_data.trend_strength;
        features.volatility_regime = market_data.volatility_regime;
        features.market_stress = 0.5; // Simplified
        
        return features;
    }
    
    void trainModel(uint32_t symbol_id) {
        // Filter training data for this symbol
        std::vector<ExecutionRecord> symbol_data;
        std::copy_if(training_data_.begin(), training_data_.end(),
                    std::back_inserter(symbol_data),
                    [symbol_id](const ExecutionRecord& record) {
                        return record.symbol_id == symbol_id;
                    });
        
        if (symbol_data.size() < 100) {
            return; // Insufficient data
        }
        
        // Simplified linear regression training
        // In production, would use more sophisticated ML algorithms
        
        auto& model = symbol_models_[symbol_id];
        size_t num_features = sizeof(FeatureVector) / sizeof(double);
        model.weights.resize(num_features, 0.0);
        model.bias = 0.0;
        
        // Simple gradient descent training (placeholder)
        double learning_rate = 0.001;
        int epochs = 100;
        
        for (int epoch = 0; epoch < epochs; ++epoch) {
            double total_error = 0.0;
            
            for (const auto& record : symbol_data) {
                // Extract features (would need market data at time of record)
                // Simplified training loop
                double prediction = model.bias; // Simplified
                double target = record.actual_impact;
                double error = prediction - target;
                
                // Update weights (simplified)
                model.bias -= learning_rate * error;
                total_error += error * error;
            }
            
            if (total_error < 1e-6) break; // Convergence
        }
        
        // Calculate R-squared (simplified)
        model.r_squared = 0.5; // Placeholder
        model.last_training_time = getCurrentTimeNs();
    }
    
    uint64_t getCurrentTimeNs() const {
        return std::chrono::high_resolution_clock::now().time_since_epoch().count();
    }
};

// Main market impact engine
class MarketImpactEngine {
private:
    KyleLambdaCalculator kyle_calculator_;
    AlmgrenChrissModel almgren_chriss_;
    MLImpactPredictor ml_predictor_;
    
    // Real-time market data cache
    std::unordered_map<uint32_t, MarketMicrostructure> market_data_;
    mutable std::shared_mutex data_mutex_;
    
    // Execution tracking
    std::vector<ExecutionRecord> execution_history_;
    std::atomic<uint64_t> total_executions_{0};
    std::atomic<double> average_slippage_bps_{0.0};
    
public:
    // Update market microstructure data
    void updateMarketData(uint32_t symbol_id, const MarketMicrostructure& data) {
        std::unique_lock<std::shared_mutex> lock(data_mutex_);
        market_data_[symbol_id] = data;
        
        // Update Kyle's lambda
        // This would be called when we observe trades
        // kyle_calculator_.addTrade(symbol_id, price_change, signed_volume);
    }
    
    // Predict market impact for an order
    double predictMarketImpact(uint32_t symbol_id, double order_size, 
                              bool is_aggressive = true) {
        std::shared_lock<std::shared_mutex> lock(data_mutex_);
        
        auto it = market_data_.find(symbol_id);
        if (it == market_data_.end()) {
            return 0.0; // No data available
        }
        
        const auto& market_data = it->second;
        
        // Get predictions from different models
        double ml_prediction = ml_predictor_.predictImpact(symbol_id, order_size, market_data);
        
        // Kyle's lambda prediction
        double kyle_lambda = kyle_calculator_.calculateLambda(symbol_id);
        double kyle_prediction = kyle_lambda * std::abs(order_size);
        
        // Simple square-root model
        double sqrt_prediction = market_data.price_impact_1k * 
                                std::sqrt(std::abs(order_size) / 1000.0);
        
        // Weighted ensemble prediction
        double weight_ml = 0.5;
        double weight_kyle = 0.3;
        double weight_sqrt = 0.2;
        
        double ensemble_prediction = weight_ml * ml_prediction +
                                   weight_kyle * kyle_prediction +
                                   weight_sqrt * sqrt_prediction;
        
        // Apply urgency multiplier for aggressive orders
        if (is_aggressive) {
            ensemble_prediction *= 1.5;
        }
        
        return ensemble_prediction;
    }
    
    // Calculate optimal execution strategy
    std::vector<double> calculateOptimalExecution(uint32_t symbol_id,
                                                 double total_shares,
                                                 double time_horizon_seconds,
                                                 double risk_aversion = 1e-6) {
        return almgren_chriss_.calculateOptimalTrajectory(symbol_id, total_shares, 
                                                         time_horizon_seconds);
    }
    
    // Calculate comprehensive transaction costs
    TransactionCost calculateTransactionCost(uint32_t symbol_id,
                                           double shares,
                                           double time_horizon_seconds) {
        std::shared_lock<std::shared_mutex> lock(data_mutex_);
        
        auto it = market_data_.find(symbol_id);
        if (it == market_data_.end()) {
            return TransactionCost{}; // No data available
        }
        
        return almgren_chriss_.calculateExpectedCost(symbol_id, shares, 
                                                    time_horizon_seconds, it->second);
    }
    
    // Record execution for model training
    void recordExecution(const ExecutionRecord& record) {
        execution_history_.push_back(record);
        
        // Keep only recent history
        if (execution_history_.size() > 10000) {
            execution_history_.erase(execution_history_.begin());
        }
        
        // Update statistics
        total_executions_.fetch_add(1);
        
        // Update running average slippage
        double current_avg = average_slippage_bps_.load();
        double new_avg = (current_avg * (total_executions_.load() - 1) + record.slippage) / 
                        total_executions_.load();
        average_slippage_bps_.store(new_avg);
        
        // Train models
        ml_predictor_.addExecutionRecord(record);
        almgren_chriss_.calibrateSymbol(record.symbol_id, execution_history_);
    }
    
    // Get performance metrics
    struct PerformanceMetrics {
        uint64_t total_executions;
        double average_slippage_bps;
        double prediction_accuracy;
        double cost_savings_estimate;
    };
    
    PerformanceMetrics getPerformanceMetrics() const {
        PerformanceMetrics metrics{};
        metrics.total_executions = total_executions_.load();
        metrics.average_slippage_bps = average_slippage_bps_.load();
        
        // Calculate prediction accuracy
        if (execution_history_.size() > 10) {
            double total_error = 0.0;
            int valid_predictions = 0;
            
            for (const auto& record : execution_history_) {
                if (record.predicted_impact > 0 && record.actual_impact > 0) {
                    double error = std::abs(record.predicted_impact - record.actual_impact) / 
                                  record.actual_impact;
                    total_error += error;
                    valid_predictions++;
                }
            }
            
            if (valid_predictions > 0) {
                metrics.prediction_accuracy = 1.0 - (total_error / valid_predictions);
            }
        }
        
        // Estimate cost savings (simplified)
        metrics.cost_savings_estimate = metrics.prediction_accuracy * 0.25; // 25 bps max savings
        
        return metrics;
    }
};

} // namespace HFT::Execution