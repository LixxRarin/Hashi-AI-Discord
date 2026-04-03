"""
HTTP Client Utilities - Centralized HTTP Session Management

This module provides properly configured aiohttp sessions with:
- Optimized TCPConnector settings for stability
- Retry logic with exponential backoff
- Proper timeout configurations
- Detailed error logging

Usage:
    async with create_http_session() as session:
        async with session.get(url) as response:
            data = await response.read()
"""

import asyncio
import logging
from typing import Optional, Callable, Any
from functools import wraps

import aiohttp
import discord

log = logging.getLogger(__name__)


def create_tcp_connector(
    limit: int = 100,
    limit_per_host: int = 30,
    ttl_dns_cache: int = 300,
    force_close: bool = False,
    enable_cleanup_closed: bool = True
) -> aiohttp.TCPConnector:
    """
    Create a properly configured TCPConnector for aiohttp sessions.
    
    Args:
        limit: Total number of simultaneous connections
        limit_per_host: Maximum connections per host
        ttl_dns_cache: DNS cache TTL in seconds
        force_close: Force close connections after each request
        enable_cleanup_closed: Enable cleanup of closed connections
        
    Returns:
        Configured TCPConnector instance
    """
    return aiohttp.TCPConnector(
        limit=limit,
        limit_per_host=limit_per_host,
        ttl_dns_cache=ttl_dns_cache,
        force_close=force_close,
        enable_cleanup_closed=enable_cleanup_closed
    )


def create_http_session(
    timeout_total: float = 30.0,
    timeout_connect: float = 10.0,
    timeout_sock_read: float = 20.0,
    connector: Optional[aiohttp.TCPConnector] = None,
    **kwargs
) -> aiohttp.ClientSession:
    """
    Create a properly configured aiohttp ClientSession.
    
    Args:
        timeout_total: Total timeout in seconds
        timeout_connect: Connection timeout in seconds
        timeout_sock_read: Socket read timeout in seconds
        connector: Optional custom TCPConnector (creates default if None)
        **kwargs: Additional arguments passed to ClientSession
        
    Returns:
        Configured ClientSession instance
        
    Example:
        async with create_http_session() as session:
            async with session.get(url) as response:
                data = await response.read()
    """
    if connector is None:
        connector = create_tcp_connector()
    
    timeout = aiohttp.ClientTimeout(
        total=timeout_total,
        connect=timeout_connect,
        sock_read=timeout_sock_read
    )
    
    return aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        **kwargs
    )


def create_webhook_session(
    webhook_url: str,
    timeout_total: float = 30.0,
    timeout_connect: float = 10.0,
    timeout_sock_read: float = 20.0
) -> tuple[aiohttp.ClientSession, discord.Webhook]:
    """
    Create an HTTP session and Discord webhook object.
    
    This is a convenience function for webhook operations that need
    both a session and webhook object.
    
    Args:
        webhook_url: Discord webhook URL
        timeout_total: Total timeout in seconds
        timeout_connect: Connection timeout in seconds
        timeout_sock_read: Socket read timeout in seconds
        
    Returns:
        Tuple of (ClientSession, Webhook)
        
    Example:
        async with create_webhook_session(url) as (session, webhook):
            await webhook.send("Hello!")
    """
    session = create_http_session(
        timeout_total=timeout_total,
        timeout_connect=timeout_connect,
        timeout_sock_read=timeout_sock_read
    )
    webhook = discord.Webhook.from_url(webhook_url, session=session)
    return session, webhook


def retry_on_network_error(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_base: float = 2.0,
    retry_on: tuple = (
        aiohttp.ClientError,
        asyncio.TimeoutError,
        ConnectionError,
        OSError
    )
):
    """
    Decorator to retry async functions on network errors with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
        retry_on: Tuple of exception types to retry on
        
    Example:
        @retry_on_network_error(max_attempts=3, base_delay=1.0)
        async def send_message(webhook, text):
            return await webhook.send(text, wait=True)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except retry_on as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        # Last attempt failed, log and re-raise
                        log.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}",
                            exc_info=True
                        )
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base ** (attempt - 1)), max_delay)
                    
                    log.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    # Non-retryable error, log and re-raise immediately
                    log.error(f"{func.__name__} failed with non-retryable error: {e}", exc_info=True)
                    raise
            
            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


class NetworkErrorHandler:
    """
    Context manager for handling network errors with detailed logging.
    
    Example:
        async with NetworkErrorHandler("send_webhook_message"):
            await webhook.send(text, wait=True)
    """
    
    def __init__(self, operation_name: str):
        """
        Initialize the error handler.
        
        Args:
            operation_name: Name of the operation for logging
        """
        self.operation_name = operation_name
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            return False
            
        # Log detailed error information
        if isinstance(exc_val, aiohttp.ClientError):
            log.error(
                f"Network error in {self.operation_name}: {exc_val.__class__.__name__}: {exc_val}"
            )
        elif isinstance(exc_val, asyncio.TimeoutError):
            log.error(f"Timeout in {self.operation_name}")
        elif isinstance(exc_val, (ConnectionError, OSError)):
            log.error(
                f"Connection error in {self.operation_name}: {exc_val.__class__.__name__}: {exc_val}"
            )
        else:
            # Not a network error, let it propagate
            return False
            
        # Don't suppress the exception, let it propagate
        return False


# Convenience function for common Discord API operations
async def fetch_with_retry(
    url: str,
    max_attempts: int = 3,
    **session_kwargs
) -> bytes:
    """
    Fetch data from URL with automatic retry on network errors.
    
    Args:
        url: URL to fetch
        max_attempts: Maximum retry attempts
        **session_kwargs: Additional arguments for create_http_session
        
    Returns:
        Response content as bytes
        
    Example:
        data = await fetch_with_retry("https://example.com/image.png")
    """
    @retry_on_network_error(max_attempts=max_attempts)
    async def _fetch():
        async with create_http_session(**session_kwargs) as session:
            async with session.get(url) as response:
                response.raise_for_status()
                return await response.read()
    
    return await _fetch()
