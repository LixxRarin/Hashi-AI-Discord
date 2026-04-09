"""
Memory Tools - Persistent memory management for LLM (Markdown-based)

This module provides tools for the LLM to manage persistent memory using Markdown files.
The LLM can read and write the entire memory file, organizing information by topics.

Tool functions (for LLM):
- read_memory(): Read the full memory file
- write_memory(): Write/update the full memory file

Exported functions for external use:
- get_memory_file_path(): Get path to memory file
- read_memory_content(): Get formatted memory content for prompt injection (without frontmatter)
- initialize_memory_file(): Create initial memory file with frontmatter
- get_memory_stats(): Get statistics about memory usage
- delete_memory_file(): Delete memory files during cleanup
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def _count_tokens(text: str) -> int:
    """
    Count tokens using tiktoken.

    Args:
        text: Text to count tokens for

    Returns:
        int: Number of tokens
    """
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception as e:
        log.warning(f"Failed to use tiktoken, falling back to approximation: {e}")
        # Fallback: approximate 4 characters per token
        return len(text) // 4


def _get_memory_path(server_id: str, channel_id: str, ai_name: str, chat_id: str) -> Path:
    """
    Get memory file path for server, channel, AI and chat.

    Args:
        server_id: Discord server ID
        channel_id: Discord channel ID
        ai_name: AI name
        chat_id: Chat ID

    Returns:
        Path: Path to memory Markdown file
    """
    from utils.core.paths import DataPaths

    data_paths = DataPaths()
    memory_file = data_paths.get_memory_file(server_id, channel_id, ai_name, chat_id)

    # Ensure directory exists
    data_paths.ensure_directory(memory_file)

    return Path(memory_file)


def get_memory_file_path(server_id: str, channel_id: str, ai_name: str, chat_id: str) -> Path:
    """
    Get path to memory file for LLM to use with Read/Edit tools.

    Args:
        server_id: Discord server ID
        channel_id: Discord channel ID
        ai_name: AI name
        chat_id: Chat ID

    Returns:
        Path: Path to memory Markdown file
    """
    return _get_memory_path(server_id, channel_id, ai_name, chat_id)


def parse_memory_frontmatter(server_id: str, channel_id: str, ai_name: str, chat_id: str) -> Optional[Dict[str, Any]]:
    """
    Parse frontmatter from memory file.

    Args:
        server_id: Discord server ID
        channel_id: Discord channel ID
        ai_name: AI name
        chat_id: Chat ID

    Returns:
        Dict with frontmatter metadata or None if file doesn't exist
    """
    path = _get_memory_path(server_id, channel_id, ai_name, chat_id)

    if not path.exists():
        return None

    try:
        import frontmatter
        with open(path, 'r', encoding='utf-8') as f:
            post = frontmatter.load(f)
        return dict(post.metadata)
    except Exception as e:
        log.error(f"Failed to parse frontmatter for {path}: {e}")
        return None


def initialize_memory_file(server_id: str, channel_id: str, ai_name: str, chat_id: str) -> bool:
    """
    Create initial memory file with frontmatter if it doesn't exist.

    Args:
        server_id: Discord server ID
        channel_id: Discord channel ID
        ai_name: AI name
        chat_id: Chat ID

    Returns:
        bool: True if file was created, False if already exists or error
    """
    path = _get_memory_path(server_id, channel_id, ai_name, chat_id)

    if path.exists():
        return False

    try:
        import frontmatter

        now = datetime.now(timezone.utc).isoformat()

        # Create initial content with frontmatter
        post = frontmatter.Post(
            "# Persistent Memory\n\n*No memories saved yet. Use the Edit tool to add information organized by topics.*\n",
            ai_name=ai_name,
            chat_id=chat_id,
            created=now,
            last_updated=now
        )

        with open(path, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(post))

        log.info(f"Initialized memory file: {path}")
        return True

    except Exception as e:
        log.error(f"Failed to initialize memory file {path}: {e}")
        return False


def read_memory_content(server_id: str, channel_id: str, ai_name: str, chat_id: str) -> Optional[str]:
    """
    Read memory content for injection into prompt (without frontmatter).

    This function is used by chat_service to inject memories into the conversation.

    Args:
        server_id: Discord server ID
        channel_id: Discord channel ID
        ai_name: AI name
        chat_id: Chat ID

    Returns:
        Memory content without frontmatter or None if no file exists
    """
    path = _get_memory_path(server_id, channel_id, ai_name, chat_id)

    if not path.exists():
        return None

    try:
        import frontmatter
        with open(path, 'r', encoding='utf-8') as f:
            post = frontmatter.load(f)

        # Return content without frontmatter
        return post.content.strip()

    except Exception as e:
        log.error(f"Error reading memory content for {path}: {e}")
        return None


def get_memory_stats(server_id: str, channel_id: str, ai_name: str, chat_id: str) -> Dict[str, Any]:
    """
    Get statistics about memory usage.

    Args:
        server_id: Discord server ID
        channel_id: Discord channel ID
        ai_name: AI name
        chat_id: Chat ID

    Returns:
        Dict with stats: exists, token_count, last_updated, file_size
    """
    path = _get_memory_path(server_id, channel_id, ai_name, chat_id)

    if not path.exists():
        return {
            "exists": False,
            "token_count": 0,
            "last_updated": None,
            "file_size": 0
        }

    try:
        content = read_memory_content(server_id, channel_id, ai_name, chat_id)
        metadata = parse_memory_frontmatter(server_id, channel_id, ai_name, chat_id)

        return {
            "exists": True,
            "token_count": _count_tokens(content) if content else 0,
            "last_updated": metadata.get("last_updated") if metadata else None,
            "file_size": path.stat().st_size
        }

    except Exception as e:
        log.error(f"Error getting memory stats for {path}: {e}")
        return {
            "exists": True,
            "token_count": 0,
            "last_updated": None,
            "file_size": 0
        }


def delete_memory_file(server_id: str, channel_id: str, ai_name: str, chat_id: str = None) -> bool:
    """
    Delete memory file(s) for an AI in a specific server and channel. Used during cleanup.

    Args:
        server_id: Discord server ID
        channel_id: Discord channel ID
        ai_name: AI name
        chat_id: Optional chat ID. If None, deletes all chats for this AI in this channel

    Returns:
        bool: True if any files were deleted
    """
    try:
        from utils.core.paths import DataPaths

        if chat_id:
            # Delete specific chat memory
            path = _get_memory_path(server_id, channel_id, ai_name, chat_id)
            if path.exists():
                path.unlink()
                log.info(f"Deleted memory file: {path.name}")
                return True
            return False
        else:
            # Delete all memory files for this AI in this channel
            data_paths = DataPaths()
            memory_dir = Path(data_paths.get_memory_dir(server_id, channel_id))

            if not memory_dir.exists():
                return False

            safe_ai_name = "".join(c for c in ai_name if c.isalnum() or c in "_-")
            pattern = f"{safe_ai_name}_*.md"

            deleted_count = 0
            for path in memory_dir.glob(pattern):
                path.unlink()
                log.info(f"Deleted memory file: {path.name}")
                deleted_count += 1

            return deleted_count > 0

    except Exception as e:
        log.error(f"Error deleting memory files for channel {channel_id}: {e}")
        return False


def delete_server_memory_files(server_id: str) -> int:
    """
    Delete all memory files for a server. Used during server cleanup.

    Args:
        server_id: Server ID

    Returns:
        int: Number of files deleted
    """
    try:
        from utils.core.paths import DataPaths

        data_paths = DataPaths()
        deleted_count = 0

        # Iterate through all channels in the server
        channels = data_paths.list_channels(server_id)

        for channel_id in channels:
            memory_dir = Path(data_paths.get_memory_dir(server_id, channel_id))

            if not memory_dir.exists():
                continue

            # Delete all memory files in this channel's memory directory
            for memory_file in memory_dir.glob("*.md"):
                memory_file.unlink()
                deleted_count += 1

        if deleted_count > 0:
            log.info(f"Deleted {deleted_count} memory file(s)")

        return deleted_count

    except Exception as e:
        log.error(f"Error deleting memory files: {e}")
        return 0


def delete_channel_memory_files(server_id: str, channel_id: str) -> int:
    """
    Delete all memory files for a specific channel. Used during channel cleanup.

    Args:
        server_id: Server ID
        channel_id: Channel ID

    Returns:
        int: Number of files deleted
    """
    try:
        from utils.core.paths import DataPaths

        data_paths = DataPaths()
        memory_dir = Path(data_paths.get_memory_dir(server_id, channel_id))

        if not memory_dir.exists():
            return 0

        deleted_count = 0
        for memory_file in memory_dir.glob("*.md"):
            memory_file.unlink()
            deleted_count += 1

        if deleted_count > 0:
            log.info(f"Deleted {deleted_count} memory file(s) for channel {channel_id}")

        return deleted_count

    except Exception as e:
        log.error(f"Error deleting memory files for channel {channel_id}: {e}")
        return 0


# ==================== Tool Functions for LLM ====================

async def read_memory(context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Read the full memory file (tool for LLM).

    Returns the complete memory content including frontmatter metadata.

    Args:
        context: Context information (server_id, channel_id, ai_name, chat_id)

    Returns:
        Dict with full_content (entire file) and metadata
    """
    if context is None:
        return {"error": "No context provided"}

    server_id = context.get("server_id")
    channel_id = context.get("channel_id")
    ai_name = context.get("ai_name")
    chat_id = context.get("chat_id", "default")

    if not server_id or not channel_id or not ai_name:
        return {"error": "Missing server_id, channel_id, or ai_name in context"}

    try:
        path = _get_memory_path(server_id, channel_id, ai_name, chat_id)

        if not path.exists():
            return {
                "error": "Memory file does not exist yet",
                "suggestion": "File will be created automatically when you save information"
            }

        import frontmatter
        with open(path, 'r', encoding='utf-8') as f:
            post = frontmatter.load(f)

        # Convert metadata to JSON-serializable format
        metadata = {}
        for key, value in post.metadata.items():
            if isinstance(value, datetime):
                metadata[key] = value.isoformat()
            else:
                metadata[key] = value

        return {
            "success": True,
            "content": post.content.strip(),
            "metadata": metadata,
            "file_path": str(path),
            "tokens": _count_tokens(post.content)
        }

    except Exception as e:
        log.error(f"Error in read_memory: {e}", exc_info=True)
        return {"error": f"Failed to read memory: {str(e)}"}


