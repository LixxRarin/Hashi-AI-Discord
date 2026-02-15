"""
AI listing commands.

Provides commands to list and display information about configured AIs.
"""
import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func


class AIListing(commands.Cog):
    """Commands for listing AIs in the server."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="list_ais", description="List all AIs and Character Cards configured in this server")
    @app_commands.default_permissions(administrator=True)
    async def list_ais(self, interaction: discord.Interaction):
        """List all AIs configured in the current server with clean, organized display."""
        await interaction.response.defer(ephemeral=True)
        server_id = str(interaction.guild.id)
        
        all_server_data = func.session_cache.get(server_id, {}).get("channels", {})
        
        if not all_server_data:
            await interaction.followup.send(
                "❌ No AIs configured in this server.",
                ephemeral=True
            )
            return
        
        # Separate AIs with and without character cards
        character_ais = []
        regular_ais = []
        
        for channel_id_str, channel_data in all_server_data.items():
            # Skip if channel_data is None or not a dictionary
            if not channel_data or not isinstance(channel_data, dict):
                continue
                
            channel_obj = interaction.guild.get_channel(int(channel_id_str))
            channel_name = channel_obj.name if channel_obj else f"deleted-{channel_id_str[:8]}"
            channel_mention = channel_obj.mention if channel_obj else f"Deleted Channel"

            for ai_name, ai_data in channel_data.items():
                ai_info = {
                    "name": ai_name,
                    "data": ai_data,
                    "channel_name": channel_name,
                    "channel_mention": channel_mention,
                    "channel_id": channel_id_str
                }
                
                if ai_data.get("character_card", {}).get("data"):
                    character_ais.append(ai_info)
                else:
                    regular_ais.append(ai_info)
        
        # Create embed
        total_ais = len(character_ais) + len(regular_ais)
        embed = discord.Embed(
            title=f"🤖 AI Overview - {interaction.guild.name}",
            description=f"**Total:** {total_ais} AI(s) • **Characters:** {len(character_ais)} • **Regular:** {len(regular_ais)}",
            color=discord.Color.purple()
        )
        
        # Add Character Card AIs section
        if character_ais:
            for ai_info in character_ais:
                ai_name = ai_info["name"]
                ai_data = ai_info["data"]
                card_data = ai_data.get("character_card", {}).get("data", {})
                
                # Get character info
                char_name = card_data.get("name", ai_name)
                nickname = card_data.get("nickname")
                display_name = nickname or char_name
                creator = card_data.get("creator", "Unknown")
                
                # Get greeting and lorebook info
                alt_greetings = card_data.get("alternate_greetings") or []
                total_greetings = 1 + len(alt_greetings)
                character_book = card_data.get("character_book")
                lorebook_entries = len(character_book.get("entries", [])) if character_book else 0
                
                # Get provider and model
                provider = ai_data.get("provider", "openai").upper()
                api_connection = ai_data.get("api_connection")
                model_info = "Unknown"
                if api_connection:
                    connection = func.get_api_connection(server_id, api_connection)
                    if connection:
                        model_info = connection.get("model", "Unknown")
                
                # Build compact field value
                field_value = f"**Character:** {display_name}"
                if creator != "Unknown":
                    field_value += f" • **By:** {creator}"
                field_value += f"\n**Channel:** #{ai_info['channel_name']}"
                field_value += f" • **Provider:** {provider}"
                
                # Add optional info on second line
                extras = []
                if total_greetings > 1:
                    extras.append(f"{total_greetings} greetings")
                if lorebook_entries > 0:
                    extras.append(f"{lorebook_entries} lorebook entries")
                if extras:
                    field_value += f"\n*{' • '.join(extras)}*"
                
                embed.add_field(
                    name=f"🎭 {ai_name}",
                    value=field_value,
                    inline=True
                )
        
        # Add Regular AIs section
        if regular_ais:
            # Add separator if there are character AIs
            if character_ais:
                embed.add_field(name="\u200b", value="\u200b", inline=False)
            
            for ai_info in regular_ais:
                ai_name = ai_info["name"]
                ai_data = ai_info["data"]
                
                # Get provider and model
                provider = ai_data.get("provider", "openai").upper()
                api_connection = ai_data.get("api_connection")
                
                if api_connection:
                    connection = func.get_api_connection(server_id, api_connection)
                    if connection:
                        model = connection.get("model", "Unknown")
                        field_value = f"**Provider:** {provider}\n"
                        field_value += f"**Channel:** #{ai_info['channel_name']}\n"
                        field_value += f"**Model:** `{model}`"
                    else:
                        field_value = f"**Provider:** {provider}\n"
                        field_value += f"**Channel:** #{ai_info['channel_name']}\n"
                        field_value += f"**Connection:** ⚠️ Not Found"
                else:
                    # Legacy
                    model = ai_data.get("model", "Unknown")
                    field_value = f"**Provider:** {provider}\n"
                    field_value += f"**Channel:** #{ai_info['channel_name']}\n"
                    field_value += f"**Model:** `{model}`"
                
                embed.add_field(
                    name=f"🤖 {ai_name}",
                    value=field_value,
                    inline=True
                )
        
        embed.set_footer(text="💡 Use /character_info <ai_name> for detailed Character Card information")
        
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    """Load the AIListing cog."""
    await bot.add_cog(AIListing(bot))
