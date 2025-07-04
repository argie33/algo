/**
 * Amazon Timestream Client for HFT System
 * High-performance time series data storage and retrieval
 */

#include <aws/timestream-write/TimestreamWriteClient.h>
#include <aws/timestream-write/model/WriteRecordsRequest.h>
#include <aws/timestream-write/model/Record.h>
#include <aws/timestream-write/model/Dimension.h>
#include <aws/timestream-query/TimestreamQueryClient.h>
#include <aws/timestream-query/model/QueryRequest.h>
#include <memory>
#include <vector>
#include <string>
#include <chrono>
#include <deque>
#include <mutex>
#include <thread>
#include <atomic>

namespace HFT {

// Time series data point
struct TimeSeriesPoint {
    uint64_t timestamp_ns;
    std::string symbol;
    std::string measure_name;
    double measure_value;
    std::unordered_map<std::string, std::string> dimensions;
};

// Market data tick for time series
struct MarketDataTick {
    uint64_t timestamp_ns;
    std::string symbol;
    double price;
    uint64_t volume;
    double bid_price;
    double ask_price;
    uint32_t bid_size;
    uint32_t ask_size;
    std::string venue;
};

// Trading metrics for time series
struct TradingMetricPoint {
    uint64_t timestamp_ns;
    std::string strategy_name;
    std::string symbol;
    double realized_pnl;
    double unrealized_pnl;
    int32_t position;
    double fill_price;
    uint32_t quantity;
};

class TimestreamClient {
private:
    std::unique_ptr<Aws::TimestreamWrite::TimestreamWriteClient> write_client_;
    std::unique_ptr<Aws::TimestreamQuery::TimestreamQueryClient> query_client_;
    
    std::string database_name_;
    std::string market_data_table_;
    std::string trading_metrics_table_;
    std::string performance_metrics_table_;
    
    // Batch writing for performance
    std::deque<Aws::TimestreamWrite::Model::Record> pending_records_;
    std::mutex records_mutex_;
    std::thread batch_writer_thread_;
    std::atomic<bool> running_{false};
    
    // Configuration
    struct TimestreamConfig {
        size_t batch_size = 100;           // Records per batch
        uint64_t flush_interval_ms = 1000; // Flush every second
        size_t max_pending_records = 10000; // Buffer limit
        uint32_t retry_attempts = 3;       // Retry failed writes
    };
    
    TimestreamConfig config_;
    
    // Performance metrics
    struct TimestreamMetrics {
        std::atomic<uint64_t> records_written{0};
        std::atomic<uint64_t> records_failed{0};
        std::atomic<uint64_t> batch_writes{0};
        std::atomic<uint64_t> avg_write_latency_ms{0};
    };
    
    TimestreamMetrics metrics_;

public:
    TimestreamClient(const std::string& database_name,
                    const std::string& region = "us-east-1") 
        : database_name_(database_name),
          market_data_table_("market-data"),
          trading_metrics_table_("trading-metrics"),
          performance_metrics_table_("performance-metrics") {
        
        // Initialize AWS clients
        Aws::Client::ClientConfiguration config;
        config.region = region;
        config.requestTimeoutMs = 5000;
        config.connectTimeoutMs = 2000;
        
        write_client_ = std::make_unique<Aws::TimestreamWrite::TimestreamWriteClient>(config);
        query_client_ = std::make_unique<Aws::TimestreamQuery::TimestreamQueryClient>(config);
    }
    
    ~TimestreamClient() {
        stop();
    }
    
    void start() {
        running_ = true;
        batch_writer_thread_ = std::thread([this]() {
            batchWriterLoop();
        });
    }
    
    void stop() {
        running_ = false;
        
        // Flush remaining records
        flushPendingRecords();
        
        if (batch_writer_thread_.joinable()) {
            batch_writer_thread_.join();
        }
    }
    
