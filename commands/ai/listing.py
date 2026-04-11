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
from utils.media.thumbnails import get_thumbnail_url
from AI.core.registry import get_registry
from utils.discord.embed_builder import EmbedBuilder
from utils.discord.embed_constants import EmbedStyle, EmbedEmojis


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
        
        # Get thumbnails for each AI with character card using intelligent caching
        thumbnail_urls = {}  # ai_name -> thumbnail_url
        
        for ai_info in all_ais:
            ai_name = ai_info["name"]
            ai_data = ai_info["data"]
            
            # Only get thumbnail if AI has a character card
            if "character_card" in ai_data and ai_data["character_card"]:
                # Construct minimal session dict for get_thumbnail_url
                session = {
                    "character_card": ai_data.get("character_card", {}),
                    "character_card_name": ai_data.get("character_card_name")
                }
                
                thumbnail_url = await get_thumbnail_url(
                    interaction.channel,
                    session,
                    server_id
                )
                
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
                provider_display = provider
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
                description = f"{EmbedEmojis.CHARACTER} Character Card • {provider_icon} {provider_display} • {channel_mention}"
                
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
                
                # Character details field
                alt_greetings = card_data.get("alternate_greetings") or []
                total_greetings = 1 + len(alt_greetings)
                character_book = card_data.get("character_book")
                lorebook_entries = len(character_book.get("entries", [])) if character_book else 0
                
                details_value = f"• **Greetings:** {total_greetings} available"
                if lorebook_entries > 0:
                    details_value += f"\n• **Lorebook:** {lorebook_entries} entries"
                
                # Create embed with custom color
                builder = EmbedBuilder(EmbedStyle.CHARACTER)
                builder.embed.color = provider_color  # Override with provider color
                builder.set_title(ai_name, auto_emoji=False)
                builder.set_description(description)
                builder.add_field(
                    name="Configuration",
                    value=config_value,
                    inline=False,
                    emoji=EmbedEmojis.SETTINGS
                )
                builder.add_field(
                    name="Character Details",
                    value=details_value,
                    inline=False,
                    emoji="📚"
                )
                
                # Add thumbnail if available
                if ai_name in thumbnail_urls:
                    builder.set_thumbnail(thumbnail_urls[ai_name])
                
                embed = builder.build()
                
            else:
                # Regular AI
                description = f"{EmbedEmojis.LLM} Regular AI • {provider_icon} {provider_display} • {channel_mention}"
                
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
                
                # Create embed with custom color
                builder = EmbedBuilder(EmbedStyle.INFO)
                builder.embed.color = provider_color  # Override with provider color
                builder.set_title(ai_name, auto_emoji=False)
                builder.set_description(description)
                builder.add_field(
                    name="Configuration",
                    value=config_value,
                    inline=False,
                    emoji=EmbedEmojis.SETTINGS
                )
                
                embed = builder.build()
            
            # Set bot avatar as author
            bot_user = interaction.client.user
            if bot_user:
                embed.set_author(name=f"@{bot_user.name}", icon_url=bot_user.display_avatar.url)
            
            # Set footer with position and helpful tip
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
