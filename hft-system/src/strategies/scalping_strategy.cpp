/**
 * Scalping Strategy Implementation
 * Quick in-and-out trades capturing small price movements
 * Suitable for retail traders with low latency setup
 */

#include "base_strategy.h"
#include <algorithm>
#include <cmath>
#include <unordered_map>
#include <deque>

namespace HFT {

// Scalping parameters
struct ScalpingParams {
    double profit_target_ticks = 2.0;      // Target profit in ticks
    double stop_loss_ticks = 3.0;          // Stop loss in ticks
    double entry_threshold = 0.0002;       // 0.02% price movement threshold
    uint32_t max_position_size = 1000;     // Max shares per position
    uint32_t min_volume_threshold = 10000; // Min volume to trade
    double min_spread_ratio = 0.0001;      // Min spread as % of price
    double max_spread_ratio = 0.001;       // Max spread as % of price
    uint64_t max_hold_time_ns = 30000000000; // 30 seconds max hold
    uint32_t momentum_lookback = 20;       // Ticks to calculate momentum
    double volume_surge_multiplier = 2.0;  // Volume surge detection
    bool use_level2_data = true;           // Use order book imbalance
    double order_book_imbalance_threshold = 0.6; // 60% imbalance threshold
};

// Trade tracking
struct ScalpTrade {
    uint64_t entry_time_ns;
    uint32_t symbol_id;
    double entry_price;
    uint32_t quantity;
    int8_t direction;  // 1 = long, -1 = short
    double target_price;
    double stop_price;
    bool is_active;
};

// Real-time market microstructure
struct MicrostructureData {
    std::deque<double> price_ticks;
    std::deque<uint32_t> volumes;
    std::deque<uint64_t> timestamps;
    double momentum;
    double volatility;
    double average_spread;
    double volume_rate;
    double order_flow_imbalance;
};

class ScalpingStrategy : public BaseStrategy {
private:
    ScalpingParams params_;
    
    // Active trades
    std::unordered_map<uint32_t, ScalpTrade> active_trades_;
    
    // Market microstructure tracking
    std::unordered_map<uint32_t, MicrostructureData> microstructure_;
    
    // Price action patterns
    std::unordered_map<uint32_t, bool> bullish_momentum_;
    std::unordered_map<uint32_t, bool> bearish_momentum_;
    std::unordered_map<uint32_t, double> support_levels_;
    std::unordered_map<uint32_t, double> resistance_levels_;
    
    // Performance tracking
    uint64_t total_trades_ = 0;
    uint64_t winning_trades_ = 0;
    uint64_t losing_trades_ = 0;
    double total_profit_ticks_ = 0.0;
    
public:
    ScalpingStrategy(const StrategyConfig& config) 
        : BaseStrategy(config) {
        loadParameters();
    }
    
    void initialize() override {
        // Initialize microstructure tracking for each symbol
        for (uint32_t symbol_id : config_.target_symbols) {
            microstructure_[symbol_id] = MicrostructureData{};
            bullish_momentum_[symbol_id] = false;
            bearish_momentum_[symbol_id] = false;
        }
    }
    
    void onMarketData(const MarketDataEvent& event) override {
        if (state_ != StrategyState::RUNNING) return;
        
        uint32_t symbol_id = event.symbol_id;
        
        // Update microstructure
        updateMicrostructure(symbol_id, event);
        
        // Check existing positions first
        checkExistingPositions(symbol_id, event.price);
        
        // Look for new scalping opportunities
        if (!hasActivePosition(symbol_id)) {
            detectScalpingOpportunity(symbol_id, event);
        }
    }
    
    void onOrderFill(const Order& order) override {
        uint32_t symbol_id = order.symbol_id;
        
        // Update position tracking
        updatePosition(symbol_id, order.quantity, order.price_ticks * 0.01);
        
        // Create or update trade record
        if (order.side == 1 || order.side == 2) { // Entry order
            ScalpTrade& trade = active_trades_[symbol_id];
            trade.entry_time_ns = getCurrentTimeNs();
            trade.symbol_id = symbol_id;
            trade.entry_price = order.price_ticks * 0.01;
            trade.quantity = order.quantity;
            trade.direction = (order.side == 1) ? 1 : -1;
            trade.target_price = trade.entry_price + (trade.direction * params_.profit_target_ticks * 0.01);
            trade.stop_price = trade.entry_price - (trade.direction * params_.stop_loss_ticks * 0.01);
            trade.is_active = true;
        }
        
        // Update metrics
        updateMetrics(order);
    }
    
    void onTick() override {
        if (state_ != StrategyState::RUNNING) return;
        
        uint64_t current_time = getCurrentTimeNs();
        
        // Check for positions held too long
        for (auto& [symbol_id, trade] : active_trades_) {
            if (trade.is_active && 
                (current_time - trade.entry_time_ns) > params_.max_hold_time_ns) {
                // Force exit on timeout
                generateExitSignal(symbol_id, trade, "timeout");
            }
        }
        
        // Update performance metrics
        updatePerformanceMetrics();
    }
    
