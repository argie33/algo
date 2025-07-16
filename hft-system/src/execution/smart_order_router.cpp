/**
 * Smart Order Router (SOR) with Advanced Venue Optimization
 * Implements ML-driven venue selection, dark pool detection, and latency arbitrage
 * Optimizes for best execution across multiple venues
 */

#include <memory>
#include <atomic>
#include <vector>
#include <unordered_map>
#include <chrono>
#include <algorithm>
#include <random>
#include <queue>
#include <mutex>

namespace HFT::Execution {

// Venue identification and characteristics
enum class VenueType : uint8_t {
    LIT_EXCHANGE = 1,       // Public exchanges (NYSE, NASDAQ, etc.)
    DARK_POOL = 2,          // Dark pools (ATSs)
    ECN = 3,                // Electronic Communication Networks
    WHOLESALER = 4,         // Wholesale market makers
    CROSSING_NETWORK = 5    // Crossing networks
};

// Real-time venue state
struct alignas(64) VenueState {
    uint8_t venue_id;
    VenueType venue_type;
    uint32_t symbol_id;
    
    // Liquidity metrics
    double bid_price;
    double ask_price;
    double bid_size;
    double ask_size;
    double spread_bps;
    double effective_spread_bps;
    
    // Performance metrics
    double fill_rate;           // Historical fill rate
    double average_fill_time_ms; // Average time to fill
    double price_improvement;    // Average price improvement
    double reject_rate;          // Order rejection rate
    
    // Quality metrics
    double adverse_selection;    // Adverse selection cost
    double hidden_liquidity;     // Estimated hidden liquidity
    double market_share;         // Venue market share for symbol
    double toxicity_score;       // Order flow toxicity
    
    // Latency metrics
    uint32_t round_trip_latency_us; // Round-trip latency
    uint32_t ack_latency_us;        // Order acknowledgment latency
    uint32_t cancel_latency_us;     // Cancellation latency
    
    // Venue-specific features
    bool supports_hidden_orders;
    bool supports_iceberg_orders;
    bool supports_immediate_or_cancel;
    bool supports_post_only;
    
    // Real-time status
    bool is_operational;
    bool has_connectivity;
    double capacity_utilization;  // How busy the venue is
    uint64_t last_update_ns;
    
    uint8_t padding[7];
};

// Order routing decision
struct RoutingDecision {
    uint8_t primary_venue_id;
    uint8_t backup_venue_id;
    double expected_fill_probability;
    double expected_price_improvement;
    double expected_total_cost;
    uint32_t expected_fill_time_ms;
    
    // Venue allocation (for large orders)
    std::vector<std::pair<uint8_t, double>> venue_allocation; // venue_id, percentage
    
    // Strategy parameters
    bool use_hidden_liquidity;
    bool enable_latency_arbitrage;
    bool enable_dark_pool_first;
    double max_market_impact_bps;
};

// Historical venue performance tracking
class VenuePerformanceTracker {
private:
    struct PerformanceRecord {
        uint64_t timestamp_ns;
        uint8_t venue_id;
        uint32_t symbol_id;
        double order_size;
        double fill_rate;
        double slippage_bps;
        double fill_time_ms;
        bool was_aggressive;
    };
    
    std::vector<PerformanceRecord> performance_history_;
    std::unordered_map<uint64_t, double> venue_quality_scores_; // venue_id << 32 | symbol_id
    mutable std::shared_mutex history_mutex_;
    
    static constexpr size_t MAX_HISTORY_SIZE = 100000;
    
public:
    // Record execution performance
    void recordExecution(uint8_t venue_id, uint32_t symbol_id, double order_size,
                        double fill_rate, double slippage_bps, double fill_time_ms,
                        bool was_aggressive) {
        std::unique_lock<std::shared_mutex> lock(history_mutex_);
        
        PerformanceRecord record;
        record.timestamp_ns = getCurrentTimeNs();
        record.venue_id = venue_id;
        record.symbol_id = symbol_id;
        record.order_size = order_size;
        record.fill_rate = fill_rate;
        record.slippage_bps = slippage_bps;
        record.fill_time_ms = fill_time_ms;
        record.was_aggressive = was_aggressive;
        
        performance_history_.push_back(record);
        
        // Keep only recent history
        if (performance_history_.size() > MAX_HISTORY_SIZE) {
            performance_history_.erase(performance_history_.begin());
        }
        
        // Update quality score
        updateQualityScore(venue_id, symbol_id);
    }
    
