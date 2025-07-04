/**
 * Mean Reversion Strategy Implementation
 * Trades on the principle that prices revert to their mean
 * Suitable for ranging markets and pairs trading
 */

#include "base_strategy.h"
#include <algorithm>
#include <cmath>
#include <unordered_map>
#include <deque>
#include <numeric>

namespace HFT {

// Mean reversion parameters
struct MeanReversionParams {
    uint32_t lookback_period = 20;         // Period for calculating mean
    double zscore_entry_threshold = 2.0;   // Z-score for entry
    double zscore_exit_threshold = 0.5;    // Z-score for exit
    uint32_t max_position_size = 1500;     // Max shares per position
    double bollinger_band_mult = 2.0;      // Bollinger band multiplier
    double min_volatility = 0.0005;        // Min volatility to trade
    double max_volatility = 0.02;          // Max volatility to trade
    uint64_t max_hold_time_ns = 3600000000000; // 1 hour max hold
    bool use_kalman_filter = true;         // Use Kalman filter for mean
    double mean_reversion_speed = 0.1;     // Speed of mean reversion
    bool trade_pairs = false;              // Enable pairs trading
    double correlation_threshold = 0.8;    // Min correlation for pairs
};

// Trade tracking
struct ReversalTrade {
    uint64_t entry_time_ns;
    uint32_t symbol_id;
    uint32_t pair_symbol_id;  // For pairs trading
    double entry_price;
    double entry_zscore;
    uint32_t quantity;
    int8_t direction;
    double target_price;
    double stop_loss;
    bool is_active;
    bool is_pair_trade;
};

// Statistical data
struct StatisticalData {
    std::deque<double> prices;
    std::deque<double> returns;
    double mean;
    double std_dev;
    double current_zscore;
    double upper_band;
    double lower_band;
    double kalman_mean;
    double kalman_variance;
    uint32_t deviations_count;
    bool mean_reverting;
};

// Pairs trading data
struct PairData {
    uint32_t symbol1_id;
    uint32_t symbol2_id;
    double correlation;
    double hedge_ratio;
    double spread_mean;
    double spread_std;
    std::deque<double> spread_history;
};

class MeanReversionStrategy : public BaseStrategy {
private:
    MeanReversionParams params_;
    
    // Active trades
    std::unordered_map<uint32_t, ReversalTrade> active_trades_;
    
    // Statistical data for each symbol
    std::unordered_map<uint32_t, StatisticalData> statistics_;
    
    // Pairs trading
    std::vector<PairData> trading_pairs_;
    std::unordered_map<uint64_t, double> pair_spreads_; // Key: (sym1_id << 32) | sym2_id
    
    // Mean reversion detection
    std::unordered_map<uint32_t, bool> oversold_signals_;
    std::unordered_map<uint32_t, bool> overbought_signals_;
    
    // Performance tracking
    std::unordered_map<uint32_t, uint32_t> false_signals_;
    double total_zscore_profit_ = 0.0;
    
public:
    MeanReversionStrategy(const StrategyConfig& config) 
        : BaseStrategy(config) {
        loadParameters();
    }
    
    void initialize() override {
        for (uint32_t symbol_id : config_.target_symbols) {
            statistics_[symbol_id] = StatisticalData{};
            statistics_[symbol_id].kalman_mean = 0.0;
            statistics_[symbol_id].kalman_variance = 1.0;
            oversold_signals_[symbol_id] = false;
            overbought_signals_[symbol_id] = false;
            false_signals_[symbol_id] = 0;
        }
        
        // Initialize pairs if enabled
        if (params_.trade_pairs) {
            identifyTradingPairs();
        }
    }
    
    void onMarketData(const MarketDataEvent& event) override {
        if (state_ != StrategyState::RUNNING) return;
        
        uint32_t symbol_id = event.symbol_id;
        
        // Update statistics
        updateStatistics(symbol_id, event.price);
        
        // Check existing positions
        if (hasActivePosition(symbol_id)) {
            manageReversalPosition(symbol_id, event.price);
        } else {
            // Look for mean reversion opportunities
            detectReversalOpportunity(symbol_id, event.price);
        }
        
        // Update pairs trading if enabled
        if (params_.trade_pairs) {
            updatePairsSpreads(symbol_id, event.price);
            checkPairsTrading();
        }
    }
    
