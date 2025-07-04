/**
 * Strategy Backtesting Framework
 * Tests trading strategies against historical data
 */

#include "../src/strategies/base_strategy.h"
#include "../src/strategies/strategy_factory.cpp"
#include <vector>
#include <fstream>
#include <sstream>
#include <chrono>
#include <iostream>
#include <iomanip>

namespace HFT {

// Backtest data point
struct BacktestDataPoint {
    uint64_t timestamp_ns;
    uint32_t symbol_id;
    double price;
    uint32_t volume;
    double bid;
    double ask;
};

// Backtest results
struct BacktestResults {
    double total_return;
    double sharpe_ratio;
    double max_drawdown;
    double win_rate;
    uint32_t total_trades;
    uint32_t winning_trades;
    uint32_t losing_trades;
    double avg_trade_duration_ms;
    double best_trade;
    double worst_trade;
    std::vector<double> daily_returns;
    std::vector<double> equity_curve;
};

class StrategyBacktester {
private:
    std::vector<BacktestDataPoint> historical_data_;
    double initial_capital_;
    double current_capital_;
    double commission_per_share_;
    
    // Trade tracking
    struct BacktestTrade {
        uint64_t entry_time;
        uint64_t exit_time;
        double entry_price;
        double exit_price;
        int32_t quantity;
        double pnl;
        double commission;
    };
    
    std::vector<BacktestTrade> completed_trades_;
    std::unordered_map<uint32_t, BacktestTrade> open_trades_;
    
    // Performance tracking
    std::vector<double> equity_curve_;
    double high_water_mark_;
    double max_drawdown_;
    
public:
    StrategyBacktester(double initial_capital = 100000.0, 
                      double commission_per_share = 0.005) 
        : initial_capital_(initial_capital),
          current_capital_(initial_capital),
          commission_per_share_(commission_per_share),
          high_water_mark_(initial_capital),
          max_drawdown_(0.0) {
    }
    
    // Load historical data from CSV file
    bool loadHistoricalData(const std::string& filename) {
        std::ifstream file(filename);
        if (!file.is_open()) {
            return false;
        }
        
        std::string line;
        // Skip header
        std::getline(file, line);
        
        while (std::getline(file, line)) {
            std::stringstream ss(line);
            std::string cell;
            
            BacktestDataPoint point;
            
            // Parse CSV: timestamp,symbol_id,price,volume,bid,ask
            std::getline(ss, cell, ',');
            point.timestamp_ns = std::stoull(cell);
            
            std::getline(ss, cell, ',');
            point.symbol_id = std::stoul(cell);
            
            std::getline(ss, cell, ',');
            point.price = std::stod(cell);
            
            std::getline(ss, cell, ',');
            point.volume = std::stoul(cell);
            
            std::getline(ss, cell, ',');
            point.bid = std::stod(cell);
            
            std::getline(ss, cell, ',');
            point.ask = std::stod(cell);
            
            historical_data_.push_back(point);
        }
        
        std::cout << "Loaded " << historical_data_.size() << " data points" << std::endl;
        return true;
    }
    
    // Generate synthetic test data
    void generateSyntheticData(uint32_t symbol_id, 
                              uint64_t start_time_ns,
                              uint64_t duration_ns,
                              uint64_t interval_ns = 1000000000) { // 1 second intervals
        
        double base_price = 100.0;
        double volatility = 0.02; // 2% volatility
        
        for (uint64_t time = start_time_ns; time < start_time_ns + duration_ns; time += interval_ns) {
            BacktestDataPoint point;
            point.timestamp_ns = time;
            point.symbol_id = symbol_id;
            
            // Random walk with trend
            double random_change = ((rand() % 1000) / 1000.0 - 0.5) * volatility;
            base_price *= (1.0 + random_change);
            
            point.price = base_price;
            point.volume = 1000 + (rand() % 5000);
            point.bid = base_price - 0.01;
            point.ask = base_price + 0.01;
            
            historical_data_.push_back(point);
        }
        
        std::cout << "Generated " << historical_data_.size() << " synthetic data points" << std::endl;
    }
    
