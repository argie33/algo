/**
 * Ultra-Low Latency Trading Engine for AWS
 * Designed for EC2 instances with enhanced networking and local storage
 */

#include <memory>
#include <atomic>
#include <array>
#include <vector>
#include <unordered_map>
#include <chrono>
#include <thread>
#include <aws/core/Aws.h>
#include <aws/dynamodb/DynamoDBClient.h>
#include <aws/sns/SNSClient.h>
#include <aws/cloudwatch/CloudWatchClient.h>

#include "market_data_handler_aws.h"
#include "order_management_system.h"
#include "risk_manager.h"
#include "strategy_framework.h"
#include "execution_engine.h"

namespace HFT {

// Order structure optimized for cache efficiency
struct alignas(64) Order {
    uint64_t order_id;
    uint64_t timestamp_ns;
    uint32_t symbol_id;
    uint32_t strategy_id;
    uint32_t price_ticks;        // Price in ticks (scaled)
    uint32_t quantity;
    uint16_t venue_id;
    uint8_t  side;               // Buy=1, Sell=2
    uint8_t  order_type;         // Market=1, Limit=2, Stop=3
    uint8_t  time_in_force;      // IOC=1, FOK=2, GTC=3, DAY=4
    uint8_t  status;             // New=1, PartialFill=2, Filled=3, Cancelled=4
    uint8_t  padding[42];        // Pad to cache line
};

// Signal structure for strategy output
struct alignas(64) TradingSignal {
    uint64_t timestamp_ns;
    uint32_t symbol_id;
    uint32_t strategy_id;
    float    signal_strength;    // -1.0 to 1.0 (sell to buy)
    float    confidence;         // 0.0 to 1.0
    uint32_t suggested_quantity;
    uint32_t suggested_price_ticks;
    uint16_t urgency;           // 0-1000 (milliseconds max delay)
    uint8_t  signal_type;       // Entry=1, Exit=2, Risk=3
    uint8_t  padding[33];
};

class AWSTradingEngine {
private:
    // AWS Integration Components
    std::unique_ptr<Aws::DynamoDB::DynamoDBClient> dynamodb_client_;
    std::unique_ptr<Aws::SNS::SNSClient> sns_client_;
    std::unique_ptr<Aws::CloudWatch::CloudWatchClient> cloudwatch_client_;
    
    // Core trading components
    std::unique_ptr<AWSMarketDataHandler> market_data_handler_;
    std::unique_ptr<OrderManagementSystem> oms_;
    std::unique_ptr<RiskManager> risk_manager_;
    std::unique_ptr<ExecutionEngine> execution_engine_;
    
    // Strategy framework
    std::vector<std::unique_ptr<BaseStrategy>> strategies_;
    
    // Lock-free queues for signal processing
    LockFreeQueue<TradingSignal, 65536> signal_queue_;
    LockFreeQueue<Order, 65536> order_queue_;
    LockFreeQueue<MarketDataEvent, 1048576> market_data_queue_;
    
    // Memory pools for zero-allocation trading
    MemoryPool<Order> order_pool_;
    MemoryPool<TradingSignal> signal_pool_;
    
    // High-frequency trading threads
    std::vector<std::thread> trading_threads_;
    std::atomic<bool> running_{false};
    
    // Performance and latency tracking
    struct alignas(64) TradingMetrics {
        std::atomic<uint64_t> signals_generated{0};
        std::atomic<uint64_t> orders_sent{0};
        std::atomic<uint64_t> orders_filled{0};
        std::atomic<uint64_t> orders_rejected{0};
        
        // Latency measurements (nanoseconds)
        std::atomic<uint64_t> signal_to_order_latency{0};
        std::atomic<uint64_t> order_to_ack_latency{0};
        std::atomic<uint64_t> market_data_to_signal_latency{0};
        
        // P&L tracking
        std::atomic<double> realized_pnl{0.0};
        std::atomic<double> unrealized_pnl{0.0};
        std::atomic<double> gross_exposure{0.0};
        std::atomic<double> net_exposure{0.0};
        
        // Risk metrics
        std::atomic<uint64_t> risk_checks_passed{0};
        std::atomic<uint64_t> risk_checks_failed{0};
    };
    
    TradingMetrics metrics_;
    
    // Configuration for AWS-optimized trading
    struct TradingConfig {
        // CPU affinity for different components
        std::vector<int> signal_processing_cores = {0, 1};
        std::vector<int> order_processing_cores = {2, 3};
        std::vector<int> risk_processing_cores = {4};
        std::vector<int> execution_cores = {5, 6, 7};
        
