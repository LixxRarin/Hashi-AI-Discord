"""
Attachment Tools - Tools for accessing and reading/sending message attachments

This module provides tools for the LLM to:
- Read attachments from Discord messages (various file types)
- Send attachments to Discord from URLs or base64 data
"""

import logging
import re
import discord
import io
import aiohttp
import base64
from typing import Dict, Any, List, Optional, Tuple
from utils.http_client import create_http_session

log = logging.getLogger(__name__)

# Discord file size limit for bots (8MB)
DISCORD_MAX_FILE_SIZE = 8 * 1024 * 1024


async def _refetch_attachment_url(
    message_id: str,
    filename: str,
    context: Dict[str, Any]
) -> Optional[str]:
    """
    Re-fetch fresh URL for an attachment from Discord API.
    
    This function fetches the message from Discord and retrieves a fresh URL
    for the specified attachment. Used when stored URLs expire (HTTP 404).
    
    Args:
        message_id: Discord message ID
        filename: Attachment filename to search for
        context: Context with bot_client and channel_id
        
    Returns:
        Fresh attachment URL or None if failed
    """
    try:
        bot_client = context.get("bot_client")
        channel_id = context.get("channel_id")
        
        if not bot_client or not channel_id:
            log.warning("Re-fetch failed: bot_client or channel_id not available in context")
            return None
        
        # Get channel
        try:
            channel = bot_client.get_channel(int(channel_id))
            if not channel:
                log.warning(f"Re-fetch failed: Channel {channel_id} not found")
                return None
        except Exception as e:
            log.warning(f"Re-fetch failed: Error getting channel: {e}")
            return None
        
        # Fetch message
        try:
            from utils.message_cache import fetch_message_cached
            
            message = await fetch_message_cached(channel, message_id)
            if not message:
                log.warning(f"Re-fetch failed: Message {message_id} not found (may be deleted)")
                return None
                
        except Exception as e:
            log.warning(f"Re-fetch failed: Error fetching message: {e}")
            return None
        
        # Check if message has attachments
        if not message.attachments:
            log.warning(f"Re-fetch failed: Message {message_id} has no attachments")
            return None
        
        # Find attachment by filename
        for att in message.attachments:
            if att.filename == filename:
                log.info(f"Re-fetch successful: Got fresh URL for {filename} from message {message_id}")
                return att.url
        
        log.warning(f"Re-fetch failed: Attachment '{filename}' not found in message {message_id}")
        return None
        
    except Exception as e:
        log.error(f"Re-fetch error: {e}", exc_info=True)
        return None


