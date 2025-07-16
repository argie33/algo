/**
 * Performance Utilities for HFT System
 * CPU optimization, timing, and profiling utilities
 */

#pragma once

#include <chrono>
#include <atomic>
#include <thread>
#include <sched.h>
#include <sys/mman.h>
#include <unistd.h>
#include <immintrin.h>

namespace HFT {

// High-resolution timestamp counter
class TSCTimer {
private:
    static std::atomic<double> tsc_frequency_;
    static std::atomic<bool> frequency_calibrated_;
    
public:
    // Get raw TSC value
    static inline uint64_t rdtsc() {
        uint32_t hi, lo;
        __asm__ __volatile__ ("rdtsc" : "=a"(lo), "=d"(hi));
        return ((uint64_t)hi << 32) | lo;
    }
    
    // Get serializing TSC (ensures ordering)
    static inline uint64_t rdtscp() {
        uint32_t hi, lo, aux;
        __asm__ __volatile__ ("rdtscp" : "=a"(lo), "=d"(hi), "=c"(aux));
        return ((uint64_t)hi << 32) | lo;
    }
    
    // Convert TSC to nanoseconds
    static inline uint64_t tsc_to_ns(uint64_t tsc_cycles) {
        if (!frequency_calibrated_.load()) {
            calibrate_frequency();
        }
        return static_cast<uint64_t>(tsc_cycles / tsc_frequency_.load());
    }
    
    // Convert nanoseconds to TSC
    static inline uint64_t ns_to_tsc(uint64_t nanoseconds) {
        if (!frequency_calibrated_.load()) {
            calibrate_frequency();
        }
        return static_cast<uint64_t>(nanoseconds * tsc_frequency_.load());
    }
    
    // Get current time in nanoseconds
    static inline uint64_t now_ns() {
        return tsc_to_ns(rdtsc());
    }
    
private:
    static void calibrate_frequency() {
        auto start_time = std::chrono::high_resolution_clock::now();
        uint64_t start_tsc = rdtsc();
        
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        
        uint64_t end_tsc = rdtsc();
        auto end_time = std::chrono::high_resolution_clock::now();
        
        auto duration_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
            end_time - start_time).count();
        
        double frequency = static_cast<double>(end_tsc - start_tsc) / duration_ns;
        tsc_frequency_.store(frequency);
        frequency_calibrated_.store(true);
    }
};

// CPU affinity and thread optimization
class CPUOptimizer {
public:
    // Set CPU affinity for current thread
    static bool setCPUAffinity(int cpu_id) {
        cpu_set_t cpuset;
        CPU_ZERO(&cpuset);
        CPU_SET(cpu_id, &cpuset);
        
        return pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset) == 0;
    }
    
    // Set multiple CPU affinity
    static bool setCPUAffinity(const std::vector<int>& cpu_ids) {
        cpu_set_t cpuset;
        CPU_ZERO(&cpuset);
        
        for (int cpu_id : cpu_ids) {
            CPU_SET(cpu_id, &cpuset);
        }
        
        return pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset) == 0;
    }
    
    // Set real-time priority
    static bool setRealtimePriority(int priority = 99) {
        struct sched_param param;
        param.sched_priority = priority;
        
        return pthread_setschedparam(pthread_self(), SCHED_FIFO, &param) == 0;
    }
    
    // Lock memory to prevent swapping
    static bool lockMemory() {
        return mlockall(MCL_CURRENT | MCL_FUTURE) == 0;
    }
    
    // Disable CPU frequency scaling
    static bool disableFrequencyScaling() {
        // This would require root privileges
        // In practice, done via system configuration
        return true;
    }
    
    // Isolate CPU cores
    static bool isolateCPUs(const std::vector<int>& cpu_ids) {
        // This would require kernel boot parameters: isolcpus=
        // and proper cgroup configuration
        return true;
    }
    
    // Get CPU topology information
    static int getNumCPUs() {
        return std::thread::hardware_concurrency();
    }
    
    // Check if CPU supports specific features
    static bool supportsTSC() {
        uint32_t eax, ebx, ecx, edx;
        __cpuid(1, eax, ebx, ecx, edx);
        return (edx & (1 << 4)) != 0; // TSC bit
    }
    
    static bool supportsRDTSCP() {
        uint32_t eax, ebx, ecx, edx;
        __cpuid(0x80000001, eax, ebx, ecx, edx);
        return (edx & (1 << 27)) != 0; // RDTSCP bit
    }
};

