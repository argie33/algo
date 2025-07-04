/**
 * AWS-Optimized Real-Time Risk Management System
 * Ultra-fast risk checks with hardware acceleration support
 */

#include <memory>
#include <atomic>
#include <array>
#include <unordered_map>
#include <vector>
#include <aws/core/Aws.h>
#include <aws/dynamodb/DynamoDBClient.h>
#include <aws/cloudwatch/CloudWatchClient.h>
#include <aws/sns/SNSClient.h>
#include <eigen3/Eigen/Dense>

#include "trading_engine_aws.h"
#include "portfolio_tracker.h"

namespace HFT {

// Risk limit structure (cache-aligned)
struct alignas(64) RiskLimits {
    // Position limits
    double max_position_value;          // Maximum position value per symbol
    double max_gross_exposure;          // Maximum gross portfolio exposure
    double max_net_exposure;            // Maximum net portfolio exposure
    uint32_t max_order_quantity;        // Maximum single order quantity
    
    // Loss limits
    double max_daily_loss;              // Maximum daily loss
    double max_drawdown;                // Maximum drawdown from high water mark
    double max_hourly_loss;             // Maximum loss per hour
    double max_var_breach_count;        // Maximum VaR breaches per day
    
    // Concentration limits
    double max_single_stock_weight;     // Maximum weight in single stock
    double max_sector_weight;           // Maximum weight in sector
    double max_strategy_allocation;     // Maximum allocation per strategy
    
    // Trading velocity limits
    uint32_t max_orders_per_second;     // Maximum order rate
    uint32_t max_fills_per_minute;      // Maximum fill rate
    
    // Market condition limits
    double max_volatility_threshold;    // Stop trading if volatility too high
    double max_spread_threshold;        // Don't trade if spread too wide
    
    uint8_t padding[8];                 // Pad to cache line
};

// Real-time position tracking (cache-aligned)
struct alignas(64) Position {
    uint32_t symbol_id;
    int32_t  quantity;                  // Signed quantity (long/short)
    double   average_price;             // Average cost basis
    double   market_value;              // Current market value
    double   unrealized_pnl;            // Unrealized P&L
    double   realized_pnl;              // Realized P&L today
    uint64_t last_update_ns;            // Last update timestamp
    uint8_t  padding[24];
};

// Risk check result
enum class RiskCheckResult : uint8_t {
    APPROVED = 0,
    REJECTED_POSITION_LIMIT = 1,
    REJECTED_LOSS_LIMIT = 2,
    REJECTED_CONCENTRATION = 3,
    REJECTED_VELOCITY = 4,
    REJECTED_MARKET_CONDITIONS = 5,
    REJECTED_VAR_LIMIT = 6,
    REJECTED_CORRELATION = 7
};

class AWSRiskManager {
private:
    // AWS Integration
    std::unique_ptr<Aws::DynamoDB::DynamoDBClient> dynamodb_client_;
    std::unique_ptr<Aws::CloudWatch::CloudWatchClient> cloudwatch_client_;
    std::unique_ptr<Aws::SNS::SNSClient> sns_client_;
    
    // Risk limits and configuration
    RiskLimits limits_;
    
    // Real-time position tracking (lock-free where possible)
    std::array<Position, 65536> positions_;  // Fast array lookup by symbol_id
    std::atomic<double> gross_exposure_{0.0};
    std::atomic<double> net_exposure_{0.0};
    std::atomic<double> daily_pnl_{0.0};
    std::atomic<double> current_drawdown_{0.0};
    std::atomic<double> high_water_mark_{0.0};
    
    // Portfolio correlation matrix (for concentration risk)
    Eigen::MatrixXd correlation_matrix_;
    std::vector<double> sector_weights_;
    std::vector<double> strategy_weights_;
    
    // Rate limiting (sliding window)
    struct RateLimiter {
        std::array<uint64_t, 60> order_counts_per_second;  // Last 60 seconds
        std::array<uint64_t, 60> fill_counts_per_minute;   // Last 60 minutes
        std::atomic<uint32_t> current_second_index{0};
        std::atomic<uint32_t> current_minute_index{0};
    };
    
    RateLimiter rate_limiter_;
    
