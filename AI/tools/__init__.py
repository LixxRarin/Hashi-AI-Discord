"""
Tool Calling System - Tool Definitions

This module defines all available tools for LLM function calling.
Each tool follows OpenAI's function calling schema format.

Unified Tools (2):
- discord_query: Query Discord information (messages, users, channels, server, emojis, polls)
- memory: Manage persistent memory (list, add, update, remove, search)
"""

# Tool definitions for LLM function calling
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "discord_query",
            "description": "Query Discord information: messages (#N or IDs), users (@mentions or names), channels, server stats, emojis/stickers, and polls. Always use this to get accurate Discord data - never guess. Examples: discord_query(resource='message', action='get', query={'short_id': 5}), discord_query(resource='user', action='search', query={'name': 'john'}), discord_query(resource='emoji', action='list', query={'limit': 10})",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource": {
                        "type": "string",
                        "enum": ["message", "user", "channel", "server", "emoji", "poll"],
                        "description": "Type of Discord resource to query: 'message' (for #N or message IDs), 'user' (for @mentions or usernames), 'channel' (for channel info), 'server' (for guild/server info), 'emoji' (for emojis/stickers), 'poll' (for poll results)"
                    },
                    "action": {
                        "type": "string",
                        "enum": ["get", "search", "list"],
                        "description": "Action to perform: 'get' (retrieve specific item by ID), 'search' (find items matching criteria), 'list' (show all or recent items)"
                    },
                    "query": {
                        "type": "object",
                        "description": "Query parameters (flexible based on resource and action). Common parameters: 'id' or 'short_id' (for get), 'name' or 'search_term' (for search), 'limit' (for list), 'include_fields' (fields to include)",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Discord ID or short ID (#N format)"
                            },
                            "short_id": {
                                "type": "integer",
                                "description": "Short message ID (e.g., 5 for #5)"
                            },
                            "discord_id": {
                                "type": "string",
                                "description": "Full Discord ID (18-19 digits)"
                            },
                            "name": {
                                "type": "string",
                                "description": "Name to search for (username, channel name, etc.)"
                            },
                            "query_type": {
                                "type": "string",
                                "description": "Specific query type for the resource (e.g., 'search_any', 'by_id', 'basic_info', 'statistics', 'roles', 'list_server_emojis', 'search_emoji')"
                            },
                            "search_term": {
                                "type": "string",
                                "description": "Search term for emojis/stickers"
                            },
                            "count": {
                                "type": "integer",
                                "description": "Number of items to retrieve (for messages)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum results to return (default: 10)"
                            },
                            "include_fields": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Fields to include in response: ['all'] for everything, ['basic'] for minimal, ['profile', 'roles', 'activity'] for specific fields"
                            },
                            "include_bots": {
                                "type": "boolean",
                                "description": "Include bot users in results (default: true)"
                            },
                            "start_index": {
                                "type": "integer",
                                "description": "Start index for range queries (0-based, negative for from end)"
                            },
                            "end_index": {
                                "type": "integer",
                                "description": "End index for range queries"
                            }
                        }
                    }
                },
                "required": ["resource", "action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory",
            "description": "Manage persistent memory across conversations. Use to remember user preferences, facts, and important information. Always check memories before answering questions about past conversations. Examples: memory(action='list'), memory(action='add', content='User prefers dark mode'), memory(action='search', query='dark mode'), memory(action='update', memory_id=3, content='Updated info'), memory(action='remove', memory_id=3)",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "add", "update", "remove", "search"],
                        "description": "Memory operation: 'list' (show all memories), 'add' (save new memory), 'update' (modify existing memory), 'remove' (delete memory), 'search' (find memories by keyword)"
                    },
                    "content": {
                        "type": "string",
                        "description": "Memory content to save or update (required for 'add' and 'update' actions). Be concise but clear."
                    },
                    "memory_id": {
                        "type": "integer",
                        "description": "ID of the memory to update or remove (required for 'update' and 'remove' actions). Get this from list_memories or search_memories."
                    },
                    "query": {
                        "type": "string",
                        "description": "Search term or keyword to look for in memories (required for 'search' action)"
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bash_tool",
            "description": "Execute bash commands in an isolated Docker container. Supports persistent containers (maintains state between commands) and ephemeral mode (one-time execution). Use this to run scripts, install packages, process data, compile code, or perform any bash operations. The container has network access and can install packages via apt-get. Examples: bash_tool(command='echo Hello'), bash_tool(command='apt-get update && apt-get install -y python3'), bash_tool(command='python3 script.py'), bash_tool(command='ls', reset=True)",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Bash command to execute. Can be a single command or multiple commands chained with && or ;. The command runs in /workspace directory by default."
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["persistent", "ephemeral"],
                        "description": "Execution mode: 'persistent' (default) maintains container state between commands, allowing you to install packages and create files that persist. 'ephemeral' creates a fresh container for each command."
                    },
                    "reset": {
                        "type": "boolean",
                        "description": "Reset the container before executing (persistent mode only). Use this to start with a clean environment. Default: false"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Command timeout in seconds. Default: 1800 (30 minutes). Use for long-running operations like large downloads or compilations."
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory for command execution. Default: /workspace"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "attachment_query",
            "description": "Access and read attachments from Discord messages or direct URLs. Supports text files (txt, md, json, xml, csv, yaml, py, js, html, css), images (jpg, png, gif, webp), PDFs (text extraction), DOCX (text extraction), and other files (metadata only). Use message ID to retrieve attachments from a message, or provide a direct URL to process files like stickers, attachment links, etc. Always use this when users ask to read, view, or analyze files. Examples: attachment_query(message_id='123456789'), attachment_query(url='https://cdn.discordapp.com/stickers/123.png'), attachment_query(message_id='5', filename='data.json'), attachment_query(message_id='10', attachment_index=0)",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "Discord message ID or short ID (#N format) containing the attachment. Examples: '123456789' or '#5'. Either message_id or url must be provided, but not both."
                    },
                    "url": {
                        "type": "string",
                        "description": "Direct URL to a file (e.g., sticker URL, attachment URL from Discord CDN). Use this to process files directly without needing a message ID. Examples: 'https://cdn.discordapp.com/stickers/123.png', 'https://cdn.discordapp.com/attachments/123/456/file.pdf'. Either message_id or url must be provided, but not both."
                    },
                    "attachment_index": {
                        "type": "integer",
                        "description": "Index of the attachment to retrieve (0-based). Only used with message_id. Use this when you know which attachment to get. If not specified, returns all attachments from the message."
                    },
                    "filename": {
                        "type": "string",
                        "description": "Filename to search for (alternative to attachment_index). Only used with message_id. Use this when you know the filename. Case-insensitive search."
                    },
                    "include_content": {
                        "type": "boolean",
                        "description": "Whether to include file content (default: true). Set to false to get only metadata (filename, size, type, URL) without downloading/processing the file."
                    }
                },
                "required": []
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