    // Get venue quality score for symbol
    double getVenueQuality(uint8_t venue_id, uint32_t symbol_id) const {
        std::shared_lock<std::shared_mutex> lock(history_mutex_);
        
        uint64_t key = (static_cast<uint64_t>(venue_id) << 32) | symbol_id;
        auto it = venue_quality_scores_.find(key);
        return (it != venue_quality_scores_.end()) ? it->second : 0.5; // Default neutral score
    }
    
    // Get best venues for symbol (ranked by quality)
    std::vector<uint8_t> getBestVenues(uint32_t symbol_id, size_t max_venues = 5) const {
        std::shared_lock<std::shared_mutex> lock(history_mutex_);
        
        std::vector<std::pair<double, uint8_t>> venue_scores;
        
        // Get unique venues for this symbol
        std::set<uint8_t> venues;
        for (const auto& record : performance_history_) {
            if (record.symbol_id == symbol_id) {
                venues.insert(record.venue_id);
            }
        }
        
        // Calculate scores for each venue
        for (uint8_t venue_id : venues) {
            double quality = getVenueQuality(venue_id, symbol_id);
            venue_scores.emplace_back(quality, venue_id);
        }
        
        // Sort by quality (descending)
        std::sort(venue_scores.begin(), venue_scores.end(), 
                 std::greater<std::pair<double, uint8_t>>());
        
        // Return top venues
        std::vector<uint8_t> best_venues;
        for (size_t i = 0; i < std::min(max_venues, venue_scores.size()); ++i) {
            best_venues.push_back(venue_scores[i].second);
        }
        
        return best_venues;
    }
    
private:
    void updateQualityScore(uint8_t venue_id, uint32_t symbol_id) {
        // Calculate quality score based on recent performance
        std::vector<PerformanceRecord> recent_records;
        uint64_t cutoff_time = getCurrentTimeNs() - 3600000000000ULL; // Last hour
        
        for (const auto& record : performance_history_) {
            if (record.venue_id == venue_id && record.symbol_id == symbol_id &&
                record.timestamp_ns > cutoff_time) {
                recent_records.push_back(record);
            }
        }
        
        if (recent_records.empty()) return;
        
        // Calculate composite quality score
        double avg_fill_rate = 0.0;
        double avg_slippage = 0.0;
        double avg_speed = 0.0;
        
        for (const auto& record : recent_records) {
            avg_fill_rate += record.fill_rate;
            avg_slippage += record.slippage_bps;
            avg_speed += (1000.0 / (record.fill_time_ms + 1.0)); // Speed score
        }
        
        size_t n = recent_records.size();
        avg_fill_rate /= n;
        avg_slippage /= n;
        avg_speed /= n;
        
        // Normalize and combine metrics (weights can be tuned)
        double quality_score = 0.4 * avg_fill_rate +                    // 40% fill rate
                              0.3 * std::max(0.0, 1.0 - avg_slippage/100.0) + // 30% low slippage
                              0.3 * std::min(1.0, avg_speed/10.0);        // 30% speed
        
        uint64_t key = (static_cast<uint64_t>(venue_id) << 32) | symbol_id;
        venue_quality_scores_[key] = std::max(0.0, std::min(1.0, quality_score));
    }
    
    uint64_t getCurrentTimeNs() const {
        return std::chrono::high_resolution_clock::now().time_since_epoch().count();
    }
};

// Dark pool detection and hidden liquidity estimation
class DarkPoolAnalyzer {
private:
    struct DarkPoolSignal {
        uint64_t timestamp_ns;
        uint32_t symbol_id;
        uint8_t venue_id;
        double estimated_hidden_size;
        double confidence_score;
        bool is_iceberg_detected;
    };
    
