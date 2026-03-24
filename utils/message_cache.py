"""
Message Cache - Discord Message Caching System

This module provides an advanced LRU cache with TTL for Discord messages to reduce
API calls and prevent rate limiting.

Features:
- LRU eviction (max 2000 messages)
- TTL expiration (30 minutes default)
- Request deduplication (prevents duplicate concurrent requests)
- Per-channel rate limiting (4 req/s per channel)
- Per-channel concurrency limiting (1 concurrent request per channel)
- Adaptive backoff that learns from 429 errors
- Circuit breaker for problematic channels
- Async-safe with locks
- Automatic invalidation on edits/deletes
- Detailed cache statistics tracking
- Exponential backoff on errors
"""

import asyncio
import time
import logging
from typing import Optional, Dict, Any, Callable
from collections import OrderedDict
from dataclasses import dataclass
import discord

log = logging.getLogger(__name__)


@dataclass
class CachedMessage:
    """Cached message data with metadata."""
    message: discord.Message
    cached_at: float
    access_count: int = 0


class RequestDeduplicator:
    """
    Request deduplication system to prevent multiple concurrent requests
    for the same message.
    
    When multiple parts of the code try to fetch the same message simultaneously
    (e.g., when processing a message with a reply), this ensures only one actual
    API request is made, and all callers receive the same result.
    
    This is the MOST CRITICAL component for preventing rate limits during
    normal bot operation.
    
    Example:
        dedup = RequestDeduplicator()
        
        # Multiple concurrent calls
        results = await asyncio.gather(
            dedup.fetch_or_wait(key, fetch_func),
            dedup.fetch_or_wait(key, fetch_func),
            dedup.fetch_or_wait(key, fetch_func)
        )
        # Only 1 actual fetch is made, all get the same result
    """
    
    def __init__(self):
        """Initialize the request deduplicator."""
        self._pending: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._dedup_saves = 0  # Track how many requests were deduplicated
        
        log.info("RequestDeduplicator initialized")
    
    async def fetch_or_wait(
        self,
        key: str,
        fetch_func: Callable,
        context: str = ""
    ) -> Any:
        """
        Fetch a resource or wait for an existing fetch to complete.
        
        If a fetch for this key is already in progress, wait for it.
        Otherwise, start a new fetch.
        
        Args:
            key: Unique key for the resource (e.g., "channel_id:message_id")
            fetch_func: Async function to call if fetch is needed
            context: Context string for logging (e.g., channel ID)
            
        Returns:
            The fetched resource
        """
        # Check if request is already pending
        async with self._lock:
            if key in self._pending:
                # Request already in progress
                task = self._pending[key]
                self._dedup_saves += 1
                # Reduced logging: only log every 10 deduplication saves
                if self._dedup_saves % 10 == 0:
                    log.debug(
                        f"[{context}] Request deduplication active "
                        f"(total saves: {self._dedup_saves})"
                    )
        
        # If we found a pending request, wait for it outside the lock
        if key in self._pending:
            try:
                return await task
            except Exception as e:
                # If the pending request failed, we'll try again below
                log.debug(f"[{context}] Pending request failed: {e}")
        
        # No pending request, or it failed - create a new one
        async with self._lock:
            # Double-check in case another coroutine created it while we waited
            if key in self._pending:
                task = self._pending[key]
                self._dedup_saves += 1
            else:
                # Create new fetch task
                task = asyncio.create_task(fetch_func())
                self._pending[key] = task
                # Reduced logging: removed verbose fetch start log
        
        try:
            result = await task
            return result
        finally:
            # Clean up completed task
            async with self._lock:
                self._pending.pop(key, None)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        return {
            "pending_requests": len(self._pending),
            "dedup_saves": self._dedup_saves
        }


