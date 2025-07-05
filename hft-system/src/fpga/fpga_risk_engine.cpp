#include "fpga_risk_engine.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <random>
#include <thread>

namespace hft::risk {

FPGARiskEngine::FPGARiskEngine(const RiskLimits& limits, const FPGAConfig& config)
    : limits_(limits), fpga_config_(config) {
    
    // Initialize position tracking
    positions_.resize(65536); // Support up to 65536 symbols
    
    // Initialize cache arrays
    std::fill(symbol_exposure_cache_.begin(), symbol_exposure_cache_.end(), 0);
    std::fill(symbol_var_cache_.begin(), symbol_var_cache_.end(), 0.0);
    std::fill(order_count_cache_.begin(), order_count_cache_.end(), 0);
}

FPGARiskEngine::~FPGARiskEngine() {
    shutdown();
}

bool FPGARiskEngine::initialize() {
    // Initialize FPGA if acceleration is enabled
#ifdef FPGA_ACCELERATION
    if (!initializeFPGA()) {
        std::cerr << "Failed to initialize FPGA acceleration" << std::endl;
        return false;
    }
#endif
    
    // Reset statistics
    resetStats();
    
    // Optimize memory layout for cache efficiency
    optimizeMemoryLayout();
    
    return true;
}

void FPGARiskEngine::shutdown() {
    // Stop monitoring if active
    if (monitoring_enabled_.load()) {
        stopRealTimeMonitoring();
    }
    
    // Cleanup FPGA resources
#ifdef FPGA_ACCELERATION
    cleanupFPGA();
#endif
}

FPGARiskEngine::RiskResult FPGARiskEngine::checkOrderRisk(uint32_t order_id, 
                                                         uint32_t symbol_id,
                                                         uint64_t price, 
                                                         uint64_t quantity, 
                                                         uint8_t side) {
    auto start_time = getCurrentTimestamp();
    
    RiskResult result = {};
    result.timestamp = start_time;
    result.order_id = order_id;
    result.symbol_id = symbol_id;
    result.price = price;
    result.quantity = quantity;
    result.risk_status = 0; // Default to pass
    result.violated_rules = 0;
    
    // Prefetch position data for better cache performance
    prefetchPositionData(symbol_id);
    
    // Run all risk checks
    uint8_t rule_violations = evaluateAllRiskRules(symbol_id, price, quantity, side, result);
    result.violated_rules = rule_violations;
    
    // Determine overall risk status
    if (rule_violations != 0) {
        result.risk_status = 1; // Fail
        stats_.failed_checks.fetch_add(1, std::memory_order_relaxed);
    } else {
        result.risk_status = 0; // Pass
        stats_.passed_checks.fetch_add(1, std::memory_order_relaxed);
    }
    
    // Calculate processing time
    auto end_time = getCurrentTimestamp();
    result.processing_time_ns = static_cast<uint16_t>(end_time - start_time);
    
    // Update statistics
    stats_.total_checks.fetch_add(1, std::memory_order_relaxed);
    stats_.total_processing_time_ns.fetch_add(result.processing_time_ns, std::memory_order_relaxed);
    
    // Update min/max processing times
    uint64_t current_min = stats_.min_processing_time_ns.load();
    while (result.processing_time_ns < current_min && 
           !stats_.min_processing_time_ns.compare_exchange_weak(current_min, result.processing_time_ns)) {
        current_min = stats_.min_processing_time_ns.load();
    }
    
    uint64_t current_max = stats_.max_processing_time_ns.load();
    while (result.processing_time_ns > current_max && 
           !stats_.max_processing_time_ns.compare_exchange_weak(current_max, result.processing_time_ns)) {
        current_max = stats_.max_processing_time_ns.load();
    }
    
    // Update exponential moving average
    double current_avg = stats_.avg_processing_time_ns.load();
    double new_avg = current_avg * 0.95 + result.processing_time_ns * 0.05;
    stats_.avg_processing_time_ns.store(new_avg);
    
    return result;
}

std::vector<FPGARiskEngine::RiskResult> FPGARiskEngine::checkBatchRisk(
    const std::vector<std::tuple<uint32_t, uint32_t, uint64_t, uint64_t, uint8_t>>& orders) {
    
    std::vector<RiskResult> results;
    results.reserve(orders.size());
    
#ifdef FPGA_ACCELERATION
    // Use FPGA for batch processing if available
    if (orders.size() > 10 && fpga_config_.enable_pipelining) {
        // Prepare order data for FPGA
        std::vector<uint8_t> order_data(orders.size() * 32); // 32 bytes per order
        for (size_t i = 0; i < orders.size(); ++i) {
            const auto& order = orders[i];
            uint32_t* data_ptr = reinterpret_cast<uint32_t*>(order_data.data() + i * 32);
            data_ptr[0] = std::get<0>(order); // order_id
            data_ptr[1] = std::get<1>(order); // symbol_id
            *reinterpret_cast<uint64_t*>(&data_ptr[2]) = std::get<2>(order); // price
            *reinterpret_cast<uint64_t*>(&data_ptr[4]) = std::get<3>(order); // quantity
            *reinterpret_cast<uint8_t*>(&data_ptr[6]) = std::get<4>(order); // side
        }
        
        // Execute FPGA kernel
        std::vector<uint8_t> result_data(orders.size() * sizeof(RiskResult));
        if (executeRiskCheckKernel(order_data.data(), orders.size(), 
                                  result_data.data(), result_data.size())) {
            // Convert results
            for (size_t i = 0; i < orders.size(); ++i) {
                const RiskResult* result_ptr = reinterpret_cast<const RiskResult*>(
                    result_data.data() + i * sizeof(RiskResult));
                results.push_back(*result_ptr);
            }
            return results;
        }
    }
#endif
    
    // Fallback to CPU processing
    for (const auto& order : orders) {
        results.push_back(checkOrderRisk(std::get<0>(order), std::get<1>(order),
                                        std::get<2>(order), std::get<3>(order),
                                        std::get<4>(order)));
    }
    
    return results;
}

bool FPGARiskEngine::checkPortfolioRisk(double& var_estimate, double& concentration_risk) {
    auto start_time = getCurrentTimestamp();
    
#ifdef FPGA_ACCELERATION
    // Use FPGA for portfolio risk calculation
    if (executePortfolioRiskKernel(positions_.data(), position_count_.load(),
                                  var_estimate, concentration_risk)) {
        return true;
    }
#endif
    
    // CPU fallback
    std::vector<double> exposures;
    std::vector<double> prices;
    std::vector<double> quantities;
    
    double total_portfolio_value = 0.0;
    uint32_t active_positions = position_count_.load();
    
    for (uint32_t i = 0; i < active_positions; ++i) {
        const Position& pos = positions_[i];
        if (pos.symbol_id != 0) {
            double long_value = pos.long_position * pos.avg_long_price / 1000000.0;
            double short_value = pos.short_position * pos.avg_short_price / 1000000.0;
            double net_exposure = long_value - short_value;
            
            exposures.push_back(std::abs(net_exposure));
            prices.push_back((pos.avg_long_price + pos.avg_short_price) / 2.0);
            quantities.push_back(std::abs(pos.net_position));
            
            total_portfolio_value += std::abs(net_exposure);
        }
    }
    
    if (exposures.empty()) {
        var_estimate = 0.0;
        concentration_risk = 0.0;
        return true;
    }
    
    // Calculate VaR using SIMD optimization
    calculateVaRSIMD(prices.data(), quantities.data(), exposures.size(), var_estimate);
    
    // Calculate concentration risk using SIMD
    std::vector<uint64_t> exposure_uint64(exposures.size());
    std::transform(exposures.begin(), exposures.end(), exposure_uint64.begin(),
                   [](double val) { return static_cast<uint64_t>(val * 1000000); });
    
    calculateConcentrationSIMD(exposure_uint64.data(), exposure_uint64.size(),
                               total_portfolio_value, concentration_risk);
    
    return true;
}

bool FPGARiskEngine::updatePosition(uint32_t symbol_id, int64_t quantity_delta, uint64_t price) {
    Position* pos = findPosition(symbol_id);
    if (!pos) {
        // Create new position
        uint32_t new_index = position_count_.fetch_add(1, std::memory_order_relaxed);
        if (new_index >= positions_.size()) {
            position_count_.fetch_sub(1, std::memory_order_relaxed);
            return false;
        }
        pos = &positions_[new_index];
        pos->symbol_id = symbol_id;
    }
    
    // Update position
    pos->last_update_time = getCurrentTimestamp();
    
    if (quantity_delta > 0) {
        // Long position
        uint64_t new_long = pos->long_position + quantity_delta;
        pos->avg_long_price = (pos->avg_long_price * pos->long_position + price * quantity_delta) / new_long;
        pos->long_position = new_long;
    } else if (quantity_delta < 0) {
        // Short position
        uint64_t short_delta = static_cast<uint64_t>(-quantity_delta);
        uint64_t new_short = pos->short_position + short_delta;
        pos->avg_short_price = (pos->avg_short_price * pos->short_position + price * short_delta) / new_short;
        pos->short_position = new_short;
    }
    
    // Update net position
    pos->net_position = static_cast<int64_t>(pos->long_position) - static_cast<int64_t>(pos->short_position);
    
    // Update unrealized PnL (simplified calculation)
    double long_value = pos->long_position * pos->avg_long_price / 1000000.0;
    double short_value = pos->short_position * pos->avg_short_price / 1000000.0;
    double current_value = (pos->long_position + pos->short_position) * price / 1000000.0;
    pos->unrealized_pnl = current_value - long_value + short_value;
    
    // Update cache
    updatePositionCache(symbol_id, *pos);
    
    return true;
}

__forceinline uint8_t FPGARiskEngine::evaluateAllRiskRules(uint32_t symbol_id, 
                                                          uint64_t price, 
                                                          uint64_t quantity, 
                                                          uint8_t side,
                                                          RiskResult& result) {
    uint8_t violations = 0;
    
    // Check position limits
    violations |= checkPositionLimits(symbol_id, price, quantity, side);
    
    // Check order value limits
    double order_value = calculateOrderValue(price, quantity);
    violations |= checkOrderValueLimits(static_cast<uint64_t>(order_value));
    
    // Check daily volume limits
    violations |= checkDailyVolumeLimits(symbol_id, quantity);
    
    // Check rate limits
    violations |= checkRateLimits(symbol_id);
    
    // Calculate exposure and VaR impact
    Position* pos = findPosition(symbol_id);
    if (pos) {
        double current_exposure = std::abs(pos->net_position) * price / 1000000.0;
        double new_exposure = current_exposure + order_value * (side == 0 ? 1 : -1);
        result.exposure_impact = new_exposure - current_exposure;
        
        // Simplified VaR calculation
        result.var_impact = result.exposure_impact * 0.02; // 2% daily volatility assumption
        
        // Margin requirement (simplified)
        result.margin_requirement = order_value * 0.1; // 10% margin requirement
    }
    
    return violations;
}

__forceinline uint8_t FPGARiskEngine::checkPositionLimits(uint32_t symbol_id, 
                                                         uint64_t price, 
                                                         uint64_t quantity, 
                                                         uint8_t side) {
    Position* pos = findPosition(symbol_id);
    if (!pos) {
        return 0; // No existing position, order is within limits
    }
    
    // Calculate new position value
    int64_t quantity_delta = (side == 0) ? static_cast<int64_t>(quantity) : -static_cast<int64_t>(quantity);
    int64_t new_position = pos->net_position + quantity_delta;
    uint64_t new_position_value = static_cast<uint64_t>(std::abs(new_position)) * price;
    
    if (new_position_value > limits_.max_position_value) {
        return POSITION_LIMIT_EXCEEDED;
    }
    
    return 0;
}

__forceinline uint8_t FPGARiskEngine::checkOrderValueLimits(uint64_t order_value) {
    if (order_value > limits_.max_order_value) {
        return ORDER_VALUE_EXCEEDED;
    }
    return 0;
}

__forceinline uint8_t FPGARiskEngine::checkDailyVolumeLimits(uint32_t symbol_id, uint64_t quantity) {
    uint32_t symbol_index = getSymbolIndex(symbol_id);
    
    // Simple daily volume tracking (would need proper time-based reset in production)
    uint64_t current_volume = symbol_exposure_cache_[symbol_index];
    if (current_volume + quantity > limits_.max_daily_volume) {
        return DAILY_VOLUME_EXCEEDED;
    }
    
    // Update cache
    symbol_exposure_cache_[symbol_index] = current_volume + quantity;
    
    return 0;
}

__forceinline uint8_t FPGARiskEngine::checkRateLimits(uint32_t symbol_id) {
    uint32_t symbol_index = getSymbolIndex(symbol_id);
    
    // Simple rate limiting (would need proper time-based tracking in production)
    uint32_t current_count = order_count_cache_[symbol_index];
    if (current_count >= limits_.max_orders_per_second) {
        return RATE_LIMIT_EXCEEDED;
    }
    
    // Update cache
    order_count_cache_[symbol_index] = current_count + 1;
    
    return 0;
}

void FPGARiskEngine::calculateVaRSIMD(const double* prices, const double* quantities, 
                                     size_t count, double& var_estimate) {
    if (count == 0) {
        var_estimate = 0.0;
        return;
    }
    
    // Simple VaR calculation using SIMD
    __m256d sum_squares = _mm256_setzero_pd();
    __m256d volatility = _mm256_set1_pd(0.02); // 2% daily volatility
    
    size_t simd_count = count / 4;
    for (size_t i = 0; i < simd_count; ++i) {
        __m256d price_vec = _mm256_load_pd(&prices[i * 4]);
        __m256d quantity_vec = _mm256_load_pd(&quantities[i * 4]);
        
        __m256d exposure = _mm256_mul_pd(price_vec, quantity_vec);
        __m256d variance = _mm256_mul_pd(exposure, volatility);
        __m256d squares = _mm256_mul_pd(variance, variance);
        
        sum_squares = _mm256_add_pd(sum_squares, squares);
    }
    
    // Sum the vector elements
    double sum_array[4];
    _mm256_store_pd(sum_array, sum_squares);
    double total_variance = sum_array[0] + sum_array[1] + sum_array[2] + sum_array[3];
    
    // Handle remaining elements
    for (size_t i = simd_count * 4; i < count; ++i) {
        double exposure = prices[i] * quantities[i];
        double variance = exposure * 0.02; // 2% volatility
        total_variance += variance * variance;
    }
    
    // VaR at 95% confidence level (approximately 1.65 * sqrt(variance))
    var_estimate = 1.65 * std::sqrt(total_variance);
}

void FPGARiskEngine::calculateConcentrationSIMD(const uint64_t* exposures, size_t count,
                                               double total_portfolio_value, double& max_concentration) {
    if (count == 0 || total_portfolio_value == 0.0) {
        max_concentration = 0.0;
        return;
    }
    
    __m256d max_vec = _mm256_setzero_pd();
    __m256d total_vec = _mm256_set1_pd(total_portfolio_value);
    
    size_t simd_count = count / 4;
    for (size_t i = 0; i < simd_count; ++i) {
        // Load 4 exposures and convert to double
        __m128i exposure_int = _mm_load_si128(reinterpret_cast<const __m128i*>(&exposures[i * 2]));
        __m256d exposure_vec = _mm256_cvtepi64_pd(exposure_int);
        
        __m256d concentration = _mm256_div_pd(exposure_vec, total_vec);
        max_vec = _mm256_max_pd(max_vec, concentration);
    }
    
    // Find maximum
    double max_array[4];
    _mm256_store_pd(max_array, max_vec);
    max_concentration = std::max({max_array[0], max_array[1], max_array[2], max_array[3]});
    
    // Handle remaining elements
    for (size_t i = simd_count * 4; i < count; ++i) {
        double concentration = static_cast<double>(exposures[i]) / total_portfolio_value;
        max_concentration = std::max(max_concentration, concentration);
    }
}

Position* FPGARiskEngine::findPosition(uint32_t symbol_id) {
    uint32_t active_positions = position_count_.load();
    for (uint32_t i = 0; i < active_positions; ++i) {
        if (positions_[i].symbol_id == symbol_id) {
            return &positions_[i];
        }
    }
    return nullptr;
}

void FPGARiskEngine::updatePositionCache(uint32_t symbol_id, const Position& position) {
    uint32_t symbol_index = getSymbolIndex(symbol_id);
    
    // Update exposure cache
    double exposure = std::abs(position.net_position) * 
                     (position.avg_long_price + position.avg_short_price) / 2.0;
    symbol_exposure_cache_[symbol_index] = static_cast<uint64_t>(exposure);
    
    // Update VaR cache (simplified)
    symbol_var_cache_[symbol_index] = exposure * 0.02; // 2% daily volatility
}

void FPGARiskEngine::prefetchPositionData(uint32_t symbol_id) const {
    Position* pos = const_cast<Position*>(findPosition(symbol_id));
    if (pos) {
        __builtin_prefetch(pos, 0, 3);
    }
    
    // Prefetch cache data
    uint32_t symbol_index = getSymbolIndex(symbol_id);
    __builtin_prefetch(&symbol_exposure_cache_[symbol_index], 0, 3);
    __builtin_prefetch(&symbol_var_cache_[symbol_index], 0, 3);
    __builtin_prefetch(&order_count_cache_[symbol_index], 0, 3);
}

void FPGARiskEngine::optimizeMemoryLayout() {
    // Optimize position array layout for better cache performance
    std::sort(positions_.begin(), positions_.begin() + position_count_.load(),
              [](const Position& a, const Position& b) {
                  return a.symbol_id < b.symbol_id;
              });
}

void FPGARiskEngine::resetStats() {
    stats_.total_checks.store(0);
    stats_.passed_checks.store(0);
    stats_.failed_checks.store(0);
    stats_.warnings.store(0);
    stats_.fpga_errors.store(0);
    stats_.timeout_errors.store(0);
    stats_.avg_processing_time_ns.store(0.0);
    stats_.min_processing_time_ns.store(UINT64_MAX);
    stats_.max_processing_time_ns.store(0);
    stats_.total_processing_time_ns.store(0);
}

double FPGARiskEngine::getAverageProcessingTimeNs() const {
    return stats_.avg_processing_time_ns.load();
}

#ifdef FPGA_ACCELERATION
bool FPGARiskEngine::initializeFPGA() {
    try {
        // Get available platforms
        std::vector<cl::Platform> platforms;
        cl::Platform::get(&platforms);
        
        // Find the specified platform
        for (const auto& platform : platforms) {
            if (platform.getInfo<CL_PLATFORM_NAME>().find(fpga_config_.platform_name) != std::string::npos) {
                fpga_platform_ = platform;
                break;
            }
        }
        
        // Get devices
        std::vector<cl::Device> devices;
        fpga_platform_.getDevices(CL_DEVICE_TYPE_ACCELERATOR, &devices);
        
        // Find the specified device
        for (const auto& device : devices) {
            if (device.getInfo<CL_DEVICE_NAME>().find(fpga_config_.device_name) != std::string::npos) {
                fpga_device_ = device;
                break;
            }
        }
        
        // Create context and command queue
        fpga_context_ = cl::Context(fpga_device_);
        fpga_queue_ = cl::CommandQueue(fpga_context_, fpga_device_, CL_QUEUE_PROFILING_ENABLE);
        
        // Load and build kernels
        return loadFPGAKernels() && setupFPGABuffers();
        
    } catch (const cl::Error& e) {
        std::cerr << "OpenCL error: " << e.what() << " (" << e.err() << ")" << std::endl;
        return false;
    }
}

bool FPGARiskEngine::loadFPGAKernels() {
    try {
        // Load kernel source from file
        std::ifstream kernel_file(fpga_config_.kernel_file);
        if (!kernel_file.is_open()) {
            return false;
        }
        
        std::string kernel_source((std::istreambuf_iterator<char>(kernel_file)),
                                 std::istreambuf_iterator<char>());
        
        // Create and build program
        fpga_program_ = cl::Program(fpga_context_, kernel_source);
        fpga_program_.build({fpga_device_});
        
        // Create kernels
        risk_check_kernel_ = cl::Kernel(fpga_program_, "risk_check_kernel");
        portfolio_risk_kernel_ = cl::Kernel(fpga_program_, "portfolio_risk_kernel");
        
        return true;
        
    } catch (const cl::Error& e) {
        std::cerr << "Kernel loading error: " << e.what() << " (" << e.err() << ")" << std::endl;
        return false;
    }
}

bool FPGARiskEngine::setupFPGABuffers() {
    try {
        // Create buffers
        size_t buffer_size = fpga_config_.buffer_size;
        
        order_buffer_ = cl::Buffer(fpga_context_, CL_MEM_READ_ONLY, buffer_size);
        position_buffer_ = cl::Buffer(fpga_context_, CL_MEM_READ_ONLY, 
                                     positions_.size() * sizeof(Position));
        result_buffer_ = cl::Buffer(fpga_context_, CL_MEM_WRITE_ONLY, buffer_size);
        limits_buffer_ = cl::Buffer(fpga_context_, CL_MEM_READ_ONLY, sizeof(RiskLimits));
        
        // Write limits to buffer
        fpga_queue_.enqueueWriteBuffer(limits_buffer_, CL_TRUE, 0, sizeof(RiskLimits), &limits_);
        
        return true;
        
    } catch (const cl::Error& e) {
        std::cerr << "Buffer setup error: " << e.what() << " (" << e.err() << ")" << std::endl;
        return false;
    }
}

bool FPGARiskEngine::executeRiskCheckKernel(const void* order_data, size_t order_count,
                                           void* result_data, size_t result_size) {
    try {
        // Write order data to buffer
        fpga_queue_.enqueueWriteBuffer(order_buffer_, CL_TRUE, 0, 
                                      order_count * 32, order_data);
        
        // Write position data to buffer
        fpga_queue_.enqueueWriteBuffer(position_buffer_, CL_TRUE, 0,
                                      position_count_.load() * sizeof(Position),
                                      positions_.data());
        
        // Set kernel arguments
        risk_check_kernel_.setArg(0, order_buffer_);
        risk_check_kernel_.setArg(1, position_buffer_);
        risk_check_kernel_.setArg(2, limits_buffer_);
        risk_check_kernel_.setArg(3, result_buffer_);
        risk_check_kernel_.setArg(4, static_cast<cl_uint>(order_count));
        
        // Execute kernel
        cl::NDRange global(order_count);
        fpga_queue_.enqueueNDRangeKernel(risk_check_kernel_, cl::NullRange, global);
        
        // Read results
        fpga_queue_.enqueueReadBuffer(result_buffer_, CL_TRUE, 0, result_size, result_data);
        
        return true;
        
    } catch (const cl::Error& e) {
        std::cerr << "Kernel execution error: " << e.what() << " (" << e.err() << ")" << std::endl;
        stats_.fpga_errors.fetch_add(1, std::memory_order_relaxed);
        return false;
    }
}

void FPGARiskEngine::cleanupFPGA() {
    // OpenCL objects are automatically cleaned up by destructors
}
#endif

} // namespace hft::risk