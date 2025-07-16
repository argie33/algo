/**
 * Integration Test Suite for HFT System
 * Tests component interactions and end-to-end workflows
 */

#include <gtest/gtest.h>
#include <chrono>
#include <thread>
#include <atomic>
#include <memory>
#include <vector>
#include <random>
#include <fstream>

// Include system components
#include "../core/trading_engine_aws.cpp"
#include "../strategies/strategy_manager.cpp"
#include "../execution/execution_engine.cpp"
#include "../execution/order_management_system.cpp"
#include "../risk/risk_manager_aws.cpp"
#include "../data/market_data_pipeline.py"
#include "../ml/alpha_engine.h"

namespace HFT::Integration {

// Test configuration
struct TestConfig {
    int test_duration_seconds = 60;
    int num_symbols = 10;
    int market_data_rate_hz = 1000;  // 1000 ticks per second
    double base_price = 100.0;
    int max_order_quantity = 10000;
    double volatility = 0.02;  // 2% volatility
};

// Market data simulator
class MarketDataSimulator {
private:
    TestConfig config_;
    std::atomic<bool> running_{false};
    std::thread simulator_thread_;
    std::vector<double> symbol_prices_;
    std::mt19937 rng_;
    std::normal_distribution<double> price_change_dist_;
    
    // Callbacks
    std::function<void(const MarketDataTick&)> tick_handler_;
    
public:
    MarketDataSimulator(const TestConfig& config) 
        : config_(config), rng_(std::random_device{}()), 
          price_change_dist_(0.0, config_.volatility) {
        
        // Initialize symbol prices
        symbol_prices_.resize(config_.num_symbols, config_.base_price);
    }
    
    void setTickHandler(std::function<void(const MarketDataTick&)> handler) {
        tick_handler_ = handler;
    }
    
    void start() {
        running_ = true;
        simulator_thread_ = std::thread([this]() { runSimulation(); });
    }
    
    void stop() {
        running_ = false;
        if (simulator_thread_.joinable()) {
            simulator_thread_.join();
        }
    }
    
private:
    void runSimulation() {
        auto tick_interval = std::chrono::microseconds(1000000 / config_.market_data_rate_hz);
        uint32_t sequence_number = 0;
        
        while (running_.load()) {
            auto start_time = std::chrono::high_resolution_clock::now();
            
            // Generate tick for random symbol
            uint32_t symbol_id = rng_() % config_.num_symbols;
            
            // Update price with random walk
            double price_change = price_change_dist_(rng_) * symbol_prices_[symbol_id];
            symbol_prices_[symbol_id] += price_change;
            
            // Ensure price doesn't go negative
            if (symbol_prices_[symbol_id] < 1.0) {
                symbol_prices_[symbol_id] = 1.0;
            }
            
            // Create market data tick
            MarketDataTick tick;
            tick.sequence_number = ++sequence_number;
            tick.symbol_id = symbol_id;
            tick.timestamp_ns = std::chrono::high_resolution_clock::now()
                               .time_since_epoch().count();
            tick.price = static_cast<uint64_t>(symbol_prices_[symbol_id] * 10000); // Price in 0.0001 increments
            tick.quantity = 100 + (rng_() % 10000);
            tick.message_type = (rng_() % 2) ? 1 : 2; // 1=bid, 2=ask
            
            // Call handler if set
            if (tick_handler_) {
                tick_handler_(tick);
            }
            
            // Sleep until next tick
            auto end_time = std::chrono::high_resolution_clock::now();
            auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(end_time - start_time);
            if (elapsed < tick_interval) {
                std::this_thread::sleep_for(tick_interval - elapsed);
            }
        }
    }
};

// Order flow analyzer
class OrderFlowAnalyzer {
private:
    struct OrderStats {
        std::atomic<uint64_t> total_orders{0};
        std::atomic<uint64_t> filled_orders{0};
        std::atomic<uint64_t> cancelled_orders{0};
        std::atomic<uint64_t> rejected_orders{0};
        std::atomic<double> total_fill_latency_us{0.0};
        std::atomic<double> total_slippage{0.0};
        std::atomic<double> total_pnl{0.0};
        std::atomic<uint64_t> min_latency_us{UINT64_MAX};
        std::atomic<uint64_t> max_latency_us{0};
    };
    