    std::vector<DarkPoolSignal> signals_;
    std::unordered_map<uint64_t, double> hidden_liquidity_estimates_; // venue_id << 32 | symbol_id
    mutable std::mutex signals_mutex_;
    
public:
    // Analyze order book for hidden liquidity signals
    void analyzeOrderBook(uint8_t venue_id, uint32_t symbol_id,
                         const std::vector<double>& bid_prices,
                         const std::vector<double>& bid_sizes,
                         const std::vector<double>& ask_prices,
                         const std::vector<double>& ask_sizes) {
        
        // Look for iceberg order patterns
        bool iceberg_detected = detectIcebergOrders(bid_prices, bid_sizes, ask_prices, ask_sizes);
        
        // Estimate hidden liquidity using various signals
        double hidden_estimate = estimateHiddenLiquidity(venue_id, symbol_id, 
                                                        bid_sizes, ask_sizes);
        
        // Calculate confidence score
        double confidence = calculateConfidence(iceberg_detected, hidden_estimate);
        
        std::lock_guard<std::mutex> lock(signals_mutex_);
        
        DarkPoolSignal signal;
        signal.timestamp_ns = getCurrentTimeNs();
        signal.symbol_id = symbol_id;
        signal.venue_id = venue_id;
        signal.estimated_hidden_size = hidden_estimate;
        signal.confidence_score = confidence;
        signal.is_iceberg_detected = iceberg_detected;
        
        signals_.push_back(signal);
        
        // Keep only recent signals
        if (signals_.size() > 10000) {
            signals_.erase(signals_.begin());
        }
        
        // Update hidden liquidity estimate
        uint64_t key = (static_cast<uint64_t>(venue_id) << 32) | symbol_id;
        hidden_liquidity_estimates_[key] = hidden_estimate;
    }
    
    // Get estimated hidden liquidity for venue/symbol
    double getHiddenLiquidity(uint8_t venue_id, uint32_t symbol_id) const {
        std::lock_guard<std::mutex> lock(signals_mutex_);
        
        uint64_t key = (static_cast<uint64_t>(venue_id) << 32) | symbol_id;
        auto it = hidden_liquidity_estimates_.find(key);
        return (it != hidden_liquidity_estimates_.end()) ? it->second : 0.0;
    }
    
    // Check if venue likely has significant dark liquidity
    bool hasDarkLiquidity(uint8_t venue_id, uint32_t symbol_id) const {
        return getHiddenLiquidity(venue_id, symbol_id) > 1000.0; // $1000 threshold
    }
    
private:
    bool detectIcebergOrders(const std::vector<double>& bid_prices,
                           const std::vector<double>& bid_sizes,
                           const std::vector<double>& ask_prices,
                           const std::vector<double>& ask_sizes) {
        // Look for repeated small orders at the same price level
        std::unordered_map<int, int> price_frequency;
        
        // Discretize prices and count frequencies
        for (double price : bid_prices) {
            int price_ticks = static_cast<int>(price * 100); // Assume cent precision
            price_frequency[price_ticks]++;
        }
        
        for (double price : ask_prices) {
            int price_ticks = static_cast<int>(price * 100);
            price_frequency[price_ticks]++;
        }
        
        // If we see the same price level refreshed multiple times, it might be an iceberg
        for (const auto& [price, frequency] : price_frequency) {
            if (frequency > 5) { // Threshold for iceberg detection
                return true;
            }
        }
        
        return false;
    }
    
    double estimateHiddenLiquidity(uint8_t venue_id, uint32_t symbol_id,
                                  const std::vector<double>& bid_sizes,
                                  const std::vector<double>& ask_sizes) {
        // Simple estimation based on order size distribution
        double total_visible = 0.0;
        for (double size : bid_sizes) total_visible += size;
        for (double size : ask_sizes) total_visible += size;
        
        // Heuristic: dark pools typically have 2-5x hidden vs visible liquidity
        double hidden_multiplier = 3.0; // Can be calibrated per venue
        
        // Adjust based on venue type
        if (venue_id >= 10 && venue_id < 20) { // Assume dark pool venue IDs
            hidden_multiplier = 5.0;
        }
        
        return total_visible * hidden_multiplier;
    }
    
    double calculateConfidence(bool iceberg_detected, double hidden_estimate) {
        double base_confidence = 0.5;
        
        if (iceberg_detected) {
            base_confidence += 0.3;
        }
        
        if (hidden_estimate > 10000.0) {
            base_confidence += 0.2;
        }
        
        return std::min(1.0, base_confidence);
    }
    
