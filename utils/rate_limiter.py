"""
Rate Limiter - Discord API Rate Limiting Protection

This module provides comprehensive rate limiting and exponential backoff to prevent
Discord API rate limit errors (HTTP 429).

Features:
- Per-channel token bucket rate limiting
- Adaptive backoff that learns from 429 errors
- Circuit breaker for problematic channels
- Exponential backoff with retry on 429 errors
- Respects Discord's Retry-After header
- Async-safe with locks
- Detailed metrics tracking
"""

import asyncio
import time
import logging
from typing import Callable, Any, Optional, Dict
from dataclasses import dataclass, field

import discord

log = logging.getLogger(__name__)


@dataclass
class ChannelMetrics:
    """Metrics for a specific channel."""
    requests_total: int = 0
    requests_success: int = 0
    requests_failed: int = 0
    rate_limits_429: int = 0
    last_request_time: float = 0.0
    last_429_time: float = 0.0
    total_wait_time: float = 0.0


class TokenBucket:
    """
    Token bucket rate limiter for a single resource.
    
    Tokens are refilled at a constant rate, and each request consumes one token.
    If no tokens are available, the request must wait.
    """
    
    def __init__(self, rate: float, burst: int):
        """
        Initialize the token bucket.
        
        Args:
            rate: Tokens per second (requests per second)
            burst: Maximum burst size (bucket capacity)
        """
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> float:
        """
        Acquire a token, waiting if necessary.
        
        Returns:
            Time waited in seconds
        """
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            
            # Refill tokens based on time elapsed
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            # If no tokens available, wait
            wait_time = 0.0
            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0
            
            return wait_time