    void shutdown() override {
        // Close all active positions
        for (auto& [symbol_id, trade] : active_trades_) {
            if (trade.is_active) {
                generateExitSignal(symbol_id, trade, "shutdown");
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
        // Base class handles position tracking
        // We track trades separately for scalping metrics
    }
    
    Position getPosition(uint32_t symbol_id) const override {
        auto it = active_trades_.find(symbol_id);
        if (it != active_trades_.end() && it->second.is_active) {
            const ScalpTrade& trade = it->second;
            int32_t position = trade.quantity * trade.direction;
            return {symbol_id, position, trade.entry_price, 0.0};
        }
        return {symbol_id, 0, 0.0, 0.0};
    }
    
    double getUnrealizedPnL() const override {
        double total_pnl = 0.0;
        for (const auto& [symbol_id, trade] : active_trades_) {
            if (trade.is_active) {
                double current_price = getLastPrice(symbol_id);
                double pnl = (current_price - trade.entry_price) * trade.quantity * trade.direction;
                total_pnl += pnl;
            }
        }
        return total_pnl;
    }
    
    bool shouldTrade(const TradingSignal& signal) override {
        // Check risk limits
        if (!checkRiskLimits()) {
            return false;
        }
        
        // Check if we already have a position
        if (hasActivePosition(signal.symbol_id)) {
            return false;
        }
        
        return true;
    }
    
    double calculatePositionSize(const TradingSignal& signal) override {
        // Simple fixed size for scalping
        return std::min(static_cast<double>(params_.max_position_size), 
                       signal.suggested_quantity * 1.0);
    }
    
    bool checkRiskLimits() override {
        // Check max daily loss
        if (metrics_.realized_pnl.load() < -config_.max_daily_loss) {
            return false;
        }
        
        // Check win rate (after minimum trades)
        if (total_trades_ > 20) {
            double win_rate = static_cast<double>(winning_trades_) / total_trades_;
            if (win_rate < 0.4) { // Stop if win rate drops below 40%
                return false;
            }
        }
        
        return true;
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
            
            if (key == "profit_target_ticks") {
                params_.profit_target_ticks = std::stod(value);
            } else if (key == "stop_loss_ticks") {
                params_.stop_loss_ticks = std::stod(value);
            } else if (key == "max_position_size") {
                params_.max_position_size = std::stoul(value);
            }
        }
    }
    
    void updateMicrostructure(uint32_t symbol_id, const MarketDataEvent& event) {
        MicrostructureData& ms = microstructure_[symbol_id];
        
        // Update price/volume history
        ms.price_ticks.push_back(event.price);
        ms.volumes.push_back(event.quantity);
        ms.timestamps.push_back(event.timestamp_ns);
        
        // Keep limited history
        while (ms.price_ticks.size() > params_.momentum_lookback) {
            ms.price_ticks.pop_front();
            ms.volumes.pop_front();
            ms.timestamps.pop_front();
        }
        
        // Calculate momentum
        if (ms.price_ticks.size() >= 5) {
            double price_change = ms.price_ticks.back() - ms.price_ticks.front();
            ms.momentum = price_change / ms.price_ticks.front();
            
            // Detect momentum
            bullish_momentum_[symbol_id] = ms.momentum > params_.entry_threshold;
            bearish_momentum_[symbol_id] = ms.momentum < -params_.entry_threshold;
        }
        
        // Calculate volume rate
        if (ms.volumes.size() >= 10) {
            uint32_t recent_volume = 0;
            for (size_t i = ms.volumes.size() - 5; i < ms.volumes.size(); i++) {
                recent_volume += ms.volumes[i];
            }
            uint32_t older_volume = 0;
            for (size_t i = 0; i < 5; i++) {
                older_volume += ms.volumes[i];
            }
            
            ms.volume_rate = static_cast<double>(recent_volume) / (older_volume + 1);
        }
        
        // Update support/resistance levels
        updateSupportResistance(symbol_id);
    }
    
    void detectScalpingOpportunity(uint32_t symbol_id, const MarketDataEvent& event) {
        const MicrostructureData& ms = microstructure_[symbol_id];
        
        // Need sufficient data
        if (ms.price_ticks.size() < params_.momentum_lookback) {
            return;
        }
        
        // Check volume surge
        bool volume_surge = ms.volume_rate > params_.volume_surge_multiplier;
        
        // Check spread conditions
        double spread = getSpread(symbol_id);
        double price = event.price;
        double spread_ratio = spread / price;
        
        if (spread_ratio < params_.min_spread_ratio || 
            spread_ratio > params_.max_spread_ratio) {
            return;
        }
        
        // Detect entry signals
        if (bullish_momentum_[symbol_id] && volume_surge) {
            // Bullish scalp opportunity
            generateEntrySignal(symbol_id, 1, event.price);
        } else if (bearish_momentum_[symbol_id] && volume_surge) {
            // Bearish scalp opportunity
            generateEntrySignal(symbol_id, -1, event.price);
        }
        
        // Check breakout opportunities
        checkBreakoutOpportunity(symbol_id, event.price);
    }
    
    void checkBreakoutOpportunity(uint32_t symbol_id, double current_price) {
        // Check resistance breakout
        if (resistance_levels_.find(symbol_id) != resistance_levels_.end()) {
            double resistance = resistance_levels_[symbol_id];
            if (current_price > resistance * 1.001) { // 0.1% above resistance
                generateEntrySignal(symbol_id, 1, current_price);
            }
        }
        
        // Check support breakdown
        if (support_levels_.find(symbol_id) != support_levels_.end()) {
            double support = support_levels_[symbol_id];
            if (current_price < support * 0.999) { // 0.1% below support
                generateEntrySignal(symbol_id, -1, current_price);
            }
        }
    }
    
    void updateSupportResistance(uint32_t symbol_id) {
        const MicrostructureData& ms = microstructure_[symbol_id];
        
        if (ms.price_ticks.size() < 20) return;
        
        // Simple support/resistance: recent highs and lows
        double recent_high = *std::max_element(ms.price_ticks.begin(), ms.price_ticks.end());
        double recent_low = *std::min_element(ms.price_ticks.begin(), ms.price_ticks.end());
        
        resistance_levels_[symbol_id] = recent_high;
        support_levels_[symbol_id] = recent_low;
    }
    
    void checkExistingPositions(uint32_t symbol_id, double current_price) {
        auto it = active_trades_.find(symbol_id);
        if (it == active_trades_.end() || !it->second.is_active) {
            return;
        }
        
        ScalpTrade& trade = it->second;
        
        // Check profit target
        if (trade.direction == 1) { // Long position
            if (current_price >= trade.target_price) {
                generateExitSignal(symbol_id, trade, "target");
                recordWin(trade, current_price);
            } else if (current_price <= trade.stop_price) {
                generateExitSignal(symbol_id, trade, "stop");
                recordLoss(trade, current_price);
            }
        } else { // Short position
            if (current_price <= trade.target_price) {
                generateExitSignal(symbol_id, trade, "target");
                recordWin(trade, current_price);
            } else if (current_price >= trade.stop_price) {
                generateExitSignal(symbol_id, trade, "stop");
                recordLoss(trade, current_price);
            }
        }
    }
    
    void generateEntrySignal(uint32_t symbol_id, int8_t direction, double price) {
        TradingSignal signal{};
        signal.timestamp_ns = getCurrentTimeNs();
        signal.symbol_id = symbol_id;
        signal.strategy_id = config_.strategy_id;
        signal.signal_strength = direction * 0.8; // 80% confidence
        signal.confidence = 0.8;
        signal.suggested_quantity = params_.max_position_size;
        signal.suggested_price_ticks = static_cast<uint32_t>(price / 0.01);
        signal.urgency = 50; // 50ms urgency for scalping
        signal.signal_type = 1; // Entry
        
        pending_signals_.push_back(signal);
        metrics_.signals_generated++;
    }
    
    void generateExitSignal(uint32_t symbol_id, ScalpTrade& trade, const std::string& reason) {
        TradingSignal signal{};
        signal.timestamp_ns = getCurrentTimeNs();
        signal.symbol_id = symbol_id;
        signal.strategy_id = config_.strategy_id;
        signal.signal_strength = -trade.direction * 1.0; // Opposite direction to close
        signal.confidence = 1.0; // Always exit when triggered
        signal.suggested_quantity = trade.quantity;
        signal.suggested_price_ticks = 0; // Market order for exit
        signal.urgency = 10; // High urgency for exit
        signal.signal_type = 2; // Exit
        
        pending_signals_.push_back(signal);
        trade.is_active = false;
    }
    
    void recordWin(const ScalpTrade& trade, double exit_price) {
        winning_trades_++;
        total_trades_++;
        double profit_ticks = (exit_price - trade.entry_price) * trade.direction / 0.01;
        total_profit_ticks_ += profit_ticks;
        metrics_.winning_trades++;
    }
    
    void recordLoss(const ScalpTrade& trade, double exit_price) {
        losing_trades_++;
        total_trades_++;
        double loss_ticks = (exit_price - trade.entry_price) * trade.direction / 0.01;
        total_profit_ticks_ += loss_ticks; // Will be negative
        metrics_.losing_trades++;
    }
    
    bool hasActivePosition(uint32_t symbol_id) const {
        auto it = active_trades_.find(symbol_id);
        return it != active_trades_.end() && it->second.is_active;
    }
    
    double getLastPrice(uint32_t symbol_id) const {
        auto it = microstructure_.find(symbol_id);
        if (it != microstructure_.end() && !it->second.price_ticks.empty()) {
            return it->second.price_ticks.back();
        }
        return 0.0;
    }
    
    double getSpread(uint32_t symbol_id) const {
        // Simplified spread calculation
        return 0.01; // 1 cent spread assumption for now
    }
    
    uint64_t getCurrentTimeNs() const {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::high_resolution_clock::now().time_since_epoch()).count();
    }
};

} // namespace HFT