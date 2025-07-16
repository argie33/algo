#pragma once

#include <cstdint>
#include <atomic>
#include <memory>
#include <vector>
#include <array>
#include <string>
#include <functional>
#include <immintrin.h>

// OpenCL headers for FPGA acceleration
#ifdef FPGA_ACCELERATION
#include <CL/opencl.h>
#include <CL/cl.hpp>
#endif

namespace hft::risk {

/**
 * Ultra-low latency FPGA-accelerated risk engine for HFT
 * Target: <50ns for basic risk checks, <200ns for complex portfolio risk
 * Features: Hardware acceleration, parallel processing, real-time monitoring
 */
class FPGARiskEngine {
public:
    // Risk check result structure
    struct alignas(64) RiskResult {
        uint64_t timestamp;          // Hardware timestamp
        uint32_t order_id;
        uint32_t symbol_id;
        uint64_t price;
        uint64_t quantity;
        uint8_t risk_status;         // 0=Pass, 1=Fail, 2=Warning
        uint8_t violated_rules;      // Bitmask of violated rules
        uint16_t processing_time_ns; // Actual processing time
        double exposure_impact;      // Delta exposure
        double var_impact;           // VaR impact
        double margin_requirement;   // Additional margin needed
        char padding[20];            // Cache line alignment
    };

    // Position tracking structure
    struct alignas(64) Position {
        uint32_t symbol_id;
        int64_t net_position;        // Signed position
        uint64_t long_position;
        uint64_t short_position;
        uint64_t avg_long_price;
        uint64_t avg_short_price;
        double unrealized_pnl;
        double realized_pnl;
        uint64_t last_update_time;
        char padding[24];
    };

    // Risk limits configuration
    struct RiskLimits {
        uint64_t max_position_value;     // Maximum position value per symbol
        uint64_t max_order_value;        // Maximum single order value
        uint64_t max_daily_volume;       // Maximum daily trading volume
        uint64_t max_portfolio_value;    // Maximum total portfolio value
        double max_var_percentage;       // Maximum VaR as % of capital
        double max_concentration;        // Maximum concentration per symbol
        uint32_t max_orders_per_second;  // Rate limiting
        uint32_t max_cancel_ratio;       // Maximum cancel/fill ratio
        bool enable_pre_trade_checks;    // Enable pre-trade risk checks
        bool enable_post_trade_checks;   // Enable post-trade risk checks
        bool enable_real_time_monitoring; // Enable continuous monitoring
    };

    // FPGA configuration
    struct FPGAConfig {
        std::string platform_name;
        std::string device_name;
        std::string kernel_file;
        uint32_t compute_units;
        uint32_t max_parallel_checks;
        bool enable_pipelining;
        bool enable_host_memory_optimization;
        size_t buffer_size;
        uint32_t timeout_ms;
    };

    // Performance statistics
    struct alignas(64) RiskStats {
        std::atomic<uint64_t> total_checks{0};
        std::atomic<uint64_t> passed_checks{0};
        std::atomic<uint64_t> failed_checks{0};
        std::atomic<uint64_t> warnings{0};
        std::atomic<uint64_t> fpga_errors{0};
        std::atomic<uint64_t> timeout_errors{0};
        std::atomic<double> avg_processing_time_ns{0.0};
        std::atomic<uint64_t> min_processing_time_ns{UINT64_MAX};
        std::atomic<uint64_t> max_processing_time_ns{0};
        std::atomic<uint64_t> total_processing_time_ns{0};
    };

private:
    RiskLimits limits_;
    FPGAConfig fpga_config_;
    RiskStats stats_;
    
    // Position tracking
    std::vector<Position> positions_;
    std::atomic<uint32_t> position_count_{0};
    
    // FPGA resources
#ifdef FPGA_ACCELERATION
    cl::Platform fpga_platform_;
    cl::Device fpga_device_;
    cl::Context fpga_context_;
    cl::CommandQueue fpga_queue_;
    cl::Program fpga_program_;
    cl::Kernel risk_check_kernel_;
    cl::Kernel portfolio_risk_kernel_;
    
    // OpenCL buffers
    cl::Buffer order_buffer_;
    cl::Buffer position_buffer_;
    cl::Buffer result_buffer_;
    cl::Buffer limits_buffer_;
#endif
    
