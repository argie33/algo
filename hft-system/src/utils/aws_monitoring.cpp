/**
 * AWS-Optimized Monitoring and Observability Framework for HFT
 * Ultra-low latency metrics collection with CloudWatch integration
 */

#include <memory>
#include <thread>
#include <atomic>
#include <chrono>
#include <vector>
#include <unordered_map>
#include <aws/core/Aws.h>
#include <aws/cloudwatch/CloudWatchClient.h>
#include <aws/cloudwatch/model/PutMetricDataRequest.h>
#include <aws/cloudwatch/model/MetricDatum.h>
#include <aws/cloudwatch/model/Dimension.h>
#include <aws/logs/CloudWatchLogsClient.h>
#include <aws/logs/model/PutLogEventsRequest.h>

#include "lock_free_queue.h"
#include "memory_pool.h"

namespace HFT {

// Metric data structure optimized for cache efficiency
struct alignas(64) MetricData {
    char metric_name[64];
    char namespace_name[32];
    char unit[16];
    double value;
    uint64_t timestamp_ns;
    char dimensions[256];  // JSON string for dimensions
    uint8_t padding[8];
};

// Log entry structure
struct alignas(64) LogEntry {
    char message[512];
    char level[16];      // DEBUG, INFO, WARN, ERROR, CRITICAL
    uint64_t timestamp_ns;
    char thread_id[32];
    char component[64];
    uint8_t padding[8];
};

class AWSMonitoring {
private:
    // AWS clients
    std::unique_ptr<Aws::CloudWatch::CloudWatchClient> cloudwatch_client_;
    std::unique_ptr<Aws::CloudWatchLogs::CloudWatchLogsClient> logs_client_;
    
    // Lock-free queues for async processing
    LockFreeQueue<MetricData, 65536> metrics_queue_;
    LockFreeQueue<LogEntry, 65536> logs_queue_;
    
    // Memory pools
    MemoryPool<MetricData> metrics_pool_;
    MemoryPool<LogEntry> logs_pool_;
    
    // Processing threads
    std::vector<std::thread> processing_threads_;
    std::atomic<bool> running_{false};
    
    // Performance metrics for the monitoring system itself
    struct MonitoringMetrics {
        std::atomic<uint64_t> metrics_sent{0};
        std::atomic<uint64_t> metrics_dropped{0};
        std::atomic<uint64_t> logs_sent{0};
        std::atomic<uint64_t> logs_dropped{0};
        std::atomic<uint64_t> aws_api_errors{0};
        std::atomic<uint64_t> avg_send_latency_ns{0};
    };
    
    MonitoringMetrics monitoring_metrics_;
    
    // Configuration
    struct Config {
        std::string cloudwatch_namespace = "HFT/Trading";
        std::string log_group_name = "/aws/ec2/hft";
        std::string log_stream_name = "trading-engine";
        uint32_t batch_size = 20;           // CloudWatch limit is 20 metrics per request
        uint32_t flush_interval_ms = 1000;  // Flush every second
        uint32_t max_retries = 3;
        bool enable_detailed_logging = true;
        
        // CPU affinity for monitoring threads
        std::vector<int> monitoring_cpu_cores = {15};  // Use last core
    };
    
    Config config_;
    
    // Cached dimension sets for performance
    std::unordered_map<std::string, std::vector<Aws::CloudWatch::Model::Dimension>> dimension_cache_;

public:
    AWSMonitoring() 
        : metrics_pool_(100000),
          logs_pool_(100000)
    {
        initializeAWS();
        setupDimensionCache();
    }
    
    ~AWSMonitoring() {
        stop();
    }
    
    // Start monitoring system
    void start() {
        running_ = true;
        
        // Start metrics processing thread
        processing_threads_.emplace_back([this]() {
            setCPUAffinity(config_.monitoring_cpu_cores[0]);
            setThreadPriority(10);  // Lower priority than trading
            processMetrics();
        });
        
        // Start logs processing thread
        processing_threads_.emplace_back([this]() {
            setCPUAffinity(config_.monitoring_cpu_cores[0]);
            setThreadPriority(10);
            processLogs();
        });
        
        // Start health monitoring thread
        processing_threads_.emplace_back([this]() {
            setCPUAffinity(config_.monitoring_cpu_cores[0]);
            setThreadPriority(5);
            monitorSystemHealth();
        });
    }
    
