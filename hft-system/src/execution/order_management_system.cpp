/**
 * Order Management System (OMS)
 * Handles order lifecycle, routing, and execution tracking
 */

#include <memory>
#include <unordered_map>
#include <atomic>
#include <queue>
#include <mutex>
#include <thread>
#include <chrono>
#include <aws/dynamodb/DynamoDBClient.h>
#include "lock_free_queue.h"

namespace HFT {

// Order states
enum class OrderState : uint8_t {
    PENDING = 0,
    SUBMITTED = 1,
    ACKNOWLEDGED = 2,
    PARTIAL_FILL = 3,
    FILLED = 4,
    CANCELLED = 5,
    REJECTED = 6,
    EXPIRED = 7
};

// Order types
enum class OrderType : uint8_t {
    MARKET = 1,
    LIMIT = 2,
    STOP = 3,
    STOP_LIMIT = 4,
    ICEBERG = 5
};

// Time in force
enum class TimeInForce : uint8_t {
    IOC = 1,  // Immediate or Cancel
    FOK = 2,  // Fill or Kill
    GTC = 3,  // Good Till Cancel
    DAY = 4,  // Day order
    GTD = 5   // Good Till Date
};

// Execution report
struct ExecutionReport {
    uint64_t report_id;
    uint64_t order_id;
    uint64_t timestamp_ns;
    uint32_t symbol_id;
    uint32_t executed_quantity;
    uint32_t remaining_quantity;
    double execution_price;
    OrderState order_state;
    std::string venue_order_id;
    std::string execution_id;
    double commission;
    char rejection_reason[128];
};

// Order book for tracking
struct OrderBookEntry {
    uint64_t order_id;
    uint32_t symbol_id;
    uint32_t quantity;
    uint32_t filled_quantity;
    double price;
    uint8_t side;
    OrderType order_type;
    TimeInForce time_in_force;
    OrderState state;
    uint64_t creation_time_ns;
    uint64_t last_update_ns;
    uint32_t strategy_id;
};

class OrderManagementSystem {
private:
    // AWS DynamoDB for order persistence
    std::unique_ptr<Aws::DynamoDB::DynamoDBClient> dynamodb_client_;
    
    // Order tracking
    std::unordered_map<uint64_t, OrderBookEntry> active_orders_;
    std::unordered_map<uint64_t, OrderBookEntry> completed_orders_;
    std::mutex orders_mutex_;
    
    // Execution reports queue
    LockFreeQueue<ExecutionReport, 65536> execution_reports_;
    
    // Order ID generation
    std::atomic<uint64_t> next_order_id_{1};
    
    // Performance metrics
    struct OMSMetrics {
        std::atomic<uint64_t> orders_submitted{0};
        std::atomic<uint64_t> orders_filled{0};
        std::atomic<uint64_t> orders_cancelled{0};
        std::atomic<uint64_t> orders_rejected{0};
        std::atomic<uint64_t> avg_ack_latency_ns{0};
        std::atomic<uint64_t> avg_fill_latency_ns{0};
        std::atomic<double> fill_rate{0.0};
    };
    
    OMSMetrics metrics_;
    
    // Configuration
    struct OMSConfig {
        std::string dynamodb_table = "hft-orders";
        uint32_t order_timeout_seconds = 300;  // 5 minutes
        bool enable_order_persistence = true;
        bool enable_fill_validation = true;
        double max_order_value = 1000000.0;    // $1M max order
    };
    
    OMSConfig config_;
    
    // Threading
    std::thread order_processor_thread_;
    std::atomic<bool> running_{false};
    
public:
    OrderManagementSystem(Aws::DynamoDB::DynamoDBClient* dynamodb_client = nullptr)
        : dynamodb_client_(dynamodb_client ? 
                          std::unique_ptr<Aws::DynamoDB::DynamoDBClient>(dynamodb_client) : 
                          nullptr) {
    }
    
    ~OrderManagementSystem() {
        stop();
    }
    
    void start() {
        running_ = true;
        order_processor_thread_ = std::thread([this]() {
            processOrders();
        });
    }
    
    void stop() {
        running_ = false;
        if (order_processor_thread_.joinable()) {
            order_processor_thread_.join();
        }
    }
    
