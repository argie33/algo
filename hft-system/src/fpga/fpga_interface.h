#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <vector>
#include <atomic>
#include <functional>

namespace hft::fpga {

/**
 * Low-level FPGA hardware interface for ultra-low latency operations
 * Provides direct hardware access and memory-mapped I/O
 */
class FPGAInterface {
public:
    // Hardware configuration
    struct HardwareConfig {
        std::string device_path;        // e.g., "/dev/xdma0_user"
        uint64_t base_address;          // Memory-mapped base address
        size_t memory_size;             // Size of mapped memory region
        uint32_t dma_channel_count;     // Number of DMA channels
        uint32_t clock_frequency_mhz;   // FPGA clock frequency
        bool enable_interrupts;         // Enable hardware interrupts
        bool enable_cache_coherency;    // Enable cache coherent DMA
        uint32_t pcie_lanes;           // PCIe lane count
        uint32_t pcie_generation;      // PCIe generation (3 or 4)
    };

    // DMA transfer descriptor
    struct DMATransfer {
        void* host_buffer;
        uint64_t fpga_address;
        size_t transfer_size;
        uint32_t channel_id;
        bool direction_to_fpga;  // true = host->FPGA, false = FPGA->host
        std::function<void(bool success)> completion_callback;
    };

    // Hardware register map
    enum class RegisterOffset : uint32_t {
        STATUS_REG = 0x00,
        CONTROL_REG = 0x04,
        INTERRUPT_REG = 0x08,
        TIMESTAMP_LOW = 0x0C,
        TIMESTAMP_HIGH = 0x10,
        DMA_CONTROL = 0x20,
        DMA_STATUS = 0x24,
        RISK_ENGINE_CONTROL = 0x100,
        RISK_ENGINE_STATUS = 0x104,
        ORDER_BUFFER_ADDR = 0x108,
        RESULT_BUFFER_ADDR = 0x10C,
        POSITION_BUFFER_ADDR = 0x110,
        PROCESSING_COUNT = 0x114,
        LATENCY_COUNTER = 0x118,
        ERROR_COUNT = 0x11C
    };

    // Hardware status flags
    enum StatusFlags : uint32_t {
        FPGA_READY = 0x01,
        DMA_ACTIVE = 0x02,
        RISK_ENGINE_BUSY = 0x04,
        INTERRUPT_PENDING = 0x08,
        ERROR_DETECTED = 0x10,
        TIMESTAMP_VALID = 0x20,
        CACHE_COHERENT = 0x40,
        THERMAL_WARNING = 0x80
    };

    // Performance counters
    struct PerformanceCounters {
        std::atomic<uint64_t> dma_transfers{0};
        std::atomic<uint64_t> dma_bytes{0};
        std::atomic<uint64_t> risk_checks{0};
        std::atomic<uint64_t> interrupts{0};
        std::atomic<uint64_t> errors{0};
        std::atomic<uint64_t> total_latency_ns{0};
        std::atomic<uint64_t> min_latency_ns{UINT64_MAX};
        std::atomic<uint64_t> max_latency_ns{0};
    };

private:
    HardwareConfig config_;
    PerformanceCounters counters_;
    
    // Hardware resources
    int device_fd_;
    void* mapped_memory_;
    volatile uint32_t* registers_;
    
    // DMA management
    std::vector<std::thread> dma_threads_;
    std::atomic<bool> dma_active_{false};
    
    // Interrupt handling
    std::thread interrupt_thread_;
    std::atomic<bool> interrupt_enabled_{false};
    std::function<void(uint32_t)> interrupt_handler_;

public:
    explicit FPGAInterface(const HardwareConfig& config);
    ~FPGAInterface();

    // Initialization and cleanup
    bool initialize();
    void shutdown();
    bool isInitialized() const;

    // Direct register access (inline for performance)
    __forceinline uint32_t readRegister(RegisterOffset offset) const {
        return registers_[static_cast<uint32_t>(offset) / 4];
    }

    __forceinline void writeRegister(RegisterOffset offset, uint32_t value) {
        registers_[static_cast<uint32_t>(offset) / 4] = value;
        __sync_synchronize(); // Memory barrier
    }

    __forceinline uint64_t readRegister64(RegisterOffset offset) const {
        uint32_t low = readRegister(offset);
        uint32_t high = readRegister(static_cast<RegisterOffset>(
            static_cast<uint32_t>(offset) + 4));
        return (static_cast<uint64_t>(high) << 32) | low;
    }

    __forceinline void writeRegister64(RegisterOffset offset, uint64_t value) {
        writeRegister(offset, static_cast<uint32_t>(value));
        writeRegister(static_cast<RegisterOffset>(
            static_cast<uint32_t>(offset) + 4), 
            static_cast<uint32_t>(value >> 32));
    }

    // Hardware timestamp (nanosecond precision)
    __forceinline uint64_t getHardwareTimestamp() const {
        return readRegister64(RegisterOffset::TIMESTAMP_LOW);
    }

    // Status checking
    bool isReady() const;
    bool isDMAActive() const;
    bool hasError() const;
    uint32_t getStatusFlags() const;

    // DMA operations
    bool submitDMATransfer(const DMATransfer& transfer);
    bool waitForDMACompletion(uint32_t channel_id, uint32_t timeout_ms = 1000);
    void cancelDMATransfer(uint32_t channel_id);

    // High-performance memory operations
    bool copyToFPGA(const void* src, uint64_t fpga_addr, size_t size, uint32_t channel_id = 0);
    bool copyFromFPGA(uint64_t fpga_addr, void* dst, size_t size, uint32_t channel_id = 0);
    