    void onOrderFill(const Order& order) override {
        uint32_t symbol_id = order.symbol_id;
        
        if (order.status == 3) { // Filled
            if (!hasActivePosition(symbol_id)) {
                // New position
                createReversalTrade(symbol_id, order);
            } else {
                // Close position
                closeReversalTrade(symbol_id, order);
            }
        }
        
        updateMetrics(order);
    }
    
    void onTick() override {
        if (state_ != StrategyState::RUNNING) return;
        
        // Check for stale positions
        uint64_t current_time = getCurrentTimeNs();
        for (auto& [symbol_id, trade] : active_trades_) {
            if (trade.is_active && 
                (current_time - trade.entry_time_ns) > params_.max_hold_time_ns) {
                generateExitSignal(symbol_id, "timeout");
            }
        }
        
        // Update Kalman filters
        updateKalmanFilters();
        
        updatePerformanceMetrics();
    }
    
    void shutdown() override {
        for (auto& [symbol_id, trade] : active_trades_) {
            if (trade.is_active) {
                generateExitSignal(symbol_id, "shutdown");
            }
        }
    }
    
    bool hasSignal() const override {
        return !pending_signals_.empty();
    }
    
    TradingSignal getSignal() override {
        if (pending_signals_.empty()) {
            return TradingSignal{};
        }
        
        TradingSignal signal = pending_signals_.front();
        pending_signals_.erase(pending_signals_.begin());
        return signal;
    }
    
    void clearSignals() override {
        pending_signals_.clear();
    }
    
    void updatePosition(uint32_t symbol_id, int32_t quantity, double price) override {
        // Position tracking in trade management
    }
    
    Position getPosition(uint32_t symbol_id) const override {
        auto it = active_trades_.find(symbol_id);
        if (it != active_trades_.end() && it->second.is_active) {
            const ReversalTrade& trade = it->second;
            int32_t position = trade.quantity * trade.direction;
            return {symbol_id, position, trade.entry_price, 0.0};
        }
        return {symbol_id, 0, 0.0, 0.0};
    }
    
    double getUnrealizedPnL() const override {
        double total_pnl = 0.0;
        for (const auto& [symbol_id, trade] : active_trades_) {
            if (trade.is_active) {
                double current_price = getCurrentPrice(symbol_id);
                double pnl = (current_price - trade.entry_price) * trade.quantity * trade.direction;
                total_pnl += pnl;
            }
        }
        return total_pnl;
    }
    
    bool shouldTrade(const TradingSignal& signal) override {
        uint32_t symbol_id = signal.symbol_id;
        
        // Check if we have too many false signals
        if (false_signals_[symbol_id] > 5) {
            return false;
        }
        
        // Check volatility range
        const StatisticalData& stats = statistics_[symbol_id];
        if (stats.std_dev < params_.min_volatility || 
            stats.std_dev > params_.max_volatility) {
            return false;
        }
        
        return checkRiskLimits();
    }
    
    double calculatePositionSize(const TradingSignal& signal) override {
        // Size based on z-score confidence
        double base_size = params_.max_position_size;
        double zscore_confidence = std::min(1.0, std::abs(signal.signal_strength) / 3.0);
        
        return base_size * zscore_confidence * 0.8; // Conservative sizing
    }
    
    bool checkRiskLimits() override {
        // Check daily P&L
        if (metrics_.realized_pnl.load() < -config_.max_daily_loss) {
            return false;
        }
        
        // Limit concurrent positions
        uint32_t active_positions = 0;
        for (const auto& [symbol_id, trade] : active_trades_) {
            if (trade.is_active) active_positions++;
        }
        
        return active_positions < 5;
    }

private:
    void loadParameters() {
        for (const auto& param : config_.parameters) {
            parseParameter(param);
        }
    }
    
    void parseParameter(const std::string& param) {
        size_t pos = param.find('=');
        if (pos != std::string::npos) {
            std::string key = param.substr(0, pos);
            std::string value = param.substr(pos + 1);
            
            if (key == "lookback_period") {
                params_.lookback_period = std::stoul(value);
            } else if (key == "zscore_entry_threshold") {
                params_.zscore_entry_threshold = std::stod(value);
            } else if (key == "zscore_exit_threshold") {
                params_.zscore_exit_threshold = std::stod(value);
            }
        }
    }
    