    // VaR calculation state
    struct VaRState {
        double portfolio_var_95;            // 95% VaR
        double portfolio_cvar_95;           // 95% CVaR
        uint32_t var_breaches_today;        // VaR breach count
        Eigen::VectorXd position_vector;    // Position vector for VaR calc
        uint64_t last_var_update_ns;       // Last VaR calculation time
    };
    
    VaRState var_state_;
    
    // Performance metrics
    struct alignas(64) RiskMetrics {
        std::atomic<uint64_t> risk_checks_performed{0};
        std::atomic<uint64_t> risk_checks_passed{0};
        std::atomic<uint64_t> risk_checks_failed{0};
        std::atomic<uint64_t> avg_check_latency_ns{0};
        std::atomic<uint64_t> max_check_latency_ns{0};
        std::atomic<uint32_t> kill_switch_activations{0};
    };
    
    RiskMetrics metrics_;
    
    // Kill switch state
    enum class KillSwitchLevel : uint8_t {
        NONE = 0,
        REDUCE_ONLY = 1,      // No new positions
        CLOSE_ONLY = 2,       // Orderly liquidation
        EMERGENCY_STOP = 3    // Immediate halt
    };
    
    std::atomic<KillSwitchLevel> kill_switch_level_{KillSwitchLevel::NONE};
    
    // AWS configuration
    struct AWSConfig {
        std::string dynamodb_positions_table = "hft-positions";
        std::string dynamodb_risk_events_table = "hft-risk-events";
        std::string sns_alerts_topic = "arn:aws:sns:us-east-1:account:hft-risk-alerts";
        std::string cloudwatch_namespace = "HFT/Risk";
    };
    
    AWSConfig aws_config_;

public:
    AWSRiskManager() {
        initializeAWS();
        initializeRiskLimits();
        initializeCorrelationMatrix();
        setupPerformanceMonitoring();
    }
    
    ~AWSRiskManager() {
        persistRiskState();
    }
    
    // Main risk check function - ultra-fast path
    __attribute__((hot, flatten)) 
    RiskCheckResult checkPreTradeRisk(const Order& order) {
        uint64_t start_time = rdtsc();
        
        // Immediate kill switch check
        if (kill_switch_level_.load() >= KillSwitchLevel::REDUCE_ONLY) {
            if (isNewPosition(order)) {
                updateRiskMetrics(start_time, false);
                return RiskCheckResult::REJECTED_POSITION_LIMIT;
            }
        }
        
        if (kill_switch_level_.load() >= KillSwitchLevel::CLOSE_ONLY) {
            if (!isPositionClosing(order)) {
                updateRiskMetrics(start_time, false);
                return RiskCheckResult::REJECTED_POSITION_LIMIT;
            }
        }
        
        if (kill_switch_level_.load() >= KillSwitchLevel::EMERGENCY_STOP) {
            updateRiskMetrics(start_time, false);
            return RiskCheckResult::REJECTED_POSITION_LIMIT;
        }
        
        // Fast path checks (most common rejections first)
        
        // 1. Rate limiting check
        if (!checkRateLimit(order)) {
            updateRiskMetrics(start_time, false);
            return RiskCheckResult::REJECTED_VELOCITY;
        }
        
        // 2. Position size check
        if (!checkPositionLimits(order)) {
            updateRiskMetrics(start_time, false);
            return RiskCheckResult::REJECTED_POSITION_LIMIT;
        }
        
        // 3. Loss limit check
        if (!checkLossLimits(order)) {
            updateRiskMetrics(start_time, false);
            return RiskCheckResult::REJECTED_LOSS_LIMIT;
        }
        
        // 4. Concentration check
        if (!checkConcentrationLimits(order)) {
            updateRiskMetrics(start_time, false);
            return RiskCheckResult::REJECTED_CONCENTRATION;
        }
        
        // 5. Market condition check
        if (!checkMarketConditions(order)) {
            updateRiskMetrics(start_time, false);
            return RiskCheckResult::REJECTED_MARKET_CONDITIONS;
        }
        
        // 6. VaR check (most expensive, done last)
        if (!checkVaRLimits(order)) {
            updateRiskMetrics(start_time, false);
            return RiskCheckResult::REJECTED_VAR_LIMIT;
        }
        
        // All checks passed
        updateRiskMetrics(start_time, true);
        return RiskCheckResult::APPROVED;
    }
    
