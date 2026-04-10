"""
Debug Embed System - Guild-Scoped Debug Information

This module provides a structured debug embed system for sending informative
embeds to configured debug channels. All embeds are guild-scoped to prevent
cross-contamination between servers.

Usage:
    await DebugEmbed.send(guild, event="setup", data={...})
    await DebugEmbed.send(guild, event="llm_response", data={...})
    await DebugEmbed.send(guild, event="error", data={...})
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path

import discord

import utils.func as func

log = logging.getLogger(__name__)


class DebugEmbed:
    """
    Guild-scoped debug embed system.
    
    Provides structured, visually consistent debug information sent to
    configured debug channels. All operations are guild-scoped to ensure
    zero cross-contamination between servers.
    """
    
    # Color palette by category
    COLORS = {
        "success": discord.Color.green(),
        "info": discord.Color.blue(),
        "llm": discord.Color.dark_embed(),
        "warning": discord.Color.gold(),
        "error": discord.Color.red(),
        "critical": discord.Color.dark_red(),
    }
    
    # Event type to color mapping
    EVENT_COLORS = {
        "setup": "success",
        "character": "success",
        "provider": "success",
        "reset": "success",
        "config_change": "info",
        "api_connection_created": "success",
        "api_connection_edited": "info",
        "api_connection_removed": "warning",
        "remove_ai": "warning",
        "llm_response": "llm",
        "ignore_detected": "warning",
        "sleep_mode_change": "info",
        "bot_status_change": "info",
        "bot_startup": "success",
        "bot_shutdown": "warning",
        "error": "error",
        "warning": "warning",
        "critical": "critical",
    }
    
    @classmethod
    async def send(
        cls,
        guild: discord.Guild,
        event: str,
        data: Dict[str, Any],
        force: bool = False
    ) -> bool:
        """
        Send a debug embed to the configured debug channel.
        
        Args:
            guild: Discord guild where the event occurred
            event: Event type (e.g., "setup", "llm_response", "error")
            data: Event-specific data dictionary
            force: If True, send even if debug is disabled (for critical events)
            
        Returns:
            True if embed was sent successfully, False otherwise
        """
        if not guild:
            log.debug("No guild provided, skipping debug embed")
            return False
        
        server_id = str(guild.id)
        
        try:
            # Check if debug is enabled (unless forced)
            if not force and not cls._is_enabled(server_id):
                return False
            
            # Get debug channel
            channel = cls._get_debug_channel(guild)
            if not channel:
                log.debug(f"No debug channel configured for guild {server_id}")
                return False
            
            # Build embed based on event type
            embed = await cls._build_embed(guild, channel, event, data, server_id)
            if not embed:
                log.warning(f"Failed to build embed for event: {event}")
                return False
            
            # Send embed
            return await cls._send_embed(channel, embed)
            
        except Exception as e:
            # Never crash the main flow due to debug failures
            log.error(f"Error sending debug embed for event '{event}': {e}")
            return False
    
    @classmethod
    async def send_to_all_guilds(
        cls,
        bot,
        event: str,
        data: Dict[str, Any]
    ) -> int:
        """
        Send debug embed to all guilds with debug enabled.
        
        This is used for global bot events (startup, shutdown, status changes)
        that aren't specific to a single guild.
        
        Args:
            bot: Discord bot instance
            event: Event type (e.g., "bot_startup", "bot_shutdown")
            data: Event-specific data dictionary
            
        Returns:
            Number of guilds that successfully received the embed
        """
        if not bot or not bot.guilds:
            log.debug("No guilds available for debug embed broadcast")
            return 0
        
        success_count = 0
        
        for guild in bot.guilds:
            try:
                if await cls.send(guild, event, data):
                    success_count += 1
            except Exception as e:
                log.error(f"Error sending debug embed to guild {guild.id}: {e}")
                continue
        
        if success_count > 0:
            log.info(f"Sent '{event}' debug embed to {success_count}/{len(bot.guilds)} guild(s)")
        
        return success_count
    
    @classmethod
    def _is_enabled(cls, server_id: str) -> bool:
        """
        Check if debug embeds are enabled for a server.
        
        Args:
            server_id: Server ID to check
            
        Returns:
            True if enabled, False otherwise
        """
        try:
            from utils.core.paths import DataPaths
            import os
            
            data_paths = DataPaths()
            debug_config_file = data_paths.get_debug_config_file(server_id)
            
            if not os.path.exists(debug_config_file):
                return False
            
            config = func.read_json(debug_config_file) or {}
            return config.get("enabled", False)
            
        except Exception as e:
            log.error(f"Error checking debug status: {e}")
            return False
    
    @classmethod
    def _get_debug_channel(cls, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """
        Get the configured debug channel for a guild.
        
        Args:
            guild: Discord guild
            
        Returns:
            Debug channel or None if not configured
        """
        try:
            from utils.core.paths import DataPaths
            import os
            
            server_id = str(guild.id)
            data_paths = DataPaths()
            debug_config_file = data_paths.get_debug_config_file(server_id)
            
            if not os.path.exists(debug_config_file):
                return None
            
            config = func.read_json(debug_config_file) or {}
            channel_id = config.get("debug_channel_id")
            
            if not channel_id:
                return None
            
            channel = guild.get_channel(int(channel_id))
            return channel if isinstance(channel, discord.TextChannel) else None
            
        except Exception as e:
            log.error(f"Error getting debug channel: {e}")
            return None
    
    @classmethod
    async def _send_embed(cls, channel: discord.TextChannel, embed: discord.Embed) -> bool:
        """
        Send an embed to a channel with error handling.
        
        Args:
            channel: Channel to send to
            embed: Embed to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            await channel.send(embed=embed)
            return True
        except discord.Forbidden:
            log.warning(f"No permission to send to debug channel {channel.id}")
            return False
        except discord.HTTPException as e:
            log.error(f"HTTP error sending debug embed: {e}")
            return False
        except Exception as e:
            log.error(f"Error sending debug embed: {e}")
            return False
    
    @classmethod
    async def _build_embed(
        cls,
        guild: discord.Guild,
        channel: discord.TextChannel,
        event: str,
        data: Dict[str, Any],
        server_id: str
    ) -> Optional[discord.Embed]:
        """
        Build an embed based on event type.
        
        Args:
            guild: Discord guild
            channel: Discord channel
            event: Event type
            data: Event data
            server_id: Server ID for footer
            
        Returns:
            Discord embed or None if build failed
        """
        try:
            # Route to appropriate builder
            if event in ["setup", "character", "provider", "reset", "config_change",
                        "api_connection_created", "api_connection_edited",
                        "api_connection_removed", "remove_ai"]:
                return cls._build_command_embed(event, data, server_id)
            elif event == "llm_response":
                return await cls._build_llm_response_embed(guild, channel, data, server_id)
            elif event == "ignore_detected":
                return await cls._build_ignore_embed(guild, channel, data, server_id)
            elif event in ["sleep_mode_change", "bot_status_change", "bot_startup", "bot_shutdown"]:
                return cls._build_system_event_embed(event, data, server_id)
            elif event in ["error", "warning", "critical"]:
                return cls._build_error_embed(data, server_id)
            else:
                log.warning(f"Unknown event type: {event}")
                return None
                
        except Exception as e:
            log.error(f"Error building embed for event '{event}': {e}")
            return None
    
    @classmethod
    def _get_color(cls, event: str) -> discord.Color:
        """Get color for an event type."""
        color_name = cls.EVENT_COLORS.get(event, "info")
        return cls.COLORS.get(color_name, discord.Color.blue())
    
    @classmethod
    def _build_footer(cls, server_id: str) -> str:
        """
        Build standard footer text.
        
        Args:
            server_id: Server ID
            
        Returns:
            Footer text
        """
        try:
            with open("version.txt", "r") as f:
                version = f.read().strip()
        except:
            version = "Unknown"
        
        return f"Project Hashi v{version} • Server: {server_id}"
    
    @classmethod
    async def _get_thumbnail_url(cls, session: Optional[Dict[str, Any]], server_id: str) -> Optional[str]:
        """
        Get thumbnail URL from character card or bot avatar.
        
        Args:
            session: AI session data
            server_id: Server ID
            
        Returns:
            Thumbnail URL or None
        """
        if not session:
            return None
        
        try:
            # Try to extract from character card
            cache_path = session.get("character_card", {}).get("cache_path")
            if cache_path:
                from commands.shared.avatar_utils import AvatarUtils
                avatar_bytes = await AvatarUtils.extract_from_card(cache_path)
                
                if avatar_bytes:
                    # For now, we can't easily convert bytes to URL without uploading
                    # This would require creating a temporary file or using Discord's CDN
                    # For simplicity, we'll skip thumbnail for now and add it later
                    pass
            
            # Could also try bot avatar as fallback, but that requires bot instance
            return None
            
        except Exception as e:
            log.debug(f"Error getting thumbnail: {e}")
            return None
    
    @classmethod
    def _create_progress_bar(cls, current: int, maximum: int, length: int = 10) -> str:
        """
        Create a visual progress bar.
        
        Args:
            current: Current value
            maximum: Maximum value
            length: Bar length in characters
            
        Returns:
            Progress bar string (e.g., "▓▓▓░░░░░░░")
        """
        if maximum <= 0:
            return "░" * length
        
        percentage = min(current / maximum, 1.0)
        filled = int(percentage * length)
        return "▓" * filled + "░" * (length - filled)
    
    @classmethod
    def _format_number(cls, num: int) -> str:
        """Format number with k/M suffix."""
        if num >= 1_000_000:
            return f"{num / 1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num / 1_000:.1f}k"
        else:
            return str(num)
    
    @classmethod
    def _build_command_embed(cls, event: str, data: Dict[str, Any], server_id: str) -> discord.Embed:
        """
        Build embed for command completion events.
        
        Args:
            event: Event type
            data: Event data
            server_id: Server ID
            
        Returns:
            Discord embed
        """
        # Event-specific titles and emojis
        event_info = {
            "setup": ("✅", "Setup Complete"),
            "character": ("🎭", "Character Applied"),
            "provider": ("🔄", "Provider Changed"),
            "reset": ("🔄", "History Reset"),
            "config_change": ("⚙️", "Config Changed"),
            "api_connection_created": ("🔌", "API Connection Created"),
            "api_connection_edited": ("✏️", "API Connection Edited"),
            "api_connection_removed": ("🗑️", "API Connection Removed"),
            "remove_ai": ("❌", "AI Removed"),
        }
        
        emoji, title_base = event_info.get(event, ("ℹ️", "Command"))
        
        # Build title
        ai_name = data.get("ai_name", "")
        if ai_name:
            title = f"{emoji} {title_base}: {ai_name}"
        else:
            title = f"{emoji} {title_base}"
        
        # Create embed
        embed = discord.Embed(
            title=title,
            color=cls._get_color(event),
            timestamp=datetime.now()
        )
        
        # Add executor info if available
        executor = data.get("executor")
        channel = data.get("channel")
        if executor or channel:
            desc_parts = []
            if executor:
                desc_parts.append(f"**Executed by:** {executor}")
            if channel:
                desc_parts.append(f"**Channel:** {channel}")
            embed.description = "\n".join(desc_parts)
        
        # Add changes/details
        changes = data.get("changes", {})
        if changes:
            for key, value in changes.items():
                # Format key nicely
                field_name = key.replace("_", " ").title()
                embed.add_field(name=field_name, value=str(value), inline=False)
        
        # Add connection-specific fields
        if event.startswith("api_connection"):
            if "connection_name" in data:
                embed.add_field(name="Connection", value=data["connection_name"], inline=True)
            if "provider" in data:
                embed.add_field(name="Provider", value=data["provider"], inline=True)
            if "endpoint" in data:
                embed.add_field(name="Endpoint", value=data["endpoint"], inline=True)
            if "model" in data:
                embed.add_field(name="Model", value=data["model"], inline=True)
        
        # Add config change specific fields
        if event == "config_change":
            if "category" in data:
                embed.add_field(name="Category", value=data["category"], inline=True)
            if "setting" in data:
                embed.add_field(name="Setting", value=data["setting"], inline=True)
            if "old_value" in data and "new_value" in data:
                change_text = f"{data['old_value']} → {data['new_value']}"
                embed.add_field(name="Change", value=change_text, inline=False)
        
        # Set footer
        embed.set_footer(text=cls._build_footer(server_id))
        
        return embed
    
    @classmethod
    async def _build_llm_response_embed(
        cls,
        guild: discord.Guild,
        channel: discord.TextChannel,
        data: Dict[str, Any],
        server_id: str
    ) -> discord.Embed:
        """
        Build embed for LLM response events.
        
        Args:
            guild: Discord guild
            channel: Discord channel
            data: Event data
            server_id: Server ID
            
        Returns:
            Discord embed
        """
        ai_name = data.get("ai_name", "AI")
        provider_raw = data.get("provider", "unknown")
        model = data.get("model", "unknown")

        # Get provider display name from registry
        try:
            from AI.core.registry import get_registry
            registry = get_registry()
            provider_meta = registry.get_metadata(provider_raw.lower())
            provider_display = provider_meta.display_name
        except:
            provider_display = provider_raw

        # Create embed
        embed = discord.Embed(
            title=f"Debug Mode: {ai_name}",
            color=cls._get_color("llm_response"),
            timestamp=datetime.now()
        )
        
        # Set bot author with icon
        try:
            bot = guild.me
            if bot:
                embed.set_author(
                    name=f"@{bot.name}",
                    icon_url=bot.display_avatar.url
                )
        except Exception as e:
            log.debug(f"Could not set author icon: {e}")
        
        # Set character card thumbnail
        try:
            session = data.get("session")
            if session:
                from utils.media.thumbnails import get_thumbnail_url
                thumbnail_url = await get_thumbnail_url(
                    channel,
                    session,
                    server_id=server_id
                )
                if thumbnail_url:
                    embed.set_thumbnail(url=thumbnail_url)
        except Exception as e:
            log.debug(f"Could not set thumbnail: {e}")
        
        # Provider & Model
        embed.add_field(
            name="Provider & Model",
            value=f"{provider_display} • {model}",
            inline=False
        )
        
        # Channel
        channel_mention = data.get("channel")
        if channel_mention:
            embed.add_field(
                name="Channel",
                value=channel_mention,
                inline=False
            )
        
        # Token Usage
        tokens = data.get("tokens", {})
        if tokens:
            system_tokens = tokens.get("system", 0)
            context_tokens = tokens.get("context", 0)
            completion_tokens = tokens.get("completion", 0)
            total_tokens = tokens.get("total", 0)
            context_window = tokens.get("context_window", 0)
            
            # Clear breakdown: System (static) | Context (messages) on first line
            # Completion (current response) | Total on second line
            token_text = f"**System Prompt:** {cls._format_number(system_tokens)} | "
            token_text += f"**Context:** {cls._format_number(context_tokens)}\n"
            token_text += f"**Completion:** {cls._format_number(completion_tokens)} | "
            token_text += f"**Total:** {cls._format_number(total_tokens)}"
            
            # Context window progress bar
            if context_window > 0:
                percentage = (total_tokens / context_window) * 100
                progress_bar = cls._create_progress_bar(total_tokens, context_window)
                token_text += f"\n**Window:** {progress_bar} "
                token_text += f"{cls._format_number(total_tokens)} / {cls._format_number(context_window)} "
                token_text += f"({percentage:.1f}%)"
            
            embed.add_field(name="Token Usage", value=token_text, inline=False)
        
        # Memory
        memory = data.get("memory", {})
        if memory:
            msg_count = memory.get("messages_count", 0)
            est_tokens = memory.get("estimated_tokens", 0)
            memory_text = f"{msg_count} messages • ~{cls._format_number(est_tokens)} tokens (history + input)"
            embed.add_field(name="Memory", value=memory_text, inline=False)
        
        # Tool Calls
        tool_calls = data.get("tool_calls", [])
        if tool_calls:
            tool_text = "\n".join([
                f"• **{call.get('name', 'unknown')}**: {call.get('result', 'N/A')}"
                for call in tool_calls[:5]  # Limit to 5
            ])
            if len(tool_calls) > 5:
                tool_text += f"\n... and {len(tool_calls) - 5} more"
            embed.add_field(name="Tool Calls", value=tool_text, inline=False)
        
        # Performance - Show both latency and TPS if available
        latency_ms = data.get("latency_ms")
        tps = data.get("tps")
        if latency_ms is not None or tps is not None:
            perf_parts = []
            if latency_ms is not None:
                perf_parts.append(f"**Latency:** {latency_ms}ms")
            if tps is not None:
                perf_parts.append(f"**Speed:** {tps:.2f} TPS")
            
            perf_text = " | ".join(perf_parts)
            embed.add_field(name="Performance", value=perf_text, inline=False)
        
        # Raw Response (truncated)
        raw_response = data.get("raw_response", "")
        if raw_response:
            # Truncate if too long
            max_length = 1000
            if len(raw_response) > max_length:
                raw_response = raw_response[:max_length] + "..."
            
            embed.add_field(
                name="Raw Response",
                value=f"```\n{raw_response}\n```",
                inline=False
            )
        
        # Set footer
        embed.set_footer(text=cls._build_footer(server_id))
        
        return embed
    
    @classmethod
    def _build_system_event_embed(cls, event: str, data: Dict[str, Any], server_id: str) -> discord.Embed:
        """
        Build embed for system events (sleep mode, bot status, etc.).
        
        Args:
            event: Event type
            data: Event data
            server_id: Server ID
            
        Returns:
            Discord embed
        """
        # Event-specific configuration
        event_config = {
            "sleep_mode_change": ("😴", "Sleep Mode"),
            "bot_status_change": ("🤖", "Bot Status Changed"),
            "bot_startup": ("🚀", "Bot Started"),
            "bot_shutdown": ("🛑", "Bot Shutdown"),
        }
        
        emoji, title_base = event_config.get(event, ("ℹ️", "System Event"))
        
        # Build title
        ai_name = data.get("ai_name", "")
        if ai_name:
            title = f"{emoji} {title_base}: {ai_name}"
        else:
            title = f"{emoji} {title_base}"
        
        # Create embed
        embed = discord.Embed(
            title=title,
            color=cls._get_color(event),
            timestamp=datetime.now()
        )
        
        # Event-specific fields
        if event == "sleep_mode_change":
            status = data.get("status", "unknown")
            embed.add_field(name="Status", value=f"{status.title()} sleep mode", inline=True)
            
            channel = data.get("channel")
            if channel:
                embed.add_field(name="Channel", value=channel, inline=True)
            
            reason = data.get("reason")
            if reason:
                embed.add_field(name="Reason", value=reason, inline=False)
            
            if status == "entered":
                embed.description = "The AI will wake up when mentioned directly."
        
        elif event == "bot_status_change":
            old_status = data.get("old_status", "unknown")
            new_status = data.get("new_status", "unknown")
            embed.add_field(name="Status Change", value=f"{old_status} → {new_status}", inline=False)
            
            reason = data.get("reason")
            if reason:
                embed.add_field(name="Reason", value=reason, inline=False)
            
            ais_in_sleep = data.get("ais_in_sleep", [])
            if ais_in_sleep:
                ais_text = "\n".join([f"• {ai}" for ai in ais_in_sleep[:10]])
                if len(ais_in_sleep) > 10:
                    ais_text += f"\n... and {len(ais_in_sleep) - 10} more"
                embed.add_field(name="AIs in Sleep Mode", value=ais_text, inline=False)
        
        elif event == "bot_startup":
            version = data.get("version", "Unknown")
            servers = data.get("servers", 0)
            total_ais = data.get("total_ais", 0)
            
            embed.add_field(name="Version", value=version, inline=True)
            embed.add_field(name="Servers", value=str(servers), inline=True)
            embed.add_field(name="Total AIs", value=str(total_ais), inline=True)
        
        elif event == "bot_shutdown":
            reason = data.get("reason", "Unknown")
            uptime = data.get("uptime", 0)
            
            embed.add_field(name="Reason", value=reason, inline=True)
            
            # Format uptime
            hours = int(uptime // 3600)
            minutes = int((uptime % 3600) // 60)
            uptime_str = f"{hours}h {minutes}m"
            embed.add_field(name="Uptime", value=uptime_str, inline=True)
        
        # Set footer
        embed.set_footer(text=cls._build_footer(server_id))
        
        return embed
    
    @classmethod
    def _build_error_embed(cls, data: Dict[str, Any], server_id: str) -> discord.Embed:
        """
        Build embed for error/warning events.
        
        Args:
            data: Event data
            server_id: Server ID
            
        Returns:
            Discord embed
        """
        severity = data.get("severity", "error")
        title = data.get("title", "Error")
        
        # Severity emoji
        severity_emoji = {
            "critical": "🔴",
            "error": "🔴",
            "warning": "🟡",
            "info": "🔵",
        }
        emoji = severity_emoji.get(severity, "🔴")
        
        # Create embed
        embed = discord.Embed(
            title=f"{emoji} {title}",
            color=cls._get_color(severity),
            timestamp=datetime.now()
        )
        
        # Error type
        error_type = data.get("error_type")
        if error_type:
            embed.add_field(name="Error Type", value=error_type, inline=True)
        
        # Message
        message = data.get("message")
        if message:
            # Truncate if too long
            if len(message) > 1000:
                message = message[:1000] + "..."
            embed.add_field(name="Message", value=message, inline=False)
        
        # Context
        context = data.get("context", {})
        if context:
            context_text = "\n".join([
                f"**{k.replace('_', ' ').title()}:** {v}"
                for k, v in context.items()
            ])
            embed.add_field(name="Context", value=context_text, inline=False)
        
        # Suggestion
        suggestion = data.get("suggestion")
        if suggestion:
            embed.add_field(name="Suggestion", value=suggestion, inline=False)
        
        # Set footer
        embed.set_footer(text=cls._build_footer(server_id))
        
        return embed
    
    @classmethod
    async def _build_ignore_embed(
        cls,
        guild: discord.Guild,
        channel: discord.TextChannel,
        data: Dict[str, Any],
        server_id: str
    ) -> discord.Embed:
        """
        Build embed for ignore detection events.
        
        Args:
            guild: Discord guild
            channel: Discord channel
            data: Event data
            server_id: Server ID
            
        Returns:
            Discord embed
        """
        ai_name = data.get("ai_name", "AI")
        ignore_type = data.get("ignore_type", "unknown")
        is_pure = ignore_type == "pure"
        
        # Title and color based on ignore type
        if is_pure:
            title = f"🚫 Ignore Detected: {ai_name}"
            color = cls._get_color("ignore_detected")
            description = "AI decided not to respond to this conversation"
        else:
            title = f"⚠️ Impure Ignore Detected: {ai_name}"
            color = cls.COLORS["error"]
            description = "AI used <IGNORE> incorrectly with additional content"
        
        # Create embed
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now()
        )
        
        # Set bot author with icon
        try:
            bot = guild.me
            if bot:
                embed.set_author(
                    name=f"@{bot.name}",
                    icon_url=bot.display_avatar.url
                )
        except Exception as e:
            log.debug(f"Could not set author icon: {e}")
        
        # Field 1: Ignore Type
        embed.add_field(
            name="Ignore Type",
            value=ignore_type.title(),
            inline=True
        )
        
        # Field 2: Channel
        channel_mention = data.get("channel")
        if channel_mention:
            embed.add_field(
                name="Channel",
                value=channel_mention,
                inline=True
            )
        
        # Field 3: Raw Response (truncated)
        raw_response = data.get("raw_response", "")
        if raw_response:
            max_length = 500
            if len(raw_response) > max_length:
                raw_response = raw_response[:max_length] + "..."
            
            embed.add_field(
                name="Raw Response",
                value=f"```\n{raw_response}\n```",
                inline=False
            )
        
        # Sleep mode fields (only if sleep mode is enabled and pure ignore)
        sleep_mode_enabled = data.get("sleep_mode_enabled", False)
        if sleep_mode_enabled and is_pure:
            # Field 4: Sleep Mode Status
            sleep_mode_active = data.get("sleep_mode_active", False)
            status = "Active" if sleep_mode_active else "Inactive"
            embed.add_field(
                name="Sleep Mode Status",
                value=status,
                inline=True
            )
            
            # Field 5: Consecutive Ignores
            consecutive = data.get("consecutive_ignores", 0)
            threshold = data.get("ignore_threshold", 3)
            embed.add_field(
                name="Consecutive Ignores",
                value=f"{consecutive} / {threshold}",
                inline=True
            )
            
            # Field 6: Sleep Mode Triggered (if just entered)
            just_entered_sleep = data.get("just_entered_sleep", False)
            if just_entered_sleep:
                embed.add_field(
                    name="Sleep Mode Triggered",
                    value=f"✅ AI entered sleep mode after {consecutive} consecutive ignores",
                    inline=False
                )
        
        # Impure ignore guidance
        if not is_pure:
            embed.add_field(
                name="Reason",
                value="<IGNORE> tag found with additional content",
                inline=False
            )
            embed.add_field(
                name="Suggestion",
                value="Use ONLY <IGNORE> without additional text to properly skip responding",
                inline=False
            )
        
        # Set character card thumbnail
        try:
            session = data.get("session")
            if session:
                from utils.media.thumbnails import get_thumbnail_url
                thumbnail_url = await get_thumbnail_url(
                    channel,
                    session,
                    server_id=server_id
                )
                if thumbnail_url:
                    embed.set_thumbnail(url=thumbnail_url)
        except Exception as e:
            log.debug(f"Could not set thumbnail: {e}")
        
        # Set footer
        embed.set_footer(text=cls._build_footer(server_id))
        
        return embed
