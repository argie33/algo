/**
 * Strategy Manager - Orchestrates multiple trading strategies
 * Handles allocation, risk management, and coordination
 */

#include "base_strategy.h"
#include "strategy_factory.cpp"
#include <memory>
#include <vector>
#include <unordered_map>
#include <atomic>
#include <thread>
#include <mutex>

namespace HFT {

// Strategy allocation and performance tracking
struct StrategyAllocation {
    std::unique_ptr<BaseStrategy> strategy;
    double capital_allocation;      // Dollar amount allocated
    double max_drawdown_limit;      // Strategy-specific drawdown limit
    double daily_loss_limit;        // Daily loss limit for this strategy
    bool is_enabled;               // Can be disabled dynamically
    uint64_t last_signal_time;     // For signal rate monitoring
    double realized_pnl_today;     // Daily P&L tracking
    uint32_t signal_count_today;   // Signal frequency tracking
    double allocation_utilization; // How much of allocation is used
};

// Portfolio-level risk metrics
struct PortfolioRisk {
    std::atomic<double> total_gross_exposure{0.0};
    std::atomic<double> total_net_exposure{0.0};
    std::atomic<double> total_realized_pnl{0.0};
    std::atomic<double> total_unrealized_pnl{0.0};
    std::atomic<double> portfolio_var{0.0};
    std::atomic<uint32_t> active_strategies{0};
    std::atomic<uint32_t> total_positions{0};
    std::atomic<bool> emergency_stop{false};
};

class StrategyManager {
private:
    std::vector<StrategyAllocation> strategy_allocations_;
    PortfolioRisk portfolio_risk_;
    
    // Configuration
    struct ManagerConfig {
        double total_capital = 1000000.0;      // $1M total capital
        double max_portfolio_drawdown = 0.05;   // 5% max portfolio drawdown
        double max_strategy_correlation = 0.7;  // Max correlation between strategies
        uint32_t max_concurrent_strategies = 5; // Max active strategies
        double emergency_stop_loss = 0.02;     // 2% emergency stop
        bool dynamic_allocation = true;         // Enable dynamic reallocation
        uint64_t rebalance_interval_ns = 3600000000000; // 1 hour rebalance
    };
    
    ManagerConfig config_;
    
    // Threading and synchronization
    std::mutex strategy_mutex_;
    std::thread management_thread_;
    std::atomic<bool> running_{false};
    
    // Performance tracking
    double portfolio_high_water_mark_ = 0.0;
    uint64_t last_rebalance_time_ = 0;
    std::unordered_map<uint32_t, double> strategy_correlations_;
    
public:
    StrategyManager(const ManagerConfig& config = ManagerConfig{}) 
        : config_(config) {
    }
    
    ~StrategyManager() {
        stop();
    }
    
    // Add a strategy to the portfolio
    bool addStrategy(const std::string& strategy_name, 
                    const StrategyConfig& config,
                    double capital_allocation = 0.2) {
        
        std::lock_guard<std::mutex> lock(strategy_mutex_);
        
        // Check if we can add more strategies
        if (strategy_allocations_.size() >= config_.max_concurrent_strategies) {
            return false;
        }
        
        // Create strategy
        auto strategy_type = StrategyFactory::getStrategyType(strategy_name);
        auto strategy = StrategyFactory::createStrategy(strategy_type, config);
        
        if (!strategy) {
            return false;
        }
        
        // Create allocation
        StrategyAllocation allocation;
        allocation.strategy = std::move(strategy);
        allocation.capital_allocation = capital_allocation * config_.total_capital;
        allocation.max_drawdown_limit = 0.03; // 3% per strategy
        allocation.daily_loss_limit = allocation.capital_allocation * 0.01; // 1% daily
        allocation.is_enabled = true;
        allocation.last_signal_time = 0;
        allocation.realized_pnl_today = 0.0;
        allocation.signal_count_today = 0;
        allocation.allocation_utilization = 0.0;
        
        strategy_allocations_.push_back(std::move(allocation));
        
        return true;
    }
    
