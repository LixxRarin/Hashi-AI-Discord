"""
AI history management commands.

Provides commands to manage conversation history for AIs.
"""
import asyncio
import time
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Tuple, List

import utils.func as func
from AI.chat_service import get_service
from messaging.response import get_response_manager
from messaging.store import get_store
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
                    pass
                
        except TimeoutError:
            try:
                await confirm_msg.edit(
                    content=f"⏱️ **Clear History Timed Out**\n\n"
                    f"No reaction received within 60 seconds. No changes were made."
                )
                await confirm_msg.clear_reactions()
            except discord.NotFound:
                pass
    
    async def _delete_single_message_with_retry(
        self,
        message: discord.Message,
        max_retries: int = 3
    ) -> bool:
        """
        Delete a single message with exponential backoff retry.
        
        Args:
            message: Message to delete
            max_retries: Maximum retry attempts
            
        Returns:
            True if deleted successfully
        """
        base_delay = 2.0
        
        for attempt in range(max_retries):
            try:
                await message.delete()
                await asyncio.sleep(1.5)
                return True
            except discord.NotFound:
                func.log.debug(f"Message {message.id} already deleted")
                return True
            except discord.Forbidden:
                func.log.error(f"No permission to delete message {message.id}")
                return False
            except discord.HTTPException as e:
                if e.status == 429:
                    if attempt < max_retries - 1:
                        wait_time = base_delay * (2 ** attempt)
                        func.log.warning(
                            f"Rate limited on message {message.id}, "
                            f"waiting {wait_time}s (attempt {attempt + 1}/{max_retries})"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        func.log.error(f"Failed to delete message {message.id} after {max_retries} attempts")
                        return False
                else:
                    func.log.error(f"HTTP error deleting message {message.id}: {e}")
                    return False
            except Exception as e:
                func.log.error(f"Unexpected error deleting message {message.id}: {e}")
                return False
        
        return False
    
    async def _bulk_delete_messages(
        self,
        channel: discord.TextChannel,
        messages: List[discord.Message]
    ) -> Tuple[int, List[str]]:
        """
        Delete messages using bulk API where possible.
        
        Args:
            channel: Discord channel
            messages: List of message objects to delete
            
        Returns:
            (deleted_count, failed_ids)
        """
        deleted_count = 0
        failed_ids = []
        
        # Separate messages by age (14 days = 1209600 seconds)
        now = time.time()
        bulk_eligible = []
        individual_delete = []
        
        for msg in messages:
            age_seconds = now - msg.created_at.timestamp()
            if age_seconds < 1209600:
                bulk_eligible.append(msg)
            else:
                individual_delete.append(msg)
        
        # Bulk delete eligible messages (max 100 at a time)
        if bulk_eligible:
            func.log.debug(f"Bulk deleting {len(bulk_eligible)} messages (< 14 days old)")
            for i in range(0, len(bulk_eligible), 100):
                batch = bulk_eligible[i:i+100]
                try:
                    await channel.delete_messages(batch)
                    deleted_count += len(batch)
                    func.log.debug(f"Bulk deleted {len(batch)} messages")
                    await asyncio.sleep(1.0)
                except discord.HTTPException as e:
                    func.log.error(f"Bulk delete failed: {e}")
                    individual_delete.extend(batch)
        
        # Individual deletion for old messages or failed bulk deletes
        if individual_delete:
            func.log.info(f"Individually deleting {len(individual_delete)} messages")
            for msg in individual_delete:
                success = await self._delete_single_message_with_retry(msg)
                if success:
                    deleted_count += 1
                else:
                    failed_ids.append(str(msg.id))
        
        return deleted_count, failed_ids
    
    async def _simple_cascade_delete(
        self,
        channel: discord.TextChannel,
        target_message_id: str,
        ai_name: str,
        server_id: str,
        channel_id: str,
        chat_id: str
    ) -> Tuple[int, int, List[str]]:
        """
        Delete target message and all newer messages.
        Uses conversation store as single source of truth.
        
        Args:
            channel: Discord channel
            target_message_id: Discord ID of target message
            ai_name: AI name
            server_id: Server ID
            channel_id: Channel ID
            chat_id: Chat ID
            
        Returns:
            (discord_deleted, history_removed, failed_ids)
        """
        service = get_service()
        store = get_store()
        
        # 1. Get full history from store (single source of truth)
        full_history = await store.get_full_history(server_id, channel_id, ai_name, chat_id)
        
        func.log.debug(f"Full history has {len(full_history)} messages")
        
        # 2. Find target message index
        target_index = None
        for i, msg in enumerate(full_history):
            if msg.role == "user" and msg.discord_id == target_message_id:
                target_index = i
                func.log.info(f"Found target at index {i} (user message)")
                break
            elif msg.role == "assistant" and msg.discord_ids and target_message_id in msg.discord_ids:
                target_index = i
                func.log.info(f"Found target at index {i} (assistant message)")
                break
        
        if target_index is None:
            func.log.warning(f"Target message {target_message_id} not found in history")
            return 0, 0, [target_message_id]
        
        # 2.5. Protect greeting message (index 0)
        if target_index == 0:
            func.log.warning(f"Cannot delete greeting message (index 0) in cascade mode")
            # Start from index 1 instead to preserve greeting
            if len(full_history) > 1:
                target_index = 1
                func.log.info(f"Adjusted target_index to 1 to preserve greeting")
            else:
                # Only greeting exists, nothing to delete
                func.log.info(f"Only greeting exists, nothing to delete")
                return 0, 0, []
        
        # 3. Collect discord IDs to delete (target + newer messages)
        discord_ids_to_delete = []
        for msg in full_history[target_index:]:
            if msg.role == "user" and msg.discord_id:
                discord_ids_to_delete.append(msg.discord_id)
            elif msg.role == "assistant" and msg.discord_ids:
                discord_ids_to_delete.extend(msg.discord_ids)
        
        # 4. Fetch message objects for deletion
        messages_to_delete = []
        for discord_id in discord_ids_to_delete:
            try:
                msg = await channel.fetch_message(int(discord_id))
                messages_to_delete.append(msg)
            except discord.NotFound:
                func.log.debug(f"Message {discord_id} not found, skipping")
            except Exception as e:
                func.log.warning(f"Error fetching message {discord_id}: {e}")
        
        # 5. Delete messages using bulk API where possible
        func.log.info(f"Deleting {len(messages_to_delete)} messages from target onwards (cascade mode)")
        func.log.debug(f"Keeping {target_index} older messages")
        deleted_count, failed_ids = await self._bulk_delete_messages(channel, messages_to_delete)
        
        # 6. Update store directly to preserve metadata
        # Get the chat object and truncate its messages list
        chat = store._ensure_chat(server_id, channel_id, ai_name, chat_id)
        history_removed = len(chat.messages) - target_index
        chat.messages = chat.messages[:target_index]
        chat.metadata.updated_at = time.time()
        chat.metadata.message_count = len(chat.messages)
        
        # Save immediately
        await store.save_immediate()
        
        # 7. Clear ResponseManager
        response_manager = get_response_manager()
        response_manager.clear(server_id, channel_id, ai_name)
        
        return deleted_count, history_removed, failed_ids
    
    async def _simple_single_delete(
        self,
        channel: discord.TextChannel,
        target_message_id: str,
        ai_name: str,
        server_id: str,
        channel_id: str,
        chat_id: str
    ) -> Tuple[int, int, List[str]]:
        """
        Delete only the target message (and its pair if part of exchange).
        Uses conversation store as single source of truth.
        
        Args:
            channel: Discord channel
            target_message_id: Discord ID of target message
            ai_name: AI name
            server_id: Server ID
            channel_id: Channel ID
            chat_id: Chat ID
            
        Returns:
            (discord_deleted, history_removed, failed_ids)
        """
        service = get_service()
        store = get_store()
        
        # 1. Get full history from store
        full_history = await store.get_full_history(server_id, channel_id, ai_name, chat_id)
        
        # 2. Find target message
        target_index = None
        target_msg = None
        for i, msg in enumerate(full_history):
            if msg.role == "user" and msg.discord_id == target_message_id:
                target_index = i
                target_msg = msg
                break
            elif msg.role == "assistant" and msg.discord_ids and target_message_id in msg.discord_ids:
                target_index = i
                target_msg = msg
                break
        
        if target_index is None or target_msg is None:
            func.log.warning(f"Target message {target_message_id} not found in history")
            return 0, 0, [target_message_id]
        
        # 2.5. Protect greeting message (index 0)
        if target_index == 0 and target_msg.role == "assistant":
            func.log.warning(f"Cannot delete greeting message (index 0)")
            return 0, 0, []
        
        # 3. Delete only the target message (not its pair)
        indices_to_remove = [target_index]
        discord_ids_to_delete = []
        
        if target_msg.role == "assistant":
            # Bot message: delete only this message
            discord_ids_to_delete.extend(target_msg.discord_ids or [])
        else:
            # User message: delete only this message
            if target_msg.discord_id:
                discord_ids_to_delete.append(target_msg.discord_id)
        
        # 4. Delete from Discord
        deleted_count = 0
        failed_ids = []
        for discord_id in discord_ids_to_delete:
            try:
                msg = await channel.fetch_message(int(discord_id))
                success = await self._delete_single_message_with_retry(msg)
                if success:
                    deleted_count += 1
                else:
                    failed_ids.append(discord_id)
            except discord.NotFound:
                func.log.debug(f"Message {discord_id} already deleted")
            except Exception as e:
                func.log.warning(f"Error deleting message {discord_id}: {e}")
                failed_ids.append(discord_id)
        
        # 5. Update store directly to preserve metadata
        # Get the chat object and remove messages by index
        chat = store._ensure_chat(server_id, channel_id, ai_name, chat_id)
        
        # Sort indices in descending order to remove from end first
        indices_to_remove.sort(reverse=True)
        for idx in indices_to_remove:
            if idx < len(chat.messages):
                chat.messages.pop(idx)
        
        chat.metadata.updated_at = time.time()
        chat.metadata.message_count = len(chat.messages)
        
        # Save immediately
        await store.save_immediate()
        
        # 6. Clear ResponseManager
        response_manager = get_response_manager()
        response_manager.clear(server_id, channel_id, ai_name)
        
        history_removed = len(indices_to_remove)
        return deleted_count, history_removed, failed_ids
    
    @app_commands.command(
        name="delete_message",
        description="Delete specific bot messages with cascade or single mode"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        mode="Delete mode: cascade (all messages up to this) or single (only this message)",
        message_id="Discord message ID (bot or user message) - leave empty for last bot message",
        ai_name="Name of the AI (auto-detects if only one AI in channel)"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Cascade (delete all messages up to this one)", value="cascade"),
        app_commands.Choice(name="Single (delete only this message)", value="single")
    ])
    @app_commands.autocomplete(ai_name=ai_name_all_autocomplete)
    async def delete_message(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str],
        message_id: str = None,
        ai_name: str = None
    ):
        """Delete specific bot messages with cascade or single mode.
        
        💡 Tip: Right-click a message → Copy ID to get the message_id.
        If message_id is not provided, the last bot message will be used.
        """
        await interaction.response.defer(ephemeral=True)
        
        server_id = str(interaction.guild.id)
        channel_id = str(interaction.channel.id)
        
        # Validate channel permissions
        if not interaction.channel.permissions_for(interaction.guild.me).manage_messages:
            await interaction.followup.send(
                "❌ I don't have permission to delete messages in this channel.\n\n"
                "💡 Grant me the 'Manage Messages' permission.",
                ephemeral=True
            )
            return
        
        # Auto-detect AI name if not provided
        if not ai_name:
            channel_data = func.get_session_data(server_id, channel_id)
            if not channel_data:
                await interaction.followup.send(
                    "❌ No AI configured in this channel.",
                    ephemeral=True
                )
                return
            
            if len(channel_data) > 1:
                await interaction.followup.send(
                    f"❌ Multiple AIs in this channel. Please specify which AI using the `ai_name` parameter.\n\n"
                    f"**Available AIs:** {', '.join(channel_data.keys())}",
                    ephemeral=True
                )
                return
            
            ai_name = list(channel_data.keys())[0]
        
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
        
        # Get current chat_id
        chat_id = session.get("chat_id", "default")
        
        # Get channel object
        channel = interaction.guild.get_channel(int(found_channel_id))
        if not channel:
            await interaction.followup.send(
                f"❌ Channel not found.",
                ephemeral=True
            )
            return
        
        bot_id = self.bot.user.id
        
        # If message_id not provided, find the last bot message
        if not message_id:
            func.log.info(f"No message_id provided, searching for last bot message from AI '{ai_name}'")
            
            # Find last bot message
            last_bot_message = None
            async for message in channel.history(limit=50):
                if message.author.id == bot_id or (message.webhook_id and ai_name.lower() in message.author.name.lower()):
                    last_bot_message = message
                    break
            
            if not last_bot_message:
                await interaction.followup.send(
                    f"❌ No bot messages found for AI '{ai_name}' in recent history.\n\n"
                    f"💡 Try providing a specific message_id.",
                    ephemeral=True
                )
                return
            
            target_message_id = str(last_bot_message.id)
            func.log.info(f"Found last bot message: {target_message_id}")
        else:
            # Use provided message_id
            target_message_id = message_id
        
        # Execute deletion based on mode
        try:
            if mode.value == "cascade":
                # Show progress message
                await interaction.followup.send(
                    f"⏳ Scanning channel history and deleting messages in cascade mode...",
                    ephemeral=True
                )
                
                deleted_count, history_removed, failed_ids = await self._simple_cascade_delete(
                    channel, target_message_id, ai_name, server_id, found_channel_id, chat_id
                )
            else:  # single
                deleted_count, history_removed, failed_ids = await self._simple_single_delete(
                    channel, target_message_id, ai_name, server_id, found_channel_id, chat_id
                )
            
            # Build success message
            if not failed_ids:
                success_msg = f"✅ **{'Cascade ' if mode.value == 'cascade' else ''}Delete Complete!**\n\n"
                success_msg += f"🗑️ **Discord Messages Deleted:** {deleted_count} message(s)\n"
                success_msg += f"📝 **History Entries Removed:** {history_removed} entry(ies)\n"
                success_msg += f"🤖 **AI:** {ai_name}\n"
                success_msg += f"🎯 **Target Message:** `{target_message_id}`\n\n"
                
                if mode.value == "cascade":
                    success_msg += "💡 All messages up to the target have been deleted."
                else:
                    success_msg += "💡 Only the target message was deleted."
            else:
                success_msg = f"⚠️ **Delete Completed with Warnings**\n\n"
                success_msg += f"✅ **Discord Messages Deleted:** {deleted_count} message(s)\n"
                success_msg += f"❌ **Failed to Delete:** {len(failed_ids)} message(s)\n"
                success_msg += f"📝 **History Entries Removed:** {history_removed} entry(ies)\n"
                success_msg += f"🤖 **AI:** {ai_name}\n\n"
                success_msg += "💡 Some messages couldn't be deleted but were removed from history."
            
            await interaction.followup.send(success_msg, ephemeral=True)
            
            func.log.debug(
                f"Deleted messages for AI {ai_name} in {mode.value} mode: "
                f"{deleted_count} Discord messages, {history_removed} history entries"
            )
            
        except Exception as e:
            func.log.error(f"Error during message deletion: {e}")
            await interaction.followup.send(
                f"❌ Error during deletion: {str(e)}\n\n"
                f"Some messages may have been partially deleted. Check the channel and history.",
                ephemeral=True
            )


async def setup(bot):
    """Load the HistoryManager cog."""
    await bot.add_cog(HistoryManager(bot))
