#!/usr/bin/env python3
"""
WebSocket Server Startup Script

This script starts the WebSocket server for real-time market data feeds.
It can be run standalone or integrated with the main application.
"""

import sys
import os
import argparse
import logging
from websocket_server import WebSocketDataFeed

def setup_logging(log_level):
    """Setup logging configuration"""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('websocket_server.log')
        ]
    )

def main():
    parser = argparse.ArgumentParser(description='Start WebSocket Market Data Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8765, help='Port to bind to (default: 8765)')
    parser.add_argument('--log-level', default='INFO', 
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level (default: INFO)')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    # Create and start server
    try:
        logger.info(f"Starting WebSocket server on {args.host}:{args.port}")
        server = WebSocketDataFeed(host=args.host, port=args.port)
        
        # Run the server
        import asyncio
        asyncio.run(server.start_server())
        
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as e:
        logger.error(f"Server failed to start: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()