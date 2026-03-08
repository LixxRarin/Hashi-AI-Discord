"""
AI listing commands.

Provides commands to list and display information about configured AIs.
"""
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from typing import Dict, List, Optional

import utils.func as func
from utils.pagination import PaginatedView
from utils.thumbnail_helper import upload_thumbnail_to_discord
from AI.provider_registry import get_registry


class AIListing(commands.Cog):
    """Commands for listing AIs in the server."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="list_ais", description="List all AIs and Character Cards configured in this server")
    @app_commands.default_permissions(administrator=True)
    async def list_ais(self, interaction: discord.Interaction):
        """List all AIs configured in the current server, grouped by provider with pagination."""
        await interaction.response.defer(ephemeral=True)
        server_id = str(interaction.guild.id)
        
        all_server_data = func.session_cache.get(server_id, {}).get("channels", {})
        
        if not all_server_data:
            await interaction.followup.send(
                "❌ No AIs configured in this server.",
                ephemeral=True
            )
            return
        
        # Collect all AIs and group by provider
        ais_by_provider: Dict[str, List[dict]] = {}
        
        for channel_id_str, channel_data in all_server_data.items():
            if not channel_data or not isinstance(channel_data, dict):
                continue
                
            channel_obj = interaction.guild.get_channel(int(channel_id_str))
            channel_name = channel_obj.name if channel_obj else f"deleted-{channel_id_str[:8]}"
            channel_mention = channel_obj.mention if channel_obj else f"Deleted Channel"

            for ai_name, ai_data in channel_data.items():
                provider = ai_data.get("provider", "openai").lower()
                
                ai_info = {
                    "name": ai_name,
                    "data": ai_data,
                    "channel_name": channel_name,
                    "channel_mention": channel_mention,
                    "channel_id": channel_id_str,
                    "provider": provider
                }
                
                if provider not in ais_by_provider:
                    ais_by_provider[provider] = []
                ais_by_provider[provider].append(ai_info)
        
        # Get registry for provider metadata
        registry = get_registry()
        
        # Flatten all AIs into a single list for unified pagination
        all_ais = []
        for provider, ais in sorted(ais_by_provider.items()):
            all_ais.extend(ais)
        
        # Upload thumbnails to Discord CDN for each AI with character card
        thumbnail_urls = {}  # ai_name -> thumbnail_url
        
        for ai_info in all_ais:
            ai_name = ai_info["name"]
            cache_path = ai_info["data"].get("character_card", {}).get("cache_path")
            if cache_path and Path(cache_path).suffix.lower() == '.png' and Path(cache_path).exists():
                thumbnail_url = await upload_thumbnail_to_discord(interaction.channel, cache_path, server_id=server_id)
                if thumbnail_url:
                    thumbnail_urls[ai_name] = thumbnail_url
        
        # Create embeds - one per AI
        embeds = []
        total_ais = len(all_ais)
        
        for idx, ai_info in enumerate(all_ais):
            ai_name = ai_info["name"]
            ai_data = ai_info["data"]
            provider = ai_info["provider"]
            channel_mention = ai_info["channel_mention"]
            
            # Get provider metadata
            try:
                provider_meta = registry.get_metadata(provider)
                provider_display = provider_meta.display_name
                provider_icon = provider_meta.icon
                provider_color = getattr(discord.Color, provider_meta.color, discord.Color.blue)()
            except ValueError:
                provider_display = provider.upper()
                provider_icon = "🔵"
                provider_color = discord.Color.blue()
            
            # Check if it's a character card AI
            card_data = ai_data.get("character_card", {}).get("data", {})
            is_character = bool(card_data)
            
            if is_character:
                # Character Card AI
                char_name = card_data.get("name", ai_name)
                nickname = card_data.get("nickname")
                display_name = nickname or char_name
                creator = card_data.get("creator", "Unknown")
                
                # Build description
                description = f"🎭 Character Card • {provider_icon} {provider_display} • {channel_mention}"
                
                # Create embed
                embed = discord.Embed(
                    title=ai_name,
                    description=description,
                    color=provider_color
                )
                
                # Get model info
                api_connection = ai_data.get("api_connection")
                model_info = "Unknown"
                connection_name = api_connection if api_connection else "Legacy"
                
                if api_connection:
                    connection = func.get_api_connection(server_id, api_connection)
                    if connection:
                        model_info = connection.get("model", "Unknown")
                
                # Main configuration field
                config_value = f"• **Character:** {display_name}\n"
                if creator != "Unknown":
                    config_value += f"• **Creator:** {creator}\n"
                config_value += f"• **Model:** `{model_info}`\n"
                config_value += f"• **Connection:** `{connection_name}`"
                
                embed.add_field(
                    name="⚙️ Configuration",
                    value=config_value,
                    inline=False
                )
                
                # Character details field
                alt_greetings = card_data.get("alternate_greetings") or []
                total_greetings = 1 + len(alt_greetings)
                character_book = card_data.get("character_book")
                lorebook_entries = len(character_book.get("entries", [])) if character_book else 0
                
                details_value = f"• **Greetings:** {total_greetings} available"
                if lorebook_entries > 0:
                    details_value += f"\n• **Lorebook:** {lorebook_entries} entries"
                
                embed.add_field(
                    name="📚 Character Details",
                    value=details_value,
                    inline=False
                )
                
            else:
                # Regular AI
                description = f"🤖 Regular AI • {provider_icon} {provider_display} • {channel_mention}"
                
                # Create embed
                embed = discord.Embed(
                    title=ai_name,
                    description=description,
                    color=provider_color
                )
                
                # Get model info
                api_connection = ai_data.get("api_connection")
                connection_name = api_connection if api_connection else "Legacy"
                
                if api_connection:
                    connection = func.get_api_connection(server_id, api_connection)
                    if connection:
                        model = connection.get("model", "Unknown")
                        config_value = f"• **Model:** `{model}`\n"
                        config_value += f"• **Connection:** `{connection_name}`"
                    else:
                        config_value = f"• **Connection:** `{connection_name}` ⚠️ Not Found"
                else:
                    # Legacy
                    model = ai_data.get("model", "Unknown")
                    config_value = f"• **Model:** `{model}`\n"
                    config_value += f"• **Connection:** Legacy (direct config)"
                
                embed.add_field(
                    name="⚙️ Configuration",
                    value=config_value,
                    inline=False
                )
            
            # Add thumbnail if available
            if ai_name in thumbnail_urls:
                embed.set_thumbnail(url=thumbnail_urls[ai_name])
            
            # Footer with position and helpful tip
            embed.set_footer(text=f"AI {idx + 1}/{total_ais} • Use /character_info for details")
            
            embeds.append(embed)
        
        # Send with pagination if multiple embeds
        if len(embeds) == 0:
            await interaction.followup.send(
                "❌ No AIs configured in this server.",
                ephemeral=True
            )
        elif len(embeds) == 1:
            # Single embed, send directly
            await interaction.followup.send(embed=embeds[0], ephemeral=True)
        else:
            # Multiple embeds, use pagination (thumbnails work via CDN URLs)
            view = PaginatedView(embeds, user_id=interaction.user.id)
            message = await interaction.followup.send(
                embed=view.get_current_embed(),
                view=view,
                ephemeral=True
            )
            view.message = message


async def setup(bot):
    """Load the AIListing cog."""
    await bot.add_cog(AIListing(bot))