    OrderStats stats_;
    std::vector<uint64_t> latency_samples_;
    std::mutex samples_mutex_;
    
public:
    void recordOrder(const Order& order) {
        stats_.total_orders.fetch_add(1);
    }
    
    void recordFill(const Order& order, double fill_price, uint64_t fill_latency_us) {
        stats_.filled_orders.fetch_add(1);
        
        // Update latency statistics
        stats_.total_fill_latency_us.fetch_add(fill_latency_us);
        
        uint64_t min_lat = stats_.min_latency_us.load();
        while (fill_latency_us < min_lat && 
               !stats_.min_latency_us.compare_exchange_weak(min_lat, fill_latency_us)) {}
        
        uint64_t max_lat = stats_.max_latency_us.load();
        while (fill_latency_us > max_lat && 
               !stats_.max_latency_us.compare_exchange_weak(max_lat, fill_latency_us)) {}
        
        // Calculate slippage
        double slippage = 0.0;
        if (order.side == OrderSide::BUY) {
            slippage = fill_price - order.expected_price;
        } else {
            slippage = order.expected_price - fill_price;
        }
        stats_.total_slippage.fetch_add(slippage);
        
        // Record latency sample for percentile calculations
        {
            std::lock_guard<std::mutex> lock(samples_mutex_);
            latency_samples_.push_back(fill_latency_us);
        }
    }
    
    void recordCancellation() {
        stats_.cancelled_orders.fetch_add(1);
    }
    
    void recordRejection() {
        stats_.rejected_orders.fetch_add(1);
    }
    
    struct PerformanceReport {
        uint64_t total_orders;
        uint64_t filled_orders;
        double fill_rate;
        double average_latency_us;
        uint64_t min_latency_us;
        uint64_t max_latency_us;
        double p50_latency_us;
        double p95_latency_us;
        double p99_latency_us;
        double average_slippage;
        double total_pnl;
        double sharpe_ratio;
    };
    
    PerformanceReport generateReport() {
        PerformanceReport report{};
        
        report.total_orders = stats_.total_orders.load();
        report.filled_orders = stats_.filled_orders.load();
        
        if (report.total_orders > 0) {
            report.fill_rate = static_cast<double>(report.filled_orders) / report.total_orders;
        }
        
        if (report.filled_orders > 0) {
            report.average_latency_us = stats_.total_fill_latency_us.load() / report.filled_orders;
            report.average_slippage = stats_.total_slippage.load() / report.filled_orders;
        }
        
        report.min_latency_us = stats_.min_latency_us.load();
        report.max_latency_us = stats_.max_latency_us.load();
        
        // Calculate percentiles
        {
            std::lock_guard<std::mutex> lock(samples_mutex_);
            if (!latency_samples_.empty()) {
                std::vector<uint64_t> sorted_samples = latency_samples_;
                std::sort(sorted_samples.begin(), sorted_samples.end());
                
                size_t size = sorted_samples.size();
                report.p50_latency_us = sorted_samples[size / 2];
                report.p95_latency_us = sorted_samples[static_cast<size_t>(size * 0.95)];
                report.p99_latency_us = sorted_samples[static_cast<size_t>(size * 0.99)];
            }
        }
        
        report.total_pnl = stats_.total_pnl.load();
        
        return report;
    }
};

// Integration test fixture
class HFTIntegrationTest : public ::testing::Test {
protected:
    void SetUp() override {
        config_ = TestConfig{};
        config_.test_duration_seconds = 30; // Shorter for tests
        config_.market_data_rate_hz = 100;  // 100 Hz for testing
        
        // Initialize components
        setupComponents();
        
        // Setup market data simulator
        simulator_ = std::make_unique<MarketDataSimulator>(config_);
        analyzer_ = std::make_unique<OrderFlowAnalyzer>();
        
        // Connect components
        connectComponents();
    }
    
    void TearDown() override {
        if (simulator_) simulator_->stop();
        if (oms_) oms_->stop();
        if (trading_engine_) trading_engine_->stop();
        if (strategy_manager_) strategy_manager_->stop();
    }
    