    // Start the strategy manager
    void start() {
        running_ = true;
        
        // Initialize all strategies
        for (auto& allocation : strategy_allocations_) {
            allocation.strategy->start();
        }
        
        // Start management thread
        management_thread_ = std::thread([this]() {
            runManagementLoop();
        });
        
        portfolio_risk_.active_strategies = strategy_allocations_.size();
    }
    
    // Stop the strategy manager
    void stop() {
        running_ = false;
        
        // Stop all strategies
        for (auto& allocation : strategy_allocations_) {
            allocation.strategy->stop();
        }
        
        if (management_thread_.joinable()) {
            management_thread_.join();
        }
    }
    
    // Process market data for all strategies
    void onMarketData(const MarketDataEvent& event) {
        if (!running_ || portfolio_risk_.emergency_stop.load()) {
            return;
        }
        
        std::lock_guard<std::mutex> lock(strategy_mutex_);
        
        for (auto& allocation : strategy_allocations_) {
            if (allocation.is_enabled) {
                allocation.strategy->onMarketData(event);
            }
        }
        
        // Update portfolio metrics
        updatePortfolioMetrics();
    }
    
    // Process order fills for all strategies
    void onOrderFill(const Order& order) {
        std::lock_guard<std::mutex> lock(strategy_mutex_);
        
        // Find which strategy owns this order
        for (auto& allocation : strategy_allocations_) {
            if (allocation.strategy->getStrategyId() == order.strategy_id) {
                allocation.strategy->onOrderFill(order);
                
                // Update strategy P&L tracking
                updateStrategyPnL(allocation, order);
                break;
            }
        }
    }
    
    // Collect signals from all strategies
    std::vector<TradingSignal> collectSignals() {
        std::vector<TradingSignal> all_signals;
        
        if (!running_ || portfolio_risk_.emergency_stop.load()) {
            return all_signals;
        }
        
        std::lock_guard<std::mutex> lock(strategy_mutex_);
        
        for (auto& allocation : strategy_allocations_) {
            if (!allocation.is_enabled) continue;
            
            // Check risk limits before allowing signals
            if (!checkStrategyRiskLimits(allocation)) {
                continue;
            }
            
            while (allocation.strategy->hasSignal()) {
                TradingSignal signal = allocation.strategy->getSignal();
                
                // Apply position sizing based on allocation
                signal.suggested_quantity = static_cast<uint32_t>(
                    signal.suggested_quantity * calculateAllocationMultiplier(allocation)
                );
                
                if (signal.suggested_quantity > 0) {
                    all_signals.push_back(signal);
                    allocation.signal_count_today++;
                    allocation.last_signal_time = getCurrentTimeNs();
                }
            }
        }
        
        return all_signals;
    }
    
    // Get portfolio performance summary
    struct PortfolioSummary {
        double total_pnl;
        double total_exposure;
        double drawdown;
        uint32_t active_strategies;
        uint32_t total_signals_today;
        double best_strategy_pnl;
        double worst_strategy_pnl;
        std::string best_strategy_name;
        std::string worst_strategy_name;
    };
    
    PortfolioSummary getPortfolioSummary() const {
        PortfolioSummary summary{};
        
        summary.total_pnl = portfolio_risk_.total_realized_pnl.load() + 
                           portfolio_risk_.total_unrealized_pnl.load();
        summary.total_exposure = portfolio_risk_.total_gross_exposure.load();
        summary.drawdown = calculatePortfolioDrawdown();
        summary.active_strategies = portfolio_risk_.active_strategies.load();
        
        double best_pnl = -std::numeric_limits<double>::max();
        double worst_pnl = std::numeric_limits<double>::max();
        
        for (const auto& allocation : strategy_allocations_) {
            double strategy_pnl = allocation.realized_pnl_today + 
                                allocation.strategy->getUnrealizedPnL();
            
            summary.total_signals_today += allocation.signal_count_today;
            
            if (strategy_pnl > best_pnl) {
                best_pnl = strategy_pnl;
                summary.best_strategy_name = allocation.strategy->getName();
            }
            
            if (strategy_pnl < worst_pnl) {
                worst_pnl = strategy_pnl;
                summary.worst_strategy_name = allocation.strategy->getName();
            }
        }
        
        summary.best_strategy_pnl = best_pnl;
        summary.worst_strategy_pnl = worst_pnl;
        
        return summary;
    }
    