    // Update position after trade execution
    void updatePosition(uint32_t symbol_id, int32_t quantity_change, double price) {
        Position& pos = positions_[symbol_id];
        
        // Update position atomically where possible
        int32_t old_quantity = pos.quantity;
        int32_t new_quantity = old_quantity + quantity_change;
        
        // Calculate new average price
        if (new_quantity != 0) {
            double total_cost = pos.average_price * old_quantity + price * quantity_change;
            pos.average_price = total_cost / new_quantity;
        }
        
        pos.quantity = new_quantity;
        pos.last_update_ns = rdtsc_to_ns(rdtsc());
        
        // Update portfolio-level metrics
        updatePortfolioMetrics();
        
        // Persist to DynamoDB asynchronously
        persistPositionUpdate(symbol_id, pos);
    }
    
    // Activate kill switch
    void activateKillSwitch(KillSwitchLevel level, const std::string& reason) {
        KillSwitchLevel current_level = kill_switch_level_.load();
        
        // Only escalate, never downgrade automatically
        if (level > current_level) {
            kill_switch_level_.store(level);
            metrics_.kill_switch_activations++;
            
            // Send immediate alert
            sendCriticalAlert("Kill switch activated", reason, static_cast<int>(level));
            
            // Log to CloudWatch
            logKillSwitchEvent(level, reason);
            
            // Persist to DynamoDB
            persistKillSwitchEvent(level, reason);
        }
    }
    
    // Get current risk metrics
    RiskMetrics getRiskMetrics() const {
        return metrics_;
    }
    
    // Get current portfolio state
    struct PortfolioState {
        double gross_exposure;
        double net_exposure;
        double daily_pnl;
        double current_drawdown;
        double portfolio_var;
        uint32_t active_positions;
        KillSwitchLevel kill_switch_level;
    };
    
    PortfolioState getPortfolioState() const {
        return {
            gross_exposure_.load(),
            net_exposure_.load(),
            daily_pnl_.load(),
            current_drawdown_.load(),
            var_state_.portfolio_var_95,
            countActivePositions(),
            kill_switch_level_.load()
        };
    }

private:
    void initializeAWS() {
        Aws::SDKOptions options;
        Aws::InitAPI(options);
        
        // Initialize AWS clients
        Aws::Client::ClientConfiguration config;
        config.region = Aws::Region::US_EAST_1;
        config.maxConnections = 25;
        config.requestTimeoutMs = 1000;
        
        dynamodb_client_ = std::make_unique<Aws::DynamoDB::DynamoDBClient>(config);
        cloudwatch_client_ = std::make_unique<Aws::CloudWatch::CloudWatchClient>(config);
        sns_client_ = std::make_unique<Aws::SNS::SNSClient>(config);
    }
    
    void initializeRiskLimits() {
        // Set conservative default limits
        limits_ = {
            .max_position_value = 1000000.0,      // $1M per position
            .max_gross_exposure = 50000000.0,     // $50M gross
            .max_net_exposure = 10000000.0,       // $10M net
            .max_order_quantity = 10000,          // 10k shares max
            
            .max_daily_loss = 500000.0,           // $500k daily loss
            .max_drawdown = 0.10,                 // 10% drawdown
            .max_hourly_loss = 100000.0,          // $100k hourly loss
            .max_var_breach_count = 5,            // 5 VaR breaches per day
            
            .max_single_stock_weight = 0.05,      // 5% in single stock
            .max_sector_weight = 0.25,            // 25% in single sector
            .max_strategy_allocation = 0.40,      // 40% in single strategy
            
            .max_orders_per_second = 100,         // 100 orders/second
            .max_fills_per_minute = 1000,         // 1000 fills/minute
            
            .max_volatility_threshold = 0.05,     // 5% volatility threshold
            .max_spread_threshold = 0.01          // 1% spread threshold
        };
        
        // Load from AWS Parameter Store or DynamoDB if available
        loadRiskLimitsFromAWS();
    }
    
