"""
Tool Calling System - Tool Definitions

This module defines all available tools for LLM function calling.
Each tool follows OpenAI's function calling schema format.
"""

# Tool definitions for LLM function calling
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_message_info",
            "description": "Get detailed information about messages in the conversation. Use this when the user asks about specific messages, wants to see message content, or needs information about past messages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["by_short_id", "by_discord_id", "recent", "range"],
                        "description": "How to query messages: 'by_short_id' for #N format, 'by_discord_id' for full Discord ID, 'recent' for last N messages, 'range' for a range of messages"
                    },
                    "short_id": {
                        "type": "integer",
                        "description": "Short ID of the message (1-999) when query_type is 'by_short_id'"
                    },
                    "discord_id": {
                        "type": "string",
                        "description": "Full Discord message ID when query_type is 'by_discord_id'"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of recent messages to retrieve when query_type is 'recent'"
                    },
                    "start_index": {
                        "type": "integer",
                        "description": "Start index for range query (0-based, negative for from end)"
                    },
                    "end_index": {
                        "type": "integer",
                        "description": "End index for range query"
                    },
                    "include_fields": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["content", "author", "timestamp", "reply_info", "ids", "all"]
                        },
                        "description": "Which fields to include in the response. Use 'all' for complete information."
                    }
                },
                "required": ["query_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_emoji_info",
            "description": "Get information about emojis and stickers available in the server. Use this when the user asks about emojis, stickers, figurinhas, wants to search for specific emojis/stickers, or needs to know what emojis/stickers are available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["list_server_emojis", "list_server_stickers", "list_recent_emojis", "search_emoji", "search_sticker"],
                        "description": "Type of query: 'list_server_emojis' for all server emojis, 'list_server_stickers' for all server stickers/figurinhas, 'list_recent_emojis' for recently created emojis, 'search_emoji' to search emoji by name, 'search_sticker' to search sticker by name"
                    },
                    "search_term": {
                        "type": "string",
                        "description": "Search term for emoji/sticker name when query_type is 'search_emoji' or 'search_sticker'"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)"
                    }
                },
                "required": ["query_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_info",
            "description": "Get information about Discord users. When user mentions someone (<@ID>) or asks about SPECIFIC user details (roles, join date, permissions), you MUST use 'by_id' with user_identifier=ID and include_fields=['all']. The 'list_all' query returns ONLY basic info (username, display_name, ID) - it does NOT include roles, join dates, or other details. Examples: User asks 'Who is <@123>?' or 'What roles does John have?' → use 'by_id' or 'search_any' then 'by_id', with include_fields=['all'].",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_identifier": {
                        "type": "string",
                        "description": "User ID, @mention, username, or search term. Not required for 'list_all' query type."
                    },
                    "query_type": {
                        "type": "string",
                        "enum": ["by_id", "by_exact_name", "search_username", "search_display_name", "search_any", "list_all"],
                        "description": "Query type: 'by_id' (for mentions <@ID> or detailed user info), 'by_exact_name' (exact username), 'search_username' (partial username), 'search_display_name' (partial display name), 'search_any' (search all fields), 'list_all' (list all members - basic info only)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10 for searches, 50 for list_all; max: 50 for searches, 100 for list_all)"
                    },
                    "include_bots": {
                        "type": "boolean",
                        "description": "Include bot users in list_all results (default: true). Only applies to 'list_all' query type."
                    },
                    "include_fields": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["profile", "roles", "activity", "join_date", "all"]
                        },
                        "description": "Fields to include. Use ['all'] for complete info including roles and join date. Use ['roles'] for just roles. Not used for 'list_all'."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_channel_info",
            "description": "Get information about Discord channels in the server. Use this when the user asks about channels, wants to see channel details, permissions, or list available channels.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["current_channel", "by_id", "by_name", "list_all", "list_threads"],
                        "description": "Type of channel query: 'current_channel' for current channel info, 'by_id' to get channel by ID, 'by_name' to search by name, 'list_all' to list all channels, 'list_threads' to list threads in current channel"
                    },
                    "channel_identifier": {
                        "type": "string",
                        "description": "Channel ID or name (required for 'by_id' and 'by_name' query types)"
                    },
                    "include_fields": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["basic", "permissions", "settings", "threads", "all"]
                        },
                        "description": "Which fields to include in the response. Use 'all' for complete information."
                    }
                },
                "required": ["query_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_server_info",
            "description": "Get information about the Discord server (guild). Use this when the user asks about server statistics, features, roles, boost status, or general server information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_type": {
                        "type": "string",
                        "enum": ["basic_info", "statistics", "features", "roles", "boost_status"],
                        "description": "Type of server query: 'basic_info' for server profile, 'statistics' for member/channel counts, 'features' for server features and boost level, 'roles' to list all roles, 'boost_status' for boost information"
                    },
                    "include_fields": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["profile", "stats", "features", "roles", "all"]
                        },
                        "description": "Which fields to include in the response. Use 'all' for complete information."
                    }
                },
                "required": ["query_type"]
            }
        }
    }
]


def get_tool_definitions(allowed_tools=None):
    """
    Get tool definitions, optionally filtered by allowed tools.
    
    Args:
        allowed_tools: List of tool names to include, or None for all tools
        
    Returns:
        List of tool definitions
    """
    if allowed_tools is None or "all" in allowed_tools:
        return TOOL_DEFINITIONS
    
    return [
        tool for tool in TOOL_DEFINITIONS
        if tool["function"]["name"] in allowed_tools
    ]


def get_tool_names():
    """Get list of all available tool names."""
    return [tool["function"]["name"] for tool in TOOL_DEFINITIONS]
