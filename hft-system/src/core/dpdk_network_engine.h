#pragma once

#include <rte_config.h>
#include <rte_common.h>
#include <rte_eal.h>
#include <rte_ethdev.h>
#include <rte_mempool.h>
#include <rte_mbuf.h>
#include <rte_ether.h>
#include <rte_ip.h>
#include <rte_tcp.h>
#include <rte_udp.h>
#include <rte_cycles.h>
#include <rte_lcore.h>
#include <rte_ring.h>

#include <atomic>
#include <memory>
#include <vector>
#include <functional>
#include <immintrin.h>

#include "../utils/performance_utils.h"
#include "../utils/lock_free_queue.h"

namespace hft::networking {

/**
 * Ultra-low latency DPDK-based networking engine
 * Provides kernel bypass with zero-copy packet processing
 * Target: <5μs packet processing latency
 */
class DPDKNetworkEngine {
public:
    // Hardware timestamp structure for precision timing
    struct alignas(64) HardwareTimestamp {
        uint64_t tsc_cycles;          // CPU timestamp counter
        uint64_t nic_timestamp;       // Network card timestamp
        uint64_t arrival_time;        // Software receive time
        uint32_t queue_id;            // RX queue identifier
        uint32_t packet_size;         // Total packet size
    };

    // Market data packet structure optimized for cache alignment
    struct alignas(64) MarketDataPacket {
        HardwareTimestamp timestamp;
        uint32_t sequence_number;
        uint16_t symbol_id;           // Pre-mapped symbol identifier
        uint16_t message_type;        // Order/Trade/Quote etc.
        uint64_t price;               // Fixed-point price (6 decimal places)
        uint64_t quantity;            // Share quantity
        uint8_t side;                 // Buy/Sell
        uint8_t flags;                // Additional flags
        uint16_t padding;             // Maintain alignment
        char raw_data[32];            // Original packet data for compliance
    };

    // Order transmission packet structure
    struct alignas(64) OrderPacket {
        HardwareTimestamp timestamp;
        uint64_t order_id;
        uint32_t symbol_id;
        uint64_t price;
        uint64_t quantity;
        uint8_t side;
        uint8_t order_type;
        uint16_t venue_id;
        char client_order_id[16];
    };

    // Configuration for DPDK networking
    struct NetworkConfig {
        uint16_t port_id = 0;
        uint16_t rx_queues = 8;       // Multiple queues for parallel processing
        uint16_t tx_queues = 8;
        uint16_t rx_desc = 1024;      // RX descriptor ring size
        uint16_t tx_desc = 1024;      // TX descriptor ring size
        uint32_t mempool_size = 8192; // Packet buffer pool size
        uint16_t mbuf_cache_size = 256;
        uint16_t mtu = 1500;
        bool enable_rss = true;       // Receive Side Scaling
        bool enable_hw_checksum = true;
        bool enable_hw_timestamp = true;
        uint64_t cpu_mask = 0xFF;     // CPU cores to use
    };

    using PacketHandler = std::function<void(const MarketDataPacket&)>;
    using OrderConfirmHandler = std::function<void(const OrderPacket&)>;

private:
    NetworkConfig config_;
    struct rte_mempool* mbuf_pool_;
    struct rte_ring* rx_ring_;
    struct rte_ring* tx_ring_;
    
    // Per-core processing queues (lock-free)
    std::vector<LockFreeQueue<MarketDataPacket>> rx_queues_;
    std::vector<LockFreeQueue<OrderPacket>> tx_queues_;
    
    // Statistics counters (cache-aligned)
    struct alignas(64) NetworkStats {
        std::atomic<uint64_t> packets_received{0};
        std::atomic<uint64_t> packets_transmitted{0};
        std::atomic<uint64_t> bytes_received{0};
        std::atomic<uint64_t> bytes_transmitted{0};
        std::atomic<uint64_t> dropped_packets{0};
        std::atomic<uint64_t> processing_errors{0};
        std::atomic<uint64_t> min_latency_ns{UINT64_MAX};
        std::atomic<uint64_t> max_latency_ns{0};
        std::atomic<uint64_t> total_latency_ns{0};
    } stats_;

    // Performance tracking
    PerformanceCounter perf_counter_;
    uint64_t tsc_freq_;
    
    // Packet handlers
    PacketHandler market_data_handler_;
    OrderConfirmHandler order_confirm_handler_;
    
    // Worker threads for packet processing
    std::vector<std::thread> worker_threads_;
    std::atomic<bool> running_{false};

public:
    explicit DPDKNetworkEngine(const NetworkConfig& config);
    ~DPDKNetworkEngine();

    // Core lifecycle
    bool initialize();
    bool start();
    void stop();
    void shutdown();

    // Packet handlers registration
    void setMarketDataHandler(PacketHandler handler) { 
        market_data_handler_ = std::move(handler); 
    }
    