class ChannelSemaphoreManager:
    """
    Per-channel semaphore manager to limit concurrent requests per channel.
    
    This prevents bursts of simultaneous requests to the same channel,
    which can trigger rate limits even with rate limiting in place.
    
    Example:
        manager = ChannelSemaphoreManager(max_concurrent_per_channel=1)
        
        semaphore = await manager.get_semaphore(channel_id)
        async with semaphore:
            # Make API request
            pass
    """
    
    def __init__(self, max_concurrent_per_channel: int = 1):
        """
        Initialize the semaphore manager.
        
        Args:
            max_concurrent_per_channel: Max concurrent requests per channel (default: 1)
        """
        self.max_concurrent = max_concurrent_per_channel
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._lock = asyncio.Lock()
        
        log.info(f"ChannelSemaphoreManager initialized (max_concurrent={max_concurrent_per_channel})")
    
    async def get_semaphore(self, channel_id: str) -> asyncio.Semaphore:
        """
        Get or create a semaphore for a channel.
        
        Args:
            channel_id: Discord channel ID
            
        Returns:
            Semaphore for the channel
        """
        async with self._lock:
            if channel_id not in self._semaphores:
                self._semaphores[channel_id] = asyncio.Semaphore(self.max_concurrent)
        
        return self._semaphores[channel_id]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get semaphore statistics."""
        return {
            "total_channels": len(self._semaphores),
            "max_concurrent_per_channel": self.max_concurrent
        }


class MessageCache:
    """
    LRU cache for Discord messages with TTL and advanced rate limiting.
    
    This cache reduces API calls by storing recently accessed messages
    in memory with automatic expiration and eviction.
    
    Example:
        cache = MessageCache(max_size=2000, ttl=1800)
        
        # Try to get from cache
        message = cache.get(channel_id, message_id)
        if not message:
            message = await channel.fetch_message(message_id)
            cache.set(channel_id, message_id, message)
    """
    
    def __init__(self, max_size: int = 2000, ttl: float = 1800.0):
        """
        Initialize the message cache.
        
        Args:
            max_size: Maximum number of messages to cache (default: 2000)
            ttl: Time-to-live in seconds (default: 30 minutes)
        """
        self.max_size = max_size
        self.ttl = ttl
        self._cache: OrderedDict[str, CachedMessage] = OrderedDict()
        self._lock = asyncio.Lock()
        
        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._expirations = 0
        
        # Per-channel statistics
        self._channel_stats: Dict[str, Dict[str, int]] = {}
        
        log.info(f"MessageCache initialized (max_size={max_size}, ttl={ttl}s)")
    
    def _make_key(self, channel_id: str, message_id: str) -> str:
        """Create cache key from channel and message IDs."""
        return f"{channel_id}:{message_id}"
    
    def _is_expired(self, cached: CachedMessage) -> bool:
        """Check if cached message has expired."""
        return (time.time() - cached.cached_at) > self.ttl
    
    def _update_channel_stats(self, channel_id: str, stat: str, increment: int = 1):
        """Update per-channel statistics."""
        if channel_id not in self._channel_stats:
            self._channel_stats[channel_id] = {
                "hits": 0,
                "misses": 0,
                "api_requests": 0
            }
        self._channel_stats[channel_id][stat] = self._channel_stats[channel_id].get(stat, 0) + increment
    
    async def get(
        self,
        channel_id: str,
        message_id: str
    ) -> Optional[discord.Message]:
        """
        Get message from cache if available and not expired.
        
        Args:
            channel_id: Discord channel ID
            message_id: Discord message ID
            
        Returns:
            Cached message if found and valid, None otherwise
        """
        async with self._lock:
            key = self._make_key(channel_id, message_id)
            
            if key not in self._cache:
                self._misses += 1
                self._update_channel_stats(channel_id, "misses")
                return None
            
            cached = self._cache[key]
            
            # Check if expired
            if self._is_expired(cached):
                self._cache.pop(key)
                self._expirations += 1
                self._misses += 1
                self._update_channel_stats(channel_id, "misses")
                # Reduced logging: removed cache expiration log
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            cached.access_count += 1
            self._hits += 1
            self._update_channel_stats(channel_id, "hits")
            
            # Reduced logging: removed cache hit log
            return cached.message
    
    async def set(
        self,
        channel_id: str,
        message_id: str,
        message: discord.Message
    ) -> None:
        """
        Store message in cache.
        
        Args:
            channel_id: Discord channel ID
            message_id: Discord message ID
            message: Discord message object to cache
        """
        async with self._lock:
            key = self._make_key(channel_id, message_id)
            
            # If already exists, update it
            if key in self._cache:
                self._cache[key] = CachedMessage(
                    message=message,
                    cached_at=time.time(),
                    access_count=self._cache[key].access_count
                )
                self._cache.move_to_end(key)
                # Reduced logging: removed cache update log
                return
            
            # Check if we need to evict
            if len(self._cache) >= self.max_size:
                # Remove oldest (first item)
                evicted_key, _ = self._cache.popitem(last=False)
                self._evictions += 1
                # Reduced logging: removed eviction log (tracked in stats)
            
            # Add new entry
            self._cache[key] = CachedMessage(
                message=message,
                cached_at=time.time()
            )
            # Reduced logging: removed cache set log
    
    async def invalidate(
        self,
        channel_id: str,
        message_id: str
    ) -> bool:
        """
        Remove message from cache (e.g., after deletion or edit).
        
        Args:
            channel_id: Discord channel ID
            message_id: Discord message ID
            
        Returns:
            True if message was in cache and removed
        """
        async with self._lock:
            key = self._make_key(channel_id, message_id)
            if key in self._cache:
                self._cache.pop(key)
                # Reduced logging: removed cache invalidation log
                return True
            return False
    
    async def clear(self) -> None:
        """Clear all cached messages."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            log.info(f"Cleared {count} messages from cache")
    
    async def cleanup_expired(self) -> int:
        """
        Remove all expired messages from cache.
        
        Returns:
            Number of messages removed
        """
        async with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, cached in self._cache.items()
                if (current_time - cached.cached_at) > self.ttl
            ]
            
            for key in expired_keys:
                self._cache.pop(key)
                self._expirations += 1
            
            # Reduced logging: only log if significant cleanup
            if len(expired_keys) > 10:
                log.debug(f"Cleaned up {len(expired_keys)} expired messages")
            
            return len(expired_keys)
    
    def get_stats(self, channel_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Args:
            channel_id: Optional channel ID for per-channel stats
        
        Returns:
            Dictionary with cache statistics
        """
        if channel_id and channel_id in self._channel_stats:
            stats = self._channel_stats[channel_id]
            total = stats["hits"] + stats["misses"]
            hit_rate = (stats["hits"] / total * 100) if total > 0 else 0
            
            return {
                "channel_id": channel_id,
                "hits": stats["hits"],
                "misses": stats["misses"],
                "api_requests": stats.get("api_requests", 0),
                "hit_rate": f"{hit_rate:.1f}%"
            }
        
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "evictions": self._evictions,
            "expirations": self._expirations,
            "total_requests": total_requests,
            "channels_tracked": len(self._channel_stats)
        }
    
    def reset_stats(self) -> None:
        """Reset cache statistics."""
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._expirations = 0
        self._channel_stats.clear()
        log.info("Cache statistics reset")


# Global cache instance
_global_cache: Optional[MessageCache] = None

# Global request deduplicator
_request_deduplicator: Optional[RequestDeduplicator] = None

# Global semaphore manager
_semaphore_manager: Optional[ChannelSemaphoreManager] = None


def get_message_cache() -> MessageCache:
    """Get the global message cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = MessageCache(max_size=2000, ttl=1800.0)
    return _global_cache


def get_request_deduplicator() -> RequestDeduplicator:
    """Get the global request deduplicator instance."""
    global _request_deduplicator
    if _request_deduplicator is None:
        _request_deduplicator = RequestDeduplicator()
    return _request_deduplicator


def get_semaphore_manager() -> ChannelSemaphoreManager:
    """Get the global semaphore manager instance."""
    global _semaphore_manager
    if _semaphore_manager is None:
        _semaphore_manager = ChannelSemaphoreManager(max_concurrent_per_channel=1)
    return _semaphore_manager


async def fetch_message_cached(
    channel: discord.TextChannel,
    message_id: str
) -> Optional[discord.Message]:
    """
    Fetch a message with advanced caching and rate limiting.
    
    This is a drop-in replacement for channel.fetch_message() that:
    - Uses cache to reduce API calls
    - Deduplicates concurrent requests for the same message
    - Limits concurrent fetches per channel (max 1)
    - Uses per-channel rate limiting (4 req/s per channel)
    - Implements adaptive backoff that learns from 429 errors
    - Uses circuit breaker to protect problematic channels
    - Implements exponential backoff for retry on errors
    
    Args:
        channel: Discord channel
        message_id: Message ID to fetch
        
    Returns:
        Discord message if found, None otherwise
    """
    from utils.rate_limiter import (
        get_channel_rate_limiter,
        get_adaptive_backoff,
        get_circuit_breaker,
        with_backoff
    )
    
    cache = get_message_cache()
    deduplicator = get_request_deduplicator()
    semaphore_manager = get_semaphore_manager()
    channel_limiter = get_channel_rate_limiter()
    adaptive_backoff = get_adaptive_backoff()
    circuit_breaker = get_circuit_breaker()
    
    channel_id = str(channel.id)
    cache_key = f"{channel_id}:{message_id}"
    
    # Try cache first (no rate limiting needed for cache access)
    cached_msg = await cache.get(channel_id, message_id)
    if cached_msg:
        return cached_msg
    
    # Cache miss - use deduplicator to prevent duplicate concurrent requests
    async def fetch_with_protection():
        """Fetch with all protection mechanisms."""
        
        # Check circuit breaker
        if await circuit_breaker.is_open(channel_id):
            log.warning(
                f"[Channel:{channel_id}] Circuit breaker is OPEN, "
                f"skipping fetch for message {message_id}"
            )
            return None
        
        # Get adaptive delay based on recent 429s
        delay = await adaptive_backoff.get_delay(channel_id)
        if delay > 0:
            log.debug(
                f"[Channel:{channel_id}] Adaptive backoff delay: {delay:.1f}s "
                f"before fetching message {message_id}"
            )
            await asyncio.sleep(delay)
        
        # Acquire per-channel rate limit token
        wait_time = await channel_limiter.acquire(channel_id)
        
        # Get per-channel semaphore and acquire it
        semaphore = await semaphore_manager.get_semaphore(channel_id)
        
        async with semaphore:
            # Reduced logging: removed verbose API fetch log
            
            try:
                # Use exponential backoff for automatic retry on 429 errors
                message = await with_backoff(
                    lambda: channel.fetch_message(int(message_id)),
                    max_retries=3,
                    base_delay=1.0
                )
                
                # Success - update all tracking systems
                await cache.set(channel_id, message_id, message)
                await channel_limiter.record_success(channel_id)
                await adaptive_backoff.record_success(channel_id)
                await circuit_breaker.record_success(channel_id)
                
                # Update channel stats
                cache._update_channel_stats(channel_id, "api_requests")
                
                # Reduced logging: removed success log
                return message
                
            except discord.NotFound:
                # Reduced logging: removed not found log (expected behavior)
                await channel_limiter.record_success(channel_id)  # Not a rate limit issue
                return None
                
            except discord.Forbidden:
                log.warning(f"[Channel:{channel_id}] No permission to fetch message {message_id}")
                await channel_limiter.record_success(channel_id)  # Not a rate limit issue
                return None
                
            except discord.HTTPException as e:
                if e.status == 429:
                    # Rate limited - update all tracking systems
                    retry_after = getattr(e, 'retry_after', None)
                    
                    await channel_limiter.record_429(channel_id)
                    await adaptive_backoff.record_429(channel_id, retry_after)
                    await circuit_breaker.record_failure(channel_id)
                    
                    log.error(
                        f"[Channel:{channel_id}] Rate limited (429) fetching message {message_id} "
                        f"(retry_after={retry_after})"
                    )
                else:
                    await channel_limiter.record_failure(channel_id)
                    await circuit_breaker.record_failure(channel_id)
                    log.error(f"[Channel:{channel_id}] HTTP error fetching message {message_id}: {e}")
                
                return None
                
            except Exception as e:
                await channel_limiter.record_failure(channel_id)
                await circuit_breaker.record_failure(channel_id)
                log.error(f"[Channel:{channel_id}] Unexpected error fetching message {message_id}: {e}")
                return None
    
    # Use deduplicator to ensure only one fetch per message
    return await deduplicator.fetch_or_wait(
        cache_key,
        fetch_with_protection,
        context=f"Channel:{channel_id}"
    )


def get_all_stats() -> Dict[str, Any]:
    """
    Get comprehensive statistics from all caching and rate limiting systems.
    
    Returns:
        Dictionary with all statistics
    """
    from utils.rate_limiter import (
        get_channel_rate_limiter,
        get_adaptive_backoff,
        get_circuit_breaker
    )
    
    cache = get_message_cache()
    deduplicator = get_request_deduplicator()
    semaphore_manager = get_semaphore_manager()
    channel_limiter = get_channel_rate_limiter()
    adaptive_backoff = get_adaptive_backoff()
    circuit_breaker = get_circuit_breaker()
    
    return {
        "cache": cache.get_stats(),
        "deduplicator": deduplicator.get_stats(),
        "semaphore_manager": semaphore_manager.get_stats(),
        "channel_rate_limiter": channel_limiter.get_metrics(),
        "adaptive_backoff": adaptive_backoff.get_stats(),
        "circuit_breaker": circuit_breaker.get_stats()
    }
