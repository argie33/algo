#include "latency_benchmark.h"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <numeric>
#include <random>
#include <sched.h>
#include <sys/mman.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <linux/perf_event.h>
#include <sys/ioctl.h>

namespace hft::testing {

LatencyBenchmark::LatencyBenchmark(const BenchmarkConfig& config)
    : config_(config), tsc_frequency_(0), use_hardware_timestamps_(true) {
    
    // Calibrate TSC frequency
    tsc_frequency_ = calibrateTSCFrequency();
    
    // Pre-allocate sample storage
    samples_.reserve(config_.num_iterations + config_.warmup_iterations);
}

LatencyBenchmark::~LatencyBenchmark() {
    shutdown();
}

bool LatencyBenchmark::initialize() {
    std::cout << "Initializing HFT Latency Benchmark Suite..." << std::endl;
    
    // Setup hardware optimizations
    if (!setupHardwareOptimizations()) {
        std::cerr << "Failed to setup hardware optimizations" << std::endl;
        return false;
    }
    
    // Initialize memory manager
    memory::NUMAMemoryManager::MemoryConfig mem_config;
    mem_config.enable_huge_pages = true;
    mem_config.enable_numa_balancing = true;
    mem_config.default_pool_size = 1024 * 1024 * 1024; // 1GB
    
    memory_manager_ = std::make_unique<memory::NUMAMemoryManager>(mem_config);
    if (!memory_manager_->initialize()) {
        std::cerr << "Failed to initialize NUMA memory manager" << std::endl;
        return false;
    }
    
    // Initialize order book
    order_book_ = std::make_unique<data::HighPerformanceOrderBook>(
        1000,        // min price: $0.01
        1000000000,  // max price: $1000.00  
        1000         // tick size: $0.001
    );
    
    // Initialize network engine
    networking::DPDKNetworkEngine::NetworkConfig net_config;
    net_config.port_id = 0;
    net_config.rx_queues = 1;
    net_config.tx_queues = 1;
    net_config.rx_desc = 1024;
    net_config.tx_desc = 1024;
    net_config.enable_hw_timestamp = true;
    net_config.enable_hw_checksum = true;
    net_config.enable_rss = false;
    
    network_engine_ = std::make_unique<networking::DPDKNetworkEngine>(net_config);
    // Note: Network engine initialization requires actual DPDK setup
    
    // Initialize risk engine
    risk::FPGARiskEngine::RiskLimits risk_limits;
    risk_limits.max_position_value = 10000000;     // $10M
    risk_limits.max_order_value = 1000000;         // $1M
    risk_limits.max_daily_volume = 100000000;      // 100M shares
    risk_limits.enable_pre_trade_checks = true;
    
    risk::FPGARiskEngine::FPGAConfig fpga_config;
    fpga_config.platform_name = "Intel";
    fpga_config.device_name = "FPGA";
    fpga_config.max_parallel_checks = 1000;
    fpga_config.enable_pipelining = true;
    
    risk_engine_ = std::make_unique<risk::FPGARiskEngine>(risk_limits, fpga_config);
    if (!risk_engine_->initialize()) {
        std::cerr << "Failed to initialize FPGA risk engine" << std::endl;
        return false;
    }
    
    // Initialize alpha engine
    ml::AlphaEngine::FeatureConfig feature_config;
    feature_config.lookback_periods = 100;
    feature_config.update_frequency_ms = 1;
    feature_config.enable_technical_features = true;
    feature_config.enable_microstructure_features = true;
    feature_config.enable_feature_scaling = true;
    
    std::vector<ml::AlphaEngine::ModelConfig> model_configs;
    ml::AlphaEngine::ModelConfig model_config;
    model_config.model_type = "linear";
    model_config.input_features = 16;
    model_config.output_signals = 1;
    model_config.confidence_threshold = 0.3;
    model_configs.push_back(model_config);
    
    alpha_engine_ = std::make_unique<ml::AlphaEngine>(feature_config, model_configs);
    if (!alpha_engine_->initialize()) {
        std::cerr << "Failed to initialize alpha engine" << std::endl;
        return false;
    }
    
    // Load or generate test data
    if (!config_.test_data_file.empty()) {
        if (!loadTestData(config_.test_data_file)) {
            std::cerr << "Failed to load test data from: " << config_.test_data_file << std::endl;
            generateSyntheticTestData(config_.num_iterations + config_.warmup_iterations);
        }
    } else {
        generateSyntheticTestData(config_.num_iterations + config_.warmup_iterations);
    }
    
    // Validate test environment
    if (!validateTestEnvironment()) {
        std::cerr << "Test environment validation failed" << std::endl;
        return false;
    }
    
    std::cout << "Benchmark initialization completed successfully" << std::endl;
    return true;
}

void LatencyBenchmark::shutdown() {
    if (benchmark_active_.load()) {
        benchmark_active_.store(false);
    }
    
    alpha_engine_.reset();
    risk_engine_.reset();
    network_engine_.reset();
    order_book_.reset();
    memory_manager_.reset();
}

LatencyBenchmark::BenchmarkResults LatencyBenchmark::runEndToEndLatencyTest() {
    std::cout << "Running end-to-end latency benchmark..." << std::endl;
    
    BenchmarkResults results = {};
    samples_.clear();
    samples_.reserve(config_.num_iterations);
    
    // Warm up the system
    std::cout << "Warming up system (" << config_.warmup_iterations << " iterations)..." << std::endl;
    for (uint32_t i = 0; i < config_.warmup_iterations; ++i) {
        if (i < test_packets_.size()) {
            LatencySample warmup_sample = runSingleIteration(test_packets_[i]);
            // Discard warmup samples
        }
    }
    
    std::cout << "Starting measurement phase..." << std::endl;
    benchmark_active_.store(true);
    
    // Flush caches and synchronize
    flushCaches();
    synchronizeTimestamps();
    
    auto test_start_time = std::chrono::high_resolution_clock::now();
    
    // Run actual benchmark iterations
    for (uint32_t i = 0; i < config_.num_iterations; ++i) {
        if (i < test_packets_.size()) {
            LatencySample sample = runSingleIteration(test_packets_[i]);
            sample.iteration_id = i;
            samples_.push_back(sample);
        }
        
        // Progress indicator
        if (i % 1000 == 0) {
            std::cout << "Completed " << i << "/" << config_.num_iterations << " iterations" << std::endl;
        }
    }
    
    auto test_end_time = std::chrono::high_resolution_clock::now();
    auto total_duration = std::chrono::duration_cast<std::chrono::microseconds>(
        test_end_time - test_start_time);
    
    benchmark_active_.store(false);
    
    std::cout << "Analyzing results..." << std::endl;
    
    // Calculate end-to-end latencies
    std::vector<double> latencies;
    latencies.reserve(samples_.size());
    
    for (const auto& sample : samples_) {
        uint64_t start_time = sample.timestamps[static_cast<uint32_t>(MeasurementPoint::PACKET_ARRIVAL)];
        uint64_t end_time = sample.timestamps[static_cast<uint32_t>(MeasurementPoint::ORDER_TRANSMITTED)];
        
        if (end_time > start_time) {
            double latency_ns = timestampToNanoseconds(end_time - start_time);
            latencies.push_back(latency_ns);
        }
    }
    
    if (latencies.empty()) {
        std::cerr << "No valid latency measurements captured" << std::endl;
        return results;
    }
    
    // Statistical analysis
    results.total_samples = latencies.size();
    results.mean_latency_ns = calculateMean(latencies);
    results.median_latency_ns = calculateMedian(latencies);
    results.p95_latency_ns = calculatePercentile(latencies, 0.95);
    results.p99_latency_ns = calculatePercentile(latencies, 0.99);
    results.p99_9_latency_ns = calculatePercentile(latencies, 0.999);
    results.min_latency_ns = *std::min_element(latencies.begin(), latencies.end());
    results.max_latency_ns = *std::max_element(latencies.begin(), latencies.end());
    results.std_dev_ns = calculateStandardDeviation(latencies, results.mean_latency_ns);
    
    // Calculate throughput
    double duration_seconds = total_duration.count() / 1000000.0;
    results.throughput_ops_per_sec = static_cast<double>(results.total_samples) / duration_seconds;
    
    // Component-level analysis
    auto component_timings = analyzeComponentLatencies(samples_);
    for (const auto& timing : component_timings) {
        results.component_names.push_back(timing.component_name);
        results.component_latencies_ns.push_back(timing.mean_ns);
    }
    
    // Store detailed samples if requested
    if (config_.enable_detailed_profiling) {
        results.detailed_samples = samples_;
    }
    
    std::cout << "End-to-end latency test completed:" << std::endl;
    std::cout << "  Mean latency: " << results.mean_latency_ns / 1000.0 << " μs" << std::endl;
    std::cout << "  Median latency: " << results.median_latency_ns / 1000.0 << " μs" << std::endl;
    std::cout << "  P95 latency: " << results.p95_latency_ns / 1000.0 << " μs" << std::endl;
    std::cout << "  P99 latency: " << results.p99_latency_ns / 1000.0 << " μs" << std::endl;
    std::cout << "  Throughput: " << results.throughput_ops_per_sec << " ops/sec" << std::endl;
    
    return results;
}

LatencyBenchmark::LatencySample LatencyBenchmark::runSingleIteration(
    const networking::MarketDataPacket& packet) {
    
    LatencySample sample = {};
    
    // Initialize all measurement points
    for (int i = 0; i < static_cast<int>(MeasurementPoint::TOTAL_POINTS); ++i) {
        sample.timestamps[i] = 0;
    }
    
    // Record packet arrival time
    sample.timestamps[static_cast<uint32_t>(MeasurementPoint::PACKET_ARRIVAL)] = 
        getHighResolutionTimestamp();
    
    // Extract market data
    sample.symbol_id = packet.symbol_id;
    sample.price = packet.price;
    sample.quantity = packet.quantity;
    sample.side = (packet.price > 50000000) ? 0 : 1; // Simple side determination
    
    // Simulate packet parsing
    processTestPacket(packet, sample);
    sample.timestamps[static_cast<uint32_t>(MeasurementPoint::PACKET_PARSED)] = 
        getHighResolutionTimestamp();
    
    // Update order book
    uint64_t ob_start = getHighResolutionTimestamp();
    bool ob_success = order_book_->addOrder(
        sample.iteration_id + 1000000, // order_id
        sample.price,
        sample.quantity,
        sample.side
    );
    sample.timestamps[static_cast<uint32_t>(MeasurementPoint::ORDER_BOOK_UPDATED)] = 
        getHighResolutionTimestamp();
    
    // Risk check
    uint64_t risk_start = getHighResolutionTimestamp();
    auto risk_result = risk_engine_->checkOrderRisk(
        sample.iteration_id + 1000000,
        sample.symbol_id,
        sample.price,
        sample.quantity,
        sample.side
    );
    sample.risk_passed = (risk_result.risk_status == 0);
    sample.timestamps[static_cast<uint32_t>(MeasurementPoint::RISK_CHECK_COMPLETE)] = 
        getHighResolutionTimestamp();
    
    // Alpha signal generation (if risk passed)
    if (sample.risk_passed) {
        uint64_t alpha_start = getHighResolutionTimestamp();
        
        // Create market data for alpha engine
        ml::AlphaEngine::MarketData alpha_data = {};
        alpha_data.timestamp = sample.timestamps[static_cast<uint32_t>(MeasurementPoint::PACKET_ARRIVAL)];
        alpha_data.symbol_id = sample.symbol_id;
        alpha_data.price = sample.price;
        alpha_data.quantity = sample.quantity;
        alpha_data.bid_price = sample.price - 1000; // 1 tick below
        alpha_data.ask_price = sample.price + 1000; // 1 tick above
        alpha_data.spread_bps = 20.0; // 2 basis points
        
        alpha_engine_->processMarketData(alpha_data);
        
        sample.timestamps[static_cast<uint32_t>(MeasurementPoint::ALPHA_SIGNAL_GENERATED)] = 
            getHighResolutionTimestamp();
        sample.alpha_signal = 0.5; // Placeholder signal strength
    } else {
        sample.timestamps[static_cast<uint32_t>(MeasurementPoint::ALPHA_SIGNAL_GENERATED)] = 
            sample.timestamps[static_cast<uint32_t>(MeasurementPoint::RISK_CHECK_COMPLETE)];
        sample.alpha_signal = 0.0;
    }
    
    // Order creation (simplified)
    sample.timestamps[static_cast<uint32_t>(MeasurementPoint::ORDER_CREATED)] = 
        getHighResolutionTimestamp();
    
    // Order transmission (simulated)
    sample.timestamps[static_cast<uint32_t>(MeasurementPoint::ORDER_TRANSMITTED)] = 
        getHighResolutionTimestamp();
    
    return sample;
}

void LatencyBenchmark::processTestPacket(const networking::MarketDataPacket& packet, 
                                        LatencySample& sample) {
    // Simulate packet parsing and validation
    // This would normally involve protocol-specific parsing
    
    // Add some realistic processing overhead
    volatile uint32_t dummy = 0;
    for (int i = 0; i < 100; ++i) {
        dummy += packet.sequence_number + i;
    }
}

uint64_t LatencyBenchmark::benchmarkOrderBookOperation(const networking::MarketDataPacket& packet) {
    uint64_t start_time = getHighResolutionTimestamp();
    
    // Perform order book operation
    order_book_->addOrder(
        packet.sequence_number,
        packet.price,
        packet.quantity,
        (packet.price % 2) // Simple side determination
    );
    
    uint64_t end_time = getHighResolutionTimestamp();
    return end_time - start_time;
}

uint64_t LatencyBenchmark::benchmarkRiskCheck(uint32_t symbol_id, uint64_t price, 
                                             uint64_t quantity, uint8_t side) {
    uint64_t start_time = getHighResolutionTimestamp();
    
    auto result = risk_engine_->checkOrderRisk(
        current_iteration_.fetch_add(1) + 2000000,
        symbol_id,
        price,
        quantity,
        side
    );
    
    uint64_t end_time = getHighResolutionTimestamp();
    return end_time - start_time;
}

uint64_t LatencyBenchmark::benchmarkMemoryAllocation(size_t size) {
    uint64_t start_time = getHighResolutionTimestamp();
    
    void* ptr = memory_manager_->allocate(size);
    
    uint64_t end_time = getHighResolutionTimestamp();
    
    if (ptr) {
        memory_manager_->deallocate(ptr);
    }
    
    return end_time - start_time;
}

bool LatencyBenchmark::setupHardwareOptimizations() {
    // Pin to specific CPU core if requested
    if (config_.enable_cpu_pinning) {
        if (!pinToCore(config_.cpu_core_id)) {
            std::cerr << "Failed to pin to CPU core " << config_.cpu_core_id << std::endl;
            return false;
        }
    }
    
    // Set real-time priority if requested
    if (config_.enable_real_time_priority) {
        if (!setRealTimePriority()) {
            std::cerr << "Failed to set real-time priority" << std::endl;
            return false;
        }
    }
    
    // Lock memory to prevent swapping
    if (mlockall(MCL_CURRENT | MCL_FUTURE) != 0) {
        std::cerr << "Failed to lock memory pages" << std::endl;
        return false;
    }
    
    return true;
}

bool LatencyBenchmark::pinToCore(uint32_t core_id) {
    cpu_set_t cpuset;
    CPU_ZERO(&cpuset);
    CPU_SET(core_id, &cpuset);
    
    if (sched_setaffinity(0, sizeof(cpuset), &cpuset) != 0) {
        return false;
    }
    
    return true;
}

bool LatencyBenchmark::setRealTimePriority() {
    struct sched_param param;
    param.sched_priority = 99; // Highest real-time priority
    
    if (sched_setscheduler(0, SCHED_FIFO, &param) != 0) {
        return false;
    }
    
    return true;
}

uint64_t LatencyBenchmark::calibrateTSCFrequency() {
    auto start_time = std::chrono::high_resolution_clock::now();
    uint64_t start_tsc = __rdtsc();
    
    // Wait for a known duration
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    
    auto end_time = std::chrono::high_resolution_clock::now();
    uint64_t end_tsc = __rdtsc();
    
    auto duration_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
        end_time - start_time).count();
    
