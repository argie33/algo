#pragma once

#include <numa.h>
#include <numaif.h>
#include <sys/mman.h>
#include <unistd.h>
#include <atomic>
#include <memory>
#include <vector>
#include <unordered_map>
#include <thread>
#include <mutex>
#include <immintrin.h>

namespace hft::memory {

/**
 * NUMA-aware memory manager optimized for ultra-low latency HFT operations
 * Features:
 * - CPU-local memory allocation
 * - Huge pages support (2MB/1GB)
 * - Lock-free memory pools
 * - Cache-aligned allocations
 * - Memory prefetching
 * - Zero-copy operations
 */
class NUMAMemoryManager {
public:
    // Memory allocation policies
    enum class AllocationPolicy {
        LOCAL_ONLY,      // Allocate only on local NUMA node
        PREFERRED,       // Prefer local but allow fallback
        INTERLEAVED,     // Distribute across all nodes
        SPECIFIC_NODE    // Allocate on specific node
    };

    // Huge page sizes
    enum class HugePageSize {
        STANDARD_4KB = 4096,
        LARGE_2MB = 2 * 1024 * 1024,
        HUGE_1GB = 1024 * 1024 * 1024
    };

    // Memory region descriptor
    struct alignas(64) MemoryRegion {
        void* base_address;
        size_t size;
        int numa_node;
        HugePageSize page_size;
        AllocationPolicy policy;
        std::atomic<size_t> allocated_bytes{0};
        std::atomic<size_t> free_bytes{0};
        uint64_t allocation_timestamp;
        char padding[16]; // Pad to cache line
    };

    // Per-CPU memory pool for lock-free allocation
    struct alignas(64) CPUMemoryPool {
        void* pool_base;
        size_t pool_size;
        std::atomic<size_t> current_offset{0};
        int cpu_id;
        int numa_node;
        
        // Fast allocation bitmap for small objects
        std::atomic<uint64_t> allocation_bitmap[1024]; // 64KB bitmap
        
        // Statistics
        std::atomic<uint64_t> allocations{0};
        std::atomic<uint64_t> deallocations{0};
        std::atomic<uint64_t> bytes_allocated{0};
        
        char padding[8]; // Pad to cache line
    };

    // Memory allocation statistics
    struct alignas(64) MemoryStats {
        std::atomic<uint64_t> total_allocated{0};
        std::atomic<uint64_t> total_freed{0};
        std::atomic<uint64_t> peak_usage{0};
        std::atomic<uint64_t> allocation_count{0};
        std::atomic<uint64_t> deallocation_count{0};
        std::atomic<uint64_t> huge_page_allocations{0};
        std::atomic<uint64_t> numa_local_allocations{0};
        std::atomic<uint64_t> numa_remote_allocations{0};
        std::atomic<double> avg_allocation_time_ns{0.0};
    };

    // Configuration for memory manager
    struct MemoryConfig {
        bool enable_huge_pages = true;
        bool enable_numa_balancing = true;
        bool enable_memory_prefetching = true;
        bool enable_zero_copy = true;
        size_t default_pool_size = 1024 * 1024 * 1024; // 1GB per CPU
        size_t max_allocation_size = 64 * 1024 * 1024;  // 64MB
        AllocationPolicy default_policy = AllocationPolicy::LOCAL_ONLY;
        HugePageSize default_page_size = HugePageSize::LARGE_2MB;
        uint32_t prefetch_distance = 64; // Cache lines to prefetch
    };

private:
    MemoryConfig config_;
    std::vector<CPUMemoryPool> cpu_pools_;
    std::vector<MemoryRegion> memory_regions_;
    MemoryStats stats_;
    
    // NUMA topology information
    int num_numa_nodes_;
    int num_cpus_;
    std::vector<std::vector<int>> numa_to_cpus_;
    std::vector<int> cpu_to_numa_;
    
    // Huge page management
    std::unordered_map<HugePageSize, size_t> huge_page_counts_;
    std::mutex huge_page_mutex_;
    
