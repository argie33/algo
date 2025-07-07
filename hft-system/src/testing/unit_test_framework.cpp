/**
 * Comprehensive Unit Testing Framework for HFT System
 * Tests all critical components with performance benchmarks
 */

#include <gtest/gtest.h>
#include <gmock/gmock.h>
#include <chrono>
#include <random>
#include <vector>
#include <memory>
#include <atomic>
#include <thread>

// Include all HFT system components
#include "../core/trading_engine_aws.cpp"
#include "../strategies/strategy_manager.cpp"
#include "../execution/execution_engine.cpp"
#include "../execution/order_management_system.cpp"
#include "../data/high_performance_order_book.h"
#include "../risk/risk_manager_aws.cpp"
#include "../ml/alpha_engine.h"
#include "../utils/memory_pool.h"
#include "../utils/lock_free_queue.h"

namespace HFT::Testing {

// Test fixture for common setup
class HFTSystemTest : public ::testing::Test {
protected:
    void SetUp() override {
        // Initialize test data
        generateTestData();
        
        // Setup mock AWS services
        setupMockAWS();
        
        // Initialize system components
        initializeComponents();
    }
    
    void TearDown() override {
        // Cleanup
        if (oms_) oms_->stop();
        if (strategy_manager_) strategy_manager_.reset();
    }
    
    void generateTestData() {
        // Generate realistic test market data
        std::random_device rd;
        std::mt19937 gen(rd());
        std::uniform_real_distribution<double> price_dist(50.0, 200.0);
        std::uniform_int_distribution<uint32_t> qty_dist(100, 10000);
        
        for (int i = 0; i < 1000; ++i) {
            MarketDataTick tick;
            tick.symbol_id = i % 10; // 10 test symbols
            tick.price = price_dist(gen);
            tick.quantity = qty_dist(gen);
            tick.timestamp_ns = std::chrono::high_resolution_clock::now()
                               .time_since_epoch().count();
            test_market_data_.push_back(tick);
        }
    }
    
    void setupMockAWS() {
        // Mock AWS services for testing
        mock_dynamodb_ = std::make_shared<MockDynamoDB>();
        mock_cloudwatch_ = std::make_shared<MockCloudWatch>();
        mock_sns_ = std::make_shared<MockSNS>();
    }
    
    void initializeComponents() {
        // Initialize OMS
        oms_ = std::make_unique<OrderManagementSystem>();
        oms_->start();
        
        // Initialize strategy manager
        strategy_manager_ = std::make_unique<StrategyManager>();
        
        // Initialize execution engine
        execution_engine_ = std::make_unique<ExecutionEngine>();
        
        // Initialize order book
        order_book_ = std::make_unique<HighPerformanceOrderBook>(1000);
    }
    
    // Test data
    std::vector<MarketDataTick> test_market_data_;
    
    // Mock AWS services
    std::shared_ptr<MockDynamoDB> mock_dynamodb_;
    std::shared_ptr<MockCloudWatch> mock_cloudwatch_;
    std::shared_ptr<MockSNS> mock_sns_;
    