    // Submit a new order
    uint64_t submitOrder(const TradingSignal& signal) {
        uint64_t order_id = generateOrderId();
        uint64_t current_time = getCurrentTimeNs();
        
        OrderBookEntry order;
        order.order_id = order_id;
        order.symbol_id = signal.symbol_id;
        order.quantity = signal.suggested_quantity;
        order.filled_quantity = 0;
        order.price = signal.suggested_price_ticks * 0.01;
        order.side = signal.signal_strength > 0 ? 1 : 2; // Buy=1, Sell=2
        order.order_type = determineOrderType(signal);
        order.time_in_force = determineTimeInForce(signal);
        order.state = OrderState::PENDING;
        order.creation_time_ns = current_time;
        order.last_update_ns = current_time;
        order.strategy_id = signal.strategy_id;
        
        // Validate order
        if (!validateOrder(order)) {
            return 0; // Invalid order
        }
        
        {
            std::lock_guard<std::mutex> lock(orders_mutex_);
            active_orders_[order_id] = order;
        }
        
        // Route to execution venue
        bool routed = routeOrder(order);
        if (routed) {
            updateOrderState(order_id, OrderState::SUBMITTED);
            metrics_.orders_submitted++;
            
            // Persist to DynamoDB
            if (config_.enable_order_persistence) {
                persistOrder(order);
            }
        } else {
            updateOrderState(order_id, OrderState::REJECTED);
            metrics_.orders_rejected++;
        }
        
        return order_id;
    }
    
    // Cancel an order
    bool cancelOrder(uint64_t order_id) {
        std::lock_guard<std::mutex> lock(orders_mutex_);
        
        auto it = active_orders_.find(order_id);
        if (it == active_orders_.end()) {
            return false; // Order not found
        }
        
        OrderBookEntry& order = it->second;
        
        // Can only cancel if not filled
        if (order.state == OrderState::FILLED) {
            return false;
        }
        
        // Send cancellation to venue
        bool cancelled = sendCancellation(order);
        if (cancelled) {
            updateOrderState(order_id, OrderState::CANCELLED);
            metrics_.orders_cancelled++;
        }
        
        return cancelled;
    }
    
    // Process execution report
    void processExecutionReport(const ExecutionReport& report) {
        std::lock_guard<std::mutex> lock(orders_mutex_);
        
        auto it = active_orders_.find(report.order_id);
        if (it == active_orders_.end()) {
            return; // Order not found
        }
        
        OrderBookEntry& order = it->second;
        
        // Update order state
        order.filled_quantity += report.executed_quantity;
        order.state = report.order_state;
        order.last_update_ns = report.timestamp_ns;
        
        // Calculate latencies
        uint64_t ack_latency = report.timestamp_ns - order.creation_time_ns;
        updateLatencyMetric(metrics_.avg_ack_latency_ns, ack_latency);
        
        if (report.order_state == OrderState::FILLED || 
            report.order_state == OrderState::PARTIAL_FILL) {
            
            uint64_t fill_latency = report.timestamp_ns - order.creation_time_ns;
            updateLatencyMetric(metrics_.avg_fill_latency_ns, fill_latency);
            
            if (report.order_state == OrderState::FILLED) {
                metrics_.orders_filled++;
                
                // Move to completed orders
                completed_orders_[order.order_id] = order;
                active_orders_.erase(it);
            }
        }
        
        // Update fill rate
        calculateFillRate();
        
        // Push to execution reports queue for strategies
        execution_reports_.push(report);
        
        // Persist state change
        if (config_.enable_order_persistence) {
            persistOrderUpdate(order, report);
        }
    }
    
    // Get order status
    OrderBookEntry getOrder(uint64_t order_id) const {
        std::lock_guard<std::mutex> lock(orders_mutex_);
        
        auto it = active_orders_.find(order_id);
        if (it != active_orders_.end()) {
            return it->second;
        }
        
        auto completed_it = completed_orders_.find(order_id);
        if (completed_it != completed_orders_.end()) {
            return completed_it->second;
        }
        
        return OrderBookEntry{}; // Not found
    }
    
    // Get all active orders
    std::vector<OrderBookEntry> getActiveOrders() const {
        std::lock_guard<std::mutex> lock(orders_mutex_);
        
        std::vector<OrderBookEntry> orders;
        orders.reserve(active_orders_.size());
        
        for (const auto& [order_id, order] : active_orders_) {
            orders.push_back(order);
        }
        
        return orders;
    }
    
    // Get execution reports
    bool getExecutionReport(ExecutionReport& report) {
        return execution_reports_.pop(report);
    }
    
    // Get metrics
    OMSMetrics getMetrics() const {
        return metrics_;
    }
    
    // Cancel all orders for a symbol
    void cancelAllOrders(uint32_t symbol_id) {
        std::lock_guard<std::mutex> lock(orders_mutex_);
        
        std::vector<uint64_t> orders_to_cancel;
        
        for (const auto& [order_id, order] : active_orders_) {
            if (order.symbol_id == symbol_id && 
                order.state != OrderState::FILLED &&
                order.state != OrderState::CANCELLED) {
                orders_to_cancel.push_back(order_id);
            }
        }
        
        // Cancel each order (unlock mutex first to avoid deadlock)
        for (uint64_t order_id : orders_to_cancel) {
            cancelOrder(order_id);
        }
    }

private:
    uint64_t generateOrderId() {
        return next_order_id_.fetch_add(1);
    }
    
