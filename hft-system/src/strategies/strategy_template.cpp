/**
 * HFT Strategy Template
 * 
 * This template provides the base structure for implementing
 * high-frequency trading strategies in the system.
 */

#ifndef HFT_STRATEGY_TEMPLATE_H
#define HFT_STRATEGY_TEMPLATE_H

#include <vector>
#include <memory>
#include <atomic>
#include <chrono>

namespace hft {
namespace strategies {

// Forward declarations
class MarketData;
class Order;
class Position;
class RiskManager;

/**
 * Base class for all HFT strategies
 */
class Strategy {
public:
    enum class StrategyState {
        INITIALIZING,
        READY,
        RUNNING,
        PAUSED,
        STOPPING,
        STOPPED
    };

    Strategy(const std::string& strategy_id, 
             std::shared_ptr<RiskManager> risk_manager);
    virtual ~Strategy() = default;

    // Core strategy lifecycle methods
    virtual void initialize() = 0;
    virtual void start() = 0;
    virtual void stop() = 0;
    virtual void pause() = 0;
    virtual void resume() = 0;

    // Market data callbacks
    virtual void on_market_data(const MarketData& data) = 0;
    virtual void on_order_book_update(const std::string& symbol, 
                                      const OrderBook& book) = 0;
    virtual void on_trade(const Trade& trade) = 0;

    // Order management callbacks
    virtual void on_order_accepted(const Order& order) = 0;
    virtual void on_order_rejected(const Order& order, 
                                   const std::string& reason) = 0;
    virtual void on_order_filled(const Order& order, 
                                 const Execution& execution) = 0;
    virtual void on_order_cancelled(const Order& order) = 0;

    // Position management
    virtual void update_position(const std::string& symbol, 
                                 int64_t quantity, 
                                 double avg_price) = 0;
    virtual double calculate_pnl() const = 0;

    // Risk management integration
    bool check_risk_limits(const Order& proposed_order);
    void update_risk_metrics();

    // Performance metrics
    struct PerformanceMetrics {
        uint64_t signals_generated;
        uint64_t orders_sent;
        uint64_t orders_filled;
        double total_pnl;
        double sharpe_ratio;
        std::chrono::nanoseconds avg_latency;
        std::chrono::nanoseconds max_latency;
    };

    PerformanceMetrics get_performance_metrics() const;

protected:
    // Helper methods for derived strategies
    void send_order(const Order& order);
    void cancel_order(const std::string& order_id);
    void modify_order(const std::string& order_id, 
                      const Order& new_order);

    // State management
    std::atomic<StrategyState> state_;
    
    // Strategy identification
    std::string strategy_id_;
    
    // Risk management
    std::shared_ptr<RiskManager> risk_manager_;
    
    // Position tracking
    std::unordered_map<std::string, Position> positions_;
    
    // Performance tracking
    mutable PerformanceMetrics metrics_;
    
    // Timing
    std::chrono::high_resolution_clock::time_point start_time_;
};

/**
 * Example Market Making Strategy Implementation
 */
class MarketMakingStrategy : public Strategy {
public:
    struct Parameters {
        double spread_bps;           // Spread in basis points
        int64_t max_position;        // Maximum position size
        double skew_factor;          // Price skew based on inventory
        int quote_levels;            // Number of price levels to quote
        double level_size_ratio;     // Size decay per level
        std::chrono::milliseconds quote_update_interval;
    };

    MarketMakingStrategy(const std::string& strategy_id,
                         std::shared_ptr<RiskManager> risk_manager,
                         const Parameters& params);

    // Strategy implementation
    void initialize() override;
    void start() override;
    void stop() override;
    void pause() override;
    void resume() override;

    // Market data handlers
    void on_market_data(const MarketData& data) override;
    void on_order_book_update(const std::string& symbol, 
                              const OrderBook& book) override;
    void on_trade(const Trade& trade) override;

    // Order callbacks
    void on_order_accepted(const Order& order) override;
    void on_order_rejected(const Order& order, 
                           const std::string& reason) override;
    void on_order_filled(const Order& order, 
                         const Execution& execution) override;
    void on_order_cancelled(const Order& order) override;

    // Position management
    void update_position(const std::string& symbol, 
                         int64_t quantity, 
                         double avg_price) override;
    double calculate_pnl() const override;

private:
    // Strategy-specific methods
    void update_quotes(const std::string& symbol);
    double calculate_fair_value(const OrderBook& book);
    double calculate_inventory_skew();
    void cancel_all_quotes();
    
    // Parameters
    Parameters params_;
    
    // Active orders
    std::unordered_map<std::string, std::vector<std::string>> active_orders_;
    
    // Market data cache
    std::unordered_map<std::string, OrderBook> order_books_;
    std::unordered_map<std::string, double> fair_values_;
    
    // Timing
    std::chrono::high_resolution_clock::time_point last_quote_update_;
};

/**
 * Example Statistical Arbitrage Strategy
 */
class StatisticalArbitrageStrategy : public Strategy {
public:
    struct Parameters {
        double entry_threshold;      // Z-score for entry
        double exit_threshold;       // Z-score for exit
        int lookback_period;         // Lookback for statistics
        double max_position_value;   // Maximum position value
        std::vector<std::pair<std::string, std::string>> pairs;
    };

    StatisticalArbitrageStrategy(const std::string& strategy_id,
                                 std::shared_ptr<RiskManager> risk_manager,
                                 const Parameters& params);

    // ... (implementation similar to above)

private:
    // Statistical calculations
    double calculate_zscore(const std::string& symbol1, 
                            const std::string& symbol2);
    void update_statistics();
    
    Parameters params_;
    
    // Price history for calculations
    std::unordered_map<std::string, std::deque<double>> price_history_;
    
    // Pair statistics
    struct PairStats {
        double mean_spread;
        double std_spread;
        double current_zscore;
        bool in_position;
    };
    std::unordered_map<std::string, PairStats> pair_stats_;
};

} // namespace strategies
} // namespace hft

#endif // HFT_STRATEGY_TEMPLATE_H