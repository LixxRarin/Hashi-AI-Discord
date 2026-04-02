"""
Interactive Config Command - Simplified

Single command to configure AI settings through interactive UI.
Uses fixed categories for clear organization.
"""

import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
from utils.config_ui_components import ConfigCategorySelectView, create_category_selection_embed
from commands.shared.autocomplete import AutocompleteHelpers


class ConfigInteractiveCommands(commands.Cog):
    """
    Simplified interactive configuration system.
    
    Features:
    - Single /config command
    - Fixed, well-organized categories
    - Simple navigation: category → config → edit
    """
    
    def __init__(self, bot):
        self.bot = bot
    
    async def ai_name_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for AI names."""
        return await AutocompleteHelpers.ai_name_all(interaction, current)
    
    @app_commands.command(
        name="config",
        description="Configure AI settings interactively"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(ai_name="Name of the AI to configure")
    @app_commands.autocomplete(ai_name=ai_name_autocomplete)
    async def config(
        self,
        interaction: discord.Interaction,
        ai_name: str
    ):
        """
        Interactive configuration command.
        
        Opens a UI for configuring AI settings organized by category.
        """
        server_id = str(interaction.guild.id)
        
        # Find AI
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.response.send_message(
                f"❌ AI '{ai_name}' not found in this server.",
                ephemeral=True
            )
            return
        
        found_channel_id, session = found_ai_data
        
        if session is None:
            await interaction.response.send_message(
                f"❌ AI '{ai_name}' session data is invalid or corrupted.",
                ephemeral=True
            )
            return
        
        # Create initial embed using standardized helper
        embed = create_category_selection_embed(ai_name)
        
        # Create view
        view = ConfigCategorySelectView(
            ai_name=ai_name,
            server_id=server_id,
            channel_id=found_channel_id,
            session=session
        )
        
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(ConfigInteractiveCommands(bot))
