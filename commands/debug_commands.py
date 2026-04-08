"""
Debug Commands - Administrative commands for debugging and system management.

This module provides commands for:
- Configuring debug channel for logs
- Restarting the bot
- Viewing system status
- Managing debug settings
"""

import asyncio
import logging
import os
import platform
import sys
import time
import psutil
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
from utils.core.debug import DiscordLogHandler


class DebugCommands(commands.Cog):
    """Cog for debug and administrative commands."""
    
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()
        self._discord_handler: Optional[DiscordLogHandler] = None
    
    async def cog_load(self):
        """Called when the cog is loaded. Initialize debug handler if configured."""
        try:
            from utils.core.paths import DataPaths

            data_paths = DataPaths()

            # Check if any server has debug enabled
            has_enabled_debug = False
            min_level = logging.CRITICAL  # Start with highest level

            for server_id in data_paths.list_servers():
                debug_config_file = data_paths.get_debug_config_file(server_id)
                if not os.path.exists(debug_config_file):
                    continue

                config = func.read_json(debug_config_file) or {}
                if config.get("enabled", False) and config.get("debug_channel_id"):
                    has_enabled_debug = True
                    # Find the lowest (most verbose) log level across all configs
                    level_name = config.get("log_level", "INFO")
                    level = getattr(logging, level_name, logging.INFO)
                    min_level = min(min_level, level)

            # Initialize handler if debug is enabled
            if has_enabled_debug:
                handler = self._get_or_create_handler()
                handler.setLevel(min_level)
        except Exception as e:
            func.log.error(f"Error initializing debug handler on startup: {e}")
    
    def _get_or_create_handler(self) -> DiscordLogHandler:
        """
        Get or create the Discord log handler.
        
        Returns:
            DiscordLogHandler instance
        """
        if self._discord_handler is None:
            # Find existing handler or create new one
            root_logger = logging.getLogger()
            for handler in root_logger.handlers:
                if isinstance(handler, DiscordLogHandler):
                    self._discord_handler = handler
                    break
            
            if self._discord_handler is None:
                # Create new handler
                self._discord_handler = DiscordLogHandler(self.bot)
                self._discord_handler.setLevel(logging.DEBUG)
                root_logger.addHandler(self._discord_handler)
                func.log.info("Discord log handler created and registered")
        
        return self._discord_handler
    
    @app_commands.command(name="set_debug_channel", description="Configure a channel to receive debug logs")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        channel="Channel to send debug logs to",
        log_level="Minimum log level to display",
        enabled="Enable or disable debug logging"
    )
    @app_commands.choices(log_level=[
        app_commands.Choice(name="DEBUG (All messages)", value="DEBUG"),
        app_commands.Choice(name="INFO (Informational and above)", value="INFO"),
        app_commands.Choice(name="WARNING (Warnings and errors only)", value="WARNING"),
        app_commands.Choice(name="ERROR (Errors only)", value="ERROR"),
        app_commands.Choice(name="CRITICAL (Critical errors only)", value="CRITICAL")
    ])
    async def set_debug_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        log_level: app_commands.Choice[str] = None,
        enabled: bool = True
    ):
        """Configure the debug channel for receiving logs."""
        await interaction.response.defer(ephemeral=True)

        server_id = str(interaction.guild.id)

        # Load existing config for this server
        from utils.core.paths import DataPaths

        data_paths = DataPaths()
        debug_config_file = data_paths.get_debug_config_file(server_id)
        data_paths.ensure_directory(debug_config_file)

        server_config = func.read_json(debug_config_file) or {}

        # Update configuration
        server_config["debug_channel_id"] = str(channel.id)
        server_config["enabled"] = enabled

        if log_level:
            server_config["log_level"] = log_level.value
        elif "log_level" not in server_config:
            server_config["log_level"] = "INFO"

        # Save configuration
        func.write_json(debug_config_file, server_config)

        # Get or create handler
        handler = self._get_or_create_handler()

        # Invalidate cache to pick up new configuration
        handler.invalidate_cache()

        # Set handler level to minimum across all enabled configs
        min_level = logging.CRITICAL
        for srv_id in data_paths.list_servers():
            cfg_file = data_paths.get_debug_config_file(srv_id)
            if os.path.exists(cfg_file):
                cfg = func.read_json(cfg_file) or {}
                if cfg.get("enabled", False):
                    lvl_name = cfg.get("log_level", "INFO")
                    lvl = getattr(logging, lvl_name, logging.INFO)
                    min_level = min(min_level, lvl)
        handler.setLevel(min_level)

        # Get the log level name for display
        level_name = server_config["log_level"]
        
        # Send test message
        if enabled:
            try:
                test_embed = discord.Embed(
                    title="✅ Debug Channel Configured",
                    description=f"This channel will now receive debug logs at level **{level_name}** and above.",
                    color=discord.Color.green(),
                    timestamp=datetime.now()
                )
                test_embed.add_field(
                    name="Configuration",
                    value=f"**Channel:** {channel.mention}\n"
                          f"**Log Level:** {level_name}\n"
                          f"**Status:** {'Enabled' if enabled else 'Disabled'}",
                    inline=False
                )
                test_embed.set_footer(text=f"Configured by {interaction.user.name}")
                
                await channel.send(embed=test_embed)
                
                # Log a test message
                func.log.info(f"Debug channel configured: {channel.id} (Level: {level_name})")
                
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ I don't have permission to send messages in that channel.",
                    ephemeral=True
                )
                return
        
        # Send confirmation
        status_emoji = "✅" if enabled else "⚠️"
        status_text = "enabled" if enabled else "disabled"

        await interaction.followup.send(
            f"{status_emoji} Debug logging {status_text} for {channel.mention}\n"
            f"**Log Level:** {server_config['log_level']}\n\n"
            f"💡 Use `/debug_level` to change the log level\n"
            f"💡 Use `/toggle_debug` to enable/disable logging",
            ephemeral=True
        )
    
    @app_commands.command(name="debug_level", description="Change the debug log level")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(level="New log level")
    @app_commands.choices(level=[
        app_commands.Choice(name="DEBUG (All messages)", value="DEBUG"),
        app_commands.Choice(name="INFO (Informational and above)", value="INFO"),
        app_commands.Choice(name="WARNING (Warnings and errors only)", value="WARNING"),
        app_commands.Choice(name="ERROR (Errors only)", value="ERROR"),
        app_commands.Choice(name="CRITICAL (Critical errors only)", value="CRITICAL")
    ])
    async def debug_level(
        self,
        interaction: discord.Interaction,
        level: app_commands.Choice[str]
    ):
        """Change the debug log level."""
        server_id = str(interaction.guild.id)

        # Load config for this server
        from utils.core.paths import DataPaths

        data_paths = DataPaths()
        debug_config_file = data_paths.get_debug_config_file(server_id)

        if not os.path.exists(debug_config_file):
            await interaction.response.send_message(
                "❌ Debug channel not configured. Use `/set_debug_channel` first.",
                ephemeral=True
            )
            return

        server_config = func.read_json(debug_config_file) or {}

        if not server_config.get("debug_channel_id"):
            await interaction.response.send_message(
                "❌ Debug channel not configured. Use `/set_debug_channel` first.",
                ephemeral=True
            )
            return

        # Update level
        old_level = server_config.get("log_level", "INFO")
        server_config["log_level"] = level.value
        func.write_json(debug_config_file, server_config)

        # Update handler
        handler = self._get_or_create_handler()
        handler.invalidate_cache()

        # Set handler level to minimum across all enabled configs
        min_level = logging.CRITICAL
        for srv_id in data_paths.list_servers():
            cfg_file = data_paths.get_debug_config_file(srv_id)
            if os.path.exists(cfg_file):
                cfg = func.read_json(cfg_file) or {}
                if cfg.get("enabled", False):
                    lvl_name = cfg.get("log_level", "INFO")
                    lvl = getattr(logging, lvl_name, logging.INFO)
                    min_level = min(min_level, lvl)
        handler.setLevel(min_level)
        
        await interaction.response.send_message(
            f"✅ Debug log level changed from **{old_level}** to **{level.value}**\n"
            f"💡 This channel will now receive logs at level **{level.value}** and above",
            ephemeral=True
        )
        
        func.log.info(f"Debug log level changed to {level.value}")
    
    @app_commands.command(name="toggle_debug", description="Enable or disable debug logging")
    @app_commands.default_permissions(administrator=True)
    async def toggle_debug(self, interaction: discord.Interaction):
        """Toggle debug logging on/off."""
        server_id = str(interaction.guild.id)

        # Load config for this server
        from utils.core.paths import DataPaths

        data_paths = DataPaths()
        debug_config_file = data_paths.get_debug_config_file(server_id)

        if not os.path.exists(debug_config_file):
            await interaction.response.send_message(
                "❌ Debug channel not configured. Use `/set_debug_channel` first.",
                ephemeral=True
            )
            return

        server_config = func.read_json(debug_config_file) or {}

        if not server_config.get("debug_channel_id"):
            await interaction.response.send_message(
                "❌ Debug channel not configured. Use `/set_debug_channel` first.",
                ephemeral=True
            )
            return

        # Toggle enabled status
        current_status = server_config.get("enabled", False)
        new_status = not current_status
        server_config["enabled"] = new_status
        func.write_json(debug_config_file, server_config)

        # Update handler
        handler = self._get_or_create_handler()
        handler.invalidate_cache()

        # Recalculate handler level based on remaining enabled configs
        min_level = logging.CRITICAL
        for srv_id in data_paths.list_servers():
            cfg_file = data_paths.get_debug_config_file(srv_id)
            if os.path.exists(cfg_file):
                cfg = func.read_json(cfg_file) or {}
                if cfg.get("enabled", False):
                    lvl_name = cfg.get("log_level", "INFO")
                    lvl = getattr(logging, lvl_name, logging.INFO)
                    min_level = min(min_level, lvl)
        handler.setLevel(min_level)
        
        status_emoji = "✅" if new_status else "⚠️"
        status_text = "enabled" if new_status else "disabled"
        
        await interaction.response.send_message(
            f"{status_emoji} Debug logging {status_text} for this server",
            ephemeral=True
        )
        
        if new_status:
            func.log.debug("Debug logging enabled")
        else:
            func.log.debug("Debug logging disabled")
    
    @app_commands.command(name="debug_status", description="Show debug system status and statistics")
    @app_commands.default_permissions(administrator=True)
    async def debug_status(self, interaction: discord.Interaction):
        """Display debug system status."""
        await interaction.response.defer(ephemeral=True)

        server_id = str(interaction.guild.id)

        # Load config for this server
        from utils.core.paths import DataPaths

        data_paths = DataPaths()
        debug_config_file = data_paths.get_debug_config_file(server_id)

        server_config = {}
        if os.path.exists(debug_config_file):
            server_config = func.read_json(debug_config_file) or {}
        
        # Create embed
        embed = discord.Embed(
            title="🔧 Debug System Status",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Configuration section
        if server_config:
            channel_id = server_config.get("debug_channel_id")
            channel = self.bot.get_channel(int(channel_id)) if channel_id else None
            
            config_value = f"**Channel:** {channel.mention if channel else 'Not found'}\n"
            config_value += f"**Log Level:** {server_config.get('log_level', 'Not set')}\n"
            config_value += f"**Status:** {'✅ Enabled' if server_config.get('enabled') else '❌ Disabled'}"
            
            embed.add_field(
                name="📋 Configuration",
                value=config_value,
                inline=False
            )
        else:
            embed.add_field(
                name="📋 Configuration",
                value="❌ Debug channel not configured",
                inline=False
            )
        
        # Handler statistics
        handler = self._get_or_create_handler()
        stats = handler.get_stats()
        
        stats_value = f"**Messages Sent:** {stats['messages_sent']}\n"
        stats_value += f"**Queue Size:** {stats['queue_size']}\n"
        stats_value += f"**Errors:** {stats['errors']}\n"
        stats_value += f"**Processing:** {'Yes' if stats['is_processing'] else 'No'}"
        
        if stats['last_send_time']:
            stats_value += f"\n**Last Send:** <t:{int(stats['last_send_time'].timestamp())}:R>"
        
        embed.add_field(
            name="📊 Statistics",
            value=stats_value,
            inline=False
        )
        
        # Bot uptime
        uptime_seconds = time.time() - self.start_time
        uptime_str = str(timedelta(seconds=int(uptime_seconds)))
        
        embed.add_field(
            name="⏱️ Uptime",
            value=f"`{uptime_str}`",
            inline=True
        )
        
        # Server count
        embed.add_field(
            name="🌐 Servers",
            value=f"`{len(self.bot.guilds)}`",
            inline=True
        )
        
        # AI count
        total_ais = 0
        for server_data in func.session_cache.values():
            for channel_data in server_data.get("channels", {}).values():
                total_ais += len(channel_data)
        
        embed.add_field(
            name="🤖 Active AIs",
            value=f"`{total_ais}`",
            inline=True
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    def _create_progress_bar(self, percentage: float, length: int = 10) -> str:
        """
        Create a visual progress bar.
        
        Args:
            percentage: Percentage value (0-100)
            length: Length of the bar in characters
            
        Returns:
            Progress bar string
        """
        filled = int((percentage / 100) * length)
        bar = "▰" * filled + "▱" * (length - filled)
        return bar
    
    def _get_health_indicator(self, percentage: float) -> str:
        """
        Get health indicator emoji based on percentage.
        
        Args:
            percentage: Percentage value (0-100)
            
        Returns:
            Health indicator emoji
        """
        if percentage < 70:
            return "🟢"
        elif percentage < 85:
            return "🟡"
        else:
            return "🔴"
    
    def _get_system_stats(self) -> dict:
        """
        Collect system statistics.
        
        Returns:
            Dictionary with system stats
        """
        stats = {}
        
        try:
            # OS information
            stats["os_name"] = f"{platform.system()} {platform.release()}"
            stats["architecture"] = platform.machine()
            stats["hostname"] = platform.node()
            
            # CPU information
            stats["cpu_count_physical"] = psutil.cpu_count(logical=False) or "N/A"
            stats["cpu_count_logical"] = psutil.cpu_count(logical=True) or "N/A"
            stats["cpu_freq"] = psutil.cpu_freq()
            stats["cpu_percent"] = psutil.cpu_percent(interval=0.5)
            
            # Memory information
            mem = psutil.virtual_memory()
            stats["memory_total"] = mem.total
            stats["memory_available"] = mem.available
            stats["memory_used"] = mem.used
            stats["memory_percent"] = mem.percent
            
            # Disk information
            disk = psutil.disk_usage('/')
            stats["disk_total"] = disk.total
            stats["disk_used"] = disk.used
            stats["disk_free"] = disk.free
            stats["disk_percent"] = disk.percent
            
            # Process information
            process = psutil.Process()
            stats["process_threads"] = process.num_threads()
            stats["process_fds"] = process.num_fds() if hasattr(process, 'num_fds') else "N/A"
            stats["process_memory"] = process.memory_info().rss
            stats["process_cpu"] = process.cpu_percent(interval=0.5)
            
        except Exception as e:
            func.log.error(f"Error collecting system stats: {e}")
        
        return stats
    
    def _get_ai_stats(self) -> dict:
        """
        Collect AI and provider statistics.
        
        Returns:
            Dictionary with AI stats
        """
        stats = {
            "total_ais": 0,
            "providers": {},
            "total_connections": 0,
            "connections_by_provider": {},
            "total_cards": 0,
            "cards_in_use": 0
        }
        
        try:
            # Count AIs and group by provider
            for server_data in func.session_cache.values():
                for channel_data in server_data.get("channels", {}).values():
                    for ai_name, ai_session in channel_data.items():
                        stats["total_ais"] += 1
                        provider = ai_session.get("provider", "unknown")
                        stats["providers"][provider] = stats["providers"].get(provider, 0) + 1
            
            # Get registered providers from registry
            try:
                from AI.core.registry import get_registry
                registry = get_registry()
                stats["registered_providers"] = registry.list_providers()
            except Exception as e:
                func.log.debug(f"Could not get provider registry: {e}")
                stats["registered_providers"] = []
            
            # Count API connections
            try:
                from utils.core.paths import DataPaths
                data_paths = DataPaths()

                for server_id in data_paths.list_servers():
                    connections_file = data_paths.get_api_connections_file(server_id)
                    if os.path.exists(connections_file):
                        server_conns = func.read_json(connections_file) or {}
                        for conn_name, conn_data in server_conns.items():
                            stats["total_connections"] += 1
                            provider = conn_data.get("provider", "unknown")
                            stats["connections_by_provider"][provider] = stats["connections_by_provider"].get(provider, 0) + 1
            except Exception as e:
                func.log.debug(f"Could not count API connections: {e}")
            
            # Count character cards
            try:
                from utils.core.paths import DataPaths
                data_paths = DataPaths()

                # Iterate through all servers and count their cards
                for server_id in data_paths.list_servers():
                    cards_file = data_paths.get_character_cards_file(server_id)
                    if os.path.exists(cards_file):
                        server_cards = func.read_json(cards_file) or {}
                        stats["total_cards"] += len(server_cards)

                # Count cards in use
                for server_data in func.session_cache.values():
                    for channel_data in server_data.get("channels", {}).values():
                        for ai_name, ai_session in channel_data.items():
                            if ai_session.get("character_card"):
                                stats["cards_in_use"] += 1
            except Exception as e:
                func.log.debug(f"Could not count character cards: {e}")
        
        except Exception as e:
            func.log.error(f"Error collecting AI stats: {e}")
        
        return stats
    
    def _get_storage_stats(self) -> dict:
        """
        Collect storage statistics.
        
        Returns:
            Dictionary with storage stats
        """
        stats = {}
        
        try:
            # Calculate total character cards size from all servers
            from utils.core.paths import DataPaths
            data_paths = DataPaths()

            total_cards_size = 0
            for server_id in data_paths.list_servers():
                cards_file = data_paths.get_character_cards_file(server_id)
                if os.path.exists(cards_file):
                    total_cards_size += os.path.getsize(cards_file)

            stats["character_cards_size"] = total_cards_size

            # Calculate total data size from hierarchical structure
            from utils.core.paths import DataPaths
            data_paths = DataPaths()
            total_size = 0

            # Sum all files in data directory
            if os.path.exists(data_paths.base_dir):
                for root, dirs, files in os.walk(data_paths.base_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            total_size += os.path.getsize(file_path)
                        except:
                            pass

            stats["total_data_size"] = total_size
            
        except Exception as e:
            func.log.error(f"Error collecting storage stats: {e}")
        
        return stats
    
    @app_commands.command(name="system_info", description="Display detailed system information")
    @app_commands.default_permissions(administrator=True)
    async def system_info(self, interaction: discord.Interaction):
        """Display comprehensive system information."""
        await interaction.response.defer(ephemeral=True) 
        
        # Collect all statistics
        sys_stats = self._get_system_stats()
        ai_stats = self._get_ai_stats()
        storage_stats = self._get_storage_stats()
        
        # Create embed
        embed = discord.Embed(
            title="💻 System Information",
            description="Detailed bot and system resource status",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        # Section 1: Versions
        try:
            with open("version.txt", "r") as f:
                version = f.read().strip()
        except:
            version = "Unknown"
        
        embed.add_field(
            name="📦 Versions",
            value=f"**Project Hashi:** `{version}`\n"
                  f"**Python:** `{sys.version.split()[0]}`\n"
                  f"**Discord.py:** `{discord.__version__}`",
            inline=False
        )
        
        # Section 2: System Information
        os_name = sys_stats.get("os_name", "Unknown")
        arch = sys_stats.get("architecture", "Unknown")
        hostname = sys_stats.get("hostname", "Unknown")
        
        embed.add_field(
            name="💻 System",
            value=f"**OS:** {os_name}\n"
                  f"**Architecture:** {arch}\n"
                  f"**Hostname:** `{hostname}`",
            inline=True
        )
        
        # Section 3: CPU Information
        cpu_physical = sys_stats.get("cpu_count_physical", "N/A")
        cpu_logical = sys_stats.get("cpu_count_logical", "N/A")
        cpu_freq = sys_stats.get("cpu_freq")
        cpu_percent = sys_stats.get("cpu_percent", 0)
        
        cpu_value = f"**Cores:** {cpu_physical} physical, {cpu_logical} logical\n"
        if cpu_freq:
            cpu_value += f"**Frequency:** {cpu_freq.current:.0f} MHz\n"
        cpu_value += f"**Usage:** {self._create_progress_bar(cpu_percent)} {cpu_percent:.1f}% {self._get_health_indicator(cpu_percent)}"
        
        embed.add_field(
            name="⚡ CPU",
            value=cpu_value,
            inline=True
        )
        
        # Section 4: Memory Information
        mem_total = sys_stats.get("memory_total", 0) / (1024**3)  # GB
        mem_used = sys_stats.get("memory_used", 0) / (1024**3)  # GB
        mem_percent = sys_stats.get("memory_percent", 0)
        
        embed.add_field(
            name="💾 Memory",
            value=f"**Total:** {mem_total:.2f} GB\n"
                  f"**Used:** {mem_used:.2f} GB\n"
                  f"**Usage:** {self._create_progress_bar(mem_percent)} {mem_percent:.1f}% {self._get_health_indicator(mem_percent)}",
            inline=False
        )
        
        # Section 5: Disk Information
        disk_total = sys_stats.get("disk_total", 0) / (1024**3)  # GB
        disk_used = sys_stats.get("disk_used", 0) / (1024**3)  # GB
        disk_free = sys_stats.get("disk_free", 0) / (1024**3)  # GB
        disk_percent = sys_stats.get("disk_percent", 0)
        
        embed.add_field(
            name="💿 Disk",
            value=f"**Total:** {disk_total:.2f} GB\n"
                  f"**Used:** {disk_used:.2f} GB | **Free:** {disk_free:.2f} GB\n"
                  f"**Usage:** {self._create_progress_bar(disk_percent)} {disk_percent:.1f}% {self._get_health_indicator(disk_percent)}",
            inline=False
        )
        
        # Section 6: Bot Statistics
        uptime_seconds = time.time() - self.start_time
        uptime_str = str(timedelta(seconds=int(uptime_seconds)))
        total_channels = sum(len(guild.channels) for guild in self.bot.guilds)
        
        embed.add_field(
            name="🤖 Bot Statistics",
            value=f"**Servers:** `{len(self.bot.guilds)}`\n"
                  f"**Channels:** `{total_channels}`\n"
                  f"**Uptime:** `{uptime_str}`",
            inline=True
        )
        
        # Section 7: AI Statistics
        total_ais = ai_stats.get("total_ais", 0)
        providers = ai_stats.get("providers", {})
        registered_providers = ai_stats.get("registered_providers", [])
        
        providers_str = ", ".join([f"`{p}`" for p in registered_providers[:5]]) if registered_providers else "None"
        if len(registered_providers) > 5:
            providers_str += f" +{len(registered_providers) - 5}"
        
        ai_value = f"**Active AIs:** `{total_ais}`\n"
        ai_value += f"**Providers:** {providers_str}\n"
        
        if providers:
            top_providers = sorted(providers.items(), key=lambda x: x[1], reverse=True)[:3]
            ai_value += f"**Most Used:** " + ", ".join([f"{p} ({c})" for p, c in top_providers])
        
        embed.add_field(
            name="🧠 Artificial Intelligence",
            value=ai_value,
            inline=True
        )
        
        # Section 8: API Connections & Character Cards
        total_connections = ai_stats.get("total_connections", 0)
        total_cards = ai_stats.get("total_cards", 0)
        cards_in_use = ai_stats.get("cards_in_use", 0)
        
        embed.add_field(
            name="📚 Resources",
            value=f"**API Connections:** `{total_connections}`\n"
                  f"**Character Cards:** `{total_cards}` (in use: `{cards_in_use}`)",
            inline=True
        )
        
        # Section 9: Process Information
        process_threads = sys_stats.get("process_threads", "N/A")
        process_fds = sys_stats.get("process_fds", "N/A")
        process_memory = sys_stats.get("process_memory", 0) / (1024**2)  # MB
        process_cpu = sys_stats.get("process_cpu", 0)
        
        embed.add_field(
            name="📊 Process",
            value=f"**Threads:** `{process_threads}`\n"
                  f"**File Descriptors:** `{process_fds}`\n"
                  f"**Memory:** `{process_memory:.2f} MB`\n"
                  f"**CPU:** `{process_cpu:.1f}%`",
            inline=True
        )
        
        # Section 10: Storage
        session_size = storage_stats.get("session_size", 0) / 1024  # KB
        conversations_size = storage_stats.get("conversations_size", 0) / 1024  # KB
        total_data_size = storage_stats.get("total_data_size", 0) / 1024  # KB
        
        embed.add_field(
            name="💾 Storage",
            value=f"**session.json:** `{session_size:.2f} KB`\n"
                  f"**conversations.json:** `{conversations_size:.2f} KB`\n"
                  f"**Total Data:** `{total_data_size:.2f} KB`",
            inline=True
        )
        
        # Section 11: Network (Gateway latency)
        gateway_ping = round(self.bot.latency * 1000)
        gateway_indicator = self._get_health_indicator(min(gateway_ping / 5, 100))  # Scale to percentage
        
        embed.add_field(
            name="🌐 Network",
            value=f"**Discord Gateway:** `{gateway_ping}ms` {gateway_indicator}",
            inline=True
        )
        
        embed.set_footer(text="System monitored • Use /debug_status for more details")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="clear_debug", description="Clear messages from the debug channel")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(limit="Number of messages to delete (default: 100)")
    async def clear_debug(self, interaction: discord.Interaction, limit: int = 100):
        """Clear messages from the debug channel."""
        await interaction.response.defer(ephemeral=True)

        server_id = str(interaction.guild.id)

        # Load config for this server
        from utils.core.paths import DataPaths

        data_paths = DataPaths()
        debug_config_file = data_paths.get_debug_config_file(server_id)

        if not os.path.exists(debug_config_file):
            await interaction.followup.send(
                "❌ Debug channel not configured.",
                ephemeral=True
            )
            return

        server_config = func.read_json(debug_config_file) or {}

        if not server_config or not server_config.get("debug_channel_id"):
            await interaction.followup.send(
                "❌ Debug channel not configured.",
                ephemeral=True
            )
            return
        
        # Get channel
        channel_id = server_config["debug_channel_id"]
        channel = self.bot.get_channel(int(channel_id))
        
        if not channel:
            await interaction.followup.send(
                "❌ Debug channel not found.",
                ephemeral=True
            )
            return
        
        # Validate limit
        if limit < 1 or limit > 1000:
            await interaction.followup.send(
                "❌ Limit must be between 1 and 1000.",
                ephemeral=True
            )
            return
        
        try:
            # Delete messages
            deleted = await channel.purge(limit=limit)
            
            await interaction.followup.send(
                f"✅ Deleted {len(deleted)} message(s) from {channel.mention}",
                ephemeral=True
            )
            
            func.log.info(f"Cleared {len(deleted)} messages from debug channel")
            
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to delete messages in that channel.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"❌ Error deleting messages: {e}",
                ephemeral=True
            )
    
    @app_commands.command(name="restart", description="Restart the bot (requires confirmation)")
    @app_commands.default_permissions(administrator=True)
    async def restart(self, interaction: discord.Interaction):
        """Restart the bot with confirmation."""
        # Send confirmation message
        confirm_msg = await interaction.channel.send(
            f"⚠️ **Bot Restart Confirmation** (requested by {interaction.user.mention})\n\n"
            f"**This will restart the entire bot process!**\n"
            f"All active operations will be interrupted.\n\n"
            f"**React with ✅ to confirm or ❌ to cancel.**"
        )
        
        # Send ephemeral acknowledgment
        await interaction.response.send_message(
            "✅ Confirmation message sent. Please react to confirm or cancel.",
            ephemeral=True
        )
        
        # Add reactions
        try:
            await confirm_msg.add_reaction("✅")
            await confirm_msg.add_reaction("❌")
        except discord.HTTPException as e:
            func.log.error(f"Failed to add reactions: {e}")
            await confirm_msg.edit(content=f"{confirm_msg.content}\n\n❌ Failed to add reactions. Please try again.")
            return
        
        # Wait for reaction
        def check(reaction, user):
            return (
                user.id == interaction.user.id and
                str(reaction.emoji) in ["✅", "❌"] and
                reaction.message.id == confirm_msg.id
            )
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            
            if str(reaction.emoji) == "❌":
                await confirm_msg.edit(content="❌ Bot restart cancelled.")
                return
            
            # User confirmed with ✅
            await confirm_msg.edit(content="🔄 Restarting bot...")
            
            func.log.warning(f"Bot restart initiated by user {interaction.user.id}")
            
            # Wait a moment for the message to send
            await asyncio.sleep(1)
            
            # Restart the bot
            os.execv(sys.executable, [sys.executable] + sys.argv)
            
        except asyncio.TimeoutError:
            await confirm_msg.edit(content="⏱️ Timeout. Bot restart cancelled.")
    
    @app_commands.command(name="cache_stats", description="Display cache and rate limiting statistics")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(channel_id="Optional: Show stats for a specific channel")
    async def cache_stats(self, interaction: discord.Interaction, channel_id: str = None):
        """Display comprehensive cache and rate limiting statistics."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            from utils.message_cache import get_all_stats, get_message_cache
            
            # Get all statistics
            all_stats = get_all_stats()
            
            # Create embed
            embed = discord.Embed(
                title="📊 Cache & Rate Limiting Statistics",
                description="Comprehensive view of the message caching and rate limiting systems",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            # Cache Statistics
            cache_stats = all_stats.get("cache", {})
            hit_rate = cache_stats.get("hit_rate", "0.0%")
            
            cache_value = f"**Size:** {cache_stats.get('size', 0)}/{cache_stats.get('max_size', 0)}\n"
            cache_value += f"**Hits:** {cache_stats.get('hits', 0)}\n"
            cache_value += f"**Misses:** {cache_stats.get('misses', 0)}\n"
            cache_value += f"**Hit Rate:** {hit_rate}\n"
            cache_value += f"**Evictions:** {cache_stats.get('evictions', 0)}\n"
            cache_value += f"**Expirations:** {cache_stats.get('expirations', 0)}\n"
            cache_value += f"**Channels Tracked:** {cache_stats.get('channels_tracked', 0)}"
            
            embed.add_field(
                name="💾 Message Cache",
                value=cache_value,
                inline=False
            )
            
            # Request Deduplication Statistics
            dedup_stats = all_stats.get("deduplicator", {})
            dedup_value = f"**Pending Requests:** {dedup_stats.get('pending_requests', 0)}\n"
            dedup_value += f"**Requests Saved:** {dedup_stats.get('dedup_saves', 0)}"
            
            if dedup_stats.get('dedup_saves', 0) > 0:
                dedup_value += f"\n\n✅ **Prevented {dedup_stats.get('dedup_saves', 0)} duplicate API calls!**"
            
            embed.add_field(
                name="🔄 Request Deduplication",
                value=dedup_value,
                inline=True
            )
            
            # Semaphore Manager Statistics
            sem_stats = all_stats.get("semaphore_manager", {})
            sem_value = f"**Channels:** {sem_stats.get('total_channels', 0)}\n"
            sem_value += f"**Max Concurrent/Channel:** {sem_stats.get('max_concurrent_per_channel', 1)}"
            
            embed.add_field(
                name="🚦 Semaphore Manager",
                value=sem_value,
                inline=True
            )
            
            # Channel Rate Limiter Statistics
            limiter_stats = all_stats.get("channel_rate_limiter", {})
            total_requests = limiter_stats.get('total_requests', 0)
            total_429s = limiter_stats.get('total_429s', 0)
            total_wait = limiter_stats.get('total_wait_time', 0)
            avg_wait = limiter_stats.get('avg_wait_time', 0)
            
            limiter_value = f"**Total Requests:** {total_requests}\n"
            limiter_value += f"**Rate Limits (429):** {total_429s}\n"
            limiter_value += f"**Total Wait Time:** {total_wait:.2f}s\n"
            limiter_value += f"**Avg Wait Time:** {avg_wait:.3f}s"
            
            if total_429s > 0:
                rate_limit_rate = (total_429s / total_requests * 100) if total_requests > 0 else 0
                limiter_value += f"\n\n⚠️ **Rate Limit Rate:** {rate_limit_rate:.2f}%"
            else:
                limiter_value += f"\n\n✅ **No rate limits!**"
            
            embed.add_field(
                name="⏱️ Channel Rate Limiter",
                value=limiter_value,
                inline=False
            )
            
            # Adaptive Backoff Statistics
            backoff_stats = all_stats.get("adaptive_backoff", {})
            channels_with_penalty = backoff_stats.get('channels_with_penalty', 0)
            
            if channels_with_penalty > 0:
                backoff_value = f"**Channels with Penalty:** {channels_with_penalty}\n\n"
                penalties = backoff_stats.get('penalties', {})
                
                # Show top 5 channels with highest penalties
                sorted_penalties = sorted(
                    penalties.items(),
                    key=lambda x: x[1]['penalty'],
                    reverse=True
                )[:5]
                
                for channel_id_str, penalty_data in sorted_penalties:
                    penalty = penalty_data.get('penalty', 0)
                    last_429 = penalty_data.get('last_429', 0)
                    
                    if last_429 > 0:
                        time_ago = int(time.time() - last_429)
                        backoff_value += f"Channel `{channel_id_str}`: {penalty:.1f}s (<t:{int(last_429)}:R>)\n"
                    else:
                        backoff_value += f"Channel `{channel_id_str}`: {penalty:.1f}s\n"
            else:
                backoff_value = "✅ **No channels with penalties**"
            
            embed.add_field(
                name="🎯 Adaptive Backoff",
                value=backoff_value,
                inline=True
            )
            
            # Circuit Breaker Statistics
            breaker_stats = all_stats.get("circuit_breaker", {})
            open_circuits = breaker_stats.get('open_circuits', 0)
            
            if open_circuits > 0:
                breaker_value = f"⚠️ **Open Circuits:** {open_circuits}\n\n"
                circuits = breaker_stats.get('circuits', {})
                
                for channel_id_str, circuit_data in list(circuits.items())[:5]:
                    failures = circuit_data.get('failures', 0)
                    opened_at = circuit_data.get('opened_at')
                    
                    if opened_at:
                        breaker_value += f"Channel `{channel_id_str}`: {failures} failures (opened <t:{int(opened_at)}:R>)\n"
                    else:
                        breaker_value += f"Channel `{channel_id_str}`: {failures} failures\n"
            else:
                breaker_value = "✅ **All circuits closed**"
            
            embed.add_field(
                name="🔌 Circuit Breaker",
                value=breaker_value,
                inline=True
            )
            
            # Per-channel statistics if requested
            if channel_id:
                try:
                    cache = get_message_cache()
                    channel_stats = cache.get_stats(channel_id)
                    
                    if channel_stats:
                        channel_value = f"**Hits:** {channel_stats.get('hits', 0)}\n"
                        channel_value += f"**Misses:** {channel_stats.get('misses', 0)}\n"
                        channel_value += f"**API Requests:** {channel_stats.get('api_requests', 0)}\n"
                        channel_value += f"**Hit Rate:** {channel_stats.get('hit_rate', '0.0%')}"
                        
                        embed.add_field(
                            name=f"📍 Channel {channel_id}",
                            value=channel_value,
                            inline=False
                        )
                    else:
                        embed.add_field(
                            name=f"📍 Channel {channel_id}",
                            value="No statistics available for this channel",
                            inline=False
                        )
                except Exception as e:
                    func.log.error(f"Error getting channel stats: {e}")
            
            # Performance Summary
            if total_requests > 0:
                api_requests = cache_stats.get('misses', 0)
                dedup_saves = dedup_stats.get('dedup_saves', 0)
                
                # Calculate reduction
                potential_requests = api_requests + dedup_saves
                if potential_requests > 0:
                    reduction = (dedup_saves / potential_requests * 100)
                    
                    summary = f"**Potential API Requests:** {potential_requests}\n"
                    summary += f"**Actual API Requests:** {api_requests}\n"
                    summary += f"**Reduction:** {reduction:.1f}%\n\n"
                    summary += f"✅ **Saved {dedup_saves} API calls through deduplication!**"
                    
                    embed.add_field(
                        name="📈 Performance Summary",
                        value=summary,
                        inline=False
                    )
            
            embed.set_footer(text="Use /cache_stats channel_id:<id> for per-channel stats")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            func.log.error(f"Error displaying cache stats: {e}")
            await interaction.followup.send(
                f"❌ Error retrieving cache statistics: {e}",
                ephemeral=True
            )


async def setup(bot):
    """Setup the DebugCommands cog."""
    await bot.add_cog(DebugCommands(bot))