    // System components
    std::unique_ptr<OrderManagementSystem> oms_;
    std::unique_ptr<StrategyManager> strategy_manager_;
    std::unique_ptr<ExecutionEngine> execution_engine_;
    std::unique_ptr<HighPerformanceOrderBook> order_book_;
};

// Mock AWS Services
class MockDynamoDB {
public:
    MOCK_METHOD(bool, putItem, (const std::string& table, const std::string& item));
    MOCK_METHOD(std::string, getItem, (const std::string& table, const std::string& key));
    MOCK_METHOD(bool, updateItem, (const std::string& table, const std::string& key, const std::string& updates));
};

class MockCloudWatch {
public:
    MOCK_METHOD(bool, putMetric, (const std::string& namespace_, const std::string& metric_name, double value));
    MOCK_METHOD(std::vector<double>, getMetrics, (const std::string& namespace_, const std::string& metric_name));
};

class MockSNS {
public:
    MOCK_METHOD(bool, publishMessage, (const std::string& topic, const std::string& message));
};

// Test data structures
struct MarketDataTick {
    uint32_t symbol_id;
    double price;
    uint32_t quantity;
    uint64_t timestamp_ns;
    uint8_t side; // 1=bid, 2=ask
};

// ================ ORDER MANAGEMENT SYSTEM TESTS ================

TEST_F(HFTSystemTest, OMSBasicOrderCreation) {
    // Test basic order creation and validation
    auto* order = oms_->create_order(
        1,                    // symbol_id
        OrderSide::BUY,      // side
        OrderType::LIMIT,    // type
        100.50,              // price
        1000,                // quantity
        1                    // strategy_id
    );
    
    ASSERT_NE(order, nullptr);
    EXPECT_EQ(order->symbol_id, 1);
    EXPECT_EQ(order->side, OrderSide::BUY);
    EXPECT_EQ(order->price, 100.50);
    EXPECT_EQ(order->quantity, 1000);
    EXPECT_EQ(order->state, OrderState::PENDING_NEW);
}

TEST_F(HFTSystemTest, OMSRiskValidation) {
    // Test risk validation rejects oversized orders
    auto* order = oms_->create_order(
        1,                    // symbol_id
        OrderSide::BUY,      // side
        OrderType::LIMIT,    // type
        10000.0,             // price (very high)
        100000,              // quantity (very large)
        1                    // strategy_id
    );
    
    // Should be rejected due to excessive value
    EXPECT_EQ(order, nullptr);
}

TEST_F(HFTSystemTest, OMSOrderFillProcessing) {
    // Create order
    auto* order = oms_->create_order(1, OrderSide::BUY, OrderType::LIMIT, 
                                    100.0, 1000, 1);
    ASSERT_NE(order, nullptr);
    
    uint64_t order_id = order->order_id;
    
    // Simulate partial fill
    oms_->process_fill(order_id, 500, 100.05, "EXEC_001", 2.5, 0.5);
    
    // Check order state
    const Order* updated_order = oms_->get_order(order_id);
    ASSERT_NE(updated_order, nullptr);
    EXPECT_EQ(updated_order->filled_quantity, 500);
    EXPECT_EQ(updated_order->remaining_quantity, 500);
    EXPECT_EQ(updated_order->state, OrderState::PARTIALLY_FILLED);
    
    // Complete the fill
    oms_->process_fill(order_id, 500, 100.07, "EXEC_002", 2.5, 0.5);
    
    updated_order = oms_->get_order(order_id);
    EXPECT_EQ(updated_order->filled_quantity, 1000);
    EXPECT_EQ(updated_order->remaining_quantity, 0);
    EXPECT_EQ(updated_order->state, OrderState::FILLED);
}

TEST_F(HFTSystemTest, OMSPerformanceBenchmark) {
    // Benchmark order creation performance
    const int num_orders = 10000;
    auto start = std::chrono::high_resolution_clock::now();
    
    std::vector<uint64_t> order_ids;
    for (int i = 0; i < num_orders; ++i) {
        auto* order = oms_->create_order(
            i % 10,               // symbol_id
            (i % 2) ? OrderSide::BUY : OrderSide::SELL,
            OrderType::LIMIT,
            100.0 + (i % 100) * 0.01,  // price
            100 + (i % 1000),          // quantity
            1                          // strategy_id
        );
        if (order) {
            order_ids.push_back(order->order_id);
        }
    }
    
    auto end = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
    
    double orders_per_second = (num_orders * 1000000.0) / duration.count();
    
    std::cout << "Order creation rate: " << orders_per_second << " orders/sec" << std::endl;
    std::cout << "Average latency: " << duration.count() / num_orders << " microseconds" << std::endl;
    
    // Performance target: >50K orders/sec
    EXPECT_GT(orders_per_second, 50000.0);
}

// ================ HIGH PERFORMANCE ORDER BOOK TESTS ================

TEST_F(HFTSystemTest, OrderBookBasicOperations) {
    // Test basic order book operations
    order_book_->addOrder(1, 100.50, 1000, OrderSide::BUY, 1001);
    order_book_->addOrder(2, 100.55, 500, OrderSide::SELL, 1002);
    
    double best_bid = order_book_->getBestBid();
    double best_ask = order_book_->getBestAsk();
    
    EXPECT_DOUBLE_EQ(best_bid, 100.50);
    EXPECT_DOUBLE_EQ(best_ask, 100.55);
    EXPECT_DOUBLE_EQ(order_book_->getSpread(), 0.05);
}

TEST_F(HFTSystemTest, OrderBookSIMDPerformance) {
    // Benchmark SIMD-optimized order book updates
    const int num_updates = 100000;
    
    auto start = std::chrono::high_resolution_clock::now();
    
    for (int i = 0; i < num_updates; ++i) {
        double price = 100.0 + (i % 1000) * 0.01;
        uint32_t quantity = 100 + (i % 1000);
        OrderSide side = (i % 2) ? OrderSide::BUY : OrderSide::SELL;
        
        order_book_->addOrder(i, price, quantity, side, 1000 + i);
    }
    
    auto end = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start);
    