        // Memory configuration
        bool use_huge_pages = true;
        bool lock_memory = true;
        size_t signal_queue_size = 65536;
        size_t order_queue_size = 65536;
        
        // AWS-specific settings
        std::string dynamodb_table = "hft-orders";
        std::string sns_topic_arn = "arn:aws:sns:us-east-1:account:hft-alerts";
        std::string cloudwatch_namespace = "HFT/Trading";
        
        // Performance targets (nanoseconds)
        uint64_t max_signal_latency = 50000;      // 50 microseconds
        uint64_t max_order_latency = 25000;       // 25 microseconds
        uint64_t max_risk_check_latency = 15000;  // 15 microseconds
    };
    
    TradingConfig config_;
    
public:
    AWSTradingEngine() 
        : order_pool_(100000),
          signal_pool_(1000000)
    {
        initializeAWS();
        initializeComponents();
        setupMemoryOptimizations();
    }
    
    ~AWSTradingEngine() {
        stop();
    }
    
    // Start the trading engine
    void start() {
        running_ = true;
        
        // Start market data handler
        market_data_handler_->start();
        
        // Start trading threads with CPU affinity
        startSignalProcessingThreads();
        startOrderProcessingThreads();
        startRiskProcessingThreads();
        startExecutionThreads();
        
        // Start AWS monitoring
        startCloudWatchMetrics();
    }
    
    // Stop the trading engine
    void stop() {
        running_ = false;
        
        // Stop market data handler
        if (market_data_handler_) {
            market_data_handler_->stop();
        }
        
        // Join all trading threads
        for (auto& thread : trading_threads_) {
            if (thread.joinable()) {
                thread.join();
            }
        }
        trading_threads_.clear();
        
        // Persist final state to DynamoDB
        persistTradingState();
    }
    
    // Add a trading strategy
    void addStrategy(std::unique_ptr<BaseStrategy> strategy) {
        strategies_.push_back(std::move(strategy));
    }
    
    // Get current performance metrics
    TradingMetrics getMetrics() const {
        return metrics_;
    }

private:
    void initializeAWS() {
        // Initialize AWS SDK with optimized settings
        Aws::SDKOptions options;
        options.loggingOptions.logLevel = Aws::Utils::Logging::LogLevel::Error;
        Aws::InitAPI(options);
        
        // DynamoDB client for order persistence
        Aws::Client::ClientConfiguration dynamodb_config;
        dynamodb_config.region = Aws::Region::US_EAST_1;
        dynamodb_config.maxConnections = 50;
        dynamodb_config.requestTimeoutMs = 1000;
        dynamodb_client_ = std::make_unique<Aws::DynamoDB::DynamoDBClient>(dynamodb_config);
        
        // SNS client for alerts
        sns_client_ = std::make_unique<Aws::SNS::SNSClient>(dynamodb_config);
        
        // CloudWatch client for metrics
        cloudwatch_client_ = std::make_unique<Aws::CloudWatch::CloudWatchClient>(dynamodb_config);
    }
    
    void initializeComponents() {
        // Initialize market data handler
        market_data_handler_ = std::make_unique<AWSMarketDataHandler>();
        
        // Initialize order management system
        oms_ = std::make_unique<OrderManagementSystem>(dynamodb_client_.get());
        
        // Initialize risk manager
        risk_manager_ = std::make_unique<RiskManager>();
        
        // Initialize execution engine
        execution_engine_ = std::make_unique<ExecutionEngine>();
    }
    
    void setupMemoryOptimizations() {
        if (config_.use_huge_pages) {
            // Enable huge pages for better memory performance
            system("echo always > /sys/kernel/mm/transparent_hugepage/enabled");
        }
        
        if (config_.lock_memory) {
            // Lock memory to prevent swapping
            mlockall(MCL_CURRENT | MCL_FUTURE);
        }
    }
    
    void startSignalProcessingThreads() {
        for (size_t i = 0; i < config_.signal_processing_cores.size(); ++i) {
            trading_threads_.emplace_back([this, i]() {
                // Set CPU affinity
                setCPUAffinity(config_.signal_processing_cores[i]);
                
                // Set real-time priority
                setRealtimePriority(99);
                
                // Signal processing loop
                processSignals();
            });
        }
    }
    
