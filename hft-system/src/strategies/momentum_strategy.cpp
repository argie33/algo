/**
 * Momentum Trading Strategy Implementation
 * Follows strong directional moves with proper risk management
 * Suitable for retail traders capturing intraday trends
 */

#include "base_strategy.h"
#include <algorithm>
#include <cmath>
#include <unordered_map>
#include <deque>
#include <numeric>

namespace HFT {

// Momentum parameters
struct MomentumParams {
    uint32_t fast_ma_period = 10;          // Fast moving average
    uint32_t slow_ma_period = 30;          // Slow moving average
    uint32_t momentum_period = 14;         // Momentum calculation period
    double momentum_threshold = 0.003;     // 0.3% momentum threshold
    double volume_confirmation = 1.5;      // Volume must be 1.5x average
    uint32_t max_position_size = 2000;     // Max shares per position
    double atr_multiplier = 2.0;           // ATR multiplier for stop loss
    double profit_target_ratio = 3.0;      // Risk/reward ratio
    uint64_t min_hold_time_ns = 60000000000; // 1 minute minimum hold
    double pullback_entry_ratio = 0.382;   // Fibonacci retracement for entry
    bool use_vwap = true;                  // Use VWAP for confirmation
    double max_distance_from_vwap = 0.02;  // Max 2% from VWAP
};

// Trade management
struct MomentumTrade {
    uint64_t entry_time_ns;
    uint32_t symbol_id;
    double entry_price;
    uint32_t quantity;
    int8_t direction;
    double stop_loss;
    double take_profit;
    double trailing_stop;
    double highest_price;  // For trailing stop
    double lowest_price;   // For trailing stop
    bool is_active;
    std::string entry_reason;
};

// Technical indicators
struct TechnicalIndicators {
    std::deque<double> prices;
    std::deque<uint32_t> volumes;
    std::deque<uint64_t> timestamps;
    double fast_ma;
    double slow_ma;
    double momentum;
    double atr;  // Average True Range
    double vwap;
    double volume_ma;
    double rsi;
    bool ma_crossover;
    bool volume_surge;
};

class MomentumStrategy : public BaseStrategy {
private:
    MomentumParams params_;
    
    // Active trades
    std::unordered_map<uint32_t, MomentumTrade> active_trades_;
    
    // Technical indicators for each symbol
    std::unordered_map<uint32_t, TechnicalIndicators> indicators_;
    
    // Trend detection
    std::unordered_map<uint32_t, int8_t> trend_direction_; // 1=up, -1=down, 0=neutral
    std::unordered_map<uint32_t, double> trend_strength_;
    
    // VWAP calculation
    std::unordered_map<uint32_t, double> cumulative_volume_;
    std::unordered_map<uint32_t, double> cumulative_price_volume_;
    
    // Performance
    std::unordered_map<uint32_t, uint32_t> consecutive_losses_;
    
public:
    MomentumStrategy(const StrategyConfig& config) 
        : BaseStrategy(config) {
        loadParameters();
    }
    
    void initialize() override {
        for (uint32_t symbol_id : config_.target_symbols) {
            indicators_[symbol_id] = TechnicalIndicators{};
            trend_direction_[symbol_id] = 0;
            trend_strength_[symbol_id] = 0.0;
            cumulative_volume_[symbol_id] = 0.0;
            cumulative_price_volume_[symbol_id] = 0.0;
            consecutive_losses_[symbol_id] = 0;
        }
    }
    
    void onMarketData(const MarketDataEvent& event) override {
        if (state_ != StrategyState::RUNNING) return;
        
        uint32_t symbol_id = event.symbol_id;
        
        // Update indicators
        updateIndicators(symbol_id, event);
        
        // Manage existing positions
        if (hasActivePosition(symbol_id)) {
            managePosition(symbol_id, event.price);
        } else {
            // Look for entry opportunities
            detectMomentumEntry(symbol_id, event);
        }
    }
    
