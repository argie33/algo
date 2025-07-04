/**
 * Market Data Feed Manager
 * Handles connections to multiple market data providers
 */

#include <aws/core/Aws.h>
#include <aws/secretsmanager/SecretsManagerClient.h>
#include <aws/secretsmanager/model/GetSecretValueRequest.h>
#include <curl/curl.h>
#include <websocketpp/config/asio_client.hpp>
#include <websocketpp/client.hpp>
#include <nlohmann/json.hpp>
#include <thread>
#include <atomic>
#include <queue>
#include <mutex>

namespace HFT {

using json = nlohmann::json;
using WebSocketClient = websocketpp::client<websocketpp::config::asio_tls_client>;

// Market data feed configuration
struct FeedConfig {
    std::string name;
    std::string api_key;
    std::string secret_key;
    std::string websocket_url;
    std::string rest_api_url;
    std::vector<std::string> symbols;
    bool enabled;
    uint32_t reconnect_delay_ms = 5000;
    uint32_t heartbeat_interval_ms = 30000;
};

// Standardized market data message
struct MarketDataMessage {
    uint64_t timestamp_ns;
    std::string symbol;
    std::string feed_name;
    
    // Price data
    double last_price = 0.0;
    uint64_t last_size = 0;
    double bid_price = 0.0;
    double ask_price = 0.0;
    uint32_t bid_size = 0;
    uint32_t ask_size = 0;
    
    // Trade data
    bool is_trade = false;
    double trade_price = 0.0;
    uint64_t trade_volume = 0;
    
    // Quote data
    bool is_quote = false;
    
    // Book data
    bool is_book_update = false;
    std::vector<std::pair<double, uint32_t>> bids;  // price, size
    std::vector<std::pair<double, uint32_t>> asks;  // price, size
};

class MarketDataFeed {
protected:
    FeedConfig config_;
    std::atomic<bool> connected_{false};
    std::atomic<bool> running_{false};
    
    // Message queue for processed data
    std::queue<MarketDataMessage> message_queue_;
    std::mutex queue_mutex_;
    
    // Statistics
    std::atomic<uint64_t> messages_received_{0};
    std::atomic<uint64_t> messages_processed_{0};
    std::atomic<uint64_t> connection_errors_{0};
    
public:
    MarketDataFeed(const FeedConfig& config) : config_(config) {}
    virtual ~MarketDataFeed() { stop(); }
    
    virtual bool start() = 0;
    virtual void stop() = 0;
    virtual bool subscribe(const std::vector<std::string>& symbols) = 0;
    virtual bool unsubscribe(const std::vector<std::string>& symbols) = 0;
    
    bool isConnected() const { return connected_.load(); }
    bool isRunning() const { return running_.load(); }
    
    // Get next message from queue
    bool getMessage(MarketDataMessage& message) {
        std::lock_guard<std::mutex> lock(queue_mutex_);
        if (message_queue_.empty()) {
            return false;
        }
        
        message = message_queue_.front();
        message_queue_.pop();
        return true;
    }
    
    // Get feed statistics
    struct FeedStats {
        uint64_t messages_received;
        uint64_t messages_processed;
        uint64_t connection_errors;
        bool connected;
        std::string feed_name;
    };
    
    FeedStats getStats() const {
        return {
            messages_received_.load(),
            messages_processed_.load(),
            connection_errors_.load(),
            connected_.load(),
            config_.name
        };
    }

protected:
    void pushMessage(const MarketDataMessage& message) {
        std::lock_guard<std::mutex> lock(queue_mutex_);
        message_queue_.push(message);
        messages_processed_++;
    }
    
    uint64_t getCurrentTimeNs() const {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::high_resolution_clock::now().time_since_epoch()).count();
    }
};