    void setupComponents() {
        // Initialize Order Management System
        oms_ = std::make_unique<OrderManagementSystem>();
        oms_->start();
        
        // Initialize Strategy Manager
        strategy_manager_ = std::make_unique<StrategyManager>();
        strategy_manager_->start();
        
        // Initialize Risk Manager
        risk_manager_ = std::make_unique<RiskManagerAWS>();
        risk_manager_->initialize();
        
        // Initialize Execution Engine
        execution_engine_ = std::make_unique<ExecutionEngine>();
        execution_engine_->start();
        
        // Initialize Trading Engine
        trading_engine_ = std::make_unique<TradingEngineAWS>();
        trading_engine_->initialize();
    }
    
    void connectComponents() {
        // Connect market data handler
        simulator_->setTickHandler([this](const MarketDataTick& tick) {
            onMarketDataTick(tick);
        });
        
        // Connect order management callbacks
        oms_->setFillHandler([this](const Order& order, const Fill& fill) {
            onOrderFill(order, fill);
        });
        
        // Connect strategy signals
        strategy_manager_->setSignalHandler([this](const TradingSignal& signal) {
            onTradingSignal(signal);
        });
    }
    
    void onMarketDataTick(const MarketDataTick& tick) {
        market_data_count_.fetch_add(1);
        
        // Update order books and generate signals
        if (trading_engine_) {
            trading_engine_->processMarketData(tick);
        }
        
        // Feed to strategies
        if (strategy_manager_) {
            strategy_manager_->processMarketData(tick);
        }
    }
    
    void onTradingSignal(const TradingSignal& signal) {
        signal_count_.fetch_add(1);
        
        // Risk check
        if (risk_manager_ && !risk_manager_->validateSignal(signal)) {
            rejected_signals_.fetch_add(1);
            return;
        }
        
        // Create order through OMS
        if (oms_) {
            auto* order = oms_->create_order(
                signal.symbol_id,
                (signal.signal_strength > 0) ? OrderSide::BUY : OrderSide::SELL,
                OrderType::LIMIT,
                static_cast<double>(signal.suggested_price_ticks) / 10000.0,
                signal.suggested_quantity,
                signal.strategy_id
            );
            
            if (order) {
                analyzer_->recordOrder(*order);
            }
        }
    }
    
    void onOrderFill(const Order& order, const Fill& fill) {
        uint64_t fill_latency_us = (fill.timestamp_ns - order.created_time_ns) / 1000;
        analyzer_->recordFill(order, fill.fill_price, fill_latency_us);
    }
    
    // Test configuration
    TestConfig config_;
    
    // Components
    std::unique_ptr<OrderManagementSystem> oms_;
    std::unique_ptr<StrategyManager> strategy_manager_;
    std::unique_ptr<RiskManagerAWS> risk_manager_;
    std::unique_ptr<ExecutionEngine> execution_engine_;
    std::unique_ptr<TradingEngineAWS> trading_engine_;
    
    // Test infrastructure
    std::unique_ptr<MarketDataSimulator> simulator_;
    std::unique_ptr<OrderFlowAnalyzer> analyzer_;
    