    // Run backtest
    BacktestResults runBacktest(BaseStrategy* strategy) {
        std::cout << "Starting backtest for strategy: " << strategy->getName() << std::endl;
        
        // Reset state
        current_capital_ = initial_capital_;
        high_water_mark_ = initial_capital_;
        max_drawdown_ = 0.0;
        completed_trades_.clear();
        open_trades_.clear();
        equity_curve_.clear();
        
        strategy->start();
        
        size_t progress_interval = historical_data_.size() / 100;
        
        // Process each data point
        for (size_t i = 0; i < historical_data_.size(); ++i) {
            const auto& data_point = historical_data_[i];
            
            // Create market data event
            MarketDataEvent event;
            event.timestamp_ns = data_point.timestamp_ns;
            event.symbol_id = data_point.symbol_id;
            event.price = data_point.price;
            event.quantity = data_point.volume;
            event.side = 1; // Simplified
            
            // Feed to strategy
            strategy->onMarketData(event);
            strategy->onTick();
            
            // Process any signals
            processStrategySignals(strategy, data_point);
            
            // Update equity curve
            updateEquityCurve();
            
            // Progress reporting
            if (i % progress_interval == 0) {
                double progress = (static_cast<double>(i) / historical_data_.size()) * 100.0;
                std::cout << "Progress: " << std::fixed << std::setprecision(1) 
                         << progress << "%" << std::endl;
            }
        }
        
        strategy->stop();
        
        // Close any remaining open trades
        closeAllOpenTrades();
        
        return calculateResults();
    }
    
    // Print backtest results
    void printResults(const BacktestResults& results) {
        std::cout << "\n=== BACKTEST RESULTS ===" << std::endl;
        std::cout << "Total Return: " << std::fixed << std::setprecision(2) 
                 << results.total_return * 100 << "%" << std::endl;
        std::cout << "Sharpe Ratio: " << std::setprecision(3) 
                 << results.sharpe_ratio << std::endl;
        std::cout << "Max Drawdown: " << std::setprecision(2) 
                 << results.max_drawdown * 100 << "%" << std::endl;
        std::cout << "Win Rate: " << std::setprecision(1) 
                 << results.win_rate * 100 << "%" << std::endl;
        std::cout << "Total Trades: " << results.total_trades << std::endl;
        std::cout << "Winning Trades: " << results.winning_trades << std::endl;
        std::cout << "Losing Trades: " << results.losing_trades << std::endl;
        std::cout << "Avg Trade Duration: " << std::setprecision(1) 
                 << results.avg_trade_duration_ms << " ms" << std::endl;
        std::cout << "Best Trade: $" << std::setprecision(2) 
                 << results.best_trade << std::endl;
        std::cout << "Worst Trade: $" << std::setprecision(2) 
                 << results.worst_trade << std::endl;
        std::cout << "========================" << std::endl;
    }

private:
    void processStrategySignals(BaseStrategy* strategy, const BacktestDataPoint& current_data) {
        while (strategy->hasSignal()) {
            TradingSignal signal = strategy->getSignal();
            
            // Simulate order execution
            Order order = simulateOrderExecution(signal, current_data);
            
            // Feed execution back to strategy
            strategy->onOrderFill(order);
            
            // Track trade
            if (signal.signal_type == 1) { // Entry
                recordTradeEntry(order, current_data.timestamp_ns);
            } else if (signal.signal_type == 2) { // Exit
                recordTradeExit(order, current_data.timestamp_ns);
            }
        }
    }
    
    Order simulateOrderExecution(const TradingSignal& signal, const BacktestDataPoint& data) {
        Order order;
        order.order_id = completed_trades_.size() + open_trades_.size() + 1;
        order.timestamp_ns = data.timestamp_ns;
        order.symbol_id = signal.symbol_id;
        order.strategy_id = signal.strategy_id;
        order.quantity = signal.suggested_quantity;
        order.side = signal.signal_strength > 0 ? 1 : 2; // Buy=1, Sell=2
        order.status = 3; // Filled
        
        // Simulate realistic execution price
        if (signal.urgency < 100) { // Market order
            order.price_ticks = static_cast<uint32_t>(data.price * 100);
        } else { // Limit order
            double execution_price = signal.suggested_price_ticks * 0.01;
            // Add some slippage
            double slippage = 0.001 * ((rand() % 100) / 100.0); // 0-0.1% slippage
            if (order.side == 1) {
                execution_price += slippage;
            } else {
                execution_price -= slippage;
            }
            order.price_ticks = static_cast<uint32_t>(execution_price * 100);
        }
        
        return order;
    }
    