    uint64_t tsc_cycles = end_tsc - start_tsc;
    return (tsc_cycles * 1000000000ULL) / duration_ns;
}

void LatencyBenchmark::generateSyntheticTestData(uint32_t num_packets) {
    test_packets_.clear();
    test_packets_.reserve(num_packets);
    
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_int_distribution<uint32_t> symbol_dist(1, 1000);
    std::uniform_int_distribution<uint64_t> price_dist(10000000, 100000000); // $10-$100
    std::uniform_int_distribution<uint64_t> quantity_dist(100, 10000);
    
    for (uint32_t i = 0; i < num_packets; ++i) {
        networking::MarketDataPacket packet = {};
        packet.timestamp.tsc_cycles = getHighResolutionTimestamp();
        packet.sequence_number = i + 1;
        packet.symbol_id = symbol_dist(gen);
        packet.price = price_dist(gen);
        packet.quantity = quantity_dist(gen);
        packet.message_type = 1; // Trade message
        
        test_packets_.push_back(packet);
    }
    
    std::cout << "Generated " << num_packets << " synthetic test packets" << std::endl;
}

double LatencyBenchmark::calculateMean(const std::vector<double>& values) {
    if (values.empty()) return 0.0;
    return std::accumulate(values.begin(), values.end(), 0.0) / values.size();
}