    // Memory alignment requirements
    static constexpr size_t CACHE_LINE_SIZE = 64;
    static constexpr size_t PAGE_SIZE = 4096;
    static constexpr size_t MEMORY_ALIGNMENT = 64;

public:
    explicit NUMAMemoryManager(const MemoryConfig& config = MemoryConfig{});
    ~NUMAMemoryManager();

    // Initialization and cleanup
    bool initialize();
    void shutdown();

    // Core allocation functions (target: <100ns for small allocations)
    void* allocate(size_t size, AllocationPolicy policy = AllocationPolicy::LOCAL_ONLY);
    void* allocateAligned(size_t size, size_t alignment, 
                         AllocationPolicy policy = AllocationPolicy::LOCAL_ONLY);
    void* allocateHugePage(size_t size, HugePageSize page_size,
                          AllocationPolicy policy = AllocationPolicy::LOCAL_ONLY);
    
    // High-performance deallocation
    void deallocate(void* ptr);
    void deallocateAligned(void* ptr, size_t size);
    
    // Specialized allocation for common HFT data structures
    template<typename T>
    T* allocateObject(AllocationPolicy policy = AllocationPolicy::LOCAL_ONLY);
    
    template<typename T>
    T* allocateArray(size_t count, AllocationPolicy policy = AllocationPolicy::LOCAL_ONLY);
    
    // Memory pool management
    bool createCPUPool(int cpu_id, size_t pool_size);
    void* allocateFromPool(int cpu_id, size_t size);
    
    // NUMA-aware operations
    void* allocateOnNode(int numa_node, size_t size);
    bool migrateToNode(void* ptr, size_t size, int target_node);
    int getCurrentNUMANode() const;
    int getCPUNUMANode(int cpu_id) const;
    
    // Memory optimization
    void prefetchMemory(const void* addr, size_t size) const;
    void prefetchForWrite(void* addr, size_t size) const;
    bool lockMemoryResident(void* addr, size_t size);
    bool unlockMemory(void* addr, size_t size);
    
    // Cache optimization
    void flushCacheLine(const void* addr) const;
    void prefetchCacheLine(const void* addr, int hint = 3) const;
    void* alignToPageBoundary(void* ptr) const;
    
    // Memory introspection
    size_t getActualSize(void* ptr) const;
    int getMemoryNUMANode(void* ptr) const;
    bool isHugePage(void* ptr) const;
    
    // Statistics and monitoring
    const MemoryStats& getStats() const { return stats_; }
    void resetStats();
    double getFragmentationRatio() const;
    size_t getTotalAllocatedMemory() const;
    
    // NUMA topology queries
    int getNumNUMANodes() const { return num_numa_nodes_; }
    int getNumCPUs() const { return num_cpus_; }
    const std::vector<int>& getCPUsForNode(int numa_node) const;
    
    // Performance tuning
    void optimizeForCPU(int cpu_id);
    void setMemoryPolicy(AllocationPolicy policy);
    bool enableHugePages(HugePageSize size);
    
private:
    // Internal allocation helpers
    void* allocateInternal(size_t size, int numa_node, HugePageSize page_size);
    void* allocateFromBitmap(CPUMemoryPool& pool, size_t size);
    bool markBitmapAllocated(CPUMemoryPool& pool, size_t offset, size_t size);
    
    // NUMA topology discovery
    bool discoverNUMATopology();
    void bindMemoryToNode(void* addr, size_t size, int node);
    
    // Huge page management
    bool setupHugePages();
    void* allocateHugePageInternal(size_t size, HugePageSize page_size, int numa_node);
    void deallocateHugePage(void* ptr, size_t size);
    
    // Memory region tracking
    void registerMemoryRegion(void* addr, size_t size, int numa_node, 
                             HugePageSize page_size, AllocationPolicy policy);
    void unregisterMemoryRegion(void* addr);
    
    // Cache line operations
    __forceinline void prefetchCacheLineInternal(const void* addr, int locality) const {
        __builtin_prefetch(addr, 0, locality);
    }
    
