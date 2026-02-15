"""
Emoji Tools - Tools for querying emoji and sticker information

This module provides tools for the LLM to query information about
emojis and stickers available in the Discord server.
"""

import logging
from typing import Dict, Any, List, Optional

log = logging.getLogger(__name__)


async def get_emoji_info(
    query_type: str,
    search_term: Optional[str] = None,
    limit: int = 10,
    context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Get information about emojis and stickers in the server.
    
    Args:
        query_type: Type of query ("list_server_emojis", "list_server_stickers",
                    "list_recent_emojis", "search_emoji", "search_sticker")
        search_term: Search term for emoji/sticker name (for "search_emoji" or "search_sticker")
        limit: Maximum number of results to return
        context: Context information (guild, etc.)
        
    Returns:
        Dict with emoji/sticker information
    """
    if context is None:
        return {"error": "No context provided"}
    
    guild = context.get("guild")
    
    # Check if guild has the necessary attributes
    if not guild or not hasattr(guild, 'emojis'):
        return {
            "error": "Guild emoji information not available in current context. This feature requires the bot to have access to guild emoji data.",
            "emojis": []
        }
    
    try:
        if query_type == "list_server_emojis":
            # List all server emojis
            emojis = []
            for emoji in guild.emojis[:limit]:
                emojis.append({
                    "name": emoji.name,
                    "id": str(emoji.id),
                    "animated": emoji.animated,
                    "url": str(emoji.url),
                    "available": emoji.available,
                    "managed": emoji.managed,
                    "require_colons": emoji.require_colons
                })
            
            # Include sticker count
            sticker_count = len(guild.stickers) if hasattr(guild, 'stickers') else 0
            
            return {
                "emojis": emojis,
                "total_count": len(guild.emojis),
                "sticker_count": sticker_count,
                "showing": len(emojis)
            }
        
        elif query_type == "list_server_stickers":
            # List all server stickers
            if not hasattr(guild, 'stickers'):
                return {
                    "error": "Stickers not available in this guild",
                    "stickers": []
                }
            
            stickers = []
            for sticker in guild.stickers[:limit]:
                stickers.append({
                    "name": sticker.name,
                    "id": str(sticker.id),
                    "description": sticker.description or "",
                    "url": sticker.url,
                    "format": str(sticker.format)
                })
            
            return {
                "stickers": stickers,
                "total_count": len(guild.stickers),
                "showing": len(stickers)
            }
        
        elif query_type == "search_emoji":
            if search_term is None:
                return {"error": "search_term is required for query_type 'search_emoji'"}
            
            # Search emojis by name
            search_lower = search_term.lower()
            matching_emojis = []
            
            for emoji in guild.emojis:
                if search_lower in emoji.name.lower():
                    matching_emojis.append({
                        "name": emoji.name,
                        "id": str(emoji.id),
                        "animated": emoji.animated,
                        "url": str(emoji.url),
                        "available": emoji.available
                    })
                    
                    if len(matching_emojis) >= limit:
                        break
            
            return {
                "emojis": matching_emojis,
                "search_term": search_term,
                "found_count": len(matching_emojis)
            }
        
        elif query_type == "search_sticker":
            if search_term is None:
                return {"error": "search_term is required for query_type 'search_sticker'"}
            
            if not hasattr(guild, 'stickers'):
                return {
                    "error": "Stickers not available in this guild",
                    "stickers": []
                }
            
            # Search stickers by name
            search_lower = search_term.lower()
            matching_stickers = []
            
            for sticker in guild.stickers:
                if search_lower in sticker.name.lower():
                    matching_stickers.append({
                        "name": sticker.name,
                        "id": str(sticker.id),
                        "description": sticker.description or "",
                        "url": sticker.url,
                        "format": str(sticker.format)
                    })
                    
                    if len(matching_stickers) >= limit:
                        break
            
            return {
                "stickers": matching_stickers,
                "search_term": search_term,
                "found_count": len(matching_stickers)
            }
        
        elif query_type == "list_recent_emojis":
            # List recently created emojis (sorted by creation time)
            sorted_emojis = sorted(
                guild.emojis,
                key=lambda e: e.created_at,
                reverse=True
            )[:limit]
            
            emojis = []
            for emoji in sorted_emojis:
                emojis.append({
                    "name": emoji.name,
                    "id": str(emoji.id),
                    "animated": emoji.animated,
                    "url": str(emoji.url),
                    "created_at": emoji.created_at.isoformat() + "Z"
                })
            
            return {
                "emojis": emojis,
                "showing": len(emojis)
            }
        
        else:
            return {"error": f"Unknown query_type: {query_type}"}
    
    except Exception as e:
        log.error(f"Error in get_emoji_info: {e}", exc_info=True)
        return {
            "error": f"Failed to retrieve emoji information: {str(e)}",
            "emojis": []
        }
