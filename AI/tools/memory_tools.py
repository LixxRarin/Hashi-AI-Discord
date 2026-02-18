"""
Memory Tools - Persistent memory management for LLM

This module provides tools for the LLM to manage persistent memory across conversations.
Each chat has its own independent memory stored as JSON.

Exported functions for external use:
- read_memory_content(): Get formatted memory content for prompt injection
- delete_memory_file(): Delete memory files during cleanup
- _load_memory(): Load raw memory data (for stats/internal use)

This module provides tools for the LLM to manage persistent memory across conversations.
Each chat has its own independent memory stored as JSON.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

log = logging.getLogger(__name__)

MEMORY_DIR = Path("data/memory")


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
        Path: Path to memory file
    """
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    
    # Sanitize names to prevent path traversal
    safe_server_id = "".join(c for c in server_id if c.isalnum() or c in "_-")
    safe_channel_id = "".join(c for c in channel_id if c.isalnum() or c in "_-")
    safe_ai_name = "".join(c for c in ai_name if c.isalnum() or c in "_-")
    safe_chat_id = "".join(c for c in chat_id if c.isalnum() or c in "_-")
    
    return MEMORY_DIR / f"{safe_server_id}_{safe_channel_id}_{safe_ai_name}_{safe_chat_id}.json"