    // Cache-aligned arrays for performance
    alignas(64) std::array<uint64_t, 65536> symbol_exposure_cache_;
    alignas(64) std::array<double, 65536> symbol_var_cache_;
    alignas(64) std::array<uint32_t, 65536> order_count_cache_;
    
    // Performance monitoring
    std::atomic<bool> monitoring_enabled_{false};
    std::atomic<uint64_t> last_check_time_{0};
    
    // Risk rule violation tracking
    enum RiskRuleFlags : uint8_t {
        POSITION_LIMIT_EXCEEDED = 0x01,
        ORDER_VALUE_EXCEEDED = 0x02,
        DAILY_VOLUME_EXCEEDED = 0x04,
        PORTFOLIO_VAR_EXCEEDED = 0x08,
        CONCENTRATION_EXCEEDED = 0x10,
        RATE_LIMIT_EXCEEDED = 0x20,
        CANCEL_RATIO_EXCEEDED = 0x40,
        MARGIN_INSUFFICIENT = 0x80
    };

public:
    explicit FPGARiskEngine(const RiskLimits& limits, const FPGAConfig& config);
    ~FPGARiskEngine();

    // Initialization and cleanup
    bool initialize();
    void shutdown();

    // Core risk check functions (target: <50ns)
    RiskResult checkOrderRisk(uint32_t order_id, uint32_t symbol_id, 
                             uint64_t price, uint64_t quantity, uint8_t side);
    
    // Batch risk checking for efficiency
    std::vector<RiskResult> checkBatchRisk(const std::vector<std::tuple<uint32_t, uint32_t, uint64_t, uint64_t, uint8_t>>& orders);
    
    // Portfolio-level risk assessment
    bool checkPortfolioRisk(double& var_estimate, double& concentration_risk);
    
    // Position management
    bool updatePosition(uint32_t symbol_id, int64_t quantity_delta, uint64_t price);
    Position getPosition(uint32_t symbol_id) const;
    std::vector<Position> getAllPositions() const;
    
    // Real-time monitoring
    void startRealTimeMonitoring();
    void stopRealTimeMonitoring();
    bool isRealTimeMonitoringActive() const;
    
    // Risk limit management
    void updateRiskLimits(const RiskLimits& new_limits);
    const RiskLimits& getRiskLimits() const { return limits_; }
    
    // Performance and diagnostics
    const RiskStats& getStats() const { return stats_; }
    void resetStats();
    double getAverageProcessingTimeNs() const;
    
    // FPGA health monitoring
    bool isFPGAHealthy() const;
    std::string getFPGAStatus() const;
    void resetFPGA();
    
    // Compliance and audit
    void enableAuditTrail(bool enable);
    std::vector<RiskResult> getAuditTrail(uint64_t start_time, uint64_t end_time) const;

private:
    // FPGA initialization and management
    bool initializeFPGA();
    bool loadFPGAKernels();
    bool setupFPGABuffers();
    void cleanupFPGA();
    
    // Risk calculation kernels
    __forceinline uint8_t checkPositionLimits(uint32_t symbol_id, uint64_t price, uint64_t quantity, uint8_t side);
    __forceinline uint8_t checkOrderValueLimits(uint64_t order_value);
    __forceinline uint8_t checkDailyVolumeLimits(uint32_t symbol_id, uint64_t quantity);
    __forceinline uint8_t checkPortfolioLimits(double new_var, double new_concentration);
    __forceinline uint8_t checkRateLimits(uint32_t symbol_id);
    
    // SIMD-optimized risk calculations
    void calculateVaRSIMD(const double* prices, const double* quantities, 
                         size_t count, double& var_estimate);
    void calculateConcentrationSIMD(const uint64_t* exposures, size_t count, 
                                   double total_portfolio_value, double& max_concentration);
    
    // Hardware-accelerated functions
#ifdef FPGA_ACCELERATION
    bool executeRiskCheckKernel(const void* order_data, size_t order_count, 
                               void* result_data, size_t result_size);
    bool executePortfolioRiskKernel(const void* position_data, size_t position_count,
                                   double& var_result, double& concentration_result);
#endif
    
