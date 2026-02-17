"""
AI history management commands.

Provides commands to manage conversation history for AIs.
"""
import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
from AI.chat_service import get_service
from commands.shared.autocomplete import AutocompleteHelpers


class HistoryManager(commands.Cog):
    """Commands for managing AI conversation history."""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def ai_name_all_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for all AI names."""
        return await AutocompleteHelpers.ai_name_all(interaction, current)
    
    @app_commands.command(name="clear_history", description="Clear conversation history for an AI")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(ai_name="Name of the AI to clear history for")
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def clear_history(self, interaction: discord.Interaction, ai_name: str):
        """Clear conversation history for an AI."""
        await interaction.response.defer(ephemeral=True)
        server_id = str(interaction.guild.id)
        
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        
        if not found_ai_data:
            await interaction.followup.send(
                f"❌ AI '{ai_name}' not found in this server.",
                ephemeral=True
            )
            return
        
        found_channel_id, session = found_ai_data
        
        # Get current chat_id from session
        current_chat_id = session.get("chat_id", "default")
        
        # Check if there's existing conversation history
        service = get_service()
        existing_history = service.get_ai_history(server_id, found_channel_id, ai_name, current_chat_id)
        
        # If there's no history or only 1 message, just inform the user
        if not existing_history or len(existing_history) <= 1:
            await interaction.followup.send(
                f"⚠️ No conversation history found for AI '{ai_name}' (or only greeting message exists).",
                ephemeral=True
            )
            return
        
        # If there's existing history, ask for confirmation
        confirm_msg = await interaction.channel.send(
            f"⚠️ **WARNING: Clear History Confirmation** (requested by {interaction.user.mention})\n\n"
            f"**AI:** {ai_name}\n"
            f"**Channel:** <#{found_channel_id}>\n"
            f"**Messages in history:** {len(existing_history)}\n\n"
            f"⚠️ **This will DELETE ALL CONVERSATION HISTORY!**\n"
            f"All RP/conversation progress will be permanently lost.\n\n"
            f"**React with ✅ to confirm or ❌ to cancel.**"
        )
        
        # Send ephemeral acknowledgment
        await interaction.followup.send(
            "✅ Confirmation message sent. Please react to confirm or cancel.",
            ephemeral=True
        )
        
        # Add reactions
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")
        
        # Wait for reaction
        def check(reaction, user):
            return (
                user == interaction.user
                and reaction.message.id == confirm_msg.id
                and str(reaction.emoji) in ["✅", "❌"]
            )
        
        try:
            reaction, user = await self.bot.wait_for("reaction_add", timeout=60.0, check=check)
            
            if str(reaction.emoji) == "✅":
                # Clear the history
                await service.clear_ai_history(server_id, found_channel_id, ai_name, current_chat_id)
                
                try:
                    await confirm_msg.edit(
                        content=f"✅ **History Cleared Successfully**\n\n"
                        f"**AI:** {ai_name}\n"
                        f"**Channel:** <#{found_channel_id}>\n"
                        f"**Cleared by:** {interaction.user.mention}\n\n"
                        f"The conversation history has been permanently deleted."
                    )
                    await confirm_msg.clear_reactions()
                except discord.NotFound:
                    # Message was deleted, that's okay! :)
                    pass
                func.log.info(f"Cleared history for AI '{ai_name}' in server {server_id}")
            else:
                try:
                    await confirm_msg.edit(
                        content=f"❌ **Clear History Cancelled**\n\n"
                        f"No changes were made to the conversation history."
                    )
                    await confirm_msg.clear_reactions()
                except discord.NotFound:
                    # Message was deleted, that's okay! :)
                    pass
                
        except TimeoutError:
            try:
                await confirm_msg.edit(
                    content=f"⏱️ **Clear History Timed Out**\n\n"
                    f"No reaction received within 60 seconds. No changes were made."
                )
                await confirm_msg.clear_reactions()
            except discord.NotFound:
                # Message was deleted, that's okay! :)
                pass


async def setup(bot):
    """Load the HistoryManager cog."""
    await bot.add_cog(HistoryManager(bot))
