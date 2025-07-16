/**
 * High-Performance Memory Pool
 * Zero-allocation memory management for trading objects
 */

#pragma once

#include <atomic>
#include <vector>
#include <memory>
#include <cstdlib>
#include <new>

namespace HFT {

template<typename T>
class MemoryPool {
private:
    struct alignas(64) Block {
        union {
            T object;
            Block* next;
        };
        std::atomic<bool> in_use{false};
    };
    
    // Memory chunks for allocation
    struct Chunk {
        std::unique_ptr<Block[]> blocks;
        size_t size;
        
        Chunk(size_t chunk_size) : size(chunk_size) {
            // Allocate aligned memory
            void* ptr = nullptr;
            if (posix_memalign(&ptr, 64, sizeof(Block) * chunk_size) != 0) {
                throw std::bad_alloc();
            }
            blocks.reset(static_cast<Block*>(ptr));
            
            // Initialize free list within chunk
            for (size_t i = 0; i < chunk_size - 1; ++i) {
                blocks[i].next = &blocks[i + 1];
            }
            blocks[chunk_size - 1].next = nullptr;
        }
        
        ~Chunk() {
            if (blocks) {
                std::free(blocks.release());
            }
        }
    };
    
    std::vector<std::unique_ptr<Chunk>> chunks_;
    std::atomic<Block*> free_head_{nullptr};
    std::atomic<size_t> allocated_count_{0};
    std::atomic<size_t> total_capacity_{0};
    
    const size_t initial_chunk_size_;
    const size_t max_chunks_;
    
    mutable std::mutex growth_mutex_;
    
public:
    explicit MemoryPool(size_t initial_size = 1000, size_t max_chunks = 10)
        : initial_chunk_size_(initial_size), max_chunks_(max_chunks) {
        
        // Allocate initial chunk
        growPool();
    }
    
    ~MemoryPool() = default;
    
    // Non-copyable
    MemoryPool(const MemoryPool&) = delete;
    MemoryPool& operator=(const MemoryPool&) = delete;
    
    T* allocate() {
        Block* block = nullptr;
        
        // Try to get from free list
        while (true) {
            block = free_head_.load(std::memory_order_acquire);
            if (!block) {
                // Try to grow pool
                if (!growPool()) {
                    return nullptr; // Pool exhausted
                }
                continue;
            }
            
            if (free_head_.compare_exchange_weak(block, block->next, std::memory_order_release)) {
                break;
            }
        }
        
        // Mark as in use
        block->in_use.store(true, std::memory_order_relaxed);
        allocated_count_.fetch_add(1, std::memory_order_relaxed);
        
        // Construct object in place
        return new (&block->object) T();
    }
    
    template<typename... Args>
    T* allocate(Args&&... args) {
        Block* block = nullptr;
        
        // Try to get from free list
        while (true) {
            block = free_head_.load(std::memory_order_acquire);
            if (!block) {
                if (!growPool()) {
                    return nullptr;
                }
                continue;
            }
            
            if (free_head_.compare_exchange_weak(block, block->next, std::memory_order_release)) {
                break;
            }
        }
        
        block->in_use.store(true, std::memory_order_relaxed);
        allocated_count_.fetch_add(1, std::memory_order_relaxed);
        
        // Construct with arguments
        return new (&block->object) T(std::forward<Args>(args)...);
    }
    
    void deallocate(T* ptr) {
        if (!ptr) return;
        
        // Get block from object pointer
        Block* block = reinterpret_cast<Block*>(ptr);
        
        // Call destructor
        ptr->~T();
        
        // Mark as free
        block->in_use.store(false, std::memory_order_relaxed);
        allocated_count_.fetch_sub(1, std::memory_order_relaxed);
        
        // Add back to free list
        while (true) {
            Block* head = free_head_.load(std::memory_order_acquire);
            block->next = head;
            
            if (free_head_.compare_exchange_weak(head, block, std::memory_order_release)) {
                break;
            }
        }
    }
    
    // Pool statistics
    size_t allocated() const {
        return allocated_count_.load(std::memory_order_relaxed);
    }
    
    size_t capacity() const {
        return total_capacity_.load(std::memory_order_relaxed);
    }
    
    size_t available() const {
        return capacity() - allocated();
    }
    