    // Stop monitoring system
    void stop() {
        running_ = false;
        
        // Flush remaining metrics and logs
        flushAll();
        
        // Join threads
        for (auto& thread : processing_threads_) {
            if (thread.joinable()) {
                thread.join();
            }
        }
        processing_threads_.clear();
    }
    
    // High-frequency metric recording (hot path)
    __attribute__((hot)) void recordMetric(
        const char* metric_name,
        double value,
        const char* unit = "Count",
        const char* dimensions = nullptr
    ) {
        MetricData* metric = metrics_pool_.allocate();
        if (!metric) {
            monitoring_metrics_.metrics_dropped++;
            return;
        }
        
        // Fast string copy
        strncpy(metric->metric_name, metric_name, sizeof(metric->metric_name) - 1);
        strncpy(metric->namespace_name, config_.cloudwatch_namespace.c_str(), sizeof(metric->namespace_name) - 1);
        strncpy(metric->unit, unit, sizeof(metric->unit) - 1);
        
        metric->value = value;
        metric->timestamp_ns = rdtsc_to_ns(rdtsc());
        
        if (dimensions) {
            strncpy(metric->dimensions, dimensions, sizeof(metric->dimensions) - 1);
        } else {
            metric->dimensions[0] = '\0';
        }
        
        // Push to queue
        if (!metrics_queue_.push(*metric)) {
            monitoring_metrics_.metrics_dropped++;
            metrics_pool_.deallocate(metric);
        }
    }
    
    // High-frequency latency recording
    __attribute__((hot)) void recordLatency(
        const char* operation,
        uint64_t start_tsc,
        uint64_t end_tsc
    ) {
        uint64_t latency_ns = tsc_to_ns(end_tsc - start_tsc);
        recordMetric(operation, static_cast<double>(latency_ns), "Microseconds");
    }
    
    // Fast logging for hot path
    __attribute__((hot)) void logMessage(
        const char* level,
        const char* component,
        const char* message
    ) {
        if (!config_.enable_detailed_logging && strcmp(level, "ERROR") != 0 && strcmp(level, "CRITICAL") != 0) {
            return;  // Skip non-critical logs in production
        }
        
        LogEntry* entry = logs_pool_.allocate();
        if (!entry) {
            monitoring_metrics_.logs_dropped++;
            return;
        }
        
        strncpy(entry->level, level, sizeof(entry->level) - 1);
        strncpy(entry->component, component, sizeof(entry->component) - 1);
        strncpy(entry->message, message, sizeof(entry->message) - 1);
        entry->timestamp_ns = rdtsc_to_ns(rdtsc());
        
        // Get thread ID
        std::thread::id tid = std::this_thread::get_id();
        snprintf(entry->thread_id, sizeof(entry->thread_id), "%zu", std::hash<std::thread::id>{}(tid));
        
        if (!logs_queue_.push(*entry)) {
            monitoring_metrics_.logs_dropped++;
            logs_pool_.deallocate(entry);
        }
    }
    
    // Convenience logging macros
    void logDebug(const char* component, const char* message) {
        logMessage("DEBUG", component, message);
    }
    
    void logInfo(const char* component, const char* message) {
        logMessage("INFO", component, message);
    }
    
    void logWarning(const char* component, const char* message) {
        logMessage("WARN", component, message);
    }
    
    void logError(const char* component, const char* message) {
        logMessage("ERROR", component, message);
    }
    
    void logCritical(const char* component, const char* message) {
        logMessage("CRITICAL", component, message);
        
        // For critical errors, also send immediate CloudWatch alarm
        recordMetric("CriticalErrors", 1.0, "Count");
    }
    
    // Trading-specific convenience methods
    void recordOrderLatency(uint64_t start_tsc, uint64_t end_tsc) {
        recordLatency("OrderLatency", start_tsc, end_tsc);
    }
    
    void recordSignalLatency(uint64_t start_tsc, uint64_t end_tsc) {
        recordLatency("SignalLatency", start_tsc, end_tsc);
    }
    
    void recordRiskCheckLatency(uint64_t start_tsc, uint64_t end_tsc) {
        recordLatency("RiskCheckLatency", start_tsc, end_tsc);
    }
    
    void recordTradingMetrics(uint64_t signals, uint64_t orders, uint64_t fills, double pnl) {
        recordMetric("SignalsGenerated", static_cast<double>(signals));
        recordMetric("OrdersSent", static_cast<double>(orders));
        recordMetric("OrdersFilled", static_cast<double>(fills));
        recordMetric("RealizedPnL", pnl, "None");
    }
    