    // Write market data tick
    bool writeMarketData(const MarketDataTick& tick) {
        Aws::TimestreamWrite::Model::Record record;
        
        // Set timestamp
        record.SetTime(std::to_string(tick.timestamp_ns / 1000000)); // Convert to milliseconds
        record.SetTimeUnit(Aws::TimestreamWrite::Model::TimeUnit::MILLISECONDS);
        
        // Set dimensions
        std::vector<Aws::TimestreamWrite::Model::Dimension> dimensions;
        
        Aws::TimestreamWrite::Model::Dimension symbol_dim;
        symbol_dim.SetName("symbol");
        symbol_dim.SetValue(tick.symbol);
        dimensions.push_back(symbol_dim);
        
        Aws::TimestreamWrite::Model::Dimension venue_dim;
        venue_dim.SetName("venue");
        venue_dim.SetValue(tick.venue);
        dimensions.push_back(venue_dim);
        
        record.SetDimensions(dimensions);
        
        // Write multiple measures for this tick
        writeMarketDataMeasures(tick, dimensions);
        
        return true;
    }
    
    // Write trading metrics
    bool writeTradingMetric(const TradingMetricPoint& metric) {
        Aws::TimestreamWrite::Model::Record record;
        
        record.SetTime(std::to_string(metric.timestamp_ns / 1000000));
        record.SetTimeUnit(Aws::TimestreamWrite::Model::TimeUnit::MILLISECONDS);
        
        // Dimensions
        std::vector<Aws::TimestreamWrite::Model::Dimension> dimensions;
        
        Aws::TimestreamWrite::Model::Dimension strategy_dim;
        strategy_dim.SetName("strategy");
        strategy_dim.SetValue(metric.strategy_name);
        dimensions.push_back(strategy_dim);
        
        Aws::TimestreamWrite::Model::Dimension symbol_dim;
        symbol_dim.SetName("symbol");
        symbol_dim.SetValue(metric.symbol);
        dimensions.push_back(symbol_dim);
        
        record.SetDimensions(dimensions);
        
        // Write P&L measures
        writeTradingMetricMeasures(metric, dimensions);
        
        return true;
    }
    
    // Query market data for backtesting
    std::vector<MarketDataTick> queryMarketData(const std::string& symbol,
                                               uint64_t start_time_ms,
                                               uint64_t end_time_ms,
                                               const std::string& interval = "1m") {
        
        std::string query = buildMarketDataQuery(symbol, start_time_ms, end_time_ms, interval);
        return executeMarketDataQuery(query);
    }
    
    // Query trading performance metrics
    struct PerformanceData {
        double total_pnl;
        double win_rate;
        double sharpe_ratio;
        uint32_t total_trades;
        double max_drawdown;
    };
    
    PerformanceData queryPerformanceMetrics(const std::string& strategy_name,
                                          uint64_t start_time_ms,
                                          uint64_t end_time_ms) {
        
        std::string query = buildPerformanceQuery(strategy_name, start_time_ms, end_time_ms);
        return executePerformanceQuery(query);
    }
    
    // Query VWAP data
    std::vector<std::pair<uint64_t, double>> queryVWAP(const std::string& symbol,
                                                       uint64_t start_time_ms,
                                                       uint64_t end_time_ms,
                                                       const std::string& interval = "5m") {
        
        std::string query = R"(
            SELECT 
                bin(time, )" + interval + R"() as time_window,
                SUM(price * volume) / SUM(volume) as vwap
            FROM ")" + database_name_ + R"(".")" + market_data_table_ + R"("
            WHERE symbol = ')" + symbol + R"('
                AND time BETWEEN from_milliseconds()" + std::to_string(start_time_ms) + R"()
                AND from_milliseconds()" + std::to_string(end_time_ms) + R"()
                AND measure_name = 'price'
            GROUP BY bin(time, )" + interval + R"()
            ORDER BY time_window
        )";
        
        return executeVWAPQuery(query);
    }
    