    // Emergency stop all strategies
    void emergencyStop(const std::string& reason) {
        portfolio_risk_.emergency_stop.store(true);
        
        std::lock_guard<std::mutex> lock(strategy_mutex_);
        for (auto& allocation : strategy_allocations_) {
            allocation.strategy->stop();
            allocation.is_enabled = false;
        }
    }
    
    // Enable/disable specific strategy
    void setStrategyEnabled(uint32_t strategy_id, bool enabled) {
        std::lock_guard<std::mutex> lock(strategy_mutex_);
        
        for (auto& allocation : strategy_allocations_) {
            if (allocation.strategy->getStrategyId() == strategy_id) {
                allocation.is_enabled = enabled;
                
                if (enabled) {
                    allocation.strategy->resume();
                } else {
                    allocation.strategy->pause();
                }
                break;
            }
        }
    }

private:
    void runManagementLoop() {
        while (running_) {
            // Portfolio risk monitoring
            checkPortfolioRisk();
            
            // Strategy performance monitoring
            monitorStrategyPerformance();
            
            // Dynamic reallocation if enabled
            if (config_.dynamic_allocation) {
                considerReallocation();
            }
            
            // Sleep for 1 second
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    }
    
    void checkPortfolioRisk() {
        updatePortfolioMetrics();
        
        // Check emergency stop conditions
        double portfolio_pnl = portfolio_risk_.total_realized_pnl.load() + 
                              portfolio_risk_.total_unrealized_pnl.load();
        
        double portfolio_loss_pct = -portfolio_pnl / config_.total_capital;
        
        if (portfolio_loss_pct > config_.emergency_stop_loss) {
            emergencyStop("Portfolio loss limit exceeded");
            return;
        }
        
        // Check drawdown
        double drawdown = calculatePortfolioDrawdown();
        if (drawdown > config_.max_portfolio_drawdown) {
            emergencyStop("Portfolio drawdown limit exceeded");
            return;
        }
    }
    
    void monitorStrategyPerformance() {
        std::lock_guard<std::mutex> lock(strategy_mutex_);
        
        for (auto& allocation : strategy_allocations_) {
            if (!allocation.is_enabled) continue;
            
            // Check strategy risk limits
            double strategy_pnl = allocation.realized_pnl_today + 
                                allocation.strategy->getUnrealizedPnL();
            
            // Disable strategy if it hits limits
            if (strategy_pnl < -allocation.daily_loss_limit) {
                allocation.is_enabled = false;
                allocation.strategy->pause();
                continue;
            }
            
            // Check drawdown
            double strategy_drawdown = allocation.strategy->getMaxDrawdown();
            if (strategy_drawdown > allocation.max_drawdown_limit) {
                allocation.is_enabled = false;
                allocation.strategy->pause();
                continue;
            }
            
            // Monitor signal frequency (avoid over-trading)
            uint64_t time_since_signal = getCurrentTimeNs() - allocation.last_signal_time;
            if (allocation.signal_count_today > 1000) { // Too many signals
                allocation.is_enabled = false;
                allocation.strategy->pause();
            }
        }
    }
    
    void considerReallocation() {
        uint64_t current_time = getCurrentTimeNs();
        
        if (current_time - last_rebalance_time_ < config_.rebalance_interval_ns) {
            return;
        }
        
        // Calculate strategy performance over rebalancing period
        std::vector<double> strategy_returns;
        std::vector<double> strategy_sharpes;
        
        {
            std::lock_guard<std::mutex> lock(strategy_mutex_);
            
            for (const auto& allocation : strategy_allocations_) {
                double strategy_return = allocation.realized_pnl_today / allocation.capital_allocation;
                double sharpe_ratio = allocation.strategy->getSharpeRatio();
                
                strategy_returns.push_back(strategy_return);
                strategy_sharpes.push_back(sharpe_ratio);
            }
        }
        
        // Reallocate based on performance (simple equal-weight for now)
        // In production, this would use more sophisticated optimization
        
        last_rebalance_time_ = current_time;
    }
    
    void updatePortfolioMetrics() {
        double total_realized = 0.0;
        double total_unrealized = 0.0;
        double total_gross_exposure = 0.0;
        double total_net_exposure = 0.0;
        uint32_t total_positions = 0;
        uint32_t active_count = 0;
        
        for (const auto& allocation : strategy_allocations_) {
            if (allocation.is_enabled) {
                active_count++;
                
                const auto& metrics = allocation.strategy->getMetrics();
                total_realized += metrics.realized_pnl.load();
                total_unrealized += allocation.strategy->getUnrealizedPnL();
                
                // Calculate exposures (simplified)
                for (uint32_t symbol_id : allocation.strategy->getConfig().target_symbols) {
                    Position pos = allocation.strategy->getPosition(symbol_id);
                    if (pos.quantity != 0) {
                        total_positions++;
                        double position_value = std::abs(pos.quantity * pos.average_price);
                        total_gross_exposure += position_value;
                        total_net_exposure += pos.quantity * pos.average_price;
                    }
                }
            }
        }
        
        portfolio_risk_.total_realized_pnl.store(total_realized);
        portfolio_risk_.total_unrealized_pnl.store(total_unrealized);
        portfolio_risk_.total_gross_exposure.store(total_gross_exposure);
        portfolio_risk_.total_net_exposure.store(total_net_exposure);
        portfolio_risk_.total_positions.store(total_positions);
        portfolio_risk_.active_strategies.store(active_count);
    }
    
    bool checkStrategyRiskLimits(const StrategyAllocation& allocation) {
        // Check daily loss limit
        double strategy_pnl = allocation.realized_pnl_today + 
                            allocation.strategy->getUnrealizedPnL();
        
        if (strategy_pnl < -allocation.daily_loss_limit) {
            return false;
        }
        
        // Check allocation utilization
        double current_exposure = 0.0;
        for (uint32_t symbol_id : allocation.strategy->getConfig().target_symbols) {
            Position pos = allocation.strategy->getPosition(symbol_id);
            current_exposure += std::abs(pos.quantity * pos.average_price);
        }
        
        double utilization = current_exposure / allocation.capital_allocation;
        if (utilization > 1.2) { // 120% max utilization
            return false;
        }
        
        return true;
    }
    
    double calculateAllocationMultiplier(const StrategyAllocation& allocation) {
        // Adjust position size based on strategy performance and allocation
        double base_multiplier = allocation.capital_allocation / config_.total_capital;
        
        // Reduce size if strategy is underperforming
        double strategy_return = allocation.realized_pnl_today / allocation.capital_allocation;
        double performance_multiplier = std::max(0.5, 1.0 + strategy_return);
        
        return base_multiplier * performance_multiplier;
    }
    
    void updateStrategyPnL(StrategyAllocation& allocation, const Order& order) {
        if (order.status == 3) { // Filled
            // This is simplified - in practice, P&L calculation is more complex
            // Real implementation would track entry/exit prices properly
        }
    }
    
    double calculatePortfolioDrawdown() const {
        double current_value = portfolio_risk_.total_realized_pnl.load() + 
                              portfolio_risk_.total_unrealized_pnl.load();
        
        if (portfolio_high_water_mark_ > 0) {
            return (portfolio_high_water_mark_ - current_value) / portfolio_high_water_mark_;
        }
        
        return 0.0;
    }
    
    uint64_t getCurrentTimeNs() const {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::high_resolution_clock::now().time_since_epoch()).count();
    }
};

} // namespace HFT