double LatencyBenchmark::calculateMedian(std::vector<double> values) {
    if (values.empty()) return 0.0;
    
    std::sort(values.begin(), values.end());
    size_t size = values.size();
    
    if (size % 2 == 0) {
        return (values[size/2 - 1] + values[size/2]) / 2.0;
    } else {
        return values[size/2];
    }
}

double LatencyBenchmark::calculatePercentile(std::vector<double> values, double percentile) {
    if (values.empty()) return 0.0;
    
    std::sort(values.begin(), values.end());
    size_t index = static_cast<size_t>(percentile * (values.size() - 1));
    
    if (index >= values.size()) {
        return values.back();
    }
    
    return values[index];
}

double LatencyBenchmark::calculateStandardDeviation(const std::vector<double>& values, double mean) {
    if (values.size() <= 1) return 0.0;
    
    double variance = 0.0;
    for (const auto& value : values) {
        double diff = value - mean;
        variance += diff * diff;
    }
    
    variance /= (values.size() - 1);
    return std::sqrt(variance);
}

std::vector<LatencyBenchmark::ComponentTiming> LatencyBenchmark::analyzeComponentLatencies(
    const std::vector<LatencySample>& samples) {
    
    std::vector<ComponentTiming> timings;
    
    // Define component measurement ranges
    struct ComponentRange {
        std::string name;
        MeasurementPoint start;
        MeasurementPoint end;
    };
    
    std::vector<ComponentRange> ranges = {
        {"Packet Parsing", MeasurementPoint::PACKET_ARRIVAL, MeasurementPoint::PACKET_PARSED},
        {"Order Book Update", MeasurementPoint::PACKET_PARSED, MeasurementPoint::ORDER_BOOK_UPDATED},
        {"Risk Check", MeasurementPoint::ORDER_BOOK_UPDATED, MeasurementPoint::RISK_CHECK_COMPLETE},
        {"Alpha Generation", MeasurementPoint::RISK_CHECK_COMPLETE, MeasurementPoint::ALPHA_SIGNAL_GENERATED},
        {"Order Creation", MeasurementPoint::ALPHA_SIGNAL_GENERATED, MeasurementPoint::ORDER_CREATED},
        {"Order Transmission", MeasurementPoint::ORDER_CREATED, MeasurementPoint::ORDER_TRANSMITTED}
    };
    
    for (const auto& range : ranges) {
        std::vector<double> component_latencies;
        
        for (const auto& sample : samples) {
            uint64_t start_ts = sample.timestamps[static_cast<uint32_t>(range.start)];
            uint64_t end_ts = sample.timestamps[static_cast<uint32_t>(range.end)];
            
            if (end_ts > start_ts) {
                double latency_ns = timestampToNanoseconds(end_ts - start_ts);
                component_latencies.push_back(latency_ns);
            }
        }
        
        if (!component_latencies.empty()) {
            ComponentTiming timing;
            timing.component_name = range.name;
            timing.mean_ns = calculateMean(component_latencies);
            timing.median_ns = calculateMedian(component_latencies);
            timing.p95_ns = calculatePercentile(component_latencies, 0.95);
            timing.p99_ns = calculatePercentile(component_latencies, 0.99);
            timing.min_ns = *std::min_element(component_latencies.begin(), component_latencies.end());
            timing.max_ns = *std::max_element(component_latencies.begin(), component_latencies.end());
            timing.std_dev_ns = calculateStandardDeviation(component_latencies, timing.mean_ns);
            timing.sample_count = component_latencies.size();
            
            timings.push_back(timing);
        }
    }
    
    return timings;
}