    // Get real-time metrics
    TimestreamMetrics getMetrics() const {
        return metrics_;
    }

private:
    void writeMarketDataMeasures(const MarketDataTick& tick,
                                const std::vector<Aws::TimestreamWrite::Model::Dimension>& dimensions) {
        
        // Price record
        Aws::TimestreamWrite::Model::Record price_record;
        price_record.SetTime(std::to_string(tick.timestamp_ns / 1000000));
        price_record.SetTimeUnit(Aws::TimestreamWrite::Model::TimeUnit::MILLISECONDS);
        price_record.SetDimensions(dimensions);
        price_record.SetMeasureName("price");
        price_record.SetMeasureValue(std::to_string(tick.price));
        price_record.SetMeasureValueType(Aws::TimestreamWrite::Model::MeasureValueType::DOUBLE);
        
        // Volume record
        Aws::TimestreamWrite::Model::Record volume_record;
        volume_record.SetTime(std::to_string(tick.timestamp_ns / 1000000));
        volume_record.SetTimeUnit(Aws::TimestreamWrite::Model::TimeUnit::MILLISECONDS);
        volume_record.SetDimensions(dimensions);
        volume_record.SetMeasureName("volume");
        volume_record.SetMeasureValue(std::to_string(tick.volume));
        volume_record.SetMeasureValueType(Aws::TimestreamWrite::Model::MeasureValueType::BIGINT);
        
        // Bid/Ask records
        Aws::TimestreamWrite::Model::Record bid_record;
        bid_record.SetTime(std::to_string(tick.timestamp_ns / 1000000));
        bid_record.SetTimeUnit(Aws::TimestreamWrite::Model::TimeUnit::MILLISECONDS);
        bid_record.SetDimensions(dimensions);
        bid_record.SetMeasureName("bid_price");
        bid_record.SetMeasureValue(std::to_string(tick.bid_price));
        bid_record.SetMeasureValueType(Aws::TimestreamWrite::Model::MeasureValueType::DOUBLE);
        
        Aws::TimestreamWrite::Model::Record ask_record;
        ask_record.SetTime(std::to_string(tick.timestamp_ns / 1000000));
        ask_record.SetTimeUnit(Aws::TimestreamWrite::Model::TimeUnit::MILLISECONDS);
        ask_record.SetDimensions(dimensions);
        ask_record.SetMeasureName("ask_price");
        ask_record.SetMeasureValue(std::to_string(tick.ask_price));
        ask_record.SetMeasureValueType(Aws::TimestreamWrite::Model::MeasureValueType::DOUBLE);
        
        // Add to batch
        std::lock_guard<std::mutex> lock(records_mutex_);
        pending_records_.push_back(price_record);
        pending_records_.push_back(volume_record);
        pending_records_.push_back(bid_record);
        pending_records_.push_back(ask_record);
    }
    
    void writeTradingMetricMeasures(const TradingMetricPoint& metric,
                                   const std::vector<Aws::TimestreamWrite::Model::Dimension>& dimensions) {
        
        // Realized P&L record
        Aws::TimestreamWrite::Model::Record pnl_record;
        pnl_record.SetTime(std::to_string(metric.timestamp_ns / 1000000));
        pnl_record.SetTimeUnit(Aws::TimestreamWrite::Model::TimeUnit::MILLISECONDS);
        pnl_record.SetDimensions(dimensions);
        pnl_record.SetMeasureName("realized_pnl");
        pnl_record.SetMeasureValue(std::to_string(metric.realized_pnl));
        pnl_record.SetMeasureValueType(Aws::TimestreamWrite::Model::MeasureValueType::DOUBLE);
        
        // Position record
        Aws::TimestreamWrite::Model::Record position_record;
        position_record.SetTime(std::to_string(metric.timestamp_ns / 1000000));
        position_record.SetTimeUnit(Aws::TimestreamWrite::Model::TimeUnit::MILLISECONDS);
        position_record.SetDimensions(dimensions);
        position_record.SetMeasureName("position");
        position_record.SetMeasureValue(std::to_string(metric.position));
        position_record.SetMeasureValueType(Aws::TimestreamWrite::Model::MeasureValueType::BIGINT);
        
        // Fill price record
        if (metric.quantity > 0) {
            Aws::TimestreamWrite::Model::Record fill_record;
            fill_record.SetTime(std::to_string(metric.timestamp_ns / 1000000));
            fill_record.SetTimeUnit(Aws::TimestreamWrite::Model::TimeUnit::MILLISECONDS);
            fill_record.SetDimensions(dimensions);
            fill_record.SetMeasureName("fill_price");
            fill_record.SetMeasureValue(std::to_string(metric.fill_price));
            fill_record.SetMeasureValueType(Aws::TimestreamWrite::Model::MeasureValueType::DOUBLE);
            
            std::lock_guard<std::mutex> lock(records_mutex_);
            pending_records_.push_back(fill_record);
        }
        
        std::lock_guard<std::mutex> lock(records_mutex_);
        pending_records_.push_back(pnl_record);
        pending_records_.push_back(position_record);
    }
    