    void onOrderFill(const Order& order) override {
        uint32_t symbol_id = order.symbol_id;
        
        if (order.status == 3) { // Filled
            if (!hasActivePosition(symbol_id)) {
                // New position entry
                createMomentumTrade(symbol_id, order);
            } else {
                // Position exit
                closeMomentumTrade(symbol_id, order);
            }
        }
        
        updateMetrics(order);
    }
    
    void onTick() override {
        if (state_ != StrategyState::RUNNING) return;
        
        // Update trailing stops
        for (auto& [symbol_id, trade] : active_trades_) {
            if (trade.is_active) {
                updateTrailingStop(symbol_id, trade);
            }
        }
        
        updatePerformanceMetrics();
    }
    
    void shutdown() override {
        // Close all positions
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
        // Position tracking handled in trade management
    }
    
    Position getPosition(uint32_t symbol_id) const override {
        auto it = active_trades_.find(symbol_id);
        if (it != active_trades_.end() && it->second.is_active) {
            const MomentumTrade& trade = it->second;
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
        
        // Skip if too many consecutive losses
        if (consecutive_losses_[symbol_id] >= 3) {
            return false;
        }
        
        // Check risk limits
        return checkRiskLimits();
    }
    
    double calculatePositionSize(const TradingSignal& signal) override {
        // Risk-based position sizing
        double account_risk = config_.max_position_size * 0.01; // 1% risk per trade
        double price = signal.suggested_price_ticks * 0.01;
        double stop_distance = indicators_[signal.symbol_id].atr * params_.atr_multiplier;
        
        double position_size = account_risk / stop_distance;
        return std::min(position_size, static_cast<double>(params_.max_position_size));
    }
    
    bool checkRiskLimits() override {
        // Check daily loss limit
        if (metrics_.realized_pnl.load() < -config_.max_daily_loss) {
            return false;
        }
        
        // Check number of open positions
        uint32_t open_positions = 0;
        for (const auto& [symbol_id, trade] : active_trades_) {
            if (trade.is_active) open_positions++;
        }
        
        return open_positions < 3; // Max 3 concurrent positions
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
            
            if (key == "fast_ma_period") {
                params_.fast_ma_period = std::stoul(value);
            } else if (key == "slow_ma_period") {
                params_.slow_ma_period = std::stoul(value);
            } else if (key == "momentum_threshold") {
                params_.momentum_threshold = std::stod(value);
            }
        }
    }
    
    void updateIndicators(uint32_t symbol_id, const MarketDataEvent& event) {
        TechnicalIndicators& ind = indicators_[symbol_id];
        
        // Update price/volume history
        ind.prices.push_back(event.price);
        ind.volumes.push_back(event.quantity);
        ind.timestamps.push_back(event.timestamp_ns);
        
        // Maintain window size
        while (ind.prices.size() > params_.slow_ma_period * 2) {
            ind.prices.pop_front();
            ind.volumes.pop_front();
            ind.timestamps.pop_front();
        }
        
        // Calculate indicators
        if (ind.prices.size() >= params_.slow_ma_period) {
            calculateMovingAverages(ind);
            calculateMomentum(ind);
            calculateATR(ind);
            calculateVolumeIndicators(ind);
            updateVWAP(symbol_id, event.price, event.quantity);
            detectTrend(symbol_id, ind);
        }
    }
    
