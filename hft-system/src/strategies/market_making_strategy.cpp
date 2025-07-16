/**
 * Market Making Strategy Implementation
 * Provides liquidity by posting bid/ask quotes and capturing spread
 */

#include "base_strategy.h"
#include <algorithm>
#include <cmath>
#include <unordered_map>
#include <deque>

namespace HFT {

// Market making specific parameters
struct MarketMakingParams {
    double spread_capture_ratio = 0.5;      // Target % of spread to capture
    double max_inventory_ratio = 0.3;       // Max inventory as % of daily volume
    double skew_adjustment = 0.1;           // Inventory skew adjustment
    double volatility_adjustment = 0.05;    // Volatility-based spread adjustment
    uint32_t min_quote_size = 100;          // Minimum quote size
    uint32_t max_quote_size = 1000;         // Maximum quote size
    double tick_size = 0.01;                // Minimum price increment
    uint64_t quote_refresh_interval_ns = 100000000; // 100ms refresh interval
    double adverse_selection_threshold = 0.02; // Stop quoting if adverse selection > 2%
};

// Quote tracking
struct Quote {
    uint64_t timestamp_ns;
    uint32_t symbol_id;
    double bid_price;
    double ask_price;
    uint32_t bid_size;
    uint32_t ask_size;
    bool is_active;
};

// Inventory tracking
struct InventoryInfo {
    int32_t quantity;
    double average_price;
    double unrealized_pnl;
    double target_quantity;
    uint64_t last_update_ns;
};

class MarketMakingStrategy : public BaseStrategy {
private:
    MarketMakingParams params_;
    
    // Quote management
    std::unordered_map<uint32_t, Quote> active_quotes_;
    std::unordered_map<uint32_t, InventoryInfo> inventory_;
    std::unordered_map<uint32_t, std::deque<double>> price_history_;
    
    // Market data tracking
    std::unordered_map<uint32_t, double> last_prices_;
    std::unordered_map<uint32_t, double> bid_prices_;
    std::unordered_map<uint32_t, double> ask_prices_;
    std::unordered_map<uint32_t, uint32_t> bid_sizes_;
    std::unordered_map<uint32_t, uint32_t> ask_sizes_;
    
    // Volatility estimation
    std::unordered_map<uint32_t, double> volatility_estimates_;
    std::unordered_map<uint32_t, std::deque<double>> return_history_;
    
    // Performance tracking
    std::unordered_map<uint32_t, double> adverse_selection_ratios_;
    std::unordered_map<uint32_t, uint64_t> quote_counts_;
    std::unordered_map<uint32_t, uint64_t> fill_counts_;
    
    uint64_t last_quote_update_ns_ = 0;
    
public:
    MarketMakingStrategy(const StrategyConfig& config) 
        : BaseStrategy(config) {
        loadParameters();
    }
    
    void initialize() override {
        // Initialize for each target symbol
        for (uint32_t symbol_id : config_.target_symbols) {
            inventory_[symbol_id] = {0, 0.0, 0.0, 0, 0};
            price_history_[symbol_id] = std::deque<double>();
            return_history_[symbol_id] = std::deque<double>();
            volatility_estimates_[symbol_id] = 0.0;
            adverse_selection_ratios_[symbol_id] = 0.0;
            quote_counts_[symbol_id] = 0;
            fill_counts_[symbol_id] = 0;
        }
    }
    
    void onMarketData(const MarketDataEvent& event) override {
        if (state_ != StrategyState::RUNNING) return;
        
        uint32_t symbol_id = event.symbol_id;
        
        // Update market data
        updateMarketData(event);
        
        // Update volatility estimates
        updateVolatilityEstimate(symbol_id, event.price);
        
        // Check if we need to refresh quotes
        uint64_t current_time = getCurrentTimeNs();
        if (current_time - last_quote_update_ns_ > params_.quote_refresh_interval_ns) {
            updateQuotes(symbol_id);
            last_quote_update_ns_ = current_time;
        }
        
        // Check for adverse selection
        checkAdverseSelection(symbol_id);
    }
    
    void onOrderFill(const Order& order) override {
        uint32_t symbol_id = order.symbol_id;
        
        // Update inventory
        updateInventory(symbol_id, order);
        
        // Update performance metrics
        updateMetrics(order);
        
        // Cancel opposite side quote if inventory limit reached
        manageInventoryRisk(symbol_id);
        
        // Generate new quotes
        updateQuotes(symbol_id);
    }
    