    uint64_t getCurrentTimeNs() const {
        return std::chrono::high_resolution_clock::now().time_since_epoch().count();
    }
};

// Machine learning-driven venue selection
class MLVenueSelector {
private:
    struct VenueFeatures {
        // Market data features
        double spread_bps;
        double volume_rate;
        double volatility;
        double time_of_day;
        double market_regime;
        
        // Venue features
        double venue_market_share;
        double venue_fill_rate;
        double venue_speed;
        double venue_adverse_selection;
        double hidden_liquidity_ratio;
        
        // Order features
        double order_size_ratio;  // Order size / average order size
        double urgency_score;
        bool is_aggressive;
        
        // Historical features
        double recent_performance;
        double venue_momentum;    // Recent trend in venue quality
    };
    
    struct VenueModel {
        std::vector<double> weights;
        double bias;
        double accuracy;
        uint64_t last_training;
    };
    
    std::unordered_map<uint32_t, VenueModel> symbol_models_;
    
public:
    // Predict best venue for order
    uint8_t selectBestVenue(uint32_t symbol_id, double order_size,
                           const std::vector<VenueState>& available_venues,
                           bool is_aggressive = false) {
        
        if (available_venues.empty()) {
            return 0; // No venues available
        }
        
        auto it = symbol_models_.find(symbol_id);
        if (it == symbol_models_.end() || it->second.weights.empty()) {
            // Use simple fallback: best spread
            return selectBySpread(available_venues);
        }
        
        const auto& model = it->second;
        double best_score = -1e9;
        uint8_t best_venue = available_venues[0].venue_id;
        
        for (const auto& venue : available_venues) {
            if (!venue.is_operational || !venue.has_connectivity) {
                continue;
            }
            
            VenueFeatures features = extractFeatures(venue, order_size, is_aggressive);
            double score = predictVenueScore(model, features);
            
            if (score > best_score) {
                best_score = score;
                best_venue = venue.venue_id;
            }
        }
        
        return best_venue;
    }
    
    // Select multiple venues for order splitting
    std::vector<std::pair<uint8_t, double>> selectVenueAllocation(
        uint32_t symbol_id, double total_order_size,
        const std::vector<VenueState>& available_venues,
        size_t max_venues = 3) {
        
        std::vector<std::pair<double, uint8_t>> venue_scores;
        
        // Score all available venues
        for (const auto& venue : available_venues) {
            if (!venue.is_operational || !venue.has_connectivity) {
                continue;
            }
            
            VenueFeatures features = extractFeatures(venue, total_order_size, false);
            double score = 0.5; // Default score
            
            auto it = symbol_models_.find(symbol_id);
            if (it != symbol_models_.end() && !it->second.weights.empty()) {
                score = predictVenueScore(it->second, features);
            }
            
            // Adjust score based on capacity
            score *= (1.0 - venue.capacity_utilization);
            
            venue_scores.emplace_back(score, venue.venue_id);
        }
        
        // Sort by score (descending)
        std::sort(venue_scores.begin(), venue_scores.end(), std::greater<>());
        
        // Allocate order across top venues
        std::vector<std::pair<uint8_t, double>> allocation;
        double remaining_size = total_order_size;
        
        for (size_t i = 0; i < std::min(max_venues, venue_scores.size()) && remaining_size > 0; ++i) {
            uint8_t venue_id = venue_scores[i].second;
            double venue_score = venue_scores[i].first;
            
            // Allocate based on score and venue capacity
            double allocation_ratio = venue_score / (i + 1); // Diminishing allocation
            double venue_allocation = std::min(remaining_size, total_order_size * allocation_ratio);
            
            if (venue_allocation > 0) {
                allocation.emplace_back(venue_id, venue_allocation);
                remaining_size -= venue_allocation;
            }
        }
        
        // Allocate any remaining size to the best venue
        if (remaining_size > 0 && !allocation.empty()) {
            allocation[0].second += remaining_size;
        }
        
        return allocation;
    }
    
