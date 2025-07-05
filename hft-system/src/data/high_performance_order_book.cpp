#include "high_performance_order_book.h"
#include <algorithm>
#include <cstring>
#include <immintrin.h>
#include <x86intrin.h>

namespace hft::data {

HighPerformanceOrderBook::HighPerformanceOrderBook(uint64_t min_price, 
                                                   uint64_t max_price, 
                                                   uint64_t tick_size)
    : min_price_(min_price), max_price_(max_price), price_tick_size_(tick_size),
      order_pool_(MAX_ORDERS) {
    
    // Initialize arrays to zero
    std::memset(orders_.data(), 0, sizeof(orders_));
    std::memset(bid_levels_.data(), 0, sizeof(bid_levels_));
    std::memset(ask_levels_.data(), 0, sizeof(ask_levels_));
    std::memset(&market_depth_, 0, sizeof(market_depth_));
    
    // Initialize lookup arrays to invalid values
    std::fill(order_id_to_index_.begin(), order_id_to_index_.end(), UINT32_MAX);
    std::fill(price_to_bid_level_.begin(), price_to_bid_level_.end(), -1);
    std::fill(price_to_ask_level_.begin(), price_to_ask_level_.end(), -1);
    
    // Initialize performance counter
    perf_counter_.reset();
}

bool HighPerformanceOrderBook::addOrder(uint64_t order_id, uint64_t price, 
                                       uint64_t quantity, uint8_t side, 
                                       uint16_t order_type) {
    // Performance measurement
    auto start_time = perf_counter_.startTimer();
    
    // Validate inputs
    if (!isValidPrice(price) || !isValidQuantity(quantity) || !isValidOrderId(order_id)) {
        return false;
    }
    
    // Check if we have space for new order
    uint32_t order_index = order_count_.load(std::memory_order_relaxed);
    if (order_index >= MAX_ORDERS) {
        return false;
    }
    
    // Create new order
    Order& order = orders_[order_index];
    order.order_id = order_id;
    order.price = price;
    order.quantity = quantity;
    order.timestamp = __rdtsc();
    order.side = side;
    order.order_type = order_type;
    order.flags = 0;
    
    // Update lookup table
    order_id_to_index_[order_id % MAX_ORDERS] = order_index;
    
    // Find or create price level
    uint32_t price_index = priceToIndex(price);
    
    if (side == 0) { // Buy order
        // Find insertion point using SIMD-optimized binary search
        uint32_t level_pos = findBidInsertionPoint(price);
        
        // Check if price level already exists
        if (level_pos < bid_level_count_ && bid_levels_[level_pos].price == price) {
            // Update existing level
            bid_levels_[level_pos].total_quantity += quantity;
            bid_levels_[level_pos].order_count++;
            bid_levels_[level_pos].last_update_time = order.timestamp;
        } else {
            // Create new price level
            PriceLevel new_level;
            new_level.price = price;
            new_level.total_quantity = quantity;
            new_level.order_count = 1;
            new_level.first_order_idx = order_index;
            new_level.last_update_time = order.timestamp;
            new_level.level_id = bid_level_count_;
            
            // Insert level using SIMD optimization
            insertBidLevelSIMD(level_pos, new_level);
            bid_level_count_.fetch_add(1, std::memory_order_relaxed);
        }
        
        // Update price-to-level mapping
        price_to_bid_level_[price_index] = static_cast<int32_t>(level_pos);
        stats_.bid_orders.fetch_add(1, std::memory_order_relaxed);
        
    } else { // Sell order
        uint32_t level_pos = findAskInsertionPoint(price);
        
        if (level_pos < ask_level_count_ && ask_levels_[level_pos].price == price) {
            ask_levels_[level_pos].total_quantity += quantity;
            ask_levels_[level_pos].order_count++;
            ask_levels_[level_pos].last_update_time = order.timestamp;
        } else {
            PriceLevel new_level;
            new_level.price = price;
            new_level.total_quantity = quantity;
            new_level.order_count = 1;
            new_level.first_order_idx = order_index;
            new_level.last_update_time = order.timestamp;
            new_level.level_id = ask_level_count_;
            
            insertAskLevelSIMD(level_pos, new_level);
            ask_level_count_.fetch_add(1, std::memory_order_relaxed);
        }
        
        price_to_ask_level_[price_index] = static_cast<int32_t>(level_pos);
        stats_.ask_orders.fetch_add(1, std::memory_order_relaxed);
    }
    
    // Update global counters
    order_count_.fetch_add(1, std::memory_order_relaxed);
    stats_.total_orders.fetch_add(1, std::memory_order_relaxed);
    stats_.total_quantity.fetch_add(quantity, std::memory_order_relaxed);
    stats_.operations_count.fetch_add(1, std::memory_order_relaxed);
    
    // Update market depth cache
    updateMarketDepthSIMD();
    
    // Update best bid/offer atomically
    if (side == 0 && (stats_.best_bid.load() == 0 || price > stats_.best_bid.load())) {
        stats_.best_bid.store(price, std::memory_order_relaxed);
    } else if (side == 1 && (stats_.best_ask.load() == 0 || price < stats_.best_ask.load())) {
        stats_.best_ask.store(price, std::memory_order_relaxed);
    }
    
    // Calculate and update spread
    uint64_t best_bid = stats_.best_bid.load();
    uint64_t best_ask = stats_.best_ask.load();
    if (best_bid > 0 && best_ask > 0) {
        double spread_bps = static_cast<double>(best_ask - best_bid) / best_bid * 10000.0;
        stats_.spread_bps.store(spread_bps, std::memory_order_relaxed);
    }
    
    perf_counter_.endTimer(start_time);
    return true;
}

bool HighPerformanceOrderBook::removeOrder(uint64_t order_id) {
    auto start_time = perf_counter_.startTimer();
    
    // Find order in lookup table
    uint32_t lookup_index = order_id % MAX_ORDERS;
    uint32_t order_index = order_id_to_index_[lookup_index];
    
    if (order_index == UINT32_MAX || order_index >= order_count_.load() || 
        orders_[order_index].order_id != order_id) {
        return false;
    }
    
    const Order& order = orders_[order_index];
    uint32_t price_index = priceToIndex(order.price);
    
    if (order.side == 0) { // Buy order
        int32_t level_idx = price_to_bid_level_[price_index];
        if (level_idx >= 0 && level_idx < static_cast<int32_t>(bid_level_count_)) {
            PriceLevel& level = bid_levels_[level_idx];
            level.total_quantity -= order.quantity;
            level.order_count--;
            
            // Remove level if no orders remain
            if (level.order_count == 0) {
                removeBidLevelSIMD(level_idx);
                bid_level_count_.fetch_sub(1, std::memory_order_relaxed);
                price_to_bid_level_[price_index] = -1;
            }
        }
        stats_.bid_orders.fetch_sub(1, std::memory_order_relaxed);
        
    } else { // Sell order
        int32_t level_idx = price_to_ask_level_[price_index];
        if (level_idx >= 0 && level_idx < static_cast<int32_t>(ask_level_count_)) {
            PriceLevel& level = ask_levels_[level_idx];
            level.total_quantity -= order.quantity;
            level.order_count--;
            
            if (level.order_count == 0) {
                removeAskLevelSIMD(level_idx);
                ask_level_count_.fetch_sub(1, std::memory_order_relaxed);
                price_to_ask_level_[price_index] = -1;
            }
        }
        stats_.ask_orders.fetch_sub(1, std::memory_order_relaxed);
    }
    
    // Mark order as removed
    order_id_to_index_[lookup_index] = UINT32_MAX;
    
    // Update statistics
    stats_.total_quantity.fetch_sub(order.quantity, std::memory_order_relaxed);
    stats_.operations_count.fetch_add(1, std::memory_order_relaxed);
    
    // Update market depth
    updateMarketDepthSIMD();
    
    perf_counter_.endTimer(start_time);
    return true;
}

__forceinline uint32_t HighPerformanceOrderBook::findBidInsertionPoint(uint64_t price) const {
    // SIMD-optimized binary search for bid levels (descending order)
    uint32_t left = 0;
    uint32_t right = bid_level_count_.load(std::memory_order_relaxed);
    
    while (right - left >= 8) {
        // Use SIMD to compare 4 prices at once
        uint32_t mid = left + ((right - left) >> 3) * 4; // Align to 4-element boundary
        
        // Load 4 prices into AVX register
        __m256d target_prices = _mm256_set1_pd(static_cast<double>(price));
        __m256d level_prices = _mm256_set_pd(
            static_cast<double>(bid_levels_[mid + 3].price),
            static_cast<double>(bid_levels_[mid + 2].price),
            static_cast<double>(bid_levels_[mid + 1].price),
            static_cast<double>(bid_levels_[mid].price)
        );
        
        // Compare all 4 at once (bid levels are in descending order)
        __m256d cmp_result = _mm256_cmp_pd(target_prices, level_prices, _CMP_GT_OQ);
        int mask = _mm256_movemask_pd(cmp_result);
        
        if (mask == 0) {
            // Target is <= all compared prices, search left half
            right = mid;
        } else if (mask == 0xF) {
            // Target is > all compared prices, search right half
            left = mid + 4;
        } else {
            // Target is between some prices, narrow down
            left = mid + __builtin_ctz(mask);
            right = left + 1;
            break;
        }
    }
    
    // Linear search for remaining elements
    while (left < right) {
        uint32_t mid = left + (right - left) / 2;
        if (price > bid_levels_[mid].price) {
            left = mid + 1;
        } else {
            right = mid;
        }
    }
    
    return left;
}

__forceinline uint32_t HighPerformanceOrderBook::findAskInsertionPoint(uint64_t price) const {
    // SIMD-optimized binary search for ask levels (ascending order)
    uint32_t left = 0;
    uint32_t right = ask_level_count_.load(std::memory_order_relaxed);
    
    while (right - left >= 8) {
        uint32_t mid = left + ((right - left) >> 3) * 4;
        
        __m256d target_prices = _mm256_set1_pd(static_cast<double>(price));
        __m256d level_prices = _mm256_set_pd(
            static_cast<double>(ask_levels_[mid + 3].price),
            static_cast<double>(ask_levels_[mid + 2].price),
            static_cast<double>(ask_levels_[mid + 1].price),
            static_cast<double>(ask_levels_[mid].price)
        );
        
        // Compare all 4 at once (ask levels are in ascending order)
        __m256d cmp_result = _mm256_cmp_pd(target_prices, level_prices, _CMP_LT_OQ);
        int mask = _mm256_movemask_pd(cmp_result);
        
        if (mask == 0) {
            // Target is >= all compared prices, search right half
            left = mid + 4;
        } else if (mask == 0xF) {
            // Target is < all compared prices, search left half
            right = mid;
        } else {
            // Target is between some prices
            right = mid + __builtin_ctz(~mask);
            break;
        }
    }
    
    // Linear search for remaining elements
    while (left < right) {
        uint32_t mid = left + (right - left) / 2;
        if (price < ask_levels_[mid].price) {
            right = mid;
        } else {
            left = mid + 1;
        }
    }
    
    return left;
}

void HighPerformanceOrderBook::insertBidLevelSIMD(uint32_t position, const PriceLevel& level) {
    uint32_t current_count = bid_level_count_.load(std::memory_order_relaxed);
    
    // Move elements using SIMD when possible
    if (position < current_count) {
        // Calculate number of elements to move
        size_t elements_to_move = current_count - position;
        
        // Use SIMD for bulk memory operations
        if (elements_to_move >= 4) {
            // Move in chunks of 4 elements (256 bytes) using AVX
            const char* src = reinterpret_cast<const char*>(&bid_levels_[position]);
            char* dst = reinterpret_cast<char*>(&bid_levels_[position + 1]);
            size_t bytes_to_move = elements_to_move * sizeof(PriceLevel);
            
            // Use non-temporal stores for large moves to avoid cache pollution
            if (bytes_to_move > 256) {
                for (size_t i = 0; i < bytes_to_move; i += 32) {
                    __m256i data = _mm256_load_si256(reinterpret_cast<const __m256i*>(src + i));
                    _mm256_stream_si256(reinterpret_cast<__m256i*>(dst + i), data);
                }
                _mm_sfence(); // Ensure all stores complete
            } else {
                std::memmove(dst, src, bytes_to_move);
            }
        } else {
            // Small move, use regular memmove
            std::memmove(&bid_levels_[position + 1], &bid_levels_[position], 
                        elements_to_move * sizeof(PriceLevel));
        }
    }
    
    // Insert new level
    bid_levels_[position] = level;
}

void HighPerformanceOrderBook::insertAskLevelSIMD(uint32_t position, const PriceLevel& level) {
    uint32_t current_count = ask_level_count_.load(std::memory_order_relaxed);
    
    if (position < current_count) {
        size_t elements_to_move = current_count - position;
        
        if (elements_to_move >= 4) {
            const char* src = reinterpret_cast<const char*>(&ask_levels_[position]);
            char* dst = reinterpret_cast<char*>(&ask_levels_[position + 1]);
            size_t bytes_to_move = elements_to_move * sizeof(PriceLevel);
            
            if (bytes_to_move > 256) {
                for (size_t i = 0; i < bytes_to_move; i += 32) {
                    __m256i data = _mm256_load_si256(reinterpret_cast<const __m256i*>(src + i));
                    _mm256_stream_si256(reinterpret_cast<__m256i*>(dst + i), data);
                }
                _mm_sfence();
            } else {
                std::memmove(dst, src, bytes_to_move);
            }
        } else {
            std::memmove(&ask_levels_[position + 1], &ask_levels_[position], 
                        elements_to_move * sizeof(PriceLevel));
        }
    }
    
    ask_levels_[position] = level;
}

void HighPerformanceOrderBook::updateMarketDepthSIMD() {
    // Update sequence number
    market_depth_.sequence_number = sequence_number_.fetch_add(1, std::memory_order_relaxed);
    market_depth_.last_update_time = __rdtsc();
    
    // Update bid side using SIMD
    uint32_t bid_count = std::min(bid_level_count_.load(), 
                                 static_cast<uint32_t>(MarketDepth::MAX_LEVELS));
    market_depth_.bid_levels = bid_count;
    
    aggregateQuantitiesSIMD(bid_levels_.data(), bid_count, 
                          market_depth_.bid_prices, market_depth_.bid_quantities);
    
    // Update ask side using SIMD
    uint32_t ask_count = std::min(ask_level_count_.load(), 
                                 static_cast<uint32_t>(MarketDepth::MAX_LEVELS));
    market_depth_.ask_levels = ask_count;
    
    aggregateQuantitiesSIMD(ask_levels_.data(), ask_count,
                          market_depth_.ask_prices, market_depth_.ask_quantities);
}

void HighPerformanceOrderBook::aggregateQuantitiesSIMD(const PriceLevel* levels, size_t count,
                                                      __m256d* prices, __m256d* quantities) const {
    // Process levels in groups of 4 using AVX
    size_t simd_count = count / 4;
    size_t remainder = count % 4;
    
    for (size_t i = 0; i < simd_count; ++i) {
        // Load 4 prices and quantities
        prices[i] = _mm256_set_pd(
            static_cast<double>(levels[i * 4 + 3].price),
            static_cast<double>(levels[i * 4 + 2].price),
            static_cast<double>(levels[i * 4 + 1].price),
            static_cast<double>(levels[i * 4].price)
        );
        
        quantities[i] = _mm256_set_pd(
            static_cast<double>(levels[i * 4 + 3].total_quantity),
            static_cast<double>(levels[i * 4 + 2].total_quantity),
            static_cast<double>(levels[i * 4 + 1].total_quantity),
            static_cast<double>(levels[i * 4].total_quantity)
        );
    }
    
    // Handle remaining elements
    if (remainder > 0) {
        double price_array[4] = {0.0, 0.0, 0.0, 0.0};
        double quantity_array[4] = {0.0, 0.0, 0.0, 0.0};
        
        for (size_t i = 0; i < remainder; ++i) {
            price_array[i] = static_cast<double>(levels[simd_count * 4 + i].price);
            quantity_array[i] = static_cast<double>(levels[simd_count * 4 + i].total_quantity);
        }
        
        prices[simd_count] = _mm256_load_pd(price_array);
        quantities[simd_count] = _mm256_load_pd(quantity_array);
    }
}

std::pair<uint64_t, uint64_t> HighPerformanceOrderBook::getBestBidOffer() const {
    // Use SIMD to find best prices efficiently
    uint64_t best_bid = 0;
    uint64_t best_ask = UINT64_MAX;
    
    // Find best bid (highest price in bid levels)
    uint32_t bid_count = bid_level_count_.load(std::memory_order_relaxed);
    if (bid_count > 0) {
        best_bid = bid_levels_[0].price; // Bid levels are sorted descending
    }
    
    // Find best ask (lowest price in ask levels)
    uint32_t ask_count = ask_level_count_.load(std::memory_order_relaxed);
    if (ask_count > 0) {
        best_ask = ask_levels_[0].price; // Ask levels are sorted ascending
    }
    
    return {best_bid, best_ask == UINT64_MAX ? 0 : best_ask};
}

uint64_t HighPerformanceOrderBook::getTotalBidQuantity() const {
    uint64_t total = 0;
    uint32_t count = bid_level_count_.load(std::memory_order_relaxed);
    
    // Use SIMD for fast aggregation
    __m256d sum_vec = _mm256_setzero_pd();
    
    // Process in chunks of 4
    size_t simd_iterations = count / 4;
    for (size_t i = 0; i < simd_iterations; ++i) {
        __m256d quantities = _mm256_set_pd(
            static_cast<double>(bid_levels_[i * 4 + 3].total_quantity),
            static_cast<double>(bid_levels_[i * 4 + 2].total_quantity),
            static_cast<double>(bid_levels_[i * 4 + 1].total_quantity),
            static_cast<double>(bid_levels_[i * 4].total_quantity)
        );
        sum_vec = _mm256_add_pd(sum_vec, quantities);
    }
    
    // Sum the vector elements
    double sum_array[4];
    _mm256_store_pd(sum_array, sum_vec);
    total = static_cast<uint64_t>(sum_array[0] + sum_array[1] + sum_array[2] + sum_array[3]);
    
    // Handle remaining elements
    for (size_t i = simd_iterations * 4; i < count; ++i) {
        total += bid_levels_[i].total_quantity;
    }
    
    return total;
}

uint64_t HighPerformanceOrderBook::getTotalAskQuantity() const {
    uint64_t total = 0;
    uint32_t count = ask_level_count_.load(std::memory_order_relaxed);
    
    // Use SIMD for fast aggregation
    __m256d sum_vec = _mm256_setzero_pd();
    
    size_t simd_iterations = count / 4;
    for (size_t i = 0; i < simd_iterations; ++i) {
        __m256d quantities = _mm256_set_pd(
            static_cast<double>(ask_levels_[i * 4 + 3].total_quantity),
            static_cast<double>(ask_levels_[i * 4 + 2].total_quantity),
            static_cast<double>(ask_levels_[i * 4 + 1].total_quantity),
            static_cast<double>(ask_levels_[i * 4].total_quantity)
        );
        sum_vec = _mm256_add_pd(sum_vec, quantities);
    }
    
    double sum_array[4];
    _mm256_store_pd(sum_array, sum_vec);
    total = static_cast<uint64_t>(sum_array[0] + sum_array[1] + sum_array[2] + sum_array[3]);
    
    for (size_t i = simd_iterations * 4; i < count; ++i) {
        total += ask_levels_[i].total_quantity;
    }
    
    return total;
}

double HighPerformanceOrderBook::getSpreadBps() const {
    auto [best_bid, best_ask] = getBestBidOffer();
    
    if (best_bid == 0 || best_ask == 0) {
        return 0.0;
    }
    
    return static_cast<double>(best_ask - best_bid) / best_bid * 10000.0;
}

double HighPerformanceOrderBook::getVWAP(uint8_t side, size_t levels) const {
    if (levels == 0) return 0.0;
    
    uint64_t total_quantity = 0;
    uint64_t weighted_price_sum = 0;
    
    const PriceLevel* level_array = (side == 0) ? bid_levels_.data() : ask_levels_.data();
    uint32_t level_count = (side == 0) ? bid_level_count_.load() : ask_level_count_.load();
    
    size_t actual_levels = std::min(levels, static_cast<size_t>(level_count));
    
    for (size_t i = 0; i < actual_levels; ++i) {
        const PriceLevel& level = level_array[i];
        total_quantity += level.total_quantity;
        weighted_price_sum += level.price * level.total_quantity;
    }
    
    if (total_quantity == 0) return 0.0;
    
    return static_cast<double>(weighted_price_sum) / total_quantity / PRICE_MULTIPLIER;
}

bool HighPerformanceOrderBook::isValidPrice(uint64_t price) const {
    return price >= min_price_ && price <= max_price_ && 
           (price % price_tick_size_) == 0;
}

bool HighPerformanceOrderBook::isValidQuantity(uint64_t quantity) const {
    return quantity > 0 && quantity <= 1000000000ULL; // Max 1 billion shares
}

bool HighPerformanceOrderBook::isValidOrderId(uint64_t order_id) const {
    return order_id > 0 && order_id != UINT64_MAX;
}

void HighPerformanceOrderBook::resetStats() {
    stats_.total_orders.store(0);
    stats_.bid_orders.store(0);
    stats_.ask_orders.store(0);
    stats_.total_quantity.store(0);
    stats_.operations_count.store(0);
    stats_.last_trade_price.store(0);
    stats_.last_trade_quantity.store(0);
    stats_.best_bid.store(0);
    stats_.best_ask.store(0);
    stats_.spread_bps.store(0.0);
}

} // namespace hft::data