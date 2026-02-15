"""
AI chat session management commands.

Provides commands to manage multiple chat sessions for AIs.
"""
import uuid

import discord
from discord import app_commands
from discord.ext import commands

import utils.func as func
from AI.chat_service import get_service
from commands.shared.autocomplete import AutocompleteHelpers
from commands.shared.webhook_utils import WebhookUtils


class ChatSessions(commands.Cog):
    """Commands for managing AI chat sessions."""
    
    def __init__(self, bot):
        self.bot = bot
        self.webhook_utils = WebhookUtils()
    
    async def ai_name_all_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for all AI names."""
        return await AutocompleteHelpers.ai_name_all(interaction, current)
    
    async def chat_id_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for chat IDs."""
        return await AutocompleteHelpers.chat_id(interaction, current)
    
    @app_commands.command(name="switch_chat", description="Switch to an existing chat session for an AI")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to switch chat for",
        chat_id="Chat ID to switch to (use autocomplete to select)"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete, chat_id=chat_id_autocomplete)
    async def switch_chat(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        chat_id: str
    ):
        """Switch to an existing chat session for an AI."""
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
        channel_data = func.get_session_data(server_id, found_channel_id)
        
        old_chat_id = session.get("chat_id", "default")
        
        # Validate that the chat_id exists
        service = get_service()
        available_chats = service.history_manager.list_chat_ids(server_id, found_channel_id, ai_name)
        
        if chat_id not in available_chats:
            await interaction.followup.send(
                f"❌ **Error:** Chat ID not found for AI '{ai_name}'.\n\n"
                f"**Available options:**\n"
                f"• Use `/list_chats {ai_name}` to see existing chats\n"
                f"• Use `/new_chat {ai_name}` to create a new chat",
                ephemeral=True
            )
            return
        
        # Update chat_id in session
        session["setup_has_already"] = False
        session["chat_id"] = chat_id
        
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)
        
        # Initialize session messages if needed
        greetings = await service.initialize_session_messages(
            session, server_id, found_channel_id, chat_id
        )
        
        # Send messages to Discord
        messages_sent = False
        channel_obj = interaction.guild.get_channel(int(found_channel_id))
        
        if channel_obj:
            if session.get("mode") == "webhook":
                WB_url = session.get("webhook_url")
                if WB_url and greetings:
                    try:
                        await self.webhook_utils.send_message(WB_url, greetings, session)
                        messages_sent = True
                    except Exception as e:
                        func.log.error("Error sending greeting via webhook: %s", e)
            else:
                if greetings:
                    try:
                        await channel_obj.send(greetings)
                        messages_sent = True
                    except Exception as e:
                        func.log.error(f"Error sending greeting as bot: {e}")
        
        # Mark as setup if messages were sent
        if messages_sent or not greetings:
            channel_data[ai_name]["setup_has_already"] = True
            await func.update_session_data(server_id, found_channel_id, channel_data)
        
        # Get info about the chat
        info = service.history_manager.get_chat_info(server_id, found_channel_id, ai_name, chat_id)
        msg_count = info.get("message_count", 0)
        
        result_msg = f"✅ **Switched to existing chat session!**\n\n"
        result_msg += f"**AI:** {ai_name}\n"
        result_msg += f"**Channel:** <#{found_channel_id}>\n"
        result_msg += f"**Previous Chat ID:** `{old_chat_id[:40]}...`\n" if len(old_chat_id) > 40 else f"**Previous Chat ID:** `{old_chat_id}`\n"
        result_msg += f"**Current Chat ID:** `{chat_id[:40]}...`\n" if len(chat_id) > 40 else f"**Current Chat ID:** `{chat_id}`\n"
        result_msg += f"**Messages in this chat:** {msg_count}\n\n"
        result_msg += f"💡 The AI is now using this existing chat session."
        
        await interaction.followup.send(result_msg, ephemeral=True)
    
    @app_commands.command(name="new_chat", description="Create a new chat session for an AI")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI to create a new chat for",
        chat_name="Custom name for the chat (optional, will generate UUID if not provided)",
        send_greeting="Send greeting message in the new chat (default: True)",
        greeting_index="Which greeting to use (0=first_mes, 1+=alternate_greetings) - only for character cards"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def new_chat(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        chat_name: str = None,
        send_greeting: bool = True,
        greeting_index: int = None
    ):
        """Create a new chat session for an AI."""
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
        channel_data = func.get_session_data(server_id, found_channel_id)
        
        old_chat_id = session.get("chat_id", "default")
        
        # Generate new chat ID
        if chat_name:
            service = get_service()
            existing_chats = service.history_manager.list_chat_ids(server_id, found_channel_id, ai_name)
            if chat_name in existing_chats:
                await interaction.followup.send(
                    f"❌ **Error:** A chat named '{chat_name}' already exists for AI '{ai_name}'.\n\n"
                    f"💡 Choose a different name or use `/list_chats {ai_name}` to see existing chats.",
                    ephemeral=True
                )
                return
            new_chat_id = chat_name
        else:
            new_chat_id = str(uuid.uuid4())
        
        # Update chat_id in session
        session["setup_has_already"] = False
        session["chat_id"] = new_chat_id
        
        channel_data[ai_name] = session
        await func.update_session_data(server_id, found_channel_id, channel_data)
        
        service = get_service()
        service.set_ai_history(server_id, found_channel_id, ai_name, [], new_chat_id)
        
        # Update greeting_index if provided
        if greeting_index is not None:
            card_data = session.get("character_card", {}).get("data", {})
            if card_data:
                alt_greetings = card_data.get("alternate_greetings") or []
                total_greetings = 1 + len(alt_greetings)
                
                if greeting_index < 0 or greeting_index >= total_greetings:
                    await interaction.followup.send(
                        f"❌ **Error:** Invalid greeting index {greeting_index}.\n"
                        f"This character has {total_greetings} greetings (0-{total_greetings-1}).",
                        ephemeral=True
                    )
                    return
                
                session["config"]["greeting_index"] = greeting_index
                channel_data[ai_name] = session
                await func.update_session_data(server_id, found_channel_id, channel_data)
        
        # Send greeting if requested
        messages_sent = False
        if send_greeting:
            channel_data = func.get_session_data(server_id, found_channel_id)
            session = channel_data[ai_name]
            
            greetings = await service.initialize_session_messages(
                session, server_id, found_channel_id, new_chat_id
            )
            
            channel_obj = interaction.guild.get_channel(int(found_channel_id))
            if channel_obj and greetings:
                if session.get("mode") == "webhook":
                    WB_url = session.get("webhook_url")
                    if WB_url:
                        try:
                            await self.webhook_utils.send_message(WB_url, greetings, session)
                            messages_sent = True
                        except Exception as e:
                            func.log.error("Error sending greeting via webhook: %s", e)
                else:
                    try:
                        await channel_obj.send(greetings)
                        messages_sent = True
                    except Exception as e:
                        func.log.error(f"Error sending greeting as bot: {e}")
        
        # Mark as setup
        if messages_sent or not send_greeting:
            channel_data = func.get_session_data(server_id, found_channel_id)
            channel_data[ai_name]["setup_has_already"] = True
            await func.update_session_data(server_id, found_channel_id, channel_data)
        
        result_msg = f"✅ **New chat session created!**\n\n"
        result_msg += f"**AI:** {ai_name}\n"
        result_msg += f"**Channel:** <#{found_channel_id}>\n"
        result_msg += f"**Previous Chat ID:** `{old_chat_id[:40]}...`\n" if len(old_chat_id) > 40 else f"**Previous Chat ID:** `{old_chat_id}`\n"
        result_msg += f"**New Chat ID:** `{new_chat_id[:40]}...`\n" if len(new_chat_id) > 40 else f"**New Chat ID:** `{new_chat_id}`\n"
        if greeting_index is not None:
            result_msg += f"**Greeting Index:** {greeting_index}\n"
        result_msg += f"\n💡 The AI is now using this new chat session."
        
        await interaction.followup.send(result_msg, ephemeral=True)


async def setup(bot):
    """Load the ChatSessions cog."""
    await bot.add_cog(ChatSessions(bot))
