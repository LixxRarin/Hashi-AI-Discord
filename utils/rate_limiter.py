"""
Rate Limiter - Discord API Rate Limiting Protection

This module provides rate limiting and exponential backoff to prevent
Discord API rate limit errors (HTTP 429).

Features:
- Token bucket algorithm for rate limiting
- Exponential backoff with retry on 429 errors
- Respects Discord's Retry-After header
- Async-safe with locks
"""

import asyncio
import time
import logging
from typing import Callable, Any, Optional

import discord

log = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter for Discord API requests.
    
    This prevents bursts of requests that would trigger rate limiting.
    Tokens are refilled at a constant rate, and each request consumes one token.
    
    Example:
        limiter = RateLimiter(rate=50.0, burst=10)
        await limiter.acquire()  # Wait for permission
        # Make API request
    """
    
    def __init__(self, rate: float = 50.0, burst: int = 10):
        """
        Initialize the rate limiter.
        
        Args:
            rate: Requests per second (default: 50, Discord's typical limit)
            burst: Maximum burst size (default: 10)
        """
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = time.time()
        self._lock = asyncio.Lock()
        
        log.info(f"RateLimiter initialized (rate={rate}/s, burst={burst})")
    
    async def acquire(self, endpoint: str = "default") -> None:
        """
        Acquire a token, waiting if necessary.
        
        Args:
            endpoint: Endpoint identifier (for logging, not used for separate buckets yet)
        """
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            
            # Refill tokens based on time elapsed
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            # If no tokens available, wait
            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) / self.rate
                log.debug(f"Rate limiter waiting {wait_time:.2f}s for token")
                await asyncio.sleep(wait_time)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0
    
    def get_stats(self) -> dict:
        """Get current rate limiter statistics."""
        return {
            "rate": self.rate,
            "burst": self.burst,
            "available_tokens": self.tokens,
            "last_update": self.last_update
        }


async def with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0
) -> Any:
    """
    Execute an async function with exponential backoff on rate limit errors.
    
    This automatically retries on HTTP 429 errors with increasing delays,
    respecting Discord's Retry-After header when available.
    
    Args:
        func: Async function to execute
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 1.0)
        
    Returns:
        Result of the function call
        
    Raises:
        Exception: If all retries are exhausted
        
    Example:
        message = await with_backoff(
            lambda: channel.fetch_message(message_id)
        )
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return await func()
        except discord.HTTPException as e:
            last_exception = e
            
            if e.status == 429:
                # Rate limited - use Retry-After header if available
                retry_after = getattr(e, 'retry_after', None)
                
                if retry_after:
                    wait_time = retry_after
                    log.warning(
                        f"Rate limited (429), Discord says wait {wait_time}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                else:
                    # Exponential backoff: 1s, 2s, 4s, 8s...
                    wait_time = base_delay * (2 ** attempt)
                    log.warning(
                        f"Rate limited (429), using exponential backoff {wait_time}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    log.error(f"Rate limit retry exhausted after {max_retries} attempts")
                    raise
            else:
                # Not a rate limit error, re-raise immediately
                raise
        except Exception as e:
            # Non-HTTP exceptions are not retried
            log.error(f"Non-retryable error in with_backoff: {e}")
            raise
    
    # Should not reach here, but just in case
    if last_exception:
        raise last_exception
    raise Exception(f"Failed after {max_retries} retries")


# Global rate limiter instance
_global_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = RateLimiter(rate=50.0, burst=10)
    return _global_limiter


def reset_rate_limiter() -> None:
    """Reset the global rate limiter (useful for testing)."""
    global _global_limiter
    _global_limiter = None
    log.info("Global rate limiter reset")