    double utilization() const {
        size_t cap = capacity();
        return cap > 0 ? static_cast<double>(allocated()) / cap : 0.0;
    }

private:
    bool growPool() {
        std::lock_guard<std::mutex> lock(growth_mutex_);
        
        // Check if we've reached max chunks
        if (chunks_.size() >= max_chunks_) {
            return false;
        }
        
        try {
            // Calculate new chunk size (exponential growth)
            size_t new_chunk_size = initial_chunk_size_ * (1 << chunks_.size());
            
            auto new_chunk = std::make_unique<Chunk>(new_chunk_size);
            
            // Add chunk's free list to global free list
            Block* chunk_head = &new_chunk->blocks[0];
            Block* chunk_tail = &new_chunk->blocks[new_chunk_size - 1];
            
            // Link chunk to existing free list
            Block* current_head = free_head_.load(std::memory_order_acquire);
            chunk_tail->next = current_head;
            
            while (!free_head_.compare_exchange_weak(current_head, chunk_head, std::memory_order_release)) {
                chunk_tail->next = current_head;
            }
            
            // Update capacity
            total_capacity_.fetch_add(new_chunk_size, std::memory_order_relaxed);
            
            // Store chunk
            chunks_.push_back(std::move(new_chunk));
            
            return true;
            
        } catch (const std::exception&) {
            return false;
        }
    }
};

// Specialized pool for fixed-size objects
template<size_t ObjectSize, size_t Alignment = 64>
class FixedSizePool {
private:
    struct alignas(Alignment) Block {
        union {
            char data[ObjectSize];
            Block* next;
        };
        std::atomic<bool> in_use{false};
    };
    
    std::unique_ptr<Block[]> blocks_;
    std::atomic<Block*> free_head_;
    const size_t pool_size_;
    std::atomic<size_t> allocated_count_{0};
    
public:
    explicit FixedSizePool(size_t pool_size) 
        : pool_size_(pool_size), allocated_count_(0) {
        
        // Allocate aligned memory
        void* ptr = nullptr;
        if (posix_memalign(&ptr, Alignment, sizeof(Block) * pool_size) != 0) {
            throw std::bad_alloc();
        }
        blocks_.reset(static_cast<Block*>(ptr));
        
        // Initialize free list
        for (size_t i = 0; i < pool_size - 1; ++i) {
            blocks_[i].next = &blocks_[i + 1];
        }
        blocks_[pool_size - 1].next = nullptr;
        
        free_head_.store(&blocks_[0], std::memory_order_relaxed);
    }
    
    ~FixedSizePool() {
        if (blocks_) {
            std::free(blocks_.release());
        }
    }
    
    void* allocate() {
        Block* block = nullptr;
        
        while (true) {
            block = free_head_.load(std::memory_order_acquire);
            if (!block) {
                return nullptr; // Pool exhausted
            }
            
            if (free_head_.compare_exchange_weak(block, block->next, std::memory_order_release)) {
                break;
            }
        }
        
        block->in_use.store(true, std::memory_order_relaxed);
        allocated_count_.fetch_add(1, std::memory_order_relaxed);
        
        return block->data;
    }
    
    void deallocate(void* ptr) {
        if (!ptr) return;
        
        Block* block = reinterpret_cast<Block*>(ptr);
        block->in_use.store(false, std::memory_order_relaxed);
        allocated_count_.fetch_sub(1, std::memory_order_relaxed);
        
        // Add back to free list
        while (true) {
            Block* head = free_head_.load(std::memory_order_acquire);
            block->next = head;
            
            if (free_head_.compare_exchange_weak(head, block, std::memory_order_release)) {
                break;
            }
        }
    }
    
    size_t allocated() const {
        return allocated_count_.load(std::memory_order_relaxed);
    }
    
    size_t capacity() const {
        return pool_size_;
    }
    
    bool empty() const {
        return allocated() == 0;
    }
    
    bool full() const {
        return allocated() == capacity();
    }
};

// Thread-local pool manager
template<typename T>
class ThreadLocalPool {
private:
    thread_local static std::unique_ptr<MemoryPool<T>> local_pool_;
    
public:
    static T* allocate() {
        if (!local_pool_) {
            local_pool_ = std::make_unique<MemoryPool<T>>(100);
        }
        return local_pool_->allocate();
    }
    
    template<typename... Args>
    static T* allocate(Args&&... args) {
        if (!local_pool_) {
            local_pool_ = std::make_unique<MemoryPool<T>>(100);
        }
        return local_pool_->allocate(std::forward<Args>(args)...);
    }
    
    static void deallocate(T* ptr) {
        if (local_pool_) {
            local_pool_->deallocate(ptr);
        }
    }
};

template<typename T>
thread_local std::unique_ptr<MemoryPool<T>> ThreadLocalPool<T>::local_pool_;

} // namespace HFT