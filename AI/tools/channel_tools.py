"""
Channel Tools - Tools for querying channel information

This module provides tools for the LLM to query information about
Discord channels in the server.
"""

import logging
from typing import Dict, Any, List, Optional
import discord

log = logging.getLogger(__name__)


async def get_channel_info(
    query_type: str,
    channel_identifier: Optional[str] = None,
    include_fields: List[str] = None,
    context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Get information about Discord channels.
    
    Args:
        query_type: Type of query ("current_channel", "by_id", "by_name", "list_all", "list_threads")
        channel_identifier: Channel ID or name (for by_id, by_name)
        include_fields: Fields to include in response
        context: Context information (guild, channel_id, etc.)
        
    Returns:
        Dict with channel information
    """
    if context is None:
        return {"error": "No context provided"}
    
    if include_fields is None:
        include_fields = ["all"]
    
    guild = context.get("guild")
    bot_client = context.get("bot_client")
    current_channel_id = context.get("channel_id")
    
    # Validate guild object
    if not guild or not hasattr(guild, 'channels'):
        if bot_client:
            try:
                server_id = context.get("server_id")
                guild = bot_client.get_guild(int(server_id))
                if guild:
                    log.debug(f"Retrieved real guild from bot_client for server {server_id}")
            except Exception as e:
                log.error(f"Failed to get guild from bot_client: {e}")
        
        if not guild or not hasattr(guild, 'channels'):
            return {
                "error": "Guild information not available in current context.",
                "channel": None
            }
    
    try:
        # Process query based on type
        if query_type == "current_channel":
            # Get current channel info
            channel = guild.get_channel(int(current_channel_id))
            
            if not channel:
                return {
                    "error": f"Current channel not found",
                    "channel": None
                }
            
            return {
                "channel": _format_channel(channel, include_fields),
                "found": True
            }
        
        elif query_type == "by_id":
            if channel_identifier is None:
                return {"error": "channel_identifier is required for query_type 'by_id'"}
            
            try:
                channel_id = int(channel_identifier)
                channel = guild.get_channel(channel_id)
                
                if not channel:
                    return {
                        "error": f"Channel with ID {channel_identifier} not found",
                        "channel": None
                    }
                
                return {
                    "channel": _format_channel(channel, include_fields),
                    "found": True
                }
            except ValueError:
                return {
                    "error": f"Invalid channel ID: {channel_identifier}",
                    "channel": None
                }
        
        elif query_type == "by_name":
            if channel_identifier is None:
                return {"error": "channel_identifier is required for query_type 'by_name'"}
            
            # Search by name (case-insensitive)
            search_name = channel_identifier.lower().strip('#')
            matching_channels = []
            
            for channel in guild.channels:
                if isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.ForumChannel)):
                    if channel.name.lower() == search_name:
                        matching_channels.append(channel)
            
            if not matching_channels:
                return {
                    "error": f"Channel '{channel_identifier}' not found",
                    "channel": None
                }
            
            # Return first match
            return {
                "channel": _format_channel(matching_channels[0], include_fields),
                "found": True,
                "total_matches": len(matching_channels)
            }
        
        elif query_type == "list_all":
            # List all channels
            channels_by_type = {
                "text": [],
                "voice": [],
                "forum": [],
                "category": [],
                "stage": []
            }
            
            for channel in guild.channels:
                if isinstance(channel, discord.TextChannel):
                    channels_by_type["text"].append(_format_channel_basic(channel))
                elif isinstance(channel, discord.VoiceChannel):
                    channels_by_type["voice"].append(_format_channel_basic(channel))
                elif isinstance(channel, discord.ForumChannel):
                    channels_by_type["forum"].append(_format_channel_basic(channel))
                elif isinstance(channel, discord.CategoryChannel):
                    channels_by_type["category"].append(_format_channel_basic(channel))
                elif isinstance(channel, discord.StageChannel):
                    channels_by_type["stage"].append(_format_channel_basic(channel))
            
            return {
                "channels": channels_by_type,
                "total_count": len(guild.channels)
            }
        
        elif query_type == "list_threads":
            # List threads in current channel
            channel = guild.get_channel(int(current_channel_id))
            
            if not channel:
                return {
                    "error": "Current channel not found",
                    "threads": []
                }
            
            if not isinstance(channel, discord.TextChannel):
                return {
                    "error": "Threads are only available in text channels",
                    "threads": []
                }
            
            threads = []
            
            # Active threads
            for thread in channel.threads:
                threads.append({
                    "id": str(thread.id),
                    "name": thread.name,
                    "archived": False,
                    "locked": thread.locked if hasattr(thread, 'locked') else False,
                    "message_count": thread.message_count if hasattr(thread, 'message_count') else None,
                    "member_count": thread.member_count if hasattr(thread, 'member_count') else None
                })
            
            return {
                "threads": threads,
                "channel_name": channel.name,
                "total_count": len(threads)
            }
        
        else:
            return {"error": f"Unknown query_type: {query_type}"}
    
    except Exception as e:
        log.error(f"Error in get_channel_info: {e}", exc_info=True)
        return {
            "error": f"Failed to retrieve channel information: {str(e)}",
            "channel": None
        }


def _format_channel(channel, include_fields: List[str]) -> Dict[str, Any]:
    """Format channel information based on include_fields."""
    channel_info = {}
    
    if "all" in include_fields or "basic" in include_fields:
        channel_info["id"] = str(channel.id)
        channel_info["name"] = channel.name
        channel_info["type"] = str(channel.type)
        
        if isinstance(channel, discord.TextChannel):
            channel_info["topic"] = channel.topic
            channel_info["nsfw"] = channel.nsfw
        
        channel_info["position"] = channel.position
        channel_info["created_at"] = channel.created_at.isoformat() + "Z"
    
    if "all" in include_fields or "permissions" in include_fields:
        # Get bot's permissions in this channel
        if hasattr(channel, 'permissions_for'):
            bot_member = channel.guild.me
            permissions = channel.permissions_for(bot_member)
            
            channel_info["bot_permissions"] = {
                "read_messages": permissions.read_messages,
                "send_messages": permissions.send_messages,
                "embed_links": permissions.embed_links,
                "attach_files": permissions.attach_files,
                "read_message_history": permissions.read_message_history,
                "add_reactions": permissions.add_reactions,
                "manage_messages": permissions.manage_messages,
                "manage_threads": permissions.manage_threads if hasattr(permissions, 'manage_threads') else False
            }
    
    if "all" in include_fields or "settings" in include_fields:
        if isinstance(channel, discord.TextChannel):
            channel_info["slowmode_delay"] = channel.slowmode_delay
            channel_info["default_auto_archive_duration"] = channel.default_auto_archive_duration
        
        if hasattr(channel, 'category'):
            channel_info["category"] = channel.category.name if channel.category else None
    
    if "all" in include_fields or "threads" in include_fields:
        if isinstance(channel, discord.TextChannel):
            active_threads = []
            for thread in channel.threads:
                active_threads.append({
                    "id": str(thread.id),
                    "name": thread.name,
                    "archived": False
                })
            channel_info["active_threads"] = active_threads
            channel_info["active_thread_count"] = len(active_threads)
    
    return channel_info


def _format_channel_basic(channel) -> Dict[str, Any]:
    """Format basic channel information for list view."""
    return {
        "id": str(channel.id),
        "name": channel.name,
        "type": str(channel.type),
        "position": channel.position
    }