    void batchWriterLoop() {
        while (running_) {
            auto start_time = std::chrono::steady_clock::now();
            
            std::vector<Aws::TimestreamWrite::Model::Record> batch;
            
            // Collect batch
            {
                std::lock_guard<std::mutex> lock(records_mutex_);
                
                size_t batch_size = std::min(config_.batch_size, pending_records_.size());
                
                for (size_t i = 0; i < batch_size; ++i) {
                    batch.push_back(pending_records_.front());
                    pending_records_.pop_front();
                }
            }
            
            // Write batch if not empty
            if (!batch.empty()) {
                writeBatch(batch, market_data_table_);
                
                auto end_time = std::chrono::steady_clock::now();
                auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(
                    end_time - start_time).count();
                
                // Update metrics
                metrics_.batch_writes++;
                uint64_t current_avg = metrics_.avg_write_latency_ms.load();
                uint64_t new_avg = (current_avg * 15 + duration) / 16; // EMA
                metrics_.avg_write_latency_ms.store(new_avg);
            }
            
            std::this_thread::sleep_for(std::chrono::milliseconds(config_.flush_interval_ms));
        }
    }
    
    void writeBatch(const std::vector<Aws::TimestreamWrite::Model::Record>& records,
                   const std::string& table_name) {
        
        Aws::TimestreamWrite::Model::WriteRecordsRequest request;
        request.SetDatabaseName(database_name_);
        request.SetTableName(table_name);
        request.SetRecords(records);
        
        for (uint32_t attempt = 0; attempt < config_.retry_attempts; ++attempt) {
            auto outcome = write_client_->WriteRecords(request);
            
            if (outcome.IsSuccess()) {
                metrics_.records_written += records.size();
                return;
            } else {
                // Log error and retry
                if (attempt == config_.retry_attempts - 1) {
                    metrics_.records_failed += records.size();
                }
                
                std::this_thread::sleep_for(std::chrono::milliseconds(100 * (attempt + 1)));
            }
        }
    }
    
    void flushPendingRecords() {
        std::lock_guard<std::mutex> lock(records_mutex_);
        
        if (!pending_records_.empty()) {
            std::vector<Aws::TimestreamWrite::Model::Record> remaining(
                pending_records_.begin(), pending_records_.end());
            
            writeBatch(remaining, market_data_table_);
            pending_records_.clear();
        }
    }
    