    // Metrics
    std::atomic<uint64_t> market_data_count_{0};
    std::atomic<uint64_t> signal_count_{0};
    std::atomic<uint64_t> rejected_signals_{0};
};

// ================ INTEGRATION TESTS ================

TEST_F(HFTIntegrationTest, BasicDataFlowTest) {
    // Test basic data flow: Market Data -> Signals -> Orders
    
    simulator_->start();
    
    // Run for short duration
    std::this_thread::sleep_for(std::chrono::seconds(5));
    
    simulator_->stop();
    
    // Verify data flow
    uint64_t ticks_received = market_data_count_.load();
    uint64_t signals_generated = signal_count_.load();
    
    std::cout << "Market data ticks received: " << ticks_received << std::endl;
    std::cout << "Trading signals generated: " << signals_generated << std::endl;
    
    EXPECT_GT(ticks_received, 0);
    EXPECT_GT(signals_generated, 0);
    
    // Verify signal rate is reasonable (not too high or low)
    double signal_rate = static_cast<double>(signals_generated) / ticks_received;
    EXPECT_GT(signal_rate, 0.001);  // At least 0.1% of ticks generate signals
    EXPECT_LT(signal_rate, 0.5);    // No more than 50% of ticks generate signals
}

TEST_F(HFTIntegrationTest, RiskManagementIntegrationTest) {
    // Test risk management integration across components
    
    // Set aggressive risk limits for testing
    risk_manager_->setMaxPositionSize(1000);
    risk_manager_->setMaxOrderValue(10000.0);
    risk_manager_->setDailyLossLimit(5000.0);
    
    simulator_->start();
    
    // Run simulation
    std::this_thread::sleep_for(std::chrono::seconds(10));
    
    simulator_->stop();
    
    uint64_t total_signals = signal_count_.load();
    uint64_t rejected_signals = rejected_signals_.load();
    
    std::cout << "Total signals: " << total_signals << std::endl;
    std::cout << "Rejected signals: " << rejected_signals << std::endl;
    
    if (total_signals > 0) {
        double rejection_rate = static_cast<double>(rejected_signals) / total_signals;
        std::cout << "Signal rejection rate: " << rejection_rate * 100.0 << "%" << std::endl;
        
        // Some signals should be rejected due to risk limits
        EXPECT_GT(rejection_rate, 0.0);
        EXPECT_LT(rejection_rate, 0.8); // Not too many rejections
    }
}

TEST_F(HFTIntegrationTest, OrderExecutionIntegrationTest) {
    // Test full order execution flow
    
    simulator_->start();
    
    // Run for longer to get meaningful execution data
    std::this_thread::sleep_for(std::chrono::seconds(15));
    
    simulator_->stop();
    
    auto report = analyzer_->generateReport();
    
    std::cout << "=== Order Execution Report ===" << std::endl;
    std::cout << "Total orders: " << report.total_orders << std::endl;
    std::cout << "Filled orders: " << report.filled_orders << std::endl;
    std::cout << "Fill rate: " << report.fill_rate * 100.0 << "%" << std::endl;
    std::cout << "Average latency: " << report.average_latency_us << " μs" << std::endl;
    std::cout << "95th percentile latency: " << report.p95_latency_us << " μs" << std::endl;
    std::cout << "99th percentile latency: " << report.p99_latency_us << " μs" << std::endl;
    std::cout << "Average slippage: " << report.average_slippage << std::endl;
    
    // Verify reasonable execution performance
    EXPECT_GT(report.total_orders, 0);
    EXPECT_GT(report.fill_rate, 0.1); // At least 10% fill rate
    
    if (report.filled_orders > 0) {
        EXPECT_LT(report.average_latency_us, 10000); // <10ms average latency
        EXPECT_LT(report.p95_latency_us, 50000);     // <50ms 95th percentile
    }
}

TEST_F(HFTIntegrationTest, StrategyPerformanceTest) {
    // Test strategy performance and signal quality
    
    // Add multiple strategies
    strategy_manager_->addStrategy("MarketMaking", 100000.0, 0.05);
    strategy_manager_->addStrategy("MeanReversion", 50000.0, 0.03);
    strategy_manager_->addStrategy("Momentum", 75000.0, 0.04);
    
    simulator_->start();
    
    // Run for extended period
    std::this_thread::sleep_for(std::chrono::seconds(20));
    
    simulator_->stop();
    
    auto allocations = strategy_manager_->getAllocations();
    
    std::cout << "=== Strategy Performance ===" << std::endl;
    for (const auto& alloc : allocations) {
        std::cout << "Strategy: " << alloc.strategy_name << std::endl;
        std::cout << "  Signals generated: " << alloc.signal_count_today << std::endl;
        std::cout << "  P&L: $" << alloc.realized_pnl_today << std::endl;
        std::cout << "  Allocation utilization: " << alloc.allocation_utilization * 100.0 << "%" << std::endl;
        std::cout << "  Enabled: " << (alloc.is_enabled ? "Yes" : "No") << std::endl;
        
        // Verify strategies are generating signals
        EXPECT_GT(alloc.signal_count_today, 0);
    }
    
    // Verify total signal count matches individual strategies
    uint32_t total_strategy_signals = 0;
    for (const auto& alloc : allocations) {
        total_strategy_signals += alloc.signal_count_today;
    }
    
    // Allow for some variance due to timing
    uint64_t measured_signals = signal_count_.load();
    EXPECT_NEAR(total_strategy_signals, measured_signals, measured_signals * 0.1);
}

TEST_F(HFTIntegrationTest, HighThroughputStressTest) {
    // Test system under high market data load
    
    config_.market_data_rate_hz = 10000; // 10K ticks/sec
    simulator_ = std::make_unique<MarketDataSimulator>(config_);
    simulator_->setTickHandler([this](const MarketDataTick& tick) {
        onMarketDataTick(tick);
    });
    
    auto start_time = std::chrono::high_resolution_clock::now();
    
    simulator_->start();
    
    // Run stress test
    std::this_thread::sleep_for(std::chrono::seconds(10));
    
    simulator_->stop();
    
    auto end_time = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time);
    