    double updates_per_second = (num_updates * 1000000000.0) / duration.count();
    double avg_latency_ns = duration.count() / num_updates;
    
    std::cout << "Order book update rate: " << updates_per_second << " updates/sec" << std::endl;
    std::cout << "Average update latency: " << avg_latency_ns << " nanoseconds" << std::endl;
    
    // Performance target: >1M updates/sec, <1000ns average latency
    EXPECT_GT(updates_per_second, 1000000.0);
    EXPECT_LT(avg_latency_ns, 1000.0);
}

// ================ STRATEGY MANAGER TESTS ================

TEST_F(HFTSystemTest, StrategyManagerAllocation) {
    // Test strategy allocation and management
    strategy_manager_->addStrategy("MarketMaking", 100000.0, 0.02); // $100k, 2% drawdown limit
    strategy_manager_->addStrategy("StatArb", 200000.0, 0.03);      // $200k, 3% drawdown limit
    
    auto allocations = strategy_manager_->getAllocations();
    EXPECT_EQ(allocations.size(), 2);
    
    double total_allocation = 0.0;
    for (const auto& alloc : allocations) {
        total_allocation += alloc.capital_allocation;
    }
    EXPECT_DOUBLE_EQ(total_allocation, 300000.0);
}

TEST_F(HFTSystemTest, StrategyManagerRiskManagement) {
    // Test strategy-level risk management
    strategy_manager_->addStrategy("TestStrategy", 50000.0, 0.05); // 5% max drawdown
    
    // Simulate losses
    strategy_manager_->updateStrategyPnL("TestStrategy", -2000.0); // 4% loss - should be OK
    EXPECT_TRUE(strategy_manager_->isStrategyEnabled("TestStrategy"));
    
    strategy_manager_->updateStrategyPnL("TestStrategy", -1000.0); // Total 6% loss - should disable
    EXPECT_FALSE(strategy_manager_->isStrategyEnabled("TestStrategy"));
}

// ================ EXECUTION ENGINE TESTS ================

TEST_F(HFTSystemTest, ExecutionEngineAlgorithms) {
    // Test TWAP algorithm
    ExecutionParams params;
    params.algorithm = ExecutionAlgorithm::TWAP;
    params.symbol_id = 1;
    params.total_quantity = 10000;
    params.duration_minutes = 60;
    params.max_participation_rate = 0.10; // 10% of volume
    
    bool success = execution_engine_->executeOrder(params);
    EXPECT_TRUE(success);
    
    // Check that child orders were created
    auto child_orders = execution_engine_->getChildOrders(params.parent_order_id);
    EXPECT_GT(child_orders.size(), 0);
}

TEST_F(HFTSystemTest, ExecutionEngineVenueSelection) {
    // Test smart venue selection
    MarketDataSnapshot snapshot;
    snapshot.symbol_id = 1;
    snapshot.venues[VenueId::NASDAQ] = {100.50, 1000, 100.51, 800};
    snapshot.venues[VenueId::NYSE] = {100.49, 1200, 100.52, 600};
    snapshot.venues[VenueId::BATS] = {100.50, 500, 100.51, 1000};
    
    VenueId best_venue = execution_engine_->selectOptimalVenue(
        OrderSide::BUY, 1000, snapshot);
    
    // Should select NYSE (best bid price)
    EXPECT_EQ(best_venue, VenueId::NYSE);
}

// ================ MEMORY POOL TESTS ================

