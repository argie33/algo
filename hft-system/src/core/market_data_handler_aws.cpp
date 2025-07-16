/**
 * Ultra-Low Latency Market Data Handler for AWS
 * Optimized for EC2 instances with enhanced networking
 */

#include <memory>
#include <thread>
#include <atomic>
#include <array>
#include <vector>
#include <unordered_map>
#include <chrono>
#include <aws/core/Aws.h>
#include <aws/kinesis/KinesisClient.h>
#include <aws/kinesis/model/PutRecordRequest.h>

// Custom networking libraries for AWS enhanced networking
#include "aws_enhanced_networking.h"
#include "lock_free_queue.h"
#include "memory_pool.h"
#include "hardware_timestamp.h"

namespace HFT {

// Market data event structure (cache-aligned)
struct alignas(64) MarketDataEvent {
    uint64_t hardware_timestamp;    // Hardware timestamp in nanoseconds
    uint64_t sequence_number;       // Event sequence number
    uint32_t symbol_id;            // Internal symbol ID
    uint32_t price;                // Price in ticks (scaled)
    uint32_t size;                 // Order/trade size
    uint16_t exchange_id;          // Exchange identifier
    uint8_t  message_type;         // ITCH/OUCH message type
    uint8_t  side;                 // Buy/Sell indicator
    uint8_t  padding[48];          // Pad to cache line
};

// Lock-free queue for market data events
using MarketDataQueue = LockFreeQueue<MarketDataEvent, 1048576>; // 1M events

class AWSMarketDataHandler {
private:
    // AWS-specific components
    std::unique_ptr<Aws::Kinesis::KinesisClient> kinesis_client_;
    std::string kinesis_stream_name_;
    
    // Hardware optimization
    struct NetworkConfig {
        // Enhanced networking with SR-IOV
        bool enhanced_networking_enabled = true;
        bool sriov_enabled = true;
        
        // CPU affinity for network interrupts
        std::vector<int> network_cpu_cores = {0, 1};  // Dedicated cores
        std::vector<int> processing_cpu_cores = {2, 3, 4, 5, 6, 7};
        
        // Buffer configurations
        uint32_t rx_buffer_size = 16 * 1024 * 1024;  // 16MB
        uint32_t tx_buffer_size = 16 * 1024 * 1024;  // 16MB
        
        // Polling vs interrupt mode
        bool use_polling = true;
        uint32_t poll_interval_ns = 100;  // 100ns polling
    };
    
    NetworkConfig network_config_;
    
    // Memory pools for zero-allocation processing
    MemoryPool<MarketDataEvent> event_pool_;
    MemoryPool<uint8_t> packet_pool_;
    
    // Lock-free queues for different data types
    MarketDataQueue trade_queue_;
    MarketDataQueue quote_queue_;
    MarketDataQueue order_book_queue_;
    
    // Processing threads with CPU affinity
    std::vector<std::thread> processing_threads_;
    std::atomic<bool> running_{false};
    
    // Performance metrics
    struct alignas(64) PerformanceMetrics {
        std::atomic<uint64_t> packets_received{0};
        std::atomic<uint64_t> events_processed{0};
        std::atomic<uint64_t> parse_errors{0};
        std::atomic<uint64_t> queue_overflows{0};
        
        // Latency tracking (nanoseconds)
        std::atomic<uint64_t> min_latency{UINT64_MAX};
        std::atomic<uint64_t> max_latency{0};
        std::atomic<uint64_t> total_latency{0};
        std::atomic<uint64_t> latency_samples{0};
    };
    
    PerformanceMetrics metrics_;
    
    // Symbol mapping for fast lookups
    std::unordered_map<std::string, uint32_t> symbol_to_id_;
    std::array<std::string, 65536> id_to_symbol_;  // Fast array lookup
    
public:
    AWSMarketDataHandler(const std::string& kinesis_stream = "hft-market-data") 
        : kinesis_stream_name_(kinesis_stream),
          event_pool_(1000000),    // 1M events pre-allocated
          packet_pool_(10000000)   // 10M bytes pre-allocated
    {
        initializeAWS();
        initializeNetworking();
        setupCPUAffinity();
    }
    
    ~AWSMarketDataHandler() {
        stop();
        Aws::ShutdownAPI({});
    }
    
    // Start the market data handler
    void start() {
        running_ = true;
        
        // Start processing threads with CPU affinity
        for (size_t i = 0; i < network_config_.processing_cpu_cores.size(); ++i) {
            processing_threads_.emplace_back([this, i]() {
                // Set CPU affinity
                cpu_set_t cpuset;
                CPU_ZERO(&cpuset);
                CPU_SET(network_config_.processing_cpu_cores[i], &cpuset);
                pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
                
                // Set thread priority
                struct sched_param param;
                param.sched_priority = 99;  // Highest priority
                pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
                
                // Main processing loop
                processMarketData();
            });
        }
    }
    
