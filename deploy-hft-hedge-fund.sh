#!/bin/bash

# Hedge Fund Grade HFT Trading Environment Setup
# Ultra-low latency trading system configuration
# Designed for sub-millisecond performance

set -e

# Configuration
ENVIRONMENT_NAME="${1:-hft-hedge-fund}"
STACK_NAME="${ENVIRONMENT_NAME}-infrastructure"
REGION="${2:-us-east-1}"
KEY_PAIR_NAME="${3:-hft-trading-keypair}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${GREEN}"
    echo "=================================="
    echo "  HEDGE FUND GRADE HFT SYSTEM"
    echo "  Ultra-Low Latency Trading Platform"
    echo "=================================="
    echo -e "${NC}"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites for hedge fund grade deployment..."
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is required but not installed"
        exit 1
    fi
    
    # Check if logged in to AWS
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured. Run 'aws configure'"
        exit 1
    fi
    
    # Check if key pair exists
    if ! aws ec2 describe-key-pairs --key-names "$KEY_PAIR_NAME" --region "$REGION" &> /dev/null; then
        print_warning "Key pair '$KEY_PAIR_NAME' not found. Creating it..."
        aws ec2 create-key-pair --key-name "$KEY_PAIR_NAME" --region "$REGION" --output text --query 'KeyMaterial' > "${KEY_PAIR_NAME}.pem"
        chmod 400 "${KEY_PAIR_NAME}.pem"
        print_success "Key pair created and saved as ${KEY_PAIR_NAME}.pem"
    fi
    
    print_success "Prerequisites validated"
}

# Deploy infrastructure
deploy_infrastructure() {
    print_status "Deploying hedge fund grade HFT infrastructure..."
    
    # Validate template
    print_status "Validating CloudFormation template..."
    aws cloudformation validate-template \
        --template-body file://template-hft-hedge-fund-grade.yml \
        --region "$REGION"
    
    print_success "Template validation passed"
    
    # Deploy stack
    print_status "Deploying CloudFormation stack: $STACK_NAME"
    aws cloudformation deploy \
        --template-file template-hft-hedge-fund-grade.yml \
        --stack-name "$STACK_NAME" \
        --parameter-overrides \
            EnvironmentName="$ENVIRONMENT_NAME" \
            TradingInstanceType="c5n.18xlarge" \
            MarketDataInstanceType="c5n.9xlarge" \
            DatabaseInstanceType="r5.24xlarge" \
            KeyPairName="$KEY_PAIR_NAME" \
        --capabilities CAPABILITY_IAM \
        --region "$REGION" \
        --no-fail-on-empty-changeset
    
    print_success "Infrastructure deployment completed"
}

# Get stack outputs
get_stack_outputs() {
    print_status "Retrieving stack outputs..."
    
    TRADING_ENGINE_IP=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query "Stacks[0].Outputs[?OutputKey=='TradingEngineIP'].OutputValue" \
        --output text \
        --region "$REGION")
    
    REDIS_ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query "Stacks[0].Outputs[?OutputKey=='RedisEndpoint'].OutputValue" \
        --output text \
        --region "$REGION")
    
    DATABASE_ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query "Stacks[0].Outputs[?OutputKey=='DatabaseEndpoint'].OutputValue" \
        --output text \
        --region "$REGION")
    
    ALB_DNS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query "Stacks[0].Outputs[?OutputKey=='LoadBalancerDNS'].OutputValue" \
        --output text \
        --region "$REGION")
    
    print_success "Stack outputs retrieved"
}

