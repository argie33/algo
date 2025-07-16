#include "fpga_interface.h"
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include <poll.h>
#include <errno.h>
#include <cstring>
#include <iostream>
#include <fstream>
#include <thread>
#include <chrono>

namespace hft::fpga {

FPGAInterface::FPGAInterface(const HardwareConfig& config)
    : config_(config), device_fd_(-1), mapped_memory_(nullptr), registers_(nullptr) {
}

FPGAInterface::~FPGAInterface() {
    shutdown();
}

bool FPGAInterface::initialize() {
    // Open FPGA device
    if (!openDevice()) {
        std::cerr << "Failed to open FPGA device: " << config_.device_path << std::endl;
        return false;
    }

    // Map memory regions
    if (!mapMemory()) {
        std::cerr << "Failed to map FPGA memory" << std::endl;
        closeDevice();
        return false;
    }

    // Setup DMA channels
    if (!setupDMA()) {
        std::cerr << "Failed to setup DMA channels" << std::endl;
        unmapMemory();
        closeDevice();
        return false;
    }

    // Configure interrupts if enabled
    if (config_.enable_interrupts && !configureInterrupts()) {
        std::cerr << "Failed to configure interrupts" << std::endl;
        unmapMemory();
        closeDevice();
        return false;
    }

    // Perform initial configuration
    optimizeCacheSettings();
    configurePCIeSettings();

    // Reset performance counters
    resetCounters();

    // Run self-test
    if (!runSelfTest()) {
        std::cerr << "FPGA self-test failed" << std::endl;
        shutdown();
        return false;
    }

    return true;
}

void FPGAInterface::shutdown() {
    // Stop all operations
    if (interrupt_enabled_.load()) {
        disableInterrupts();
    }

    if (dma_active_.load()) {
        dma_active_.store(false);
        for (auto& thread : dma_threads_) {
            if (thread.joinable()) {
                thread.join();
            }
        }
        dma_threads_.clear();
    }

    // Cleanup resources
    unmapMemory();
    closeDevice();
}

bool FPGAInterface::isInitialized() const {
    return device_fd_ >= 0 && mapped_memory_ != nullptr && registers_ != nullptr;
}

bool FPGAInterface::isReady() const {
    return (getStatusFlags() & StatusFlags::FPGA_READY) != 0;
}

bool FPGAInterface::isDMAActive() const {
    return (getStatusFlags() & StatusFlags::DMA_ACTIVE) != 0;
}

bool FPGAInterface::hasError() const {
    return (getStatusFlags() & StatusFlags::ERROR_DETECTED) != 0;
}

uint32_t FPGAInterface::getStatusFlags() const {
    if (!isInitialized()) {
        return 0;
    }
    return readRegister(RegisterOffset::STATUS_REG);
}

bool FPGAInterface::submitDMATransfer(const DMATransfer& transfer) {
    if (!isInitialized() || transfer.channel_id >= config_.dma_channel_count) {
        return false;
    }

    // Configure DMA transfer
    uint32_t control_reg = 0;
    control_reg |= (transfer.channel_id & 0xFF);
    control_reg |= (transfer.direction_to_fpga ? 0x100 : 0x000);
    control_reg |= (transfer.transfer_size & 0xFFFF) << 16;

    // Set buffer addresses
    writeRegister64(RegisterOffset::DMA_CONTROL, 
                   reinterpret_cast<uint64_t>(transfer.host_buffer));
    writeRegister64(static_cast<RegisterOffset>(
        static_cast<uint32_t>(RegisterOffset::DMA_CONTROL) + 8), 
        transfer.fpga_address);

    // Start transfer
    writeRegister(RegisterOffset::DMA_CONTROL, control_reg | 0x80000000);

    counters_.dma_transfers.fetch_add(1, std::memory_order_relaxed);
    counters_.dma_bytes.fetch_add(transfer.transfer_size, std::memory_order_relaxed);

    return true;
}

bool FPGAInterface::waitForDMACompletion(uint32_t channel_id, uint32_t timeout_ms) {
    auto start_time = std::chrono::steady_clock::now();
    
    while (true) {
        uint32_t status = readRegister(RegisterOffset::DMA_STATUS);
        uint32_t channel_status = (status >> (channel_id * 4)) & 0xF;
        
        if (channel_status & 0x1) {
            // Transfer completed
            return true;
        }
        
        if (channel_status & 0x2) {
            // Transfer failed
            counters_.errors.fetch_add(1, std::memory_order_relaxed);
            return false;
        }
        
        // Check timeout
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - start_time);
        if (elapsed.count() >= timeout_ms) {
            return false;
        }
        
        // Small delay to prevent busy waiting
        std::this_thread::sleep_for(std::chrono::microseconds(10));
    }
}