    void startOrderProcessingThreads() {
        for (size_t i = 0; i < config_.order_processing_cores.size(); ++i) {
            trading_threads_.emplace_back([this, i]() {
                setCPUAffinity(config_.order_processing_cores[i]);
                setRealtimePriority(98);
                processOrders();
            });
        }
    }
    
    void startRiskProcessingThreads() {
        for (size_t i = 0; i < config_.risk_processing_cores.size(); ++i) {
            trading_threads_.emplace_back([this, i]() {
                setCPUAffinity(config_.risk_processing_cores[i]);
                setRealtimePriority(97);
                processRiskChecks();
            });
        }
    }
    
    void startExecutionThreads() {
        for (size_t i = 0; i < config_.execution_cores.size(); ++i) {
            trading_threads_.emplace_back([this, i]() {
                setCPUAffinity(config_.execution_cores[i]);
                setRealtimePriority(96);
                processExecution();
            });
        }
    }
    
    // Main signal processing loop
    __attribute__((hot)) void processSignals() {
        MarketDataEvent market_event;
        
        while (running_) {
            // Get market data from handler
            if (market_data_handler_->getTrade(market_event)) {
                uint64_t start_time = rdtsc();
                
                // Run all strategies on this market event
                for (auto& strategy : strategies_) {
                    strategy->onMarketData(market_event);
                    
                    // Check if strategy generated a signal
                    if (strategy->hasSignal()) {
                        TradingSignal signal = strategy->getSignal();
                        signal.timestamp_ns = start_time;
                        
                        // Push to signal queue
                        if (!signal_queue_.push(signal)) {
                            // Queue overflow - critical issue
                            sendAlert("Signal queue overflow detected");
                        }
                        
                        metrics_.signals_generated++;
                    }
                }
                
                // Update latency metrics
                uint64_t processing_time = rdtsc() - start_time;
                updateLatencyMetric(metrics_.market_data_to_signal_latency, processing_time);
                
                // Check for performance degradation
                if (processing_time > config_.max_signal_latency) {
                    sendAlert("Signal processing latency exceeded threshold");
                }
            }
        }
    }
    
    // Order processing and generation
    __attribute__((hot)) void processOrders() {
        TradingSignal signal;
        
        while (running_) {
            if (signal_queue_.pop(signal)) {
                uint64_t start_time = rdtsc();
                
                // Convert signal to order
                Order* order = generateOrder(signal);
                if (order) {
                    // Push to order queue for risk checking
                    if (!order_queue_.push(*order)) {
                        sendAlert("Order queue overflow detected");
                    }
                    
                    metrics_.orders_sent++;
                }
                
                // Update latency
                uint64_t processing_time = rdtsc() - start_time;
                updateLatencyMetric(metrics_.signal_to_order_latency, processing_time);
            }
        }
    }
    
    // Risk management processing
    __attribute__((hot)) void processRiskChecks() {
        Order order;
        
        while (running_) {
            if (order_queue_.pop(order)) {
                uint64_t start_time = rdtsc();
                
                // Perform risk checks
                bool risk_passed = risk_manager_->checkPreTradeRisk(order);
                
                if (risk_passed) {
                    // Send to execution
                    execution_engine_->submitOrder(order);
                    metrics_.risk_checks_passed++;
                } else {
                    // Risk check failed
                    handleRiskRejection(order);
                    metrics_.risk_checks_failed++;
                }
                
                // Update risk check latency
                uint64_t processing_time = rdtsc() - start_time;
                if (processing_time > config_.max_risk_check_latency) {
                    sendAlert("Risk check latency exceeded threshold");
                }
            }
        }
    }
    
    // Execution processing
    __attribute__((hot)) void processExecution() {
        while (running_) {
            // Process execution reports
            execution_engine_->processExecutionReports();
            
            // Update positions and P&L
            updatePortfolioMetrics();
            
            // Process any execution-related AWS operations
            processAWSExecutionTasks();
        }
    }
    
    // Generate order from trading signal
    Order* generateOrder(const TradingSignal& signal) {
        Order* order = order_pool_.allocate();
        if (!order) return nullptr;
        
        order->order_id = generateOrderID();
        order->timestamp_ns = rdtsc_to_ns(rdtsc());
        order->symbol_id = signal.symbol_id;
        order->strategy_id = signal.strategy_id;
        order->price_ticks = signal.suggested_price_ticks;
        order->quantity = signal.suggested_quantity;
        order->side = signal.signal_strength > 0 ? 1 : 2;  // Buy=1, Sell=2
        order->status = 1;  // New
        
        // Determine order type based on urgency
        if (signal.urgency < 100) {  // < 100ms urgency
            order->order_type = 1;   // Market order
            order->time_in_force = 1; // IOC
        } else {
            order->order_type = 2;   // Limit order
            order->time_in_force = 4; // DAY
        }
        
        return order;
    }
    
