"""
User Tools - Tools for querying user information

This module provides tools for the LLM to query information about
Discord users in the server with flexible search capabilities.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
import discord

log = logging.getLogger(__name__)


def _rank_user_match(field_value: str, query: str) -> int:
    """
    Calculate relevance score for a field match.
    
    Args:
        field_value: The field to match against (username, display_name, etc.)
        query: The search query (already lowercased)
        
    Returns:
        Score: 100 (exact), 75 (starts with), 50 (contains), 0 (no match)
    """
    field_lower = field_value.lower()
    
    if field_lower == query:
        return 100  # Exact match
    elif field_lower.startswith(query):
        return 75   # Starts with
    elif query in field_lower:
        return 50   # Contains
    else:
        return 0    # No match


def _search_users_by_username(guild: discord.Guild, query: str, limit: int) -> List[Tuple[discord.Member, int, str]]:
    """
    Search users by username with ranking.
    
    Args:
        guild: Discord guild object
        query: Search query (case-insensitive)
        limit: Maximum number of results
        
    Returns:
        List of (member, score, match_field) tuples sorted by score descending
    """
    query_lower = query.lower()
    results = []
    
    for member in guild.members:
        score = _rank_user_match(member.name, query_lower)
        if score > 0:
            results.append((member, score, "username"))
    
    # Sort by score descending, then by username
    results.sort(key=lambda x: (-x[1], x[0].name.lower()))
    
    return results[:limit]


def _search_users_by_display_name(guild: discord.Guild, query: str, limit: int) -> List[Tuple[discord.Member, int, str]]:
    """
    Search users by display name with ranking.
    
    Args:
        guild: Discord guild object
        query: Search query (case-insensitive)
        limit: Maximum number of results
        
    Returns:
        List of (member, score, match_field) tuples sorted by score descending
    """
    query_lower = query.lower()
    results = []
    
    for member in guild.members:
        score = _rank_user_match(member.display_name, query_lower)
        if score > 0:
            results.append((member, score, "display_name"))
    
    # Sort by score descending, then by display name
    results.sort(key=lambda x: (-x[1], x[0].display_name.lower()))
    
    return results[:limit]


def _search_users_any(guild: discord.Guild, query: str, limit: int) -> List[Tuple[discord.Member, int, str]]:
    """
    Search users across username, display name, and nickname with ranking.
    
    Args:
        guild: Discord guild object
        query: Search query (case-insensitive)
        limit: Maximum number of results
        
    Returns:
        List of (member, score, match_field) tuples sorted by score descending
    """
    query_lower = query.lower()
    results_dict = {}  # Use dict to avoid duplicates, key is member.id
    
    for member in guild.members:
        best_score = 0
        best_field = ""
        
        # Check username
        username_score = _rank_user_match(member.name, query_lower)
        if username_score > best_score:
            best_score = username_score
            best_field = "username"
        
        # Check display name
        display_score = _rank_user_match(member.display_name, query_lower)
        if display_score > best_score:
            best_score = display_score
            best_field = "display_name"
        
        # Check nickname (if different from display_name)
        if member.nick:
            nick_score = _rank_user_match(member.nick, query_lower)
            # Add bonus for nickname matches
            if nick_score > 0:
                nick_score += 10
            if nick_score > best_score:
                best_score = nick_score
                best_field = "nickname"
        
        # Add to results if any match found
        if best_score > 0:
            results_dict[member.id] = (member, best_score, best_field)
    
    # Convert to list and sort
    results = list(results_dict.values())
    results.sort(key=lambda x: (-x[1], x[0].name.lower()))
    
    return results[:limit]


def _format_user_info(member: discord.Member, include_fields: List[str]) -> Dict[str, Any]:
    """
    Format user information based on include_fields.
    
    Args:
        member: Discord member object
        include_fields: List of fields to include
        
    Returns:
        Dict with formatted user information
    """
    user_info = {}
    
    if "all" in include_fields or "profile" in include_fields:
        user_info["user_id"] = str(member.id)
        user_info["username"] = member.name
        user_info["display_name"] = member.display_name
        user_info["discriminator"] = member.discriminator
        user_info["avatar_url"] = str(member.avatar.url) if member.avatar else None
        user_info["bot"] = member.bot
        user_info["system"] = member.system if hasattr(member, 'system') else False
        
        # Get user's custom status if available
        if member.activity:
            if isinstance(member.activity, discord.CustomActivity):
                user_info["custom_status"] = member.activity.name
            elif isinstance(member.activity, discord.Activity):
                user_info["activity"] = {
                    "type": str(member.activity.type),
                    "name": member.activity.name
                }
    
    if "all" in include_fields or "roles" in include_fields:
        # Get roles (excluding @everyone)
        roles = [role.name for role in member.roles if role.name != "@everyone"]
        user_info["roles"] = roles
        user_info["top_role"] = member.top_role.name if member.top_role.name != "@everyone" else None
        user_info["role_color"] = str(member.color) if member.color != discord.Color.default() else None
    
    if "all" in include_fields or "join_date" in include_fields:
        if member.joined_at:
            user_info["joined_at"] = member.joined_at.isoformat() + "Z"
        
        # Account creation date
        user_info["created_at"] = member.created_at.isoformat() + "Z"
    
    if "all" in include_fields or "activity" in include_fields:
        # Current status
        user_info["status"] = str(member.status)
        
        # Activities
        if member.activities:
            activities = []
            for activity in member.activities:
                if isinstance(activity, discord.CustomActivity):
                    activities.append({
                        "type": "custom",
                        "name": activity.name
                    })
                elif isinstance(activity, discord.Spotify):
                    activities.append({
                        "type": "spotify",
                        "title": activity.title,
                        "artist": activity.artist,
                        "album": activity.album
                    })
                elif isinstance(activity, discord.Game):
                    activities.append({
                        "type": "game",
                        "name": activity.name
                    })
                elif isinstance(activity, discord.Streaming):
                    activities.append({
                        "type": "streaming",
                        "name": activity.name,
                        "url": activity.url
                    })
                else:
                    activities.append({
                        "type": str(activity.type),
                        "name": activity.name
                    })
            
            user_info["activities"] = activities
    
    # Additional server-specific info
    if "all" in include_fields:
        user_info["nickname"] = member.nick
        user_info["premium_since"] = member.premium_since.isoformat() + "Z" if member.premium_since else None
        user_info["pending"] = member.pending if hasattr(member, 'pending') else False
        
        # Permissions
        permissions = member.guild_permissions
        user_info["is_admin"] = permissions.administrator
        user_info["is_moderator"] = permissions.kick_members or permissions.ban_members or permissions.manage_messages
    
    return user_info


def _format_user_basic(member: discord.Member) -> Dict[str, Any]:
    """
    Format basic user information for list operations.
    
    Args:
        member: Discord member object
        
    Returns:
        Dict with minimal user information
    """
    return {
        "user_id": str(member.id),
        "username": member.name,
        "display_name": member.display_name,
        "bot": member.bot
    }


async def get_user_info(
    user_identifier: Optional[str] = None,
    query_type: str = "by_exact_name",
    limit: int = 10,
    include_bots: bool = True,
    include_fields: List[str] = None,
    context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Get information about Discord user(s) with flexible search capabilities.
    
    Args:
        user_identifier: User ID, @mention, username, or search term (optional for list_all)
        query_type: Type of query - "by_id", "by_exact_name", "search_username",
                   "search_display_name", "search_any", "list_all" (default: "by_exact_name")
        limit: Maximum number of results (default: 10, max: 50 for searches, 100 for list_all)
        include_bots: Include bot users in list_all results (default: True)
        include_fields: Fields to include in response (not used for list_all)
        context: Context information (guild, etc.)
        
    Returns:
        Dict with user information or search results
    """
    if context is None:
        return {"error": "No context provided"}
    
    if include_fields is None:
        include_fields = ["all"]
    
    # Adjust default limit for list_all
    if query_type == "list_all" and limit == 10:
        limit = 50  # Better default for listing all members
    
    # Validate and cap limit
    if query_type == "list_all":
        limit = max(1, min(limit, 100))
    else:
        limit = max(1, min(limit, 50))
    
    # Get guild from context
    guild = context.get("guild")
    bot_client = context.get("bot_client")
    
    # Validate guild object - try to get real guild if needed
    if not guild or not hasattr(guild, 'members'):
        if bot_client:
            try:
                server_id = context.get("server_id")
                guild = bot_client.get_guild(int(server_id))
                if guild:
                    log.debug(f"Retrieved real guild from bot_client for server {server_id}")
            except Exception as e:
                log.error(f"Failed to get guild from bot_client: {e}")
        
        if not guild or not hasattr(guild, 'members'):
            return {
                "error": "Guild information not available in current context.",
                "user": None
            }
    
    try:
        # Handle list_all query type
        if query_type == "list_all":
            # Validate and cap limit (max 100 for list_all)
            limit = max(1, min(limit, 100))
            
            # Collect and filter members
            members = []
            for member in guild.members:
                # Filter bots if requested
                if not include_bots and member.bot:
                    continue
                members.append(member)
            
            # Sort alphabetically by username
            members.sort(key=lambda m: m.name.lower())
            
            # Get total count before applying limit
            total_count = len(members)
            
            # Apply limit
            members = members[:limit]
            
            return {
                "users": [_format_user_basic(m) for m in members],
                "total_members": total_count,
                "returned_count": len(members),
                "has_more": total_count > limit,
                "query_type": "list_all",
                "filters": {
                    "include_bots": include_bots,
                    "limit": limit
                }
            }
        
        # Validate user_identifier for non-list_all queries
        if user_identifier is None:
            return {
                "error": f"user_identifier is required for query_type '{query_type}'",
                "user": None
            }
        
        # Handle search query types
        if query_type == "search_username":
            results = _search_users_by_username(guild, user_identifier, limit)
            
            if not results:
                return {
                    "error": f"No users found with username matching '{user_identifier}'",
                    "users": [],
                    "search_term": user_identifier,
                    "found_count": 0
                }
            
            return {
                "users": [
                    {
                        "user": _format_user_info(member, include_fields),
                        "match_score": score,
                        "match_field": field
                    }
                    for member, score, field in results
                ],
                "search_term": user_identifier,
                "found_count": len(results),
                "query_type": query_type
            }
        
        elif query_type == "search_display_name":
            results = _search_users_by_display_name(guild, user_identifier, limit)
            
            if not results:
                return {
                    "error": f"No users found with display name matching '{user_identifier}'",
                    "users": [],
                    "search_term": user_identifier,
                    "found_count": 0
                }
            
            return {
                "users": [
                    {
                        "user": _format_user_info(member, include_fields),
                        "match_score": score,
                        "match_field": field
                    }
                    for member, score, field in results
                ],
                "search_term": user_identifier,
                "found_count": len(results),
                "query_type": query_type
            }
        
        elif query_type == "search_any":
            results = _search_users_any(guild, user_identifier, limit)
            
            if not results:
                return {
                    "error": f"No users found matching '{user_identifier}'",
                    "users": [],
                    "search_term": user_identifier,
                    "found_count": 0
                }
            
            return {
                "users": [
                    {
                        "user": _format_user_info(member, include_fields),
                        "match_score": score,
                        "match_field": field
                    }
                    for member, score, field in results
                ],
                "search_term": user_identifier,
                "found_count": len(results),
                "query_type": query_type
            }
        
        # Handle direct lookup query types (by_id, by_exact_name)
        member = None
        user_id = None
        
        # Try to extract user ID from mention format (<@123456789> or @username)
        if user_identifier.startswith("<@") and user_identifier.endswith(">"):
            user_id_str = user_identifier[2:-1]
            if user_id_str.startswith("!"):
                user_id_str = user_id_str[1:]
            
            try:
                user_id = int(user_id_str)
            except ValueError:
                pass
        elif user_identifier.startswith("@"):
            # Remove @ prefix for username search
            user_identifier = user_identifier[1:]
        
        # For by_id query type, try as direct user ID
        if query_type == "by_id" or user_id is None:
            try:
                user_id = int(user_identifier)
            except ValueError:
                if query_type == "by_id":
                    return {
                        "error": f"Invalid user ID: {user_identifier}",
                        "user": None
                    }
        
        # If we have a user ID, try to get the member
        if user_id is not None:
            # Try from cache first
            member = guild.get_member(user_id)
            
            # If not in cache, fetch from API
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.NotFound:
                    pass
                except discord.HTTPException as e:
                    log.warning(f"Failed to fetch member {user_id}: {e}")
        
        # For by_exact_name, try as username or display name if we still don't have a member
        if member is None and query_type == "by_exact_name":
            # Search by username (case-insensitive)
            for m in guild.members:
                if m.name.lower() == user_identifier.lower():
                    member = m
                    break
            
            # Search by display name if not found
            if member is None:
                for m in guild.members:
                    if m.display_name.lower() == user_identifier.lower():
                        member = m
                        break
        
        if member is None:
            return {
                "error": f"User '{user_identifier}' not found in server",
                "user": None
            }
        
        return {
            "user": _format_user_info(member, include_fields),
            "found": True
        }
    
    except Exception as e:
        log.error(f"Error in get_user_info: {e}", exc_info=True)
        return {
            "error": f"Failed to retrieve user information: {str(e)}",
            "user": None
        }
