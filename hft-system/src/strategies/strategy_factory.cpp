/**
 * Strategy Factory Implementation
 * Creates and manages trading strategy instances
 */

#include "base_strategy.h"
#include "scalping_strategy.cpp"
#include "momentum_strategy.cpp"
#include "mean_reversion_strategy.cpp"
#include <memory>
#include <stdexcept>

namespace HFT {

std::unique_ptr<BaseStrategy> StrategyFactory::createStrategy(
    StrategyType type,
    const StrategyConfig& config
) {
    switch (type) {
        case StrategyType::SCALPING:
            return std::make_unique<ScalpingStrategy>(config);
        
        case StrategyType::MOMENTUM:
            return std::make_unique<MomentumStrategy>(config);
        
        case StrategyType::MEAN_REVERSION:
            return std::make_unique<MeanReversionStrategy>(config);
        
        case StrategyType::STATISTICAL_ARBITRAGE:
            // Placeholder - could implement stat arb strategy
            throw std::runtime_error("Statistical arbitrage strategy not implemented");
        
        case StrategyType::ML_ALPHA:
            // Placeholder - could implement ML-based strategy
            throw std::runtime_error("ML alpha strategy not implemented");
        
        default:
            throw std::runtime_error("Unknown strategy type");
    }
}

std::vector<std::string> StrategyFactory::getAvailableStrategies() {
    return {
        "scalping",
        "momentum", 
        "mean_reversion",
        "statistical_arbitrage",
        "ml_alpha"
    };
}

StrategyFactory::StrategyType StrategyFactory::getStrategyType(const std::string& name) {
    if (name == "scalping") {
        return StrategyType::SCALPING;
    } else if (name == "momentum") {
        return StrategyType::MOMENTUM;
    } else if (name == "mean_reversion") {
        return StrategyType::MEAN_REVERSION;
    } else if (name == "statistical_arbitrage") {
        return StrategyType::STATISTICAL_ARBITRAGE;
    } else if (name == "ml_alpha") {
        return StrategyType::ML_ALPHA;
    } else {
        return StrategyType::CUSTOM;
    }
}

// Helper methods for BaseStrategy
void BaseStrategy::updateMetrics(const Order& order) {
    if (order.status == 3) { // Filled
        metrics_.orders_executed++;
        
        // Calculate P&L if this is a closing order
        Position pos = getPosition(order.symbol_id);
        if (pos.quantity == 0) { // Position closed
            // P&L calculation would be done by derived strategy
            metrics_.total_trades++;
        }
    }
}

void BaseStrategy::updatePerformanceMetrics() {
    // Calculate win rate
    if (metrics_.total_trades > 0) {
        double win_rate = static_cast<double>(metrics_.winning_trades) / metrics_.total_trades;
        metrics_.win_rate.store(win_rate);
    }
    
    // Calculate Sharpe ratio
    double sharpe = calculateSharpeRatio();
    metrics_.sharpe_ratio.store(sharpe);
    
    // Update drawdown
    double current_pnl = metrics_.realized_pnl.load() + getUnrealizedPnL();
    if (current_pnl > high_water_mark_) {
        high_water_mark_ = current_pnl;
    }
    
    double drawdown = (high_water_mark_ - current_pnl) / std::max(high_water_mark_, 1.0);
    if (drawdown > metrics_.max_drawdown.load()) {
        metrics_.max_drawdown.store(drawdown);
    }
}

void BaseStrategy::recordSignal(const TradingSignal& signal) {
    metrics_.signals_generated++;
    last_signal_time_ns_ = signal.timestamp_ns;
}

double BaseStrategy::calculateSharpeRatio() const {
    if (daily_returns_.size() < 2) {
        return 0.0;
    }
    
    // Calculate mean and std dev of daily returns
    double mean_return = 0.0;
    for (double ret : daily_returns_) {
        mean_return += ret;
    }
    mean_return /= daily_returns_.size();
    
    double variance = 0.0;
    for (double ret : daily_returns_) {
        variance += (ret - mean_return) * (ret - mean_return);
    }
    variance /= (daily_returns_.size() - 1);
    
    double std_dev = std::sqrt(variance);
    
    // Assume risk-free rate of 2% annually (daily: 0.02/252)
    double risk_free_rate = 0.02 / 252.0;
    
    return std_dev > 0 ? (mean_return - risk_free_rate) / std_dev : 0.0;
}

bool BaseStrategy::isWithinRiskLimits(double proposed_position_size) const {
    // Check if proposed position exceeds limits
    double current_exposure = getCurrentExposure();
    return (current_exposure + proposed_position_size) <= config_.max_position_size;
}

uint64_t BaseStrategy::getCurrentTimeNs() const {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::high_resolution_clock::now().time_since_epoch()).count();
}

uint64_t BaseStrategy::getTimeSinceLastSignal() const {
    return getCurrentTimeNs() - last_signal_time_ns_;
}

double BaseStrategy::getLastPrice(uint32_t symbol_id) const {
    // This would be implemented by accessing market data
    // For now, return placeholder
    return 0.0;
}

double BaseStrategy::getBidPrice(uint32_t symbol_id) const {
    // This would be implemented by accessing market data
    return 0.0;
}

double BaseStrategy::getAskPrice(uint32_t symbol_id) const {
    // This would be implemented by accessing market data
    return 0.0;
}

double BaseStrategy::getSpread(uint32_t symbol_id) const {
    return getAskPrice(symbol_id) - getBidPrice(symbol_id);
}

double BaseStrategy::getCurrentExposure() const {
    // Calculate total exposure across all positions
    double total_exposure = 0.0;
    for (uint32_t symbol_id : config_.target_symbols) {
        Position pos = getPosition(symbol_id);
        total_exposure += std::abs(pos.quantity * pos.average_price);
    }
    return total_exposure;
}

bool BaseStrategy::hasPosition(uint32_t symbol_id) const {
    Position pos = getPosition(symbol_id);
    return pos.quantity != 0;
}

int32_t BaseStrategy::getPositionQuantity(uint32_t symbol_id) const {
    Position pos = getPosition(symbol_id);
    return pos.quantity;
}

} // namespace HFT