async def edit_memory(old_string: str, new_string: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Edit memory by replacing old_string with new_string (tool for LLM).

    Similar to a text editor's find-and-replace. Use this to make surgical edits
    without rewriting the entire file.

    Args:
        old_string: Text to find and replace (must match exactly)
        new_string: Text to replace it with
        context: Context information

    Returns:
        Dict with success status and statistics
    """
    if context is None:
        return {"error": "No context provided"}

    if old_string == new_string:
        return {"error": "old_string and new_string are identical - no changes to make"}

    server_id = context.get("server_id")
    channel_id = context.get("channel_id")
    ai_name = context.get("ai_name")
    chat_id = context.get("chat_id", "default")
    max_tokens = context.get("memory_max_tokens", 1500)

    if not server_id or not channel_id or not ai_name:
        return {"error": "Missing server_id, channel_id, or ai_name in context"}

    try:
        path = _get_memory_path(server_id, channel_id, ai_name, chat_id)

        # Load existing file or create new
        import frontmatter
        now = datetime.now(timezone.utc).isoformat()

        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                post = frontmatter.load(f)
            content = post.content
            metadata = dict(post.metadata)
        else:
            # Create new file with initial structure
            content = "# Persistent Memory\n\n*No memories saved yet.*\n"
            metadata = {
                "ai_name": ai_name,
                "chat_id": chat_id,
                "created": now,
                "last_updated": now
            }

        # Perform replacement
        if old_string not in content:
            return {
                "error": f"String to replace not found in memory file",
                "old_string": old_string[:100] + "..." if len(old_string) > 100 else old_string,
                "suggestion": "Use read_memory() to see current content, then try again with exact text"
            }

        # Count occurrences
        occurrences = content.count(old_string)
        if occurrences > 1:
            return {
                "error": f"Found {occurrences} matches of old_string. Please provide more context to make it unique.",
                "occurrences": occurrences
            }

        # Replace
        new_content = content.replace(old_string, new_string, 1)

        # Check token limit
        new_tokens = _count_tokens(new_content)
        if new_tokens > max_tokens:
            return {
                "error": f"Edit would exceed token limit. Result: {new_tokens} tokens, Max: {max_tokens} tokens. "
                        f"Please consolidate or remove some information.",
                "current_tokens": new_tokens,
                "max_tokens": max_tokens
            }

        # Update metadata
        metadata["last_updated"] = now

        # Save
        post = frontmatter.Post(new_content.strip(), **metadata)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(post))

        log.info(f"Edited memory for channel {channel_id}/chat {chat_id} ({new_tokens} tokens)")

        return {
            "success": True,
            "tokens_used": new_tokens,
            "max_tokens": max_tokens,
            "file_path": str(path)
        }

    except Exception as e:
        log.error(f"Error in edit_memory: {e}", exc_info=True)
        return {"error": f"Failed to edit memory: {str(e)}"}


async def write_memory(content: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Write/replace the full memory file (tool for LLM).

    Use this ONLY for initial creation or complete rewrites.
    For updates, use edit_memory() instead.

    Args:
        content: New memory content (Markdown format, without frontmatter)
        context: Context information

    Returns:
        Dict with success status and statistics
    """
    if context is None:
        return {"error": "No context provided"}

    if not content or not content.strip():
        return {"error": "Memory content cannot be empty"}

    server_id = context.get("server_id")
    channel_id = context.get("channel_id")
    ai_name = context.get("ai_name")
    chat_id = context.get("chat_id", "default")
    max_tokens = context.get("memory_max_tokens", 1500)

    if not server_id or not channel_id or not ai_name:
        return {"error": "Missing server_id, channel_id, or ai_name in context"}

    try:
        path = _get_memory_path(server_id, channel_id, ai_name, chat_id)

        # Check token limit
        new_tokens = _count_tokens(content)
        if new_tokens > max_tokens:
            return {
                "error": f"Memory exceeds token limit. Content: {new_tokens} tokens, Max: {max_tokens} tokens. "
                        f"Please consolidate or remove some information.",
                "current_tokens": new_tokens,
                "max_tokens": max_tokens
            }

        # Load existing metadata or create new
        import frontmatter
        now = datetime.now(timezone.utc).isoformat()

        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                old_post = frontmatter.load(f)
            metadata = dict(old_post.metadata)
            metadata["last_updated"] = now
        else:
            metadata = {
                "ai_name": ai_name,
                "chat_id": chat_id,
                "created": now,
                "last_updated": now
            }

        # Create new post with updated content
        post = frontmatter.Post(content.strip(), **metadata)

        # Save
        with open(path, 'w', encoding='utf-8') as f:
            f.write(frontmatter.dumps(post))

        log.info(f"Wrote memory file for channel {channel_id}/chat {chat_id} ({new_tokens} tokens)")

        return {
            "success": True,
            "tokens_used": new_tokens,
            "max_tokens": max_tokens,
            "file_path": str(path)
        }

    except Exception as e:
        log.error(f"Error in write_memory: {e}", exc_info=True)
        return {"error": f"Failed to write memory: {str(e)}"}