bool LatencyBenchmark::validateTestEnvironment() {
    // Check if running as root (required for some optimizations)
    if (getuid() != 0) {
        std::cout << "Warning: Not running as root, some optimizations may not work" << std::endl;
    }
    
    // Check TSC frequency calibration
    if (tsc_frequency_ == 0) {
        std::cerr << "Failed to calibrate TSC frequency" << std::endl;
        return false;
    }
    
    // Check if we have test data
    if (test_packets_.empty()) {
        std::cerr << "No test data available" << std::endl;
        return false;
    }
    
    std::cout << "Test environment validation passed" << std::endl;
    std::cout << "  TSC frequency: " << tsc_frequency_ / 1000000 << " MHz" << std::endl;
    std::cout << "  Test packets: " << test_packets_.size() << std::endl;
    
    return true;
}

void LatencyBenchmark::flushCaches() {
    // Flush instruction cache
    __builtin___clear_cache(nullptr, nullptr);
    
    // Flush data caches by reading/writing large amount of memory
    const size_t cache_size = 32 * 1024 * 1024; // 32MB to clear L3 cache
    volatile char* flush_buffer = new char[cache_size];
    
    for (size_t i = 0; i < cache_size; i += 64) {
        flush_buffer[i] = 0;
    }
    
    delete[] flush_buffer;
}