    // Position tracking helpers
    Position* findPosition(uint32_t symbol_id);
    void updatePositionCache(uint32_t symbol_id, const Position& position);
    
    // Performance optimization
    void prefetchPositionData(uint32_t symbol_id) const;
    void optimizeMemoryLayout();
    
    // Risk rule evaluation
    uint8_t evaluateAllRiskRules(uint32_t symbol_id, uint64_t price, 
                                uint64_t quantity, uint8_t side, RiskResult& result);
    
    // Monitoring and alerting
    void monitoringThread();
    void sendRiskAlert(const RiskResult& result);
    
    // Utility functions
    __forceinline uint64_t getCurrentTimestamp() const {
        return __rdtsc();
    }
    
    __forceinline double calculateOrderValue(uint64_t price, uint64_t quantity) const {
        return static_cast<double>(price) * quantity / 1000000.0; // Assuming 6 decimal places
    }
    
    __forceinline uint32_t getSymbolIndex(uint32_t symbol_id) const {
        return symbol_id % 65536; // Hash to array index
    }
};

/**
 * Hardware-accelerated VaR calculation engine
 * Uses FPGA for Monte Carlo simulations and risk factor modeling
 */
class FPGAVaREngine {
private:
    static constexpr size_t MAX_SYMBOLS = 10000;
    static constexpr size_t MAX_SCENARIOS = 100000;
    
    // Risk factor structure
    struct alignas(64) RiskFactor {
        uint32_t factor_id;
        double current_value;
        double volatility;
        double correlation_matrix[32]; // Up to 32 correlated factors
        uint64_t last_update_time;
        char padding[24];
    };
    
    // Monte Carlo simulation parameters
    struct MCSimulationConfig {
        uint32_t num_scenarios;
        uint32_t time_horizon_days;
        double confidence_level;
        uint32_t random_seed;
        bool enable_correlation;
        bool enable_fat_tails;
        bool enable_regime_switching;
    };
    
    std::vector<RiskFactor> risk_factors_;
    MCSimulationConfig mc_config_;
    
#ifdef FPGA_ACCELERATION
    cl::Kernel monte_carlo_kernel_;
    cl::Buffer risk_factor_buffer_;
    cl::Buffer scenario_buffer_;
    cl::Buffer correlation_buffer_;
#endif

public:
    explicit FPGAVaREngine(const MCSimulationConfig& config);
    ~FPGAVaREngine() = default;
    
    // VaR calculation functions
    double calculatePortfolioVaR(const std::vector<Position>& positions, 
                                double confidence_level = 0.95);
    double calculateIncrementalVaR(const Position& new_position, 
                                  const std::vector<Position>& existing_positions);
    
    // Risk factor management
    void updateRiskFactor(uint32_t factor_id, double new_value, double volatility);
    void updateCorrelationMatrix(const std::vector<std::vector<double>>& correlation_matrix);
    
    // Monte Carlo simulation
    std::vector<double> runMonteCarloSimulation(const std::vector<Position>& positions);
    
private:
    bool initializeVaRKernels();
    void generateRandomScenarios(double* scenarios, size_t count);
    void applyCorrelations(double* scenarios, size_t scenario_count, size_t factor_count);
};

/**
 * Real-time risk monitoring system
 * Continuously monitors positions and market conditions
 */
class RealTimeRiskMonitor {
private:
    FPGARiskEngine* risk_engine_;
    std::atomic<bool> monitoring_active_{false};
    std::vector<std::thread> monitor_threads_;
    
    // Alert thresholds
    struct AlertThresholds {
        double portfolio_var_threshold;
        double concentration_threshold;
        double drawdown_threshold;
        uint64_t processing_time_threshold_ns;
        uint32_t failed_checks_threshold;
    } alert_thresholds_;
    
    // Alert callback
    std::function<void(const std::string&, const RiskResult&)> alert_callback_;

public:
    explicit RealTimeRiskMonitor(FPGARiskEngine* engine, 
                               const AlertThresholds& thresholds);
    ~RealTimeRiskMonitor();
    
    void startMonitoring();
    void stopMonitoring();
    
    void setAlertCallback(std::function<void(const std::string&, const RiskResult&)> callback);
    
private:
    void monitorPositions();
    void monitorPerformance();
    void checkAlertConditions();
};

} // namespace hft::risk