"""
Message Tools - Tools for querying and managing messages

This module provides tools for the LLM to query and manage messages:
- get_message_info: Query message information from conversation history
- edit_own_message: Edit the AI's own messages
- delete_message: Delete messages (own or others with permission)
"""

import logging
import discord
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

        store = get_store(server_id, channel_id)
        short_id_manager = get_short_id_manager()

        # Ensure store data is loaded from disk
        await store._ensure_loaded()

        # Get chat from store (store is now scoped to channel)
        chat = store._data.get(ai_name, {}).get("chats", {}).get(chat_id)
        
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


async def edit_own_message(
    message_id: str,
    new_content: str,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Edit one of the AI's own messages.
    
    This tool allows the LLM to edit any of its previous messages in the
    current conversation. It validates that the message belongs to the AI
    before editing.
    
    Args:
        message_id: Short ID (#5) or Discord ID to edit
        new_content: New content for the message
        context: Tool execution context (bot_client, guild, channel_id, etc.)
        
    Returns:
        Dict with success status and details
    """
    if context is None:
        return {"success": False, "error": "No context provided"}
    
    # Validate parameters
    if not message_id:
        return {
            "success": False,
            "error": "message_id is required",
            "message": "Please provide a message_id to edit"
        }
    
    if not new_content or new_content.isspace():
        return {
            "success": False,
            "error": "new_content cannot be empty",
            "message": "Please provide non-empty content for the message"
        }
    
    try:
        # Extract context
        bot_client = context.get("bot_client")
        channel_id = context.get("channel_id")
        server_id = context.get("server_id")
        ai_name = context.get("ai_name")
        session = context.get("session", {})
        
        if not all([bot_client, channel_id, server_id, ai_name]):
            return {
                "success": False,
                "error": "Missing required context",
                "message": "Internal error: missing bot_client, channel_id, server_id, or ai_name"
            }
        
        # Get channel
        try:
            channel = bot_client.get_channel(int(channel_id))
            if not channel:
                return {
                    "success": False,
                    "error": "Channel not found",
                    "message": f"Could not find channel {channel_id}"
                }
        except ValueError:
            return {
                "success": False,
                "error": "Invalid channel_id",
                "message": f"Invalid channel ID: {channel_id}"
            }
        
        # Resolve message_id (short_id -> discord_id if needed)
        resolved_message_id = message_id
        short_id = None
        
        # Check if it's a short_id format (#5 or just 5)
        if message_id.startswith('#'):
            try:
                short_id = int(message_id[1:])
                # Resolve short_id to discord_id
                from messaging.short_id_manager import get_short_id_manager
                short_id_manager = get_short_id_manager()
                resolved_message_id = await short_id_manager.get_discord_id(
                    server_id, channel_id, ai_name, short_id
                )
                if not resolved_message_id:
                    return {
                        "success": False,
                        "error": f"Short ID #{short_id} not found",
                        "message": f"Message #{short_id} not found in conversation history"
                    }
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid short_id format: {message_id}",
                    "message": "Short ID must be a number (e.g., #5)"
                }
        elif message_id.isdigit() and len(message_id) < 10:
            # Looks like a short_id without #
            try:
                short_id = int(message_id)
                from messaging.short_id_manager import get_short_id_manager
                short_id_manager = get_short_id_manager()
                resolved_message_id = await short_id_manager.get_discord_id(
                    server_id, channel_id, ai_name, short_id
                )
                if not resolved_message_id:
                    return {
                        "success": False,
                        "error": f"Short ID {short_id} not found",
                        "message": f"Message #{short_id} not found in conversation history"
                    }
            except ValueError:
                pass  # Not a valid short_id, treat as discord_id
        
        # Fetch the message
        try:
            from utils.message_cache import fetch_message_cached
            message = await fetch_message_cached(channel, resolved_message_id)
            
            if not message:
                return {
                    "success": False,
                    "error": "Message not found",
                    "message_id": message_id,
                    "message": f"Message {message_id} not found in channel"
                }
        except discord.NotFound:
            return {
                "success": False,
                "error": "Message not found",
                "message_id": message_id,
                "message": f"Message {message_id} not found (may have been deleted)"
            }
        except Exception as e:
            log.error(f"Error fetching message {resolved_message_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to fetch message: {str(e)}",
                "message_id": message_id
            }
        
        # Validate ownership - check if message is from the bot
        if message.author.id != bot_client.user.id:
            return {
                "success": False,
                "error": "Cannot edit message: not your message",
                "message_id": message_id,
                "message_author": f"{message.author.name}#{message.author.discriminator}",
                "message": f"You can only edit your own messages. This message belongs to {message.author.name}."
            }
        
        # Edit the message using MessageSender
        from utils.message_sender import get_message_sender
        sender = get_message_sender()
        
        mode = session.get("mode", "bot")
        webhook_url = session.get("webhook_url")
        
        try:
            updated_ids = await sender.edit_messages(
                channel=channel,
                message_ids=[resolved_message_id],
                new_text=new_content,
                mode=mode,
                webhook_url=webhook_url,
                split_message_fn=None
            )
            
            if not updated_ids:
                return {
                    "success": False,
                    "error": "Failed to edit message",
                    "message_id": message_id,
                    "message": "Message edit operation failed"
                }
            
            # Update conversation history
            from AI.services.chat_service import get_service
            chat_service = get_service()
            
            current_chat_id = session.get("chat_id", "default")
            history = await chat_service.get_ai_history(
                server_id,
                channel_id,
                ai_name,
                current_chat_id
            )
            
            # Find and update the assistant message in history
            updated_history = False
            if history:
                for i in range(len(history) - 1, -1, -1):
                    if history[i]["role"] == "assistant":
                        # Check if this is the message we edited
                        # (we'll update the most recent assistant message for simplicity)
                        history[i]["content"] = new_content
                        updated_history = True
                        break
                
                if updated_history:
                    await chat_service.set_ai_history(
                        server_id,
                        channel_id,
                        ai_name,
                        history,
                        current_chat_id
                    )
            
            log.info(f"Message {message_id} edited successfully by AI {ai_name}")
            
            return {
                "success": True,
                "message_id": resolved_message_id,
                "short_id": short_id,
                "updated_content": new_content[:100] + "..." if len(new_content) > 100 else new_content,
                "message": f"Message {message_id} edited successfully"
            }
            
        except discord.Forbidden:
            return {
                "success": False,
                "error": "Permission denied",
                "message_id": message_id,
                "message": "Cannot edit message: missing permissions"
            }
        except Exception as e:
            log.error(f"Error editing message {message_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to edit message: {str(e)}",
                "message_id": message_id
            }
    
    except Exception as e:
        log.error(f"Error in edit_own_message: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Internal error: {str(e)}",
            "message_id": message_id
        }


async def delete_message(
    message_id: str,
    reason: Optional[str] = None,
    context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Delete a message from Discord.
    
    The AI can always delete its own messages. To delete other users' messages,
    the bot needs 'manage_messages' permission. Returns clear error if permission
    is missing.
    
    Args:
        message_id: Short ID (#5) or Discord ID to delete
        reason: Optional reason for deletion (for logging)
        context: Tool execution context
        
    Returns:
        Dict with success status and permission details
    """
    if context is None:
        return {"success": False, "error": "No context provided"}
    
    # Validate parameters
    if not message_id:
        return {
            "success": False,
            "error": "message_id is required",
            "message": "Please provide a message_id to delete"
        }
    
    try:
        # Extract context
        bot_client = context.get("bot_client")
        channel_id = context.get("channel_id")
        server_id = context.get("server_id")
        ai_name = context.get("ai_name")
        session = context.get("session", {})
        
        if not all([bot_client, channel_id, server_id, ai_name]):
            return {
                "success": False,
                "error": "Missing required context",
                "message": "Internal error: missing bot_client, channel_id, server_id, or ai_name"
            }
        
        # Get channel
        try:
            channel = bot_client.get_channel(int(channel_id))
            if not channel:
                return {
                    "success": False,
                    "error": "Channel not found",
                    "message": f"Could not find channel {channel_id}"
                }
        except ValueError:
            return {
                "success": False,
                "error": "Invalid channel_id",
                "message": f"Invalid channel ID: {channel_id}"
            }
        
        # Resolve message_id (short_id -> discord_id if needed)
        resolved_message_id = message_id
        short_id = None
        
        # Check if it's a short_id format (#5 or just 5)
        if message_id.startswith('#'):
            try:
                short_id = int(message_id[1:])
                from messaging.short_id_manager import get_short_id_manager
                short_id_manager = get_short_id_manager()
                resolved_message_id = await short_id_manager.get_discord_id(
                    server_id, channel_id, ai_name, short_id
                )
                if not resolved_message_id:
                    return {
                        "success": False,
                        "error": f"Short ID #{short_id} not found",
                        "message": f"Message #{short_id} not found in conversation history"
                    }
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid short_id format: {message_id}",
                    "message": "Short ID must be a number (e.g., #5)"
                }
        elif message_id.isdigit() and len(message_id) < 10:
            # Looks like a short_id without #
            try:
                short_id = int(message_id)
                from messaging.short_id_manager import get_short_id_manager
                short_id_manager = get_short_id_manager()
                resolved_message_id = await short_id_manager.get_discord_id(
                    server_id, channel_id, ai_name, short_id
                )
                if not resolved_message_id:
                    return {
                        "success": False,
                        "error": f"Short ID {short_id} not found",
                        "message": f"Message #{short_id} not found in conversation history"
                    }
            except ValueError:
                pass  # Not a valid short_id, treat as discord_id
        
        # Fetch the message
        try:
            from utils.message_cache import fetch_message_cached
            message = await fetch_message_cached(channel, resolved_message_id)
            
            if not message:
                return {
                    "success": False,
                    "error": "Message not found",
                    "message_id": message_id,
                    "message": f"Message {message_id} not found in channel"
                }
        except discord.NotFound:
            return {
                "success": False,
                "error": "Message not found",
                "message_id": message_id,
                "message": f"Message {message_id} not found (may have been deleted)"
            }
        except Exception as e:
            log.error(f"Error fetching message {resolved_message_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to fetch message: {str(e)}",
                "message_id": message_id
            }
        
        # Check if it's the bot's own message
        is_own_message = message.author.id == bot_client.user.id
        
        # Check permissions
        if not is_own_message:
            # Need manage_messages permission to delete other users' messages
            if not channel.permissions_for(channel.guild.me).manage_messages:
                return {
                    "success": False,
                    "error": "Missing permissions: manage_messages",
                    "required_permission": "manage_messages",
                    "message_id": message_id,
                    "message": "Cannot delete message: bot lacks 'manage_messages' permission. Ask a server admin to grant this permission."
                }
        
        # Delete the message
        try:
            await message.delete()
            
            # Invalidate cache
            from utils.message_cache import get_message_cache
            cache = get_message_cache()
            await cache.invalidate(channel_id, resolved_message_id)
            
            # If it's own message, update ResponseManager and history
            if is_own_message:
                # Update ResponseManager (remove from state)
                response_manager = bot_client.message_pipeline.response_manager
                state = response_manager.get_state(server_id, channel_id, ai_name)
                current_gen = state.get_current()
                
                # Check if this message is in the current generation
                if current_gen and resolved_message_id in current_gen.discord_ids:
                    # Clear the response manager state
                    response_manager.clear(server_id, channel_id, ai_name)
                
                # Update conversation history
                from AI.services.chat_service import get_service
                chat_service = get_service()
                
                current_chat_id = session.get("chat_id", "default")
                history = chat_service.get_ai_history(
                    server_id,
                    channel_id,
                    ai_name,
                    current_chat_id
                )
                
                # Remove the last assistant message from history
                if history:
                    updated_history = []
                    removed_assistant = False
                    for msg in reversed(history):
                        if msg["role"] == "assistant" and not removed_assistant:
                            removed_assistant = True
                            continue  # Skip this message
                        updated_history.insert(0, msg)
                    
                    await chat_service.set_ai_history(
                        server_id,
                        channel_id,
                        ai_name,
                        updated_history,
                        current_chat_id
                    )
            
            log.info(
                f"Message {message_id} deleted by AI {ai_name} "
                f"(own_message={is_own_message}, reason={reason})"
            )
            
            return {
                "success": True,
                "message_id": resolved_message_id,
                "short_id": short_id,
                "deleted_by": "bot",
                "was_own_message": is_own_message,
                "reason": reason,
                "message": f"Message {message_id} deleted successfully"
            }
            
        except discord.Forbidden:
            return {
                "success": False,
                "error": "Permission denied",
                "message_id": message_id,
                "message": "Cannot delete message: missing permissions (this shouldn't happen)"
            }
        except discord.NotFound:
            return {
                "success": False,
                "error": "Message not found",
                "message_id": message_id,
                "message": "Message was already deleted"
            }
        except Exception as e:
            log.error(f"Error deleting message {message_id}: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"Failed to delete message: {str(e)}",
                "message_id": message_id
            }
    
    except Exception as e:
        log.error(f"Error in delete_message: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Internal error: {str(e)}",
            "message_id": message_id
        }