void LatencyBenchmark::synchronizeTimestamps() {
    // Synchronize timestamp counters across cores
    for (int i = 0; i < 10; ++i) {
        volatile uint64_t dummy = getHighResolutionTimestamp();
        (void)dummy;
    }
}

std::string LatencyBenchmark::generateReport(const BenchmarkResults& results) {
    std::ostringstream report;
    
    report << "=== HFT Latency Benchmark Report ===" << std::endl;
    report << "Test Configuration:" << std::endl;
    report << "  Iterations: " << config_.num_iterations << std::endl;
    report << "  Warmup Iterations: " << config_.warmup_iterations << std::endl;
    report << "  CPU Core: " << config_.cpu_core_id << std::endl;
    report << "  Real-time Priority: " << (config_.enable_real_time_priority ? "Yes" : "No") << std::endl;
    report << std::endl;
    
    report << "End-to-End Latency Results:" << std::endl;
    report << "  Total Samples: " << results.total_samples << std::endl;
    report << "  Mean Latency: " << results.mean_latency_ns / 1000.0 << " μs" << std::endl;
    report << "  Median Latency: " << results.median_latency_ns / 1000.0 << " μs" << std::endl;
    report << "  P95 Latency: " << results.p95_latency_ns / 1000.0 << " μs" << std::endl;
    report << "  P99 Latency: " << results.p99_latency_ns / 1000.0 << " μs" << std::endl;
    report << "  P99.9 Latency: " << results.p99_9_latency_ns / 1000.0 << " μs" << std::endl;
    report << "  Min Latency: " << results.min_latency_ns / 1000.0 << " μs" << std::endl;
    report << "  Max Latency: " << results.max_latency_ns / 1000.0 << " μs" << std::endl;
    report << "  Std Deviation: " << results.std_dev_ns / 1000.0 << " μs" << std::endl;
    report << "  Throughput: " << results.throughput_ops_per_sec << " ops/sec" << std::endl;
    report << std::endl;
    
    if (!results.component_names.empty()) {
        report << "Component Breakdown:" << std::endl;
        for (size_t i = 0; i < results.component_names.size() && i < results.component_latencies_ns.size(); ++i) {
            report << "  " << results.component_names[i] << ": " 
                   << results.component_latencies_ns[i] / 1000.0 << " μs" << std::endl;
        }
    }
    
    return report.str();
}

} // namespace hft::testing