bool FPGAInterface::copyToFPGA(const void* src, uint64_t fpga_addr, size_t size, uint32_t channel_id) {
    if (!isInitialized()) {
        return false;
    }

    auto start_time = std::chrono::high_resolution_clock::now();

    DMATransfer transfer;
    transfer.host_buffer = const_cast<void*>(src);
    transfer.fpga_address = fpga_addr;
    transfer.transfer_size = size;
    transfer.channel_id = channel_id;
    transfer.direction_to_fpga = true;

    if (!submitDMATransfer(transfer)) {
        return false;
    }

    bool success = waitForDMACompletion(channel_id, 1000);
    
    // Update latency statistics
    auto end_time = std::chrono::high_resolution_clock::now();
    auto latency_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
        end_time - start_time).count();
    
    counters_.total_latency_ns.fetch_add(latency_ns, std::memory_order_relaxed);
    
    uint64_t current_min = counters_.min_latency_ns.load();
    while (latency_ns < current_min && 
           !counters_.min_latency_ns.compare_exchange_weak(current_min, latency_ns)) {
        current_min = counters_.min_latency_ns.load();
    }
    
    uint64_t current_max = counters_.max_latency_ns.load();
    while (latency_ns > current_max && 
           !counters_.max_latency_ns.compare_exchange_weak(current_max, latency_ns)) {
        current_max = counters_.max_latency_ns.load();
    }

    return success;
}

bool FPGAInterface::copyFromFPGA(uint64_t fpga_addr, void* dst, size_t size, uint32_t channel_id) {
    if (!isInitialized()) {
        return false;
    }

    DMATransfer transfer;
    transfer.host_buffer = dst;
    transfer.fpga_address = fpga_addr;
    transfer.transfer_size = size;
    transfer.channel_id = channel_id;
    transfer.direction_to_fpga = false;

    if (!submitDMATransfer(transfer)) {
        return false;
    }

    return waitForDMACompletion(channel_id, 1000);
}

void* FPGAInterface::allocateDMABuffer(size_t size, bool coherent) {
    if (!isInitialized()) {
        return nullptr;
    }

    // Allocate memory aligned to page boundaries
    size_t aligned_size = (size + 4095) & ~4095;
    
    void* buffer = nullptr;
    if (coherent && config_.enable_cache_coherency) {
        // Allocate cache-coherent DMA buffer
        buffer = mmap(nullptr, aligned_size, PROT_READ | PROT_WRITE,
                     MAP_SHARED | MAP_LOCKED, device_fd_, 0);
    } else {
        // Allocate regular DMA buffer
        buffer = mmap(nullptr, aligned_size, PROT_READ | PROT_WRITE,
                     MAP_PRIVATE | MAP_ANONYMOUS | MAP_LOCKED, -1, 0);
    }

    if (buffer == MAP_FAILED) {
        return nullptr;
    }

    // Lock pages in memory to prevent swapping
    if (mlock(buffer, aligned_size) != 0) {
        munmap(buffer, aligned_size);
        return nullptr;
    }

    return buffer;
}

void FPGAInterface::freeDMABuffer(void* buffer, size_t size) {
    if (buffer != nullptr) {
        size_t aligned_size = (size + 4095) & ~4095;
        munlock(buffer, aligned_size);
        munmap(buffer, aligned_size);
    }
}

bool FPGAInterface::startRiskEngine() {
    if (!isInitialized()) {
        return false;
    }

    // Configure risk engine
    uint32_t control = 0x00000001; // Enable risk engine
    writeRegister(RegisterOffset::RISK_ENGINE_CONTROL, control);

    // Wait for ready status
    return waitForStatus(StatusFlags::FPGA_READY, StatusFlags::FPGA_READY, 1000);
}

bool FPGAInterface::stopRiskEngine() {
    if (!isInitialized()) {
        return false;
    }

    writeRegister(RegisterOffset::RISK_ENGINE_CONTROL, 0);
    return true;
}

bool FPGAInterface::isRiskEngineReady() const {
    if (!isInitialized()) {
        return false;
    }

    uint32_t status = readRegister(RegisterOffset::RISK_ENGINE_STATUS);
    return (status & 0x1) != 0;
}

