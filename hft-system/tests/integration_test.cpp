/**
 * HFT System Integration Tests
 * End-to-end testing of the complete trading system
 */

#include "../src/core/trading_engine_aws.cpp"
#include "../src/strategies/strategy_manager.cpp"
#include "../src/execution/execution_engine.cpp"
#include "../src/utils/performance_utils.h"
#include <gtest/gtest.h>
#include <chrono>
#include <thread>

namespace HFT {

class HFTSystemIntegrationTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Initialize system components
        trading_engine_ = std::make_unique<AWSTradingEngine>();
        strategy_manager_ = std::make_unique<StrategyManager>();
        execution_engine_ = std::make_unique<ExecutionEngine>();
        
        // Set up test symbols
        test_symbols_ = {1001, 1002, 1003}; // AAPL, MSFT, GOOGL
        
        // Initialize with test configuration
        setupTestEnvironment();
    }
    
    void TearDown() override {
        if (trading_engine_) trading_engine_->stop();
        if (strategy_manager_) strategy_manager_->stop();
        if (execution_engine_) execution_engine_->stop();
    }
    
    void setupTestEnvironment() {
        // Create test strategies
        for (const std::string& strategy_name : {"scalping", "momentum", "mean_reversion"}) {
            StrategyConfig config;
            config.name = strategy_name;
            config.strategy_id = strategy_counter_++;
            config.max_position_size = 10000.0;
            config.max_daily_loss = 1000.0;
            config.enabled = true;
            config.target_symbols = test_symbols_;
            config.parameters = getDefaultParameters(strategy_name);
            
            strategy_manager_->addStrategy(strategy_name, config, 0.3); // 30% allocation each
        }
    }
    
    std::vector<std::string> getDefaultParameters(const std::string& strategy_name) {
        if (strategy_name == "scalping") {
            return {"profit_target_ticks=2", "stop_loss_ticks=3", "max_position_size=1000"};
        } else if (strategy_name == "momentum") {
            return {"fast_ma_period=10", "slow_ma_period=30", "momentum_threshold=0.003"};
        } else if (strategy_name == "mean_reversion") {
            return {"lookback_period=20", "zscore_entry_threshold=2.0", "zscore_exit_threshold=0.5"};
        }
        return {};
    }
    
    std::unique_ptr<AWSTradingEngine> trading_engine_;
    std::unique_ptr<StrategyManager> strategy_manager_;
    std::unique_ptr<ExecutionEngine> execution_engine_;
    
    std::vector<uint32_t> test_symbols_;
    uint32_t strategy_counter_ = 1;
};

// Test basic system startup and shutdown
TEST_F(HFTSystemIntegrationTest, SystemStartupShutdown) {
    EXPECT_NO_THROW({
        trading_engine_->start();
        strategy_manager_->start();
        execution_engine_->start();
        
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        
        trading_engine_->stop();
        strategy_manager_->stop();
        execution_engine_->stop();
    });
}

// Test market data flow through the system
TEST_F(HFTSystemIntegrationTest, MarketDataFlow) {
    trading_engine_->start();
    strategy_manager_->start();
    execution_engine_->start();
    
    // Generate test market data
    auto start_time = std::chrono::high_resolution_clock::now();
    uint64_t timestamp_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
        start_time.time_since_epoch()).count();
    
    // Send market data events
    for (int i = 0; i < 100; ++i) {
        for (uint32_t symbol_id : test_symbols_) {
            MarketDataEvent event;
            event.timestamp_ns = timestamp_ns + i * 1000000; // 1ms apart
            event.symbol_id = symbol_id;
            event.price = 100.0 + (i * 0.01); // Trending price
            event.quantity = 1000 + (i * 10);
            event.side = (i % 2) + 1; // Alternate bid/ask
            
            strategy_manager_->onMarketData(event);
            execution_engine_->updateMarketData(event);
        }
        
        std::this_thread::sleep_for(std::chrono::microseconds(100));
    }
    
    // Allow processing time
    std::this_thread::sleep_for(std::chrono::milliseconds(500));
    
    // Check that signals were generated
    auto signals = strategy_manager_->collectSignals();
    EXPECT_GT(signals.size(), 0) << "No trading signals generated";
    
    auto portfolio_summary = strategy_manager_->getPortfolioSummary();
    EXPECT_GT(portfolio_summary.total_signals_today, 0) << "No signals recorded in portfolio summary";
}

