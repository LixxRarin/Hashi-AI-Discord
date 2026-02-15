"""
Message Tools - Tools for querying message information

This module provides tools for the LLM to query information about
messages in the conversation history.
"""

import logging
from typing import Dict, Any, List, Optional

log = logging.getLogger(__name__)


async def get_message_info(
    query_type: str,
    short_id: Optional[int] = None,
    discord_id: Optional[str] = None,
    count: Optional[int] = None,
    start_index: Optional[int] = None,
    end_index: Optional[int] = None,
    include_fields: List[str] = None,
    context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Get detailed message information from conversation history.
    
    Args:
        query_type: Type of query ("by_short_id", "by_discord_id", "recent", "range")
        short_id: Short ID to query (for "by_short_id")
        discord_id: Discord ID to query (for "by_discord_id")
        count: Number of recent messages (for "recent")
        start_index: Start index (for "range")
        end_index: End index (for "range")
        include_fields: Fields to include in response
        context: Context information (server_id, channel_id, ai_name, etc.)
        
    Returns:
        Dict with message information
    """
    if context is None:
        return {"error": "No context provided"}
    
    if include_fields is None:
        include_fields = ["all"]
    
    server_id = context.get("server_id")
    channel_id = context.get("channel_id")
    ai_name = context.get("ai_name")
    chat_id = context.get("chat_id", "default")
    
    if not all([server_id, channel_id, ai_name]):
        return {"error": "Missing required context (server_id, channel_id, ai_name)"}
    
    try:
        # Get store and short ID manager
        from messaging.store import get_store
        from messaging.short_id_manager import get_short_id_manager

        store = get_store()
        short_id_manager = get_short_id_manager()
        
        # Get chat from store
        chat = store._data.get(server_id, {}).get(channel_id, {}).get(ai_name, {}).get("chats", {}).get(chat_id)
        
        if not chat:
            return {
                "error": f"No conversation history found for AI {ai_name}",
                "messages": []
            }
        
        messages = chat.messages if hasattr(chat, 'messages') else []
        
        # Process query based on type
        if query_type == "by_short_id":
            if short_id is None:
                return {"error": "short_id is required for query_type 'by_short_id'"}
            
            # Find message by short_id
            found_messages = [msg for msg in messages if msg.short_id == short_id]
            
            if not found_messages:
                return {
                    "error": f"Message with short ID #{short_id} not found",
                    "messages": []
                }
            
            result_messages = found_messages
        
        elif query_type == "by_discord_id":
            if discord_id is None:
                return {"error": "discord_id is required for query_type 'by_discord_id'"}
            
            # Find message by discord_id
            found_messages = []
            for msg in messages:
                if msg.discord_id == discord_id:
                    found_messages.append(msg)
                elif msg.discord_ids and discord_id in msg.discord_ids:
                    found_messages.append(msg)
            
            if not found_messages:
                return {
                    "error": f"Message with Discord ID {discord_id} not found",
                    "messages": []
                }
            
            result_messages = found_messages
        
        elif query_type == "recent":
            if count is None:
                count = 5  # Default to 5 recent messages
            
            # Get last N messages
            result_messages = messages[-count:] if len(messages) >= count else messages
        
        elif query_type == "range":
            if start_index is None or end_index is None:
                return {"error": "start_index and end_index are required for query_type 'range'"}
            
            # Handle negative indices
            if start_index < 0:
                start_index = len(messages) + start_index
            if end_index < 0:
                end_index = len(messages) + end_index
            
            # Clamp to valid range
            start_index = max(0, min(start_index, len(messages)))
            end_index = max(0, min(end_index, len(messages)))
            
            result_messages = messages[start_index:end_index]
        
        else:
            return {"error": f"Unknown query_type: {query_type}"}
        
        # Format messages based on include_fields
        formatted_messages = []
        for msg in result_messages:
            formatted_msg = {}
            
            if "all" in include_fields or "ids" in include_fields:
                if msg.short_id is not None:
                    formatted_msg["short_id"] = msg.short_id
                if msg.discord_id:
                    formatted_msg["discord_id"] = msg.discord_id
                if msg.discord_ids:
                    formatted_msg["discord_ids"] = msg.discord_ids
            
            if "all" in include_fields or "content" in include_fields:
                formatted_msg["content"] = msg.content
            
            if "all" in include_fields or "author" in include_fields:
                if msg.role == "user":
                    formatted_msg["author"] = {
                        "type": "user",
                        "username": msg.author_username,
                        "display_name": msg.author_display_name,
                        "id": msg.author_id
                    }
                else:
                    formatted_msg["author"] = {
                        "type": "bot",
                        "name": ai_name
                    }
            
            if "all" in include_fields or "timestamp" in include_fields:
                from datetime import datetime
                formatted_msg["timestamp"] = datetime.fromtimestamp(msg.timestamp).isoformat() + "Z"
            
            if "all" in include_fields or "reply_info" in include_fields:
                # Extract reply information from message
                if msg.reply_to_id:
                    formatted_msg["reply_info"] = {
                        "reply_to_discord_id": msg.reply_to_id,
                        "reply_to_short_id": msg.reply_to_short_id,
                        "reply_to_content": msg.reply_to_content,
                        "reply_to_author": msg.reply_to_author,
                        "reply_to_is_bot": msg.reply_to_is_bot
                    }
                else:
                    formatted_msg["reply_info"] = None
            
            formatted_messages.append(formatted_msg)
        
        return {
            "messages": formatted_messages,
            "total_count": len(result_messages)
        }
    
    except Exception as e:
        log.error(f"Error in get_message_info: {e}", exc_info=True)
        return {
            "error": f"Failed to retrieve message information: {str(e)}",
            "messages": []
        }
