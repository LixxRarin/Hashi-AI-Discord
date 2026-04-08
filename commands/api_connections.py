"""
API Connections Command - Interactive UI

Single unified command for managing API connections.
Replaces: /new_api, /api_config, /list_apis, /remove_api, /show_api
"""

import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
from utils.discord.api_ui import (
    APIConnectionListView,
    create_connection_list_embed
)


class APIConnections(commands.Cog):
    """Interactive API connection management."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="api_connections",
        description="Manage API connections interactively"
    )
    @app_commands.default_permissions(administrator=True)
    async def api_connections(self, interaction: discord.Interaction):
        """
        Interactive API connection management.
        
        Provides a unified interface for:
        - Creating new API connections
        - Editing existing connections
        - Removing connections
        - Viewing connection details
        """
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        guild_name = interaction.guild.name
        user_id = interaction.user.id
        
        # Create main view with pagination
        view = APIConnectionListView(
            server_id=server_id,
            guild_name=guild_name,
            user_id=user_id,
            page=0
        )
        
        # Create embed for first page
        embed = create_connection_list_embed(
            server_id=server_id,
            guild_name=guild_name,
            page=0,
            per_page=5
        )
        
        await interaction.followup.send(
            embed=embed,
            view=view,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(APIConnections(bot))
