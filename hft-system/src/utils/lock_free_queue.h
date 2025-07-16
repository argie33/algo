/**
 * Lock-Free Queue Implementation
 * High-performance circular buffer for inter-thread communication
 */

#pragma once

#include <atomic>
#include <memory>
#include <cstring>

namespace HFT {

template<typename T, size_t Size>
class LockFreeQueue {
    static_assert((Size & (Size - 1)) == 0, "Size must be power of 2");
    
private:
    struct alignas(64) Element {
        std::atomic<uint64_t> sequence{0};
        T data;
    };
    
    static constexpr size_t MASK = Size - 1;
    
    alignas(64) Element buffer_[Size];
    alignas(64) std::atomic<uint64_t> head_{0};
    alignas(64) std::atomic<uint64_t> tail_{0};
    
public:
    LockFreeQueue() {
        for (size_t i = 0; i < Size; ++i) {
            buffer_[i].sequence.store(i, std::memory_order_relaxed);
        }
    }
    
    ~LockFreeQueue() = default;
    
    // Non-copyable
    LockFreeQueue(const LockFreeQueue&) = delete;
    LockFreeQueue& operator=(const LockFreeQueue&) = delete;
    
    bool push(const T& item) {
        uint64_t head = head_.load(std::memory_order_relaxed);
        
        while (true) {
            Element* element = &buffer_[head & MASK];
            uint64_t sequence = element->sequence.load(std::memory_order_acquire);
            
            if (sequence == head) {
                if (head_.compare_exchange_weak(head, head + 1, std::memory_order_relaxed)) {
                    element->data = item;
                    element->sequence.store(head + 1, std::memory_order_release);
                    return true;
                }
            } else if (sequence < head) {
                return false; // Queue is full
            } else {
                head = head_.load(std::memory_order_relaxed);
            }
        }
    }
    
    bool pop(T& item) {
        uint64_t tail = tail_.load(std::memory_order_relaxed);
        
        while (true) {
            Element* element = &buffer_[tail & MASK];
            uint64_t sequence = element->sequence.load(std::memory_order_acquire);
            
            if (sequence == tail + 1) {
                if (tail_.compare_exchange_weak(tail, tail + 1, std::memory_order_relaxed)) {
                    item = element->data;
                    element->sequence.store(tail + Size, std::memory_order_release);
                    return true;
                }
            } else if (sequence < tail + 1) {
                return false; // Queue is empty
            } else {
                tail = tail_.load(std::memory_order_relaxed);
            }
        }
    }
    
    bool empty() const {
        uint64_t head = head_.load(std::memory_order_acquire);
        uint64_t tail = tail_.load(std::memory_order_acquire);
        return head == tail;
    }
    
    size_t size() const {
        uint64_t head = head_.load(std::memory_order_acquire);
        uint64_t tail = tail_.load(std::memory_order_acquire);
        return head - tail;
    }
    
    size_t capacity() const {
        return Size;
    }
};

// Specialized queue for raw memory transfers (zero-copy)
template<size_t Size>
class LockFreeRawQueue {
    static_assert((Size & (Size - 1)) == 0, "Size must be power of 2");
    
private:
    struct alignas(64) Slot {
        std::atomic<uint64_t> sequence{0};
        char data[64]; // Fixed 64-byte slots
    };
    
    static constexpr size_t MASK = Size - 1;
    
    alignas(64) Slot buffer_[Size];
    alignas(64) std::atomic<uint64_t> head_{0};
    alignas(64) std::atomic<uint64_t> tail_{0};
    
public:
    LockFreeRawQueue() {
        for (size_t i = 0; i < Size; ++i) {
            buffer_[i].sequence.store(i, std::memory_order_relaxed);
        }
    }
    
    bool push(const void* data, size_t data_size) {
        if (data_size > 64) return false; // Data too large
        
        uint64_t head = head_.load(std::memory_order_relaxed);
        
        while (true) {
            Slot* slot = &buffer_[head & MASK];
            uint64_t sequence = slot->sequence.load(std::memory_order_acquire);
            
            if (sequence == head) {
                if (head_.compare_exchange_weak(head, head + 1, std::memory_order_relaxed)) {
                    std::memcpy(slot->data, data, data_size);
                    slot->sequence.store(head + 1, std::memory_order_release);
                    return true;
                }
            } else if (sequence < head) {
                return false; // Queue is full
            } else {
                head = head_.load(std::memory_order_relaxed);
            }
        }
    }
    
    bool pop(void* data, size_t max_size) {
        if (max_size < 64) return false; // Buffer too small
        
        uint64_t tail = tail_.load(std::memory_order_relaxed);
        
        while (true) {
            Slot* slot = &buffer_[tail & MASK];
            uint64_t sequence = slot->sequence.load(std::memory_order_acquire);
            
            if (sequence == tail + 1) {
                if (tail_.compare_exchange_weak(tail, tail + 1, std::memory_order_relaxed)) {
                    std::memcpy(data, slot->data, 64);
                    slot->sequence.store(tail + Size, std::memory_order_release);
                    return true;
                }
            } else if (sequence < tail + 1) {
                return false; // Queue is empty
            } else {
                tail = tail_.load(std::memory_order_relaxed);
            }
        }
    }
};

// Multiple producer, single consumer queue
template<typename T, size_t Size>
class MPSCQueue {
    static_assert((Size & (Size - 1)) == 0, "Size must be power of 2");
    
private:
    struct alignas(64) Element {
        std::atomic<T*> data{nullptr};
    };
    
    static constexpr size_t MASK = Size - 1;
    
    alignas(64) Element buffer_[Size];
    alignas(64) std::atomic<uint64_t> head_{0};
    alignas(64) uint64_t tail_{0}; // Only consumer modifies
    
public:
    MPSCQueue() = default;
    
    bool push(T* item) {
        uint64_t head = head_.fetch_add(1, std::memory_order_relaxed);
        Element* element = &buffer_[head & MASK];
        
        T* expected = nullptr;
        if (element->data.compare_exchange_strong(expected, item, std::memory_order_release)) {
            return true;
        }
        
        return false; // Slot was occupied
    }
    
    T* pop() {
        Element* element = &buffer_[tail_ & MASK];
        T* data = element->data.load(std::memory_order_acquire);
        
        if (data != nullptr) {
            element->data.store(nullptr, std::memory_order_relaxed);
            tail_++;
            return data;
        }
        
        return nullptr;
    }
};

} // namespace HFT