    void calculateMovingAverages(TechnicalIndicators& ind) {
        // Fast MA
        if (ind.prices.size() >= params_.fast_ma_period) {
            double sum = 0.0;
            for (size_t i = ind.prices.size() - params_.fast_ma_period; i < ind.prices.size(); i++) {
                sum += ind.prices[i];
            }
            ind.fast_ma = sum / params_.fast_ma_period;
        }
        
        // Slow MA
        if (ind.prices.size() >= params_.slow_ma_period) {
            double sum = 0.0;
            for (size_t i = ind.prices.size() - params_.slow_ma_period; i < ind.prices.size(); i++) {
                sum += ind.prices[i];
            }
            ind.slow_ma = sum / params_.slow_ma_period;
        }
        
        // Detect crossover
        if (ind.fast_ma > 0 && ind.slow_ma > 0) {
            double prev_fast = calculateMA(ind.prices, params_.fast_ma_period, 1);
            double prev_slow = calculateMA(ind.prices, params_.slow_ma_period, 1);
            
            ind.ma_crossover = (prev_fast <= prev_slow && ind.fast_ma > ind.slow_ma) ||
                              (prev_fast >= prev_slow && ind.fast_ma < ind.slow_ma);
        }
    }
    
    double calculateMA(const std::deque<double>& prices, uint32_t period, uint32_t offset = 0) {
        if (prices.size() < period + offset) return 0.0;
        
        double sum = 0.0;
        size_t start = prices.size() - period - offset;
        size_t end = prices.size() - offset;
        
        for (size_t i = start; i < end; i++) {
            sum += prices[i];
        }
        return sum / period;
    }
    
    void calculateMomentum(TechnicalIndicators& ind) {
        if (ind.prices.size() >= params_.momentum_period) {
            double current_price = ind.prices.back();
            double past_price = ind.prices[ind.prices.size() - params_.momentum_period];
            ind.momentum = (current_price - past_price) / past_price;
        }
    }
    
    void calculateATR(TechnicalIndicators& ind) {
        if (ind.prices.size() < 2) return;
        
        // Simplified ATR calculation
        std::vector<double> true_ranges;
        for (size_t i = 1; i < ind.prices.size() && i < 14; i++) {
            double high_low = std::abs(ind.prices[i] - ind.prices[i-1]);
            true_ranges.push_back(high_low);
        }
        
        if (!true_ranges.empty()) {
            ind.atr = std::accumulate(true_ranges.begin(), true_ranges.end(), 0.0) / true_ranges.size();
        }
    }
    
    void calculateVolumeIndicators(TechnicalIndicators& ind) {
        // Volume moving average
        if (ind.volumes.size() >= 20) {
            uint32_t sum = 0;
            for (size_t i = ind.volumes.size() - 20; i < ind.volumes.size(); i++) {
                sum += ind.volumes[i];
            }
            ind.volume_ma = static_cast<double>(sum) / 20.0;
            
            // Check for volume surge
            ind.volume_surge = ind.volumes.back() > ind.volume_ma * params_.volume_confirmation;
        }
    }
    
    void updateVWAP(uint32_t symbol_id, double price, uint32_t volume) {
        cumulative_volume_[symbol_id] += volume;
        cumulative_price_volume_[symbol_id] += price * volume;
        
        if (cumulative_volume_[symbol_id] > 0) {
            indicators_[symbol_id].vwap = cumulative_price_volume_[symbol_id] / cumulative_volume_[symbol_id];
        }
    }
    
    void detectTrend(uint32_t symbol_id, const TechnicalIndicators& ind) {
        // Simple trend detection based on MA alignment and momentum
        if (ind.fast_ma > ind.slow_ma && ind.momentum > params_.momentum_threshold) {
            trend_direction_[symbol_id] = 1;  // Uptrend
            trend_strength_[symbol_id] = ind.momentum;
        } else if (ind.fast_ma < ind.slow_ma && ind.momentum < -params_.momentum_threshold) {
            trend_direction_[symbol_id] = -1; // Downtrend
            trend_strength_[symbol_id] = std::abs(ind.momentum);
        } else {
            trend_direction_[symbol_id] = 0;  // No clear trend
            trend_strength_[symbol_id] = 0.0;
        }
    }
    
