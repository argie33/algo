#pragma once

#include <cstdint>
#include <vector>
#include <string>
#include <memory>
#include <atomic>
#include <chrono>
#include <functional>
#include <unordered_map>
#include <fstream>

// Include core HFT components for testing
#include "../core/dpdk_network_engine.h"
#include "../data/high_performance_order_book.h"
#include "../fpga/fpga_risk_engine.h"
#include "../ml/alpha_engine.h"
#include "../utils/numa_memory_manager.h"

namespace hft::testing {

/**
 * Comprehensive latency benchmarking suite for HFT system components
 * Measures end-to-end latency from packet reception to order transmission
 * Target: <50μs tick-to-trade latency measurement accuracy
 */
class LatencyBenchmark {
public:
    // Benchmark configuration
    struct BenchmarkConfig {
        uint32_t num_iterations;
        uint32_t warmup_iterations;
        bool enable_detailed_profiling;
        bool enable_cpu_pinning;
        bool enable_real_time_priority;
        uint32_t cpu_core_id;
        std::string output_file;
        std::string test_data_file;
    };

    // Latency measurement point
    enum class MeasurementPoint : uint32_t {
        PACKET_ARRIVAL = 0,
        PACKET_PARSED = 1,
        ORDER_BOOK_UPDATED = 2,
        RISK_CHECK_COMPLETE = 3,
        ALPHA_SIGNAL_GENERATED = 4,
        ORDER_CREATED = 5,
        ORDER_TRANSMITTED = 6,
        TOTAL_POINTS = 7
    };

    // Single measurement sample
    struct alignas(64) LatencySample {
        uint64_t timestamps[static_cast<uint32_t>(MeasurementPoint::TOTAL_POINTS)];
        uint64_t iteration_id;
        uint32_t symbol_id;
        uint64_t price;
        uint64_t quantity;
        uint8_t side;
        bool risk_passed;
        double alpha_signal;
        char padding[16];
    };

    // Benchmark results
    struct BenchmarkResults {
        uint64_t total_samples;
        double mean_latency_ns;
        double median_latency_ns;
        double p95_latency_ns;
        double p99_latency_ns;
        double p99_9_latency_ns;
        double min_latency_ns;
        double max_latency_ns;
        double std_dev_ns;
        std::vector<double> component_latencies_ns;
        std::vector<std::string> component_names;
        double throughput_ops_per_sec;
        std::vector<LatencySample> detailed_samples;
    };

    // Per-component timing results
    struct ComponentTiming {
        std::string component_name;
        double mean_ns;
        double median_ns;
        double p95_ns;
        double p99_ns;
        double min_ns;
        double max_ns;
        double std_dev_ns;
        uint64_t sample_count;
    };

private:
    BenchmarkConfig config_;
    
    // HFT system components under test
    std::unique_ptr<networking::DPDKNetworkEngine> network_engine_;
    std::unique_ptr<data::HighPerformanceOrderBook> order_book_;
    std::unique_ptr<risk::FPGARiskEngine> risk_engine_;
    std::unique_ptr<ml::AlphaEngine> alpha_engine_;
    std::unique_ptr<memory::NUMAMemoryManager> memory_manager_;
    
    // Benchmark state
    std::vector<LatencySample> samples_;
    std::atomic<uint64_t> current_iteration_{0};
    std::atomic<bool> benchmark_active_{false};
    
    // Test data
    std::vector<networking::MarketDataPacket> test_packets_;
    
    // Hardware timestamp support
    uint64_t tsc_frequency_;
    bool use_hardware_timestamps_;
    
    // Profiling support
    std::unordered_map<std::string, std::vector<uint64_t>> detailed_timings_;

public:
    explicit LatencyBenchmark(const BenchmarkConfig& config);
    ~LatencyBenchmark();

    // Initialization and setup
    bool initialize();
    void shutdown();

    // Core benchmarking
    BenchmarkResults runEndToEndLatencyTest();
    BenchmarkResults runComponentLatencyTest(const std::string& component_name);
    BenchmarkResults runThroughputTest(uint32_t duration_seconds);
    
