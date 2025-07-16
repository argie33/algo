#pragma once

#include <immintrin.h>
#include <x86intrin.h>
#include <array>
#include <atomic>
#include <memory>
#include <unordered_map>
#include <vector>
#include <algorithm>

#include "../utils/performance_utils.h"
#include "../utils/memory_pool.h"

namespace hft::data {

/**
 * Ultra-high performance order book optimized for HFT operations
 * Target: <1μs for add/remove/modify operations
 * Features: SIMD vectorization, cache-aligned arrays, O(1) operations
 */
class HighPerformanceOrderBook {
public:
    // Order structure optimized for cache alignment and SIMD operations
    struct alignas(64) Order {
        uint64_t order_id;
        uint64_t price;           // Fixed-point with 6 decimal precision
        uint64_t quantity;
        uint64_t timestamp;       // Hardware timestamp
        uint32_t trader_id;
        uint16_t order_type;      // Market, Limit, Stop, etc.
        uint8_t side;             // 0=Buy, 1=Sell
        uint8_t flags;            // Hidden, IOC, FOK, etc.
        char padding[32];         // Pad to cache line boundary
    };

    // Price level structure with SIMD-friendly layout
    struct alignas(64) PriceLevel {
        uint64_t price;
        uint64_t total_quantity;
        uint32_t order_count;
        uint32_t first_order_idx; // Index into order array
        uint64_t last_update_time;
        uint32_t level_id;
        char padding[20];         // Pad to cache line
    };

    // Market depth snapshot for ultra-fast access
    struct alignas(64) MarketDepth {
        static constexpr size_t MAX_LEVELS = 32; // Top 32 levels each side
        
        // Bid side (buy orders)
        __m256d bid_prices[MAX_LEVELS / 4];      // 4 prices per AVX register
        __m256d bid_quantities[MAX_LEVELS / 4];   // 4 quantities per AVX register
        
        // Ask side (sell orders)  
        __m256d ask_prices[MAX_LEVELS / 4];
        __m256d ask_quantities[MAX_LEVELS / 4];
        
        // Metadata
        uint32_t bid_levels;
        uint32_t ask_levels;
        uint64_t last_update_time;
        uint64_t sequence_number;
        char padding[32];
    };

    // Order book statistics
    struct alignas(64) BookStats {
        std::atomic<uint64_t> total_orders{0};
        std::atomic<uint64_t> bid_orders{0};
        std::atomic<uint64_t> ask_orders{0};
        std::atomic<uint64_t> total_quantity{0};
        std::atomic<uint64_t> operations_count{0};
        std::atomic<uint64_t> last_trade_price{0};
        std::atomic<uint64_t> last_trade_quantity{0};
        std::atomic<uint64_t> best_bid{0};
        std::atomic<uint64_t> best_ask{0};
        std::atomic<double> spread_bps{0.0};
    };

private:
    // Constants for optimization
    static constexpr size_t MAX_ORDERS = 100000;
    static constexpr size_t MAX_PRICE_LEVELS = 10000;
    static constexpr size_t CACHE_LINE_SIZE = 64;
    static constexpr uint64_t PRICE_MULTIPLIER = 1000000; // 6 decimal places
    
    // Core data structures (cache-aligned)
    alignas(CACHE_LINE_SIZE) std::array<Order, MAX_ORDERS> orders_;
    alignas(CACHE_LINE_SIZE) std::array<PriceLevel, MAX_PRICE_LEVELS> bid_levels_;
    alignas(CACHE_LINE_SIZE) std::array<PriceLevel, MAX_PRICE_LEVELS> ask_levels_;
    
    // Fast lookup structures
    alignas(CACHE_LINE_SIZE) std::array<uint32_t, MAX_ORDERS> order_id_to_index_;
    alignas(CACHE_LINE_SIZE) std::array<int32_t, MAX_PRICE_LEVELS> price_to_bid_level_;
    alignas(CACHE_LINE_SIZE) std::array<int32_t, MAX_PRICE_LEVELS> price_to_ask_level_;
    
    // Market depth cache
    alignas(CACHE_LINE_SIZE) MarketDepth market_depth_;
    
    // Counters and state
    std::atomic<uint32_t> order_count_{0};
    std::atomic<uint32_t> bid_level_count_{0};
    std::atomic<uint32_t> ask_level_count_{0};
    std::atomic<uint64_t> sequence_number_{0};
    
    // Performance tracking
    BookStats stats_;
    PerformanceCounter perf_counter_;
    
    // Memory management
    MemoryPool<Order> order_pool_;
    
    // Price indexing for O(1) lookup
    uint64_t min_price_;
    uint64_t max_price_;
    uint64_t price_tick_size_;

public:
    explicit HighPerformanceOrderBook(uint64_t min_price = 1000,      // $0.01
                                     uint64_t max_price = 1000000000, // $1000.00
                                     uint64_t tick_size = 1000);      // $0.001

    ~HighPerformanceOrderBook() = default;

    // Core order book operations (target: <1μs each)
    bool addOrder(uint64_t order_id, uint64_t price, uint64_t quantity, 
                 uint8_t side, uint16_t order_type = 1);
    
    bool removeOrder(uint64_t order_id);
    
    bool modifyOrder(uint64_t order_id, uint64_t new_price, uint64_t new_quantity);
    
    // Ultra-fast market data access
    const MarketDepth& getMarketDepth() const { return market_depth_; }
    
    // Best bid/offer with SIMD optimization
    std::pair<uint64_t, uint64_t> getBestBidOffer() const;
    