    void recordTradeEntry(const Order& order, uint64_t timestamp) {
        BacktestTrade trade;
        trade.entry_time = timestamp;
        trade.entry_price = order.price_ticks * 0.01;
        trade.quantity = order.quantity;
        if (order.side == 2) trade.quantity = -trade.quantity; // Short
        trade.commission = order.quantity * commission_per_share_;
        
        open_trades_[order.symbol_id] = trade;
        
        // Update capital
        current_capital_ -= std::abs(trade.quantity * trade.entry_price) + trade.commission;
    }
    
    void recordTradeExit(const Order& order, uint64_t timestamp) {
        auto it = open_trades_.find(order.symbol_id);
        if (it == open_trades_.end()) {
            return; // No open trade to close
        }
        
        BacktestTrade& trade = it->second;
        trade.exit_time = timestamp;
        trade.exit_price = order.price_ticks * 0.01;
        trade.commission += order.quantity * commission_per_share_;
        
        // Calculate P&L
        if (trade.quantity > 0) { // Long trade
            trade.pnl = (trade.exit_price - trade.entry_price) * trade.quantity - trade.commission;
        } else { // Short trade
            trade.pnl = (trade.entry_price - trade.exit_price) * std::abs(trade.quantity) - trade.commission;
        }
        
        // Update capital
        current_capital_ += std::abs(trade.quantity * trade.exit_price) + trade.pnl;
        
        completed_trades_.push_back(trade);
        open_trades_.erase(it);
    }
    
    void closeAllOpenTrades() {
        // Close any remaining open trades at last price
        if (!historical_data_.empty() && !open_trades_.empty()) {
            const auto& last_data = historical_data_.back();
            
            for (auto& [symbol_id, trade] : open_trades_) {
                trade.exit_time = last_data.timestamp_ns;
                trade.exit_price = last_data.price;
                
                if (trade.quantity > 0) {
                    trade.pnl = (trade.exit_price - trade.entry_price) * trade.quantity - trade.commission;
                } else {
                    trade.pnl = (trade.entry_price - trade.exit_price) * std::abs(trade.quantity) - trade.commission;
                }
                
                current_capital_ += trade.pnl;
                completed_trades_.push_back(trade);
            }
            
            open_trades_.clear();
        }
    }
    
    void updateEquityCurve() {
        double current_equity = current_capital_;
        
        // Add unrealized P&L from open trades
        if (!historical_data_.empty()) {
            double current_price = historical_data_[equity_curve_.size() % historical_data_.size()].price;
            
            for (const auto& [symbol_id, trade] : open_trades_) {
                double unrealized_pnl;
                if (trade.quantity > 0) {
                    unrealized_pnl = (current_price - trade.entry_price) * trade.quantity;
                } else {
                    unrealized_pnl = (trade.entry_price - current_price) * std::abs(trade.quantity);
                }
                current_equity += unrealized_pnl;
            }
        }
        
        equity_curve_.push_back(current_equity);
        
        // Update high water mark and drawdown
        if (current_equity > high_water_mark_) {
            high_water_mark_ = current_equity;
        } else {
            double drawdown = (high_water_mark_ - current_equity) / high_water_mark_;
            if (drawdown > max_drawdown_) {
                max_drawdown_ = drawdown;
            }
        }
    }
    