    void updateStatistics(uint32_t symbol_id, double price) {
        StatisticalData& stats = statistics_[symbol_id];
        
        // Update price history
        stats.prices.push_back(price);
        if (stats.prices.size() > params_.lookback_period * 2) {
            stats.prices.pop_front();
        }
        
        // Calculate returns
        if (stats.prices.size() > 1) {
            double return_val = (price - stats.prices[stats.prices.size() - 2]) / 
                               stats.prices[stats.prices.size() - 2];
            stats.returns.push_back(return_val);
            if (stats.returns.size() > params_.lookback_period) {
                stats.returns.pop_front();
            }
        }
        
        // Update statistics
        if (stats.prices.size() >= params_.lookback_period) {
            calculateMeanAndStdDev(stats);
            calculateBollingerBands(stats);
            calculateZScore(stats, price);
            
            if (params_.use_kalman_filter) {
                updateKalmanMean(stats, price);
            }
            
            detectMeanReversion(stats);
        }
    }
    
    void calculateMeanAndStdDev(StatisticalData& stats) {
        // Calculate simple moving average
        double sum = 0.0;
        size_t start = stats.prices.size() - params_.lookback_period;
        for (size_t i = start; i < stats.prices.size(); i++) {
            sum += stats.prices[i];
        }
        stats.mean = sum / params_.lookback_period;
        
        // Calculate standard deviation
        double variance = 0.0;
        for (size_t i = start; i < stats.prices.size(); i++) {
            double diff = stats.prices[i] - stats.mean;
            variance += diff * diff;
        }
        stats.std_dev = std::sqrt(variance / (params_.lookback_period - 1));
    }
    
    void calculateBollingerBands(StatisticalData& stats) {
        stats.upper_band = stats.mean + (params_.bollinger_band_mult * stats.std_dev);
        stats.lower_band = stats.mean - (params_.bollinger_band_mult * stats.std_dev);
    }
    
    void calculateZScore(StatisticalData& stats, double current_price) {
        if (stats.std_dev > 0) {
            double mean_to_use = params_.use_kalman_filter ? stats.kalman_mean : stats.mean;
            stats.current_zscore = (current_price - mean_to_use) / stats.std_dev;
        } else {
            stats.current_zscore = 0.0;
        }
    }
    
    void updateKalmanMean(StatisticalData& stats, double price) {
        // Simple Kalman filter for estimating mean
        double process_variance = 0.01;
        double measurement_variance = stats.std_dev * stats.std_dev;
        
        // Prediction step
        double predicted_mean = stats.kalman_mean;
        double predicted_variance = stats.kalman_variance + process_variance;
        
        // Update step
        double kalman_gain = predicted_variance / (predicted_variance + measurement_variance);
        stats.kalman_mean = predicted_mean + kalman_gain * (price - predicted_mean);
        stats.kalman_variance = (1 - kalman_gain) * predicted_variance;
    }
    
    void detectMeanReversion(StatisticalData& stats) {
        // Check if price series exhibits mean reversion
        if (stats.returns.size() < 10) return;
        
        // Calculate autocorrelation of returns
        double autocorr = calculateAutocorrelation(stats.returns, 1);
        
        // Negative autocorrelation suggests mean reversion
        stats.mean_reverting = autocorr < -0.1;
        
        // Count deviations beyond threshold
        if (std::abs(stats.current_zscore) > params_.zscore_entry_threshold) {
            stats.deviations_count++;
        }
    }
    
    double calculateAutocorrelation(const std::deque<double>& data, int lag) {
        if (data.size() < lag + 2) return 0.0;
        
        double mean = std::accumulate(data.begin(), data.end(), 0.0) / data.size();
        
        double numerator = 0.0;
        double denominator = 0.0;
        
        for (size_t i = lag; i < data.size(); i++) {
            numerator += (data[i] - mean) * (data[i - lag] - mean);
        }
        
        for (size_t i = 0; i < data.size(); i++) {
            denominator += (data[i] - mean) * (data[i] - mean);
        }
        
        return denominator > 0 ? numerator / denominator : 0.0;
    }
    
