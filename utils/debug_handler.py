"""
Discord Log Handler - Sends Python logs to a configured Discord channel.

This module implements a custom logging handler that sends log messages
to a specific Discord channel, with support for batching, colors, and
level filtering.
"""

import asyncio
import logging
import sys
import time
from typing import Optional, Dict, Any
from datetime import datetime
from collections import deque

import discord

import utils.func as func


class DiscordLogHandler(logging.Handler):
    """
    Custom handler that sends logs to a Discord channel.
    
    Features:
    - Message batching to avoid spam
    - Colored embeds by log level
    - Async queue to not block logging
    - Respects Discord rate limits
    - Automatically truncates long messages
    """
    
    # Mapping of log levels to embed colors
    LEVEL_COLORS = {
        logging.DEBUG: discord.Color.blue(),
        logging.INFO: discord.Color.green(),
        logging.WARNING: discord.Color.gold(),
        logging.ERROR: discord.Color.red(),
        logging.CRITICAL: discord.Color.dark_red(),
    }
    
    # Emojis for each level
    LEVEL_EMOJIS = {
        logging.DEBUG: "🔵",
        logging.INFO: "🟢",
        logging.WARNING: "🟡",
        logging.ERROR: "🔴",
        logging.CRITICAL: "🚫",
    }
    
    def __init__(self, bot: discord.Client, batch_interval: float = 2.0, max_queue_size: int = 100):
        """
        Initialize the handler.
        
        Args:
            bot: Discord bot instance
            batch_interval: Interval in seconds to send batched messages
            max_queue_size: Maximum queue size for pending messages
        """
        super().__init__()
        self.bot = bot
        self.batch_interval = batch_interval
        self.max_queue_size = max_queue_size
        
        # Queue for pending messages
        self.message_queue = deque(maxlen=max_queue_size)
        
        # Statistics
        self.stats = {
            "messages_sent": 0,
            "messages_dropped": 0,
            "errors": 0,
            "last_send_time": None
        }
        
        # Batching control
        self._batch_task: Optional[asyncio.Task] = None
        self._last_batch_time = time.time()
        self._is_processing = False
        
        # Configuration cache - now stores list of all enabled configs
        self._config_cache: Optional[list] = None
        self._config_cache_time = 0
        self._config_cache_ttl = 5.0  # 5 seconds
    
    def emit(self, record: logging.LogRecord) -> None:
        """
        Called when a log is emitted.
        
        Args:
            record: Log record
        """
        try:
            # Get configurations (list of all enabled configs)
            configs = self._get_config()
            if not configs:
                return
            
            # Check if level is enabled
            if record.levelno < self.level:
                return
            
            # Format the message
            msg = self.format(record)
            
            # Add to queue
            log_entry = {
                "level": record.levelno,
                "level_name": record.levelname,
                "message": msg,
                "timestamp": datetime.now(),
                "filename": record.filename,
                "lineno": record.lineno
            }
            
            self.message_queue.append(log_entry)
            
            # Start batching task if not running
            if not self._batch_task or self._batch_task.done():
                try:
                    loop = asyncio.get_event_loop()
                    self._batch_task = loop.create_task(self._process_batch())
                except RuntimeError:
                    # No event loop running, ignore
                    pass
                    
        except Exception as e:
            # Log error
            func.log.error(f"Error in DiscordLogHandler.emit: {e}")
            self.stats["errors"] += 1
    
    def _get_config(self) -> list:
        """
        Get all enabled debug channel configurations with caching.
        
        Returns:
            List of configuration dictionaries (empty list if none configured)
        """
        current_time = time.time()
        
        # Use cache if still valid
        if self._config_cache is not None and (current_time - self._config_cache_time) < self._config_cache_ttl:
            return self._config_cache
        
        # Load configuration
        try:
            debug_config = func.read_json(func.get_debug_config_file()) or {}
            
            # Collect all enabled configurations
            enabled_configs = []
            for server_id, config in debug_config.items():
                if config.get("enabled", False) and config.get("debug_channel_id"):
                    # Add server_id to config for reference
                    config_copy = config.copy()
                    config_copy["server_id"] = server_id
                    enabled_configs.append(config_copy)
            
            self._config_cache = enabled_configs
            self._config_cache_time = current_time
            return enabled_configs
            
        except Exception as e:
            func.log.error(f"Error loading debug config: {e}")
            return []
    
    async def _process_batch(self) -> None:
        """
        Process messages in batches and send to Discord.
        """
        if self._is_processing:
            return
        
        self._is_processing = True
        
        try:
            while self.message_queue:
                # Wait for batching interval
                time_since_last = time.time() - self._last_batch_time
                if time_since_last < self.batch_interval:
                    await asyncio.sleep(self.batch_interval - time_since_last)
                
                # Collect messages to send
                messages_to_send = []
                while self.message_queue and len(messages_to_send) < 10:  # Max 10 per batch
                    messages_to_send.append(self.message_queue.popleft())
                
                if messages_to_send:
                    await self._send_batch(messages_to_send)
                    self._last_batch_time = time.time()
                
        except Exception as e:
            func.log.error(f"Error in _process_batch: {e}")
            self.stats["errors"] += 1
        finally:
            self._is_processing = False
    
    async def _send_batch(self, messages: list) -> None:
        """
        Send a batch of messages to all configured Discord channels.
        
        Args:
            messages: List of messages to send
        """
        configs = self._get_config()
        if not configs:
            return
        
        # Create embed once (will be reused for all channels)
        if len(messages) == 1:
            # Single message
            msg = messages[0]
            embed = self._create_single_embed(msg)
        else:
            # Multiple messages
            embed = self._create_batch_embed(messages)
        
        # Send to all configured channels
        sent_count = 0
        for config in configs:
            try:
                channel_id = config.get("debug_channel_id")
                if not channel_id:
                    continue
                
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    continue
                
                # Check if this message level meets the channel's log level
                channel_log_level = config.get("log_level", "INFO")
                min_level = getattr(logging, channel_log_level, logging.INFO)
                
                # Get max level from messages
                max_msg_level = max(msg["level"] for msg in messages)
                
                # Skip if message level is below channel's minimum
                if max_msg_level < min_level:
                    continue
                
                # Send to channel
                await channel.send(embed=embed)
                sent_count += 1
                
            except discord.Forbidden:
                func.log.warning(f"No permission to send to debug channel {channel_id}")
                self.stats["errors"] += 1
            except discord.HTTPException as e:
                func.log.error(f"HTTP error sending to debug channel {channel_id}: {e}")
                self.stats["errors"] += 1
            except Exception as e:
                func.log.error(f"Error sending batch to channel {channel_id}: {e}")
                self.stats["errors"] += 1
        
        # Update stats if at least one send was successful
        if sent_count > 0:
            self.stats["messages_sent"] += len(messages)
            self.stats["last_send_time"] = datetime.now()
    
    def _create_single_embed(self, msg: Dict[str, Any]) -> discord.Embed:
        """
        Create an embed for a single message.
        
        Args:
            msg: Message data dictionary
            
        Returns:
            Discord embed
        """
        level = msg["level"]
        level_name = msg["level_name"]
        message = msg["message"]
        timestamp = msg["timestamp"]
        filename = msg["filename"]
        lineno = msg["lineno"]
        
        # Get color and emoji
        color = self.LEVEL_COLORS.get(level, discord.Color.greyple())
        emoji = self.LEVEL_EMOJIS.get(level, "⚪")
        
        # Create embed
        embed = discord.Embed(
            title=f"{emoji} {level_name} | {timestamp.strftime('%H:%M:%S')}",
            color=color,
            timestamp=timestamp
        )
        
        # Truncate message if too long
        if len(message) > 1900:
            message = message[:1900] + "..."
        
        embed.description = f"```\n[{filename}:{lineno}] {message}\n```"
        
        return embed
    
    def _create_batch_embed(self, messages: list) -> discord.Embed:
        """
        Create an embed for multiple messages.
        
        Args:
            messages: List of messages
            
        Returns:
            Discord embed
        """
        first_msg = messages[0]
        last_msg = messages[-1]
        
        # Determine color based on highest level
        max_level = max(msg["level"] for msg in messages)
        color = self.LEVEL_COLORS.get(max_level, discord.Color.greyple())
        
        # Create title
        time_range = f"{first_msg['timestamp'].strftime('%H:%M:%S')} - {last_msg['timestamp'].strftime('%H:%M:%S')}"
        title = f"📊 Logs ({len(messages)} messages) | {time_range}"
        
        # Create embed
        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=last_msg["timestamp"]
        )
        
        # Build description with all messages
        lines = []
        for msg in messages:
            emoji = self.LEVEL_EMOJIS.get(msg["level"], "⚪")
            filename = msg["filename"]
            lineno = msg["lineno"]
            message = msg["message"]
            
            # Truncate individual message if needed
            if len(message) > 100:
                message = message[:100] + "..."
            
            lines.append(f"{emoji} [{filename}:{lineno}] {message}")
        
        description = "\n".join(lines)
        
        # Truncate total description if too long
        if len(description) > 1900:
            description = description[:1900] + "\n..."
        
        embed.description = f"```\n{description}\n```"
        
        return embed
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Return handler statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            **self.stats,
            "queue_size": len(self.message_queue),
            "is_processing": self._is_processing
        }
    
    def clear_queue(self) -> int:
        """
        Clear the pending message queue.
        
        Returns:
            Number of messages removed
        """
        count = len(self.message_queue)
        self.message_queue.clear()
        return count
    
    def invalidate_cache(self) -> None:
        """
        Invalidate the configuration cache.
        Call this when debug configuration changes.
        """
        self._config_cache = None
        self._config_cache_time = 0