// Memory optimization utilities
class MemoryOptimizer {
public:
    // Enable huge pages
    static bool enableHugePages() {
        // Request transparent huge pages
        system("echo always > /sys/kernel/mm/transparent_hugepage/enabled");
        return true;
    }
    
    // Prefetch memory for better cache performance
    template<typename T>
    static void prefetch(const T* ptr, int distance = 1) {
        __builtin_prefetch(ptr + distance, 0, 3); // Read, high temporal locality
    }
    
    // Prefetch for write
    template<typename T>
    static void prefetchWrite(T* ptr, int distance = 1) {
        __builtin_prefetch(ptr + distance, 1, 3); // Write, high temporal locality
    }
    
    // Memory barrier utilities
    static void memoryBarrier() {
        std::atomic_thread_fence(std::memory_order_seq_cst);
    }
    
    static void compilerBarrier() {
        asm volatile("" ::: "memory");
    }
    
    // Cache line size detection
    static size_t getCacheLineSize() {
        return sysconf(_SC_LEVEL1_DCACHE_LINESIZE);
    }
    
    // Align pointer to cache line boundary
    template<typename T>
    static T* alignToCacheLine(T* ptr) {
        size_t cache_line_size = getCacheLineSize();
        uintptr_t addr = reinterpret_cast<uintptr_t>(ptr);
        uintptr_t aligned = (addr + cache_line_size - 1) & ~(cache_line_size - 1);
        return reinterpret_cast<T*>(aligned);
    }
};

// Branch prediction hints
#define LIKELY(x)       __builtin_expect(!!(x), 1)
#define UNLIKELY(x)     __builtin_expect(!!(x), 0)

// Force inlining
#define FORCE_INLINE    __attribute__((always_inline)) inline

// Performance profiler for critical sections
class PerformanceProfiler {
private:
    struct ProfileData {
        std::atomic<uint64_t> call_count{0};
        std::atomic<uint64_t> total_cycles{0};
        std::atomic<uint64_t> min_cycles{UINT64_MAX};
        std::atomic<uint64_t> max_cycles{0};
        std::string name;
    };
    
    static std::unordered_map<std::string, ProfileData> profiles_;
    static std::mutex profiles_mutex_;
    
public:
    class ScopedTimer {
    private:
        const std::string& name_;
        uint64_t start_tsc_;
        
    public:
        explicit ScopedTimer(const std::string& name) 
            : name_(name), start_tsc_(TSCTimer::rdtsc()) {}
        
        ~ScopedTimer() {
            uint64_t end_tsc = TSCTimer::rdtsc();
            uint64_t cycles = end_tsc - start_tsc_;
            
            std::lock_guard<std::mutex> lock(profiles_mutex_);
            
            ProfileData& data = profiles_[name_];
            data.name = name_;
            data.call_count.fetch_add(1);
            data.total_cycles.fetch_add(cycles);
            
            // Update min/max atomically
            uint64_t current_min = data.min_cycles.load();
            while (cycles < current_min && 
                   !data.min_cycles.compare_exchange_weak(current_min, cycles));
            
            uint64_t current_max = data.max_cycles.load();
            while (cycles > current_max && 
                   !data.max_cycles.compare_exchange_weak(current_max, cycles));
        }
    };
    