    // Send alert via AWS SNS
    void sendAlert(const std::string& message) {
        Aws::SNS::Model::PublishRequest request;
        request.SetTopicArn(config_.sns_topic_arn);
        request.SetMessage(message);
        request.SetSubject("HFT Trading Alert");
        
        // Async publish (non-blocking)
        sns_client_->PublishAsync(request, 
            [](const Aws::SNS::SNSClient* client,
               const Aws::SNS::Model::PublishRequest& request,
               const Aws::SNS::Model::PublishOutcome& outcome,
               const std::shared_ptr<const Aws::Client::AsyncCallerContext>& context) {
                // Alert sent (or failed silently)
            });
    }
    
    // Send metrics to CloudWatch
    void startCloudWatchMetrics() {
        trading_threads_.emplace_back([this]() {
            while (running_) {
                sendMetricsToCloudWatch();
                std::this_thread::sleep_for(std::chrono::seconds(10));
            }
        });
    }
    
    void sendMetricsToCloudWatch() {
        // Create CloudWatch metric data
        std::vector<Aws::CloudWatch::Model::MetricDatum> metrics;
        
        // Add key trading metrics
        addMetric(metrics, "SignalsGenerated", metrics_.signals_generated.load());
        addMetric(metrics, "OrdersSent", metrics_.orders_sent.load());
        addMetric(metrics, "OrdersFilled", metrics_.orders_filled.load());
        addMetric(metrics, "RealizedPnL", metrics_.realized_pnl.load());
        addMetric(metrics, "GrossExposure", metrics_.gross_exposure.load());
        
        // Send to CloudWatch
        Aws::CloudWatch::Model::PutMetricDataRequest request;
        request.SetNamespace(config_.cloudwatch_namespace);
        request.SetMetricData(metrics);
        
        cloudwatch_client_->PutMetricDataAsync(request, nullptr);
    }
    
    void addMetric(std::vector<Aws::CloudWatch::Model::MetricDatum>& metrics,
                   const std::string& name, double value) {
        Aws::CloudWatch::Model::MetricDatum datum;
        datum.SetMetricName(name);
        datum.SetValue(value);
        datum.SetTimestamp(Aws::Utils::DateTime::Now());
        metrics.push_back(datum);
    }
    
    // Utility functions
    void setCPUAffinity(int cpu_id) {
        cpu_set_t cpuset;
        CPU_ZERO(&cpuset);
        CPU_SET(cpu_id, &cpuset);
        pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
    }
    
    void setRealtimePriority(int priority) {
        struct sched_param param;
        param.sched_priority = priority;
        pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
    }
    
    uint64_t generateOrderID() {
        static std::atomic<uint64_t> order_counter{1};
        return order_counter.fetch_add(1);
    }
    
    __attribute__((always_inline)) inline uint64_t rdtsc() {
        uint32_t hi, lo;
        __asm__ __volatile__ ("rdtsc" : "=a"(lo), "=d"(hi));
        return ((uint64_t)hi << 32) | lo;
    }
    
    uint64_t rdtsc_to_ns(uint64_t tsc) {
        // Convert TSC to nanoseconds (assuming 3GHz CPU)
        return tsc / 3;
    }
    
    void updateLatencyMetric(std::atomic<uint64_t>& metric, uint64_t new_value) {
        // Simple exponential moving average
        uint64_t current = metric.load();
        uint64_t updated = (current * 15 + new_value) / 16;  // 15/16 weight to history
        metric.store(updated);
    }
    
    void persistTradingState() {
        // Save critical trading state to DynamoDB for recovery
        // This would include positions, pending orders, etc.
    }
    
    void processAWSExecutionTasks() {
        // Handle any AWS-specific execution tasks
        // Such as updating DynamoDB, sending notifications, etc.
    }
    
    void updatePortfolioMetrics() {
        // Update real-time P&L and exposure metrics
        // This would typically query current positions and market prices
    }
    
    void handleRiskRejection(const Order& order) {
        // Handle risk rejection - log, alert, and possibly adjust strategy
        sendAlert("Order rejected by risk management: " + std::to_string(order.order_id));
    }
};

} // namespace HFT