bool FPGAInterface::submitRiskCheckBatch(const void* orders, size_t order_count,
                                        void* results, size_t result_size) {
    if (!isInitialized() || !isRiskEngineReady()) {
        return false;
    }

    auto start_time = getHardwareTimestamp();

    // Copy order data to FPGA
    if (!copyToFPGA(orders, 0x10000, order_count * 32, 0)) {
        return false;
    }

    // Set processing parameters
    writeRegister(RegisterOffset::PROCESSING_COUNT, order_count);

    // Start processing
    uint32_t control = readRegister(RegisterOffset::RISK_ENGINE_CONTROL);
    writeRegister(RegisterOffset::RISK_ENGINE_CONTROL, control | 0x2);

    // Wait for completion
    if (!waitForStatus(0x4, 0x4, 1000)) { // Wait for processing complete flag
        return false;
    }

    // Copy results back
    bool success = copyFromFPGA(0x20000, results, result_size, 1);

    counters_.risk_checks.fetch_add(order_count, std::memory_order_relaxed);

    // Update latency counter
    auto end_time = getHardwareTimestamp();
    auto latency = end_time - start_time;
    writeRegister64(RegisterOffset::LATENCY_COUNTER, latency);

    return success;
}

bool FPGAInterface::getRiskCheckResults(void* results, size_t result_size) {
    if (!isInitialized()) {
        return false;
    }

    return copyFromFPGA(0x20000, results, result_size, 1);
}

void FPGAInterface::setInterruptHandler(std::function<void(uint32_t)> handler) {
    interrupt_handler_ = handler;
}

void FPGAInterface::enableInterrupts() {
    if (!config_.enable_interrupts) {
        return;
    }

    interrupt_enabled_.store(true);
    interrupt_thread_ = std::thread(&FPGAInterface::interruptWorkerThread, this);

    // Enable interrupts in hardware
    writeRegister(RegisterOffset::CONTROL_REG, 0x80000000);
}

void FPGAInterface::disableInterrupts() {
    interrupt_enabled_.store(false);
    
    if (interrupt_thread_.joinable()) {
        interrupt_thread_.join();
    }

    // Disable interrupts in hardware
    uint32_t control = readRegister(RegisterOffset::CONTROL_REG);
    writeRegister(RegisterOffset::CONTROL_REG, control & ~0x80000000);
}

void FPGAInterface::resetCounters() {
    counters_.dma_transfers.store(0);
    counters_.dma_bytes.store(0);
    counters_.risk_checks.store(0);
    counters_.interrupts.store(0);
    counters_.errors.store(0);
    counters_.total_latency_ns.store(0);
    counters_.min_latency_ns.store(UINT64_MAX);
    counters_.max_latency_ns.store(0);
}

double FPGAInterface::getAverageLatencyNs() const {
    uint64_t total_operations = counters_.dma_transfers.load() + counters_.risk_checks.load();
    if (total_operations == 0) {
        return 0.0;
    }
    return static_cast<double>(counters_.total_latency_ns.load()) / total_operations;
}

bool FPGAInterface::runSelfTest() {
    if (!isInitialized()) {
        return false;
    }

    // Test register access
    writeRegister(RegisterOffset::CONTROL_REG, 0x12345678);
    if (readRegister(RegisterOffset::CONTROL_REG) != 0x12345678) {
        return false;
    }

    // Test timestamp functionality
    uint64_t ts1 = getHardwareTimestamp();
    std::this_thread::sleep_for(std::chrono::microseconds(100));
    uint64_t ts2 = getHardwareTimestamp();
    
    if (ts2 <= ts1) {
        return false; // Timestamp not advancing
    }

    // Test DMA with small buffer
    constexpr size_t test_size = 1024;
    void* test_buffer = allocateDMABuffer(test_size, true);
    if (!test_buffer) {
        return false;
    }

    // Fill with test pattern
    uint32_t* data = static_cast<uint32_t*>(test_buffer);
    for (size_t i = 0; i < test_size / 4; ++i) {
        data[i] = static_cast<uint32_t>(i ^ 0xDEADBEEF);
    }

    // Test round-trip DMA
    bool dma_test = copyToFPGA(test_buffer, 0x1000, test_size, 0) &&
                   copyFromFPGA(0x1000, test_buffer, test_size, 0);

    freeDMABuffer(test_buffer, test_size);

    return dma_test;
}