    void recordRiskMetrics(double gross_exposure, double net_exposure, double var) {
        recordMetric("GrossExposure", gross_exposure, "None");
        recordMetric("NetExposure", net_exposure, "None");
        recordMetric("PortfolioVaR", var, "None");
    }
    
    // Get monitoring system performance metrics
    MonitoringMetrics getMonitoringMetrics() const {
        return monitoring_metrics_;
    }

private:
    void initializeAWS() {
        Aws::SDKOptions options;
        Aws::InitAPI(options);
        
        // CloudWatch client configuration
        Aws::Client::ClientConfiguration cw_config;
        cw_config.region = Aws::Region::US_EAST_1;
        cw_config.maxConnections = 10;
        cw_config.requestTimeoutMs = 5000;
        cw_config.connectTimeoutMs = 2000;
        
        cloudwatch_client_ = std::make_unique<Aws::CloudWatch::CloudWatchClient>(cw_config);
        
        // CloudWatch Logs client
        logs_client_ = std::make_unique<Aws::CloudWatchLogs::CloudWatchLogsClient>(cw_config);
    }
    
    void setupDimensionCache() {
        // Pre-create common dimension combinations for performance
        
        // Trading engine dimensions
        std::vector<Aws::CloudWatch::Model::Dimension> trading_dims;
        Aws::CloudWatch::Model::Dimension component_dim;
        component_dim.SetName("Component");
        component_dim.SetValue("TradingEngine");
        trading_dims.push_back(component_dim);
        dimension_cache_["trading"] = trading_dims;
        
        // Risk management dimensions
        std::vector<Aws::CloudWatch::Model::Dimension> risk_dims;
        component_dim.SetValue("RiskManager");
        risk_dims.push_back(component_dim);
        dimension_cache_["risk"] = risk_dims;
        
        // Market data dimensions
        std::vector<Aws::CloudWatch::Model::Dimension> data_dims;
        component_dim.SetValue("MarketData");
        data_dims.push_back(component_dim);
        dimension_cache_["market_data"] = data_dims;
    }
    
    // Process metrics in batches
    void processMetrics() {
        std::vector<MetricData> batch;
        batch.reserve(config_.batch_size);
        
        auto last_flush = std::chrono::steady_clock::now();
        
        while (running_) {
            MetricData metric;
            
            // Collect metrics for batching
            while (batch.size() < config_.batch_size && metrics_queue_.pop(metric)) {
                batch.push_back(metric);
            }
            
            // Flush if batch is full or timeout reached
            auto now = std::chrono::steady_clock::now();
            auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(now - last_flush);
            
            if (!batch.empty() && (batch.size() >= config_.batch_size || duration.count() >= config_.flush_interval_ms)) {
                sendMetricsBatch(batch);
                batch.clear();
                last_flush = now;
            }
            
            // Small sleep to prevent busy waiting
            if (batch.empty()) {
                std::this_thread::sleep_for(std::chrono::microseconds(100));
            }
        }
        
        // Final flush
        if (!batch.empty()) {
            sendMetricsBatch(batch);
        }
    }
    
    void sendMetricsBatch(const std::vector<MetricData>& batch) {
        uint64_t start_time = rdtsc();
        
        try {
            Aws::CloudWatch::Model::PutMetricDataRequest request;
            request.SetNamespace(config_.cloudwatch_namespace);
            
            std::vector<Aws::CloudWatch::Model::MetricDatum> metric_data;
            metric_data.reserve(batch.size());
            
            for (const auto& metric : batch) {
                Aws::CloudWatch::Model::MetricDatum datum;
                datum.SetMetricName(metric.metric_name);
                datum.SetValue(metric.value);
                datum.SetUnit(Aws::CloudWatch::Model::StandardUnitMapper::GetStandardUnitForName(metric.unit));
                
                // Set timestamp
                auto timestamp = Aws::Utils::DateTime(static_cast<int64_t>(metric.timestamp_ns / 1000000000));
                datum.SetTimestamp(timestamp);
                
                // Add dimensions if present
                if (strlen(metric.dimensions) > 0) {
                    auto dims = parseDimensions(metric.dimensions);
                    datum.SetDimensions(dims);
                }
                
                metric_data.push_back(datum);
            }
            
            request.SetMetricData(metric_data);
            
            // Send asynchronously
            cloudwatch_client_->PutMetricDataAsync(request,
                [this, start_time](const Aws::CloudWatch::CloudWatchClient* client,
                                  const Aws::CloudWatch::Model::PutMetricDataRequest& request,
                                  const Aws::CloudWatch::Model::PutMetricDataOutcome& outcome,
                                  const std::shared_ptr<const Aws::Client::AsyncCallerContext>& context) {
                    uint64_t end_time = rdtsc();
                    uint64_t latency = tsc_to_ns(end_time - start_time);
                    
                    if (outcome.IsSuccess()) {
                        monitoring_metrics_.metrics_sent += request.GetMetricData().size();
                        updateSendLatency(latency);
                    } else {
                        monitoring_metrics_.aws_api_errors++;
                        // Log error but don't block
                    }
                });
                
        } catch (const std::exception& e) {
            monitoring_metrics_.aws_api_errors++;
            // Continue processing, don't block trading
        }
    }
    