    void detectMomentumEntry(uint32_t symbol_id, const MarketDataEvent& event) {
        const TechnicalIndicators& ind = indicators_[symbol_id];
        
        // Need sufficient data
        if (ind.prices.size() < params_.slow_ma_period) return;
        
        // Check for strong momentum with volume confirmation
        bool strong_momentum = std::abs(ind.momentum) > params_.momentum_threshold;
        bool volume_confirmed = ind.volume_surge;
        bool trend_aligned = (ind.momentum > 0 && trend_direction_[symbol_id] == 1) ||
                           (ind.momentum < 0 && trend_direction_[symbol_id] == -1);
        
        // VWAP filter
        bool vwap_filter = true;
        if (params_.use_vwap && ind.vwap > 0) {
            double distance_from_vwap = std::abs(event.price - ind.vwap) / ind.vwap;
            vwap_filter = distance_from_vwap < params_.max_distance_from_vwap;
        }
        
        if (strong_momentum && volume_confirmed && trend_aligned && vwap_filter) {
            // Check for entry patterns
            if (ind.ma_crossover) {
                generateEntrySignal(symbol_id, trend_direction_[symbol_id], event.price, "MA Crossover");
            } else if (checkPullbackEntry(symbol_id, event.price)) {
                generateEntrySignal(symbol_id, trend_direction_[symbol_id], event.price, "Pullback");
            }
        }
    }
    
    bool checkPullbackEntry(uint32_t symbol_id, double current_price) {
        const TechnicalIndicators& ind = indicators_[symbol_id];
        
        if (trend_direction_[symbol_id] == 1) { // Uptrend
            // Look for pullback to support (near fast MA)
            double pullback_level = ind.fast_ma + (ind.atr * 0.5);
            return current_price <= pullback_level && current_price > ind.slow_ma;
        } else if (trend_direction_[symbol_id] == -1) { // Downtrend
            // Look for pullback to resistance
            double pullback_level = ind.fast_ma - (ind.atr * 0.5);
            return current_price >= pullback_level && current_price < ind.slow_ma;
        }
        
        return false;
    }
    
    void generateEntrySignal(uint32_t symbol_id, int8_t direction, double price, const std::string& reason) {
        TradingSignal signal{};
        signal.timestamp_ns = getCurrentTimeNs();
        signal.symbol_id = symbol_id;
        signal.strategy_id = config_.strategy_id;
        signal.signal_strength = direction * trend_strength_[symbol_id];
        signal.confidence = std::min(0.9, trend_strength_[symbol_id] * 100); // Cap at 90%
        signal.suggested_quantity = calculatePositionSize(signal);
        signal.suggested_price_ticks = static_cast<uint32_t>(price / 0.01);
        signal.urgency = 200; // 200ms for momentum trades
        signal.signal_type = 1; // Entry
        
        pending_signals_.push_back(signal);
        metrics_.signals_generated++;
    }
    
    void generateExitSignal(uint32_t symbol_id, const std::string& reason) {
        const MomentumTrade& trade = active_trades_[symbol_id];
        
        TradingSignal signal{};
        signal.timestamp_ns = getCurrentTimeNs();
        signal.symbol_id = symbol_id;
        signal.strategy_id = config_.strategy_id;
        signal.signal_strength = -trade.direction * 1.0;
        signal.confidence = 1.0;
        signal.suggested_quantity = trade.quantity;
        signal.suggested_price_ticks = 0; // Market order
        signal.urgency = 50; // Higher urgency for exits
        signal.signal_type = 2; // Exit
        
        pending_signals_.push_back(signal);
    }
    