    uint64_t total_ticks = market_data_count_.load();
    double actual_rate = (total_ticks * 1000.0) / duration.count();
    
    std::cout << "=== High Throughput Stress Test ===" << std::endl;
    std::cout << "Target rate: " << config_.market_data_rate_hz << " ticks/sec" << std::endl;
    std::cout << "Actual rate: " << actual_rate << " ticks/sec" << std::endl;
    std::cout << "Total ticks processed: " << total_ticks << std::endl;
    std::cout << "Signals generated: " << signal_count_.load() << std::endl;
    
    // Verify system can handle high throughput
    EXPECT_GT(actual_rate, config_.market_data_rate_hz * 0.8); // At least 80% of target rate
    
    // Verify system didn't crash or drop too many events
    EXPECT_GT(signal_count_.load(), 0);
}

TEST_F(HFTIntegrationTest, MemoryUsageTest) {
    // Test memory usage under load
    
    size_t initial_memory = getCurrentMemoryUsage();
    
    simulator_->start();
    
    // Run for extended period to check for memory leaks
    std::this_thread::sleep_for(std::chrono::seconds(30));
    
    size_t peak_memory = getCurrentMemoryUsage();
    
    simulator_->stop();
    
    // Let system settle
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    size_t final_memory = getCurrentMemoryUsage();
    
    std::cout << "=== Memory Usage Test ===" << std::endl;
    std::cout << "Initial memory: " << initial_memory / 1024 / 1024 << " MB" << std::endl;
    std::cout << "Peak memory: " << peak_memory / 1024 / 1024 << " MB" << std::endl;
    std::cout << "Final memory: " << final_memory / 1024 / 1024 << " MB" << std::endl;
    
    // Check for memory leaks (final should be close to initial)
    double memory_growth = static_cast<double>(final_memory - initial_memory) / initial_memory;
    EXPECT_LT(memory_growth, 0.1); // Less than 10% memory growth
    
    // Check peak memory usage is reasonable
    double peak_growth = static_cast<double>(peak_memory - initial_memory) / initial_memory;
    EXPECT_LT(peak_growth, 2.0); // Less than 200% growth at peak
}

TEST_F(HFTIntegrationTest, SystemRecoveryTest) {
    // Test system recovery from component failures
    
    simulator_->start();
    
    // Run normally for a bit
    std::this_thread::sleep_for(std::chrono::seconds(5));
    
    uint64_t signals_before_failure = signal_count_.load();
    
    // Simulate component failure (stop and restart risk manager)
    risk_manager_->stop();
    
    // Continue running with failed component
    std::this_thread::sleep_for(std::chrono::seconds(3));
    
    // Restart failed component
    risk_manager_->initialize();
    risk_manager_->start();
    
    // Run for recovery period
    std::this_thread::sleep_for(std::chrono::seconds(5));
    
    simulator_->stop();
    
    uint64_t total_signals = signal_count_.load();
    
    std::cout << "=== System Recovery Test ===" << std::endl;
    std::cout << "Signals before failure: " << signals_before_failure << std::endl;
    std::cout << "Total signals after recovery: " << total_signals << std::endl;
    
    // System should continue generating signals after recovery
    EXPECT_GT(total_signals, signals_before_failure);
    
    // Generate test report
    auto report = analyzer_->generateReport();
    EXPECT_GT(report.total_orders, 0);
}

private:
    size_t getCurrentMemoryUsage() {
        // Simple memory usage check (Linux-specific)
        std::ifstream status("/proc/self/status");
        std::string line;
        
        while (std::getline(status, line)) {
            if (line.substr(0, 6) == "VmRSS:") {
                std::istringstream iss(line);
                std::string label, value, unit;
                iss >> label >> value >> unit;
                return std::stoull(value) * 1024; // Convert kB to bytes
            }
        }
        
        return 0;
    }
};

} // namespace HFT::Integration

// Main test runner
int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    
    std::cout << "=== HFT System Integration Test Suite ===" << std::endl;
    std::cout << "Testing component interactions and end-to-end workflows" << std::endl;
    
    return RUN_ALL_TESTS();
}