/**
 * Base Strategy Interface for HFT System
 * Defines the interface for all trading strategies
 */

#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <vector>
#include <atomic>
#include "market_data_handler_aws.h"

namespace HFT {

// Forward declarations
struct TradingSignal;
struct Position;
struct Order;

// Strategy performance metrics
struct StrategyMetrics {
    std::atomic<uint64_t> signals_generated{0};
    std::atomic<uint64_t> orders_executed{0};
    std::atomic<double> realized_pnl{0.0};
    std::atomic<double> unrealized_pnl{0.0};
    std::atomic<double> max_drawdown{0.0};
    std::atomic<double> sharpe_ratio{0.0};
    std::atomic<double> win_rate{0.0};
    std::atomic<uint64_t> total_trades{0};
    std::atomic<uint64_t> winning_trades{0};
    std::atomic<uint64_t> losing_trades{0};
};

// Strategy configuration
struct StrategyConfig {
    std::string name;
    uint32_t strategy_id;
    double max_position_size;
    double max_daily_loss;
    double risk_multiplier;
    bool enabled;
    std::vector<uint32_t> target_symbols;
    std::vector<std::string> parameters;
};

// Strategy state
enum class StrategyState : uint8_t {
    STOPPED = 0,
    RUNNING = 1,
    PAUSED = 2,
    ERROR = 3
};

/**
 * Base Strategy Class
 * All trading strategies must inherit from this class
 */
class BaseStrategy {
protected:
    StrategyConfig config_;
    StrategyMetrics metrics_;
    std::atomic<StrategyState> state_{StrategyState::STOPPED};
    
    // Strategy-specific data
    std::vector<TradingSignal> pending_signals_;
    std::vector<Position> positions_;
    uint64_t last_signal_time_ns_{0};
    
    // Performance tracking
    double high_water_mark_{0.0};
    std::vector<double> daily_returns_;
    
public:
    BaseStrategy(const StrategyConfig& config) : config_(config) {}
    virtual ~BaseStrategy() = default;
    
    // Core strategy interface
    virtual void initialize() = 0;
    virtual void onMarketData(const MarketDataEvent& event) = 0;
    virtual void onOrderFill(const Order& order) = 0;
    virtual void onTick() = 0;
    virtual void shutdown() = 0;
    
    // Signal management
    virtual bool hasSignal() const = 0;
    virtual TradingSignal getSignal() = 0;
    virtual void clearSignals() = 0;
    
    // Position management
    virtual void updatePosition(uint32_t symbol_id, int32_t quantity, double price) = 0;
    virtual Position getPosition(uint32_t symbol_id) const = 0;
    virtual double getUnrealizedPnL() const = 0;
    
    // Risk management
    virtual bool shouldTrade(const TradingSignal& signal) = 0;
    virtual double calculatePositionSize(const TradingSignal& signal) = 0;
    virtual bool checkRiskLimits() = 0;
    
    // State management
    void start() {
        if (state_ == StrategyState::STOPPED) {
            initialize();
            state_ = StrategyState::RUNNING;
        }
    }
    
    void stop() {
        if (state_ != StrategyState::STOPPED) {
            shutdown();
            state_ = StrategyState::STOPPED;
        }
    }
    
    void pause() {
        if (state_ == StrategyState::RUNNING) {
            state_ = StrategyState::PAUSED;
        }
    }
    
    void resume() {
        if (state_ == StrategyState::PAUSED) {
            state_ = StrategyState::RUNNING;
        }
    }
    
    // Getters
    const StrategyConfig& getConfig() const { return config_; }
    const StrategyMetrics& getMetrics() const { return metrics_; }
    StrategyState getState() const { return state_.load(); }
    uint32_t getStrategyId() const { return config_.strategy_id; }
    const std::string& getName() const { return config_.name; }
    
    // Performance metrics
    double getSharpeRatio() const { return metrics_.sharpe_ratio.load(); }
    double getWinRate() const { return metrics_.win_rate.load(); }
    double getMaxDrawdown() const { return metrics_.max_drawdown.load(); }
    double getRealizedPnL() const { return metrics_.realized_pnl.load(); }
    double getUnrealizedPnL() const { return metrics_.unrealized_pnl.load(); }
    
protected:
    // Helper methods for derived strategies
    void updateMetrics(const Order& order);
    void updatePerformanceMetrics();
    void recordSignal(const TradingSignal& signal);
    double calculateSharpeRatio() const;
    bool isWithinRiskLimits(double proposed_position_size) const;
    
    // Time utilities
    uint64_t getCurrentTimeNs() const;
    uint64_t getTimeSinceLastSignal() const;
    
    // Market data utilities
    double getLastPrice(uint32_t symbol_id) const;
    double getBidPrice(uint32_t symbol_id) const;
    double getAskPrice(uint32_t symbol_id) const;
    double getSpread(uint32_t symbol_id) const;
    
    // Position utilities
    double getCurrentExposure() const;
    bool hasPosition(uint32_t symbol_id) const;
    int32_t getPositionQuantity(uint32_t symbol_id) const;
};

/**
 * Strategy Factory
 * Creates strategy instances based on configuration
 */
class StrategyFactory {
public:
    enum class StrategyType {
        MARKET_MAKING = 1,
        STATISTICAL_ARBITRAGE = 2,
        MOMENTUM = 3,
        MEAN_REVERSION = 4,
        ML_ALPHA = 5,
        CUSTOM = 99
    };
    
    static std::unique_ptr<BaseStrategy> createStrategy(
        StrategyType type,
        const StrategyConfig& config
    );
    
    static std::vector<std::string> getAvailableStrategies();
    static StrategyType getStrategyType(const std::string& name);
};

} // namespace HFT