    void onTick() override {
        if (state_ != StrategyState::RUNNING) return;
        
        // Periodic maintenance
        uint64_t current_time = getCurrentTimeNs();
        
        // Update quotes periodically
        if (current_time - last_quote_update_ns_ > params_.quote_refresh_interval_ns) {
            for (uint32_t symbol_id : config_.target_symbols) {
                updateQuotes(symbol_id);
            }
            last_quote_update_ns_ = current_time;
        }
        
        // Update performance metrics
        updatePerformanceMetrics();
    }
    
    void shutdown() override {
        // Cancel all active quotes
        for (auto& [symbol_id, quote] : active_quotes_) {
            cancelQuote(symbol_id);
        }
        active_quotes_.clear();
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
        InventoryInfo& inv = inventory_[symbol_id];
        
        // Update average price
        if (inv.quantity == 0) {
            inv.average_price = price;
        } else {
            double total_cost = inv.average_price * inv.quantity + price * quantity;
            inv.quantity += quantity;
            if (inv.quantity != 0) {
                inv.average_price = total_cost / inv.quantity;
            }
        }
        
        inv.last_update_ns = getCurrentTimeNs();
        
        // Update unrealized P&L
        double current_price = getLastPrice(symbol_id);
        inv.unrealized_pnl = (current_price - inv.average_price) * inv.quantity;
    }
    
    Position getPosition(uint32_t symbol_id) const override {
        auto it = inventory_.find(symbol_id);
        if (it != inventory_.end()) {
            const InventoryInfo& inv = it->second;
            return {symbol_id, inv.quantity, inv.average_price, inv.unrealized_pnl};
        }
        return {symbol_id, 0, 0.0, 0.0};
    }
    
    double getUnrealizedPnL() const override {
        double total_pnl = 0.0;
        for (const auto& [symbol_id, inv] : inventory_) {
            total_pnl += inv.unrealized_pnl;
        }
        return total_pnl;
    }
    
    bool shouldTrade(const TradingSignal& signal) override {
        uint32_t symbol_id = signal.symbol_id;
        
        // Check if we have market data
        if (last_prices_.find(symbol_id) == last_prices_.end()) {
            return false;
        }
        
        // Check adverse selection
        if (adverse_selection_ratios_[symbol_id] > params_.adverse_selection_threshold) {
            return false;
        }
        
        // Check inventory limits
        const InventoryInfo& inv = inventory_[symbol_id];
        double proposed_quantity = signal.suggested_quantity;
        
        if (signal.signal_strength > 0) { // Buy signal
            if (inv.quantity + proposed_quantity > getMaxInventory(symbol_id)) {
                return false;
            }
        } else { // Sell signal
            if (inv.quantity - proposed_quantity < -getMaxInventory(symbol_id)) {
                return false;
            }
        }
        
        return true;
    }
    
    double calculatePositionSize(const TradingSignal& signal) override {
        uint32_t symbol_id = signal.symbol_id;
        
        // Base size calculation
        double base_size = params_.min_quote_size;
        
        // Adjust based on volatility
        double volatility = volatility_estimates_[symbol_id];
        double volatility_multiplier = std::max(0.5, 1.0 - volatility * 10.0);
        
        // Adjust based on current inventory
        const InventoryInfo& inv = inventory_[symbol_id];
        double inventory_ratio = std::abs(inv.quantity) / getMaxInventory(symbol_id);
        double inventory_multiplier = std::max(0.1, 1.0 - inventory_ratio);
        
        double adjusted_size = base_size * volatility_multiplier * inventory_multiplier;
        
        return std::min(adjusted_size, static_cast<double>(params_.max_quote_size));
    }
    
    bool checkRiskLimits() override {
        // Check total portfolio exposure
        double total_exposure = getCurrentExposure();
        if (total_exposure > config_.max_position_size) {
            return false;
        }
        
        // Check daily P&L
        double daily_pnl = metrics_.realized_pnl.load();
        if (daily_pnl < -config_.max_daily_loss) {
            return false;
        }
        
        return true;
    }

private:
    void loadParameters() {
        // Load parameters from config
        for (const auto& param : config_.parameters) {
            parseParameter(param);
        }
    }
    
    void parseParameter(const std::string& param) {
        // Parse parameter string (format: "key=value")
        size_t pos = param.find('=');
        if (pos != std::string::npos) {
            std::string key = param.substr(0, pos);
            std::string value = param.substr(pos + 1);
            
            if (key == "spread_capture_ratio") {
                params_.spread_capture_ratio = std::stod(value);
            } else if (key == "max_inventory_ratio") {
                params_.max_inventory_ratio = std::stod(value);
            } else if (key == "min_quote_size") {
                params_.min_quote_size = std::stoul(value);
            } else if (key == "max_quote_size") {
                params_.max_quote_size = std::stoul(value);
            }
        }
    }
    
