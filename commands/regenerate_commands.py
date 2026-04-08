"""
Regenerate Commands

Commands for regenerating AI responses and navigating between generations.
"""

import asyncio
import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
from AI.services.chat_service import get_service
from commands.shared.autocomplete import AutocompleteHelpers


# Module-level autocomplete functions (must be defined before class)
async def ai_name_autocomplete(
    interaction: discord.Interaction,
    current: str
) -> list[app_commands.Choice[str]]:
    """Autocomplete for AI names."""
    return await AutocompleteHelpers.ai_name_all(interaction, current)


class RegenerateCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="regenerate", description="Regenerate the last AI response")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI"
    )
    @app_commands.autocomplete(ai_name=ai_name_autocomplete)
    async def regenerate(
        self,
        interaction: discord.Interaction,
        ai_name: str = None
    ):
        """Regenerate the last AI response."""
        await interaction.response.defer(ephemeral=True)

        server_id = str(interaction.guild.id)
        channel_id = str(interaction.channel.id)

        # Try to detect AI name if not provided
        if not ai_name:
            channel_data = func.get_session_data(server_id, channel_id)
            if channel_data:
                if len(channel_data) == 1:
                    ai_name = list(channel_data.keys())[0]
                else:
                    await interaction.followup.send(
                        f"❌ Multiple AIs in this channel. Please specify which AI using the `ai_name` parameter.\n\n"
                        f"**Available AIs:** {', '.join(channel_data.keys())}",
                        ephemeral=True
                    )
                    return
            else:
                await interaction.followup.send(
                    "❌ No AI configured in this channel.",
                    ephemeral=True
                )
                return
        else:
            # Parse AI identifier from autocomplete (format: "ai_name|||channel_id")
            ai_name, channel_id_hint = AutocompleteHelpers.parse_ai_identifier(ai_name)

        # Verify AI exists
        found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
        if not found_ai_data:
            await interaction.followup.send(
                f"❌ AI '{ai_name}' not found in this server.",
                ephemeral=True
            )
            return
        
        found_channel_id, session = found_ai_data
        
        # Verify session data is valid
        if session is None:
            await interaction.followup.send(
                f"❌ AI '{ai_name}' session data is invalid or corrupted.",
                ephemeral=True
            )
            return
        
        # Get current chat_id from session
        current_chat_id = session.get("chat_id", "default")
        
        # Get conversation history
        service = get_service()
        history = await service.get_ai_history(server_id, found_channel_id, ai_name, current_chat_id)
        
        if not history or len(history) < 2:
            await interaction.followup.send(
                f"❌ Not enough conversation history to regenerate.",
                ephemeral=True
            )
            return
        
        # Get the last user message and AI response
        last_ai_message = None
        last_user_message = None
        
        for i in range(len(history) - 1, -1, -1):
            if history[i]["role"] == "assistant" and not last_ai_message:
                last_ai_message = history[i]["content"]
            elif history[i]["role"] == "user" and not last_user_message:
                last_user_message = history[i]["content"]
            
            if last_ai_message and last_user_message:
                break
        
        if not last_user_message or not last_ai_message:
            await interaction.followup.send(
                f"❌ Could not find last user message and AI response.",
                ephemeral=True
            )
            return
        
        try:
            # Get ResponseManager from bot's message pipeline
            if not hasattr(self.bot, 'message_pipeline'):
                await interaction.followup.send(
                    f"❌ Message pipeline not initialized. Please restart the bot.",
                    ephemeral=True
                )
                return
            
            response_manager = self.bot.message_pipeline.response_manager
            
            # Get current generation state
            state = response_manager.get_state(server_id, found_channel_id, ai_name)
            current = state.get_current()
            
            if not current or not current.discord_ids:
                await interaction.followup.send(
                    f"❌ No messages found to regenerate for AI '{ai_name}'.",
                    ephemeral=True
                )
                return
            
            # Delete Discord messages
            channel = interaction.guild.get_channel(int(found_channel_id))
            if not channel:
                await interaction.followup.send(
                    f"❌ Channel not found.",
                    ephemeral=True
                )
                return
            
            deleted_count = 0
            from utils.message_cache import fetch_message_cached
            
            for msg_id in current.discord_ids:
                try:
                    msg = await fetch_message_cached(channel, msg_id)
                    if msg:
                        await msg.delete()
                        deleted_count += 1
                    # Small delay to prevent burst operations
                    await asyncio.sleep(0.1)
                except discord.NotFound:
                    func.log.warning(f"Message {msg_id} not found, skipping")
                except Exception as e:
                    func.log.error(f"Error deleting message {msg_id}: {e}")
            
            # Remove last 2 messages from conversation history (user + assistant)
            if len(history) >= 2:
                updated_history = history[:-2]
                await service.set_ai_history(server_id, found_channel_id, ai_name, updated_history, current_chat_id)
                func.log.debug("Removed last 2 messages from history")
            
            await interaction.followup.send(
                f"✅ Deleted {deleted_count} message(s) and removed from history.\n"
                f"🔄 Generating new response for AI '{ai_name}'...",
                ephemeral=True
            )
            
            # Trigger regeneration using the message pipeline
            if state.user_message:
                # Get chat service
                from AI.services.chat_service import get_service
                chat_service = get_service()
                
                # Create callback for sending to Discord using centralized MessageSender
                async def send_callback(response_text, ids_list):
                    """Send response to Discord."""
                    from utils.message_sender import get_message_sender
                    sender = get_message_sender()
                    
                    discord_ids, view = await sender.send(
                        response_text=response_text,
                        channel=channel,
                        session=session,
                        split_message_fn=None,  # Use default splitting
                        bot=self.bot
                    )
                    ids_list.extend(discord_ids)
                
                # Generate new response
                result = await self.bot.message_pipeline.generate_response(
                    server_id,
                    found_channel_id,
                    ai_name,
                    session,
                    chat_service,
                    send_callback
                )
                
                if result:
                    response, discord_ids = result
                
                func.log.info("Regeneration complete")
            else:
                func.log.warning("No user message found for regeneration")
            
        except Exception as e:
            func.log.error(f"Error during regeneration: {e}")
            await interaction.followup.send(
                f"❌ Error during regeneration: {str(e)}",
                ephemeral=True
            )


async def setup(bot):
    """Setup the RegenerateCommands cog."""
    await bot.add_cog(RegenerateCommands(bot))