    std::string buildMarketDataQuery(const std::string& symbol,
                                   uint64_t start_time_ms,
                                   uint64_t end_time_ms,
                                   const std::string& interval) {
        
        return R"(
            SELECT 
                bin(time, )" + interval + R"() as time_window,
                symbol,
                avg(case when measure_name = 'price' then measure_value::double end) as avg_price,
                sum(case when measure_name = 'volume' then measure_value::bigint end) as total_volume,
                avg(case when measure_name = 'bid_price' then measure_value::double end) as avg_bid,
                avg(case when measure_name = 'ask_price' then measure_value::double end) as avg_ask
            FROM ")" + database_name_ + R"(".")" + market_data_table_ + R"("
            WHERE symbol = ')" + symbol + R"('
                AND time BETWEEN from_milliseconds()" + std::to_string(start_time_ms) + R"()
                AND from_milliseconds()" + std::to_string(end_time_ms) + R"()
            GROUP BY bin(time, )" + interval + R"(), symbol
            ORDER BY time_window
        )";
    }
    
    std::string buildPerformanceQuery(const std::string& strategy_name,
                                    uint64_t start_time_ms,
                                    uint64_t end_time_ms) {
        
        return R"(
            SELECT 
                strategy,
                SUM(case when measure_name = 'realized_pnl' then measure_value::double else 0 end) as total_pnl,
                COUNT(case when measure_name = 'realized_pnl' and measure_value::double > 0 then 1 end) as winning_trades,
                COUNT(case when measure_name = 'realized_pnl' then 1 end) as total_trades,
                MIN(case when measure_name = 'realized_pnl' then measure_value::double end) as worst_trade,
                MAX(case when measure_name = 'realized_pnl' then measure_value::double end) as best_trade
            FROM ")" + database_name_ + R"(".")" + trading_metrics_table_ + R"("
            WHERE strategy = ')" + strategy_name + R"('
                AND time BETWEEN from_milliseconds()" + std::to_string(start_time_ms) + R"()
                AND from_milliseconds()" + std::to_string(end_time_ms) + R"()
            GROUP BY strategy
        )";
    }
    
    std::vector<MarketDataTick> executeMarketDataQuery(const std::string& query) {
        std::vector<MarketDataTick> results;
        
        Aws::TimestreamQuery::Model::QueryRequest request;
        request.SetQueryString(query);
        
        auto outcome = query_client_->Query(request);
        
        if (outcome.IsSuccess()) {
            const auto& result = outcome.GetResult();
            
            for (const auto& row : result.GetRows()) {
                MarketDataTick tick;
                
                // Parse row data (simplified)
                if (row.GetData().size() >= 6) {
                    tick.timestamp_ns = std::stoull(row.GetData()[0].GetScalarValue()) * 1000000;
                    tick.symbol = row.GetData()[1].GetScalarValue();
                    tick.price = std::stod(row.GetData()[2].GetScalarValue());
                    tick.volume = std::stoull(row.GetData()[3].GetScalarValue());
                    tick.bid_price = std::stod(row.GetData()[4].GetScalarValue());
                    tick.ask_price = std::stod(row.GetData()[5].GetScalarValue());
                    
                    results.push_back(tick);
                }
            }
        }
        
        return results;
    }
    
    PerformanceData executePerformanceQuery(const std::string& query) {
        PerformanceData performance{};
        
        Aws::TimestreamQuery::Model::QueryRequest request;
        request.SetQueryString(query);
        
        auto outcome = query_client_->Query(request);
        
        if (outcome.IsSuccess()) {
            const auto& result = outcome.GetResult();
            
            if (!result.GetRows().empty()) {
                const auto& row = result.GetRows()[0];
                const auto& data = row.GetData();
                
                if (data.size() >= 6) {
                    performance.total_pnl = std::stod(data[1].GetScalarValue());
                    uint32_t winning_trades = std::stoul(data[2].GetScalarValue());
                    performance.total_trades = std::stoul(data[3].GetScalarValue());
                    
                    performance.win_rate = performance.total_trades > 0 ? 
                        static_cast<double>(winning_trades) / performance.total_trades : 0.0;
                }
            }
        }
        
        return performance;
    }
    
    std::vector<std::pair<uint64_t, double>> executeVWAPQuery(const std::string& query) {
        std::vector<std::pair<uint64_t, double>> results;
        
        Aws::TimestreamQuery::Model::QueryRequest request;
        request.SetQueryString(query);
        
        auto outcome = query_client_->Query(request);
        
        if (outcome.IsSuccess()) {
            const auto& result = outcome.GetResult();
            
            for (const auto& row : result.GetRows()) {
                if (row.GetData().size() >= 2) {
                    uint64_t timestamp = std::stoull(row.GetData()[0].GetScalarValue());
                    double vwap = std::stod(row.GetData()[1].GetScalarValue());
                    
                    results.emplace_back(timestamp, vwap);
                }
            }
        }
        
        return results;
    }
};

} // namespace HFT