async def _process_direct_url(
    url: str,
    include_content: bool,
    context: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Process a direct URL to a file (sticker, attachment, etc.).
    
    Note: Automatic URL refresh on 404 requires message_id in attachment metadata.
    For old messages without stored message_id, URL refresh is not possible.
    
    Args:
        url: Direct URL to the file
        include_content: Whether to include file content
        context: Context information (for automatic URL refresh)
        
    Returns:
        Dict with processed file data or error
    """
    try:
        from utils.attachment_processor import get_attachment_processor
        import os
        
        # Extract filename from URL
        filename = os.path.basename(url.split('?')[0])  # Remove query params
        
        # Try to determine content type from extension
        ext = os.path.splitext(filename)[1].lower()
        content_type_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.txt': 'text/plain',
            '.json': 'application/json',
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.md': 'text/markdown',
            '.xml': 'application/xml',
            '.csv': 'text/csv',
            '.yaml': 'text/yaml',
            '.yml': 'text/yaml'
        }
        content_type = content_type_map.get(ext, 'application/octet-stream')
        
        # Create attachment dict
        attachment = {
            "filename": filename,
            "url": url,
            "content_type": content_type,
            "size": 0  # Unknown until downloaded
        }
        
        log.info(f"Processing direct URL: {filename} ({content_type})")
        
        # Process using AttachmentProcessor (with context for automatic URL refresh)
        processor = get_attachment_processor()
        result = await processor.process_attachment(
            attachment=attachment,
            include_content=include_content,
            context=context
        )
        
        return {
            "source": "direct_url",
            "url": url,
            "attachment": result
        }
        
    except Exception as e:
        log.error(f"Error processing direct URL: {e}", exc_info=True)
        return {
            "error": f"Failed to process URL: {str(e)}",
            "url": url
        }


async def get_attachment_content(
    message_id: Optional[str] = None,
    url: Optional[str] = None,
    attachment_index: Optional[int] = None,
    filename: Optional[str] = None,
    include_content: bool = True,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Get attachment content from a Discord message or direct URL.
    
    This tool allows the LLM to access and read attachments from messages or direct URLs,
    supporting various file types:
    - Text files (txt, md, json, xml, csv, yaml, py, js, html, css, etc.)
    - Images (jpg, png, gif, webp) - returns base64
    - PDFs - extracts text using PyPDF2
    - DOCX - extracts text using python-docx
    - Other files - returns metadata only
    
    Args:
        message_id: Discord message ID or short ID (#N format) - optional if url is provided
        url: Direct URL to file (e.g., sticker URL, attachment URL) - optional if message_id is provided
        attachment_index: Index of attachment to retrieve (0-based, optional, only for message_id)
        filename: Filename to search for (alternative to attachment_index, only for message_id)
        include_content: Whether to include file content (default: True)
        context: Context information (server_id, channel_id, bot_client, etc.)
        
    Returns:
        Dict with attachment data or error
        
    Examples:
        # Get all attachments from a message
        get_attachment_content(message_id="123456789")
        
        # Get specific attachment by index
        get_attachment_content(message_id="123456789", attachment_index=0)
        
        # Get attachment by filename
        get_attachment_content(message_id="5", filename="data.json")
        
        # Process direct URL (sticker, attachment link, etc.)
        get_attachment_content(url="https://cdn.discordapp.com/stickers/123.png")
        
        # Get metadata only (no content)
        get_attachment_content(message_id="10", include_content=False)
    """
    # Validate input
    if not message_id and not url:
        return {"error": "Either message_id or url must be provided"}
    
    if message_id and url:
        return {"error": "Provide either message_id or url, not both"}
    
    # Handle direct URL processing
    if url:
        return await _process_direct_url(url, include_content, context)
    
    # Handle message_id processing (existing logic)
    if context is None:
        return {"error": "No context provided"}
    
    server_id = context.get("server_id")
    channel_id = context.get("channel_id")
    bot_client = context.get("bot_client")
    
    if not all([server_id, channel_id, bot_client]):
        return {"error": "Missing required context (server_id, channel_id, bot_client)"}
    
    try:
        # Get channel
        try:
            channel = bot_client.get_channel(int(channel_id))
            if not channel:
                return {"error": f"Channel {channel_id} not found"}
        except Exception as e:
            log.error(f"Error getting channel: {e}")
            return {"error": f"Failed to get channel: {str(e)}"}
        
        # Handle short ID format (#N)
        discord_id = message_id
        if message_id.startswith('#'):
            # Convert short ID to Discord ID
            try:
                from messaging.short_id_manager import get_short_id_manager_sync
                from messaging.store import get_store

                short_id = int(message_id[1:])
                manager = get_short_id_manager_sync()
                store = get_store(server_id, channel_id)

                # Get AI name from context
                ai_name = context.get("ai_name")
                chat_id = context.get("chat_id", "default")
                
                if not ai_name:
                    return {"error": "AI name not found in context (required for short ID lookup)"}
                
                # Look up Discord ID
                discord_id = await manager.get_discord_id(
                    server_id=server_id,
                    channel_id=channel_id,
                    ai_name=ai_name,
                    short_id=short_id
                )
                
                if not discord_id:
                    return {"error": f"Message with short ID #{short_id} not found"}
                
            except ValueError:
                return {"error": f"Invalid short ID format: {message_id}"}
            except Exception as e:
                log.error(f"Error resolving short ID: {e}")
                return {"error": f"Failed to resolve short ID: {str(e)}"}
        
        # Fetch message using cached fetch
        try:
            from utils.message_cache import fetch_message_cached
            
            message = await fetch_message_cached(channel, discord_id)
            
            if not message:
                return {"error": f"Message {message_id} not found"}
                
        except Exception as e:
            log.error(f"Error fetching message: {e}")
            return {"error": f"Failed to fetch message: {str(e)}"}
        
        # Check if message has attachments
        if not message.attachments or len(message.attachments) == 0:
            return {
                "message_id": message_id,
                "discord_id": str(message.id),
                "attachments": [],
                "total_attachments": 0,
                "note": "Message has no attachments"
            }
        
        # Convert Discord attachments to dict format
        attachments_data = []
        for att in message.attachments:
            attachments_data.append({
                "filename": att.filename,
                "url": att.url,
                "content_type": att.content_type or "unknown",
                "size": att.size,
                "message_id": str(message.id)
            })
        
        # Filter attachments if requested
        filtered_attachments = []
        
        if attachment_index is not None:
            # Get specific attachment by index
            if 0 <= attachment_index < len(attachments_data):
                filtered_attachments = [attachments_data[attachment_index]]
            else:
                return {
                    "error": f"Attachment index {attachment_index} out of range (0-{len(attachments_data)-1})",
                    "total_attachments": len(attachments_data)
                }
        
        elif filename is not None:
            # Search by filename
            for att in attachments_data:
                if att["filename"].lower() == filename.lower():
                    filtered_attachments.append(att)
            
            if not filtered_attachments:
                available_files = [att["filename"] for att in attachments_data]
                return {
                    "error": f"Attachment with filename '{filename}' not found",
                    "available_files": available_files,
                    "total_attachments": len(attachments_data)
                }
        
        else:
            # Return all attachments
            filtered_attachments = attachments_data
        
        # Process attachments
        from utils.attachment_processor import get_attachment_processor
        
        processor = get_attachment_processor()
        processed_attachments = []
        
        for idx, att in enumerate(filtered_attachments):
            log.info(f"Processing attachment: {att['filename']} ({att['content_type']}, {att['size']} bytes)")
            
            try:
                result = await processor.process_attachment(
                    attachment=att,
                    include_content=include_content,
                    context=context
                )
                
                # Add index information
                if attachment_index is not None:
                    result["index"] = attachment_index
                else:
                    # Find original index
                    for i, original_att in enumerate(attachments_data):
                        if original_att["filename"] == att["filename"]:
                            result["index"] = i
                            break
                
                processed_attachments.append(result)
                
            except Exception as e:
                log.error(f"Error processing attachment {att['filename']}: {e}")
                processed_attachments.append({
                    "filename": att["filename"],
                    "error": f"Failed to process attachment: {str(e)}"
                })
        
        return {
            "message_id": message_id,
            "discord_id": str(message.id),
            "attachments": processed_attachments,
            "total_attachments": len(attachments_data),
            "processed_count": len(processed_attachments)
        }
    
    except Exception as e:
        log.error(f"Error in get_attachment_content: {e}", exc_info=True)
        return {
            "error": f"Failed to get attachment content: {str(e)}",
            "message_id": message_id
        }


async def send_attachment(
    file_source: str,
    url: Optional[str] = None,
    base64_data: Optional[str] = None,
    filename: Optional[str] = None,
    content: Optional[str] = None,
    reply_to: Optional[str] = None,
    spoiler: bool = False,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Send an attachment to Discord from various sources.
    
    This tool allows the LLM to send files to Discord from:
    - URLs: Download and send files from external links
    - Base64: Send files encoded as base64 strings
    
    Note: For sending files from the container, use container_file with action="send_to_discord"
    
    Args:
        file_source: Source type ("url" or "base64")
        url: URL to download file from (required if file_source="url")
        base64_data: Base64-encoded file data (required if file_source="base64")
        filename: Filename for the attachment (required for base64, optional for url)
        content: Optional text message to send with the attachment
        reply_to: Optional message ID to reply to
        spoiler: Mark attachment as spoiler (default: False)
        context: Context information (channel, session, etc.)
        
    Returns:
        Dict with message_id and status, or error
        
    Examples:
        # Send image from URL
        send_attachment(
            file_source="url",
            url="https://example.com/image.png",
            content="Here's the image!"
        )
        
        # Send file from base64
        send_attachment(
            file_source="base64",
            base64_data="iVBORw0KGgo...",
            filename="chart.png",
            content="Generated chart"
        )
        
        # Send with spoiler tag
        send_attachment(
            file_source="url",
            url="https://example.com/spoiler.jpg",
            spoiler=True
        )
    """
    if context is None:
        return {"error": "No context provided"}
    
    log.info(f"send_attachment called: source={file_source}, filename={filename}")
    
    # Validate file_source
    if file_source not in ["url", "base64"]:
        return {
            "error": f"Invalid file_source: {file_source}",
            "valid_sources": ["url", "base64"],
            "note": "For container files, use container_file with action='send_to_discord'"
        }
    
    try:
        # Route to appropriate handler
        if file_source == "url":
            return await _send_from_url(
                url, filename, content, reply_to, spoiler, context
            )
        elif file_source == "base64":
            return await _send_from_base64(
                base64_data, filename, content, reply_to, spoiler, context
            )
    
    except Exception as e:
        log.error(f"Error in send_attachment: {e}", exc_info=True)
        return {
            "error": f"Failed to send attachment: {str(e)}",
            "file_source": file_source
        }


async def _send_from_url(
    url: Optional[str],
    filename: Optional[str],
    content: Optional[str],
    reply_to: Optional[str],
    spoiler: bool,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle sending attachment from URL."""
    if not url:
        return {"error": "URL is required for file_source='url'"}
    
    log.info(f"Downloading file from URL: {url}")
    
    try:
        # Download file from URL
        async with create_http_session(timeout_total=30) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return {
                        "error": f"Failed to download from URL: HTTP {response.status}",
                        "url": url
                    }
                
                # Check content length
                content_length = response.headers.get('Content-Length')
                if content_length:
                    size = int(content_length)
                    if size > DISCORD_MAX_FILE_SIZE:
                        return {
                            "error": f"File too large: {size} bytes (max: {DISCORD_MAX_FILE_SIZE} bytes)",
                            "size": size,
                            "max_size": DISCORD_MAX_FILE_SIZE,
                            "url": url
                        }
                
                # Read file data
                file_data = await response.read()
                
                # Check actual size
                if len(file_data) > DISCORD_MAX_FILE_SIZE:
                    return {
                        "error": f"File too large: {len(file_data)} bytes (max: {DISCORD_MAX_FILE_SIZE} bytes)",
                        "size": len(file_data),
                        "max_size": DISCORD_MAX_FILE_SIZE,
                        "url": url
                    }
                
                # Determine filename if not provided
                if not filename:
                    # Try to get from Content-Disposition header
                    content_disposition = response.headers.get('Content-Disposition', '')
                    if 'filename=' in content_disposition:
                        filename = content_disposition.split('filename=')[1].strip('"\'')
                    else:
                        # Extract from URL
                        import os
                        filename = os.path.basename(url.split('?')[0])
                        if not filename or filename == '/':
                            filename = "download"
                
                log.info(f"Downloaded {len(file_data)} bytes from {url}")
        
        # Send to Discord
        return await _send_file_to_discord(
            file_data, filename, content, reply_to, spoiler, context
        )
    
    except aiohttp.ClientError as e:
        log.error(f"HTTP error downloading from URL: {e}")
        return {
            "error": f"Failed to download from URL: {str(e)}",
            "url": url
        }
    except Exception as e:
        log.error(f"Error downloading from URL: {e}", exc_info=True)
        return {
            "error": f"Failed to download from URL: {str(e)}",
            "url": url
        }


async def _send_from_base64(
    base64_data: Optional[str],
    filename: Optional[str],
    content: Optional[str],
    reply_to: Optional[str],
    spoiler: bool,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle sending attachment from base64 data."""
    if not base64_data:
        return {"error": "base64_data is required for file_source='base64'"}
    
    if not filename:
        return {"error": "filename is required for file_source='base64'"}
    
    log.info(f"Decoding base64 data for file: {filename}")
    
    try:
        # Decode base64
        file_data = base64.b64decode(base64_data)
        
        # Check size
        if len(file_data) > DISCORD_MAX_FILE_SIZE:
            return {
                "error": f"File too large: {len(file_data)} bytes (max: {DISCORD_MAX_FILE_SIZE} bytes)",
                "size": len(file_data),
                "max_size": DISCORD_MAX_FILE_SIZE
            }
        
        log.info(f"Decoded {len(file_data)} bytes from base64")
        
        # Send to Discord
        return await _send_file_to_discord(
            file_data, filename, content, reply_to, spoiler, context
        )
    
    except base64.binascii.Error as e:
        log.error(f"Invalid base64 data: {e}")
        return {
            "error": f"Invalid base64 data: {str(e)}"
        }
    except Exception as e:
        log.error(f"Error decoding base64: {e}", exc_info=True)
        return {
            "error": f"Failed to decode base64: {str(e)}"
        }


async def _send_file_to_discord(
    file_data: bytes,
    filename: str,
    content: Optional[str],
    reply_to: Optional[str],
    spoiler: bool,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Send file data to Discord."""
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
        file_obj = discord.File(
            io.BytesIO(file_data),
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
            content=content,
            reference=reference_message,
            spoiler=spoiler,
            session=session
        )
        
        if message_id:
            log.info(f"Sent attachment {filename} to Discord (message_id: {message_id})")
            return {
                "success": True,
                "message_id": message_id,
                "filename": filename,
                "size": len(file_data)
            }
        else:
            return {
                "error": "Failed to send attachment to Discord",
                "filename": filename
            }
    
    except discord.HTTPException as e:
        log.error(f"Discord HTTP error: {e}")
        return {
            "error": f"Discord error: {str(e)}",
            "filename": filename
        }
    except Exception as e:
        log.error(f"Error sending to Discord: {e}", exc_info=True)
        return {
            "error": f"Failed to send to Discord: {str(e)}",
            "filename": filename
        }