    // Train model based on execution outcomes
    void trainModel(uint32_t symbol_id, const std::vector<VenueFeatures>& features,
                   const std::vector<double>& outcomes) {
        if (features.size() != outcomes.size() || features.size() < 50) {
            return; // Insufficient training data
        }
        
        // Simple logistic regression (placeholder for more sophisticated ML)
        auto& model = symbol_models_[symbol_id];
        
        size_t num_features = sizeof(VenueFeatures) / sizeof(double);
        model.weights.resize(num_features, 0.0);
        model.bias = 0.0;
        
        // Training parameters
        double learning_rate = 0.01;
        int epochs = 100;
        
        // Simple gradient descent
        for (int epoch = 0; epoch < epochs; ++epoch) {
            double total_loss = 0.0;
            
            for (size_t i = 0; i < features.size(); ++i) {
                double prediction = predictVenueScore(model, features[i]);
                double target = outcomes[i];
                double error = prediction - target;
                
                // Update weights
                const double* feature_data = reinterpret_cast<const double*>(&features[i]);
                for (size_t j = 0; j < num_features; ++j) {
                    model.weights[j] -= learning_rate * error * feature_data[j];
                }
                model.bias -= learning_rate * error;
                
                total_loss += error * error;
            }
            
            if (total_loss < 1e-6) break; // Convergence
        }
        
        model.last_training = getCurrentTimeNs();
    }
    
private:
    uint8_t selectBySpread(const std::vector<VenueState>& venues) {
        double best_spread = 1e9;
        uint8_t best_venue = venues[0].venue_id;
        
        for (const auto& venue : venues) {
            if (venue.is_operational && venue.has_connectivity && 
                venue.spread_bps < best_spread) {
                best_spread = venue.spread_bps;
                best_venue = venue.venue_id;
            }
        }
        
        return best_venue;
    }
    
    VenueFeatures extractFeatures(const VenueState& venue, double order_size, 
                                 bool is_aggressive) {
        VenueFeatures features{};
        
        // Market data features
        features.spread_bps = venue.spread_bps;
        features.volume_rate = 1.0; // Simplified
        features.volatility = 0.5;  // Simplified
        features.time_of_day = getCurrentTimeOfDay();
        features.market_regime = 0.5; // Simplified
        
        // Venue features
        features.venue_market_share = venue.market_share;
        features.venue_fill_rate = venue.fill_rate;
        features.venue_speed = 1000.0 / (venue.average_fill_time_ms + 1.0);
        features.venue_adverse_selection = venue.adverse_selection;
        features.hidden_liquidity_ratio = venue.hidden_liquidity / 
                                         (venue.bid_size + venue.ask_size + 1.0);
        
        // Order features
        features.order_size_ratio = order_size / 1000.0; // Normalized
        features.urgency_score = is_aggressive ? 1.0 : 0.0;
        features.is_aggressive = is_aggressive;
        
        // Historical features
        features.recent_performance = venue.price_improvement;
        features.venue_momentum = 0.5; // Simplified
        
        return features;
    }
    
    double predictVenueScore(const VenueModel& model, const VenueFeatures& features) {
        double score = model.bias;
        
        const double* feature_data = reinterpret_cast<const double*>(&features);
        size_t num_features = sizeof(VenueFeatures) / sizeof(double);
        
        for (size_t i = 0; i < std::min(num_features, model.weights.size()); ++i) {
            score += model.weights[i] * feature_data[i];
        }
        
        // Apply sigmoid activation
        return 1.0 / (1.0 + std::exp(-score));
    }
    
    double getCurrentTimeOfDay() {
        auto now = std::chrono::system_clock::now();
        auto time_t = std::chrono::system_clock::to_time_t(now);
        auto tm = *std::localtime(&time_t);
        return (tm.tm_hour * 60 + tm.tm_min) / (24.0 * 60.0);
    }
    
    uint64_t getCurrentTimeNs() const {
        return std::chrono::high_resolution_clock::now().time_since_epoch().count();
    }
};

// Main Smart Order Router
class SmartOrderRouter {
private:
    VenuePerformanceTracker performance_tracker_;
    DarkPoolAnalyzer dark_pool_analyzer_;
    MLVenueSelector ml_selector_;
    