    // Specialized tests
    BenchmarkResults runOrderBookLatencyTest();
    BenchmarkResults runRiskEngineLatencyTest();
    BenchmarkResults runAlphaEngineLatencyTest();
    BenchmarkResults runNetworkLatencyTest();
    BenchmarkResults runMemoryLatencyTest();
    
    // Load testing
    BenchmarkResults runLoadTest(uint32_t target_ops_per_second, uint32_t duration_seconds);
    BenchmarkResults runStressTest(uint32_t max_ops_per_second);
    
    // Latency distribution analysis
    std::vector<double> analyzeLatencyDistribution(const std::vector<LatencySample>& samples);
    std::vector<ComponentTiming> analyzeComponentLatencies(const std::vector<LatencySample>& samples);
    
    // Performance regression testing
    bool runRegressionTest(const std::string& baseline_file);
    void saveBaseline(const std::string& baseline_file, const BenchmarkResults& results);
    
    // Real-time monitoring
    void startRealTimeMonitoring(uint32_t update_frequency_ms);
    void stopRealTimeMonitoring();
    
    // Test data management
    bool loadTestData(const std::string& filename);
    void generateSyntheticTestData(uint32_t num_packets);
    
    // Results export
    bool exportResults(const BenchmarkResults& results, const std::string& filename);
    bool exportDetailedProfile(const std::string& filename);
    std::string generateReport(const BenchmarkResults& results);

private:
    // Hardware setup and optimization
    bool setupHardwareOptimizations();
    bool pinToCore(uint32_t core_id);
    bool setRealTimePriority();
    void disableHyperThreading();
    void optimizeCPUGovernor();
    
    // Timing utilities
    __forceinline uint64_t getHighResolutionTimestamp() const {
        return __rdtsc();
    }
    
    __forceinline double timestampToNanoseconds(uint64_t timestamp) const {
        return static_cast<double>(timestamp) * 1000000000.0 / tsc_frequency_;
    }
    
    uint64_t calibrateTSCFrequency();
    
    // Test execution
    LatencySample runSingleIteration(const networking::MarketDataPacket& packet);
    void processTestPacket(const networking::MarketDataPacket& packet, LatencySample& sample);
    
    // Component testing
    uint64_t benchmarkOrderBookOperation(const networking::MarketDataPacket& packet);
    uint64_t benchmarkRiskCheck(uint32_t symbol_id, uint64_t price, uint64_t quantity, uint8_t side);
    uint64_t benchmarkAlphaGeneration(uint32_t symbol_id);
    uint64_t benchmarkMemoryAllocation(size_t size);
    
    // Statistical analysis
    double calculateMean(const std::vector<double>& values);
    double calculateMedian(std::vector<double> values);
    double calculatePercentile(std::vector<double> values, double percentile);
    double calculateStandardDeviation(const std::vector<double>& values, double mean);
    
    // Test validation
    bool validateTestEnvironment();
    bool checkSystemStability();
    void warmupSystem();
    
    // Monitoring and profiling
    void startDetailedProfiling();
    void stopDetailedProfiling();
    void recordComponentTiming(const std::string& component, uint64_t start_time, uint64_t end_time);
    
    // Utilities
    networking::MarketDataPacket createTestPacket(uint32_t symbol_id, uint64_t price, uint64_t quantity);
    void flushCaches();
    void synchronizeTimestamps();
};

/**
 * Hardware performance counter interface
 * Provides access to CPU performance monitoring units (PMU)
 */
class PerformanceCounters {
private:
    struct PMUEvent {
        std::string name;
        uint64_t config;
        int fd;
        uint64_t value;
        bool enabled;
    };
    
    std::vector<PMUEvent> events_;
    bool counters_enabled_;

public:
    PerformanceCounters();
    ~PerformanceCounters();
    
    // Counter management
    bool enableCounter(const std::string& event_name);
    bool disableCounter(const std::string& event_name);
    void enableAllCounters();
    void disableAllCounters();
    
    // Data collection
    bool startCounting();
    bool stopCounting();
    void resetCounters();
    
    // Results
    uint64_t getCounterValue(const std::string& event_name);
    std::unordered_map<std::string, uint64_t> getAllCounterValues();
    