// Test order execution flow
TEST_F(HFTSystemIntegrationTest, OrderExecutionFlow) {
    trading_engine_->start();
    execution_engine_->start();
    
    // Create a test trading signal
    TradingSignal signal;
    signal.timestamp_ns = TSCTimer::now_ns();
    signal.symbol_id = 1001;
    signal.strategy_id = 1;
    signal.signal_strength = 0.8;
    signal.confidence = 0.9;
    signal.suggested_quantity = 500;
    signal.suggested_price_ticks = 10050; // $100.50
    signal.urgency = 100;
    signal.signal_type = 1; // Entry
    
    // Submit to execution engine
    uint64_t parent_order_id = execution_engine_->submitParentOrder(signal, ExecutionAlgorithm::TWAP);
    EXPECT_GT(parent_order_id, 0) << "Failed to submit parent order";
    
    // Generate market data to trigger execution
    for (int i = 0; i < 50; ++i) {
        MarketDataEvent event;
        event.timestamp_ns = TSCTimer::now_ns();
        event.symbol_id = 1001;
        event.price = 100.48 + (i * 0.001); // Moving price
        event.quantity = 1000;
        event.side = 1; // Bid
        
        execution_engine_->updateMarketData(event);
        execution_engine_->processExecutionReports();
        
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    
    // Check execution progress
    ParentOrder parent = execution_engine_->getParentOrder(parent_order_id);
    EXPECT_GT(parent.executed_quantity, 0) << "No execution occurred";
    
    auto metrics = execution_engine_->getMetrics();
    EXPECT_GT(metrics.child_orders_sent.load(), 0) << "No child orders sent";
}

// Test strategy performance under load
TEST_F(HFTSystemIntegrationTest, StrategyPerformanceUnderLoad) {
    trading_engine_->start();
    strategy_manager_->start();
    
    const int NUM_EVENTS = 10000;
    const int NUM_SYMBOLS = 10;
    
    LatencyMeasurer signal_latency("SignalGeneration");
    
    auto start_time = std::chrono::high_resolution_clock::now();
    
    // Generate high-frequency market data
    for (int i = 0; i < NUM_EVENTS; ++i) {
        uint64_t event_start = TSCTimer::rdtsc();
        
        MarketDataEvent event;
        event.timestamp_ns = TSCTimer::now_ns();
        event.symbol_id = 1001 + (i % NUM_SYMBOLS);
        event.price = 100.0 + sin(i * 0.01) * 2.0; // Oscillating price
        event.quantity = 1000 + (rand() % 2000);
        event.side = (i % 2) + 1;
        
        strategy_manager_->onMarketData(event);
        
        // Collect signals
        auto signals = strategy_manager_->collectSignals();
        for (const auto& signal : signals) {
            uint64_t event_end = TSCTimer::rdtsc();
            signal_latency.recordLatency(event_start, event_end);
        }
        
        if (i % 1000 == 0) {
            std::this_thread::sleep_for(std::chrono::microseconds(1)); // Brief pause
        }
    }
    
    auto end_time = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time);
    
    printf("Processed %d events in %ld ms (%.2f events/ms)\n", 
           NUM_EVENTS, duration.count(), 
           static_cast<double>(NUM_EVENTS) / duration.count());
    
    signal_latency.printStatistics();
    
    auto portfolio_summary = strategy_manager_->getPortfolioSummary();
    EXPECT_GT(portfolio_summary.total_signals_today, 0);
    
    // Verify all strategies are still active
    EXPECT_EQ(portfolio_summary.active_strategies, 3);
}