    // Process logs in batches
    void processLogs() {
        std::vector<LogEntry> batch;
        batch.reserve(50);  // CloudWatch Logs supports larger batches
        
        auto last_flush = std::chrono::steady_clock::now();
        
        while (running_) {
            LogEntry entry;
            
            while (batch.size() < 50 && logs_queue_.pop(entry)) {
                batch.push_back(entry);
            }
            
            auto now = std::chrono::steady_clock::now();
            auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(now - last_flush);
            
            if (!batch.empty() && (batch.size() >= 50 || duration.count() >= config_.flush_interval_ms)) {
                sendLogsBatch(batch);
                batch.clear();
                last_flush = now;
            }
            
            if (batch.empty()) {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
        }
        
        if (!batch.empty()) {
            sendLogsBatch(batch);
        }
    }
    
    void sendLogsBatch(const std::vector<LogEntry>& batch) {
        try {
            Aws::CloudWatchLogs::Model::PutLogEventsRequest request;
            request.SetLogGroupName(config_.log_group_name);
            request.SetLogStreamName(config_.log_stream_name);
            
            std::vector<Aws::CloudWatchLogs::Model::InputLogEvent> log_events;
            log_events.reserve(batch.size());
            
            for (const auto& entry : batch) {
                Aws::CloudWatchLogs::Model::InputLogEvent event;
                
                // Format log message
                char formatted_message[1024];
                snprintf(formatted_message, sizeof(formatted_message),
                    "[%s] [%s] [%s] %s",
                    entry.level, entry.component, entry.thread_id, entry.message);
                
                event.SetMessage(formatted_message);
                event.SetTimestamp(entry.timestamp_ns / 1000000);  // CloudWatch expects milliseconds
                
                log_events.push_back(event);
            }
            
            request.SetLogEvents(log_events);
            
            // Send asynchronously
            logs_client_->PutLogEventsAsync(request,
                [this](const Aws::CloudWatchLogs::CloudWatchLogsClient* client,
                       const Aws::CloudWatchLogs::Model::PutLogEventsRequest& request,
                       const Aws::CloudWatchLogs::Model::PutLogEventsOutcome& outcome,
                       const std::shared_ptr<const Aws::Client::AsyncCallerContext>& context) {
                    if (outcome.IsSuccess()) {
                        monitoring_metrics_.logs_sent += request.GetLogEvents().size();
                    } else {
                        monitoring_metrics_.aws_api_errors++;
                    }
                });
                
        } catch (const std::exception& e) {
            monitoring_metrics_.aws_api_errors++;
        }
    }
    
    // Monitor system health and send periodic metrics
    void monitorSystemHealth() {
        while (running_) {
            // Send monitoring system metrics
            recordMetric("MonitoringMetricsSent", static_cast<double>(monitoring_metrics_.metrics_sent.load()));
            recordMetric("MonitoringMetricsDropped", static_cast<double>(monitoring_metrics_.metrics_dropped.load()));
            recordMetric("MonitoringLogsSent", static_cast<double>(monitoring_metrics_.logs_sent.load()));
            recordMetric("MonitoringLogsDropped", static_cast<double>(monitoring_metrics_.logs_dropped.load()));
            recordMetric("MonitoringAPIErrors", static_cast<double>(monitoring_metrics_.aws_api_errors.load()));
            
            // System resource metrics
            recordSystemResourceMetrics();
            
            // Sleep for 30 seconds
            std::this_thread::sleep_for(std::chrono::seconds(30));
        }
    }
    
    void recordSystemResourceMetrics() {
        // CPU usage
        double cpu_usage = getCPUUsage();
        recordMetric("CPUUtilization", cpu_usage, "Percent");
        
        // Memory usage
        auto memory_info = getMemoryUsage();
        recordMetric("MemoryUtilization", memory_info.first, "Percent");
        recordMetric("MemoryUsedMB", memory_info.second, "Megabytes");
        
        // Network stats
        auto network_stats = getNetworkStats();
        recordMetric("NetworkPacketsReceived", static_cast<double>(network_stats.packets_rx), "Count");
        recordMetric("NetworkPacketsSent", static_cast<double>(network_stats.packets_tx), "Count");
        recordMetric("NetworkBytesReceived", static_cast<double>(network_stats.bytes_rx), "Bytes");
        recordMetric("NetworkBytesSent", static_cast<double>(network_stats.bytes_tx), "Bytes");
    }
    
    void flushAll() {
        // Flush remaining metrics and logs
        // Implementation would force processing of remaining queue items
    }
    
    std::vector<Aws::CloudWatch::Model::Dimension> parseDimensions(const char* dimensions_json) {
        // Simple JSON parsing for dimensions
        // In production, use a proper JSON library
        std::vector<Aws::CloudWatch::Model::Dimension> dimensions;
        
        // For now, return empty dimensions
        // TODO: Implement JSON parsing
        
        return dimensions;
    }
    
    void updateSendLatency(uint64_t latency_ns) {
        uint64_t current_avg = monitoring_metrics_.avg_send_latency_ns.load();
        uint64_t new_avg = (current_avg * 15 + latency_ns) / 16;  // EMA
        monitoring_metrics_.avg_send_latency_ns.store(new_avg);
    }
    
    // Utility functions
    void setCPUAffinity(int cpu_id) {
        cpu_set_t cpuset;
        CPU_ZERO(&cpuset);
        CPU_SET(cpu_id, &cpuset);
        pthread_setaffinity_np(pthread_self(), sizeof(cpu_set_t), &cpuset);
    }
    
    void setThreadPriority(int priority) {
        struct sched_param param;
        param.sched_priority = priority;
        pthread_setschedparam(pthread_self(), SCHED_FIFO, &param);
    }
    
    uint64_t rdtsc() {
        uint32_t hi, lo;
        __asm__ __volatile__ ("rdtsc" : "=a"(lo), "=d"(hi));
        return ((uint64_t)hi << 32) | lo;
    }
    
    uint64_t rdtsc_to_ns(uint64_t tsc) {
        return tsc / 3;  // Assuming 3GHz CPU
    }
    
    uint64_t tsc_to_ns(uint64_t tsc_diff) {
        return tsc_diff / 3;  // Convert TSC cycles to nanoseconds
    }
    
    // System monitoring helpers (simplified implementations)
    double getCPUUsage() {
        // Read from /proc/stat and calculate CPU usage
        return 0.0;  // Placeholder
    }
    
    std::pair<double, double> getMemoryUsage() {
        // Read from /proc/meminfo
        return {0.0, 0.0};  // Placeholder: (percentage, MB used)
    }
    
    struct NetworkStats {
        uint64_t packets_rx;
        uint64_t packets_tx;
        uint64_t bytes_rx;
        uint64_t bytes_tx;
    };
    
    NetworkStats getNetworkStats() {
        // Read from /proc/net/dev
        return {0, 0, 0, 0};  // Placeholder
    }
};

// Global monitoring instance for convenience
extern AWSMonitoring* g_monitoring;

// Convenience macros for hot path usage
#define RECORD_METRIC(name, value) \
    if (g_monitoring) g_monitoring->recordMetric(name, value)

#define RECORD_LATENCY(operation, start_tsc, end_tsc) \
    if (g_monitoring) g_monitoring->recordLatency(operation, start_tsc, end_tsc)

#define LOG_DEBUG(component, message) \
    if (g_monitoring) g_monitoring->logDebug(component, message)

#define LOG_INFO(component, message) \
    if (g_monitoring) g_monitoring->logInfo(component, message)

#define LOG_WARNING(component, message) \
    if (g_monitoring) g_monitoring->logWarning(component, message)

#define LOG_ERROR(component, message) \
    if (g_monitoring) g_monitoring->logError(component, message)

#define LOG_CRITICAL(component, message) \
    if (g_monitoring) g_monitoring->logCritical(component, message)

} // namespace HFT