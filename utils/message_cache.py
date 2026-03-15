"""
Message Cache - Discord Message Caching System

This module provides an LRU cache with TTL for Discord messages to reduce
API calls and prevent rate limiting.

Features:
- LRU eviction (max 1000 messages)
- TTL expiration (10 minutes default)
- Async-safe with locks
- Automatic invalidation on edits/deletes
- Cache statistics tracking
"""

import asyncio
import time
import logging
from typing import Optional, Dict, Any
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


class MessageCache:
    """
    LRU cache for Discord messages with TTL.
    
    This cache reduces API calls by storing recently accessed messages
    in memory with automatic expiration and eviction.
    
    Example:
        cache = MessageCache(max_size=1000, ttl=600)
        
        # Try to get from cache
        message = cache.get(channel_id, message_id)
        if not message:
            message = await channel.fetch_message(message_id)
            cache.set(channel_id, message_id, message)
    """
    
    def __init__(self, max_size: int = 1000, ttl: float = 600.0):
        """
        Initialize the message cache.
        
        Args:
            max_size: Maximum number of messages to cache
            ttl: Time-to-live in seconds (default: 10 minutes)
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
        
        log.info(f"MessageCache initialized (max_size={max_size}, ttl={ttl}s)")
    
    def _make_key(self, channel_id: str, message_id: str) -> str:
        """Create cache key from channel and message IDs."""
        return f"{channel_id}:{message_id}"
    
    def _is_expired(self, cached: CachedMessage) -> bool:
        """Check if cached message has expired."""
        return (time.time() - cached.cached_at) > self.ttl
    
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
                return None
            
            cached = self._cache[key]
            
            # Check if expired
            if self._is_expired(cached):
                self._cache.pop(key)
                self._expirations += 1
                self._misses += 1
                log.debug(f"Cache expired for message {message_id}")
                return None
            
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            cached.access_count += 1
            self._hits += 1
            
            log.debug(f"Cache hit for message {message_id} (accessed {cached.access_count} times)")
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
                log.debug(f"Updated cache for message {message_id}")
                return
            
            # Check if we need to evict
            if len(self._cache) >= self.max_size:
                # Remove oldest (first item)
                evicted_key, _ = self._cache.popitem(last=False)
                self._evictions += 1
                log.debug(f"Evicted oldest message from cache: {evicted_key}")
            
            # Add new entry
            self._cache[key] = CachedMessage(
                message=message,
                cached_at=time.time()
            )
            log.debug(f"Cached message {message_id}")
    
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
                log.debug(f"Invalidated cache for message {message_id}")
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
            
            if expired_keys:
                log.debug(f"Cleaned up {len(expired_keys)} expired messages")
            
            return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
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
            "total_requests": total_requests
        }
    
    def reset_stats(self) -> None:
        """Reset cache statistics."""
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._expirations = 0
        log.info("Cache statistics reset")


# Global cache instance
_global_cache: Optional[MessageCache] = None


def get_message_cache() -> MessageCache:
    """Get the global message cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = MessageCache(max_size=1000, ttl=600.0)
    return _global_cache


async def fetch_message_cached(
    channel: discord.TextChannel,
    message_id: str
) -> Optional[discord.Message]:
    """
    Fetch a message with caching.
    
    This is a drop-in replacement for channel.fetch_message() that
    uses the cache to reduce API calls.
    
    Args:
        channel: Discord channel
        message_id: Message ID to fetch
        
    Returns:
        Discord message if found, None otherwise
    """
    cache = get_message_cache()
    channel_id = str(channel.id)
    
    # Try cache first
    cached_msg = await cache.get(channel_id, message_id)
    if cached_msg:
        return cached_msg
    
    # Cache miss - fetch from API
    try:
        message = await channel.fetch_message(int(message_id))
        await cache.set(channel_id, message_id, message)
        return message
    except discord.NotFound:
        log.debug(f"Message {message_id} not found in channel {channel_id}")
        return None
    except discord.Forbidden:
        log.warning(f"No permission to fetch message {message_id} in channel {channel_id}")
        return None
    except discord.HTTPException as e:
        log.error(f"HTTP error fetching message {message_id}: {e}")
        return None
    except Exception as e:
        log.error(f"Unexpected error fetching message {message_id}: {e}")
        return None
