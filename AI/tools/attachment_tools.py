"""
Attachment Tools - Tools for accessing and reading message attachments

This module provides tools for the LLM to access and read attachments from
Discord messages, supporting various file types including text, images, PDFs, and DOCX.
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple

log = logging.getLogger(__name__)


def parse_discord_cdn_url(url: str) -> Optional[Dict[str, str]]:
    """
    Parse Discord CDN URL to extract channel_id, message_id, and filename.
    
    URL format: https://cdn.discordapp.com/attachments/{channel_id}/{message_id}/{filename}
    or: https://media.discordapp.net/attachments/{channel_id}/{message_id}/{filename}
    
    Args:
        url: Discord CDN URL
        
    Returns:
        Dict with 'channel_id', 'message_id', 'filename' or None if not a valid Discord attachment URL
    """
    try:
        # Pattern for Discord CDN attachment URLs
        pattern = r'https?://(?:cdn\.discordapp\.com|media\.discordapp\.net)/attachments/(\d+)/(\d+)/([^?]+)'
        match = re.match(pattern, url)
        
        if match:
            channel_id, message_id, filename = match.groups()
            return {
                'channel_id': channel_id,
                'message_id': message_id,
                'filename': filename
            }
        
        return None
        
    except Exception as e:
        log.debug(f"Failed to parse Discord CDN URL: {e}")
        return None


async def _fallback_fetch_from_message(
    channel_id: str,
    message_id: str,
    filename: str,
    include_content: bool,
    context: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Fallback: Fetch attachment directly from Discord message.
    
    This is used when a direct URL download fails (e.g., expired URL).
    Fetches the message via Discord API to get a fresh URL.
    
    Args:
        channel_id: Discord channel ID
        message_id: Discord message ID
        filename: Filename to search for
        include_content: Whether to include file content
        context: Context with bot_client
        
    Returns:
        Processed attachment result or None if failed
    """
    try:
        bot_client = context.get("bot_client")
        if not bot_client:
            log.warning("Fallback failed: bot_client not available in context")
            return None
        
        # Get channel
        try:
            channel = bot_client.get_channel(int(channel_id))
            if not channel:
                log.warning(f"Fallback failed: Channel {channel_id} not found")
                return None
        except Exception as e:
            log.warning(f"Fallback failed: Error getting channel: {e}")
            return None
        
        # Fetch message
        try:
            from utils.message_cache import fetch_message_cached
            
            message = await fetch_message_cached(channel, message_id)
            if not message:
                log.warning(f"Fallback failed: Message {message_id} not found (may be deleted)")
                return None
                
        except Exception as e:
            log.warning(f"Fallback failed: Error fetching message: {e}")
            return None
        
        # Check if message has attachments
        if not message.attachments:
            log.warning(f"Fallback failed: Message {message_id} has no attachments")
            return None
        
        # Find attachment by filename
        target_attachment = None
        for att in message.attachments:
            if att.filename == filename:
                target_attachment = att
                break
        
        if not target_attachment:
            log.warning(f"Fallback failed: Attachment '{filename}' not found in message {message_id}")
            return None
        
        # Process attachment with fresh URL
        from utils.attachment_processor import get_attachment_processor
        
        attachment_data = {
            "filename": target_attachment.filename,
            "url": target_attachment.url,  # Fresh URL from Discord API
            "content_type": target_attachment.content_type or "unknown",
            "size": target_attachment.size
        }
        
        log.info(f"Fallback successful: Processing {filename} with fresh URL from message {message_id}")
        
        processor = get_attachment_processor()
        result = await processor.process_attachment(
            attachment=attachment_data,
            include_content=include_content
        )
        
        return result
        
    except Exception as e:
        log.error(f"Fallback error: {e}", exc_info=True)
        return None


async def _process_direct_url(
    url: str,
    include_content: bool,
    context: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Process a direct URL to a file (sticker, attachment, etc.).
    
    Implements automatic fallback for expired Discord CDN URLs:
    1. Tries direct download first
    2. If download fails and URL is from Discord CDN, attempts to fetch from message
    3. Returns result from fallback if successful, otherwise returns original error
    
    Args:
        url: Direct URL to the file
        include_content: Whether to include file content
        context: Context information (required for fallback)
        
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
        
        # Process using AttachmentProcessor
        processor = get_attachment_processor()
        result = await processor.process_attachment(
            attachment=attachment,
            include_content=include_content
        )
        
        # Check if download failed and try fallback for Discord CDN URLs
        if "error" in result and include_content:
            # Parse URL to check if it's a Discord CDN attachment URL
            parsed_url = parse_discord_cdn_url(url)
            
            if parsed_url:
                # This is a Discord CDN attachment URL that failed
                log.info(f"Direct URL download failed for {filename}, attempting fallback to message fetch")
                
                # Try fallback if context is available
                if context:
                    fallback_result = await _fallback_fetch_from_message(
                        channel_id=parsed_url['channel_id'],
                        message_id=parsed_url['message_id'],
                        filename=parsed_url['filename'],
                        include_content=include_content,
                        context=context
                    )
                    
                    if fallback_result:
                        # Fallback succeeded
                        log.info(f"Fallback successful for {filename}")
                        return {
                            "source": "direct_url_with_fallback",
                            "url": url,
                            "attachment": fallback_result,
                            "note": "Original URL failed, retrieved from Discord message (URL may have expired)"
                        }
                    else:
                        # Fallback failed, add helpful context to error
                        result["fallback_attempted"] = True
                        result["fallback_failed"] = True
                        result["suggestion"] = f"URL may have expired and message may be deleted. Try using message_id='{parsed_url['message_id']}' with filename='{parsed_url['filename']}' instead."
                else:
                    # No context available for fallback
                    result["fallback_not_attempted"] = True
                    result["suggestion"] = f"URL may have expired. Try using message_id='{parsed_url['message_id']}' with filename='{parsed_url['filename']}' instead."
        
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
                store = get_store()
                
                # Get AI name from context
                ai_name = context.get("ai_name")
                chat_id = context.get("chat_id", "default")
                
                if not ai_name:
                    return {"error": "AI name not found in context (required for short ID lookup)"}
                
                # Look up Discord ID
                discord_id = manager.get_discord_id(
                    server_id=server_id,
                    channel_id=channel_id,
                    ai_name=ai_name,
                    chat_id=chat_id,
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
                "size": att.size
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
                    include_content=include_content
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