// Polygon.io market data feed
class PolygonFeed : public MarketDataFeed {
private:
    WebSocketClient ws_client_;
    websocketpp::connection_hdl connection_hdl_;
    std::thread ws_thread_;
    
public:
    PolygonFeed(const FeedConfig& config) : MarketDataFeed(config) {
        ws_client_.set_access_channels(websocketpp::log::alevel::all);
        ws_client_.clear_access_channels(websocketpp::log::alevel::frame_payload);
        ws_client_.init_asio();
        
        // Set handlers
        ws_client_.set_message_handler([this](websocketpp::connection_hdl hdl, WebSocketClient::message_ptr msg) {
            handleMessage(msg->get_payload());
        });
        
        ws_client_.set_open_handler([this](websocketpp::connection_hdl hdl) {
            connected_ = true;
            authenticate();
        });
        
        ws_client_.set_close_handler([this](websocketpp::connection_hdl hdl) {
            connected_ = false;
        });
    }
    
    bool start() override {
        if (running_) return true;
        
        running_ = true;
        
        try {
            websocketpp::lib::error_code ec;
            auto con = ws_client_.get_connection(config_.websocket_url, ec);
            
            if (ec) {
                running_ = false;
                return false;
            }
            
            connection_hdl_ = con->get_handle();
            ws_client_.connect(con);
            
            ws_thread_ = std::thread([this]() {
                ws_client_.run();
            });
            
            return true;
            
        } catch (const std::exception& e) {
            running_ = false;
            connection_errors_++;
            return false;
        }
    }
    
    void stop() override {
        if (!running_) return;
        
        running_ = false;
        connected_ = false;
        
        try {
            ws_client_.close(connection_hdl_, websocketpp::close::status::normal, "");
            ws_client_.stop();
            
            if (ws_thread_.joinable()) {
                ws_thread_.join();
            }
        } catch (const std::exception& e) {
            // Ignore cleanup errors
        }
    }
    
    bool subscribe(const std::vector<std::string>& symbols) override {
        if (!connected_) return false;
        
        json subscribe_msg = {
            {"action", "subscribe"},
            {"params", symbols}
        };
        
        try {
            ws_client_.send(connection_hdl_, subscribe_msg.dump(), websocketpp::frame::opcode::text);
            return true;
        } catch (const std::exception& e) {
            return false;
        }
    }
    
    bool unsubscribe(const std::vector<std::string>& symbols) override {
        if (!connected_) return false;
        
        json unsubscribe_msg = {
            {"action", "unsubscribe"},
            {"params", symbols}
        };
        
        try {
            ws_client_.send(connection_hdl_, unsubscribe_msg.dump(), websocketpp::frame::opcode::text);
            return true;
        } catch (const std::exception& e) {
            return false;
        }
    }

private:
    void authenticate() {
        json auth_msg = {
            {"action", "auth"},
            {"params", config_.api_key}
        };
        
        try {
            ws_client_.send(connection_hdl_, auth_msg.dump(), websocketpp::frame::opcode::text);
        } catch (const std::exception& e) {
            connection_errors_++;
        }
    }
    
    void handleMessage(const std::string& payload) {
        messages_received_++;
        
        try {
            json msg = json::parse(payload);
            
            // Handle different message types
            if (msg.contains("ev")) {
                std::string event_type = msg["ev"];
                
                if (event_type == "T") {  // Trade
                    handleTrade(msg);
                } else if (event_type == "Q") {  // Quote
                    handleQuote(msg);
                } else if (event_type == "A") {  // Aggregate
                    handleAggregate(msg);
                }
            }
            
        } catch (const std::exception& e) {
            // Invalid JSON or parsing error
        }
    }
    
    void handleTrade(const json& msg) {
        MarketDataMessage market_msg;
        market_msg.timestamp_ns = getCurrentTimeNs();
        market_msg.symbol = msg.value("sym", "");
        market_msg.feed_name = config_.name;
        market_msg.is_trade = true;
        market_msg.trade_price = msg.value("p", 0.0);
        market_msg.trade_volume = msg.value("s", 0);
        market_msg.last_price = market_msg.trade_price;
        market_msg.last_size = market_msg.trade_volume;
        
        pushMessage(market_msg);
    }
    
    void handleQuote(const json& msg) {
        MarketDataMessage market_msg;
        market_msg.timestamp_ns = getCurrentTimeNs();
        market_msg.symbol = msg.value("sym", "");
        market_msg.feed_name = config_.name;
        market_msg.is_quote = true;
        market_msg.bid_price = msg.value("bp", 0.0);
        market_msg.ask_price = msg.value("ap", 0.0);
        market_msg.bid_size = msg.value("bs", 0);
        market_msg.ask_size = msg.value("as", 0);
        
        pushMessage(market_msg);
    }
    
