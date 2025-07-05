#include "dpdk_network_engine.h"
#include <rte_launch.h>
#include <rte_per_lcore.h>
#include <x86intrin.h>
#include <numa.h>
#include <sched.h>

namespace hft::networking {

DPDKNetworkEngine::DPDKNetworkEngine(const NetworkConfig& config)
    : config_(config), mbuf_pool_(nullptr), rx_ring_(nullptr), tx_ring_(nullptr),
      tsc_freq_(rte_get_tsc_hz()) {
    
    // Initialize per-core queues
    rx_queues_.resize(config_.rx_queues);
    tx_queues_.resize(config_.tx_queues);
    
    // Initialize performance counter
    perf_counter_.reset();
}

DPDKNetworkEngine::~DPDKNetworkEngine() {
    shutdown();
}

bool DPDKNetworkEngine::initialize() {
    // Initialize DPDK Environment Abstraction Layer
    int argc = 3;
    const char* argv[] = {"hft_system", "-c", "0xFF", nullptr};
    char* argv_copy[4];
    for (int i = 0; i < argc; ++i) {
        argv_copy[i] = const_cast<char*>(argv[i]);
    }
    argv_copy[argc] = nullptr;
    
    int ret = rte_eal_init(argc, argv_copy);
    if (ret < 0) {
        return false;
    }

    // Check if we have available ports
    uint16_t nb_ports = rte_eth_dev_count_avail();
    if (nb_ports == 0) {
        return false;
    }

    // Create memory pool for packet buffers
    mbuf_pool_ = rte_pktmbuf_pool_create("mbuf_pool", 
                                        config_.mempool_size,
                                        config_.mbuf_cache_size,
                                        0,  // private data size
                                        RTE_MBUF_DEFAULT_BUF_SIZE,
                                        rte_socket_id());
    if (mbuf_pool_ == nullptr) {
        return false;
    }

    // Configure Ethernet port
    struct rte_eth_conf port_conf = {};
    port_conf.rxmode.mq_mode = RTE_ETH_MQ_RX_RSS;
    port_conf.txmode.mq_mode = RTE_ETH_MQ_TX_NONE;
    
    // Enable hardware features for performance
    if (config_.enable_hw_checksum) {
        port_conf.rxmode.offloads |= RTE_ETH_RX_OFFLOAD_CHECKSUM;
        port_conf.txmode.offloads |= RTE_ETH_TX_OFFLOAD_CHECKSUM;
    }
    
    if (config_.enable_hw_timestamp) {
        port_conf.rxmode.offloads |= RTE_ETH_RX_OFFLOAD_TIMESTAMP;
    }

    // RSS (Receive Side Scaling) configuration for multi-queue
    if (config_.enable_rss) {
        port_conf.rx_adv_conf.rss_conf.rss_key = nullptr;
        port_conf.rx_adv_conf.rss_conf.rss_hf = RTE_ETH_RSS_IP | RTE_ETH_RSS_TCP | RTE_ETH_RSS_UDP;
    }

    ret = rte_eth_dev_configure(config_.port_id, config_.rx_queues, 
                               config_.tx_queues, &port_conf);
    if (ret < 0) {
        return false;
    }

    // Setup RX queues
    for (uint16_t q = 0; q < config_.rx_queues; q++) {
        ret = rte_eth_rx_queue_setup(config_.port_id, q, config_.rx_desc,
                                    rte_eth_dev_socket_id(config_.port_id),
                                    nullptr, mbuf_pool_);
        if (ret < 0) {
            return false;
        }
    }

    // Setup TX queues
    for (uint16_t q = 0; q < config_.tx_queues; q++) {
        ret = rte_eth_tx_queue_setup(config_.port_id, q, config_.tx_desc,
                                    rte_eth_dev_socket_id(config_.port_id),
                                    nullptr);
        if (ret < 0) {
            return false;
        }
    }

    // Create lock-free rings for inter-thread communication
    rx_ring_ = rte_ring_create("rx_ring", 8192, rte_socket_id(), 
                              RING_F_SP_ENQ | RING_F_SC_DEQ);
    tx_ring_ = rte_ring_create("tx_ring", 8192, rte_socket_id(),
                              RING_F_SP_ENQ | RING_F_SC_DEQ);
    
    if (!rx_ring_ || !tx_ring_) {
        return false;
    }

    // Start the Ethernet port
    ret = rte_eth_dev_start(config_.port_id);
    if (ret < 0) {
        return false;
    }

    // Enable promiscuous mode for capturing all packets
    ret = rte_eth_promiscuous_enable(config_.port_id);
    if (ret != 0) {
        return false;
    }

    optimizeRXDescriptors();
    optimizeTXDescriptors();
    
    return true;
}

bool DPDKNetworkEngine::start() {
    if (running_.load()) {
        return false;
    }
    
    running_.store(true);
    
    // Launch worker threads on specific CPU cores
    for (uint16_t i = 0; i < config_.rx_queues; ++i) {
        worker_threads_.emplace_back([this, i]() {
            // Pin to specific CPU core
            cpu_set_t cpuset;
            CPU_ZERO(&cpuset);
            CPU_SET(i + 1, &cpuset); // Core 0 usually reserved for OS
            pthread_setaffinity_np(pthread_self(), sizeof(cpuset), &cpuset);
            
            rxWorkerThread(i, i + 1);
        });
    }
    
    for (uint16_t i = 0; i < config_.tx_queues; ++i) {
        worker_threads_.emplace_back([this, i]() {
            // Pin to specific CPU core
            cpu_set_t cpuset;
            CPU_ZERO(&cpuset);
            CPU_SET(i + config_.rx_queues + 1, &cpuset);
            pthread_setaffinity_np(pthread_self(), sizeof(cpuset), &cpuset);
            
            txWorkerThread(i, i + config_.rx_queues + 1);
        });
    }
    
    return true;
}

void DPDKNetworkEngine::stop() {
    running_.store(false);
    
    // Wait for all worker threads to finish
    for (auto& thread : worker_threads_) {
        if (thread.joinable()) {
            thread.join();
        }
    }
    worker_threads_.clear();
}

void DPDKNetworkEngine::shutdown() {
    stop();
    
    if (mbuf_pool_) {
        rte_mempool_free(mbuf_pool_);
        mbuf_pool_ = nullptr;
    }
    
    if (rx_ring_) {
        rte_ring_free(rx_ring_);
        rx_ring_ = nullptr;
    }
    
    if (tx_ring_) {
        rte_ring_free(tx_ring_);
        tx_ring_ = nullptr;
    }
    
    rte_eth_dev_stop(config_.port_id);
    rte_eth_dev_close(config_.port_id);
    rte_eal_cleanup();
}

void DPDKNetworkEngine::rxWorkerThread(unsigned queue_id, unsigned core_id) {
    // Set thread name for debugging
    char thread_name[16];
    snprintf(thread_name, sizeof(thread_name), "rx_worker_%u", queue_id);
    pthread_setname_np(pthread_self(), thread_name);
    
    // Configure for real-time processing
    struct sched_param param;
    param.sched_priority = 99; // Highest RT priority
    pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
    
    struct rte_mbuf* mbufs[64]; // Burst size for efficiency
    const uint16_t burst_size = 64;
    
    while (running_.load(std::memory_order_relaxed)) {
        // Receive packet burst
        uint16_t nb_rx = rte_eth_rx_burst(config_.port_id, queue_id, 
                                         mbufs, burst_size);
        
        if (likely(nb_rx > 0)) {
            stats_.packets_received.fetch_add(nb_rx, std::memory_order_relaxed);
            
            // Prefetch next cache lines for better performance
            prefetchNextPackets(mbufs, nb_rx);
            
            // Process each packet
            for (uint16_t i = 0; i < nb_rx; ++i) {
                MarketDataPacket packet;
                
                // Record hardware timestamp immediately
                packet.timestamp.tsc_cycles = rte_rdtsc();
                packet.timestamp.arrival_time = rte_get_timer_cycles();
                packet.timestamp.queue_id = queue_id;
                packet.timestamp.packet_size = rte_pktmbuf_pkt_len(mbufs[i]);
                
                // Parse packet (optimized inline function)
                if (likely(parseMarketDataPacket(mbufs[i], packet))) {
                    // Extract hardware timestamp if available
                    packet.timestamp.nic_timestamp = extractHardwareTimestamp(mbufs[i]);
                    
                    // Update statistics
                    stats_.bytes_received.fetch_add(packet.timestamp.packet_size, 
                                                   std::memory_order_relaxed);
                    
                    // Call registered handler
                    if (market_data_handler_) {
                        market_data_handler_(packet);
                    }
                } else {
                    stats_.processing_errors.fetch_add(1, std::memory_order_relaxed);
                }
                
                // Free packet buffer
                rte_pktmbuf_free(mbufs[i]);
            }
        }
        
        // Yield CPU briefly to prevent spinning at 100%
        if (unlikely(nb_rx == 0)) {
            _mm_pause(); // x86 pause instruction
        }
    }
}

void DPDKNetworkEngine::txWorkerThread(unsigned queue_id, unsigned core_id) {
    // Set thread name for debugging
    char thread_name[16];
    snprintf(thread_name, sizeof(thread_name), "tx_worker_%u", queue_id);
    pthread_setname_np(pthread_self(), thread_name);
    
    // Configure for real-time processing
    struct sched_param param;
    param.sched_priority = 99; // Highest RT priority
    pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
    
    struct rte_mbuf* mbufs[64];
    const uint16_t burst_size = 64;
    
    while (running_.load(std::memory_order_relaxed)) {
        // Check for outgoing packets in lock-free queue
        OrderPacket orders[burst_size];
        size_t nb_orders = 0;
        
        // Dequeue orders from lock-free queue
        while (nb_orders < burst_size && !tx_queues_[queue_id].empty()) {
            if (tx_queues_[queue_id].pop(orders[nb_orders])) {
                ++nb_orders;
            }
        }
        
        if (likely(nb_orders > 0)) {
            // Allocate mbufs for transmission
            if (rte_pktmbuf_alloc_bulk(mbuf_pool_, mbufs, nb_orders) == 0) {
                // Build packets
                for (size_t i = 0; i < nb_orders; ++i) {
                    // Add hardware timestamp
                    orders[i].timestamp.tsc_cycles = rte_rdtsc();
                    
                    // Build packet data (protocol-specific)
                    char* packet_data = rte_pktmbuf_append(mbufs[i], 
                                                          sizeof(OrderPacket));
                    if (packet_data) {
                        memcpy(packet_data, &orders[i], sizeof(OrderPacket));
                    }
                }
                
                // Transmit packet burst
                uint16_t nb_tx = rte_eth_tx_burst(config_.port_id, queue_id,
                                                 mbufs, nb_orders);
                
                stats_.packets_transmitted.fetch_add(nb_tx, std::memory_order_relaxed);
                
                // Free any unsent packets
                if (unlikely(nb_tx < nb_orders)) {
                    for (uint16_t i = nb_tx; i < nb_orders; ++i) {
                        rte_pktmbuf_free(mbufs[i]);
                    }
                    stats_.dropped_packets.fetch_add(nb_orders - nb_tx, 
                                                    std::memory_order_relaxed);
                }
            }
        }
        
        // Yield CPU briefly if no packets to send
        if (unlikely(nb_orders == 0)) {
            _mm_pause();
        }
    }
}

__forceinline bool DPDKNetworkEngine::parseMarketDataPacket(struct rte_mbuf* mbuf, 
                                                           MarketDataPacket& packet) {
    // Get packet data pointer
    char* packet_data = rte_pktmbuf_mtod(mbuf, char*);
    uint32_t packet_len = rte_pktmbuf_pkt_len(mbuf);
    
    // Validate minimum packet size
    if (unlikely(packet_len < sizeof(struct rte_ether_hdr) + 
                 sizeof(struct rte_ipv4_hdr) + sizeof(struct rte_udp_hdr))) {
        return false;
    }
    
    // Parse Ethernet header
    struct rte_ether_hdr* eth_hdr = reinterpret_cast<struct rte_ether_hdr*>(packet_data);
    if (unlikely(rte_be_to_cpu_16(eth_hdr->ether_type) != RTE_ETHER_TYPE_IPV4)) {
        return false;
    }
    
    // Parse IP header
    struct rte_ipv4_hdr* ip_hdr = reinterpret_cast<struct rte_ipv4_hdr*>(
        packet_data + sizeof(struct rte_ether_hdr));
    
    if (unlikely(ip_hdr->next_proto_id != IPPROTO_UDP)) {
        return false;
    }
    
    // Parse UDP header
    struct rte_udp_hdr* udp_hdr = reinterpret_cast<struct rte_udp_hdr*>(
        packet_data + sizeof(struct rte_ether_hdr) + sizeof(struct rte_ipv4_hdr));
    
    // Extract payload
    char* payload = packet_data + sizeof(struct rte_ether_hdr) + 
                   sizeof(struct rte_ipv4_hdr) + sizeof(struct rte_udp_hdr);
    
    uint32_t payload_len = packet_len - (sizeof(struct rte_ether_hdr) + 
                          sizeof(struct rte_ipv4_hdr) + sizeof(struct rte_udp_hdr));
    
    // SIMD-optimized packet validation
    if (unlikely(!validatePacketSIMD(payload, payload_len))) {
        return false;
    }
    
    // Store raw data for compliance (first 32 bytes)
    size_t copy_size = std::min(static_cast<size_t>(32), static_cast<size_t>(payload_len));
    memcpy(packet.raw_data, payload, copy_size);
    
    // Protocol-specific parsing would go here
    // For now, use generic parsing
    if (payload_len >= 20) {
        // Example binary protocol parsing
        packet.sequence_number = *reinterpret_cast<uint32_t*>(payload);
        packet.symbol_id = *reinterpret_cast<uint16_t*>(payload + 4);
        packet.message_type = *reinterpret_cast<uint16_t*>(payload + 6);
        packet.price = *reinterpret_cast<uint64_t*>(payload + 8);
        packet.quantity = *reinterpret_cast<uint64_t*>(payload + 16);
        
        // Convert network byte order if needed
        packet.sequence_number = rte_be_to_cpu_32(packet.sequence_number);
        packet.symbol_id = rte_be_to_cpu_16(packet.symbol_id);
        packet.message_type = rte_be_to_cpu_16(packet.message_type);
        packet.price = rte_be_to_cpu_64(packet.price);
        packet.quantity = rte_be_to_cpu_64(packet.quantity);
    }
    
    return true;
}

__forceinline uint64_t DPDKNetworkEngine::extractHardwareTimestamp(struct rte_mbuf* mbuf) {
    // Check if hardware timestamping is available
    if (mbuf->ol_flags & RTE_MBUF_F_RX_TIMESTAMP) {
        return mbuf->timestamp;
    }
    
    // Fallback to software timestamp
    return rte_rdtsc();
}

__forceinline bool DPDKNetworkEngine::validatePacketSIMD(const void* packet_data, size_t size) {
    // Use SIMD instructions for fast packet validation
    // This is a simplified example - real validation would be protocol-specific
    
    const uint8_t* data = static_cast<const uint8_t*>(packet_data);
    
    // Ensure minimum size
    if (size < 16) {
        return false;
    }
    
    // Load 16 bytes into SIMD register
    __m128i packet_chunk = _mm_loadu_si128(reinterpret_cast<const __m128i*>(data));
    
    // Check for null bytes (simple validation example)
    __m128i zero = _mm_setzero_si128();
    __m128i cmp = _mm_cmpeq_epi8(packet_chunk, zero);
    
    // If all bytes are zero, packet is likely invalid
    int mask = _mm_movemask_epi8(cmp);
    
    return mask != 0xFFFF; // Not all zeros
}

bool DPDKNetworkEngine::sendOrder(const OrderPacket& order) {
    // Find least loaded TX queue
    size_t min_queue_size = SIZE_MAX;
    size_t best_queue = 0;
    
    for (size_t i = 0; i < tx_queues_.size(); ++i) {
        size_t queue_size = tx_queues_[i].size();
        if (queue_size < min_queue_size) {
            min_queue_size = queue_size;
            best_queue = i;
        }
    }
    
    // Try to enqueue order
    return tx_queues_[best_queue].push(order);
}

void DPDKNetworkEngine::prefetchNextPackets(struct rte_mbuf** mbufs, uint16_t count) {
    // Prefetch packet data into CPU cache for faster processing
    for (uint16_t i = 0; i < count; ++i) {
        char* packet_data = rte_pktmbuf_mtod(mbufs[i], char*);
        __builtin_prefetch(packet_data, 0, 3); // Prefetch for read, high temporal locality
        
        // Prefetch next cache line as well
        __builtin_prefetch(packet_data + 64, 0, 3);
    }
}

void DPDKNetworkEngine::optimizeRXDescriptors() {
    // Platform-specific RX optimizations
    struct rte_eth_rxconf rxconf;
    rte_eth_dev_default_rx_conf_get(config_.port_id, &rxconf);
    
    // Enable scatter-gather for jumbo frames
    rxconf.offloads |= RTE_ETH_RX_OFFLOAD_SCATTER;
    
    // Optimize descriptor thresholds
    rxconf.rx_thresh.pthresh = 8;   // Prefetch threshold
    rxconf.rx_thresh.hthresh = 8;   // Host threshold  
    rxconf.rx_thresh.wthresh = 4;   // Write-back threshold
    
    // Enable free threshold
    rxconf.rx_free_thresh = 32;
}

void DPDKNetworkEngine::optimizeTXDescriptors() {
    // Platform-specific TX optimizations
    struct rte_eth_txconf txconf;
    rte_eth_dev_default_tx_conf_get(config_.port_id, &txconf);
    
    // Optimize descriptor thresholds
    txconf.tx_thresh.pthresh = 36;  // Prefetch threshold
    txconf.tx_thresh.hthresh = 0;   // Host threshold
    txconf.tx_thresh.wthresh = 0;   // Write-back threshold
    
    // Enable free threshold
    txconf.tx_free_thresh = 32;
}

double DPDKNetworkEngine::getAverageLatencyMicros() const {
    uint64_t total_packets = stats_.packets_received.load();
    if (total_packets == 0) {
        return 0.0;
    }
    
    uint64_t total_latency = stats_.total_latency_ns.load();
    return static_cast<double>(total_latency) / total_packets / 1000.0; // Convert to microseconds
}

void DPDKNetworkEngine::resetStats() {
    stats_.packets_received.store(0);
    stats_.packets_transmitted.store(0);
    stats_.bytes_received.store(0);
    stats_.bytes_transmitted.store(0);
    stats_.dropped_packets.store(0);
    stats_.processing_errors.store(0);
    stats_.min_latency_ns.store(UINT64_MAX);
    stats_.max_latency_ns.store(0);
    stats_.total_latency_ns.store(0);
}

} // namespace hft::networking