"""
Server Tools - Tools for querying server/guild information

This module provides tools for the LLM to query information about
the Discord server (guild).
"""

import logging
from typing import Dict, Any, List, Optional
import discord

log = logging.getLogger(__name__)


async def get_server_info(
    query_type: str,
    include_fields: List[str] = None,
    context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Get information about the Discord server.
    
    Args:
        query_type: Type of query ("basic_info", "statistics", "features", "roles", "boost_status")
        include_fields: Fields to include in response
        context: Context information (guild, etc.)
        
    Returns:
        Dict with server information
    """
    if context is None:
        return {"error": "No context provided"}
    
    if include_fields is None:
        include_fields = ["all"]
    
    guild = context.get("guild")
    bot_client = context.get("bot_client")
    
    # Validate guild object
    if not guild or not hasattr(guild, 'name'):
        if bot_client:
            try:
                server_id = context.get("server_id")
                guild = bot_client.get_guild(int(server_id))
                if guild:
                    log.debug(f"Retrieved real guild from bot_client for server {server_id}")
            except Exception as e:
                log.error(f"Failed to get guild from bot_client: {e}")
        
        if not guild or not hasattr(guild, 'name'):
            return {
                "error": "Guild information not available in current context.",
                "server": None
            }
    
    try:
        # Process query based on type
        if query_type == "basic_info":
            server_info = {}
            
            if "all" in include_fields or "profile" in include_fields:
                server_info["id"] = str(guild.id)
                server_info["name"] = guild.name
                server_info["description"] = guild.description
                server_info["icon_url"] = str(guild.icon.url) if guild.icon else None
                server_info["banner_url"] = str(guild.banner.url) if guild.banner else None
                server_info["owner_id"] = str(guild.owner_id)
                server_info["owner_name"] = guild.owner.name if guild.owner else "Unknown"
                server_info["created_at"] = guild.created_at.isoformat() + "Z"
                server_info["verification_level"] = str(guild.verification_level)
                server_info["vanity_url_code"] = guild.vanity_url_code
            
            return {
                "server": server_info,
                "found": True
            }
        
        elif query_type == "statistics":
            stats = {}
            
            if "all" in include_fields or "stats" in include_fields:
                stats["member_count"] = guild.member_count
                stats["channel_count"] = len(guild.channels)
                stats["text_channel_count"] = len([c for c in guild.channels if isinstance(c, discord.TextChannel)])
                stats["voice_channel_count"] = len([c for c in guild.channels if isinstance(c, discord.VoiceChannel)])
                stats["category_count"] = len([c for c in guild.channels if isinstance(c, discord.CategoryChannel)])
                stats["role_count"] = len(guild.roles)
                stats["emoji_count"] = len(guild.emojis)
                stats["sticker_count"] = len(guild.stickers) if hasattr(guild, 'stickers') else 0
                
                # Count bots vs humans
                if hasattr(guild, 'members'):
                    bot_count = sum(1 for m in guild.members if m.bot)
                    stats["bot_count"] = bot_count
                    stats["human_count"] = guild.member_count - bot_count
            
            return {
                "statistics": stats,
                "server_name": guild.name
            }
        
        elif query_type == "features":
            features_info = {}
            
            if "all" in include_fields or "features" in include_fields:
                features_info["premium_tier"] = guild.premium_tier
                features_info["premium_subscription_count"] = guild.premium_subscription_count
                features_info["features"] = guild.features
                features_info["max_members"] = guild.max_members
                features_info["max_presences"] = guild.max_presences
                features_info["max_video_channel_users"] = guild.max_video_channel_users
                features_info["preferred_locale"] = str(guild.preferred_locale)
                features_info["mfa_level"] = str(guild.mfa_level)
                features_info["nsfw_level"] = str(guild.nsfw_level)
                
                # Parse features into readable format
                feature_descriptions = {
                    "COMMUNITY": "Community server",
                    "VERIFIED": "Verified server",
                    "PARTNERED": "Partnered server",
                    "DISCOVERABLE": "Discoverable in server discovery",
                    "VANITY_URL": "Has custom vanity URL",
                    "ANIMATED_ICON": "Can use animated icon",
                    "BANNER": "Has server banner",
                    "INVITE_SPLASH": "Has invite splash screen",
                    "WELCOME_SCREEN_ENABLED": "Welcome screen enabled",
                    "MEMBER_VERIFICATION_GATE_ENABLED": "Member verification enabled",
                    "PREVIEW_ENABLED": "Server preview enabled"
                }
                
                active_features = []
                for feature in guild.features:
                    active_features.append({
                        "code": feature,
                        "description": feature_descriptions.get(feature, feature)
                    })
                
                features_info["active_features"] = active_features
            
            return {
                "features": features_info,
                "server_name": guild.name
            }
        
        elif query_type == "roles":
            roles_list = []
            
            for role in guild.roles:
                if role.name == "@everyone":
                    continue
                
                role_info = {
                    "id": str(role.id),
                    "name": role.name,
                    "color": str(role.color) if role.color != discord.Color.default() else None,
                    "position": role.position,
                    "mentionable": role.mentionable,
                    "hoist": role.hoist,
                    "managed": role.managed,
                    "member_count": len(role.members) if hasattr(role, 'members') else None
                }
                
                if "all" in include_fields:
                    # Include permissions for detailed view
                    perms = role.permissions
                    role_info["permissions"] = {
                        "administrator": perms.administrator,
                        "manage_guild": perms.manage_guild,
                        "manage_roles": perms.manage_roles,
                        "manage_channels": perms.manage_channels,
                        "kick_members": perms.kick_members,
                        "ban_members": perms.ban_members,
                        "manage_messages": perms.manage_messages,
                        "mention_everyone": perms.mention_everyone
                    }
                
                roles_list.append(role_info)
            
            # Sort by position (highest first)
            roles_list.sort(key=lambda r: r["position"], reverse=True)
            
            return {
                "roles": roles_list,
                "total_count": len(roles_list),
                "server_name": guild.name
            }
        
        elif query_type == "boost_status":
            boost_info = {}
            
            boost_info["premium_tier"] = guild.premium_tier
            boost_info["premium_subscription_count"] = guild.premium_subscription_count
            boost_info["server_name"] = guild.name
            
            # Boost tier benefits
            tier_benefits = {
                0: "No boosts - Basic features",
                1: "Level 1 (2 boosts) - 128 Kbps audio, custom server invite background, animated server icon",
                2: "Level 2 (7 boosts) - 256 Kbps audio, server banner, 50 MB upload limit, custom stickers",
                3: "Level 3 (14 boosts) - 384 Kbps audio, vanity URL, 100 MB upload limit, animated server banner"
            }
            
            boost_info["current_tier_benefits"] = tier_benefits.get(guild.premium_tier, "Unknown")
            
            # Calculate boosts needed for next tier
            boosts_needed = {
                0: 2 - guild.premium_subscription_count,
                1: 7 - guild.premium_subscription_count,
                2: 14 - guild.premium_subscription_count,
                3: 0  # Max tier
            }
            
            if guild.premium_tier < 3:
                boost_info["boosts_to_next_tier"] = max(0, boosts_needed.get(guild.premium_tier, 0))
                boost_info["next_tier"] = guild.premium_tier + 1
            else:
                boost_info["boosts_to_next_tier"] = 0
                boost_info["next_tier"] = None
                boost_info["message"] = "Server is at maximum boost tier!"
            
            # Get list of boosters if available
            if hasattr(guild, 'premium_subscribers'):
                boosters = []
                for member in guild.premium_subscribers[:10]:  # Limit to 10
                    boosters.append({
                        "username": member.name,
                        "display_name": member.display_name,
                        "id": str(member.id)
                    })
                boost_info["recent_boosters"] = boosters
                boost_info["showing_boosters"] = len(boosters)
            
            return {
                "boost_status": boost_info
            }
        
        else:
            return {"error": f"Unknown query_type: {query_type}"}
    
    except Exception as e:
        log.error(f"Error in get_server_info: {e}", exc_info=True)
        return {
            "error": f"Failed to retrieve server information: {str(e)}",
            "server": None
        }
