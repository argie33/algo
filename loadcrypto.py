#!/usr/bin/env python3
"""
Cryptocurrency Data Loader - Institutional Grade Analytics
Loads comprehensive crypto market data, on-chain metrics, and DeFi analytics
"""
import sys
import time
import logging
import json
import os
import gc
import resource
from datetime import datetime, timedelta
from decimal import Decimal

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
import boto3
import requests
import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

class CryptoDataLoader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Institutional-Crypto-Analytics/1.0'
        })
        
    def get_db_config(self):
        """Get database configuration from AWS Secrets Manager"""
        try:
            secret_arn = os.environ["DB_SECRET_ARN"]
            client = boto3.client("secretsmanager")
            response = client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(response["SecretString"])
            
            return {
                "host": secret["host"],
                "port": int(secret.get("port", 5432)),
                "user": secret["username"],
                "password": secret["password"],
                "dbname": secret["dbname"]
            }
        except Exception as e:
            logger.error(f"Failed to get database config: {e}")
            raise

    def create_crypto_tables(self, cur):
        """Create all cryptocurrency tables"""
        logger.info("Creating cryptocurrency tables...")
        
        tables = [
            # Core crypto assets
            """
            CREATE TABLE IF NOT EXISTS crypto_assets (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                coingecko_id VARCHAR(255),
                contract_address VARCHAR(255),
                blockchain VARCHAR(50),
                market_cap BIGINT,
                circulating_supply DECIMAL(30, 8),
                total_supply DECIMAL(30, 8),
                max_supply DECIMAL(30, 8),
                launch_date DATE,
                website VARCHAR(255),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # Real-time price data
            """
            CREATE TABLE IF NOT EXISTS crypto_prices (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                price DECIMAL(20, 8) NOT NULL,
                market_cap BIGINT,
                volume_24h DECIMAL(30, 8),
                volume_usd DECIMAL(30, 2),
                price_change_24h DECIMAL(10, 4),
                price_change_7d DECIMAL(10, 4),
                price_change_30d DECIMAL(10, 4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, timestamp)
            )
            """,
            
            # Market dominance and metrics
            """
            CREATE TABLE IF NOT EXISTS crypto_market_metrics (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP NOT NULL,
                total_market_cap BIGINT NOT NULL,
                total_volume_24h BIGINT NOT NULL,
                btc_dominance DECIMAL(5, 2) NOT NULL,
                eth_dominance DECIMAL(5, 2) NOT NULL,
                active_cryptocurrencies INTEGER,
                market_cap_change_24h DECIMAL(10, 4),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(timestamp)
            )
            """,
            
            # Exchange data
            """
            CREATE TABLE IF NOT EXISTS crypto_exchanges (
                id SERIAL PRIMARY KEY,
                exchange_id VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                country VARCHAR(50),
                trust_score INTEGER,
                volume_24h_btc DECIMAL(20, 8),
                normalized_volume_24h_btc DECIMAL(20, 8),
                is_centralized BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # DeFi Total Value Locked
            """
            CREATE TABLE IF NOT EXISTS defi_tvl (
                id SERIAL PRIMARY KEY,
                protocol VARCHAR(100) NOT NULL,
                chain VARCHAR(50) NOT NULL,
                tvl_usd DECIMAL(30, 2) NOT NULL,
                tvl_change_24h DECIMAL(10, 4),
                tvl_change_7d DECIMAL(10, 4),
                category VARCHAR(50),
                timestamp TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(protocol, chain, timestamp)
            )
            """,
            
            # Fear and Greed Index
            """
            CREATE TABLE IF NOT EXISTS crypto_fear_greed (
                id SERIAL PRIMARY KEY,
                timestamp DATE NOT NULL UNIQUE,
                value INTEGER NOT NULL,
                value_classification VARCHAR(20) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # Top gainers/losers
            """
            CREATE TABLE IF NOT EXISTS crypto_movers (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                price DECIMAL(20, 8) NOT NULL,
                price_change_24h DECIMAL(10, 4) NOT NULL,
                volume_24h DECIMAL(30, 8),
                market_cap BIGINT,
                mover_type VARCHAR(10) NOT NULL, -- 'gainer' or 'loser'
                timestamp TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            
            # Trending cryptocurrencies
            """
            CREATE TABLE IF NOT EXISTS crypto_trending (
                id SERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                name VARCHAR(255) NOT NULL,
                coingecko_id VARCHAR(255),
                market_cap_rank INTEGER,
                search_score INTEGER,
                timestamp TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ]
        
        for i, table_sql in enumerate(tables):
            try:
                cur.execute(table_sql)
                logger.info(f"Created table {i+1}/{len(tables)}")
            except Exception as e:
                logger.error(f"Failed to create table {i+1}: {e}")
                raise
                
        # Create indexes
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_crypto_prices_symbol_timestamp ON crypto_prices(symbol, timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_crypto_prices_timestamp ON crypto_prices(timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_crypto_market_metrics_timestamp ON crypto_market_metrics(timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_defi_tvl_protocol_timestamp ON defi_tvl(protocol, timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_crypto_movers_timestamp ON crypto_movers(timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_crypto_trending_timestamp ON crypto_trending(timestamp DESC)"
        ]
        
        for idx_sql in indexes:
            cur.execute(idx_sql)
            
        logger.info("Cryptocurrency tables created successfully")

    def fetch_coingecko_data(self, endpoint, params=None):
        """Fetch data from CoinGecko API with rate limiting"""
        base_url = "https://api.coingecko.com/api/v3"
        url = f"{base_url}/{endpoint}"
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            time.sleep(1.1)  # Rate limiting for free tier
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch from CoinGecko {endpoint}: {e}")
            return None

    def load_crypto_assets(self, cur):
        """Load top crypto assets data"""
        logger.info("Loading crypto assets...")
        
        # Get top 250 cryptocurrencies by market cap
        data = self.fetch_coingecko_data("coins/markets", {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': 250,
            'page': 1,
            'sparkline': False,
            'price_change_percentage': '24h,7d,30d'
        })
        
        if not data:
            logger.error("Failed to fetch crypto assets data")
            return
            
        assets_data = []
        for coin in data:
            assets_data.append((
                coin['symbol'].upper(),
                coin['name'],
                coin['id'],
                coin.get('contract_address'),
                'ethereum' if coin.get('contract_address') else 'native',
                coin.get('market_cap'),
                coin.get('circulating_supply'),
                coin.get('total_supply'),
                coin.get('max_supply'),
                coin.get('atl_date', '').split('T')[0] if coin.get('atl_date') else None,
                coin.get('homepage', [''])[0] if coin.get('homepage') else None
            ))
        
        # Insert or update assets
        execute_values(
            cur,
            """
            INSERT INTO crypto_assets (
                symbol, name, coingecko_id, contract_address, blockchain,
                market_cap, circulating_supply, total_supply, max_supply,
                launch_date, website
            ) VALUES %s
            ON CONFLICT (symbol) DO UPDATE SET
                name = EXCLUDED.name,
                market_cap = EXCLUDED.market_cap,
                circulating_supply = EXCLUDED.circulating_supply,
                total_supply = EXCLUDED.total_supply,
                updated_at = CURRENT_TIMESTAMP
            """,
            assets_data
        )
        
        logger.info(f"Loaded {len(assets_data)} crypto assets")

    def load_crypto_prices(self, cur):
        """Load current crypto prices"""
        logger.info("Loading crypto prices...")
        
        data = self.fetch_coingecko_data("coins/markets", {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': 250,
            'page': 1,
            'sparkline': False,
            'price_change_percentage': '24h,7d,30d'
        })
        
        if not data:
            logger.error("Failed to fetch crypto prices data")
            return
            
        current_time = datetime.utcnow().replace(second=0, microsecond=0)
        prices_data = []
        
        for coin in data:
            prices_data.append((
                coin['symbol'].upper(),
                current_time,
                coin['current_price'],
                coin.get('market_cap'),
                coin.get('total_volume'),
                coin.get('total_volume'),  # volume_usd same as volume_24h for now
                coin.get('price_change_percentage_24h'),
                coin.get('price_change_percentage_7d_in_currency'),
                coin.get('price_change_percentage_30d_in_currency')
            ))
        
        execute_values(
            cur,
            """
            INSERT INTO crypto_prices (
                symbol, timestamp, price, market_cap, volume_24h, volume_usd,
                price_change_24h, price_change_7d, price_change_30d
            ) VALUES %s
            ON CONFLICT (symbol, timestamp) DO UPDATE SET
                price = EXCLUDED.price,
                market_cap = EXCLUDED.market_cap,
                volume_24h = EXCLUDED.volume_24h,
                price_change_24h = EXCLUDED.price_change_24h
            """,
            prices_data
        )
        
        logger.info(f"Loaded {len(prices_data)} crypto prices")

    def load_market_metrics(self, cur):
        """Load overall crypto market metrics"""
        logger.info("Loading crypto market metrics...")
        
        data = self.fetch_coingecko_data("global")
        
        if not data or 'data' not in data:
            logger.error("Failed to fetch market metrics")
            return
            
        global_data = data['data']
        current_time = datetime.utcnow().replace(second=0, microsecond=0)
        
        cur.execute("""
            INSERT INTO crypto_market_metrics (
                timestamp, total_market_cap, total_volume_24h, btc_dominance,
                eth_dominance, active_cryptocurrencies, market_cap_change_24h
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (timestamp) DO UPDATE SET
                total_market_cap = EXCLUDED.total_market_cap,
                total_volume_24h = EXCLUDED.total_volume_24h,
                btc_dominance = EXCLUDED.btc_dominance,
                eth_dominance = EXCLUDED.eth_dominance
        """, (
            current_time,
            global_data.get('total_market_cap', {}).get('usd', 0),
            global_data.get('total_volume', {}).get('usd', 0),
            global_data.get('market_cap_percentage', {}).get('btc', 0),
            global_data.get('market_cap_percentage', {}).get('eth', 0),
            global_data.get('active_cryptocurrencies', 0),
            global_data.get('market_cap_change_percentage_24h_usd', 0)
        ))
        
        logger.info("Loaded crypto market metrics")

    def load_fear_greed_index(self, cur):
        """Load Fear and Greed Index"""
        logger.info("Loading Fear and Greed Index...")
        
        try:
            response = self.session.get("https://api.alternative.me/fng/")
            response.raise_for_status()
            data = response.json()
            
            if 'data' in data and len(data['data']) > 0:
                fng_data = data['data'][0]
                
                cur.execute("""
                    INSERT INTO crypto_fear_greed (timestamp, value, value_classification)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (timestamp) DO UPDATE SET
                        value = EXCLUDED.value,
                        value_classification = EXCLUDED.value_classification
                """, (
                    datetime.fromtimestamp(int(fng_data['timestamp'])).date(),
                    int(fng_data['value']),
                    fng_data['value_classification']
                ))
                
                logger.info(f"Loaded Fear and Greed Index: {fng_data['value']} ({fng_data['value_classification']})")
            
        except Exception as e:
            logger.error(f"Failed to load Fear and Greed Index: {e}")

    def load_trending_cryptos(self, cur):
        """Load trending cryptocurrencies"""
        logger.info("Loading trending cryptocurrencies...")
        
        data = self.fetch_coingecko_data("search/trending")
        
        if not data or 'coins' not in data:
            logger.error("Failed to fetch trending cryptos")
            return
            
        current_time = datetime.utcnow().replace(second=0, microsecond=0)
        trending_data = []
        
        for i, coin_data in enumerate(data['coins'][:10]):  # Top 10 trending
            coin = coin_data['item']
            trending_data.append((
                coin['symbol'].upper(),
                coin['name'],
                coin['id'],
                coin.get('market_cap_rank'),
                coin.get('score', 0),
                current_time
            ))
        
        # Clear old trending data (older than 1 hour)
        cur.execute("""
            DELETE FROM crypto_trending 
            WHERE timestamp < %s
        """, (current_time - timedelta(hours=1),))
        
        execute_values(
            cur,
            """
            INSERT INTO crypto_trending (
                symbol, name, coingecko_id, market_cap_rank, search_score, timestamp
            ) VALUES %s
            """,
            trending_data
        )
        
        logger.info(f"Loaded {len(trending_data)} trending cryptocurrencies")

    def load_movers(self, cur):
        """Load top gainers and losers"""
        logger.info("Loading crypto movers...")
        
        data = self.fetch_coingecko_data("coins/markets", {
            'vs_currency': 'usd',
            'order': 'market_cap_desc',
            'per_page': 250,
            'page': 1,
            'sparkline': False,
            'price_change_percentage': '24h'
        })
        
        if not data:
            logger.error("Failed to fetch movers data")
            return
            
        # Filter and sort for gainers and losers
        filtered_data = [coin for coin in data if coin.get('price_change_percentage_24h') is not None]
        
        # Top 10 gainers
        gainers = sorted(filtered_data, key=lambda x: x['price_change_percentage_24h'], reverse=True)[:10]
        
        # Top 10 losers
        losers = sorted(filtered_data, key=lambda x: x['price_change_percentage_24h'])[:10]
        
        current_time = datetime.utcnow().replace(second=0, microsecond=0)
        
        # Clear old movers data
        cur.execute("""
            DELETE FROM crypto_movers 
            WHERE timestamp < %s
        """, (current_time - timedelta(hours=1),))
        
        movers_data = []
        
        # Add gainers
        for coin in gainers:
            movers_data.append((
                coin['symbol'].upper(),
                coin['current_price'],
                coin['price_change_percentage_24h'],
                coin.get('total_volume'),
                coin.get('market_cap'),
                'gainer',
                current_time
            ))
            
        # Add losers
        for coin in losers:
            movers_data.append((
                coin['symbol'].upper(),
                coin['current_price'],
                coin['price_change_percentage_24h'],
                coin.get('total_volume'),
                coin.get('market_cap'),
                'loser',
                current_time
            ))
        
        execute_values(
            cur,
            """
            INSERT INTO crypto_movers (
                symbol, price, price_change_24h, volume_24h, market_cap, mover_type, timestamp
            ) VALUES %s
            """,
            movers_data
        )
        
        logger.info(f"Loaded {len(movers_data)} crypto movers")

    def run(self):
        """Main execution method"""
        logger.info("🚀 Starting Crypto Data Loader")
        
        try:
            # Get database config and connect
            db_config = self.get_db_config()
            conn = psycopg2.connect(**db_config,
            sslmode='disable'
        )
            conn.autocommit = False
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Create tables
            self.create_crypto_tables(cur)
            conn.commit()
            
            # Load all data
            self.load_crypto_assets(cur)
            conn.commit()
            
            self.load_crypto_prices(cur)
            conn.commit()
            
            self.load_market_metrics(cur)
            conn.commit()
            
            self.load_fear_greed_index(cur)
            conn.commit()
            
            self.load_trending_cryptos(cur)
            conn.commit()
            
            self.load_movers(cur)
            conn.commit()
            
            # Record last run
            cur.execute("""
                INSERT INTO last_updated (script_name, last_run)
                VALUES (%s, NOW())
                ON CONFLICT (script_name) DO UPDATE
                    SET last_run = EXCLUDED.last_run
            """, ("loadcrypto.py",))
            conn.commit()
            
            logger.info("✅ Crypto data loading completed successfully")
            
        except Exception as e:
            logger.error(f"❌ Crypto data loading failed: {e}")
            if 'conn' in locals():
                conn.rollback()
            raise
        finally:
            if 'cur' in locals():
                cur.close()
            if 'conn' in locals():
                conn.close()

if __name__ == "__main__":
    loader = CryptoDataLoader()
    loader.run()# Deploy crypto data loader - Wed Jul 16 15:36:24 CDT 2025
