#!/usr/bin/env python3
"""
Caching Layer for Stock Analytics API
Speeds up slow endpoints (signals: 876ms → <100ms)
Uses in-memory cache with TTL
"""

import time
import json
from functools import wraps
from datetime import datetime, timedelta

class CacheManager:
    """Simple in-memory cache with TTL"""

    def __init__(self):
        self.cache = {}
        self.ttl = {}

    def get(self, key):
        """Get cached value if not expired"""
        if key not in self.cache:
            return None

        if key in self.ttl:
            if datetime.now() > self.ttl[key]:
                del self.cache[key]
                del self.ttl[key]
                return None

        return self.cache[key]

    def set(self, key, value, ttl_seconds=300):
        """Set cache value with TTL"""
        self.cache[key] = value
        self.ttl[key] = datetime.now() + timedelta(seconds=ttl_seconds)

    def clear(self):
        """Clear all cache"""
        self.cache.clear()
        self.ttl.clear()

# Global cache instance
_cache = CacheManager()

def cached(ttl_seconds=300):
    """Decorator to cache function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and args
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

            # Try to get from cache
            cached_result = _cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            # If not in cache, execute function
            result = func(*args, **kwargs)

            # Store in cache
            _cache.set(cache_key, result, ttl_seconds)

            return result

        return wrapper
    return decorator

def get_cache_stats():
    """Get cache statistics"""
    return {
        'cached_items': len(_cache.cache),
        'cache_size_bytes': len(json.dumps(_cache.cache)),
        'timestamp': datetime.now().isoformat()
    }

def clear_cache():
    """Clear all cache"""
    _cache.clear()

# Example usage for signals endpoint:
# @cached(ttl_seconds=60)  # Cache for 60 seconds
# def get_signals(symbol=None, limit=1000):
#     # ... expensive query ...
#     return signals_data