    void setOrderConfirmHandler(OrderConfirmHandler handler) { 
        order_confirm_handler_ = std::move(handler); 
    }

    // Ultra-fast packet transmission (target: <10μs)
    bool sendOrder(const OrderPacket& order);
    bool sendOrderBatch(const std::vector<OrderPacket>& orders);

    // Performance monitoring
    const NetworkStats& getStats() const { return stats_; }
    double getAverageLatencyMicros() const;
    void resetStats();

    // Hardware optimization
    void bindToCore(unsigned core_id);
    void enableHugePages();
    void optimizeCache();

private:
    // Core packet processing functions
    void rxWorkerThread(unsigned queue_id, unsigned core_id);
    void txWorkerThread(unsigned queue_id, unsigned core_id);
    
    // Optimized packet parsing (inline assembly where needed)
    __forceinline bool parseMarketDataPacket(struct rte_mbuf* mbuf, 
                                           MarketDataPacket& packet);
    
    // Hardware timestamp extraction
    __forceinline uint64_t extractHardwareTimestamp(struct rte_mbuf* mbuf);
    
    // SIMD-optimized packet validation
    __forceinline bool validatePacketSIMD(const void* packet_data, size_t size);
    
    // Zero-copy packet forwarding
    void forwardPacketZeroCopy(struct rte_mbuf* mbuf, uint16_t dst_queue);
    
    // Performance optimization helpers
    void prefetchNextPackets(struct rte_mbuf** mbufs, uint16_t count);
    void optimizeRXDescriptors();
    void optimizeTXDescriptors();
    
    // Error handling and recovery
    void handlePortError(uint16_t port_id);
    void recoverFromDroppedPackets();
};

/**
 * Specialized market data feed handler with protocol-specific optimizations
 */
class MarketDataFeedHandler {
public:
    enum class FeedType {
        NASDAQ_ITCH,
        NYSE_PILLAR,
        CME_MDP3,
        ICE_IMPACT,
        CUSTOM_BINARY
    };

    struct FeedConfig {
        FeedType type;
        std::string multicast_address;
        uint16_t port;
        uint32_t expected_rate;  // packets per second
        bool enable_sequence_check = true;
        bool enable_gap_detection = true;
    };

private:
    FeedType feed_type_;
    DPDKNetworkEngine* network_engine_;
    
    // Protocol-specific parsers (hand-optimized)
    void parseNASDAQITCH(const void* data, size_t size, 
                        DPDKNetworkEngine::MarketDataPacket& packet);
    void parseNYSEPillar(const void* data, size_t size,
                        DPDKNetworkEngine::MarketDataPacket& packet);
    void parseCMEMDP3(const void* data, size_t size,
                     DPDKNetworkEngine::MarketDataPacket& packet);

public:
    explicit MarketDataFeedHandler(const FeedConfig& config,
                                  DPDKNetworkEngine* engine);
    
    bool initialize();
    void processPacket(const DPDKNetworkEngine::MarketDataPacket& packet);
    
    // Protocol-specific optimizations
    void enableJumboFrames();
    void optimizeForFeedType();
};

/**
 * Order transmission engine optimized for specific venues
 */
class OrderTransmissionEngine {
public:
    enum class VenueProtocol {
        FIX_42,
        FIX_44,
        FIX_50,
        OUCH_40,
        NATIVE_BINARY
    };

    struct VenueConfig {
        VenueProtocol protocol;
        std::string host;
        uint16_t port;
        uint32_t heartbeat_interval_ms = 30000;
        bool enable_nagle = false;    // Disable for low latency
        bool enable_tcp_nodelay = true;
    };

private:
    VenueProtocol protocol_;
    DPDKNetworkEngine* network_engine_;
    
    // Pre-allocated message buffers for zero allocation
    std::array<char, 1024> message_buffer_;
    
    // FIX message templates (pre-compiled)
    std::unordered_map<std::string, std::string> fix_templates_;

public:
    explicit OrderTransmissionEngine(const VenueConfig& config,
                                   DPDKNetworkEngine* engine);
    
    // Ultra-fast order transmission
    bool sendNewOrderSingle(uint64_t order_id, uint32_t symbol_id,
                          uint64_t price, uint64_t quantity, char side);
    
    bool sendCancelOrder(uint64_t order_id);
    bool sendReplaceOrder(uint64_t order_id, uint64_t new_price, 
                         uint64_t new_quantity);
    
    // Batch operations for efficiency
    bool sendOrderBatch(const std::vector<DPDKNetworkEngine::OrderPacket>& orders);
    
private:
    // Protocol-specific encoding (hand-optimized)
    size_t encodeFIXMessage(const DPDKNetworkEngine::OrderPacket& order,
                          char* buffer, size_t buffer_size);
    size_t encodeOUCHMessage(const DPDKNetworkEngine::OrderPacket& order,
                           char* buffer, size_t buffer_size);
};

} // namespace hft::networking