    bool validateOrder(const OrderBookEntry& order) {
        // Basic validation
        if (order.quantity == 0) return false;
        if (order.price <= 0 && order.order_type != OrderType::MARKET) return false;
        
        // Value validation
        double order_value = order.quantity * order.price;
        if (order_value > config_.max_order_value) return false;
        
        return true;
    }
    
    OrderType determineOrderType(const TradingSignal& signal) {
        if (signal.urgency < 100) {
            return OrderType::MARKET; // High urgency = market order
        } else {
            return OrderType::LIMIT;  // Low urgency = limit order
        }
    }
    
    TimeInForce determineTimeInForce(const TradingSignal& signal) {
        if (signal.urgency < 50) {
            return TimeInForce::IOC; // Very urgent = IOC
        } else if (signal.urgency < 200) {
            return TimeInForce::FOK; // Urgent = FOK
        } else {
            return TimeInForce::DAY; // Normal = DAY
        }
    }
    
    bool routeOrder(const OrderBookEntry& order) {
        // Simulate order routing to execution venue
        // In real implementation, this would connect to actual venues
        
        // Simulate random routing success/failure
        return (rand() % 100) < 95; // 95% success rate
    }
    
    bool sendCancellation(const OrderBookEntry& order) {
        // Simulate cancel request to venue
        return (rand() % 100) < 90; // 90% cancel success rate
    }
    
    void updateOrderState(uint64_t order_id, OrderState new_state) {
        std::lock_guard<std::mutex> lock(orders_mutex_);
        
        auto it = active_orders_.find(order_id);
        if (it != active_orders_.end()) {
            it->second.state = new_state;
            it->second.last_update_ns = getCurrentTimeNs();
        }
    }
    
    void processOrders() {
        while (running_) {
            // Check for expired orders
            checkExpiredOrders();
            
            // Process any venue messages (simulated)
            simulateVenueMessages();
            
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
    }
    
    void checkExpiredOrders() {
        uint64_t current_time = getCurrentTimeNs();
        uint64_t timeout_ns = config_.order_timeout_seconds * 1000000000ULL;
        
        std::vector<uint64_t> expired_orders;
        
        {
            std::lock_guard<std::mutex> lock(orders_mutex_);
            
            for (const auto& [order_id, order] : active_orders_) {
                if (order.time_in_force == TimeInForce::DAY &&
                    (current_time - order.creation_time_ns) > timeout_ns) {
                    expired_orders.push_back(order_id);
                }
            }
        }
        
        // Expire orders
        for (uint64_t order_id : expired_orders) {
            updateOrderState(order_id, OrderState::EXPIRED);
        }
    }
    
    void simulateVenueMessages() {
        // Simulate random execution reports for testing
        // In real implementation, this would receive actual venue messages
        
        if ((rand() % 1000) < 5) { // 0.5% chance per iteration
            std::lock_guard<std::mutex> lock(orders_mutex_);
            
            if (!active_orders_.empty()) {
                // Pick a random order to fill
                auto it = active_orders_.begin();
                std::advance(it, rand() % active_orders_.size());
                
                const OrderBookEntry& order = it->second;
                
                if (order.state == OrderState::SUBMITTED || 
                    order.state == OrderState::ACKNOWLEDGED) {
                    
                    ExecutionReport report;
                    report.report_id = rand();
                    report.order_id = order.order_id;
                    report.timestamp_ns = getCurrentTimeNs();
                    report.symbol_id = order.symbol_id;
                    report.executed_quantity = order.quantity - order.filled_quantity;
                    report.remaining_quantity = 0;
                    report.execution_price = order.price;
                    report.order_state = OrderState::FILLED;
                    report.commission = order.quantity * 0.005; // $0.005 per share
                    
                    processExecutionReport(report);
                }
            }
        }
    }
    
    void calculateFillRate() {
        uint64_t total_orders = metrics_.orders_submitted.load();
        uint64_t filled_orders = metrics_.orders_filled.load();
        
        if (total_orders > 0) {
            double fill_rate = static_cast<double>(filled_orders) / total_orders;
            metrics_.fill_rate.store(fill_rate);
        }
    }
    
    void updateLatencyMetric(std::atomic<uint64_t>& metric, uint64_t new_value) {
        uint64_t current = metric.load();
        uint64_t updated = (current * 15 + new_value) / 16; // EMA
        metric.store(updated);
    }
    
    void persistOrder(const OrderBookEntry& order) {
        if (!dynamodb_client_) return;
        
        // Create DynamoDB put item request
        // Implementation would serialize order to DynamoDB format
    }
    
    void persistOrderUpdate(const OrderBookEntry& order, const ExecutionReport& report) {
        if (!dynamodb_client_) return;
        
        // Update order record in DynamoDB
        // Implementation would update the order state and execution details
    }
    
    uint64_t getCurrentTimeNs() const {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::high_resolution_clock::now().time_since_epoch()).count();
    }
};

} // namespace HFT