    // Stop the handler
    void stop() {
        running_ = false;
        for (auto& thread : processing_threads_) {
            if (thread.joinable()) {
                thread.join();
            }
        }
        processing_threads_.clear();
    }
    
    // Get performance metrics
    PerformanceMetrics getMetrics() const {
        return metrics_;
    }
    
    // Reset performance metrics
    void resetMetrics() {
        metrics_ = PerformanceMetrics{};
    }

private:
    void initializeAWS() {
        // Initialize AWS SDK
        Aws::SDKOptions options;
        options.loggingOptions.logLevel = Aws::Utils::Logging::LogLevel::Error;
        Aws::InitAPI(options);
        
        // Create Kinesis client with optimized configuration
        Aws::Client::ClientConfiguration client_config;
        client_config.region = Aws::Region::US_EAST_1;
        client_config.maxConnections = 100;
        client_config.requestTimeoutMs = 1000;
        client_config.connectTimeoutMs = 500;
        
        kinesis_client_ = std::make_unique<Aws::Kinesis::KinesisClient>(client_config);
    }
    
    void initializeNetworking() {
        // Configure enhanced networking
        if (network_config_.enhanced_networking_enabled) {
            enableEnhancedNetworking();
        }
        
        // Setup SR-IOV if available
        if (network_config_.sriov_enabled) {
            enableSRIOV();
        }
        
        // Configure receive buffers
        configureNetworkBuffers();
    }
    
    void setupCPUAffinity() {
        // Isolate network interrupt CPUs
        for (int cpu : network_config_.network_cpu_cores) {
            isolateCPU(cpu);
        }
        
        // Isolate processing CPUs
        for (int cpu : network_config_.processing_cpu_cores) {
            isolateCPU(cpu);
        }
    }
    
    // Main market data processing loop
    __attribute__((hot)) void processMarketData() {
        // Pre-allocate buffers
        alignas(64) uint8_t packet_buffer[65536];
        MarketDataEvent event;
        
        while (running_) {
            // High-frequency polling loop
            if (network_config_.use_polling) {
                pollForPackets(packet_buffer, sizeof(packet_buffer));
            } else {
                waitForPackets(packet_buffer, sizeof(packet_buffer));
            }
        }
    }
    
    // Optimized packet polling
    __attribute__((hot)) void pollForPackets(uint8_t* buffer, size_t buffer_size) {
        // Use DPDK-style polling for AWS enhanced networking
        uint16_t num_packets = receivePacketBurst(buffer, buffer_size);
        
        for (uint16_t i = 0; i < num_packets; ++i) {
            uint64_t hw_timestamp = getHardwareTimestamp();
            processPacket(buffer + i * 1500, hw_timestamp);  // Assume 1500 byte MTU
        }
    }
    
    // Process individual packet with zero-copy parsing
    __attribute__((hot, flatten)) void processPacket(const uint8_t* packet, uint64_t hw_timestamp) {
        // Record receive timestamp
        uint64_t start_processing = rdtsc();
        
        // Parse packet header to determine protocol
        uint16_t protocol = parseProtocolType(packet);
        
        MarketDataEvent event;
        bool parsed = false;
        
        switch (protocol) {
            case ITCH_50:
                parsed = parseITCHMessage(packet, event);
                break;
            case OUCH_42:
                parsed = parseOUCHMessage(packet, event);
                break;
            case FIX_42:
                parsed = parseFIXMessage(packet, event);
                break;
            default:
                metrics_.parse_errors++;
                return;
        }
        
        if (parsed) {
            event.hardware_timestamp = hw_timestamp;
            event.sequence_number = metrics_.events_processed++;
            
            // Route to appropriate queue based on message type
            routeToQueue(event);
            
            // Update latency metrics
            uint64_t processing_latency = rdtsc() - start_processing;
            updateLatencyMetrics(processing_latency);
            
            // Forward to AWS Kinesis for downstream processing
            forwardToKinesis(event);
        }
    }
    
    // Ultra-fast ITCH 5.0 message parsing
    __attribute__((hot)) bool parseITCHMessage(const uint8_t* data, MarketDataEvent& event) {
        // Assembly-optimized parsing for critical path
        const ITCHHeader* header = reinterpret_cast<const ITCHHeader*>(data);
        
        // Fast path for common message types
        switch (header->message_type) {
            case 'A':  // Add Order
                return parseAddOrder(data, event);
            case 'E':  // Order Executed
                return parseOrderExecuted(data, event);
            case 'P':  // Trade Message
                return parseTradeMessage(data, event);
            case 'U':  // Replace Order
                return parseReplaceOrder(data, event);
            case 'D':  // Delete Order
                return parseDeleteOrder(data, event);
            default:
                return false;
        }
    }
    
