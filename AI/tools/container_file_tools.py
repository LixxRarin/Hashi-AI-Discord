"""
Container File Tools - Tools for accessing and manipulating files in bash containers

This module provides tools for the LLM to interact with files in Docker containers,
including listing, reading, writing, and sending files to Discord.
"""

import logging
import discord
import io
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)


async def container_file(
    action: str,
    path: str,
    content: Optional[str] = None,
    recursive: bool = False,
    pattern: Optional[str] = None,
    message_content: Optional[str] = None,
    reply_to: Optional[str] = None,
    spoiler: bool = False,
    encoding: str = "utf-8",
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Access and manipulate files in the bash container.
    
    This tool allows the LLM to interact with files created in the container,
    including listing, reading, writing, and sending them to Discord.
    
    Args:
        action: Action to perform:
            - "list": List files in directory
            - "read": Read file content
            - "write": Write content to file
            - "send_to_discord": Extract file and send to Discord
        path: File or directory path in container (must be within /workspace)
        content: Content to write (for "write" action)
        recursive: List files recursively (for "list" action)
        pattern: Filename pattern to filter (for "list" action, e.g., "*.py")
        message_content: Text message to send with file (for "send_to_discord")
        reply_to: Message ID to reply to (for "send_to_discord")
        spoiler: Mark file as spoiler (for "send_to_discord")
        encoding: Text encoding (for "write" action, default: utf-8)
        context: Context information (chat_id, channel, session, etc.)
        
    Returns:
        Dict with operation results or error
        
    Examples:
        # List files in workspace
        container_file(action="list", path="/workspace", recursive=True)
        
        # Read a file
        container_file(action="read", path="/workspace/data.json")
        
        # Write a file
        container_file(action="write", path="/workspace/output.txt", content="Hello!")
        
        # Send file to Discord
        container_file(
            action="send_to_discord",
            path="/workspace/chart.png",
            message_content="Here's the chart you requested!"
        )
    """
    if context is None:
        return {"error": "No context provided"}
    
    # Get configuration
    session = context.get("session", {})
    config = session.get("config", {})
    bash_config = config.get("bash_tool", {})
    
    # Check if bash_tool is enabled
    if not bash_config.get("enabled", True):
        return {
            "error": "bash_tool is disabled in configuration",
            "action": action
        }
    
    # Check if file access is enabled
    file_access_config = bash_config.get("file_access", {})
    if not file_access_config.get("enabled", True):
        return {
            "error": "Container file access is disabled in configuration",
            "action": action
        }
    
    # Get chat_id
    chat_id = context.get("chat_id", "default")
    
    log.info(f"container_file called: action={action}, path={path}, chat_id={chat_id}")
    
    try:
        # Get container manager
        from utils.container_manager import get_container_manager
        manager = get_container_manager(bash_config)
        
        # Route to appropriate action
        if action == "list":
            return await _handle_list(manager, chat_id, path, recursive, pattern)
        
        elif action == "read":
            max_size = file_access_config.get("max_file_size", 10 * 1024 * 1024)
            return await _handle_read(manager, chat_id, path, max_size)
        
        elif action == "write":
            if content is None:
                return {"error": "Content is required for 'write' action"}
            return await _handle_write(manager, chat_id, path, content, encoding)
        
        elif action == "send_to_discord":
            return await _handle_send_to_discord(
                manager, chat_id, path, message_content, reply_to, spoiler, context
            )
        
        else:
            return {
                "error": f"Unknown action: {action}",
                "valid_actions": ["list", "read", "write", "send_to_discord"]
            }
    
    except Exception as e:
        log.error(f"Error in container_file (action={action}): {e}", exc_info=True)
        return {
            "error": f"Failed to execute container_file: {str(e)}",
            "action": action
        }


async def _handle_list(
    manager,
    chat_id: str,
    path: str,
    recursive: bool,
    pattern: Optional[str]
) -> Dict[str, Any]:
    """Handle list action."""
    result = await manager.list_files(
        chat_id=chat_id,
        path=path,
        recursive=recursive,
        pattern=pattern
    )
    
    if "error" in result:
        log.warning(f"Failed to list files: {result['error']}")
    else:
        log.info(f"Listed {result.get('total', 0)} files in {path}")
    
    return result


async def _handle_read(
    manager,
    chat_id: str,
    path: str,
    max_size: int
) -> Dict[str, Any]:
    """Handle read action."""
    result = await manager.read_file(
        chat_id=chat_id,
        path=path,
        max_size=max_size
    )
    
    if "error" in result:
        log.warning(f"Failed to read file: {result['error']}")
    else:
        log.info(f"Read file {path} ({result.get('size', 0)} bytes)")
    
    return result


async def _handle_write(
    manager,
    chat_id: str,
    path: str,
    content: str,
    encoding: str
) -> Dict[str, Any]:
    """Handle write action."""
    result = await manager.write_file(
        chat_id=chat_id,
        path=path,
        content=content,
        encoding=encoding
    )
    
    if "error" in result:
        log.warning(f"Failed to write file: {result['error']}")
    else:
        log.info(f"Wrote {result.get('bytes_written', 0)} bytes to {path}")
    
    return result


async def _handle_send_to_discord(
    manager,
    chat_id: str,
    path: str,
    message_content: Optional[str],
    reply_to: Optional[str],
    spoiler: bool,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle send_to_discord action."""
    # Extract file from container
    extract_result = await manager.extract_file(
        chat_id=chat_id,
        path=path,
        max_size=8 * 1024 * 1024  # 8MB Discord limit for bots
    )
    
    if "error" in extract_result:
        log.warning(f"Failed to extract file: {extract_result['error']}")
        return extract_result
    
    # Get channel and session
    channel_id = context.get("channel_id")
    bot_client = context.get("bot_client")
    session = context.get("session", {})
    server_id = context.get("server_id")
    ai_name = context.get("ai_name")
    
    if not all([channel_id, bot_client]):
        return {"error": "Missing required context (channel_id, bot_client)"}
    
    try:
        # Get channel
        channel = bot_client.get_channel(int(channel_id))
        if not channel:
            return {"error": f"Channel {channel_id} not found"}
        
        # Create discord.File from bytes
        file_bytes = extract_result["bytes"]
        filename = extract_result["filename"]
        
        file_obj = discord.File(
            io.BytesIO(file_bytes),
            filename=filename,
            spoiler=spoiler
        )
        
        # Get reference message if reply_to is provided
        reference_message = None
        if reply_to:
            from expressions.reply_expression import ReplyExpression
            reference_message = await ReplyExpression.fetch_message_safe(
                channel, reply_to,
                server_id=server_id,
                ai_name=ai_name
            )
            if not reference_message:
                log.warning(f"Reply target message {reply_to} not found")
        
        # Send using MessageSender
        from utils.message_sender import get_message_sender
        sender = get_message_sender()
        
        message_id = await sender.send_with_attachment(
            channel=channel,
            file=file_obj,
            content=message_content,
            reference=reference_message,
            spoiler=spoiler,
            session=session
        )
        
        if message_id:
            log.info(f"Sent file {filename} to Discord (message_id: {message_id})")
            return {
                "success": True,
                "message_id": message_id,
                "filename": filename,
                "size": extract_result["size"],
                "path": path
            }
        else:
            return {
                "error": "Failed to send file to Discord",
                "filename": filename
            }
    
    except Exception as e:
        log.error(f"Error sending file to Discord: {e}", exc_info=True)
        return {
            "error": f"Failed to send file to Discord: {str(e)}",
            "filename": extract_result.get("filename", "unknown")
        }
