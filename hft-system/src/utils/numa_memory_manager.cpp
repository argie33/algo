#include "numa_memory_manager.h"
#include <sched.h>
#include <sys/syscall.h>
#include <linux/mempolicy.h>
#include <fcntl.h>
#include <fstream>
#include <cstring>
#include <chrono>

namespace hft::memory {

NUMAMemoryManager::NUMAMemoryManager(const MemoryConfig& config) 
    : config_(config), num_numa_nodes_(0), num_cpus_(0) {
    
    // Initialize NUMA if available
    if (numa_available() == 0) {
        num_numa_nodes_ = numa_max_node() + 1;
        num_cpus_ = numa_num_possible_cpus();
    } else {
        // Fallback for non-NUMA systems
        num_numa_nodes_ = 1;
        num_cpus_ = std::thread::hardware_concurrency();
    }
    
    // Initialize data structures
    cpu_pools_.resize(num_cpus_);
    numa_to_cpus_.resize(num_numa_nodes_);
    cpu_to_numa_.resize(num_cpus_);
}

NUMAMemoryManager::~NUMAMemoryManager() {
    shutdown();
}

bool NUMAMemoryManager::initialize() {
    // Discover NUMA topology
    if (!discoverNUMATopology()) {
        return false;
    }
    
    // Setup huge pages if enabled
    if (config_.enable_huge_pages) {
        if (!setupHugePages()) {
            // Continue without huge pages if setup fails
        }
    }
    
    // Create per-CPU memory pools
    for (int cpu_id = 0; cpu_id < num_cpus_; ++cpu_id) {
        if (!createCPUPool(cpu_id, config_.default_pool_size)) {
            return false;
        }
    }
    
    // Set memory policy for current process
    if (config_.enable_numa_balancing) {
        unsigned long nodemask = (1UL << num_numa_nodes_) - 1;
        if (set_mempolicy(MPOL_PREFERRED, &nodemask, num_numa_nodes_) != 0) {
            // Continue without NUMA policy if it fails
        }
    }
    
    return true;
}

void NUMAMemoryManager::shutdown() {
    // Cleanup CPU pools
    for (auto& pool : cpu_pools_) {
        if (pool.pool_base) {
            // Unmap huge pages properly
            if (pool.pool_size >= static_cast<size_t>(HugePageSize::LARGE_2MB)) {
                munmap(pool.pool_base, pool.pool_size);
            } else {
                free(pool.pool_base);
            }
            pool.pool_base = nullptr;
        }
    }
    
    // Cleanup memory regions
    for (auto& region : memory_regions_) {
        if (region.base_address) {
            if (region.page_size != HugePageSize::STANDARD_4KB) {
                munmap(region.base_address, region.size);
            } else {
                free(region.base_address);
            }
        }
    }
    
    memory_regions_.clear();
    cpu_pools_.clear();
}

void* NUMAMemoryManager::allocate(size_t size, AllocationPolicy policy) {
    auto start_time = std::chrono::high_resolution_clock::now();
    
    // Handle zero-size allocation
    if (size == 0) return nullptr;
    
    // Align size to cache line boundary for performance
    size_t aligned_size = alignUp(size, MEMORY_ALIGNMENT);
    
    // Determine target NUMA node based on policy
    int target_node = -1;
    int current_cpu = getCurrentCPU();
    
    switch (policy) {
        case AllocationPolicy::LOCAL_ONLY:
            target_node = getCurrentNUMANode();
            break;
        case AllocationPolicy::PREFERRED:
            target_node = getCurrentNUMANode();
            break;
        case AllocationPolicy::INTERLEAVED:
            target_node = -1; // Will be handled by kernel
            break;
        case AllocationPolicy::SPECIFIC_NODE:
            target_node = getCurrentNUMANode();
            break;
    }
    
    void* ptr = nullptr;
    
    // Try fast path: allocate from CPU-local pool
    if (current_cpu >= 0 && current_cpu < num_cpus_ && 
        aligned_size <= config_.max_allocation_size / 4) {
        
        ptr = allocateFromPool(current_cpu, aligned_size);
        if (ptr) {
            stats_.numa_local_allocations.fetch_add(1, std::memory_order_relaxed);
        }
    }
    
    // Fallback to system allocation
    if (!ptr) {
        if (aligned_size >= static_cast<size_t>(HugePageSize::LARGE_2MB) && 
            config_.enable_huge_pages) {
            // Use huge pages for large allocations
            ptr = allocateHugePageInternal(aligned_size, config_.default_page_size, target_node);
        } else {
            ptr = allocateInternal(aligned_size, target_node, HugePageSize::STANDARD_4KB);
        }
        
        if (ptr && target_node != getCurrentNUMANode()) {
            stats_.numa_remote_allocations.fetch_add(1, std::memory_order_relaxed);
        } else if (ptr) {
            stats_.numa_local_allocations.fetch_add(1, std::memory_order_relaxed);
        }
    }
    
    if (ptr) {
        // Update statistics
        stats_.total_allocated.fetch_add(aligned_size, std::memory_order_relaxed);
        stats_.allocation_count.fetch_add(1, std::memory_order_relaxed);
        
        // Update peak usage
        size_t current_total = stats_.total_allocated.load();
        size_t current_peak = stats_.peak_usage.load();
        while (current_total > current_peak && 
               !stats_.peak_usage.compare_exchange_weak(current_peak, current_total)) {
            current_peak = stats_.peak_usage.load();
        }
        
        // Prefetch if enabled
        if (config_.enable_memory_prefetching) {
            prefetchMemory(ptr, std::min(aligned_size, static_cast<size_t>(256)));
        }
        
        // Calculate allocation time
        auto end_time = std::chrono::high_resolution_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::nanoseconds>(end_time - start_time);
        
        // Update average allocation time (lock-free exponential moving average)
        double current_avg = stats_.avg_allocation_time_ns.load();
        double new_time = static_cast<double>(duration.count());
        double new_avg = current_avg * 0.9 + new_time * 0.1;
        stats_.avg_allocation_time_ns.store(new_avg);
    }
    
    return ptr;
}

void* NUMAMemoryManager::allocateAligned(size_t size, size_t alignment, AllocationPolicy policy) {
    if (alignment <= MEMORY_ALIGNMENT) {
        return allocate(size, policy);
    }
    
    // Allocate extra space for alignment
    size_t total_size = size + alignment - 1 + sizeof(void*);
    void* raw_ptr = allocate(total_size, policy);
    
    if (!raw_ptr) return nullptr;
    
    // Calculate aligned address
    uintptr_t raw_addr = reinterpret_cast<uintptr_t>(raw_ptr);
    uintptr_t aligned_addr = (raw_addr + sizeof(void*) + alignment - 1) & ~(alignment - 1);
    void* aligned_ptr = reinterpret_cast<void*>(aligned_addr);
    
    // Store original pointer for deallocation
    void** ptr_storage = reinterpret_cast<void**>(aligned_addr - sizeof(void*));
    *ptr_storage = raw_ptr;
    
    return aligned_ptr;
}

void* NUMAMemoryManager::allocateHugePage(size_t size, HugePageSize page_size, AllocationPolicy policy) {
    int target_node = (policy == AllocationPolicy::LOCAL_ONLY) ? getCurrentNUMANode() : -1;
    
    void* ptr = allocateHugePageInternal(size, page_size, target_node);
    
    if (ptr) {
        stats_.huge_page_allocations.fetch_add(1, std::memory_order_relaxed);
        registerMemoryRegion(ptr, size, target_node, page_size, policy);
    }
    
    return ptr;
}

void NUMAMemoryManager::deallocate(void* ptr) {
    if (!ptr) return;
    
    // Try to deallocate from CPU pools first
    bool deallocated_from_pool = false;
    for (auto& pool : cpu_pools_) {
        uintptr_t pool_start = reinterpret_cast<uintptr_t>(pool.pool_base);
        uintptr_t pool_end = pool_start + pool.pool_size;
        uintptr_t ptr_addr = reinterpret_cast<uintptr_t>(ptr);
        
        if (ptr_addr >= pool_start && ptr_addr < pool_end) {
            // Mark as free in bitmap (simplified - real implementation would be more complex)
            pool.deallocations.fetch_add(1, std::memory_order_relaxed);
            deallocated_from_pool = true;
            break;
        }
    }
    
    if (!deallocated_from_pool) {
        // Check if it's a huge page allocation
        bool is_huge = false;
        for (const auto& region : memory_regions_) {
            if (region.base_address == ptr) {
                deallocateHugePage(ptr, region.size);
                is_huge = true;
                break;
            }
        }
        
        if (!is_huge) {
            free(ptr);
        }
    }
    
    stats_.deallocation_count.fetch_add(1, std::memory_order_relaxed);
}

bool NUMAMemoryManager::createCPUPool(int cpu_id, size_t pool_size) {
    if (cpu_id < 0 || cpu_id >= num_cpus_) return false;
    
    CPUMemoryPool& pool = cpu_pools_[cpu_id];
    pool.cpu_id = cpu_id;
    pool.numa_node = cpu_to_numa_[cpu_id];
    pool.pool_size = pool_size;
    
    // Allocate memory on the appropriate NUMA node
    void* memory = nullptr;
    
    if (config_.enable_huge_pages && pool_size >= static_cast<size_t>(HugePageSize::LARGE_2MB)) {
        // Use huge pages for CPU pools
        memory = allocateHugePageInternal(pool_size, HugePageSize::LARGE_2MB, pool.numa_node);
    } else {
        // Use regular pages
        memory = numa_alloc_onnode(pool_size, pool.numa_node);
    }
    
    if (!memory) {
        return false;
    }
    
    pool.pool_base = memory;
    pool.current_offset.store(0);
    
    // Initialize allocation bitmap
    for (auto& bitmap_word : pool.allocation_bitmap) {
        bitmap_word.store(0, std::memory_order_relaxed);
    }
    
    // Lock memory to prevent swapping
    if (config_.enable_huge_pages) {
        mlock(memory, pool_size);
    }
    
    return true;
}

void* NUMAMemoryManager::allocateFromPool(int cpu_id, size_t size) {
    if (cpu_id < 0 || cpu_id >= num_cpus_) return nullptr;
    
    CPUMemoryPool& pool = cpu_pools_[cpu_id];
    
    // Try fast bump allocator first
    size_t current_offset = pool.current_offset.load(std::memory_order_relaxed);
    size_t new_offset = current_offset + size;
    
    if (new_offset <= pool.pool_size) {
        // Try to atomically update offset
        if (pool.current_offset.compare_exchange_weak(current_offset, new_offset,
                                                     std::memory_order_acquire,
                                                     std::memory_order_relaxed)) {
            void* ptr = static_cast<char*>(pool.pool_base) + current_offset;
            pool.allocations.fetch_add(1, std::memory_order_relaxed);
            pool.bytes_allocated.fetch_add(size, std::memory_order_relaxed);
            return ptr;
        }
    }
    
    // Fallback to bitmap allocation for smaller objects
    if (size <= 64) { // Objects smaller than 64 bytes
        return allocateFromBitmap(pool, size);
    }
    
    return nullptr;
}

void* NUMAMemoryManager::allocateFromBitmap(CPUMemoryPool& pool, size_t size) {
    // Simplified bitmap allocation (real implementation would be more sophisticated)
    size_t blocks_needed = (size + 63) / 64; // 64-byte blocks
    
    for (size_t i = 0; i < 1024 - blocks_needed; ++i) {
        uint64_t mask = (1ULL << blocks_needed) - 1;
        uint64_t expected = 0;
        
        if (pool.allocation_bitmap[i].compare_exchange_weak(expected, mask,
                                                           std::memory_order_acquire,
                                                           std::memory_order_relaxed)) {
            void* ptr = static_cast<char*>(pool.pool_base) + (i * 64);
            pool.allocations.fetch_add(1, std::memory_order_relaxed);
            return ptr;
        }
    }
    
    return nullptr;
}

bool NUMAMemoryManager::discoverNUMATopology() {
    if (numa_available() != 0) {
        // Non-NUMA system - assign all CPUs to node 0
        for (int cpu = 0; cpu < num_cpus_; ++cpu) {
            numa_to_cpus_[0].push_back(cpu);
            cpu_to_numa_[cpu] = 0;
        }
        return true;
    }
    
    // Discover CPU to NUMA node mapping
    for (int cpu = 0; cpu < num_cpus_; ++cpu) {
        int node = numa_node_of_cpu(cpu);
        if (node >= 0 && node < num_numa_nodes_) {
            numa_to_cpus_[node].push_back(cpu);
            cpu_to_numa_[cpu] = node;
        } else {
            // Fallback: assign to node 0
            numa_to_cpus_[0].push_back(cpu);
            cpu_to_numa_[cpu] = 0;
        }
    }
    
    return true;
}

bool NUMAMemoryManager::setupHugePages() {
    // Try to enable transparent huge pages
    std::ofstream thp_file("/sys/kernel/mm/transparent_hugepage/enabled");
    if (thp_file.is_open()) {
        thp_file << "always";
        thp_file.close();
    }
    
    // Check available huge pages
    std::ifstream hugepages_file("/proc/meminfo");
    std::string line;
    
    while (std::getline(hugepages_file, line)) {
        if (line.find("HugePages_Total:") != std::string::npos) {
            size_t pos = line.find_last_of(' ');
            if (pos != std::string::npos) {
                size_t total_hugepages = std::stoull(line.substr(pos + 1));
                huge_page_counts_[HugePageSize::LARGE_2MB] = total_hugepages;
            }
            break;
        }
    }
    
    return true;
}

void* NUMAMemoryManager::allocateHugePageInternal(size_t size, HugePageSize page_size, int numa_node) {
    // Round up to page boundary
    size_t page_size_bytes = static_cast<size_t>(page_size);
    size_t aligned_size = alignUp(size, page_size_bytes);
    
    // Use mmap with huge page flags
    int flags = MAP_PRIVATE | MAP_ANONYMOUS;
    
    if (page_size == HugePageSize::LARGE_2MB) {
        flags |= MAP_HUGETLB | (21 << MAP_HUGE_SHIFT); // 2MB = 2^21
    } else if (page_size == HugePageSize::HUGE_1GB) {
        flags |= MAP_HUGETLB | (30 << MAP_HUGE_SHIFT); // 1GB = 2^30
    }
    
    void* ptr = mmap(nullptr, aligned_size, PROT_READ | PROT_WRITE, flags, -1, 0);
    
    if (ptr == MAP_FAILED) {
        // Fallback to regular allocation
        if (numa_node >= 0) {
            ptr = numa_alloc_onnode(aligned_size, numa_node);
        } else {
            ptr = malloc(aligned_size);
        }
    } else {
        // Bind to specific NUMA node if requested
        if (numa_node >= 0) {
            bindMemoryToNode(ptr, aligned_size, numa_node);
        }
    }
    
    return ptr;
}

void NUMAMemoryManager::bindMemoryToNode(void* addr, size_t size, int node) {
    unsigned long nodemask = 1UL << node;
    mbind(addr, size, MPOL_BIND, &nodemask, node + 1, MPOL_MF_STRICT);
}

int NUMAMemoryManager::getCurrentCPU() const {
    return sched_getcpu();
}

int NUMAMemoryManager::getCurrentNUMANode() const {
    int cpu = getCurrentCPU();
    if (cpu >= 0 && cpu < num_cpus_) {
        return cpu_to_numa_[cpu];
    }
    return 0; // Fallback to node 0
}

void NUMAMemoryManager::prefetchMemory(const void* addr, size_t size) const {
    if (!config_.enable_memory_prefetching) return;
    
    const char* ptr = static_cast<const char*>(addr);
    size_t prefetch_lines = (size + CACHE_LINE_SIZE - 1) / CACHE_LINE_SIZE;
    
    for (size_t i = 0; i < prefetch_lines && i < config_.prefetch_distance; ++i) {
        __builtin_prefetch(ptr + i * CACHE_LINE_SIZE, 0, 3);
    }
}

void NUMAMemoryManager::prefetchForWrite(void* addr, size_t size) const {
    if (!config_.enable_memory_prefetching) return;
    
    char* ptr = static_cast<char*>(addr);
    size_t prefetch_lines = (size + CACHE_LINE_SIZE - 1) / CACHE_LINE_SIZE;
    
    for (size_t i = 0; i < prefetch_lines && i < config_.prefetch_distance; ++i) {
        __builtin_prefetch(ptr + i * CACHE_LINE_SIZE, 1, 3);
    }
}

void NUMAMemoryManager::prefetchCacheLine(const void* addr, int hint) const {
    __builtin_prefetch(addr, 0, hint);
}

void NUMAMemoryManager::flushCacheLine(const void* addr) const {
    _mm_clflush(addr);
}

void* NUMAMemoryManager::allocateInternal(size_t size, int numa_node, HugePageSize page_size) {
    if (numa_node >= 0 && numa_available() == 0) {
        return numa_alloc_onnode(size, numa_node);
    } else {
        void* ptr = malloc(size);
        if (ptr && numa_node >= 0 && numa_available() == 0) {
            bindMemoryToNode(ptr, size, numa_node);
        }
        return ptr;
    }
}

void NUMAMemoryManager::registerMemoryRegion(void* addr, size_t size, int numa_node,
                                            HugePageSize page_size, AllocationPolicy policy) {
    MemoryRegion region;
    region.base_address = addr;
    region.size = size;
    region.numa_node = numa_node;
    region.page_size = page_size;
    region.policy = policy;
    region.allocation_timestamp = __rdtsc();
    
    memory_regions_.push_back(region);
}

void NUMAMemoryManager::resetStats() {
    stats_.total_allocated.store(0);
    stats_.total_freed.store(0);
    stats_.peak_usage.store(0);
    stats_.allocation_count.store(0);
    stats_.deallocation_count.store(0);
    stats_.huge_page_allocations.store(0);
    stats_.numa_local_allocations.store(0);
    stats_.numa_remote_allocations.store(0);
    stats_.avg_allocation_time_ns.store(0.0);
}

size_t NUMAMemoryManager::getTotalAllocatedMemory() const {
    return stats_.total_allocated.load();
}

const std::vector<int>& NUMAMemoryManager::getCPUsForNode(int numa_node) const {
    if (numa_node >= 0 && numa_node < num_numa_nodes_) {
        return numa_to_cpus_[numa_node];
    }
    static std::vector<int> empty;
    return empty;
}

double NUMAMemoryManager::getFragmentationRatio() const {
    size_t total_allocated = 0;
    size_t total_pool_size = 0;
    
    for (const auto& pool : cpu_pools_) {
        total_allocated += pool.bytes_allocated.load();
        total_pool_size += pool.pool_size;
    }
    
    if (total_pool_size == 0) return 0.0;
    
    return 1.0 - (static_cast<double>(total_allocated) / total_pool_size);
}

} // namespace hft::memory