    // Zero-copy operations (using user-space DMA)
    void* allocateDMABuffer(size_t size, bool coherent = true);
    void freeDMABuffer(void* buffer, size_t size);
    uint64_t getDMAPhysicalAddress(void* buffer);

    // Risk engine specific operations
    bool startRiskEngine();
    bool stopRiskEngine();
    bool isRiskEngineReady() const;
    
    bool submitRiskCheckBatch(const void* orders, size_t order_count, 
                             void* results, size_t result_size);
    bool getRiskCheckResults(void* results, size_t result_size);

    // Interrupt handling
    void setInterruptHandler(std::function<void(uint32_t)> handler);
    void enableInterrupts();
    void disableInterrupts();

    // Performance monitoring
    const PerformanceCounters& getCounters() const { return counters_; }
    void resetCounters();
    double getAverageLatencyNs() const;

    // Hardware diagnostics
    bool runSelfTest();
    std::string getHardwareInfo() const;
    float getFPGATemperature() const;
    uint32_t getFPGAUtilization() const;

    // Power management
    void setPowerState(bool low_power);
    uint32_t getPowerConsumption() const; // milliwatts

private:
    // Low-level hardware operations
    bool openDevice();
    bool mapMemory();
    bool setupDMA();
    bool configureInterrupts();
    
    void unmapMemory();
    void closeDevice();

    // DMA management
    void dmaWorkerThread(uint32_t channel_id);
    bool executeDMATransfer(const DMATransfer& transfer);
    
    // Interrupt handling
    void interruptWorkerThread();
    void handleInterrupt(uint32_t interrupt_flags);

    // Hardware abstraction
    bool waitForStatus(uint32_t mask, uint32_t expected, uint32_t timeout_ms);
    void triggerSoftwareReset();
    
    // Performance optimization
    void optimizeCacheSettings();
    void configurePCIeSettings();
    
    // Error handling
    void handleHardwareError(uint32_t error_code);
    std::string decodeErrorCode(uint32_t error_code) const;
};

/**
 * FPGA memory manager for efficient buffer allocation
 * Manages pinned memory buffers for zero-copy DMA
 */
class FPGAMemoryManager {
private:
    struct MemoryRegion {
        void* virtual_address;
        uint64_t physical_address;
        size_t size;
        bool in_use;
        bool cache_coherent;
    };

    FPGAInterface* fpga_interface_;
    std::vector<MemoryRegion> memory_pool_;
    std::mutex pool_mutex_;
    
    // Pre-allocated buffers for common sizes
    static constexpr size_t SMALL_BUFFER_SIZE = 4096;    // 4KB
    static constexpr size_t MEDIUM_BUFFER_SIZE = 65536;  // 64KB
    static constexpr size_t LARGE_BUFFER_SIZE = 1048576; // 1MB
    
    std::vector<void*> small_buffers_;
    std::vector<void*> medium_buffers_;
    std::vector<void*> large_buffers_;

public:
    explicit FPGAMemoryManager(FPGAInterface* interface);
    ~FPGAMemoryManager();

    // Buffer allocation
    void* allocateBuffer(size_t size, bool cache_coherent = true);
    void freeBuffer(void* buffer);
    
    // Bulk allocation for performance
    std::vector<void*> allocateBuffers(size_t size, size_t count);
    void freeBuffers(const std::vector<void*>& buffers);
    
    // Pre-allocation for hot paths
    bool preallocateBuffers();
    void* getPreallocatedBuffer(size_t size);
    void returnPreallocatedBuffer(void* buffer, size_t size);
    
    // Memory info
    size_t getTotalAllocated() const;
    size_t getAvailableMemory() const;
    
private:
    void initializeMemoryPool();
    void cleanupMemoryPool();
    MemoryRegion* findFreeRegion(size_t size);
};

/**
 * Hardware-accelerated packet processor
 * Processes network packets directly on FPGA
 */
class FPGAPacketProcessor {
private:
    FPGAInterface* fpga_interface_;
    FPGAMemoryManager* memory_manager_;
    
    // Packet processing configuration
    struct PacketConfig {
        uint32_t max_packet_size;
        uint32_t packet_buffer_count;
        uint32_t processing_cores;
        bool enable_checksum_offload;
        bool enable_timestamp_insertion;
        bool enable_latency_measurement;
    } config_;
    
    // Packet ring buffers
    void* rx_ring_buffer_;
    void* tx_ring_buffer_;
    size_t ring_buffer_size_;
    
    std::atomic<uint32_t> rx_head_{0};
    std::atomic<uint32_t> rx_tail_{0};
    std::atomic<uint32_t> tx_head_{0};
    std::atomic<uint32_t> tx_tail_{0};

public:
    explicit FPGAPacketProcessor(FPGAInterface* interface, 
                                FPGAMemoryManager* memory_mgr,
                                const PacketConfig& config);
    ~FPGAPacketProcessor();

    bool initialize();
    void shutdown();

    // Packet processing
    bool submitPacketForProcessing(const void* packet_data, size_t size);
    bool getProcessedPacket(void* packet_data, size_t& size);
    
    // Bulk operations
    uint32_t submitPacketBatch(const void** packets, const size_t* sizes, uint32_t count);
    uint32_t getProcessedPacketBatch(void** packets, size_t* sizes, uint32_t max_count);
    
    // Statistics
    uint64_t getPacketsProcessed() const;
    uint64_t getAverageProcessingTime() const;

private:
    bool setupRingBuffers();
    void cleanupRingBuffers();
    
    bool isRxRingFull() const;
    bool isTxRingEmpty() const;
    
    void advanceRxHead();
    void advanceTxTail();
};

} // namespace hft::fpga