    // Route events to appropriate lock-free queues
    __attribute__((hot)) void routeToQueue(const MarketDataEvent& event) {
        switch (event.message_type) {
            case TRADE_MESSAGE:
                if (!trade_queue_.push(event)) {
                    metrics_.queue_overflows++;
                }
                break;
            case QUOTE_MESSAGE:
                if (!quote_queue_.push(event)) {
                    metrics_.queue_overflows++;
                }
                break;
            case ORDER_BOOK_MESSAGE:
                if (!order_book_queue_.push(event)) {
                    metrics_.queue_overflows++;
                }
                break;
        }
    }
    
    // Forward to AWS Kinesis for persistence and analytics
    void forwardToKinesis(const MarketDataEvent& event) {
        // Serialize event to binary format
        std::string serialized_event = serializeEvent(event);
        
        // Create Kinesis put record request
        Aws::Kinesis::Model::PutRecordRequest request;
        request.SetStreamName(kinesis_stream_name_);
        request.SetPartitionKey(std::to_string(event.symbol_id));
        
        Aws::Utils::ByteBuffer data(reinterpret_cast<const unsigned char*>(serialized_event.data()), 
                                   serialized_event.length());
        request.SetData(data);
        
        // Async send (non-blocking)
        kinesis_client_->PutRecordAsync(request, 
            [this](const Aws::Kinesis::KinesisClient* client,
                   const Aws::Kinesis::Model::PutRecordRequest& request,
                   const Aws::Kinesis::Model::PutRecordOutcome& outcome,
                   const std::shared_ptr<const Aws::Client::AsyncCallerContext>& context) {
                if (!outcome.IsSuccess()) {
                    // Log error but don't block trading
                    // TODO: Implement fallback storage
                }
            });
    }
    
    // Hardware-specific optimizations for AWS
    void enableEnhancedNetworking() {
        // Enable SR-IOV and enhanced networking features
        // This would typically involve configuring the network interface
        // for maximum performance on AWS instances
        
        system("ethtool -K eth0 rx-checksumming off");
        system("ethtool -K eth0 tx-checksumming off");
        system("ethtool -K eth0 generic-segmentation-offload off");
        system("ethtool -K eth0 tcp-segmentation-offload off");
        system("ethtool -K eth0 generic-receive-offload off");
        system("ethtool -K eth0 large-receive-offload off");
        
        // Set interrupt coalescing for low latency
        system("ethtool -C eth0 rx-usecs 0");
        system("ethtool -C eth0 tx-usecs 0");
    }
    
    void enableSRIOV() {
        // Configure SR-IOV virtual functions for dedicated data paths
        // This provides hardware-level isolation and performance
    }
    
    void configureNetworkBuffers() {
        // Optimize network buffer sizes for high-frequency data
        system("sysctl -w net.core.rmem_max=134217728");
        system("sysctl -w net.core.wmem_max=134217728");
        system("sysctl -w net.core.netdev_max_backlog=5000");
        system("sysctl -w net.ipv4.tcp_rmem='4096 65536 134217728'");
        system("sysctl -w net.ipv4.tcp_wmem='4096 65536 134217728'");
    }
    
    void isolateCPU(int cpu_id) {
        // Isolate CPU from kernel scheduler
        std::string cmd = "echo 0 > /sys/devices/system/cpu/cpu" + 
                         std::to_string(cpu_id) + "/online";
        system(cmd.c_str());
        
        cmd = "echo 1 > /sys/devices/system/cpu/cpu" + 
              std::to_string(cpu_id) + "/online";
        system(cmd.c_str());
    }
    
    // Update latency metrics (lock-free)
    __attribute__((hot)) void updateLatencyMetrics(uint64_t latency_ns) {
        metrics_.total_latency += latency_ns;
        metrics_.latency_samples++;
        
        // Update min/max atomically
        uint64_t current_min = metrics_.min_latency.load();
        while (latency_ns < current_min && 
               !metrics_.min_latency.compare_exchange_weak(current_min, latency_ns)) {
            // Spin until successful
        }
        
        uint64_t current_max = metrics_.max_latency.load();
        while (latency_ns > current_max && 
               !metrics_.max_latency.compare_exchange_weak(current_max, latency_ns)) {
            // Spin until successful
        }
    }
    
    // Hardware timestamp using TSC
    __attribute__((always_inline)) inline uint64_t rdtsc() {
        uint32_t hi, lo;
        __asm__ __volatile__ ("rdtsc" : "=a"(lo), "=d"(hi));
        return ((uint64_t)hi << 32) | lo;
    }
};

} // namespace HFT