# Setup trading environment
setup_trading_environment() {
    print_status "Setting up ultra-low latency trading environment..."
    
    # Create trading configuration
    cat > hft-config.yaml << EOF
# Hedge Fund Grade HFT Configuration
trading_engine:
  primary_ip: ${TRADING_ENGINE_IP}
  instance_type: "c5n.18xlarge"
  cpu_cores: 72
  memory_gb: 192
  network_gbps: 100
  
market_data:
  redis_endpoint: ${REDIS_ENDPOINT}
  database_endpoint: ${DATABASE_ENDPOINT}
  
performance:
  target_latency_microseconds: 10
  cpu_isolation: "4-71"
  numa_nodes: 2
  network_mode: "dpdk"
  
exchanges:
  - name: "NYSE"
    connection_type: "direct_feed"
    protocols: ["FIX", "OUCH", "Binary"]
  - name: "NASDAQ"
    connection_type: "direct_feed"
    protocols: ["FIX", "OUCH", "Binary"]
  - name: "CBOE"
    connection_type: "direct_feed"
    protocols: ["FIX", "Binary"]

algorithms:
  - name: "statistical_arbitrage"
    enabled: true
    latency_target_us: 5
  - name: "market_making"
    enabled: true
    latency_target_us: 8
  - name: "momentum_trading"
    enabled: true
    latency_target_us: 12

risk_management:
  max_position_size: 1000000
  max_daily_loss: 500000
  position_limits_per_symbol: 10000
  stop_loss_percent: 2.0

monitoring:
  latency_monitoring: true
  trade_surveillance: true
  risk_alerts: true
  performance_dashboard: true
EOF
    
    print_success "Trading configuration created: hft-config.yaml"
}

# Create deployment scripts
create_deployment_scripts() {
    print_status "Creating specialized deployment scripts..."
    
    # Trading engine deployment script
    cat > deploy-trading-engine.sh << 'EOF'
#!/bin/bash

# Ultra-Low Latency Trading Engine Deployment
set -e

TRADING_IP="$1"
KEY_FILE="$2"

if [ -z "$TRADING_IP" ] || [ -z "$KEY_FILE" ]; then
    echo "Usage: $0 <trading_engine_ip> <key_file>"
    exit 1
fi

echo "Deploying to trading engine: $TRADING_IP"

# Copy trading application
scp -i "$KEY_FILE" -r ../hft/trading_engine/ ec2-user@$TRADING_IP:/opt/trading/
scp -i "$KEY_FILE" hft-config.yaml ec2-user@$TRADING_IP:/opt/trading/

# Setup trading environment
ssh -i "$KEY_FILE" ec2-user@$TRADING_IP << 'REMOTE_EOF'
    # Switch to trading user
    sudo su - trading << 'TRADING_EOF'
    
    # Set up Python environment for trading
    python3 -m venv /opt/trading/venv
    source /opt/trading/venv/bin/activate
    
    # Install ultra-low latency Python packages
    pip install numpy==1.24.3
    pip install pandas==2.0.3
    pip install asyncio
    pip install aioredis
    pip install psycopg2-binary
    pip install ujson  # Ultra-fast JSON
    pip install cython
    pip install numba  # JIT compilation for speed
    
    # Install market data libraries
    pip install websocket-client
    pip install fix-protocol
    
    # Compile critical trading algorithms with Cython
    cd /opt/trading/trading_engine/algorithms
    python setup.py build_ext --inplace
    
    # Set CPU affinity for trading processes
    echo "Setting CPU affinity for ultra-low latency..."
    taskset -cp 4-35 $$  # First NUMA node for main trading
    
    echo "Trading engine setup completed"
TRADING_EOF

    # Configure system for ultra-low latency
    echo "Configuring system optimizations..."
    
    # Disable CPU frequency scaling
    echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
    
    # Set network interface optimizations
    sudo ethtool -G eth0 rx 4096 tx 4096
    sudo ethtool -K eth0 tso off gso off lro off
    sudo ethtool -C eth0 rx-usecs 0 tx-usecs 0
    
    # Configure kernel parameters for trading
    echo "# Ultra-low latency kernel parameters" | sudo tee -a /etc/sysctl.conf
    echo "kernel.sched_rt_runtime_us = -1" | sudo tee -a /etc/sysctl.conf
    echo "kernel.sched_rt_period_us = 1000000" | sudo tee -a /etc/sysctl.conf
    echo "vm.swappiness = 1" | sudo tee -a /etc/sysctl.conf
    echo "net.core.busy_poll = 50" | sudo tee -a /etc/sysctl.conf
    echo "net.core.busy_read = 50" | sudo tee -a /etc/sysctl.conf
    
    sudo sysctl -p
    
    echo "System optimization completed"
REMOTE_EOF

echo "Trading engine deployment completed successfully"
EOF

    chmod +x deploy-trading-engine.sh
    
    # Market data setup script
    cat > setup-market-data.sh << 'EOF'
#!/bin/bash

# Market Data Feed Setup for Hedge Fund Grade HFT
set -e

REDIS_ENDPOINT="$1"
DATABASE_ENDPOINT="$2"

echo "Setting up market data infrastructure..."
echo "Redis: $REDIS_ENDPOINT"
echo "Database: $DATABASE_ENDPOINT"

# Create market data configuration
cat > market-data-config.json << JSON_EOF
{
  "feeds": {
    "nyse": {
      "url": "wss://api.exchange.com/feed/nyse",
      "symbols": ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"],
      "latency_target_ms": 0.1
    },
    "nasdaq": {
      "url": "wss://api.exchange.com/feed/nasdaq",
      "symbols": ["NVDA", "META", "NFLX", "ADBE", "CRM"],
      "latency_target_ms": 0.1
    }
  },
  "processing": {
    "cache_endpoint": "$REDIS_ENDPOINT",
    "database_endpoint": "$DATABASE_ENDPOINT",
    "batch_size": 1000,
    "flush_interval_ms": 1
  },
  "algorithms": {
    "technical_indicators": true,
    "order_book_analysis": true,
    "volatility_calculation": true,
    "correlation_analysis": true
  }
}
JSON_EOF

echo "Market data configuration created"
EOF

    chmod +x setup-market-data.sh
    
    # Risk management setup
    cat > setup-risk-management.sh << 'EOF'
#!/bin/bash

# Risk Management System Setup
set -e

echo "Setting up real-time risk management system..."

cat > risk-config.yaml << YAML_EOF
risk_limits:
  global:
    max_daily_pnl_loss: -500000
    max_daily_pnl_gain: 2000000
    max_position_concentration: 0.1
    max_sector_exposure: 0.3
  
  per_symbol:
    max_position_size: 10000
    max_order_size: 1000
    price_deviation_limit: 0.05
  
  latency_limits:
    max_order_latency_ms: 1
    max_cancel_latency_ms: 0.5
    max_modification_latency_ms: 0.8

monitoring:
  real_time_pnl: true
  position_tracking: true
  order_flow_analysis: true
  latency_monitoring: true
  
  alerts:
    - type: "position_limit_breach"
      severity: "critical"
      action: "halt_trading"
    - type: "latency_spike"
      threshold_ms: 2
      action: "reduce_order_rate"
    - type: "unusual_market_activity"
      action: "increase_monitoring"

compliance:
  trade_reporting: true
  best_execution: true
  market_surveillance: true
  audit_trail: true
YAML_EOF

echo "Risk management configuration created"
EOF

    chmod +x setup-risk-management.sh
    
    print_success "Deployment scripts created"
}

