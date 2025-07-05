import os
import json
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
from scoring_engine import StockScoringEngine
from datetime import datetime, timedelta
import yfinance as yf

# Initialize scoring engine
scoring_engine = StockScoringEngine()

def handler(event, context):
    """
    Main Lambda handler for stock scoring API
    """
    try:
        # Parse the request
        path = event.get('rawPath', '/')
        method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        query_params = event.get('queryStringParameters') or {}
        
        # CORS headers
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Content-Type': 'application/json'
        }
        
        # Handle OPTIONS request for CORS
        if method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': ''
            }
        
        # Route requests
        if path == '/' or path == '/health':
            return health_check(headers)
        elif path == '/scores' or path.startswith('/scores/'):
            return handle_scores_request(path, query_params, headers)
        elif path == '/stocks' or path.startswith('/stocks/'):
            return handle_stocks_request(path, query_params, headers)
        elif path == '/peer-comparison':
            return handle_peer_comparison(query_params, headers)
        elif path == '/historical-scores':
            return handle_historical_scores(query_params, headers)
        else:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'error': 'Endpoint not found'})
            }
    
    except Exception as e:
        print(f"Error in handler: {e}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': 'Internal server error', 'details': str(e)})
        }

def health_check(headers):
    """Health check endpoint"""
    return {
        'statusCode': 200,
        'headers': headers,
        'body': json.dumps({
            'status': 'healthy',
            'service': 'stock-scoring-api',
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0'
        })
    }

def handle_scores_request(path, query_params, headers):
    """Handle scoring requests"""
    try:
        # Extract symbol from path or query params
        symbol = None
        if path.startswith('/scores/'):
            symbol = path.replace('/scores/', '').upper()
        else:
            symbol = query_params.get('symbol', '').upper()
        
        if not symbol:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Symbol parameter is required'})
            }
        
        # Calculate scores
        print(f"Calculating scores for {symbol}")
        scores = scoring_engine.calculate_composite_score(symbol)
        
        if not scores:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'error': f'Unable to calculate scores for {symbol}'})
            }
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps(scores)
        }
    
    except Exception as e:
        print(f"Error calculating scores: {e}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': 'Error calculating scores', 'details': str(e)})
        }

def handle_stocks_request(path, query_params, headers):
    """Handle stock information requests"""
    try:
        # Return list of available stocks
        stocks = [
            {'symbol': 'AAPL', 'company_name': 'Apple Inc.', 'sector': 'Technology'},
            {'symbol': 'MSFT', 'company_name': 'Microsoft Corporation', 'sector': 'Technology'},
            {'symbol': 'GOOGL', 'company_name': 'Alphabet Inc.', 'sector': 'Technology'},
            {'symbol': 'AMZN', 'company_name': 'Amazon.com Inc.', 'sector': 'Consumer Discretionary'},
            {'symbol': 'NVDA', 'company_name': 'NVIDIA Corporation', 'sector': 'Technology'},
            {'symbol': 'META', 'company_name': 'Meta Platforms Inc.', 'sector': 'Technology'},
            {'symbol': 'TSLA', 'company_name': 'Tesla Inc.', 'sector': 'Consumer Discretionary'},
            {'symbol': 'BRK.B', 'company_name': 'Berkshire Hathaway Inc.', 'sector': 'Financial Services'},
            {'symbol': 'JPM', 'company_name': 'JPMorgan Chase & Co.', 'sector': 'Financial Services'},
            {'symbol': 'JNJ', 'company_name': 'Johnson & Johnson', 'sector': 'Healthcare'},
            {'symbol': 'V', 'company_name': 'Visa Inc.', 'sector': 'Financial Services'},
            {'symbol': 'PG', 'company_name': 'Procter & Gamble Co.', 'sector': 'Consumer Staples'},
            {'symbol': 'UNH', 'company_name': 'UnitedHealth Group Inc.', 'sector': 'Healthcare'},
            {'symbol': 'HD', 'company_name': 'Home Depot Inc.', 'sector': 'Consumer Discretionary'},
            {'symbol': 'MA', 'company_name': 'Mastercard Inc.', 'sector': 'Financial Services'},
            {'symbol': 'BAC', 'company_name': 'Bank of America Corp.', 'sector': 'Financial Services'},
            {'symbol': 'XOM', 'company_name': 'Exxon Mobil Corp.', 'sector': 'Energy'},
            {'symbol': 'LLY', 'company_name': 'Eli Lilly and Co.', 'sector': 'Healthcare'},
            {'symbol': 'ABBV', 'company_name': 'AbbVie Inc.', 'sector': 'Healthcare'},
            {'symbol': 'AVGO', 'company_name': 'Broadcom Inc.', 'sector': 'Technology'}
        ]
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'stocks': stocks})
        }
    
    except Exception as e:
        print(f"Error getting stocks: {e}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': 'Error getting stocks', 'details': str(e)})
        }