class ChannelRateLimiter:
    """
    Per-channel rate limiter using token bucket algorithm.
    
    This prevents bursts of requests to the same channel that would trigger
    Discord's rate limiting. Each channel has its own independent rate limit.
    
    Example:
        limiter = ChannelRateLimiter(rate_per_channel=4.0, burst=2)
        await limiter.acquire(channel_id)  # Wait for permission
        # Make API request to channel
    """
    
    def __init__(self, rate_per_channel: float = 4.0, burst: int = 2):
        """
        Initialize the channel rate limiter.
        
        Args:
            rate_per_channel: Requests per second per channel (default: 4.0)
            burst: Maximum burst size per channel (default: 2)
        """
        self.rate = rate_per_channel
        self.burst = burst
        self._limiters: Dict[str, TokenBucket] = {}
        self._metrics: Dict[str, ChannelMetrics] = {}
        self._lock = asyncio.Lock()
        
        log.info(f"ChannelRateLimiter initialized (rate={rate_per_channel}/s per channel, burst={burst})")
    
    async def acquire(self, channel_id: str) -> float:
        """
        Acquire a token for the specified channel, waiting if necessary.
        
        Args:
            channel_id: Discord channel ID
            
        Returns:
            Time waited in seconds
        """
        # Get or create limiter for this channel
        async with self._lock:
            if channel_id not in self._limiters:
                self._limiters[channel_id] = TokenBucket(
                    rate=self.rate,
                    burst=self.burst
                )
            if channel_id not in self._metrics:
                self._metrics[channel_id] = ChannelMetrics()
        
        limiter = self._limiters[channel_id]
        wait_time = await limiter.acquire()
        
        # Update metrics
        async with self._lock:
            metrics = self._metrics[channel_id]
            metrics.requests_total += 1
            metrics.last_request_time = time.time()
            metrics.total_wait_time += wait_time
        
        if wait_time > 0:
            log.debug(f"[Channel:{channel_id}] Rate limiter waited {wait_time:.2f}s")
        
        return wait_time
    
    async def record_success(self, channel_id: str) -> None:
        """Record a successful request."""
        async with self._lock:
            if channel_id in self._metrics:
                self._metrics[channel_id].requests_success += 1
    
    async def record_failure(self, channel_id: str) -> None:
        """Record a failed request."""
        async with self._lock:
            if channel_id in self._metrics:
                self._metrics[channel_id].requests_failed += 1
    
    async def record_429(self, channel_id: str) -> None:
        """Record a rate limit error."""
        async with self._lock:
            if channel_id in self._metrics:
                metrics = self._metrics[channel_id]
                metrics.rate_limits_429 += 1
                metrics.last_429_time = time.time()
    
    def get_metrics(self, channel_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get metrics for a specific channel or all channels.
        
        Args:
            channel_id: Channel ID, or None for all channels
            
        Returns:
            Dictionary with metrics
        """
        if channel_id:
            metrics = self._metrics.get(channel_id)
            if not metrics:
                return {}
            return {
                "channel_id": channel_id,
                "requests_total": metrics.requests_total,
                "requests_success": metrics.requests_success,
                "requests_failed": metrics.requests_failed,
                "rate_limits_429": metrics.rate_limits_429,
                "last_request_time": metrics.last_request_time,
                "last_429_time": metrics.last_429_time,
                "total_wait_time": metrics.total_wait_time,
                "avg_wait_time": metrics.total_wait_time / metrics.requests_total if metrics.requests_total > 0 else 0
            }
        else:
            # Aggregate metrics for all channels
            total_requests = sum(m.requests_total for m in self._metrics.values())
            total_429s = sum(m.rate_limits_429 for m in self._metrics.values())
            total_wait = sum(m.total_wait_time for m in self._metrics.values())
            
            return {
                "total_channels": len(self._metrics),
                "total_requests": total_requests,
                "total_429s": total_429s,
                "total_wait_time": total_wait,
                "avg_wait_time": total_wait / total_requests if total_requests > 0 else 0,
                "channels": {cid: self.get_metrics(cid) for cid in self._metrics.keys()}
            }


class AdaptiveBackoff:
    """
    Adaptive backoff system that learns from rate limit errors.
    
    When a channel receives 429 errors, this system increases the delay
    before making subsequent requests to that channel. The penalty decays
    over time as the channel recovers.
    
    Example:
        backoff = AdaptiveBackoff()
        
        # After receiving 429
        await backoff.record_429(channel_id, retry_after=5.0)
        
        # Before next request
        delay = await backoff.get_delay(channel_id)
        await asyncio.sleep(delay)
    """
    
    def __init__(
        self,
        min_delay: float = 0.5,
        max_delay: float = 60.0,
        decay_rate: float = 0.1
    ):
        """
        Initialize the adaptive backoff system.
        
        Args:
            min_delay: Minimum delay in seconds (default: 0.5)
            max_delay: Maximum delay in seconds (default: 60.0)
            decay_rate: Rate at which penalties decay per second (default: 0.1)
        """
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.decay_rate = decay_rate
        self._channel_penalties: Dict[str, float] = {}
        self._last_429: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        
        log.info(f"AdaptiveBackoff initialized (min={min_delay}s, max={max_delay}s, decay={decay_rate})")
    
    async def record_429(self, channel_id: str, retry_after: Optional[float] = None) -> None:
        """
        Record a rate limit error and increase penalty.
        
        Args:
            channel_id: Discord channel ID
            retry_after: Discord's Retry-After value in seconds
        """
        async with self._lock:
            current_penalty = self._channel_penalties.get(channel_id, 0.0)
            
            # Use retry_after if provided, otherwise increase exponentially
            if retry_after:
                new_penalty = max(retry_after, current_penalty * 1.5)
            else:
                new_penalty = max(self.min_delay, current_penalty * 2.0 + 1.0)
            
            # Cap at max_delay
            new_penalty = min(new_penalty, self.max_delay)
            
            self._channel_penalties[channel_id] = new_penalty
            self._last_429[channel_id] = time.time()
            
            log.warning(
                f"[Channel:{channel_id}] Rate limit penalty increased to {new_penalty:.1f}s "
                f"(retry_after={retry_after})"
            )
    
    async def get_delay(self, channel_id: str) -> float:
        """
        Get the current delay for a channel.
        
        The delay decays over time as the channel recovers from rate limiting.
        
        Args:
            channel_id: Discord channel ID
            
        Returns:
            Delay in seconds (0 if no penalty)
        """
        async with self._lock:
            if channel_id not in self._channel_penalties:
                return 0.0
            
            penalty = self._channel_penalties[channel_id]
            
            # Decay penalty based on time elapsed since last 429
            if channel_id in self._last_429:
                elapsed = time.time() - self._last_429[channel_id]
                decay = elapsed * self.decay_rate
                penalty = max(0.0, penalty - decay)
                
                # Update stored penalty
                if penalty > 0:
                    self._channel_penalties[channel_id] = penalty
                else:
                    # Penalty fully decayed, remove from tracking
                    self._channel_penalties.pop(channel_id, None)
                    self._last_429.pop(channel_id, None)
            
            return penalty
    
    async def record_success(self, channel_id: str) -> None:
        """
        Record a successful request, which helps decay penalties faster.
        
        Args:
            channel_id: Discord channel ID
        """
        async with self._lock:
            if channel_id in self._channel_penalties:
                # Reduce penalty on success
                current = self._channel_penalties[channel_id]
                new_penalty = max(0.0, current * 0.9)
                
                if new_penalty > 0:
                    self._channel_penalties[channel_id] = new_penalty
                else:
                    self._channel_penalties.pop(channel_id, None)
                    self._last_429.pop(channel_id, None)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current backoff statistics."""
        return {
            "channels_with_penalty": len(self._channel_penalties),
            "penalties": {
                cid: {
                    "penalty": penalty,
                    "last_429": self._last_429.get(cid, 0.0)
                }
                for cid, penalty in self._channel_penalties.items()
            }
        }


class CircuitBreaker:
    """
    Circuit breaker pattern for protecting problematic channels.
    
    When a channel consistently returns errors, the circuit breaker "opens"
    and prevents requests to that channel for a timeout period. After the
    timeout, it enters a "half-open" state where limited requests are allowed
    to test if the channel has recovered.
    
    States:
    - CLOSED: Normal operation, all requests allowed
    - OPEN: Too many failures, requests blocked
    - HALF_OPEN: Testing recovery, limited requests allowed
    
    Example:
        breaker = CircuitBreaker(failure_threshold=5, timeout=60.0)
        
        if await breaker.is_open(channel_id):
            # Circuit open, skip request
            return None
        
        try:
            result = await make_request()
            await breaker.record_success(channel_id)
        except Exception:
            await breaker.record_failure(channel_id)
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        half_open_requests: int = 1
    ):
        """
        Initialize the circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening (default: 5)
            timeout: Seconds to wait before trying again (default: 60.0)
            half_open_requests: Requests allowed in half-open state (default: 1)
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.half_open_requests = half_open_requests
        
        self._failures: Dict[str, int] = {}
        self._opened_at: Dict[str, float] = {}
        self._half_open_attempts: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        
        log.info(
            f"CircuitBreaker initialized "
            f"(threshold={failure_threshold}, timeout={timeout}s)"
        )
    
    async def is_open(self, channel_id: str) -> bool:
        """
        Check if the circuit is open for a channel.
        
        Args:
            channel_id: Discord channel ID
            
        Returns:
            True if circuit is open (requests should be blocked)
        """
        async with self._lock:
            if channel_id not in self._opened_at:
                return False
            
            elapsed = time.time() - self._opened_at[channel_id]
            
            if elapsed > self.timeout:
                # Transition to half-open state
                self._half_open_attempts[channel_id] = 0
                log.info(f"[Channel:{channel_id}] Circuit breaker entering half-open state")
                return False
            
            # Check if in half-open state
            if channel_id in self._half_open_attempts:
                attempts = self._half_open_attempts[channel_id]
                if attempts < self.half_open_requests:
                    self._half_open_attempts[channel_id] += 1
                    return False
            
            return True
    
    async def record_failure(self, channel_id: str) -> None:
        """
        Record a failure for a channel.
        
        Args:
            channel_id: Discord channel ID
        """
        async with self._lock:
            self._failures[channel_id] = self._failures.get(channel_id, 0) + 1
            
            if self._failures[channel_id] >= self.failure_threshold:
                if channel_id not in self._opened_at:
                    self._opened_at[channel_id] = time.time()
                    log.error(
                        f"[Channel:{channel_id}] Circuit breaker OPENED "
                        f"after {self._failures[channel_id]} failures"
                    )
            
            # If in half-open state and failed, reopen circuit
            if channel_id in self._half_open_attempts:
                self._opened_at[channel_id] = time.time()
                self._half_open_attempts.pop(channel_id, None)
                log.warning(f"[Channel:{channel_id}] Circuit breaker reopened after half-open failure")
    
    async def record_success(self, channel_id: str) -> None:
        """
        Record a success for a channel.
        
        Args:
            channel_id: Discord channel ID
        """
        async with self._lock:
            # Reset failure count
            self._failures[channel_id] = 0
            
            # If in half-open state and succeeded, close circuit
            if channel_id in self._half_open_attempts:
                self._opened_at.pop(channel_id, None)
                self._half_open_attempts.pop(channel_id, None)
                log.info(f"[Channel:{channel_id}] Circuit breaker CLOSED after successful recovery")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current circuit breaker statistics."""
        return {
            "open_circuits": len(self._opened_at),
            "circuits": {
                cid: {
                    "failures": self._failures.get(cid, 0),
                    "opened_at": self._opened_at.get(cid),
                    "half_open_attempts": self._half_open_attempts.get(cid, 0)
                }
                for cid in set(list(self._failures.keys()) + list(self._opened_at.keys()))
            }
        }


class RateLimiter:
    """
    Legacy global rate limiter (kept for backward compatibility).
    
    Note: New code should use ChannelRateLimiter instead for better
    per-channel rate limiting.
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


# Global instances
_global_limiter: Optional[RateLimiter] = None
_channel_limiter: Optional[ChannelRateLimiter] = None
_adaptive_backoff: Optional[AdaptiveBackoff] = None
_circuit_breaker: Optional[CircuitBreaker] = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance (legacy)."""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = RateLimiter(rate=50.0, burst=10)
    return _global_limiter


def get_channel_rate_limiter() -> ChannelRateLimiter:
    """Get the global channel rate limiter instance."""
    global _channel_limiter
    if _channel_limiter is None:
        _channel_limiter = ChannelRateLimiter(rate_per_channel=4.0, burst=2)
    return _channel_limiter


def get_adaptive_backoff() -> AdaptiveBackoff:
    """Get the global adaptive backoff instance."""
    global _adaptive_backoff
    if _adaptive_backoff is None:
        _adaptive_backoff = AdaptiveBackoff(min_delay=0.5, max_delay=60.0, decay_rate=0.1)
    return _adaptive_backoff


def get_circuit_breaker() -> CircuitBreaker:
    """Get the global circuit breaker instance."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60.0)
    return _circuit_breaker


def reset_rate_limiter() -> None:
    """Reset all global rate limiter instances (useful for testing)."""
    global _global_limiter, _channel_limiter, _adaptive_backoff, _circuit_breaker
    _global_limiter = None
    _channel_limiter = None
    _adaptive_backoff = None
    _circuit_breaker = None
    log.info("All rate limiter instances reset")
