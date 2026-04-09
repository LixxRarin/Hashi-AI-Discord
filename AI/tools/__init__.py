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
            "description": "Query and manage Discord information: messages (#N or IDs), users (@mentions or names), channels, server stats, emojis/stickers, and polls. Supports querying (get/search/list) and message management (edit/delete). Use 'include_image: true' in query to visually see user avatars or emoji images (requires vision). Always use this to get accurate Discord data - never guess. Examples: discord_query(resource='user', action='search', query={'name': 'João', 'include_image': true}), discord_query(resource='emoji', action='search', query={'search_term': 'happy', 'include_image': true, 'limit': 3}), discord_query(resource='message', action='get', query={'short_id': 5})",
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
                        "enum": ["get", "search", "list", "edit", "delete"],
                        "description": "Action to perform: 'get' (retrieve specific item by ID), 'search' (find items matching criteria), 'list' (show all or recent items), 'edit' (edit own message - messages only), 'delete' (delete message - messages only)"
                    },
                    "query": {
                        "type": "object",
                        "description": "Query parameters (flexible based on resource and action). Common parameters: 'id' or 'short_id' (for get), 'name' or 'search_term' (for search), 'limit' (for list), 'include_fields' (fields to include), 'include_image' (to visually see avatars/emojis), 'new_content' (for edit), 'reason' (for delete)",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Discord ID or short ID (#N format)"
                            },
                            "message_id": {
                                "type": "string",
                                "description": "Message ID for edit/delete actions. Can be short ID (#5) or full Discord ID"
                            },
                            "new_content": {
                                "type": "string",
                                "description": "New content for message (required for action='edit'). Special syntax will be automatically removed."
                            },
                            "reason": {
                                "type": "string",
                                "description": "Reason for deletion (optional for action='delete'). Used for logging/audit purposes."
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
                            },
                            "include_image": {
                                "type": "boolean",
                                "description": "Include visual image for you to 'see' (requires vision enabled). Works with resource='user' (fetches avatar image) or resource='emoji' (fetches emoji/sticker image). When true, downloads and processes the image so you can visually analyze it - perfect for questions like 'how does their avatar look?' or 'what does this emoji show?'. Works with any action (get/search/list). Default: false. Examples: discord_query(resource='user', action='search', query={'name': 'João', 'include_image': true}) to see João's avatar, discord_query(resource='emoji', action='search', query={'search_term': 'cat', 'include_image': true}) to see cat emojis visually."
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
            "name": "read_memory",
            "description": "Read your persistent memory file. Returns the complete memory content organized by topics (Users, Server Information, Preferences, etc.). Use this to check what information you have saved before editing or adding new content.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_memory",
            "description": "Edit your memory by replacing old text with new text. Works like find-and-replace. Use this to make surgical edits without rewriting the entire file. The old_string must match exactly (including whitespace). If you want to add new information to an existing section, use old_string to match that section and new_string to include the section with the new info added. Example: To add 'Likes pizza' to Rarin's section, use old_string='### Rarin (@lixxrarin)\\n- Creator, female' and new_string='### Rarin (@lixxrarin)\\n- Creator, female\\n- Likes pizza'",
            "parameters": {
                "type": "object",
                "properties": {
                    "old_string": {
                        "type": "string",
                        "description": "Text to find and replace. Must match exactly (including line breaks and spacing). If not found or found multiple times, the edit will fail with an error."
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Text to replace it with. Can be longer or shorter than old_string."
                    }
                },
                "required": ["old_string", "new_string"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_memory",
            "description": "Write/replace the entire memory file. Use this ONLY for initial creation or complete rewrites. For updates to existing content, use edit_memory instead (it's more efficient). Organize content by topics with ## headers for main sections and ### for subsections.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Complete memory content in Markdown format. Organize by topics with ## headers (Users, Server Information, Preferences) and ### for subsections (individual users). Use bullet points for facts. Do NOT include YAML frontmatter - that's handled automatically."
                    }
                },
                "required": ["content"]
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
    },
    {
        "type": "function",
        "function": {
            "name": "send_attachment",
            "description": "Send attachments to Discord from URLs or base64-encoded data. Use this to share images, files, or any content from external sources. Supports spoiler tags and replies. For files from the container, use container_file with action='send_to_discord' instead. Examples: send_attachment(file_source='url', url='https://example.com/image.png', content='Check this out!'), send_attachment(file_source='base64', base64_data='iVBORw0KGgo...', filename='chart.png', content='Generated chart'), send_attachment(file_source='url', url='https://example.com/meme.jpg', spoiler=True)",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_source": {
                        "type": "string",
                        "enum": ["url", "base64"],
                        "description": "Source of the file: 'url' (download from URL) or 'base64' (decode base64 data). For container files, use container_file tool instead."
                    },
                    "url": {
                        "type": "string",
                        "description": "URL to download file from (required if file_source='url'). Must be a direct link to the file. Discord CDN URLs, image hosting sites, etc."
                    },
                    "base64_data": {
                        "type": "string",
                        "description": "Base64-encoded file data (required if file_source='base64'). The raw base64 string without data URI prefix."
                    },
                    "filename": {
                        "type": "string",
                        "description": "Filename for the attachment. Required for base64 source. Optional for URL (will be extracted from URL if not provided)."
                    },
                    "content": {
                        "type": "string",
                        "description": "Optional text message to send with the attachment. Use this to provide context or description."
                    },
                    "reply_to": {
                        "type": "string",
                        "description": "Optional message ID to reply to. Can be short ID (#N) or full Discord ID."
                    },
                    "spoiler": {
                        "type": "boolean",
                        "description": "Mark attachment as spoiler (blurred until clicked). Default: false"
                    }
                },
                "required": ["file_source"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "container_file",
            "description": "Access and manipulate files in the bash container. Use this to list, read, write, and send files created in the container. Perfect for sharing generated content like charts, reports, processed data, etc. All paths must be within /workspace. Examples: container_file(action='list', path='/workspace', recursive=True), container_file(action='read', path='/workspace/data.json'), container_file(action='write', path='/workspace/output.txt', content='Hello!'), container_file(action='send_to_discord', path='/workspace/chart.png', message_content='Here is your chart!')",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "read", "write", "send_to_discord"],
                        "description": "Action to perform: 'list' (list files in directory), 'read' (read file content), 'write' (create/modify file), 'send_to_discord' (extract and send file to Discord)"
                    },
                    "path": {
                        "type": "string",
                        "description": "File or directory path in container. Must be within /workspace (e.g., '/workspace/file.txt', '/workspace/images/'). Required for all actions."
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to file (required for action='write'). Can be text or any string data."
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "List files recursively (for action='list'). Default: false. Set to true to list all files in subdirectories."
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Filename pattern to filter (for action='list'). Examples: '*.py', '*.json', 'test_*'. Uses shell glob patterns."
                    },
                    "message_content": {
                        "type": "string",
                        "description": "Text message to send with file (for action='send_to_discord'). Use this to provide context about the file."
                    },
                    "reply_to": {
                        "type": "string",
                        "description": "Message ID to reply to (for action='send_to_discord'). Can be short ID (#N) or full Discord ID."
                    },
                    "spoiler": {
                        "type": "boolean",
                        "description": "Mark file as spoiler (for action='send_to_discord'). Default: false"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "Text encoding for write action. Default: 'utf-8'. Other options: 'ascii', 'latin-1', etc."
                    }
                },
                "required": ["action", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "moderate_member",
            "description": "Execute moderation actions on server members: timeout (mute temporarily), ban (permanent removal), kick (temporary removal), unban (remove ban), remove_timeout (unmute). Each action requires specific permissions and will return clear errors if permissions are missing. Cannot moderate server owner or members with higher roles. Examples: moderate_member(action='timeout', user_id='123', duration=60, reason='Spam'), moderate_member(action='ban', user_id='456', delete_message_days=1, reason='Harassment')",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["timeout", "ban", "kick", "unban", "remove_timeout"],
                        "description": "Moderation action: 'timeout' (mute, requires moderate_members), 'ban' (permanent ban, requires ban_members), 'kick' (temporary removal, requires kick_members), 'unban' (remove ban, requires ban_members), 'remove_timeout' (unmute, requires moderate_members)"
                    },
                    "user_id": {
                        "type": "string",
                        "description": "Discord user ID of the target member. For unban, can be ID of user not in server."
                    },
                    "duration": {
                        "type": "integer",
                        "description": "Timeout duration in minutes (required for action='timeout'). Min: 1, Max: 40320 (28 days). Example: 60 for 1 hour, 1440 for 1 day."
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional reason for the moderation action (shown in audit log and to moderators)."
                    },
                    "delete_message_days": {
                        "type": "integer",
                        "description": "For action='ban' only: delete user's messages from last N days (0-7). Default: 0 (don't delete messages)."
                    }
                },
                "required": ["action", "user_id"]
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