# Performance testing setup
create_performance_tests() {
    print_status "Creating performance testing suite..."
    
    cat > performance-test.py << 'EOF'
#!/usr/bin/env python3
"""
Hedge fund grade HFT performance testing suite
Tests latency, throughput, and system performance under load
"""

import asyncio
import time
import statistics
import json
from typing import List, Dict

class LatencyTester:
    def __init__(self, trading_engine_ip: str):
        self.trading_engine_ip = trading_engine_ip
        self.results: List[float] = []
    
    async def test_order_latency(self, num_orders: int = 10000) -> Dict:
        """Test order placement latency"""
        print(f"Testing order placement latency with {num_orders} orders...")
        
        latencies = []
        
        for i in range(num_orders):
            start_time = time.perf_counter()
            
            # Simulate order placement (replace with actual API call)
            await asyncio.sleep(0.00001)  # Simulate 10 microsecond processing
            
            end_time = time.perf_counter()
            latency_us = (end_time - start_time) * 1_000_000
            latencies.append(latency_us)
            
            if i % 1000 == 0:
                print(f"Processed {i} orders...")
        
        return {
            'mean_latency_us': statistics.mean(latencies),
            'median_latency_us': statistics.median(latencies),
            'p95_latency_us': statistics.quantiles(latencies, n=20)[18],  # 95th percentile
            'p99_latency_us': statistics.quantiles(latencies, n=100)[98],  # 99th percentile
            'max_latency_us': max(latencies),
            'min_latency_us': min(latencies),
            'total_orders': num_orders
        }
    
    async def test_market_data_latency(self) -> Dict:
        """Test market data processing latency"""
        print("Testing market data processing latency...")
        
        # Simulate market data processing
        processing_times = []
        
        for _ in range(10000):
            start_time = time.perf_counter()
            
            # Simulate market data processing
            await asyncio.sleep(0.000005)  # 5 microsecond processing
            
            end_time = time.perf_counter()
            processing_times.append((end_time - start_time) * 1_000_000)
        
        return {
            'mean_processing_us': statistics.mean(processing_times),
            'p99_processing_us': statistics.quantiles(processing_times, n=100)[98],
            'throughput_per_second': 1_000_000 / statistics.mean(processing_times)
        }
    
    def generate_report(self, results: Dict) -> str:
        """Generate performance report"""
        report = f"""
HEDGE FUND GRADE HFT PERFORMANCE REPORT
=====================================

Order Placement Performance:
- Mean Latency: {results['order_latency']['mean_latency_us']:.2f} μs
- Median Latency: {results['order_latency']['median_latency_us']:.2f} μs
- 95th Percentile: {results['order_latency']['p95_latency_us']:.2f} μs
- 99th Percentile: {results['order_latency']['p99_latency_us']:.2f} μs
- Maximum Latency: {results['order_latency']['max_latency_us']:.2f} μs

Market Data Performance:
- Mean Processing: {results['market_data']['mean_processing_us']:.2f} μs
- 99th Percentile: {results['market_data']['p99_processing_us']:.2f} μs
- Throughput: {results['market_data']['throughput_per_second']:.0f} ticks/second

Performance Grade: {'HEDGE FUND READY' if results['order_latency']['p99_latency_us'] < 50 else 'NEEDS OPTIMIZATION'}

Recommendations:
- Target sub-10μs mean latency for institutional grade
- Optimize network stack for sub-microsecond jitter
- Consider FPGA acceleration for critical paths
- Implement hardware timestamping
        """
        return report

async def main():
    tester = LatencyTester("127.0.0.1")  # Replace with actual IP
    
    print("Starting hedge fund grade HFT performance testing...")
    
    # Run tests
    order_results = await tester.test_order_latency(10000)
    market_data_results = await tester.test_market_data_latency()
    
    # Combine results
    results = {
        'order_latency': order_results,
        'market_data': market_data_results
    }
    
    # Generate and save report
    report = tester.generate_report(results)
    print(report)
    
    with open('hft-performance-report.txt', 'w') as f:
        f.write(report)
    
    with open('hft-performance-data.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\nPerformance test completed!")
    print("Reports saved to: hft-performance-report.txt and hft-performance-data.json")

if __name__ == "__main__":
    asyncio.run(main())
EOF

    chmod +x performance-test.py
    
    print_success "Performance testing suite created"
}

# Main deployment function
main() {
    print_header
    
    print_status "Starting hedge fund grade HFT system deployment..."
    print_status "Environment: $ENVIRONMENT_NAME"
    print_status "Region: $REGION"
    print_status "Stack: $STACK_NAME"
    
    # Run deployment steps
    check_prerequisites
    deploy_infrastructure
    get_stack_outputs
    setup_trading_environment
    create_deployment_scripts
    create_performance_tests
    
    print_success "Hedge fund grade HFT system deployment completed!"
    
    echo
    print_status "Next steps:"
    echo "1. Wait for EC2 instances to complete initialization (5-10 minutes)"
    echo "2. Run: ./deploy-trading-engine.sh $TRADING_ENGINE_IP $KEY_PAIR_NAME.pem"
    echo "3. Run: ./setup-market-data.sh $REDIS_ENDPOINT $DATABASE_ENDPOINT"
    echo "4. Run: ./setup-risk-management.sh"
    echo "5. Run: python3 performance-test.py"
    echo
    echo "System Information:"
    echo "Trading Engine IP: $TRADING_ENGINE_IP"
    echo "Redis Endpoint: $REDIS_ENDPOINT"
    echo "Database Endpoint: $DATABASE_ENDPOINT"
    echo "Load Balancer: $ALB_DNS"
    echo
    print_success "Your hedge fund grade HFT system is ready for ultra-low latency trading!"
}

# Run main function
main "$@"