    BacktestResults calculateResults() {
        BacktestResults results;
        
        // Basic metrics
        results.total_return = (current_capital_ - initial_capital_) / initial_capital_;
        results.max_drawdown = max_drawdown_;
        results.total_trades = completed_trades_.size();
        
        // Trade statistics
        uint32_t winning_trades = 0;
        double total_pnl = 0.0;
        double best_trade = -std::numeric_limits<double>::max();
        double worst_trade = std::numeric_limits<double>::max();
        uint64_t total_duration = 0;
        
        for (const auto& trade : completed_trades_) {
            total_pnl += trade.pnl;
            if (trade.pnl > 0) winning_trades++;
            
            best_trade = std::max(best_trade, trade.pnl);
            worst_trade = std::min(worst_trade, trade.pnl);
            total_duration += (trade.exit_time - trade.entry_time);
        }
        
        results.winning_trades = winning_trades;
        results.losing_trades = results.total_trades - winning_trades;
        results.win_rate = results.total_trades > 0 ? 
                          static_cast<double>(winning_trades) / results.total_trades : 0.0;
        results.best_trade = best_trade;
        results.worst_trade = worst_trade;
        results.avg_trade_duration_ms = results.total_trades > 0 ? 
                                       (total_duration / results.total_trades) / 1000000.0 : 0.0;
        
        // Calculate Sharpe ratio from daily returns
        results.daily_returns = calculateDailyReturns();
        results.sharpe_ratio = calculateSharpeRatio(results.daily_returns);
        results.equity_curve = equity_curve_;
        
        return results;
    }
    
    std::vector<double> calculateDailyReturns() {
        std::vector<double> daily_returns;
        
        if (equity_curve_.size() < 2) {
            return daily_returns;
        }
        
        // Assuming we have data every second, group by days
        size_t seconds_per_day = 24 * 60 * 60;
        size_t points_per_day = std::min(equity_curve_.size(), seconds_per_day);
        
        for (size_t i = points_per_day; i < equity_curve_.size(); i += points_per_day) {
            double start_value = equity_curve_[i - points_per_day];
            double end_value = equity_curve_[i];
            double daily_return = (end_value - start_value) / start_value;
            daily_returns.push_back(daily_return);
        }
        
        return daily_returns;
    }
    
    double calculateSharpeRatio(const std::vector<double>& daily_returns) {
        if (daily_returns.size() < 2) {
            return 0.0;
        }
        
        double mean_return = 0.0;
        for (double ret : daily_returns) {
            mean_return += ret;
        }
        mean_return /= daily_returns.size();
        
        double variance = 0.0;
        for (double ret : daily_returns) {
            variance += (ret - mean_return) * (ret - mean_return);
        }
        variance /= (daily_returns.size() - 1);
        
        double std_dev = std::sqrt(variance);
        double risk_free_rate = 0.02 / 252.0; // 2% annual risk-free rate
        
        return std_dev > 0 ? (mean_return - risk_free_rate) / std_dev * std::sqrt(252) : 0.0;
    }
};

// Example usage and testing
void runStrategyBacktests() {
    std::cout << "Running strategy backtests..." << std::endl;
    
    StrategyBacktester backtester(100000.0); // $100k initial capital
    
    // Generate synthetic data for testing
    uint64_t start_time = std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    
    backtester.generateSyntheticData(1001, start_time, 24*60*60*1000000000ULL); // 1 day
    
    // Test each strategy
    std::vector<std::string> strategies = {"scalping", "momentum", "mean_reversion"};
    
    for (const auto& strategy_name : strategies) {
        std::cout << "\nTesting " << strategy_name << " strategy..." << std::endl;
        
        // Create strategy config
        StrategyConfig config;
        config.name = strategy_name;
        config.strategy_id = 1;
        config.max_position_size = 10000.0;
        config.max_daily_loss = 1000.0;
        config.enabled = true;
        config.target_symbols = {1001};
        
        // Create strategy
        auto strategy_type = StrategyFactory::getStrategyType(strategy_name);
        auto strategy = StrategyFactory::createStrategy(strategy_type, config);
        
        if (strategy) {
            BacktestResults results = backtester.runBacktest(strategy.get());
            backtester.printResults(results);
        } else {
            std::cout << "Failed to create strategy: " << strategy_name << std::endl;
        }
    }
}

} // namespace HFT

// Main function for standalone testing
int main() {
    try {
        HFT::runStrategyBacktests();
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}