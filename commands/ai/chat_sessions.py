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
    
    @app_commands.command(name="list_chats", description="List all chat sessions for an AI")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(ai_name="Name of the AI to list chats for")
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def list_chats(self, interaction: discord.Interaction, ai_name: str):
        """List all chat sessions for an AI with summary information."""
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
        
        # Get all chat IDs
        service = get_service()
        chat_ids = service.history_manager.list_chat_ids(server_id, found_channel_id, ai_name)
        
        if not chat_ids:
            await interaction.followup.send(
                f"❌ No chat sessions found for AI '{ai_name}'.",
                ephemeral=True
            )
            return
        
        # Get active chat
        active_chat_id = session.get("chat_id", "default")
        
        # Build embed
        embed = discord.Embed(
            title=f"💬 Chat Sessions - {ai_name}",
            description=f"**Total chats:** {len(chat_ids)}\n**Active chat:** `{active_chat_id}`",
            color=discord.Color.blue()
        )
        
        # Add info for each chat (limit to 10 most recent)
        for i, chat_id in enumerate(chat_ids[:10]):
            info = service.history_manager.get_chat_info(server_id, found_channel_id, ai_name, chat_id)
            
            # Format timestamps
            import datetime
            created = datetime.datetime.fromtimestamp(info["created_at"]).strftime("%Y-%m-%d %H:%M")
            updated = datetime.datetime.fromtimestamp(info["updated_at"]).strftime("%Y-%m-%d %H:%M")
            
            # Active indicator
            indicator = "🟢 " if chat_id == active_chat_id else ""
            
            # Truncate chat_id if too long
            display_id = chat_id[:30] + "..." if len(chat_id) > 30 else chat_id
            
            field_value = f"{indicator}**Messages:** {info['message_count']}\n"
            field_value += f"**Created:** {created}\n"
            field_value += f"**Updated:** {updated}"
            
            embed.add_field(
                name=f"📝 {display_id}",
                value=field_value,
                inline=True
            )
        
        if len(chat_ids) > 10:
            embed.set_footer(text=f"Showing 10 of {len(chat_ids)} chats. Use /chat_info to see specific chats.")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name="delete_chat", description="Delete a specific chat session")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI",
        chat_id="Chat ID to delete (use autocomplete)"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete, chat_id=chat_id_autocomplete)
    async def delete_chat(self, interaction: discord.Interaction, ai_name: str, chat_id: str):
        """Delete a specific chat session with confirmation."""
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
        
        # Get chat info
        service = get_service()
        available_chats = service.history_manager.list_chat_ids(server_id, found_channel_id, ai_name)
        
        if chat_id not in available_chats:
            await interaction.followup.send(
                f"❌ Chat '{chat_id}' not found for AI '{ai_name}'.",
                ephemeral=True
            )
            return
        
        # Check if it's the active chat
        active_chat_id = session.get("chat_id", "default")
        if chat_id == active_chat_id:
            await interaction.followup.send(
                f"❌ **Cannot delete active chat!**\n\n"
                f"Chat '{chat_id}' is currently active.\n"
                f"Please switch to another chat first using `/switch_chat`.",
                ephemeral=True
            )
            return
        
        # Get chat info for confirmation
        info = service.history_manager.get_chat_info(server_id, found_channel_id, ai_name, chat_id)
        
        # Send confirmation message
        import datetime
        created = datetime.datetime.fromtimestamp(info["created_at"]).strftime("%Y-%m-%d %H:%M")
        
        confirm_msg = await interaction.channel.send(
            f"⚠️ **WARNING: Delete Chat Confirmation** (requested by {interaction.user.mention})\n\n"
            f"**AI:** {ai_name}\n"
            f"**Chat ID:** `{chat_id}`\n"
            f"**Messages:** {info['message_count']}\n"
            f"**Created:** {created}\n\n"
            f"⚠️ **This will PERMANENTLY DELETE this chat session!**\n"
            f"All conversation history will be lost.\n\n"
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
                # Delete the chat
                try:
                    success = await service.history_manager.delete_chat(
                        server_id, found_channel_id, ai_name, chat_id
                    )
                    
                    if success:
                        try:
                            await confirm_msg.edit(
                                content=f"✅ **Chat Deleted Successfully**\n\n"
                                f"**AI:** {ai_name}\n"
                                f"**Chat ID:** `{chat_id}`\n"
                                f"**Deleted by:** {interaction.user.mention}\n\n"
                                f"The chat session has been permanently deleted."
                            )
                            await confirm_msg.clear_reactions()
                        except discord.NotFound:
                            pass
                        func.log.info(f"Deleted chat '{chat_id}' for AI '{ai_name}' in server {server_id}")
                    else:
                        await interaction.followup.send(
                            f"❌ Failed to delete chat. Check logs for details.",
                            ephemeral=True
                        )
                except ValueError as e:
                    await interaction.followup.send(
                        f"❌ Error: {str(e)}",
                        ephemeral=True
                    )
            else:
                try:
                    await confirm_msg.edit(
                        content=f"❌ **Delete Chat Cancelled**\n\n"
                        f"No changes were made."
                    )
                    await confirm_msg.clear_reactions()
                except discord.NotFound:
                    pass
                
        except TimeoutError:
            try:
                await confirm_msg.edit(
                    content=f"⏱️ **Delete Chat Timed Out**\n\n"
                    f"No reaction received within 60 seconds. No changes were made."
                )
                await confirm_msg.clear_reactions()
            except discord.NotFound:
                pass
    
    @app_commands.command(name="rename_chat", description="Rename a chat session")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI",
        old_name="Current chat ID (use autocomplete)",
        new_name="New name for the chat"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete, old_name=chat_id_autocomplete)
    async def rename_chat(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        old_name: str,
        new_name: str
    ):
        """Rename a chat session."""
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
        
        # Validate new name length
        if len(new_name) > 100:
            await interaction.followup.send(
                f"❌ New name is too long. Maximum 100 characters.",
                ephemeral=True
            )
            return
        
        # Rename the chat
        service = get_service()
        try:
            success = await service.history_manager.rename_chat(
                server_id, found_channel_id, ai_name, old_name, new_name
            )
            
            if success:
                # Update session data if this is the active chat
                active_chat_id = session.get("chat_id", "default")
                if old_name == active_chat_id:
                    session["chat_id"] = new_name
                    channel_data[ai_name] = session
                    await func.update_session_data(server_id, found_channel_id, channel_data)
                
                result_msg = f"✅ **Chat Renamed Successfully!**\n\n"
                result_msg += f"**AI:** {ai_name}\n"
                result_msg += f"**Old name:** `{old_name}`\n"
                result_msg += f"**New name:** `{new_name}`\n"
                
                if old_name == active_chat_id:
                    result_msg += f"\n💡 This was the active chat. Session updated."
                
                await interaction.followup.send(result_msg, ephemeral=True)
                func.log.info(f"Renamed chat '{old_name}' to '{new_name}' for AI '{ai_name}' in server {server_id}")
            else:
                await interaction.followup.send(
                    f"❌ Failed to rename chat. Check logs for details.",
                    ephemeral=True
                )
        except ValueError as e:
            await interaction.followup.send(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )
    
    @app_commands.command(name="chat_info", description="View detailed information about chat sessions")
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        ai_name="Name of the AI",
        chat_id="Specific chat ID (optional - shows general info if not provided)"
    )
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete, chat_id=chat_id_autocomplete)
    async def chat_info(
        self,
        interaction: discord.Interaction,
        ai_name: str,
        chat_id: str = None
    ):
        """View detailed information about chat sessions."""
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
        service = get_service()
        
        if chat_id:
            # Show detailed info for specific chat
            available_chats = service.history_manager.list_chat_ids(server_id, found_channel_id, ai_name)
            
            if chat_id not in available_chats:
                await interaction.followup.send(
                    f"❌ Chat '{chat_id}' not found for AI '{ai_name}'.",
                    ephemeral=True
                )
                return
            
            info = service.history_manager.get_chat_info(server_id, found_channel_id, ai_name, chat_id)
            active_chat_id = session.get("chat_id", "default")
            
            # Format timestamps
            import datetime
            created = datetime.datetime.fromtimestamp(info["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
            updated = datetime.datetime.fromtimestamp(info["updated_at"]).strftime("%Y-%m-%d %H:%M:%S")
            
            # Build embed
            embed = discord.Embed(
                title=f"📊 Chat Information - {ai_name}",
                description=f"**Chat ID:** `{chat_id}`",
                color=discord.Color.green() if chat_id == active_chat_id else discord.Color.blue()
            )
            
            # Status
            status = "🟢 Active" if chat_id == active_chat_id else "⚪ Inactive"
            embed.add_field(name="Status", value=status, inline=True)
            embed.add_field(name="Messages", value=str(info["message_count"]), inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            # Timestamps
            embed.add_field(name="Created", value=created, inline=True)
            embed.add_field(name="Last Updated", value=updated, inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            # Greeting
            if info["greeting"]:
                embed.add_field(
                    name="Greeting Message",
                    value=f"```{info['greeting']}```",
                    inline=False
                )
            
            # Recent messages
            if info["last_messages"]:
                recent_text = ""
                for msg in info["last_messages"]:
                    recent_text += f"{msg['preview']}\n\n"
                
                # Wrap all messages in a single code block
                embed.add_field(
                    name="Recent Messages",
                    value=f"```{recent_text[:1018]}```",  # 1024 - 6 for ``` markers
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        else:
            # Show general info for all chats
            chat_ids = service.history_manager.list_chat_ids(server_id, found_channel_id, ai_name)
            
            if not chat_ids:
                await interaction.followup.send(
                    f"❌ No chat sessions found for AI '{ai_name}'.",
                    ephemeral=True
                )
                return
            
            active_chat_id = session.get("chat_id", "default")
            
            # Calculate total messages
            total_messages = 0
            for cid in chat_ids:
                info = service.history_manager.get_chat_info(server_id, found_channel_id, ai_name, cid)
                total_messages += info["message_count"]
            
            # Build embed
            embed = discord.Embed(
                title=f"📊 Chat Overview - {ai_name}",
                description=f"**Channel:** <#{found_channel_id}>",
                color=discord.Color.purple()
            )
            
            embed.add_field(name="Total Chats", value=str(len(chat_ids)), inline=True)
            embed.add_field(name="Total Messages", value=str(total_messages), inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            embed.add_field(
                name="Active Chat",
                value=f"`{active_chat_id[:50]}{'...' if len(active_chat_id) > 50 else ''}`",
                inline=False
            )
            
            # List chats (limit to 5)
            chat_list = ""
            for i, cid in enumerate(chat_ids[:5]):
                info = service.history_manager.get_chat_info(server_id, found_channel_id, ai_name, cid)
                indicator = "🟢" if cid == active_chat_id else "⚪"
                display_id = cid[:25] + "..." if len(cid) > 25 else cid
                chat_list += f"{indicator} `{display_id}` - {info['message_count']} msgs\n"
            
            if len(chat_ids) > 5:
                chat_list += f"\n*...and {len(chat_ids) - 5} more*"
            
            embed.add_field(
                name="Chat Sessions",
                value=chat_list,
                inline=False
            )
            
            embed.set_footer(text="💡 Use /chat_info <ai_name> <chat_id> for detailed information about a specific chat")
            
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    """Load the ChatSessions cog."""
    await bot.add_cog(ChatSessions(bot))