def handle_peer_comparison(query_params, headers):
    """Handle peer comparison requests"""
    try:
        symbol = query_params.get('symbol', '').upper()
        if not symbol:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Symbol parameter is required'})
            }
        
        # Get sector peers (simplified)
        stock = yf.Ticker(symbol)
        info = stock.info
        sector = info.get('sector', 'Technology')
        
        # Define peer groups by sector
        peer_groups = {
            'Technology': ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'META', 'AVGO'],
            'Consumer Discretionary': ['AMZN', 'TSLA', 'HD'],
            'Financial Services': ['BRK.B', 'JPM', 'V', 'MA', 'BAC'],
            'Healthcare': ['JNJ', 'UNH', 'LLY', 'ABBV'],
            'Energy': ['XOM'],
            'Consumer Staples': ['PG']
        }
        
        peers = peer_groups.get(sector, ['AAPL', 'MSFT', 'GOOGL'])
        
        # Calculate scores for each peer
        peer_scores = []
        for peer_symbol in peers[:5]:  # Limit to 5 peers
            try:
                scores = scoring_engine.calculate_composite_score(peer_symbol)
                if scores:
                    peer_scores.append({
                        'symbol': peer_symbol,
                        'name': scores['company_name'].split()[0],  # Shortened name
                        'composite': scores['composite'],
                        'quality': scores['quality']['composite'],
                        'growth': scores['growth']['composite'],
                        'value': scores['value']['composite'],
                        'momentum': scores['momentum']['composite'],
                        'sentiment': scores['sentiment']['composite'],
                        'positioning': scores['positioning']['composite']
                    })
            except Exception as e:
                print(f"Error calculating scores for peer {peer_symbol}: {e}")
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'peers': peer_scores})
        }
    
    except Exception as e:
        print(f"Error in peer comparison: {e}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': 'Error getting peer comparison', 'details': str(e)})
        }

def handle_historical_scores(query_params, headers):
    """Handle historical scores requests"""
    try:
        symbol = query_params.get('symbol', '').upper()
        period = query_params.get('period', '3M')
        
        if not symbol:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': 'Symbol parameter is required'})
            }
        
        # Generate mock historical data based on current scores
        current_scores = scoring_engine.calculate_composite_score(symbol)
        if not current_scores:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'error': f'Unable to get scores for {symbol}'})
            }
        
        # Generate historical data points
        period_days = {'1W': 7, '1M': 30, '3M': 90, '6M': 180, '1Y': 365}
        days = period_days.get(period, 90)
        
        historical_data = []
        for i in range(days):
            date = datetime.now() - timedelta(days=days-i)
            
            # Add some variation to current scores for historical simulation
            import random
            variation = random.uniform(0.9, 1.1)
            
            historical_data.append({
                'date': date.strftime('%Y-%m-%d'),
                'composite': round(current_scores['composite'] * variation, 1),
                'quality': round(current_scores['quality']['composite'] * variation, 1),
                'growth': round(current_scores['growth']['composite'] * variation, 1),
                'value': round(current_scores['value']['composite'] * variation, 1),
                'momentum': round(current_scores['momentum']['composite'] * variation, 1),
                'sentiment': round(current_scores['sentiment']['composite'] * variation, 1),
                'positioning': round(current_scores['positioning']['composite'] * variation, 1)
            })
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({'historical_scores': historical_data})
        }
    
    except Exception as e:
        print(f"Error getting historical scores: {e}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': 'Error getting historical scores', 'details': str(e)})
        }