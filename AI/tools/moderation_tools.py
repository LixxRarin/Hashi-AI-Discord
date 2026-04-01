"""
Moderation Tools - Tools for server moderation actions

This module provides tools for the LLM to execute moderation actions:
- moderate_member: Timeout, ban, kick, unban, and remove timeout
"""

import logging
import discord
from typing import Dict, Any, Optional
from datetime import timedelta

log = logging.getLogger(__name__)


async def moderate_member(
    action: str,
    user_id: str,
    duration: Optional[int] = None,
    reason: Optional[str] = None,
    delete_message_days: Optional[int] = None,
    context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Execute moderation action on a server member.
    
    Supported actions:
    - timeout: Mute member temporarily (requires moderate_members permission)
    - ban: Ban member permanently (requires ban_members permission)
    - kick: Kick member from server (requires kick_members permission)
    - unban: Remove ban from user (requires ban_members permission)
    - remove_timeout: Remove timeout from member (requires moderate_members permission)
    
    Args:
        action: Moderation action to execute
        user_id: Discord user ID of target
        duration: Timeout duration in minutes (1-40320, required for timeout)
        reason: Optional reason for moderation action
        delete_message_days: Days of messages to delete for ban (0-7)
        context: Tool execution context
        
    Returns:
        Dict with success status and permission details
    """
    if context is None:
        return {"success": False, "error": "No context provided"}
    
    # Validate action
    valid_actions = ["timeout", "ban", "kick", "unban", "remove_timeout"]
    if action not in valid_actions:
        return {
            "success": False,
            "error": f"Invalid action: {action}",
            "valid_actions": valid_actions,
            "message": f"Action must be one of: {', '.join(valid_actions)}"
        }
    
    # Validate user_id
    if not user_id:
        return {
            "success": False,
            "error": "user_id is required",
            "message": "Please provide a user_id for the moderation action"
        }
    
    try:
        user_id_int = int(user_id)
    except ValueError:
        return {
            "success": False,
            "error": f"Invalid user_id: {user_id}",
            "message": "user_id must be a valid Discord user ID (numeric)"
        }
    
    # Validate duration for timeout
    if action == "timeout":
        if duration is None:
            return {
                "success": False,
                "error": "duration is required for timeout action",
                "message": "Please provide duration in minutes (1-40320)"
            }
        if not isinstance(duration, int) or duration < 1 or duration > 40320:
            return {
                "success": False,
                "error": f"Invalid duration: {duration}",
                "message": "Duration must be between 1 and 40320 minutes (28 days)"
            }
    
    # Validate delete_message_days for ban
    if action == "ban" and delete_message_days is not None:
        if not isinstance(delete_message_days, int) or delete_message_days < 0 or delete_message_days > 7:
            return {
                "success": False,
                "error": f"Invalid delete_message_days: {delete_message_days}",
                "message": "delete_message_days must be between 0 and 7"
            }
    
    try:
        # Extract context
        bot_client = context.get("bot_client")
        guild = context.get("guild")
        
        if not bot_client:
            return {
                "success": False,
                "error": "Missing bot_client in context",
                "message": "Internal error: bot_client not available"
            }
        
        if not guild:
            return {
                "success": False,
                "error": "Missing guild in context",
                "message": "Internal error: guild not available"
            }
        
        # Get bot member
        bot_member = guild.me
        if not bot_member:
            return {
                "success": False,
                "error": "Bot is not a member of this guild",
                "message": "Internal error: bot not found in guild"
            }
        
        # Check permissions based on action
        permission_map = {
            "timeout": ("moderate_members", bot_member.guild_permissions.moderate_members),
            "ban": ("ban_members", bot_member.guild_permissions.ban_members),
            "kick": ("kick_members", bot_member.guild_permissions.kick_members),
            "unban": ("ban_members", bot_member.guild_permissions.ban_members),
            "remove_timeout": ("moderate_members", bot_member.guild_permissions.moderate_members)
        }
        
        required_permission, has_permission = permission_map[action]
        
        if not has_permission:
            return {
                "success": False,
                "action": action,
                "error": f"Missing permissions: {required_permission}",
                "required_permission": required_permission,
                "message": f"Cannot {action} user: bot lacks '{required_permission}' permission. Ask a server admin to grant this permission."
            }
        
        # For unban, we don't need to fetch the member (they're not in the server)
        if action == "unban":
            try:
                # Get user object
                user = await bot_client.fetch_user(user_id_int)
                
                # Unban the user
                await guild.unban(user, reason=reason)
                
                log.info(f"User {user.name} ({user_id}) unbanned from guild {guild.id} (reason: {reason})")
                
                return {
                    "success": True,
                    "action": "unban",
                    "user_id": user_id,
                    "username": user.name,
                    "reason": reason,
                    "message": f"User {user.name} unbanned successfully"
                }
                
            except discord.NotFound:
                return {
                    "success": False,
                    "action": "unban",
                    "error": "User not found or not banned",
                    "user_id": user_id,
                    "message": f"User {user_id} not found or is not banned"
                }
            except discord.Forbidden:
                return {
                    "success": False,
                    "action": "unban",
                    "error": "Permission denied",
                    "user_id": user_id,
                    "message": "Cannot unban user: missing permissions (this shouldn't happen)"
                }
            except Exception as e:
                log.error(f"Error unbanning user {user_id}: {e}", exc_info=True)
                return {
                    "success": False,
                    "action": "unban",
                    "error": f"Failed to unban user: {str(e)}",
                    "user_id": user_id
                }
        
        # For other actions, fetch the member
        try:
            member = await guild.fetch_member(user_id_int)
        except discord.NotFound:
            return {
                "success": False,
                "action": action,
                "error": "Member not found",
                "user_id": user_id,
                "message": f"User {user_id} is not a member of this server"
            }
        except Exception as e:
            log.error(f"Error fetching member {user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "action": action,
                "error": f"Failed to fetch member: {str(e)}",
                "user_id": user_id
            }
        
        # Check if target is server owner
        if member.id == guild.owner_id:
            return {
                "success": False,
                "action": action,
                "error": "Cannot moderate server owner",
                "user_id": user_id,
                "message": f"Cannot {action} user: target is the server owner"
            }
        
        # Check role hierarchy (bot's top role must be higher than target's top role)
        if member.top_role >= bot_member.top_role:
            return {
                "success": False,
                "action": action,
                "error": "Cannot moderate user with higher or equal role",
                "user_id": user_id,
                "bot_top_role": bot_member.top_role.name,
                "target_top_role": member.top_role.name,
                "message": f"Cannot {action} user: target has higher or equal role than bot. Bot role must be above target's highest role."
            }
        
        # Execute the action
        try:
            if action == "timeout":
                # Calculate timeout duration
                timeout_duration = timedelta(minutes=duration)
                
                # Apply timeout
                await member.timeout(timeout_duration, reason=reason)
                
                log.info(
                    f"Member {member.name} ({user_id}) timed out for {duration} minutes "
                    f"in guild {guild.id} (reason: {reason})"
                )
                
                return {
                    "success": True,
                    "action": "timeout",
                    "user_id": user_id,
                    "username": member.name,
                    "display_name": member.display_name,
                    "duration_minutes": duration,
                    "reason": reason,
                    "message": f"User {member.display_name} timed out for {duration} minutes"
                }
            
            elif action == "ban":
                # Set default delete_message_days if not provided
                if delete_message_days is None:
                    delete_message_days = 0
                
                # Ban the member
                await member.ban(
                    reason=reason,
                    delete_message_days=delete_message_days
                )
                
                log.info(
                    f"Member {member.name} ({user_id}) banned from guild {guild.id} "
                    f"(reason: {reason}, delete_message_days: {delete_message_days})"
                )
                
                return {
                    "success": True,
                    "action": "ban",
                    "user_id": user_id,
                    "username": member.name,
                    "display_name": member.display_name,
                    "delete_message_days": delete_message_days,
                    "reason": reason,
                    "message": f"User {member.display_name} banned successfully"
                }
            
            elif action == "kick":
                # Kick the member
                await member.kick(reason=reason)
                
                log.info(
                    f"Member {member.name} ({user_id}) kicked from guild {guild.id} "
                    f"(reason: {reason})"
                )
                
                return {
                    "success": True,
                    "action": "kick",
                    "user_id": user_id,
                    "username": member.name,
                    "display_name": member.display_name,
                    "reason": reason,
                    "message": f"User {member.display_name} kicked successfully"
                }
            
            elif action == "remove_timeout":
                # Remove timeout by setting it to None
                await member.timeout(None, reason=reason)
                
                log.info(
                    f"Timeout removed from member {member.name} ({user_id}) "
                    f"in guild {guild.id} (reason: {reason})"
                )
                
                return {
                    "success": True,
                    "action": "remove_timeout",
                    "user_id": user_id,
                    "username": member.name,
                    "display_name": member.display_name,
                    "reason": reason,
                    "message": f"Timeout removed from user {member.display_name}"
                }
        
        except discord.Forbidden:
            return {
                "success": False,
                "action": action,
                "error": "Permission denied",
                "user_id": user_id,
                "message": f"Cannot {action} user: missing permissions (this shouldn't happen)"
            }
        except discord.HTTPException as e:
            log.error(f"HTTP error during {action} for user {user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "action": action,
                "error": f"Discord API error: {str(e)}",
                "user_id": user_id,
                "message": f"Failed to {action} user: {str(e)}"
            }
        except Exception as e:
            log.error(f"Error during {action} for user {user_id}: {e}", exc_info=True)
            return {
                "success": False,
                "action": action,
                "error": f"Failed to {action} user: {str(e)}",
                "user_id": user_id
            }
    
    except Exception as e:
        log.error(f"Error in moderate_member: {e}", exc_info=True)
        return {
            "success": False,
            "action": action,
            "error": f"Internal error: {str(e)}",
            "user_id": user_id
        }
