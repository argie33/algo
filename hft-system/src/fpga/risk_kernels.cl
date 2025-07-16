// OpenCL kernels for FPGA-accelerated risk calculations
// Target: Sub-100ns risk checks with hardware acceleration

// Risk check result structure (must match C++ definition)
typedef struct __attribute__ ((packed)) {
    ulong timestamp;
    uint order_id;
    uint symbol_id;
    ulong price;
    ulong quantity;
    uchar risk_status;
    uchar violated_rules;
    ushort processing_time_ns;
    double exposure_impact;
    double var_impact;
    double margin_requirement;
    char padding[20];
} RiskResult;

// Position structure (must match C++ definition)
typedef struct __attribute__ ((packed)) {
    uint symbol_id;
    long net_position;
    ulong long_position;
    ulong short_position;
    ulong avg_long_price;
    ulong avg_short_price;
    double unrealized_pnl;
    double realized_pnl;
    ulong last_update_time;
    char padding[24];
} Position;

// Risk limits structure
typedef struct __attribute__ ((packed)) {
    ulong max_position_value;
    ulong max_order_value;
    ulong max_daily_volume;
    ulong max_portfolio_value;
    double max_var_percentage;
    double max_concentration;
    uint max_orders_per_second;
    uint max_cancel_ratio;
    bool enable_pre_trade_checks;
    bool enable_post_trade_checks;
    bool enable_real_time_monitoring;
} RiskLimits;

// Order data structure for kernel input
typedef struct __attribute__ ((packed)) {
    uint order_id;
    uint symbol_id;
    ulong price;
    ulong quantity;
    uchar side;
    char padding[7];
} OrderData;

// Risk rule violation flags
#define POSITION_LIMIT_EXCEEDED   0x01
#define ORDER_VALUE_EXCEEDED      0x02
#define DAILY_VOLUME_EXCEEDED     0x04
#define PORTFOLIO_VAR_EXCEEDED    0x08
#define CONCENTRATION_EXCEEDED    0x10
#define RATE_LIMIT_EXCEEDED       0x20
#define CANCEL_RATIO_EXCEEDED     0x40
#define MARGIN_INSUFFICIENT       0x80

// Utility functions
inline double calculate_order_value(ulong price, ulong quantity) {
    return ((double)price * (double)quantity) / 1000000.0;
}

inline uint find_position_index(__global Position* positions, uint position_count, uint symbol_id) {
    // Linear search for simplicity - could be optimized with hash tables
    for (uint i = 0; i < position_count; i++) {
        if (positions[i].symbol_id == symbol_id) {
            return i;
        }
    }
    return UINT_MAX; // Not found
}

inline uchar check_position_limits(__global Position* positions, uint position_count,
                                  uint symbol_id, ulong price, ulong quantity, 
                                  uchar side, __global RiskLimits* limits) {
    uint pos_idx = find_position_index(positions, position_count, symbol_id);
    
    if (pos_idx == UINT_MAX) {
        // No existing position, check if new position exceeds limits
        ulong new_position_value = price * quantity;
        if (new_position_value > limits->max_position_value) {
            return POSITION_LIMIT_EXCEEDED;
        }
        return 0;
    }
    
    // Calculate new position after this order
    Position pos = positions[pos_idx];
    long quantity_delta = (side == 0) ? (long)quantity : -(long)quantity;
    long new_net_position = pos.net_position + quantity_delta;
    
    // Calculate new position value
    ulong abs_position = (new_net_position < 0) ? (ulong)(-new_net_position) : (ulong)new_net_position;
    ulong new_position_value = abs_position * price;
    
    if (new_position_value > limits->max_position_value) {
        return POSITION_LIMIT_EXCEEDED;
    }
    
    return 0;
}

inline uchar check_order_value_limits(double order_value, __global RiskLimits* limits) {
    if (order_value > (double)limits->max_order_value) {
        return ORDER_VALUE_EXCEEDED;
    }
    return 0;
}

inline uchar check_daily_volume_limits(uint symbol_id, ulong quantity, __global RiskLimits* limits) {
    // Simplified daily volume check - in production would track per-symbol daily volumes
    if (quantity > limits->max_daily_volume) {
        return DAILY_VOLUME_EXCEEDED;
    }
    return 0;
}