TEST_F(HFTSystemTest, MemoryPoolPerformance) {
    // Test zero-allocation memory pool performance
    MemoryPool<Order, 10000> pool;
    
    const int num_allocations = 10000;
    std::vector<Order*> allocations;
    
    auto start = std::chrono::high_resolution_clock::now();
    
    // Allocate
    for (int i = 0; i < num_allocations; ++i) {
        Order* order = pool.allocate();
        ASSERT_NE(order, nullptr);
        allocations.push_back(order);
    }
    
    // Deallocate
    for (Order* order : allocations) {
        pool.deallocate(order);
    }
    
    auto end = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(end - start);
    
    double ops_per_second = (num_allocations * 2 * 1000000000.0) / duration.count();
    double avg_latency_ns = duration.count() / (num_allocations * 2);
    
    std::cout << "Memory pool ops rate: " << ops_per_second << " ops/sec" << std::endl;
    std::cout << "Average allocation latency: " << avg_latency_ns << " nanoseconds" << std::endl;
    
    // Performance target: >10M ops/sec, <100ns average latency
    EXPECT_GT(ops_per_second, 10000000.0);
    EXPECT_LT(avg_latency_ns, 100.0);
}

// ================ LOCK-FREE QUEUE TESTS ================

TEST_F(HFTSystemTest, LockFreeQueueConcurrency) {
    // Test lock-free queue with multiple producers/consumers
    LockFreeQueue<int, 65536> queue;
    std::atomic<int> total_produced{0};
    std::atomic<int> total_consumed{0};
    const int items_per_thread = 10000;
    const int num_producers = 4;
    const int num_consumers = 2;
    
    std::vector<std::thread> producers;
    std::vector<std::thread> consumers;
    
    auto start = std::chrono::high_resolution_clock::now();
    
    // Start producers
    for (int p = 0; p < num_producers; ++p) {
        producers.emplace_back([&queue, &total_produced, items_per_thread, p]() {
            for (int i = 0; i < items_per_thread; ++i) {
                while (!queue.push(p * items_per_thread + i)) {
                    std::this_thread::yield();
                }
                total_produced.fetch_add(1);
            }
        });
    }
    
    // Start consumers
    for (int c = 0; c < num_consumers; ++c) {
        consumers.emplace_back([&queue, &total_consumed, num_producers, items_per_thread]() {
            int item;
            int target = (num_producers * items_per_thread) / 2; // Each consumer gets half
            
            for (int i = 0; i < target; ++i) {
                while (!queue.pop(item)) {
                    std::this_thread::yield();
                }
                total_consumed.fetch_add(1);
            }
        });
    }
    
    // Wait for completion
    for (auto& t : producers) t.join();
    for (auto& t : consumers) t.join();
    
    auto end = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
    
    EXPECT_EQ(total_produced.load(), num_producers * items_per_thread);
    EXPECT_EQ(total_consumed.load(), num_producers * items_per_thread);
    
    double throughput = (total_produced.load() * 1000000.0) / duration.count();
    std::cout << "Lock-free queue throughput: " << throughput << " items/sec" << std::endl;
    
    // Performance target: >1M items/sec throughput
    EXPECT_GT(throughput, 1000000.0);
}

// ================ LATENCY BENCHMARK TESTS ================