    void handleAggregate(const json& msg) {
        MarketDataMessage market_msg;
        market_msg.timestamp_ns = getCurrentTimeNs();
        market_msg.symbol = msg.value("sym", "");
        market_msg.feed_name = config_.name;
        market_msg.last_price = msg.value("c", 0.0);  // Close price
        market_msg.last_size = msg.value("v", 0);     // Volume
        
        pushMessage(market_msg);
    }
};

// Alpha Vantage market data feed (REST-based)
class AlphaVantageFeed : public MarketDataFeed {
private:
    std::thread polling_thread_;
    std::atomic<bool> should_poll_{false};
    
public:
    AlphaVantageFeed(const FeedConfig& config) : MarketDataFeed(config) {}
    
    bool start() override {
        if (running_) return true;
        
        running_ = true;
        should_poll_ = true;
        
        polling_thread_ = std::thread([this]() {
            pollMarketData();
        });
        
        return true;
    }
    
    void stop() override {
        if (!running_) return;
        
        running_ = false;
        should_poll_ = false;
        
        if (polling_thread_.joinable()) {
            polling_thread_.join();
        }
    }
    
    bool subscribe(const std::vector<std::string>& symbols) override {
        // Alpha Vantage doesn't use subscriptions, just update symbol list
        config_.symbols = symbols;
        return true;
    }
    
    bool unsubscribe(const std::vector<std::string>& symbols) override {
        // Remove symbols from config
        for (const auto& symbol : symbols) {
            config_.symbols.erase(
                std::remove(config_.symbols.begin(), config_.symbols.end(), symbol),
                config_.symbols.end());
        }
        return true;
    }

private:
    void pollMarketData() {
        while (should_poll_) {
            for (const auto& symbol : config_.symbols) {
                if (!should_poll_) break;
                
                fetchQuote(symbol);
                std::this_thread::sleep_for(std::chrono::seconds(1)); // Rate limit
            }
            
            std::this_thread::sleep_for(std::chrono::seconds(10)); // Poll every 10 seconds
        }
    }
    
    void fetchQuote(const std::string& symbol) {
        std::string url = config_.rest_api_url + 
                         "?function=GLOBAL_QUOTE&symbol=" + symbol + 
                         "&apikey=" + config_.api_key;
        
        std::string response = makeHTTPRequest(url);
        if (!response.empty()) {
            parseQuoteResponse(symbol, response);
        }
    }
    
    std::string makeHTTPRequest(const std::string& url) {
        CURL* curl = curl_easy_init();
        if (!curl) return "";
        
        std::string response_data;
        
        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_data);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, 10L);
        
        CURLcode res = curl_easy_perform(curl);
        curl_easy_cleanup(curl);
        
        return (res == CURLE_OK) ? response_data : "";
    }
    
    static size_t writeCallback(void* contents, size_t size, size_t nmemb, std::string* response) {
        size_t total_size = size * nmemb;
        response->append(static_cast<char*>(contents), total_size);
        return total_size;
    }
    
    void parseQuoteResponse(const std::string& symbol, const std::string& response) {
        try {
            json data = json::parse(response);
            
            if (data.contains("Global Quote")) {
                json quote = data["Global Quote"];
                
                MarketDataMessage market_msg;
                market_msg.timestamp_ns = getCurrentTimeNs();
                market_msg.symbol = symbol;
                market_msg.feed_name = config_.name;
                market_msg.last_price = std::stod(quote.value("05. price", "0"));
                market_msg.last_size = std::stoull(quote.value("06. volume", "0"));
                
                pushMessage(market_msg);
                messages_received_++;
            }
            
        } catch (const std::exception& e) {
            // Parsing error
        }
    }
};

// Market Data Feed Manager
class MarketDataFeedManager {
private:
    std::vector<std::unique_ptr<MarketDataFeed>> feeds_;
    std::atomic<bool> running_{false};
    std::thread aggregation_thread_;
    