std::string FPGAInterface::getHardwareInfo() const {
    if (!isInitialized()) {
        return "FPGA not initialized";
    }

    std::ostringstream info;
    info << "FPGA Hardware Information:\n";
    info << "  Device: " << config_.device_path << "\n";
    info << "  Clock Frequency: " << config_.clock_frequency_mhz << " MHz\n";
    info << "  PCIe: Gen" << config_.pcie_generation << " x" << config_.pcie_lanes << "\n";
    info << "  Memory Size: " << (config_.memory_size / 1024 / 1024) << " MB\n";
    info << "  DMA Channels: " << config_.dma_channel_count << "\n";
    info << "  Status: " << std::hex << getStatusFlags() << std::dec;

    return info.str();
}

bool FPGAInterface::openDevice() {
    device_fd_ = open(config_.device_path.c_str(), O_RDWR | O_SYNC);
    return device_fd_ >= 0;
}

bool FPGAInterface::mapMemory() {
    mapped_memory_ = mmap(nullptr, config_.memory_size, 
                         PROT_READ | PROT_WRITE, MAP_SHARED, 
                         device_fd_, config_.base_address);
    
    if (mapped_memory_ == MAP_FAILED) {
        mapped_memory_ = nullptr;
        return false;
    }

    registers_ = static_cast<volatile uint32_t*>(mapped_memory_);
    return true;
}

bool FPGAInterface::setupDMA() {
    dma_active_.store(true);
    
    // Create worker threads for each DMA channel
    for (uint32_t i = 0; i < config_.dma_channel_count; ++i) {
        dma_threads_.emplace_back(&FPGAInterface::dmaWorkerThread, this, i);
    }

    return true;
}

bool FPGAInterface::configureInterrupts() {
    if (!config_.enable_interrupts) {
        return true;
    }

    // Configure interrupt settings in hardware
    // This would be device-specific implementation
    return true;
}

void FPGAInterface::unmapMemory() {
    if (mapped_memory_ != nullptr) {
        munmap(mapped_memory_, config_.memory_size);
        mapped_memory_ = nullptr;
        registers_ = nullptr;
    }
}

void FPGAInterface::closeDevice() {
    if (device_fd_ >= 0) {
        close(device_fd_);
        device_fd_ = -1;
    }
}

void FPGAInterface::dmaWorkerThread(uint32_t channel_id) {
    // Set thread name and priority
    char thread_name[16];
    snprintf(thread_name, sizeof(thread_name), "fpga_dma_%u", channel_id);
    pthread_setname_np(pthread_self(), thread_name);

    // Set real-time priority
    struct sched_param param;
    param.sched_priority = 90;
    pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);

    while (dma_active_.load(std::memory_order_relaxed)) {
        // DMA worker implementation would go here
        // This would handle queued DMA transfers for the specific channel
        
        std::this_thread::sleep_for(std::chrono::microseconds(100));
    }
}

void FPGAInterface::interruptWorkerThread() {
    // Set thread name and priority
    pthread_setname_np(pthread_self(), "fpga_irq");
    
    struct sched_param param;
    param.sched_priority = 95;
    pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);

    struct pollfd pfd;
    pfd.fd = device_fd_;
    pfd.events = POLLIN;

    while (interrupt_enabled_.load(std::memory_order_relaxed)) {
        int ret = poll(&pfd, 1, 100); // 100ms timeout
        
        if (ret > 0 && (pfd.revents & POLLIN)) {
            uint32_t interrupt_flags = readRegister(RegisterOffset::INTERRUPT_REG);
            
            if (interrupt_flags != 0) {
                handleInterrupt(interrupt_flags);
                
                // Clear interrupt
                writeRegister(RegisterOffset::INTERRUPT_REG, interrupt_flags);
                
                counters_.interrupts.fetch_add(1, std::memory_order_relaxed);
            }
        }
    }
}

void FPGAInterface::handleInterrupt(uint32_t interrupt_flags) {
    if (interrupt_handler_) {
        interrupt_handler_(interrupt_flags);
    }
}

bool FPGAInterface::waitForStatus(uint32_t mask, uint32_t expected, uint32_t timeout_ms) {
    auto start_time = std::chrono::steady_clock::now();
    
    while (true) {
        uint32_t status = getStatusFlags();
        if ((status & mask) == expected) {
            return true;
        }
        
        auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - start_time);
        if (elapsed.count() >= timeout_ms) {
            return false;
        }
        
        std::this_thread::sleep_for(std::chrono::microseconds(10));
    }
}

void FPGAInterface::optimizeCacheSettings() {
    // Platform-specific cache optimization
    // This would configure cache coherency settings for optimal performance
}

void FPGAInterface::configurePCIeSettings() {
    // Configure PCIe settings for maximum bandwidth and minimum latency
    // This would involve setting up DMA burst sizes, read/write preferences, etc.
}

} // namespace hft::fpga