inline double calculate_var_impact(__global Position* positions, uint position_count, 
                                  uint symbol_id, double order_value, uchar side) {
    // Simplified VaR calculation
    // In production, this would use historical volatility and correlations
    double volatility = 0.02; // 2% daily volatility assumption
    double var_multiplier = 1.65; // 95% confidence level
    
    return order_value * volatility * var_multiplier;
}

inline double calculate_margin_requirement(double order_value) {
    // Simplified margin calculation - 10% of order value
    return order_value * 0.1;
}

/**
 * Main risk check kernel - processes multiple orders in parallel
 * Each work item processes one order
 */
__kernel void risk_check_kernel(__global OrderData* orders,
                               __global Position* positions,
                               __global RiskLimits* limits,
                               __global RiskResult* results,
                               uint order_count) {
    
    uint gid = get_global_id(0);
    
    // Boundary check
    if (gid >= order_count) {
        return;
    }
    
    // Get the order to process
    OrderData order = orders[gid];
    
    // Initialize result structure
    RiskResult result;
    result.timestamp = 0; // Would use hardware timestamp in production
    result.order_id = order.order_id;
    result.symbol_id = order.symbol_id;
    result.price = order.price;
    result.quantity = order.quantity;
    result.risk_status = 0; // Default to pass
    result.violated_rules = 0;
    result.processing_time_ns = 0;
    result.exposure_impact = 0.0;
    result.var_impact = 0.0;
    result.margin_requirement = 0.0;
    
    // Calculate order value
    double order_value = calculate_order_value(order.price, order.quantity);
    
    // Perform risk checks
    uchar violations = 0;
    
    // Check position limits
    violations |= check_position_limits(positions, order_count, order.symbol_id,
                                       order.price, order.quantity, order.side, limits);
    
    // Check order value limits
    violations |= check_order_value_limits(order_value, limits);
    
    // Check daily volume limits
    violations |= check_daily_volume_limits(order.symbol_id, order.quantity, limits);
    
    // Calculate risk metrics
    result.exposure_impact = order_value * (order.side == 0 ? 1.0 : -1.0);
    result.var_impact = calculate_var_impact(positions, order_count, order.symbol_id, 
                                           order_value, order.side);
    result.margin_requirement = calculate_margin_requirement(order_value);
    
    // Set final status
    result.violated_rules = violations;
    result.risk_status = (violations != 0) ? 1 : 0; // 1 = fail, 0 = pass
    
    // Store result
    results[gid] = result;
}

/**
 * Portfolio risk calculation kernel
 * Calculates VaR and concentration risk for entire portfolio
 */
__kernel void portfolio_risk_kernel(__global Position* positions,
                                   __global double* var_result,
                                   __global double* concentration_result,
                                   uint position_count) {
    
    uint gid = get_global_id(0);
    uint local_id = get_local_id(0);
    uint local_size = get_local_size(0);
    
    // Local memory for reduction
    __local double local_exposures[256];
    __local double local_variances[256];
    
    // Initialize local memory
    if (local_id < 256) {
        local_exposures[local_id] = 0.0;
        local_variances[local_id] = 0.0;
    }
    barrier(CLK_LOCAL_MEM_FENCE);
    
    // Each work item processes multiple positions
    double total_exposure = 0.0;
    double total_variance = 0.0;
    double max_single_exposure = 0.0;
    
    for (uint i = gid; i < position_count; i += get_global_size(0)) {
        Position pos = positions[i];
        
        if (pos.symbol_id == 0) continue; // Skip empty positions
        
        // Calculate exposure
        double long_value = ((double)pos.long_position * (double)pos.avg_long_price) / 1000000.0;
        double short_value = ((double)pos.short_position * (double)pos.avg_short_price) / 1000000.0;
        double net_exposure = fabs(long_value - short_value);
        
        total_exposure += net_exposure;
        max_single_exposure = fmax(max_single_exposure, net_exposure);
        
        // Calculate variance contribution (simplified)
        double volatility = 0.02; // 2% daily volatility
        double variance = net_exposure * volatility;
        total_variance += variance * variance;
    }
    
    // Store in local memory for reduction
    if (local_id < local_size) {
        local_exposures[local_id] = total_exposure;
        local_variances[local_id] = total_variance;
    }
    barrier(CLK_LOCAL_MEM_FENCE);
    
    // Reduction to find total portfolio metrics
    for (uint stride = local_size / 2; stride > 0; stride /= 2) {
        if (local_id < stride) {
            local_exposures[local_id] += local_exposures[local_id + stride];
            local_variances[local_id] += local_variances[local_id + stride];
        }
        barrier(CLK_LOCAL_MEM_FENCE);
    }
    
    // Work item 0 writes final results
    if (gid == 0) {
        double portfolio_exposure = local_exposures[0];
        double portfolio_variance = local_variances[0];
        
        // Calculate VaR (95% confidence level)
        *var_result = 1.65 * sqrt(portfolio_variance);
        
        // Calculate concentration risk (max single position as % of total)
        *concentration_result = (portfolio_exposure > 0.0) ? 
                               (max_single_exposure / portfolio_exposure) : 0.0;
    }
}

