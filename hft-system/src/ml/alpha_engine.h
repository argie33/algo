#pragma once

#include <cstdint>
#include <vector>
#include <array>
#include <memory>
#include <atomic>
#include <functional>
#include <unordered_map>
#include <immintrin.h>

// TensorFlow Lite for edge inference
#ifdef USE_TENSORFLOW_LITE
#include <tensorflow/lite/interpreter.h>
#include <tensorflow/lite/model.h>
#include <tensorflow/lite/kernels/register.h>
#endif

// Intel MKL for optimized math operations
#ifdef USE_INTEL_MKL
#include <mkl.h>
#include <mkl_dnn.h>
#endif

namespace hft::ml {

/**
 * Ultra-low latency ML alpha generation engine for HFT
 * Target: <100μs for feature extraction and alpha signal generation
 * Features: Real-time feature pipeline, optimized inference, SIMD vectorization
 */
class AlphaEngine {
public:
    // Market data input structure
    struct alignas(64) MarketData {
        uint64_t timestamp;
        uint32_t symbol_id;
        uint64_t price;              // Fixed-point with 6 decimals
        uint64_t quantity;
        uint64_t bid_price;
        uint64_t ask_price;
        uint64_t bid_quantity;
        uint64_t ask_quantity;
        double last_trade_price;
        double last_trade_quantity;
        double volume_weighted_price;
        double spread_bps;
        char padding[16];
    };

    // Technical features structure
    struct alignas(64) TechnicalFeatures {
        // Price-based features
        double price_return_1m;      // 1-minute return
        double price_return_5m;      // 5-minute return
        double price_return_15m;     // 15-minute return
        double volatility_5m;        // 5-minute realized volatility
        double rsi_14;               // 14-period RSI
        double macd_signal;          // MACD signal
        double bollinger_position;   // Position within Bollinger bands
        
        // Volume-based features
        double volume_ratio;         // Current vs average volume
        double vwap_deviation;       // Deviation from VWAP
        double volume_imbalance;     // Buy vs sell volume imbalance
        
        // Microstructure features
        double spread_normalized;    // Spread / mid price
        double order_flow_imbalance; // Order flow imbalance
        double trade_intensity;      // Trades per minute
        double effective_spread;     // Effective spread (vs mid)
        
        // Cross-asset features
        double market_beta;          // Beta to market index
        double sector_momentum;      // Sector momentum
        double correlation_spy;      // Correlation to SPY
        
        char padding[32];
    };

    // Alpha signal output
    struct alignas(64) AlphaSignal {
        uint64_t timestamp;
        uint32_t symbol_id;
        double signal_strength;      // [-1, 1] signal strength
        double confidence;           // [0, 1] confidence level
        double expected_return;      // Expected return (bps)
        double risk_adjusted_return; // Sharpe-adjusted return
        uint32_t horizon_minutes;    // Signal horizon
        uint32_t model_id;          // Model that generated signal
        char padding[24];
    };

    // Feature computation configuration
    struct FeatureConfig {
        uint32_t lookback_periods;
        uint32_t update_frequency_ms;
        bool enable_technical_features;
        bool enable_microstructure_features;
        bool enable_cross_asset_features;
        bool enable_feature_scaling;
        bool enable_feature_selection;
        double feature_decay_factor;
    };

    // Model configuration
    struct ModelConfig {
        std::string model_path;
        std::string model_type;      // "tensorflow", "xgboost", "linear"
        uint32_t input_features;
        uint32_t output_signals;
        uint32_t batch_size;
        bool enable_quantization;
        bool enable_acceleration;    // Use hardware acceleration
        double confidence_threshold;
    };

    // Performance statistics
    struct alignas(64) AlphaStats {
        std::atomic<uint64_t> features_computed{0};
        std::atomic<uint64_t> signals_generated{0};
        std::atomic<uint64_t> inference_calls{0};
        std::atomic<double> avg_feature_time_us{0.0};
        std::atomic<double> avg_inference_time_us{0.0};
        std::atomic<double> avg_signal_strength{0.0};
        std::atomic<double> signal_accuracy{0.0};
        std::atomic<uint64_t> total_processing_time_us{0};
    };

private:
    FeatureConfig feature_config_;
    std::vector<ModelConfig> model_configs_;
    AlphaStats stats_;
    
    // Feature computation state
    std::unordered_map<uint32_t, std::vector<MarketData>> price_history_;
    std::unordered_map<uint32_t, std::vector<double>> feature_history_;
    std::unordered_map<uint32_t, TechnicalFeatures> latest_features_;
    
    // ML models
#ifdef USE_TENSORFLOW_LITE
    std::vector<std::unique_ptr<tflite::Interpreter>> tf_interpreters_;
    std::vector<std::unique_ptr<tflite::FlatBufferModel>> tf_models_;
#endif
    