    void detectReversalOpportunity(uint32_t symbol_id, double current_price) {
        const StatisticalData& stats = statistics_[symbol_id];
        
        // Need sufficient data and mean-reverting behavior
        if (!stats.mean_reverting || stats.prices.size() < params_.lookback_period) {
            return;
        }
        
        // Check for extreme z-scores
        bool oversold = stats.current_zscore < -params_.zscore_entry_threshold;
        bool overbought = stats.current_zscore > params_.zscore_entry_threshold;
        
        // Additional filters
        bool bollinger_confirmation = oversold ? (current_price < stats.lower_band) : 
                                                (current_price > stats.upper_band);
        
        if (oversold && bollinger_confirmation && !oversold_signals_[symbol_id]) {
            // Buy signal (expect price to rise back to mean)
            generateReversalSignal(symbol_id, 1, current_price, stats.current_zscore);
            oversold_signals_[symbol_id] = true;
        } else if (overbought && bollinger_confirmation && !overbought_signals_[symbol_id]) {
            // Sell signal (expect price to fall back to mean)
            generateReversalSignal(symbol_id, -1, current_price, stats.current_zscore);
            overbought_signals_[symbol_id] = true;
        }
        
        // Reset signals when z-score normalizes
        if (std::abs(stats.current_zscore) < 1.0) {
            oversold_signals_[symbol_id] = false;
            overbought_signals_[symbol_id] = false;
        }
    }
    
    void generateReversalSignal(uint32_t symbol_id, int8_t direction, double price, double zscore) {
        TradingSignal signal{};
        signal.timestamp_ns = getCurrentTimeNs();
        signal.symbol_id = symbol_id;
        signal.strategy_id = config_.strategy_id;
        signal.signal_strength = -zscore; // Negative z-score = buy, positive = sell
        signal.confidence = std::min(0.9, std::abs(zscore) / 3.0);
        signal.suggested_quantity = calculatePositionSize(signal);
        signal.suggested_price_ticks = static_cast<uint32_t>(price / 0.01);
        signal.urgency = 500; // Lower urgency for mean reversion
        signal.signal_type = 1; // Entry
        
        pending_signals_.push_back(signal);
        metrics_.signals_generated++;
    }
    
    void generateExitSignal(uint32_t symbol_id, const std::string& reason) {
        const ReversalTrade& trade = active_trades_[symbol_id];
        
        TradingSignal signal{};
        signal.timestamp_ns = getCurrentTimeNs();
        signal.symbol_id = symbol_id;
        signal.strategy_id = config_.strategy_id;
        signal.signal_strength = -trade.direction * 1.0;
        signal.confidence = 1.0;
        signal.suggested_quantity = trade.quantity;
        signal.suggested_price_ticks = 0; // Market order
        signal.urgency = 100;
        signal.signal_type = 2; // Exit
        
        pending_signals_.push_back(signal);
    }
    
    void manageReversalPosition(uint32_t symbol_id, double current_price) {
        ReversalTrade& trade = active_trades_[symbol_id];
        const StatisticalData& stats = statistics_[symbol_id];
        
        if (!trade.is_active) return;
        
        // Check if z-score has reverted
        if (std::abs(stats.current_zscore) < params_.zscore_exit_threshold) {
            generateExitSignal(symbol_id, "mean_reversion");
            return;
        }
        
        // Check if z-score has gone further extreme (stop loss)
        if (trade.direction == 1 && stats.current_zscore < trade.entry_zscore - 1.0) {
            generateExitSignal(symbol_id, "stop_loss");
            false_signals_[symbol_id]++;
            return;
        } else if (trade.direction == -1 && stats.current_zscore > trade.entry_zscore + 1.0) {
            generateExitSignal(symbol_id, "stop_loss");
            false_signals_[symbol_id]++;
            return;
        }
        
        // Check absolute stop loss
        double pnl = (current_price - trade.entry_price) * trade.direction;
        if (pnl < -stats.std_dev * 3) {
            generateExitSignal(symbol_id, "max_loss");
        }
    }
    
    void createReversalTrade(uint32_t symbol_id, const Order& order) {
        ReversalTrade& trade = active_trades_[symbol_id];
        const StatisticalData& stats = statistics_[symbol_id];
        
        trade.entry_time_ns = getCurrentTimeNs();
        trade.symbol_id = symbol_id;
        trade.entry_price = order.price_ticks * 0.01;
        trade.entry_zscore = stats.current_zscore;
        trade.quantity = order.quantity;
        trade.direction = (order.side == 1) ? 1 : -1;
        
        // Target is mean price
        trade.target_price = params_.use_kalman_filter ? stats.kalman_mean : stats.mean;
        
        // Stop loss beyond another standard deviation
        trade.stop_loss = trade.entry_price - (trade.direction * stats.std_dev * 3);
        
        trade.is_active = true;
        trade.is_pair_trade = false;
    }
    