    void updateMarketData(const MarketDataEvent& event) {
        uint32_t symbol_id = event.symbol_id;
        
        last_prices_[symbol_id] = event.price;
        
        if (event.side == 1) { // Bid
            bid_prices_[symbol_id] = event.price;
            bid_sizes_[symbol_id] = event.quantity;
        } else { // Ask
            ask_prices_[symbol_id] = event.price;
            ask_sizes_[symbol_id] = event.quantity;
        }
        
        // Update price history
        auto& history = price_history_[symbol_id];
        history.push_back(event.price);
        if (history.size() > 1000) {
            history.pop_front();
        }
    }
    
    void updateVolatilityEstimate(uint32_t symbol_id, double price) {
        auto& history = return_history_[symbol_id];
        
        if (!history.empty()) {
            double return_val = std::log(price / history.back());
            history.push_back(return_val);
            
            if (history.size() > 100) {
                history.pop_front();
            }
            
            // Calculate volatility (standard deviation of returns)
            if (history.size() >= 20) {
                double mean = 0.0;
                for (double ret : history) {
                    mean += ret;
                }
                mean /= history.size();
                
                double variance = 0.0;
                for (double ret : history) {
                    variance += (ret - mean) * (ret - mean);
                }
                variance /= (history.size() - 1);
                
                volatility_estimates_[symbol_id] = std::sqrt(variance);
            }
        } else {
            history.push_back(price);
        }
    }
    
    void updateQuotes(uint32_t symbol_id) {
        // Get current market data
        double bid = getBidPrice(symbol_id);
        double ask = getAskPrice(symbol_id);
        double last_price = getLastPrice(symbol_id);
        
        if (bid <= 0 || ask <= 0 || last_price <= 0) {
            return; // No valid market data
        }
        
        double spread = ask - bid;
        if (spread <= 0) {
            return; // Invalid spread
        }
        
        // Calculate our quotes
        auto [our_bid, our_ask] = calculateQuotePrices(symbol_id, bid, ask, spread);
        auto [bid_size, ask_size] = calculateQuoteSizes(symbol_id);
        
        // Generate trading signals for quotes
        generateQuoteSignals(symbol_id, our_bid, our_ask, bid_size, ask_size);
    }
    
    std::pair<double, double> calculateQuotePrices(uint32_t symbol_id, double bid, double ask, double spread) {
        double mid_price = (bid + ask) / 2.0;
        double target_spread = spread * params_.spread_capture_ratio;
        
        // Apply inventory skew
        const InventoryInfo& inv = inventory_[symbol_id];
        double max_inventory = getMaxInventory(symbol_id);
        double inventory_skew = 0.0;
        
        if (max_inventory > 0) {
            double inventory_ratio = inv.quantity / max_inventory;
            inventory_skew = inventory_ratio * params_.skew_adjustment * spread;
        }
        
        // Apply volatility adjustment
        double volatility = volatility_estimates_[symbol_id];
        double volatility_adjustment = volatility * params_.volatility_adjustment * spread;
        
        double adjusted_spread = target_spread + volatility_adjustment;
        
        double our_bid = mid_price - adjusted_spread / 2.0 + inventory_skew;
        double our_ask = mid_price + adjusted_spread / 2.0 + inventory_skew;
        
        // Round to tick size
        our_bid = std::floor(our_bid / params_.tick_size) * params_.tick_size;
        our_ask = std::ceil(our_ask / params_.tick_size) * params_.tick_size;
        
        return {our_bid, our_ask};
    }
    
    std::pair<uint32_t, uint32_t> calculateQuoteSizes(uint32_t symbol_id) {
        const InventoryInfo& inv = inventory_[symbol_id];
        double max_inventory = getMaxInventory(symbol_id);
        
        uint32_t base_size = params_.min_quote_size;
        
        // Adjust size based on inventory
        double inventory_ratio = std::abs(inv.quantity) / max_inventory;
        double size_multiplier = std::max(0.1, 1.0 - inventory_ratio);
        
        uint32_t bid_size = static_cast<uint32_t>(base_size * size_multiplier);
        uint32_t ask_size = static_cast<uint32_t>(base_size * size_multiplier);
        
        // If we have too much inventory, reduce size on that side
        if (inv.quantity > max_inventory * 0.8) {
            bid_size = std::max(params_.min_quote_size / 2, bid_size / 2);
        } else if (inv.quantity < -max_inventory * 0.8) {
            ask_size = std::max(params_.min_quote_size / 2, ask_size / 2);
        }
        
        return {bid_size, ask_size};
    }
    