    // Feature computation cache
    alignas(64) std::array<double, 1024> feature_buffer_;
    alignas(64) std::array<double, 1024> normalized_features_;
    alignas(64) std::array<double, 64> model_outputs_;
    
    // SIMD optimization arrays
    alignas(32) std::array<double, 256> simd_workspace_a_;
    alignas(32) std::array<double, 256> simd_workspace_b_;
    
    // Real-time feature pipeline
    std::atomic<bool> pipeline_active_{false};
    std::vector<std::thread> feature_threads_;
    
    // Signal callback
    std::function<void(const AlphaSignal&)> signal_callback_;

public:
    explicit AlphaEngine(const FeatureConfig& feature_config,
                        const std::vector<ModelConfig>& model_configs);
    ~AlphaEngine();

    // Initialization and cleanup
    bool initialize();
    void shutdown();

    // Core processing pipeline
    bool processMarketData(const MarketData& data);
    bool processBatchMarketData(const std::vector<MarketData>& batch);
    
    // Feature computation (target: <50μs)
    TechnicalFeatures computeFeatures(uint32_t symbol_id, const MarketData& latest_data);
    bool updateFeatureHistory(uint32_t symbol_id, const TechnicalFeatures& features);
    
    // Alpha signal generation (target: <50μs)
    std::vector<AlphaSignal> generateAlphaSignals(uint32_t symbol_id, 
                                                 const TechnicalFeatures& features);
    
    // Real-time processing
    void startRealTimeProcessing();
    void stopRealTimeProcessing();
    bool isProcessingActive() const;
    
    // Signal subscription
    void setSignalCallback(std::function<void(const AlphaSignal&)> callback);
    
    // Model management
    bool loadModel(const ModelConfig& config);
    bool updateModel(uint32_t model_id, const ModelConfig& config);
    void enableModel(uint32_t model_id, bool enabled);
    
    // Feature engineering
    void enableFeatureSelection(bool enable);
    void setFeatureWeights(const std::vector<double>& weights);
    std::vector<double> getFeatureImportance() const;
    
    // Performance monitoring
    const AlphaStats& getStats() const { return stats_; }
    void resetStats();
    double getAverageLatencyUs() const;
    
    // Backtesting and validation
    double backtestSignals(const std::vector<MarketData>& historical_data,
                          uint32_t start_index, uint32_t end_index);
    std::vector<double> validateSignalAccuracy(const std::vector<AlphaSignal>& signals,
                                              const std::vector<double>& actual_returns);

private:
    // Feature computation implementations
    void computePriceFeaturesSIMD(const std::vector<MarketData>& history, 
                                 TechnicalFeatures& features);
    void computeVolumeFeaturesSIMD(const std::vector<MarketData>& history,
                                  TechnicalFeatures& features);
    void computeMicrostructureFeatures(const MarketData& data, 
                                      TechnicalFeatures& features);
    void computeCrossAssetFeatures(uint32_t symbol_id, 
                                  TechnicalFeatures& features);
    
    // Technical indicator implementations (SIMD optimized)
    double computeRSI(const double* prices, size_t count, uint32_t period);
    void computeMACD(const double* prices, size_t count, 
                    double& macd, double& signal, double& histogram);
    void computeBollingerBands(const double* prices, size_t count, uint32_t period,
                              double& upper, double& middle, double& lower);
    double computeVolatility(const double* returns, size_t count);
    
    // SIMD-optimized math operations
    void vectorizedReturns(const double* prices, double* returns, size_t count);
    void vectorizedMA(const double* data, double* ma, size_t count, uint32_t period);
    void vectorizedStdDev(const double* data, double mean, double& stddev, size_t count);
    
    // Feature normalization and scaling
    void normalizeFeatures(const TechnicalFeatures& raw_features,
                          double* normalized, size_t feature_count);
    void scaleFeatures(double* features, size_t count, 
                      const std::vector<double>& means,
                      const std::vector<double>& stds);
    
    // Model inference implementations
#ifdef USE_TENSORFLOW_LITE
    std::vector<double> runTensorFlowInference(uint32_t model_id, 
                                              const double* features, 
                                              size_t feature_count);
#endif
    
    std::vector<double> runLinearModelInference(const double* features,
                                               size_t feature_count,
                                               const std::vector<double>& weights);
    
    // Signal post-processing
    void applySignalFilters(AlphaSignal& signal);
    void combineMultiModelSignals(const std::vector<AlphaSignal>& model_signals,
                                 AlphaSignal& combined_signal);
    