    // Market depth queries
    uint64_t getBidQuantityAtPrice(uint64_t price) const;
    uint64_t getAskQuantityAtPrice(uint64_t price) const;
    
    // Aggregate quantities using SIMD
    uint64_t getTotalBidQuantity() const;
    uint64_t getTotalAskQuantity() const;
    
    // Order matching engine
    std::vector<std::pair<uint64_t, uint64_t>> matchOrder(uint64_t price, 
                                                          uint64_t quantity, 
                                                          uint8_t side);
    
    // Market impact calculation
    double calculateMarketImpact(uint64_t quantity, uint8_t side) const;
    
    // Spread analysis
    double getSpreadBps() const;
    uint64_t getSpreadTicks() const;
    
    // Volume-weighted average price
    double getVWAP(uint8_t side, size_t levels = 5) const;
    
    // Statistics and monitoring
    const BookStats& getStats() const { return stats_; }
    void resetStats();
    
    // Performance optimization
    void optimizeMemoryLayout();
    void prefetchLevels(uint8_t side, size_t start_level, size_t count);
    
    // Compliance and audit
    std::vector<Order> getOrderHistory() const;
    void validateBookIntegrity() const;

private:
    // Core internal operations optimized with SIMD
    __forceinline uint32_t findBidInsertionPoint(uint64_t price) const;
    __forceinline uint32_t findAskInsertionPoint(uint64_t price) const;
    
    // SIMD-optimized level operations
    void insertBidLevelSIMD(uint32_t position, const PriceLevel& level);
    void insertAskLevelSIMD(uint32_t position, const PriceLevel& level);
    void removeBidLevelSIMD(uint32_t position);
    void removeAskLevelSIMD(uint32_t position);
    
    // Fast price-to-index conversion
    __forceinline uint32_t priceToIndex(uint64_t price) const {
        return static_cast<uint32_t>((price - min_price_) / price_tick_size_);
    }
    
    __forceinline uint64_t indexToPrice(uint32_t index) const {
        return min_price_ + (index * price_tick_size_);
    }
    
    // Market depth update with vectorization
    void updateMarketDepthSIMD();
    
    // Level aggregation using AVX instructions
    void aggregateQuantitiesSIMD(const PriceLevel* levels, size_t count, 
                                __m256d* prices, __m256d* quantities) const;
    
    // Memory prefetching for cache optimization
    void prefetchOrderData(uint32_t order_index) const;
    void prefetchLevelData(uint32_t level_index, uint8_t side) const;
    
    // Validation helpers
    bool isValidPrice(uint64_t price) const;
    bool isValidQuantity(uint64_t quantity) const;
    bool isValidOrderId(uint64_t order_id) const;
};

/**
 * Specialized order book for market making strategies
 * Optimized for frequent updates and tight spreads
 */
class MarketMakerOrderBook : public HighPerformanceOrderBook {
private:
    // Market maker specific optimizations
    struct MarketMakerState {
        uint64_t our_best_bid_price{0};
        uint64_t our_best_ask_price{0};
        uint64_t our_bid_quantity{0};
        uint64_t our_ask_quantity{0};
        uint32_t our_bid_order_count{0};
        uint32_t our_ask_order_count{0};
        bool is_crossed{false};
        double adverse_selection_ratio{0.0};
    };
    
    MarketMakerState mm_state_;
    std::unordered_map<uint64_t, bool> our_orders_; // Track our own orders

public:
    explicit MarketMakerOrderBook(uint64_t min_price = 1000,
                                 uint64_t max_price = 1000000000,
                                 uint64_t tick_size = 1000);
    
    // Market maker specific operations
    bool addOurOrder(uint64_t order_id, uint64_t price, uint64_t quantity, uint8_t side);
    bool removeOurOrder(uint64_t order_id);
    
    // Optimal spread calculation
    std::pair<uint64_t, uint64_t> calculateOptimalSpread() const;
    
    // Adverse selection detection
    double getAdverseSelectionRatio() const { return mm_state_.adverse_selection_ratio; }
    
    // Position sizing optimization
    uint64_t calculateOptimalQuantity(uint64_t price, uint8_t side) const;
    
    // Inventory management
    int64_t getNetPosition() const;
    bool isInventoryRiskAcceptable() const;
};

/**
 * Multi-symbol order book manager
 * Manages multiple order books with shared memory pools
 */
class MultiSymbolOrderBookManager {
private:
    std::unordered_map<uint32_t, std::unique_ptr<HighPerformanceOrderBook>> books_;
    std::shared_ptr<MemoryPool<HighPerformanceOrderBook::Order>> shared_order_pool_;
    
    // Cross-symbol analytics
    struct CrossSymbolStats {
        std::atomic<uint64_t> total_operations{0};
        std::atomic<double> avg_spread_bps{0.0};
        std::atomic<uint64_t> total_volume{0};
    } cross_stats_;

public:
    MultiSymbolOrderBookManager();
    ~MultiSymbolOrderBookManager() = default;
    
    // Book management
    bool addSymbol(uint32_t symbol_id, uint64_t min_price, uint64_t max_price, uint64_t tick_size);
    bool removeSymbol(uint32_t symbol_id);
    HighPerformanceOrderBook* getBook(uint32_t symbol_id);
    
    // Cross-symbol operations
    std::vector<std::pair<uint32_t, double>> getSymbolsBySpread() const;
    double calculateCorrelation(uint32_t symbol1, uint32_t symbol2) const;
    
    // Performance monitoring
    const CrossSymbolStats& getCrossStats() const { return cross_stats_; }
    void optimizeAllBooks();
};

} // namespace hft::data