    void generateQuoteSignals(uint32_t symbol_id, double bid_price, double ask_price, 
                             uint32_t bid_size, uint32_t ask_size) {
        uint64_t current_time = getCurrentTimeNs();
        
        // Generate bid signal
        if (bid_size > 0) {
            TradingSignal bid_signal{};
            bid_signal.timestamp_ns = current_time;
            bid_signal.symbol_id = symbol_id;
            bid_signal.strategy_id = config_.strategy_id;
            bid_signal.signal_strength = -1.0; // Sell signal (provide liquidity)
            bid_signal.confidence = 0.8;
            bid_signal.suggested_quantity = bid_size;
            bid_signal.suggested_price_ticks = static_cast<uint32_t>(bid_price / params_.tick_size);
            bid_signal.urgency = 100; // Low urgency for limit orders
            bid_signal.signal_type = 1; // Entry signal
            
            pending_signals_.push_back(bid_signal);
        }
        
        // Generate ask signal
        if (ask_size > 0) {
            TradingSignal ask_signal{};
            ask_signal.timestamp_ns = current_time;
            ask_signal.symbol_id = symbol_id;
            ask_signal.strategy_id = config_.strategy_id;
            ask_signal.signal_strength = 1.0; // Buy signal (provide liquidity)
            ask_signal.confidence = 0.8;
            ask_signal.suggested_quantity = ask_size;
            ask_signal.suggested_price_ticks = static_cast<uint32_t>(ask_price / params_.tick_size);
            ask_signal.urgency = 100;
            ask_signal.signal_type = 1;
            
            pending_signals_.push_back(ask_signal);
        }
    }
    
    void updateInventory(uint32_t symbol_id, const Order& order) {
        InventoryInfo& inv = inventory_[symbol_id];
        
        int32_t quantity_change = (order.side == 1) ? order.quantity : -order.quantity;
        
        // Update position
        updatePosition(symbol_id, quantity_change, order.price_ticks * params_.tick_size);
        
        // Update fill count
        fill_counts_[symbol_id]++;
    }
    
    void manageInventoryRisk(uint32_t symbol_id) {
        const InventoryInfo& inv = inventory_[symbol_id];
        double max_inventory = getMaxInventory(symbol_id);
        
        // If inventory is too high, cancel quotes on that side
        if (std::abs(inv.quantity) > max_inventory * 0.9) {
            cancelQuote(symbol_id);
        }
    }
    
    void checkAdverseSelection(uint32_t symbol_id) {
        // Simple adverse selection check
        // In production, this would be more sophisticated
        uint64_t quote_count = quote_counts_[symbol_id];
        uint64_t fill_count = fill_counts_[symbol_id];
        
        if (quote_count > 0) {
            double fill_ratio = static_cast<double>(fill_count) / quote_count;
            adverse_selection_ratios_[symbol_id] = fill_ratio;
        }
    }
    
    void cancelQuote(uint32_t symbol_id) {
        auto it = active_quotes_.find(symbol_id);
        if (it != active_quotes_.end()) {
            it->second.is_active = false;
        }
    }
    
    double getMaxInventory(uint32_t symbol_id) const {
        // Calculate max inventory based on daily volume and parameters
        // For now, use a simple fixed value
        return 10000.0 * params_.max_inventory_ratio;
    }
    
    double getBidPrice(uint32_t symbol_id) const {
        auto it = bid_prices_.find(symbol_id);
        return (it != bid_prices_.end()) ? it->second : 0.0;
    }
    
    double getAskPrice(uint32_t symbol_id) const {
        auto it = ask_prices_.find(symbol_id);
        return (it != ask_prices_.end()) ? it->second : 0.0;
    }
    
    double getLastPrice(uint32_t symbol_id) const {
        auto it = last_prices_.find(symbol_id);
        return (it != last_prices_.end()) ? it->second : 0.0;
    }
    
    uint64_t getCurrentTimeNs() const {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::high_resolution_clock::now().time_since_epoch()).count();
    }
    
    double getCurrentExposure() const {
        double total_exposure = 0.0;
        for (const auto& [symbol_id, inv] : inventory_) {
            total_exposure += std::abs(inv.quantity * getLastPrice(symbol_id));
        }
        return total_exposure;
    }
};

} // namespace HFT