TEST_F(HFTSystemTest, EndToEndLatencyBenchmark) {
    // Test full end-to-end latency from market data to order
    const int num_iterations = 1000;
    std::vector<uint64_t> latencies_ns;
    
    for (int i = 0; i < num_iterations; ++i) {
        auto start = std::chrono::high_resolution_clock::now();
        
        // 1. Market data tick
        MarketDataTick tick;
        tick.symbol_id = 1;
        tick.price = 100.0 + (i % 100) * 0.01;
        tick.quantity = 1000;
        tick.timestamp_ns = std::chrono::high_resolution_clock::now()
                           .time_since_epoch().count();
        
        // 2. Strategy signal generation
        TradingSignal signal;
        signal.symbol_id = tick.symbol_id;
        signal.signal_strength = (i % 2) ? 0.8 : -0.8;
        signal.confidence = 0.9;
        signal.suggested_quantity = 500;
        signal.suggested_price_ticks = static_cast<uint32_t>(tick.price * 100);
        signal.strategy_id = 1;
        signal.urgency = 50;
        
        // 3. Order creation
        auto* order = oms_->create_order(
            signal.symbol_id,
            (signal.signal_strength > 0) ? OrderSide::BUY : OrderSide::SELL,
            OrderType::LIMIT,
            tick.price,
            signal.suggested_quantity,
            signal.strategy_id
        );
        
        auto end = std::chrono::high_resolution_clock::now();
        
        if (order) {
            uint64_t latency_ns = std::chrono::duration_cast<std::chrono::nanoseconds>
                                 (end - start).count();
            latencies_ns.push_back(latency_ns);
        }
    }
    
    // Calculate statistics
    std::sort(latencies_ns.begin(), latencies_ns.end());
    
    uint64_t min_latency = latencies_ns.front();
    uint64_t max_latency = latencies_ns.back();
    uint64_t median_latency = latencies_ns[latencies_ns.size() / 2];
    uint64_t p95_latency = latencies_ns[static_cast<size_t>(latencies_ns.size() * 0.95)];
    uint64_t p99_latency = latencies_ns[static_cast<size_t>(latencies_ns.size() * 0.99)];
    
    double avg_latency = 0.0;
    for (uint64_t latency : latencies_ns) {
        avg_latency += latency;
    }
    avg_latency /= latencies_ns.size();
    
    std::cout << "=== End-to-End Latency Benchmark ===" << std::endl;
    std::cout << "Min latency: " << min_latency / 1000.0 << " microseconds" << std::endl;
    std::cout << "Max latency: " << max_latency / 1000.0 << " microseconds" << std::endl;
    std::cout << "Average latency: " << avg_latency / 1000.0 << " microseconds" << std::endl;
    std::cout << "Median latency: " << median_latency / 1000.0 << " microseconds" << std::endl;
    std::cout << "95th percentile: " << p95_latency / 1000.0 << " microseconds" << std::endl;
    std::cout << "99th percentile: " << p99_latency / 1000.0 << " microseconds" << std::endl;
    
    // Performance targets for HFT system
    EXPECT_LT(avg_latency, 100000);    // <100 microseconds average
    EXPECT_LT(p95_latency, 200000);    // <200 microseconds 95th percentile
    EXPECT_LT(p99_latency, 500000);    // <500 microseconds 99th percentile
}

// ================ STRESS TESTS ================

TEST_F(HFTSystemTest, HighThroughputStressTest) {
    // Test system under high load
    const int num_threads = 8;
    const int orders_per_thread = 10000;
    std::atomic<int> successful_orders{0};
    std::atomic<int> failed_orders{0};
    
    std::vector<std::thread> threads;
    auto start = std::chrono::high_resolution_clock::now();
    
    for (int t = 0; t < num_threads; ++t) {
        threads.emplace_back([this, &successful_orders, &failed_orders, 
                             orders_per_thread, t]() {
            for (int i = 0; i < orders_per_thread; ++i) {
                auto* order = oms_->create_order(
                    (t + i) % 10,         // symbol_id
                    (i % 2) ? OrderSide::BUY : OrderSide::SELL,
                    OrderType::LIMIT,
                    100.0 + (i % 100) * 0.01,
                    100 + (i % 1000),
                    t + 1                 // strategy_id
                );
                
                if (order) {
                    successful_orders.fetch_add(1);
                } else {
                    failed_orders.fetch_add(1);
                }
            }
        });
    }
    
    for (auto& thread : threads) {
        thread.join();
    }
    
    auto end = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start);
    
    int total_orders = successful_orders.load() + failed_orders.load();
    double success_rate = static_cast<double>(successful_orders.load()) / total_orders;
    double throughput = (successful_orders.load() * 1000.0) / duration.count();
    
    std::cout << "=== High Throughput Stress Test ===" << std::endl;
    std::cout << "Total orders attempted: " << total_orders << std::endl;
    std::cout << "Successful orders: " << successful_orders.load() << std::endl;
    std::cout << "Failed orders: " << failed_orders.load() << std::endl;
    std::cout << "Success rate: " << success_rate * 100.0 << "%" << std::endl;
    std::cout << "Throughput: " << throughput << " orders/sec" << std::endl;
    
    // Performance targets
    EXPECT_GT(success_rate, 0.95);     // >95% success rate
    EXPECT_GT(throughput, 10000.0);    // >10K orders/sec
}

} // namespace HFT::Testing

// Main test runner
int main(int argc, char** argv) {
    ::testing::InitGoogleTest(&argc, argv);
    ::testing::InitGoogleMock(&argc, argv);
    
    std::cout << "=== HFT System Unit Test Suite ===" << std::endl;
    std::cout << "Testing all critical components with performance benchmarks" << std::endl;
    
    return RUN_ALL_TESTS();
}