def _load_memory(server_id: str, channel_id: str, ai_name: str, chat_id: str) -> List[Dict[str, Any]]:
    """
    Load memory entries from file with automatic migration from old format.
    
    Args:
        server_id: Discord server ID
        channel_id: Discord channel ID
        ai_name: AI name
        chat_id: Chat ID
        
    Returns:
        List of memory entries
    """
    # Try new format first
    path = _get_memory_path(server_id, channel_id, ai_name, chat_id)
    
    if not path.exists():
        # Fallback to old format for migration
        safe_ai_name = "".join(c for c in ai_name if c.isalnum() or c in "_-")
        safe_chat_id = "".join(c for c in chat_id if c.isalnum() or c in "_-")
        old_path = MEMORY_DIR / f"{safe_ai_name}_{safe_chat_id}.json"
        
        if old_path.exists():
            log.info(f"Migrating old memory file: {old_path.name} -> {path.name}")
            try:
                with open(old_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Validate structure
                if not isinstance(data, list):
                    log.error(f"Invalid memory file structure in old format for {ai_name}/{chat_id}")
                    return []
                
                # Save to new format (migration)
                _save_memory(server_id, channel_id, ai_name, chat_id, data)
                log.info(f"Successfully migrated memory file to new format")
                
                # Keep old file as backup (don't delete automatically)
                return data
                
            except json.JSONDecodeError as e:
                log.error(f"Failed to parse old memory file for {ai_name}/{chat_id}: {e}")
                return []
            except Exception as e:
                log.error(f"Failed to migrate old memory file for {ai_name}/{chat_id}: {e}")
                return []
        
        # No file exists in either format
        return []
    
    # Load from new format
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Validate structure
        if not isinstance(data, list):
            log.error(f"Invalid memory file structure for {server_id}/{channel_id}/{ai_name}/{chat_id}")
            return []
        
        return data
        
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse memory file for {server_id}/{channel_id}/{ai_name}/{chat_id}: {e}")
        return []
    except Exception as e:
        log.error(f"Failed to load memory for {server_id}/{channel_id}/{ai_name}/{chat_id}: {e}")
        return []


def _save_memory(server_id: str, channel_id: str, ai_name: str, chat_id: str, entries: List[Dict[str, Any]]) -> bool:
    """
    Save memory entries to file.
    
    Args:
        server_id: Discord server ID
        channel_id: Discord channel ID
        ai_name: AI name
        chat_id: Chat ID
        entries: List of memory entries
        
    Returns:
        bool: True if successful
    """
    path = _get_memory_path(server_id, channel_id, ai_name, chat_id)
    
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        
        log.debug(f"Saved {len(entries)} memory entries for {server_id}/{channel_id}/{ai_name}/{chat_id}")
        return True
        
    except Exception as e:
        log.error(f"Failed to save memory for {server_id}/{channel_id}/{ai_name}/{chat_id}: {e}")
        return False


def _calculate_total_tokens(entries: List[Dict]) -> int:
    """
    Calculate total tokens in all entries.
    
    Args:
        entries: List of memory entries
        
    Returns:
        int: Total tokens
    """
    total = 0
    for entry in entries:
        content = entry.get("content", "")
        total += _count_tokens(content)
    return total


def _get_next_id(entries: List[Dict]) -> int:
    """
    Get next available ID.
    
    Args:
        entries: List of memory entries
        
    Returns:
        int: Next ID
    """
    if not entries:
        return 1
    
    return max(entry.get("id", 0) for entry in entries) + 1


async def list_memories(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all memory entries.
    
    Args:
        context: Context information (server_id, channel_id, ai_name, chat_id)
        
    Returns:
        Dict with memories list and metadata
    """
    if context is None:
        return {"error": "No context provided"}
    
    server_id = context.get("server_id")
    channel_id = context.get("channel_id")
    ai_name = context.get("ai_name")
    chat_id = context.get("chat_id", "default")
    max_tokens = context.get("memory_max_tokens", 1000)
    
    if not server_id or not channel_id or not ai_name:
        return {"error": "Missing server_id, channel_id, or ai_name in context"}
    
    try:
        entries = _load_memory(server_id, channel_id, ai_name, chat_id)
        total_tokens = _calculate_total_tokens(entries)
        
        return {
            "memories": entries,
            "count": len(entries),
            "total_tokens": total_tokens,
            "max_tokens": max_tokens
        }
        
    except Exception as e:
        log.error(f"Error in list_memories: {e}", exc_info=True)
        return {
            "error": f"Failed to list memories: {str(e)}",
            "memories": []
        }


async def add_memory(content: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Add a new memory entry.
    
    Args:
        content: Memory content to save
        context: Context information
        
    Returns:
        Dict with success status and new memory ID
    """
    if context is None:
        return {"error": "No context provided"}
    
    if not content or not content.strip():
        return {"error": "Memory content cannot be empty"}
    
    server_id = context.get("server_id")
    channel_id = context.get("channel_id")
    ai_name = context.get("ai_name")
    chat_id = context.get("chat_id", "default")
    max_tokens = context.get("memory_max_tokens", 1000)
    
    if not server_id or not channel_id or not ai_name:
        return {"error": "Missing server_id, channel_id, or ai_name in context"}
    
    try:
        entries = _load_memory(server_id, channel_id, ai_name, chat_id)
        
        # Check token limit
        new_tokens = _count_tokens(content)
        current_tokens = _calculate_total_tokens(entries)
        
        if current_tokens + new_tokens > max_tokens:
            return {
                "error": f"Memory limit exceeded. Current: {current_tokens} tokens, "
                        f"New entry: {new_tokens} tokens, Max: {max_tokens} tokens. "
                        f"Please remove some old memories first.",
                "current_tokens": current_tokens,
                "new_tokens": new_tokens,
                "max_tokens": max_tokens
            }
        
        # Create new entry
        new_id = _get_next_id(entries)
        new_entry = {
            "id": new_id,
            "content": content.strip(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        entries.append(new_entry)
        
        # Save
        if not _save_memory(server_id, channel_id, ai_name, chat_id, entries):
            return {"error": "Failed to save memory"}
        
        log.info(f"Added memory #{new_id} for {server_id}/{channel_id}/{ai_name}/{chat_id} ({new_tokens} tokens)")
        
        return {
            "success": True,
            "memory_id": new_id,
            "tokens_used": new_tokens,
            "total_tokens": current_tokens + new_tokens,
            "max_tokens": max_tokens
        }
        
    except Exception as e:
        log.error(f"Error in add_memory: {e}", exc_info=True)
        return {"error": f"Failed to add memory: {str(e)}"}


async def update_memory(memory_id: int, content: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Update an existing memory entry.
    
    Args:
        memory_id: ID of memory to update
        content: New content
        context: Context information
        
    Returns:
        Dict with success status
    """
    if context is None:
        return {"error": "No context provided"}
    
    if not content or not content.strip():
        return {"error": "Memory content cannot be empty"}
    
    server_id = context.get("server_id")
    channel_id = context.get("channel_id")
    ai_name = context.get("ai_name")
    chat_id = context.get("chat_id", "default")
    max_tokens = context.get("memory_max_tokens", 1000)
    
    if not server_id or not channel_id or not ai_name:
        return {"error": "Missing server_id, channel_id, or ai_name in context"}
    
    try:
        entries = _load_memory(server_id, channel_id, ai_name, chat_id)
        
        # Find entry
        entry_index = None
        for i, entry in enumerate(entries):
            if entry.get("id") == memory_id:
                entry_index = i
                break
        
        if entry_index is None:
            return {
                "error": f"Memory with ID {memory_id} not found",
                "available_ids": [e.get("id") for e in entries]
            }
        
        # Check token limit (excluding the old entry)
        old_tokens = _count_tokens(entries[entry_index].get("content", ""))
        new_tokens = _count_tokens(content)
        other_tokens = _calculate_total_tokens(entries) - old_tokens
        
        if other_tokens + new_tokens > max_tokens:
            return {
                "error": f"Memory limit exceeded. Other entries: {other_tokens} tokens, "
                        f"New content: {new_tokens} tokens, Max: {max_tokens} tokens.",
                "current_tokens": other_tokens + old_tokens,
                "new_tokens": new_tokens,
                "max_tokens": max_tokens
            }
        
        # Update entry
        entries[entry_index]["content"] = content.strip()
        entries[entry_index]["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        # Save
        if not _save_memory(server_id, channel_id, ai_name, chat_id, entries):
            return {"error": "Failed to save memory"}
        
        log.info(f"Updated memory #{memory_id} for {server_id}/{channel_id}/{ai_name}/{chat_id}")
        
        return {
            "success": True,
            "memory_id": memory_id,
            "old_tokens": old_tokens,
            "new_tokens": new_tokens,
            "total_tokens": other_tokens + new_tokens
        }
        
    except Exception as e:
        log.error(f"Error in update_memory: {e}", exc_info=True)
        return {"error": f"Failed to update memory: {str(e)}"}


async def remove_memory(memory_id: int, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Remove a specific memory entry.
    
    Args:
        memory_id: ID of memory to remove
        context: Context information
        
    Returns:
        Dict with success status
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
        entries = _load_memory(server_id, channel_id, ai_name, chat_id)
        
        # Find and remove entry
        entry_index = None
        for i, entry in enumerate(entries):
            if entry.get("id") == memory_id:
                entry_index = i
                break
        
        if entry_index is None:
            return {
                "error": f"Memory with ID {memory_id} not found",
                "available_ids": [e.get("id") for e in entries]
            }
        
        removed_entry = entries.pop(entry_index)
        removed_tokens = _count_tokens(removed_entry.get("content", ""))
        
        # Save
        if not _save_memory(server_id, channel_id, ai_name, chat_id, entries):
            return {"error": "Failed to save memory"}
        
        log.info(f"Removed memory #{memory_id} for {server_id}/{channel_id}/{ai_name}/{chat_id}")
        
        return {
            "success": True,
            "memory_id": memory_id,
            "removed_tokens": removed_tokens,
            "remaining_count": len(entries),
            "remaining_tokens": _calculate_total_tokens(entries)
        }
        
    except Exception as e:
        log.error(f"Error in remove_memory: {e}", exc_info=True)
        return {"error": f"Failed to remove memory: {str(e)}"}


async def search_memories(query: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Search memories by keyword.
    
    Args:
        query: Search term
        context: Context information
        
    Returns:
        Dict with matching memories
    """
    if context is None:
        return {"error": "No context provided"}
    
    if not query or not query.strip():
        return {"error": "Search query cannot be empty"}
    
    server_id = context.get("server_id")
    channel_id = context.get("channel_id")
    ai_name = context.get("ai_name")
    chat_id = context.get("chat_id", "default")
    
    if not server_id or not channel_id or not ai_name:
        return {"error": "Missing server_id, channel_id, or ai_name in context"}
    
    try:
        entries = _load_memory(server_id, channel_id, ai_name, chat_id)
        
        # Search (case-insensitive)
        query_lower = query.lower()
        matches = []
        
        for entry in entries:
            content = entry.get("content", "")
            if query_lower in content.lower():
                matches.append(entry)
        
        return {
            "matches": matches,
            "count": len(matches),
            "query": query
        }
        
    except Exception as e:
        log.error(f"Error in search_memories: {e}", exc_info=True)
        return {
            "error": f"Failed to search memories: {str(e)}",
            "matches": []
        }


def read_memory_content(server_id: str, channel_id: str, ai_name: str, chat_id: str) -> Optional[str]:
    """
    Read memory content for injection into prompt.
    
    This function is used by chat_service to inject memories into the conversation.
    
    Args:
        server_id: Discord server ID
        channel_id: Discord channel ID
        ai_name: AI name
        chat_id: Chat ID
        
    Returns:
        Formatted memory content or None if no memories
    """
    try:
        entries = _load_memory(server_id, channel_id, ai_name, chat_id)
        
        if not entries:
            return None
        
        lines = []
        for entry in entries:
            memory_id = entry.get("id")
            content = entry.get("content", "")
            lines.append(f"[{memory_id}] {content}")
        
        return "\n".join(lines)
        
    except Exception as e:
        log.error(f"Error reading memory content for {server_id}/{channel_id}/{ai_name}/{chat_id}: {e}")
        return None


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
            safe_server_id = "".join(c for c in server_id if c.isalnum() or c in "_-")
            safe_channel_id = "".join(c for c in channel_id if c.isalnum() or c in "_-")
            safe_ai_name = "".join(c for c in ai_name if c.isalnum() or c in "_-")
            pattern = f"{safe_server_id}_{safe_channel_id}_{safe_ai_name}_*.json"
            
            deleted_count = 0
            for path in MEMORY_DIR.glob(pattern):
                path.unlink()
                log.info(f"Deleted memory file: {path.name}")
                deleted_count += 1
            
            return deleted_count > 0
            
    except Exception as e:
        log.error(f"Error deleting memory files for {server_id}/{channel_id}/{ai_name}: {e}")
        return False