    void closeReversalTrade(uint32_t symbol_id, const Order& order) {
        ReversalTrade& trade = active_trades_[symbol_id];
        
        if (trade.is_active) {
            double exit_price = order.price_ticks * 0.01;
            double pnl = (exit_price - trade.entry_price) * trade.quantity * trade.direction;
            
            // Track z-score profit
            const StatisticalData& stats = statistics_[symbol_id];
            double zscore_change = std::abs(trade.entry_zscore) - std::abs(stats.current_zscore);
            total_zscore_profit_ += zscore_change;
            
            if (pnl > 0) {
                metrics_.winning_trades++;
                false_signals_[symbol_id] = 0; // Reset false signals
            } else {
                metrics_.losing_trades++;
            }
            
            trade.is_active = false;
            metrics_.realized_pnl += pnl;
        }
    }
    
    // Pairs trading implementation
    void identifyTradingPairs() {
        // Simple correlation-based pair identification
        for (size_t i = 0; i < config_.target_symbols.size(); i++) {
            for (size_t j = i + 1; j < config_.target_symbols.size(); j++) {
                uint32_t sym1 = config_.target_symbols[i];
                uint32_t sym2 = config_.target_symbols[j];
                
                // Would calculate correlation here
                // For now, just create a pair
                PairData pair;
                pair.symbol1_id = sym1;
                pair.symbol2_id = sym2;
                pair.correlation = 0.85; // Placeholder
                pair.hedge_ratio = 1.0;  // Placeholder
                pair.spread_mean = 0.0;
                pair.spread_std = 0.01;
                
                trading_pairs_.push_back(pair);
            }
        }
    }
    
    void updatePairsSpreads(uint32_t symbol_id, double price) {
        // Update spread calculations for pairs involving this symbol
        for (auto& pair : trading_pairs_) {
            if (pair.symbol1_id == symbol_id || pair.symbol2_id == symbol_id) {
                updatePairSpread(pair);
            }
        }
    }
    
    void updatePairSpread(PairData& pair) {
        double price1 = getCurrentPrice(pair.symbol1_id);
        double price2 = getCurrentPrice(pair.symbol2_id);
        
        if (price1 > 0 && price2 > 0) {
            double spread = price1 - pair.hedge_ratio * price2;
            pair.spread_history.push_back(spread);
            
            if (pair.spread_history.size() > params_.lookback_period) {
                pair.spread_history.pop_front();
            }
            
            // Update spread statistics
            if (pair.spread_history.size() >= 10) {
                double sum = std::accumulate(pair.spread_history.begin(), 
                                           pair.spread_history.end(), 0.0);
                pair.spread_mean = sum / pair.spread_history.size();
                
                double variance = 0.0;
                for (double s : pair.spread_history) {
                    variance += (s - pair.spread_mean) * (s - pair.spread_mean);
                }
                pair.spread_std = std::sqrt(variance / (pair.spread_history.size() - 1));
            }
        }
    }
    
    void checkPairsTrading() {
        // Check for pairs trading opportunities
        for (const auto& pair : trading_pairs_) {
            if (pair.spread_history.size() < params_.lookback_period) continue;
            
            double current_spread = pair.spread_history.back();
            double spread_zscore = (current_spread - pair.spread_mean) / pair.spread_std;
            
            // Check for extreme spreads
            if (std::abs(spread_zscore) > params_.zscore_entry_threshold) {
                // Would generate pairs trading signals here
            }
        }
    }
    
    void updateKalmanFilters() {
        // Periodic update of Kalman filters for all symbols
        for (auto& [symbol_id, stats] : statistics_) {
            if (stats.prices.size() >= params_.lookback_period) {
                // Re-estimate parameters if needed
            }
        }
    }
    
    bool hasActivePosition(uint32_t symbol_id) const {
        auto it = active_trades_.find(symbol_id);
        return it != active_trades_.end() && it->second.is_active;
    }
    
    double getCurrentPrice(uint32_t symbol_id) const {
        auto it = statistics_.find(symbol_id);
        if (it != statistics_.end() && !it->second.prices.empty()) {
            return it->second.prices.back();
        }
        return 0.0;
    }
    
    uint64_t getCurrentTimeNs() const {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::high_resolution_clock::now().time_since_epoch()).count();
    }
};

} // namespace HFT