    // Venue state management
    std::unordered_map<uint8_t, VenueState> venue_states_;
    mutable std::shared_mutex venues_mutex_;
    
    // Routing statistics
    std::atomic<uint64_t> total_routes_{0};
    std::atomic<uint64_t> successful_routes_{0};
    std::atomic<double> average_improvement_bps_{0.0};
    
public:
    // Update venue state
    void updateVenueState(const VenueState& venue_state) {
        std::unique_lock<std::shared_mutex> lock(venues_mutex_);
        venue_states_[venue_state.venue_id] = venue_state;
        
        // Analyze for dark liquidity if it's a dark pool
        if (venue_state.venue_type == VenueType::DARK_POOL) {
            // Would need order book data for full analysis
            // dark_pool_analyzer_.analyzeOrderBook(...);
        }
    }
    
    // Route order to best venue(s)
    RoutingDecision routeOrder(uint32_t symbol_id, double order_size,
                              bool is_aggressive, double max_impact_bps = 50.0) {
        total_routes_.fetch_add(1);
        
        RoutingDecision decision{};
        
        // Get available venues for symbol
        std::vector<VenueState> available_venues;
        {
            std::shared_lock<std::shared_mutex> lock(venues_mutex_);
            for (const auto& [venue_id, venue_state] : venue_states_) {
                if (venue_state.symbol_id == symbol_id) {
                    available_venues.push_back(venue_state);
                }
            }
        }
        
        if (available_venues.empty()) {
            return decision; // No venues available
        }
        
        // Filter operational venues
        available_venues.erase(
            std::remove_if(available_venues.begin(), available_venues.end(),
                          [](const VenueState& venue) {
                              return !venue.is_operational || !venue.has_connectivity;
                          }),
            available_venues.end());
        
        if (available_venues.empty()) {
            return decision; // No operational venues
        }
        
        // Routing strategy based on order characteristics
        if (order_size < 1000.0) {
            // Small order - route to best single venue
            decision = routeSmallOrder(symbol_id, order_size, available_venues, is_aggressive);
        } else if (order_size > 100000.0) {
            // Large order - split across multiple venues
            decision = routeLargeOrder(symbol_id, order_size, available_venues, is_aggressive);
        } else {
            // Medium order - adaptive routing
            decision = routeMediumOrder(symbol_id, order_size, available_venues, 
                                      is_aggressive, max_impact_bps);
        }
        
        // Apply additional optimizations
        optimizeRouting(decision, available_venues);
        
        return decision;
    }
    
    // Record execution outcome for learning
    void recordExecution(uint8_t venue_id, uint32_t symbol_id, double order_size,
                        double fill_rate, double slippage_bps, double fill_time_ms,
                        bool was_aggressive, double price_improvement = 0.0) {
        
        performance_tracker_.recordExecution(venue_id, symbol_id, order_size,
                                           fill_rate, slippage_bps, fill_time_ms, was_aggressive);
        
        // Update success metrics
        if (fill_rate > 0.95) {
            successful_routes_.fetch_add(1);
            
            // Update average improvement
            double current_avg = average_improvement_bps_.load();
            uint64_t total = total_routes_.load();
            double new_avg = (current_avg * (total - 1) + price_improvement) / total;
            average_improvement_bps_.store(new_avg);
        }
    }
    
    // Get routing performance metrics
    struct RoutingMetrics {
        uint64_t total_routes;
        uint64_t successful_routes;
        double success_rate;
        double average_improvement_bps;
        std::vector<std::pair<uint8_t, double>> top_venues; // venue_id, quality_score
    };
    