    static void printReport() {
        std::lock_guard<std::mutex> lock(profiles_mutex_);
        
        printf("\n=== PERFORMANCE PROFILE REPORT ===\n");
        printf("%-30s %10s %15s %15s %15s %15s\n", 
               "Function", "Calls", "Total (ns)", "Avg (ns)", "Min (ns)", "Max (ns)");
        printf("%-30s %10s %15s %15s %15s %15s\n", 
               "--------", "-----", "---------", "--------", "--------", "--------");
        
        for (const auto& [name, data] : profiles_) {
            uint64_t calls = data.call_count.load();
            uint64_t total_cycles = data.total_cycles.load();
            uint64_t avg_cycles = calls > 0 ? total_cycles / calls : 0;
            
            uint64_t total_ns = TSCTimer::tsc_to_ns(total_cycles);
            uint64_t avg_ns = TSCTimer::tsc_to_ns(avg_cycles);
            uint64_t min_ns = TSCTimer::tsc_to_ns(data.min_cycles.load());
            uint64_t max_ns = TSCTimer::tsc_to_ns(data.max_cycles.load());
            
            printf("%-30s %10lu %15lu %15lu %15lu %15lu\n",
                   name.c_str(), calls, total_ns, avg_ns, min_ns, max_ns);
        }
        printf("=====================================\n\n");
    }
    
    static void reset() {
        std::lock_guard<std::mutex> lock(profiles_mutex_);
        profiles_.clear();
    }
};

// Macro for easy profiling
#define PROFILE_SCOPE(name) \
    PerformanceProfiler::ScopedTimer _prof_timer(name)

// Hot/cold path annotations
#define HOT_PATH       __attribute__((hot))
#define COLD_PATH      __attribute__((cold))

// Loop optimization hints
#define UNROLL_LOOP    #pragma unroll
#define VECTORIZE      #pragma omp simd

// Latency measurement utilities
class LatencyMeasurer {
private:
    std::string name_;
    std::vector<uint64_t> measurements_;
    size_t max_measurements_;
    
public:
    explicit LatencyMeasurer(const std::string& name, size_t max_measurements = 10000)
        : name_(name), max_measurements_(max_measurements) {
        measurements_.reserve(max_measurements);
    }
    
    void recordLatency(uint64_t start_tsc, uint64_t end_tsc) {
        if (measurements_.size() < max_measurements_) {
            measurements_.push_back(end_tsc - start_tsc);
        }
    }
    
    void printStatistics() const {
        if (measurements_.empty()) return;
        
        std::vector<uint64_t> sorted = measurements_;
        std::sort(sorted.begin(), sorted.end());
        
        uint64_t sum = std::accumulate(sorted.begin(), sorted.end(), 0ULL);
        double mean_cycles = static_cast<double>(sum) / sorted.size();
        
        printf("\n=== LATENCY STATISTICS: %s ===\n", name_.c_str());
        printf("Measurements: %zu\n", sorted.size());
        printf("Mean: %.2f ns\n", TSCTimer::tsc_to_ns(static_cast<uint64_t>(mean_cycles)));
        printf("Min:  %lu ns\n", TSCTimer::tsc_to_ns(sorted.front()));
        printf("Max:  %lu ns\n", TSCTimer::tsc_to_ns(sorted.back()));
        printf("P50:  %lu ns\n", TSCTimer::tsc_to_ns(sorted[sorted.size() * 50 / 100]));
        printf("P95:  %lu ns\n", TSCTimer::tsc_to_ns(sorted[sorted.size() * 95 / 100]));
        printf("P99:  %lu ns\n", TSCTimer::tsc_to_ns(sorted[sorted.size() * 99 / 100]));
        printf("P99.9: %lu ns\n", TSCTimer::tsc_to_ns(sorted[sorted.size() * 999 / 1000]));
        printf("================================\n\n");
    }
};

// Static member definitions
std::atomic<double> TSCTimer::tsc_frequency_{3.0}; // Default 3GHz
std::atomic<bool> TSCTimer::frequency_calibrated_{false};

std::unordered_map<std::string, PerformanceProfiler::ProfileData> PerformanceProfiler::profiles_;
std::mutex PerformanceProfiler::profiles_mutex_;

} // namespace HFT