    void createMomentumTrade(uint32_t symbol_id, const Order& order) {
        MomentumTrade& trade = active_trades_[symbol_id];
        const TechnicalIndicators& ind = indicators_[symbol_id];
        
        trade.entry_time_ns = getCurrentTimeNs();
        trade.symbol_id = symbol_id;
        trade.entry_price = order.price_ticks * 0.01;
        trade.quantity = order.quantity;
        trade.direction = (order.side == 1) ? 1 : -1;
        
        // Set stop loss based on ATR
        double stop_distance = ind.atr * params_.atr_multiplier;
        trade.stop_loss = trade.entry_price - (trade.direction * stop_distance);
        
        // Set take profit based on risk/reward ratio
        double profit_distance = stop_distance * params_.profit_target_ratio;
        trade.take_profit = trade.entry_price + (trade.direction * profit_distance);
        
        // Initialize trailing stop
        trade.trailing_stop = trade.stop_loss;
        trade.highest_price = trade.entry_price;
        trade.lowest_price = trade.entry_price;
        
        trade.is_active = true;
    }
    
    void closeMomentumTrade(uint32_t symbol_id, const Order& order) {
        MomentumTrade& trade = active_trades_[symbol_id];
        
        if (trade.is_active) {
            double exit_price = order.price_ticks * 0.01;
            double pnl = (exit_price - trade.entry_price) * trade.quantity * trade.direction;
            
            if (pnl > 0) {
                metrics_.winning_trades++;
                consecutive_losses_[symbol_id] = 0;
            } else {
                metrics_.losing_trades++;
                consecutive_losses_[symbol_id]++;
            }
            
            trade.is_active = false;
            metrics_.realized_pnl += pnl;
        }
    }
    
    void managePosition(uint32_t symbol_id, double current_price) {
        MomentumTrade& trade = active_trades_[symbol_id];
        
        if (!trade.is_active) return;
        
        // Update high/low water marks
        if (trade.direction == 1) {
            trade.highest_price = std::max(trade.highest_price, current_price);
        } else {
            trade.lowest_price = std::min(trade.lowest_price, current_price);
        }
        
        // Check stop loss
        if ((trade.direction == 1 && current_price <= trade.trailing_stop) ||
            (trade.direction == -1 && current_price >= trade.trailing_stop)) {
            generateExitSignal(symbol_id, "stop_loss");
            return;
        }
        
        // Check take profit
        if ((trade.direction == 1 && current_price >= trade.take_profit) ||
            (trade.direction == -1 && current_price <= trade.take_profit)) {
            generateExitSignal(symbol_id, "take_profit");
            return;
        }
        
        // Check momentum exhaustion
        if (checkMomentumExhaustion(symbol_id)) {
            generateExitSignal(symbol_id, "momentum_exhaustion");
        }
    }
    
    void updateTrailingStop(uint32_t symbol_id, MomentumTrade& trade) {
        const TechnicalIndicators& ind = indicators_[symbol_id];
        
        if (trade.direction == 1) {
            // Long position - trail stop below highs
            double new_stop = trade.highest_price - (ind.atr * params_.atr_multiplier);
            trade.trailing_stop = std::max(trade.trailing_stop, new_stop);
        } else {
            // Short position - trail stop above lows
            double new_stop = trade.lowest_price + (ind.atr * params_.atr_multiplier);
            trade.trailing_stop = std::min(trade.trailing_stop, new_stop);
        }
    }
    
    bool checkMomentumExhaustion(uint32_t symbol_id) {
        const TechnicalIndicators& ind = indicators_[symbol_id];
        const MomentumTrade& trade = active_trades_[symbol_id];
        
        // Check if momentum is reversing
        if (trade.direction == 1 && ind.momentum < 0) {
            return true;
        } else if (trade.direction == -1 && ind.momentum > 0) {
            return true;
        }
        
        // Check if trend is weakening
        if (std::abs(trend_strength_[symbol_id]) < params_.momentum_threshold * 0.5) {
            return true;
        }
        
        return false;
    }
    
    bool hasActivePosition(uint32_t symbol_id) const {
        auto it = active_trades_.find(symbol_id);
        return it != active_trades_.end() && it->second.is_active;
    }
    
    double getCurrentPrice(uint32_t symbol_id) const {
        auto it = indicators_.find(symbol_id);
        if (it != indicators_.end() && !it->second.prices.empty()) {
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