    RoutingMetrics getRoutingMetrics(uint32_t symbol_id) const {
        RoutingMetrics metrics{};
        metrics.total_routes = total_routes_.load();
        metrics.successful_routes = successful_routes_.load();
        
        if (metrics.total_routes > 0) {
            metrics.success_rate = static_cast<double>(metrics.successful_routes) / 
                                  metrics.total_routes;
        }
        
        metrics.average_improvement_bps = average_improvement_bps_.load();
        
        // Get top venues for symbol
        auto best_venues = performance_tracker_.getBestVenues(symbol_id, 5);
        for (uint8_t venue_id : best_venues) {
            double quality = performance_tracker_.getVenueQuality(venue_id, symbol_id);
            metrics.top_venues.emplace_back(venue_id, quality);
        }
        
        return metrics;
    }
    
private:
    RoutingDecision routeSmallOrder(uint32_t symbol_id, double order_size,
                                   const std::vector<VenueState>& venues,
                                   bool is_aggressive) {
        RoutingDecision decision{};
        
        // For small orders, prioritize speed and low cost
        uint8_t best_venue = ml_selector_.selectBestVenue(symbol_id, order_size, venues, is_aggressive);
        
        decision.primary_venue_id = best_venue;
        decision.expected_fill_probability = 0.95;
        decision.expected_fill_time_ms = 100; // Fast execution expected
        decision.use_hidden_liquidity = false; // Not needed for small orders
        
        return decision;
    }
    
    RoutingDecision routeLargeOrder(uint32_t symbol_id, double order_size,
                                   const std::vector<VenueState>& venues,
                                   bool is_aggressive) {
        RoutingDecision decision{};
        
        // For large orders, split across multiple venues to minimize impact
        auto allocation = ml_selector_.selectVenueAllocation(symbol_id, order_size, venues, 5);
        
        if (!allocation.empty()) {
            decision.primary_venue_id = allocation[0].first;
            decision.venue_allocation = allocation;
            decision.expected_fill_probability = 0.85;
            decision.expected_fill_time_ms = 5000; // Slower but lower impact
            decision.use_hidden_liquidity = true; // Try dark pools first
            decision.enable_dark_pool_first = true;
        }
        
        return decision;
    }
    
    RoutingDecision routeMediumOrder(uint32_t symbol_id, double order_size,
                                    const std::vector<VenueState>& venues,
                                    bool is_aggressive, double max_impact_bps) {
        RoutingDecision decision{};
        
        // Adaptive routing based on market conditions
        bool use_multiple_venues = false;
        
        // Check if single-venue execution would exceed impact limit
        for (const auto& venue : venues) {
            double estimated_impact = venue.spread_bps * 0.5; // Simplified estimation
            if (estimated_impact > max_impact_bps) {
                use_multiple_venues = true;
                break;
            }
        }
        
        if (use_multiple_venues) {
            decision = routeLargeOrder(symbol_id, order_size, venues, is_aggressive);
        } else {
            decision = routeSmallOrder(symbol_id, order_size, venues, is_aggressive);
        }
        
        return decision;
    }
    
    void optimizeRouting(RoutingDecision& decision, 
                        const std::vector<VenueState>& venues) {
        // Add backup venue
        if (decision.venue_allocation.empty()) {
            // Single venue routing - add backup
            auto venue_it = std::find_if(venues.begin(), venues.end(),
                                        [&](const VenueState& venue) {
                                            return venue.venue_id != decision.primary_venue_id;
                                        });
            if (venue_it != venues.end()) {
                decision.backup_venue_id = venue_it->venue_id;
            }
        }
        
        // Enable latency arbitrage if beneficial
        decision.enable_latency_arbitrage = checkLatencyArbitrageOpportunity(venues);
        
        // Set market impact limit
        decision.max_market_impact_bps = calculateOptimalImpactLimit(venues);
    }
    
    bool checkLatencyArbitrageOpportunity(const std::vector<VenueState>& venues) {
        if (venues.size() < 2) return false;
        
        // Look for significant latency differences
        uint32_t min_latency = UINT32_MAX;
        uint32_t max_latency = 0;
        
        for (const auto& venue : venues) {
            min_latency = std::min(min_latency, venue.round_trip_latency_us);
            max_latency = std::max(max_latency, venue.round_trip_latency_us);
        }
        
        // If latency difference > 500μs, arbitrage might be profitable
        return (max_latency - min_latency) > 500;
    }
    
    double calculateOptimalImpactLimit(const std::vector<VenueState>& venues) {
        // Calculate average spread across venues
        double avg_spread = 0.0;
        for (const auto& venue : venues) {
            avg_spread += venue.spread_bps;
        }
        avg_spread /= venues.size();
        
        // Set limit as fraction of average spread
        return avg_spread * 2.0; // Allow up to 2x average spread as impact
    }
};

} // namespace HFT::Execution