    void initializeCorrelationMatrix() {
        // Initialize with identity matrix (no correlation)
        correlation_matrix_ = Eigen::MatrixXd::Identity(65536, 65536);
        
        // Load historical correlations from S3 or DynamoDB
        loadCorrelationMatrixFromAWS();
    }
    
    // Fast rate limiting check
    __attribute__((hot)) bool checkRateLimit(const Order& order) {
        uint64_t current_time_s = rdtsc_to_ns(rdtsc()) / 1000000000ULL;
        uint32_t second_index = current_time_s % 60;
        
        // Atomic increment and check
        uint64_t current_count = ++rate_limiter_.order_counts_per_second[second_index];
        
        return current_count <= limits_.max_orders_per_second;
    }
    
    // Fast position limit check
    __attribute__((hot)) bool checkPositionLimits(const Order& order) {
        const Position& pos = positions_[order.symbol_id];
        
        // Calculate new position after this order
        int32_t quantity_change = (order.side == 1) ? order.quantity : -order.quantity;
        int32_t new_quantity = pos.quantity + quantity_change;
        
        // Check absolute position size
        double new_position_value = std::abs(new_quantity) * order.price_ticks * 0.01;  // Assuming ticks are cents
        if (new_position_value > limits_.max_position_value) {
            return false;
        }
        
        // Check order size
        if (order.quantity > limits_.max_order_quantity) {
            return false;
        }
        
        // Check gross exposure (approximate)
        double gross_change = order.quantity * order.price_ticks * 0.01;
        if (gross_exposure_.load() + gross_change > limits_.max_gross_exposure) {
            return false;
        }
        
        return true;
    }
    
    // Fast loss limit check
    __attribute__((hot)) bool checkLossLimits(const Order& order) {
        // Check daily P&L
        if (daily_pnl_.load() < -limits_.max_daily_loss) {
            return false;
        }
        
        // Check drawdown
        if (current_drawdown_.load() > limits_.max_drawdown) {
            return false;
        }
        
        return true;
    }
    
    // Concentration limit check
    __attribute__((hot)) bool checkConcentrationLimits(const Order& order) {
        // Single stock concentration check
        const Position& pos = positions_[order.symbol_id];
        double position_value = std::abs(pos.quantity) * pos.market_value;
        double total_portfolio_value = gross_exposure_.load();
        
        if (total_portfolio_value > 0) {
            double concentration = position_value / total_portfolio_value;
            if (concentration > limits_.max_single_stock_weight) {
                return false;
            }
        }
        
        return true;
    }
    
    // Market condition check
    __attribute__((hot)) bool checkMarketConditions(const Order& order) {
        // This would check current market volatility, spreads, etc.
        // For now, simplified implementation
        return true;
    }
    
    // VaR limit check (most expensive)
    bool checkVaRLimits(const Order& order) {
        // Only recalculate VaR if enough time has passed (e.g., every second)
        uint64_t current_time = rdtsc_to_ns(rdtsc());
        if (current_time - var_state_.last_var_update_ns > 1000000000ULL) {  // 1 second
            calculatePortfolioVaR();
            var_state_.last_var_update_ns = current_time;
        }
        
        // Check if current VaR breaches would exceed daily limit
        return var_state_.var_breaches_today < limits_.max_var_breach_count;
    }
    
    void calculatePortfolioVaR() {
        // Simplified parametric VaR calculation
        // In production, this would use more sophisticated models
        
        // Get position vector
        updatePositionVector();
        
        // Portfolio variance = w^T * Σ * w
        Eigen::VectorXd portfolio_variance = var_state_.position_vector.transpose() * 
                                           correlation_matrix_ * 
                                           var_state_.position_vector;
        
        // VaR (95% confidence) = 1.645 * sqrt(variance)
        var_state_.portfolio_var_95 = 1.645 * std::sqrt(portfolio_variance(0));
        
        // CVaR approximation
        var_state_.portfolio_cvar_95 = var_state_.portfolio_var_95 * 1.25;
    }
    
    void updatePositionVector() {
        // Update position vector for VaR calculation
        var_state_.position_vector.resize(65536);
        
        for (size_t i = 0; i < 65536; ++i) {
            var_state_.position_vector(i) = positions_[i].market_value;
        }
    }
    
