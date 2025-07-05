#include "alpha_engine.h"
#include <algorithm>
#include <cmath>
#include <chrono>
#include <fstream>
#include <numeric>
#include <thread>
#include <iostream>

namespace hft::ml {

AlphaEngine::AlphaEngine(const FeatureConfig& feature_config,
                        const std::vector<ModelConfig>& model_configs)
    : feature_config_(feature_config), model_configs_(model_configs) {
    
    // Initialize feature and workspace arrays
    std::fill(feature_buffer_.begin(), feature_buffer_.end(), 0.0);
    std::fill(normalized_features_.begin(), normalized_features_.end(), 0.0);
    std::fill(model_outputs_.begin(), model_outputs_.end(), 0.0);
    std::fill(simd_workspace_a_.begin(), simd_workspace_a_.end(), 0.0);
    std::fill(simd_workspace_b_.begin(), simd_workspace_b_.end(), 0.0);
}

AlphaEngine::~AlphaEngine() {
    shutdown();
}

bool AlphaEngine::initialize() {
    // Load all configured models
    for (const auto& config : model_configs_) {
        if (!loadModel(config)) {
            std::cerr << "Failed to load model: " << config.model_path << std::endl;
            return false;
        }
    }
    
    // Optimize feature computation
    optimizeFeatureComputation();
    
    // Reset statistics
    resetStats();
    
    return true;
}

void AlphaEngine::shutdown() {
    // Stop real-time processing if active
    if (pipeline_active_.load()) {
        stopRealTimeProcessing();
    }
    
    // Clear model resources
#ifdef USE_TENSORFLOW_LITE
    tf_interpreters_.clear();
    tf_models_.clear();
#endif
    
    // Clear feature history
    price_history_.clear();
    feature_history_.clear();
    latest_features_.clear();
}

bool AlphaEngine::processMarketData(const MarketData& data) {
    auto start_time = getCurrentTimestamp();
    
    // Update price history
    auto& history = price_history_[data.symbol_id];
    history.push_back(data);
    
    // Maintain history size
    if (history.size() > feature_config_.lookback_periods) {
        history.erase(history.begin());
    }
    
    // Compute features if we have enough history
    if (history.size() >= 20) { // Minimum periods for technical indicators
        TechnicalFeatures features = computeFeatures(data.symbol_id, data);
        
        // Update feature history
        updateFeatureHistory(data.symbol_id, features);
        
        // Generate alpha signals
        auto signals = generateAlphaSignals(data.symbol_id, features);
        
        // Send signals via callback
        if (signal_callback_) {
            for (const auto& signal : signals) {
                signal_callback_(signal);
            }
        }
    }
    
    // Update processing time statistics
    auto end_time = getCurrentTimestamp();
    auto processing_time_us = (end_time - start_time) / 3000; // Assuming 3GHz CPU
    
    stats_.total_processing_time_us.fetch_add(processing_time_us, std::memory_order_relaxed);
    
    // Update average processing time (exponential moving average)
    double current_avg = stats_.avg_feature_time_us.load();
    double new_avg = current_avg * 0.95 + processing_time_us * 0.05;
    stats_.avg_feature_time_us.store(new_avg);
    
    return true;
}

TechnicalFeatures AlphaEngine::computeFeatures(uint32_t symbol_id, const MarketData& latest_data) {
    auto start_time = getCurrentTimestamp();
    
    TechnicalFeatures features = {};
    
    const auto& history = price_history_[symbol_id];
    if (history.size() < 20) {
        return features; // Not enough data
    }
    
    // Compute price-based features using SIMD
    if (feature_config_.enable_technical_features) {
        computePriceFeaturesSIMD(history, features);
    }
    
    // Compute volume-based features using SIMD
    computeVolumeFeaturesSIMD(history, features);
    
    // Compute microstructure features
    if (feature_config_.enable_microstructure_features) {
        computeMicrostructureFeatures(latest_data, features);
    }
    
    // Compute cross-asset features
    if (feature_config_.enable_cross_asset_features) {
        computeCrossAssetFeatures(symbol_id, features);
    }
    
    // Store latest features
    latest_features_[symbol_id] = features;
    
    auto end_time = getCurrentTimestamp();
    auto feature_time_us = (end_time - start_time) / 3000;
    
    stats_.features_computed.fetch_add(1, std::memory_order_relaxed);
    
    // Update average feature computation time
    double current_avg = stats_.avg_feature_time_us.load();
    double new_avg = current_avg * 0.95 + feature_time_us * 0.05;
    stats_.avg_feature_time_us.store(new_avg);
    
    return features;
}

void AlphaEngine::computePriceFeaturesSIMD(const std::vector<MarketData>& history, 
                                          TechnicalFeatures& features) {
    size_t count = history.size();
    if (count < 20) return;
    
    // Extract prices into aligned array
    std::vector<double> prices(count);
    for (size_t i = 0; i < count; ++i) {
        prices[i] = priceToDouble(history[i].price);
    }
    
    // Compute returns using SIMD
    std::vector<double> returns(count - 1);
    vectorizedReturns(prices.data(), returns.data(), count);
    
    // Calculate price returns for different periods
    if (count >= 2) {
        features.price_return_1m = returns.back(); // Latest 1-minute return
    }
    
    if (count >= 6) {
        // 5-minute return (last 5 periods)
        double sum = 0.0;
        for (size_t i = count - 5; i < count - 1; ++i) {
            sum += returns[i];
        }
        features.price_return_5m = sum;
    }
    
    if (count >= 16) {
        // 15-minute return (last 15 periods)
        double sum = 0.0;
        for (size_t i = count - 15; i < count - 1; ++i) {
            sum += returns[i];
        }
        features.price_return_15m = sum;
    }
    
    // Compute 5-minute realized volatility using SIMD
    if (count >= 6) {
        size_t vol_count = std::min(static_cast<size_t>(5), returns.size());
        features.volatility_5m = computeVolatility(returns.data() + returns.size() - vol_count, vol_count);
    }
    
    // Compute technical indicators
    if (count >= 14) {
        features.rsi_14 = computeRSI(prices.data(), count, 14);
    }
    
    if (count >= 26) {
        double macd, signal, histogram;
        computeMACD(prices.data(), count, macd, signal, histogram);
        features.macd_signal = signal;
    }
    
    if (count >= 20) {
        double upper, middle, lower;
        computeBollingerBands(prices.data(), count, 20, upper, middle, lower);
        double current_price = prices.back();
        features.bollinger_position = (current_price - lower) / (upper - lower);
    }
}

void AlphaEngine::computeVolumeFeaturesSIMD(const std::vector<MarketData>& history,
                                           TechnicalFeatures& features) {
    size_t count = history.size();
    if (count < 5) return;
    
    // Extract volumes
    std::vector<double> volumes(count);
    std::vector<double> prices(count);
    
    for (size_t i = 0; i < count; ++i) {
        volumes[i] = static_cast<double>(history[i].quantity);
        prices[i] = priceToDouble(history[i].price);
    }
    
    // Compute average volume using SIMD
    __m256d sum_vec = _mm256_setzero_pd();
    size_t simd_count = count / 4;
    
    for (size_t i = 0; i < simd_count; ++i) {
        __m256d vol_vec = _mm256_load_pd(&volumes[i * 4]);
        sum_vec = _mm256_add_pd(sum_vec, vol_vec);
    }
    
    double sum_array[4];
    _mm256_store_pd(sum_array, sum_vec);
    double total_volume = sum_array[0] + sum_array[1] + sum_array[2] + sum_array[3];
    
    // Handle remaining elements
    for (size_t i = simd_count * 4; i < count; ++i) {
        total_volume += volumes[i];
    }
    
    double avg_volume = total_volume / count;
    double current_volume = volumes.back();
    
    features.volume_ratio = current_volume / avg_volume;
    
    // Compute VWAP
    double total_value = 0.0;
    double total_vol = 0.0;
    
    for (size_t i = 0; i < count; ++i) {
        total_value += prices[i] * volumes[i];
        total_vol += volumes[i];
    }
    
    double vwap = (total_vol > 0) ? total_value / total_vol : 0.0;
    double current_price = prices.back();
    features.vwap_deviation = (current_price - vwap) / vwap;
    
    // Simple volume imbalance (would need bid/ask volumes in production)
    features.volume_imbalance = 0.0; // Placeholder
}

void AlphaEngine::computeMicrostructureFeatures(const MarketData& data, 
                                                TechnicalFeatures& features) {
    // Spread-based features
    if (data.bid_price > 0 && data.ask_price > 0) {
        double mid_price = (priceToDouble(data.bid_price) + priceToDouble(data.ask_price)) / 2.0;
        double spread = priceToDouble(data.ask_price) - priceToDouble(data.bid_price);
        
        features.spread_normalized = spread / mid_price;
        
        // Order flow imbalance
        double bid_qty = static_cast<double>(data.bid_quantity);
        double ask_qty = static_cast<double>(data.ask_quantity);
        double total_qty = bid_qty + ask_qty;
        
        if (total_qty > 0) {
            features.order_flow_imbalance = (bid_qty - ask_qty) / total_qty;
        }
        
        // Effective spread (simplified)
        double trade_price = priceToDouble(data.price);
        features.effective_spread = 2.0 * std::abs(trade_price - mid_price) / mid_price;
    }
    
    // Trade intensity (simplified - would need time-based calculation)
    features.trade_intensity = 1.0; // Placeholder
}

void AlphaEngine::computeCrossAssetFeatures(uint32_t symbol_id, TechnicalFeatures& features) {
    // Cross-asset features would require market index data
    // For now, use simplified placeholders
    
    features.market_beta = 1.0;      // Default market beta
    features.sector_momentum = 0.0;  // No sector data available
    features.correlation_spy = 0.0;  // No SPY data available
}

double AlphaEngine::computeRSI(const double* prices, size_t count, uint32_t period) {
    if (count <= period) return 50.0; // Neutral RSI
    
    // Compute price changes
    std::vector<double> gains, losses;
    
    for (size_t i = 1; i < count; ++i) {
        double change = prices[i] - prices[i-1];
        gains.push_back(std::max(change, 0.0));
        losses.push_back(std::max(-change, 0.0));
    }
    
    // Compute average gains and losses
    double avg_gain = 0.0, avg_loss = 0.0;
    
    // Initial averages
    for (uint32_t i = 0; i < period && i < gains.size(); ++i) {
        avg_gain += gains[i];
        avg_loss += losses[i];
    }
    avg_gain /= period;
    avg_loss /= period;
    
    // Smoothed averages
    for (size_t i = period; i < gains.size(); ++i) {
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period;
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period;
    }
    
    if (avg_loss == 0.0) return 100.0;
    
    double rs = avg_gain / avg_loss;
    return 100.0 - (100.0 / (1.0 + rs));
}

void AlphaEngine::computeMACD(const double* prices, size_t count, 
                             double& macd, double& signal, double& histogram) {
    if (count < 26) {
        macd = signal = histogram = 0.0;
        return;
    }
    
    // Compute EMAs
    std::vector<double> ema12(count), ema26(count);
    
    // EMA12
    ema12[0] = prices[0];
    double alpha12 = 2.0 / (12.0 + 1.0);
    for (size_t i = 1; i < count; ++i) {
        ema12[i] = alpha12 * prices[i] + (1.0 - alpha12) * ema12[i-1];
    }
    
    // EMA26
    ema26[0] = prices[0];
    double alpha26 = 2.0 / (26.0 + 1.0);
    for (size_t i = 1; i < count; ++i) {
        ema26[i] = alpha26 * prices[i] + (1.0 - alpha26) * ema26[i-1];
    }
    
    // MACD line
    macd = ema12.back() - ema26.back();
    
    // Signal line (simplified - would need historical MACD values)
    signal = macd; // Placeholder
    
    histogram = macd - signal;
}

void AlphaEngine::computeBollingerBands(const double* prices, size_t count, uint32_t period,
                                       double& upper, double& middle, double& lower) {
    if (count < period) {
        upper = middle = lower = 0.0;
        return;
    }
    
    // Compute moving average
    double sum = 0.0;
    size_t start_idx = count - period;
    
    for (size_t i = start_idx; i < count; ++i) {
        sum += prices[i];
    }
    middle = sum / period;
    
    // Compute standard deviation
    double var_sum = 0.0;
    for (size_t i = start_idx; i < count; ++i) {
        double diff = prices[i] - middle;
        var_sum += diff * diff;
    }
    double std_dev = std::sqrt(var_sum / period);
    
    // Bollinger bands (2 standard deviations)
    upper = middle + 2.0 * std_dev;
    lower = middle - 2.0 * std_dev;
}

double AlphaEngine::computeVolatility(const double* returns, size_t count) {
    if (count == 0) return 0.0;
    
    // Compute mean
    double mean = 0.0;
    for (size_t i = 0; i < count; ++i) {
        mean += returns[i];
    }
    mean /= count;
    
    // Compute variance using SIMD
    __m256d mean_vec = _mm256_set1_pd(mean);
    __m256d sum_vec = _mm256_setzero_pd();
    
    size_t simd_count = count / 4;
    for (size_t i = 0; i < simd_count; ++i) {
        __m256d ret_vec = _mm256_load_pd(&returns[i * 4]);
        __m256d diff_vec = _mm256_sub_pd(ret_vec, mean_vec);
        __m256d sq_vec = _mm256_mul_pd(diff_vec, diff_vec);
        sum_vec = _mm256_add_pd(sum_vec, sq_vec);
    }
    
    double sum_array[4];
    _mm256_store_pd(sum_array, sum_vec);
    double variance = sum_array[0] + sum_array[1] + sum_array[2] + sum_array[3];
    
    // Handle remaining elements
    for (size_t i = simd_count * 4; i < count; ++i) {
        double diff = returns[i] - mean;
        variance += diff * diff;
    }
    
    variance /= count;
    return std::sqrt(variance);
}

void AlphaEngine::vectorizedReturns(const double* prices, double* returns, size_t count) {
    if (count < 2) return;
    
    // Compute returns using SIMD
    size_t simd_count = (count - 1) / 4;
    
    for (size_t i = 0; i < simd_count; ++i) {
        __m256d curr_prices = _mm256_load_pd(&prices[i * 4 + 1]);
        __m256d prev_prices = _mm256_load_pd(&prices[i * 4]);
        __m256d ret_vec = _mm256_div_pd(
            _mm256_sub_pd(curr_prices, prev_prices), prev_prices);
        _mm256_store_pd(&returns[i * 4], ret_vec);
    }
    
    // Handle remaining elements
    for (size_t i = simd_count * 4; i < count - 1; ++i) {
        returns[i] = (prices[i + 1] - prices[i]) / prices[i];
    }
}

std::vector<AlphaEngine::AlphaSignal> AlphaEngine::generateAlphaSignals(
    uint32_t symbol_id, const TechnicalFeatures& features) {
    
    auto start_time = getCurrentTimestamp();
    
    std::vector<AlphaSignal> signals;
    
    // Normalize features
    double normalized[16];
    normalizeFeatures(features, normalized, 16);
    
    // Run inference on all loaded models
    for (size_t model_id = 0; model_id < model_configs_.size(); ++model_id) {
        std::vector<double> outputs;
        
#ifdef USE_TENSORFLOW_LITE
        if (model_configs_[model_id].model_type == "tensorflow" && 
            model_id < tf_interpreters_.size()) {
            outputs = runTensorFlowInference(model_id, normalized, 16);
        } else
#endif
        if (model_configs_[model_id].model_type == "linear") {
            // Simple linear model for demonstration
            std::vector<double> weights = {0.1, -0.05, 0.2, 0.15, -0.1, 0.08, 0.12, -0.3,
                                          0.25, -0.15, 0.18, 0.22, -0.08, 0.05, 0.1, -0.12};
            outputs = runLinearModelInference(normalized, 16, weights);
        }
        
        if (!outputs.empty()) {
            AlphaSignal signal = {};
            signal.timestamp = getCurrentTimestamp();
            signal.symbol_id = symbol_id;
            signal.signal_strength = std::tanh(outputs[0]); // Normalize to [-1, 1]
            signal.confidence = std::min(std::abs(outputs[0]), 1.0);
            signal.expected_return = outputs[0] * 10.0; // Convert to basis points
            signal.risk_adjusted_return = signal.expected_return / std::max(features.volatility_5m, 0.01);
            signal.horizon_minutes = 5; // 5-minute horizon
            signal.model_id = model_id;
            
            // Apply signal filters
            applySignalFilters(signal);
            
            signals.push_back(signal);
        }
    }
    
    auto end_time = getCurrentTimestamp();
    auto inference_time_us = (end_time - start_time) / 3000;
    
    stats_.signals_generated.fetch_add(signals.size(), std::memory_order_relaxed);
    stats_.inference_calls.fetch_add(1, std::memory_order_relaxed);
    
    // Update average inference time
    double current_avg = stats_.avg_inference_time_us.load();
    double new_avg = current_avg * 0.95 + inference_time_us * 0.05;
    stats_.avg_inference_time_us.store(new_avg);
    
    return signals;
}

void AlphaEngine::normalizeFeatures(const TechnicalFeatures& raw_features,
                                   double* normalized, size_t feature_count) {
    // Simple feature normalization (z-score)
    // In production, would use pre-computed means and standard deviations
    
    const double* raw_ptr = reinterpret_cast<const double*>(&raw_features);
    
    for (size_t i = 0; i < feature_count && i < 16; ++i) {
        // Simple normalization - clip to [-3, 3] range
        normalized[i] = std::max(-3.0, std::min(3.0, raw_ptr[i]));
    }
}

std::vector<double> AlphaEngine::runLinearModelInference(const double* features,
                                                        size_t feature_count,
                                                        const std::vector<double>& weights) {
    if (weights.size() != feature_count) {
        return {};
    }
    
    // Compute dot product using SIMD
    __m256d sum_vec = _mm256_setzero_pd();
    size_t simd_count = feature_count / 4;
    
    for (size_t i = 0; i < simd_count; ++i) {
        __m256d feat_vec = _mm256_load_pd(&features[i * 4]);
        __m256d weight_vec = _mm256_load_pd(&weights[i * 4]);
        __m256d prod_vec = _mm256_mul_pd(feat_vec, weight_vec);
        sum_vec = _mm256_add_pd(sum_vec, prod_vec);
    }
    
    double sum_array[4];
    _mm256_store_pd(sum_array, sum_vec);
    double result = sum_array[0] + sum_array[1] + sum_array[2] + sum_array[3];
    
    // Handle remaining elements
    for (size_t i = simd_count * 4; i < feature_count; ++i) {
        result += features[i] * weights[i];
    }
    
    return {result};
}

void AlphaEngine::applySignalFilters(AlphaSignal& signal) {
    // Apply confidence threshold
    if (signal.confidence < 0.3) {
        signal.signal_strength *= 0.5; // Reduce signal strength for low confidence
    }
    
    // Cap signal strength
    signal.signal_strength = std::max(-1.0, std::min(1.0, signal.signal_strength));
    
    // Adjust for volatility
    if (signal.risk_adjusted_return < -2.0) {
        signal.signal_strength *= 0.8; // Reduce for poor risk-adjusted returns
    }
}

bool AlphaEngine::loadModel(const ModelConfig& config) {
#ifdef USE_TENSORFLOW_LITE
    if (config.model_type == "tensorflow") {
        auto model = tflite::FlatBufferModel::BuildFromFile(config.model_path.c_str());
        if (!model) {
            return false;
        }
        
        tflite::ops::builtin::BuiltinOpResolver resolver;
        auto interpreter = std::make_unique<tflite::Interpreter>();
        
        if (tflite::InterpreterBuilder(*model, resolver)(&interpreter) != kTfLiteOk) {
            return false;
        }
        
        if (interpreter->AllocateTensors() != kTfLiteOk) {
            return false;
        }
        
        tf_models_.push_back(std::move(model));
        tf_interpreters_.push_back(std::move(interpreter));
        
        return true;
    }
#endif
    
    // For other model types, just validate the path exists
    std::ifstream file(config.model_path);
    return file.good();
}

void AlphaEngine::resetStats() {
    stats_.features_computed.store(0);
    stats_.signals_generated.store(0);
    stats_.inference_calls.store(0);
    stats_.avg_feature_time_us.store(0.0);
    stats_.avg_inference_time_us.store(0.0);
    stats_.avg_signal_strength.store(0.0);
    stats_.signal_accuracy.store(0.0);
    stats_.total_processing_time_us.store(0);
}

double AlphaEngine::getAverageLatencyUs() const {
    return stats_.avg_feature_time_us.load() + stats_.avg_inference_time_us.load();
}

void AlphaEngine::setSignalCallback(std::function<void(const AlphaSignal&)> callback) {
    signal_callback_ = callback;
}

void AlphaEngine::optimizeFeatureComputation() {
    // Pre-allocate memory pools and optimize cache access patterns
    // This would include setting up memory prefetching and SIMD optimization
}

} // namespace hft::ml