/**
 * Monte Carlo VaR calculation kernel
 * Runs Monte Carlo simulations for portfolio VaR calculation
 */
__kernel void monte_carlo_var_kernel(__global Position* positions,
                                    __global double* random_numbers,
                                    __global double* scenario_results,
                                    __global double* risk_factors,
                                    uint position_count,
                                    uint num_scenarios) {
    
    uint gid = get_global_id(0);
    
    if (gid >= num_scenarios) {
        return;
    }
    
    // Initialize scenario PnL
    double scenario_pnl = 0.0;
    
    // Generate correlated risk factor moves
    // Simplified - in production would use Cholesky decomposition for correlations
    double market_move = random_numbers[gid * 10] * 0.02; // 2% market volatility
    double sector_move = random_numbers[gid * 10 + 1] * 0.015; // 1.5% sector volatility
    double idiosyncratic_move = random_numbers[gid * 10 + 2] * 0.01; // 1% idiosyncratic
    
    // Apply moves to each position
    for (uint i = 0; i < position_count; i++) {
        Position pos = positions[i];
        
        if (pos.symbol_id == 0) continue;
        
        // Calculate position value
        double avg_price = ((double)pos.avg_long_price + (double)pos.avg_short_price) / 2.0;
        double position_value = (double)pos.net_position * avg_price / 1000000.0;
        
        // Apply risk factor moves (simplified factor model)
        double beta_market = 1.0; // Market beta
        double beta_sector = 0.5;  // Sector beta
        
        double price_change = beta_market * market_move + 
                             beta_sector * sector_move + 
                             idiosyncratic_move;
        
        // Calculate PnL contribution
        scenario_pnl += position_value * price_change;
    }
    
    // Store scenario result
    scenario_results[gid] = scenario_pnl;
}

/**
 * Real-time risk monitoring kernel
 * Continuously monitors risk metrics and triggers alerts
 */
__kernel void real_time_monitor_kernel(__global Position* positions,
                                      __global RiskLimits* limits,
                                      __global uchar* alert_flags,
                                      uint position_count) {
    
    uint gid = get_global_id(0);
    
    if (gid >= position_count) {
        return;
    }
    
    Position pos = positions[gid];
    
    if (pos.symbol_id == 0) {
        alert_flags[gid] = 0;
        return;
    }
    
    uchar alerts = 0;
    
    // Check position value limits
    double long_value = ((double)pos.long_position * (double)pos.avg_long_price) / 1000000.0;
    double short_value = ((double)pos.short_position * (double)pos.avg_short_price) / 1000000.0;
    double position_value = fabs(long_value - short_value);
    
    if (position_value > (double)limits->max_position_value * 0.9) { // 90% threshold
        alerts |= POSITION_LIMIT_EXCEEDED;
    }
    
    // Check unrealized PnL
    if (pos.unrealized_pnl < -position_value * 0.05) { // 5% loss threshold
        alerts |= 0x80; // Custom alert flag
    }
    
    alert_flags[gid] = alerts;
}

/**
 * Hardware timestamp kernel
 * Provides nanosecond-precision timestamps for latency measurement
 */
__kernel void timestamp_kernel(__global ulong* timestamps) {
    uint gid = get_global_id(0);
    
    // In a real FPGA implementation, this would read from hardware timers
    // For simulation, use a cycle counter
    timestamps[gid] = 0; // Placeholder - would be hardware timestamp
}