    bool isNewPosition(const Order& order) {
        const Position& pos = positions_[order.symbol_id];
        int32_t quantity_change = (order.side == 1) ? order.quantity : -order.quantity;
        
        // Check if this order increases the absolute position size
        return std::abs(pos.quantity + quantity_change) > std::abs(pos.quantity);
    }
    
    bool isPositionClosing(const Order& order) {
        const Position& pos = positions_[order.symbol_id];
        int32_t quantity_change = (order.side == 1) ? order.quantity : -order.quantity;
        
        // Check if this order reduces the absolute position size
        return std::abs(pos.quantity + quantity_change) < std::abs(pos.quantity);
    }
    
    void updatePortfolioMetrics() {
        double gross = 0.0, net = 0.0;
        
        for (const auto& pos : positions_) {
            if (pos.quantity != 0) {
                gross += std::abs(pos.market_value);
                net += pos.market_value;
            }
        }
        
        gross_exposure_.store(gross);
        net_exposure_.store(net);
        
        // Update drawdown
        double current_portfolio_value = net;
        double hwm = high_water_mark_.load();
        
        if (current_portfolio_value > hwm) {
            high_water_mark_.store(current_portfolio_value);
            current_drawdown_.store(0.0);
        } else {
            double drawdown = (hwm - current_portfolio_value) / hwm;
            current_drawdown_.store(drawdown);
        }
    }
    
    void updateRiskMetrics(uint64_t start_time, bool passed) {
        uint64_t latency = rdtsc() - start_time;
        
        metrics_.risk_checks_performed++;
        if (passed) {
            metrics_.risk_checks_passed++;
        } else {
            metrics_.risk_checks_failed++;
        }
        
        // Update latency metrics
        uint64_t current_avg = metrics_.avg_check_latency_ns.load();
        uint64_t new_avg = (current_avg * 15 + latency) / 16;  // EMA
        metrics_.avg_check_latency_ns.store(new_avg);
        
        uint64_t current_max = metrics_.max_check_latency_ns.load();
        if (latency > current_max) {
            metrics_.max_check_latency_ns.store(latency);
        }
    }
    
    uint32_t countActivePositions() const {
        uint32_t count = 0;
        for (const auto& pos : positions_) {
            if (pos.quantity != 0) {
                count++;
            }
        }
        return count;
    }
    
    // AWS integration functions
    void sendCriticalAlert(const std::string& title, const std::string& message, int level) {
        Aws::SNS::Model::PublishRequest request;
        request.SetTopicArn(aws_config_.sns_alerts_topic);
        request.SetSubject(title);
        request.SetMessage(message + " (Level: " + std::to_string(level) + ")");
        
        sns_client_->PublishAsync(request, nullptr);
    }
    
    void persistPositionUpdate(uint32_t symbol_id, const Position& position) {
        // Async DynamoDB update (implementation would be here)
    }
    
    void persistKillSwitchEvent(KillSwitchLevel level, const std::string& reason) {
        // Log kill switch event to DynamoDB (implementation would be here)
    }
    
    void logKillSwitchEvent(KillSwitchLevel level, const std::string& reason) {
        // Send to CloudWatch Logs (implementation would be here)
    }
    
    void loadRiskLimitsFromAWS() {
        // Load risk limits from AWS Parameter Store or DynamoDB
    }
    
    void loadCorrelationMatrixFromAWS() {
        // Load correlation matrix from S3 or DynamoDB
    }
    
    void persistRiskState() {
        // Save risk state to DynamoDB for recovery
    }
    
    void setupPerformanceMonitoring() {
        // Setup CloudWatch custom metrics
    }
    
    __attribute__((always_inline)) inline uint64_t rdtsc() {
        uint32_t hi, lo;
        __asm__ __volatile__ ("rdtsc" : "=a"(lo), "=d"(hi));
        return ((uint64_t)hi << 32) | lo;
    }
    
    uint64_t rdtsc_to_ns(uint64_t tsc) {
        // Convert TSC to nanoseconds (CPU frequency dependent)
        return tsc / 3;  // Assuming 3GHz CPU
    }
};

} // namespace HFT