    // Common performance metrics
    double getCacheHitRate();
    double getBranchPredictionAccuracy();
    uint64_t getInstructionsPerCycle();
    uint64_t getCacheMisses();
    uint64_t getTLBMisses();

private:
    bool openPMUEvent(PMUEvent& event);
    void closePMUEvent(PMUEvent& event);
    uint64_t readPMUEvent(const PMUEvent& event);
};

/**
 * System resource monitor for benchmarking
 * Monitors CPU, memory, and network utilization during tests
 */
class SystemResourceMonitor {
private:
    struct ResourceSnapshot {
        uint64_t timestamp;
        double cpu_usage_percent;
        double memory_usage_percent;
        uint64_t memory_available_mb;
        uint64_t network_rx_bytes;
        uint64_t network_tx_bytes;
        uint32_t context_switches;
        uint32_t interrupts;
        double cpu_frequency_mhz;
        double cpu_temperature_celsius;
    };
    
    std::vector<ResourceSnapshot> snapshots_;
    std::atomic<bool> monitoring_active_{false};
    std::thread monitor_thread_;
    uint32_t update_frequency_ms_;

public:
    explicit SystemResourceMonitor(uint32_t update_frequency_ms = 100);
    ~SystemResourceMonitor();
    
    // Monitoring control
    void startMonitoring();
    void stopMonitoring();
    bool isMonitoring() const;
    
    // Data access
    std::vector<ResourceSnapshot> getSnapshots() const;
    ResourceSnapshot getLatestSnapshot() const;
    void clearSnapshots();
    
    // Analysis
    double getAverageCPUUsage() const;
    double getPeakMemoryUsage() const;
    uint64_t getTotalNetworkTraffic() const;
    bool detectResourceBottlenecks() const;
    
    // Export
    bool exportToCSV(const std::string& filename) const;

private:
    void monitoringThread();
    ResourceSnapshot captureSnapshot();
    
    // System info collection
    double getCPUUsage();
    double getMemoryUsage();
    uint64_t getAvailableMemory();
    void getNetworkStats(uint64_t& rx_bytes, uint64_t& tx_bytes);
    uint32_t getContextSwitches();
    uint32_t getInterrupts();
    double getCPUFrequency();
    double getCPUTemperature();
};

/**
 * Jitter analysis toolkit
 * Analyzes timing jitter and variance in latency measurements
 */
class JitterAnalyzer {
private:
    std::vector<double> latency_samples_;
    
public:
    explicit JitterAnalyzer(const std::vector<double>& samples);
    
    // Jitter metrics
    double calculateRMSJitter();
    double calculatePeakToPeakJitter();
    double calculateJitterBandwidth();
    
    // Distribution analysis
    bool isNormalDistribution(double alpha = 0.05);
    std::vector<double> detectOutliers(double threshold = 3.0);
    
    // Frequency domain analysis
    std::vector<double> performFFT();
    std::vector<double> analyzePowerSpectralDensity();
    
    // Trend analysis
    bool detectLatencyTrend();
    double calculateTrendSlope();
    
    // Report generation
    std::string generateJitterReport();
    
private:
    double calculateMean();
    double calculateVariance();
    void sortSamples();
};

/**
 * Benchmark test suite orchestrator
 * Manages and coordinates multiple benchmark tests
 */
class BenchmarkSuite {
private:
    std::vector<std::unique_ptr<LatencyBenchmark>> benchmarks_;
    std::string suite_name_;
    std::string output_directory_;
    
public:
    explicit BenchmarkSuite(const std::string& suite_name,
                           const std::string& output_dir);
    ~BenchmarkSuite();
    
    // Test management
    void addBenchmark(std::unique_ptr<LatencyBenchmark> benchmark);
    bool runAllBenchmarks();
    bool runBenchmark(const std::string& benchmark_name);
    
    // Suite-level analysis
    std::string generateSuiteReport();
    bool exportSuiteResults(const std::string& filename);
    
    // Regression testing
    bool runRegressionSuite(const std::string& baseline_directory);
    bool compareSuiteResults(const std::string& current_results,
                            const std::string& baseline_results);

private:
    void setupOutputDirectory();
    std::string generateTimestamp();
};

} // namespace hft::testing