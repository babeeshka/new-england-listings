import hashlib
import json
import time
import logging
from functools import wraps
from typing import Any, Dict, Callable, Optional
import os
import pickle

logger = logging.getLogger(__name__)


def persistent_cache(max_size: int = 1000, ttl: int = 86400, disk_persistence: bool = False,
                     cache_dir: str = ".cache", filename_prefix: str = "cache"):
    """
    Create a persistent cache with advanced features:
    - Uses LRU strategy for in-memory caching
    - Supports time-based expiration
    - Optional disk persistence
    - Cache statistics
    
    Args:
        max_size: Maximum number of items to store in memory
        ttl: Time-to-live in seconds
        disk_persistence: Whether to persist cache to disk
        cache_dir: Directory to store cache files if disk_persistence is True
        filename_prefix: Prefix for cache files if disk_persistence is True
    
    Returns:
        Decorator function
    """
    def decorator(func):
        # Initialize cache storage
        cache_storage = {}
        cache_stats = {"hits": 0, "misses": 0, "evictions": 0}

        # Store the disk_persistence setting for this specific decorator instance
        use_disk_persistence = disk_persistence

        # Create cache directory if needed and disk persistence is enabled
        if use_disk_persistence:
            try:
                if not os.path.exists(cache_dir):
                    os.makedirs(cache_dir)
                    logger.debug(f"Created cache directory: {cache_dir}")
            except Exception as e:
                logger.warning(
                    f"Failed to create cache directory {cache_dir}: {e}")
                use_disk_persistence = False

        # Load from disk if enabled
        if use_disk_persistence:
            cache_file = os.path.join(
                cache_dir, f"{filename_prefix}_{func.__name__}.pkl")
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'rb') as f:
                        disk_cache = pickle.load(f)
                        cache_storage.update(disk_cache)
                        logger.debug(
                            f"Loaded {len(disk_cache)} items from disk cache for {func.__name__}")
                except Exception as e:
                    logger.warning(
                        f"Failed to load disk cache for {func.__name__}: {e}")

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create a unique cache key
            try:
                key = hashlib.md5(
                    json.dumps(
                        {
                            'args': args,
                            'kwargs': kwargs
                        },
                        sort_keys=True,
                        default=str  # Handle non-serializable objects
                    ).encode()
                ).hexdigest()
            except Exception as e:
                logger.warning(f"Failed to create cache key: {e}")
                return func(*args, **kwargs)

            # Check cache
            cached_result = cache_storage.get(key)
            current_time = time.time()

            if cached_result and current_time - cached_result['timestamp'] < ttl:
                cache_stats["hits"] += 1
                logger.debug(f"Cache hit for {func.__name__}")
                return cached_result['value']

            # Cache miss or expired
            cache_stats["misses"] += 1
            logger.debug(f"Cache miss for {func.__name__}")

            # Compute result
            result = func(*args, **kwargs)

            # Store in cache
            if len(cache_storage) >= max_size:
                # Remove oldest entry
                oldest_key = min(
                    cache_storage, key=lambda k: cache_storage[k]['timestamp'])
                del cache_storage[oldest_key]
                cache_stats["evictions"] += 1
                logger.debug(f"Cache eviction for {func.__name__}")

            cache_storage[key] = {
                'value': result,
                'timestamp': current_time
            }

            # Persist to disk if enabled
            if use_disk_persistence:
                try:
                    cache_file = os.path.join(
                        cache_dir, f"{filename_prefix}_{func.__name__}.pkl")
                    with open(cache_file, 'wb') as f:
                        pickle.dump(cache_storage, f)
                    logger.debug(
                        f"Persisted cache to disk for {func.__name__}")
                except Exception as e:
                    logger.warning(
                        f"Failed to persist cache to disk for {func.__name__}: {e}")

            return result

        # Add functions to get cache stats and clear cache
        def get_cache_stats():
            return {
                "function": func.__name__,
                "cache_size": len(cache_storage),
                "max_size": max_size,
                "ttl": ttl,
                "hits": cache_stats["hits"],
                "misses": cache_stats["misses"],
                "evictions": cache_stats["evictions"],
                "hit_ratio": cache_stats["hits"] / (cache_stats["hits"] + cache_stats["misses"])
                if (cache_stats["hits"] + cache_stats["misses"]) > 0 else 0
            }

        def clear_cache():
            cache_storage.clear()
            cache_stats["hits"] = 0
            cache_stats["misses"] = 0
            cache_stats["evictions"] = 0
            if use_disk_persistence:
                cache_file = os.path.join(
                    cache_dir, f"{filename_prefix}_{func.__name__}.pkl")
                if os.path.exists(cache_file):
                    try:
                        os.remove(cache_file)
                    except Exception as e:
                        logger.warning(
                            f"Failed to remove disk cache file: {e}")

            return f"Cache cleared for {func.__name__}"

        wrapper.get_cache_stats = get_cache_stats
        wrapper.clear_cache = clear_cache

        return wrapper
    return decorator


def memoize(func: Callable) -> Callable:
    """Simple memoization decorator for methods with no args."""
    cache = {}

    @wraps(func)
    def wrapper(self):
        key = id(self)
        if key not in cache:
            cache[key] = func(self)
        return cache[key]

    return wrapper
