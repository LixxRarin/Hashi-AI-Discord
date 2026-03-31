"""
Discord Tools - Unified Discord Query Handler

This module provides a unified interface for querying Discord information.
It routes requests to the appropriate specialized tool based on resource type.

Supported resources:
- message: Query message information (#N or Discord IDs)
- user: Query user information (@mentions, names, IDs)
- channel: Query channel information
- server: Query server/guild information
- emoji: Query emojis and stickers
- poll: Query poll information and results
"""

import logging
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)


async def discord_query(
    resource: str,
    action: str,
    query: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Unified Discord query handler.
    
    Routes requests to appropriate specialized tools based on resource type.
    
    Args:
        resource: Type of Discord resource ("message", "user", "channel", "server", "emoji", "poll")
        action: Action to perform ("get", "search", "list")
        query: Query parameters (flexible based on resource type)
        context: Context information (server_id, channel_id, guild, etc.)
        
    Returns:
        Dict with query results or error
    """
    if query is None:
        query = {}
    
    if context is None:
        return {"error": "No context provided"}
    
    log.info(f"Discord query: resource={resource}, action={action}")
    log.debug(f"Query parameters: {query}")
    
    try:
        # Route to appropriate handler
        if resource == "message":
            return await _handle_message_query(action, query, context)
        elif resource == "user":
            return await _handle_user_query(action, query, context)
        elif resource == "channel":
            return await _handle_channel_query(action, query, context)
        elif resource == "server":
            return await _handle_server_query(action, query, context)
        elif resource == "emoji":
            return await _handle_emoji_query(action, query, context)
        elif resource == "poll":
            return await _handle_poll_query(action, query, context)
        else:
            return {
                "error": f"Unknown resource type: {resource}",
                "valid_resources": ["message", "user", "channel", "server", "emoji", "poll"]
            }
    
    except Exception as e:
        log.error(f"Error in discord_query (resource={resource}, action={action}): {e}", exc_info=True)
        return {
            "error": f"Failed to execute discord_query: {str(e)}",
            "resource": resource,
            "action": action
        }


async def _handle_message_query(action: str, query: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Handle message resource queries."""
    from AI.tools.message_tools import get_message_info
    
    if action == "get":
        # Get specific message by ID
        if "short_id" in query:
            return await get_message_info(
                query_type="by_short_id",
                short_id=query["short_id"],
                include_fields=query.get("include_fields", ["all"]),
                context=context
            )
        elif "discord_id" in query or "id" in query:
            discord_id = query.get("discord_id") or query.get("id")
            return await get_message_info(
                query_type="by_discord_id",
                discord_id=discord_id,
                include_fields=query.get("include_fields", ["all"]),
                context=context
            )
        else:
            return {"error": "For action 'get', provide either 'short_id' or 'id'/'discord_id'"}
    
    elif action == "list":
        # List recent messages
        count = query.get("count", 5)
        return await get_message_info(
            query_type="recent",
            count=count,
            include_fields=query.get("include_fields", ["all"]),
            context=context
        )
    
    elif action == "search":
        # Range query
        if "start_index" in query and "end_index" in query:
            return await get_message_info(
                query_type="range",
                start_index=query["start_index"],
                end_index=query["end_index"],
                include_fields=query.get("include_fields", ["all"]),
                context=context
            )
        else:
            return {"error": "For action 'search' on messages, provide 'start_index' and 'end_index'"}
    
    else:
        return {
            "error": f"Unknown action '{action}' for resource 'message'",
            "valid_actions": ["get", "list", "search"]
        }


async def _handle_user_query(action: str, query: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Handle user resource queries."""
    from AI.tools.user_tools import get_user_info
    
    if action == "get":
        # Get specific user by ID
        user_id = query.get("id") or query.get("user_id")
        if not user_id:
            return {"error": "For action 'get', provide 'id' or 'user_id'"}
        
        return await get_user_info(
            user_identifier=user_id,
            query_type="by_id",
            include_fields=query.get("include_fields", ["all"]),
            context=context
        )
    
    elif action == "search":
        # Search users by name
        name = query.get("name") or query.get("search_term")
        if not name:
            return {"error": "For action 'search', provide 'name' or 'search_term'"}
        
        query_type = query.get("query_type", "search_any")
        return await get_user_info(
            user_identifier=name,
            query_type=query_type,
            limit=query.get("limit", 10),
            include_fields=query.get("include_fields", ["all"]),
            context=context
        )
    
    elif action == "list":
        # List all users
        return await get_user_info(
            query_type="list_all",
            limit=query.get("limit", 50),
            include_bots=query.get("include_bots", True),
            context=context
        )
    
    else:
        return {
            "error": f"Unknown action '{action}' for resource 'user'",
            "valid_actions": ["get", "search", "list"]
        }


async def _handle_channel_query(action: str, query: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Handle channel resource queries."""
    from AI.tools.channel_tools import get_channel_info
    
    if action == "get":
        # Get specific channel (current or by ID)
        if "id" in query or "channel_id" in query:
            channel_id = query.get("id") or query.get("channel_id")
            return await get_channel_info(
                query_type="by_id",
                channel_identifier=channel_id,
                include_fields=query.get("include_fields", ["all"]),
                context=context
            )
        else:
            # Default to current channel
            return await get_channel_info(
                query_type="current_channel",
                include_fields=query.get("include_fields", ["all"]),
                context=context
            )
    
    elif action == "search":
        # Search channel by name
        name = query.get("name") or query.get("search_term")
        if not name:
            return {"error": "For action 'search', provide 'name' or 'search_term'"}
        
        return await get_channel_info(
            query_type="by_name",
            channel_identifier=name,
            include_fields=query.get("include_fields", ["all"]),
            context=context
        )
    
    elif action == "list":
        # List all channels or threads
        query_type = query.get("query_type", "list_all")
        if query_type == "list_threads":
            return await get_channel_info(
                query_type="list_threads",
                context=context
            )
        else:
            return await get_channel_info(
                query_type="list_all",
                context=context
            )
    
    else:
        return {
            "error": f"Unknown action '{action}' for resource 'channel'",
            "valid_actions": ["get", "search", "list"]
        }


async def _handle_server_query(action: str, query: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Handle server resource queries."""
    from AI.tools.server_tools import get_server_info
    
    if action == "get":
        # Get server information
        query_type = query.get("query_type", "basic_info")
        return await get_server_info(
            query_type=query_type,
            include_fields=query.get("include_fields", ["all"]),
            context=context
        )
    
    elif action == "list":
        # List server resources (roles, features, etc.)
        query_type = query.get("query_type", "roles")
        return await get_server_info(
            query_type=query_type,
            include_fields=query.get("include_fields", ["all"]),
            context=context
        )
    
    elif action == "search":
        return {"error": "Action 'search' is not supported for resource 'server'"}
    
    else:
        return {
            "error": f"Unknown action '{action}' for resource 'server'",
            "valid_actions": ["get", "list"]
        }


async def _handle_emoji_query(action: str, query: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Handle emoji resource queries."""
    from AI.tools.emoji_tools import get_emoji_info
    
    if action == "search":
        # Search emoji or sticker
        search_term = query.get("search_term") or query.get("name")
        if not search_term:
            return {"error": "For action 'search', provide 'search_term' or 'name'"}
        
        query_type = query.get("query_type", "search_emoji")
        return await get_emoji_info(
            query_type=query_type,
            search_term=search_term,
            limit=query.get("limit", 10),
            context=context
        )
    
    elif action == "list":
        # List emojis or stickers
        query_type = query.get("query_type", "list_server_emojis")
        return await get_emoji_info(
            query_type=query_type,
            limit=query.get("limit", 10),
            context=context
        )
    
    elif action == "get":
        return {"error": "Action 'get' is not supported for resource 'emoji'. Use 'search' or 'list' instead."}
    
    else:
        return {
            "error": f"Unknown action '{action}' for resource 'emoji'",
            "valid_actions": ["search", "list"]
        }


async def _handle_poll_query(action: str, query: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Handle poll resource queries."""
    from AI.tools.poll_tools import get_poll_info
    
    if action == "get":
        # Get poll information
        message_id = query.get("id") or query.get("message_id")
        if not message_id:
            return {"error": "For action 'get', provide 'id' or 'message_id'"}
        
        return await get_poll_info(
            message_id=message_id,
            context=context
        )
    
    elif action in ["search", "list"]:
        return {"error": f"Action '{action}' is not supported for resource 'poll'. Use 'get' with a message ID."}
    
    else:
        return {
            "error": f"Unknown action '{action}' for resource 'poll'",
            "valid_actions": ["get"]
        }