    // Output queue for aggregated data
    std::queue<MarketDataMessage> output_queue_;
    std::mutex output_mutex_;
    
    // AWS Secrets Manager for API keys
    std::unique_ptr<Aws::SecretsManager::SecretsManagerClient> secrets_client_;
    
public:
    MarketDataFeedManager() {
        Aws::Client::ClientConfiguration config;
        config.region = "us-east-1";
        secrets_client_ = std::make_unique<Aws::SecretsManager::SecretsManagerClient>(config);
    }
    
    ~MarketDataFeedManager() {
        stop();
    }
    
    bool initialize(const std::string& secrets_name) {
        // Load API keys from AWS Secrets Manager
        auto feed_configs = loadFeedConfigs(secrets_name);
        
        // Create feeds
        for (const auto& config : feed_configs) {
            if (config.name == "polygon") {
                feeds_.push_back(std::make_unique<PolygonFeed>(config));
            } else if (config.name == "alpha_vantage") {
                feeds_.push_back(std::make_unique<AlphaVantageFeed>(config));
            }
        }
        
        return !feeds_.empty();
    }
    
    bool start() {
        if (running_) return true;
        
        running_ = true;
        
        // Start all feeds
        for (auto& feed : feeds_) {
            feed->start();
        }
        
        // Start aggregation thread
        aggregation_thread_ = std::thread([this]() {
            aggregateFeeds();
        });
        
        return true;
    }
    
    void stop() {
        if (!running_) return;
        
        running_ = false;
        
        // Stop all feeds
        for (auto& feed : feeds_) {
            feed->stop();
        }
        
        if (aggregation_thread_.joinable()) {
            aggregation_thread_.join();
        }
    }
    
    bool subscribeSymbols(const std::vector<std::string>& symbols) {
        bool success = true;
        for (auto& feed : feeds_) {
            success &= feed->subscribe(symbols);
        }
        return success;
    }
    
    bool getMessage(MarketDataMessage& message) {
        std::lock_guard<std::mutex> lock(output_mutex_);
        if (output_queue_.empty()) {
            return false;
        }
        
        message = output_queue_.front();
        output_queue_.pop();
        return true;
    }
    
    std::vector<MarketDataFeed::FeedStats> getFeedStats() const {
        std::vector<MarketDataFeed::FeedStats> stats;
        for (const auto& feed : feeds_) {
            stats.push_back(feed->getStats());
        }
        return stats;
    }

private:
    std::vector<FeedConfig> loadFeedConfigs(const std::string& secrets_name) {
        std::vector<FeedConfig> configs;
        
        try {
            Aws::SecretsManager::Model::GetSecretValueRequest request;
            request.SetSecretId(secrets_name);
            
            auto outcome = secrets_client_->GetSecretValue(request);
            if (outcome.IsSuccess()) {
                std::string secret_string = outcome.GetResult().GetSecretString();
                json secrets = json::parse(secret_string);
                
                // Polygon.io config
                if (secrets.contains("polygon_api_key")) {
                    FeedConfig polygon_config;
                    polygon_config.name = "polygon";
                    polygon_config.api_key = secrets["polygon_api_key"];
                    polygon_config.websocket_url = "wss://socket.polygon.io/stocks";
                    polygon_config.enabled = true;
                    configs.push_back(polygon_config);
                }
                
                // Alpha Vantage config
                if (secrets.contains("alpha_vantage_api_key")) {
                    FeedConfig av_config;
                    av_config.name = "alpha_vantage";
                    av_config.api_key = secrets["alpha_vantage_api_key"];
                    av_config.rest_api_url = "https://www.alphavantage.co/query";
                    av_config.enabled = true;
                    configs.push_back(av_config);
                }
            }
            
        } catch (const std::exception& e) {
            // Error loading secrets
        }
        
        return configs;
    }
    
    void aggregateFeeds() {
        while (running_) {
            // Collect messages from all feeds
            for (auto& feed : feeds_) {
                MarketDataMessage message;
                while (feed->getMessage(message)) {
                    // Add to output queue
                    std::lock_guard<std::mutex> lock(output_mutex_);
                    output_queue_.push(message);
                }
            }
            
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }
};

} // namespace HFT