    __forceinline void prefetchForWriteInternal(void* addr) const {
        __builtin_prefetch(addr, 1, 3);
    }
    
    // Alignment helpers
    __forceinline size_t alignUp(size_t size, size_t alignment) const {
        return (size + alignment - 1) & ~(alignment - 1);
    }
    
    __forceinline void* alignPointer(void* ptr, size_t alignment) const {
        uintptr_t addr = reinterpret_cast<uintptr_t>(ptr);
        return reinterpret_cast<void*>((addr + alignment - 1) & ~(alignment - 1));
    }
    
    // CPU and NUMA detection
    int getCurrentCPU() const;
    void bindCurrentThreadToNUMA(int numa_node);
};

/**
 * Lock-free memory pool optimized for frequent small allocations
 * Used for order objects, market data packets, etc.
 */
template<typename T>
class LockFreeMemoryPool {
private:
    struct alignas(64) PoolChunk {
        T objects[64]; // One cache line per chunk
        std::atomic<uint64_t> allocation_mask{0};
        PoolChunk* next{nullptr};
        char padding[64 - sizeof(PoolChunk*)];
    };
    
    std::atomic<PoolChunk*> head_{nullptr};
    NUMAMemoryManager* numa_manager_;
    int numa_node_;
    std::atomic<size_t> allocated_objects_{0};
    std::atomic<size_t> pool_chunks_{0};

public:
    explicit LockFreeMemoryPool(NUMAMemoryManager* numa_mgr, int numa_node = -1);
    ~LockFreeMemoryPool();
    
    // High-performance allocation/deallocation
    T* allocate();
    void deallocate(T* obj);
    
    // Bulk operations
    std::vector<T*> allocateBulk(size_t count);
    void deallocateBulk(const std::vector<T*>& objects);
    
    // Statistics
    size_t getAllocatedCount() const { return allocated_objects_.load(); }
    size_t getChunkCount() const { return pool_chunks_.load(); }
    
private:
    PoolChunk* allocateNewChunk();
    void deallocateChunk(PoolChunk* chunk);
};

/**
 * NUMA-aware circular buffer for ultra-low latency IPC
 */
template<typename T, size_t Capacity>
class NUMACircularBuffer {
private:
    static_assert((Capacity & (Capacity - 1)) == 0, "Capacity must be power of 2");
    
    alignas(64) T buffer_[Capacity];
    alignas(64) std::atomic<size_t> write_pos_{0};
    alignas(64) std::atomic<size_t> read_pos_{0};
    
    NUMAMemoryManager* numa_manager_;
    int numa_node_;

public:
    explicit NUMACircularBuffer(NUMAMemoryManager* numa_mgr, int numa_node = -1);
    
    // Lock-free operations
    bool push(const T& item);
    bool pop(T& item);
    
    // Bulk operations for efficiency
    size_t pushBulk(const T* items, size_t count);
    size_t popBulk(T* items, size_t count);
    
    // Status queries
    size_t size() const;
    bool empty() const;
    bool full() const;
    
    // Memory optimization
    void prefetchForWrite();
    void prefetchForRead();
};

// Template implementations
template<typename T>
T* NUMAMemoryManager::allocateObject(AllocationPolicy policy) {
    size_t size = sizeof(T);
    size_t aligned_size = alignUp(size, alignof(T));
    
    void* ptr = allocateAligned(aligned_size, alignof(T), policy);
    if (!ptr) return nullptr;
    
    // Use placement new for proper construction
    return new(ptr) T;
}

template<typename T>
T* NUMAMemoryManager::allocateArray(size_t count, AllocationPolicy policy) {
    size_t total_size = sizeof(T) * count;
    size_t aligned_size = alignUp(total_size, alignof(T));
    
    void* ptr = allocateAligned(aligned_size, alignof(T), policy);
    if (!ptr) return nullptr;
    
    // Initialize array elements
    T* array = static_cast<T*>(ptr);
    for (size_t i = 0; i < count; ++i) {
        new(&array[i]) T;
    }
    
    return array;
}

} // namespace hft::memory