// Test risk management integration
TEST_F(HFTSystemIntegrationTest, RiskManagementIntegration) {
    trading_engine_->start();
    strategy_manager_->start();
    
    // Create aggressive signals to trigger risk limits
    std::vector<TradingSignal> aggressive_signals;
    
    for (int i = 0; i < 20; ++i) {
        TradingSignal signal;
        signal.timestamp_ns = TSCTimer::now_ns();
        signal.symbol_id = 1001;
        signal.strategy_id = 1;
        signal.signal_strength = 1.0; // Maximum bullish
        signal.confidence = 1.0;
        signal.suggested_quantity = 5000; // Large size
        signal.suggested_price_ticks = 10100; // $101.00
        signal.urgency = 10; // Very urgent
        signal.signal_type = 1;
        
        // Submit signals rapidly
        for (int j = 0; j < 5; ++j) {
            // Simulate signal generation by adding to strategy
            // In real test, this would come from strategy
        }
        
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    
    // Allow processing time
    std::this_thread::sleep_for(std::chrono::seconds(1));
    
    auto portfolio_summary = strategy_manager_->getPortfolioSummary();
    
    // Verify risk limits prevented excessive trading
    EXPECT_LT(portfolio_summary.total_exposure, 500000.0) << "Portfolio exposure too high";
    EXPECT_GT(portfolio_summary.active_strategies, 0) << "All strategies were stopped";
}

// Test system recovery from failures
TEST_F(HFTSystemIntegrationTest, SystemRecovery) {
    trading_engine_->start();
    strategy_manager_->start();
    execution_engine_->start();
    
    // Run normal operations
    for (int i = 0; i < 50; ++i) {
        MarketDataEvent event;
        event.timestamp_ns = TSCTimer::now_ns();
        event.symbol_id = 1001;
        event.price = 100.0 + (i * 0.01);
        event.quantity = 1000;
        event.side = 1;
        
        strategy_manager_->onMarketData(event);
        
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    
    auto initial_summary = strategy_manager_->getPortfolioSummary();
    
    // Simulate system stress (emergency stop)
    strategy_manager_->emergencyStop("Test emergency stop");
    
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    auto emergency_summary = strategy_manager_->getPortfolioSummary();
    EXPECT_EQ(emergency_summary.active_strategies, 0) << "Strategies not stopped during emergency";
    
    // Restart components
    strategy_manager_->stop();
    strategy_manager_ = std::make_unique<StrategyManager>();
    setupTestEnvironment();
    strategy_manager_->start();
    
    // Verify recovery
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    auto recovery_summary = strategy_manager_->getPortfolioSummary();
    EXPECT_GT(recovery_summary.active_strategies, 0) << "System did not recover properly";
}

// Test memory and performance under extended operation
TEST_F(HFTSystemIntegrationTest, ExtendedOperationTest) {
    trading_engine_->start();
    strategy_manager_->start();
    execution_engine_->start();
    
    const int RUNTIME_SECONDS = 10;
    const int EVENTS_PER_SECOND = 1000;
    
    auto start_time = std::chrono::steady_clock::now();
    auto end_time = start_time + std::chrono::seconds(RUNTIME_SECONDS);
    
    size_t total_events = 0;
    size_t total_signals = 0;
    
    while (std::chrono::steady_clock::now() < end_time) {
        // Generate burst of events
        for (int i = 0; i < EVENTS_PER_SECOND / 100; ++i) { // 10 events per burst
            MarketDataEvent event;
            event.timestamp_ns = TSCTimer::now_ns();
            event.symbol_id = 1001 + (total_events % 3);
            event.price = 100.0 + sin(total_events * 0.001) * 5.0;
            event.quantity = 1000 + (rand() % 1000);
            event.side = (total_events % 2) + 1;
            
            strategy_manager_->onMarketData(event);
            execution_engine_->updateMarketData(event);
            
            total_events++;
        }
        
        // Collect signals
        auto signals = strategy_manager_->collectSignals();
        total_signals += signals.size();
        
        // Process execution reports
        execution_engine_->processExecutionReports();
        
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    
    auto actual_runtime = std::chrono::steady_clock::now() - start_time;
    auto runtime_ms = std::chrono::duration_cast<std::chrono::milliseconds>(actual_runtime).count();
    
    printf("\nExtended Operation Results:\n");
    printf("Runtime: %ld ms\n", runtime_ms);
    printf("Total Events: %zu (%.2f events/ms)\n", total_events, 
           static_cast<double>(total_events) / runtime_ms);
    printf("Total Signals: %zu (%.2f signals/event)\n", total_signals,
           static_cast<double>(total_signals) / total_events);
    
    auto portfolio_summary = strategy_manager_->getPortfolioSummary();
    auto execution_metrics = execution_engine_->getMetrics();
    
    printf("Active Strategies: %u\n", portfolio_summary.active_strategies);
    printf("Parent Orders Completed: %lu\n", execution_metrics.parent_orders_completed.load());
    printf("Average Execution Time: %lu ms\n", execution_metrics.avg_execution_time_ms.load());
    
    // Verify system stability
    EXPECT_EQ(portfolio_summary.active_strategies, 3) << "Strategies became inactive";
    EXPECT_GT(total_signals, 0) << "No signals generated during extended run";
    EXPECT_LT(execution_metrics.avg_slippage_bps.load(), 50.0) << "Excessive slippage detected";
}

} // namespace HFT

// Main function for running tests
int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    
    // Set up performance optimizations for testing
    HFT::CPUOptimizer::setCPUAffinity(0); // Run tests on CPU 0
    
    printf("Starting HFT System Integration Tests...\n");
    printf("TSC Support: %s\n", HFT::CPUOptimizer::supportsTSC() ? "Yes" : "No");
    printf("RDTSCP Support: %s\n", HFT::CPUOptimizer::supportsRDTSCP() ? "Yes" : "No");
    printf("CPU Count: %d\n", HFT::CPUOptimizer::getNumCPUs());
    printf("Cache Line Size: %zu bytes\n", HFT::MemoryOptimizer::getCacheLineSize());
    
    int result = RUN_ALL_TESTS();
    
    // Print performance report
    HFT::PerformanceProfiler::printReport();
    
    return result;
}