    // Real-time processing threads
    void featureComputationThread(uint32_t thread_id);
    void signalGenerationThread(uint32_t thread_id);
    
    // Performance optimization
    void optimizeFeatureComputation();
    void prefetchMarketData(uint32_t symbol_id);
    
    // Utility functions
    __forceinline uint64_t getCurrentTimestamp() const {
        return __rdtsc();
    }
    
    __forceinline double priceToDouble(uint64_t price) const {
        return static_cast<double>(price) / 1000000.0; // 6 decimal places
    }
    
    __forceinline uint64_t doubleToPrice(double price) const {
        return static_cast<uint64_t>(price * 1000000.0);
    }
};

/**
 * Real-time feature pipeline for continuous feature computation
 * Processes market data streams and maintains feature state
 */
class RealTimeFeaturePipeline {
private:
    AlphaEngine* alpha_engine_;
    std::atomic<bool> active_{false};
    
    // Input data queues
    LockFreeQueue<MarketData> market_data_queue_;
    LockFreeQueue<TechnicalFeatures> feature_queue_;
    
    // Processing threads
    std::vector<std::thread> worker_threads_;
    std::atomic<uint32_t> processed_count_{0};

public:
    explicit RealTimeFeaturePipeline(AlphaEngine* engine);
    ~RealTimeFeaturePipeline();
    
    bool start(uint32_t worker_count = 4);
    void stop();
    
    bool enqueueMarketData(const MarketData& data);
    bool dequeueFeatures(TechnicalFeatures& features);
    
    uint32_t getProcessedCount() const;
    uint32_t getQueueSize() const;

private:
    void workerThread(uint32_t thread_id);
};

/**
 * Multi-model ensemble for robust alpha generation
 * Combines signals from multiple models with dynamic weighting
 */
class AlphaEnsemble {
private:
    struct ModelWeight {
        uint32_t model_id;
        double weight;
        double recent_performance;
        uint64_t last_update_time;
    };
    
    std::vector<ModelWeight> model_weights_;
    std::vector<AlphaSignal> recent_signals_;
    
    // Ensemble parameters
    double decay_factor_;
    uint32_t performance_window_;
    double min_confidence_threshold_;

public:
    explicit AlphaEnsemble(double decay_factor = 0.95,
                          uint32_t performance_window = 100,
                          double min_confidence = 0.3);
    
    // Model management
    void addModel(uint32_t model_id, double initial_weight);
    void removeModel(uint32_t model_id);
    void updateModelWeight(uint32_t model_id, double new_weight);
    
    // Signal combination
    AlphaSignal combineSignals(const std::vector<AlphaSignal>& model_signals);
    
    // Performance tracking
    void updatePerformance(uint32_t model_id, double realized_return);
    double getModelPerformance(uint32_t model_id) const;
    
    // Dynamic reweighting
    void rebalanceWeights();
    std::vector<double> getModelWeights() const;

private:
    ModelWeight* findModel(uint32_t model_id);
    double calculatePerformanceScore(const ModelWeight& model) const;
    void normalizeWeights();
};

/**
 * Alpha strategy backtesting framework
 * Validates alpha signals against historical data
 */
class AlphaBacktester {
private:
    struct BacktestResult {
        double total_return;
        double sharpe_ratio;
        double max_drawdown;
        double hit_rate;
        double average_holding_period;
        uint64_t total_trades;
        std::vector<double> daily_returns;
    };
    
    AlphaEngine* alpha_engine_;
    std::vector<MarketData> historical_data_;
    
    // Backtest parameters
    double transaction_cost_bps_;
    double slippage_bps_;
    uint32_t max_position_size_;
    double risk_limit_;

public:
    explicit AlphaBacktester(AlphaEngine* engine,
                            double transaction_cost = 1.0,
                            double slippage = 0.5);
    
    // Data management
    bool loadHistoricalData(const std::string& data_file);
    void addMarketData(const MarketData& data);
    
    // Backtesting
    BacktestResult runBacktest(uint64_t start_time, uint64_t end_time);
    BacktestResult runWalkForwardTest(uint32_t training_days, uint32_t test_days);
    
    // Analysis
    std::vector<double> analyzeSignalDecay(uint32_t max_horizon_minutes);
    double calculateInformationRatio(const std::vector<AlphaSignal>& signals,
                                    const std::vector<double>& returns);
    
    // Risk analysis
    double calculateVaR(const std::vector<double>& returns, double confidence = 0.05);
    double calculateMaxDrawdown(const std::vector<double>& equity_curve);

private:
    double simulateTrade(const AlphaSignal& signal, const MarketData& entry_data,
                        const MarketData& exit_data);
    std::vector<double> generateEquityCurve(const std::vector<double>& returns);
};

} // namespace hft::ml