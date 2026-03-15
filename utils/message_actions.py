"""
Message Action Buttons - Discord UI Components for AI Messages

This module provides Discord UI buttons for interacting with AI messages:
- Navigation between generations (previous/next)
- Regeneration of responses
- Deletion of messages
- Editing of messages

Replaces the old reaction-based system with modern Discord UI components.
"""

import asyncio
import discord
from discord import ui
from typing import Dict, Any, List, Optional
import logging

log = logging.getLogger(__name__)


class EditMessageModal(ui.Modal):
    """
    Modal for editing AI messages.
    
    Allows users to edit the text of an AI message and updates:
    - The message in Discord
    - The conversation history
    - The ResponseManager state
    """
    
    def __init__(
        self,
        bot,
        server_id: str,
        channel_id: str,
        ai_name: str,
        current_text: str,
        session: Dict[str, Any]
    ):
        super().__init__(title="Edit AI Message", timeout=300)
        
        self.bot = bot
        self.server_id = server_id
        self.channel_id = channel_id
        self.ai_name = ai_name
        self.session = session
        
        # Text input field with current message
        # Discord limits TextInput to 4000 chars, but messages are 2000
        # We'll truncate if needed
        truncated_text = current_text[:4000] if len(current_text) > 4000 else current_text
        
        self.message_input = ui.TextInput(
            label="Message Content",
            style=discord.TextStyle.paragraph,
            default=truncated_text,
            max_length=4000,
            required=True,
            placeholder="Enter the new message content..."
        )
        self.add_item(self.message_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Process the message edit."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            new_text = self.message_input.value
            
            if not new_text or new_text.isspace():
                await interaction.followup.send(
                    "❌ Message cannot be empty.",
                    ephemeral=True
                )
                return
            
            # Get ResponseManager
            response_manager = self.bot.message_pipeline.response_manager
            state = response_manager.get_state(self.server_id, self.channel_id, self.ai_name)
            current_gen = state.get_current()
            
            if not current_gen:
                await interaction.followup.send(
                    "❌ No message found to edit.",
                    ephemeral=True
                )
                return
            
            # Get channel
            channel = interaction.guild.get_channel(int(self.channel_id))
            if not channel:
                await interaction.followup.send(
                    "❌ Channel not found.",
                    ephemeral=True
                )
                return
            
            # Update messages in Discord using MessageSender
            from utils.message_sender import get_message_sender
            sender = get_message_sender()
            
            mode = self.session.get("mode", "webhook")
            webhook_url = self.session.get("webhook_url")
            
            updated_ids = await sender.edit_messages(
                channel=channel,
                message_ids=current_gen.discord_ids,
                new_text=new_text,
                mode=mode,
                webhook_url=webhook_url,
                split_message_fn=None
            )
            
            # Update ResponseManager
            response_manager.update_generation_text(
                self.server_id,
                self.channel_id,
                self.ai_name,
                new_text
            )
            
            # Update Discord IDs if they changed
            if updated_ids:
                current_gen.discord_ids = updated_ids
            
            # Update conversation history
            from AI.chat_service import get_service
            chat_service = get_service()
            
            current_chat_id = self.session.get("chat_id", "default")
            history = chat_service.get_ai_history(
                self.server_id,
                self.channel_id,
                self.ai_name,
                current_chat_id
            )
            
            # Find and update the last assistant message
            if history:
                for i in range(len(history) - 1, -1, -1):
                    if history[i]["role"] == "assistant":
                        history[i]["content"] = new_text
                        break
                
                await chat_service.set_ai_history(
                    self.server_id,
                    self.channel_id,
                    self.ai_name,
                    history,
                    current_chat_id
                )
            
            await interaction.followup.send(
                "✅ Message edited successfully!",
                ephemeral=True
            )
            
            log.info(f"Message edited for AI {self.ai_name} in channel {self.channel_id}")
            
        except Exception as e:
            log.error(f"Error editing message: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error editing message: {str(e)}",
                ephemeral=True
            )
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """Handle modal errors."""
        log.error(f"Modal error: {error}", exc_info=True)
        try:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(error)}",
                ephemeral=True
            )
        except:
            pass


class MessageActionsView(ui.View):
    """
    Discord UI View with action buttons for AI messages.
    
    Provides buttons for:
    - Navigation between generations (◀️/▶️)
    - Regeneration (🔄)
    - Deletion (🗑️)
    - Editing (✏️)
    
    Buttons are configurable via the session config.
    """
    
    def __init__(
        self,
        bot,
        server_id: str,
        channel_id: str,
        ai_name: str,
        session: Dict[str, Any],
        timeout: Optional[float] = None
    ):
        """
        Initialize the message actions view.
        
        Args:
            bot: Bot instance
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            session: AI session data
            timeout: View timeout (None = persistent)
        """
        super().__init__(timeout=timeout)
        
        self.bot = bot
        self.server_id = server_id
        self.channel_id = channel_id
        self.ai_name = ai_name
        self.session = session
        
        # Get button configuration
        button_config = session.get("config", {}).get("message_action_buttons", {})
        buttons = button_config.get("buttons", [])
        
        # Create buttons dynamically
        self._create_buttons(buttons)
        
        # Update button states
        self._update_button_states()
    
    def _create_buttons(self, button_configs: List[Dict[str, Any]]):
        """Create buttons based on configuration."""
        self.counter_button = None  # Store reference to counter button
        
        for btn_cfg in button_configs:
            if not btn_cfg.get("enabled", True):
                continue
            
            btn_type = btn_cfg.get("type")
            emoji = btn_cfg.get("emoji")
            label = btn_cfg.get("label")
            style_name = btn_cfg.get("style", "secondary")
            
            # Map style name to ButtonStyle
            style_map = {
                "primary": discord.ButtonStyle.primary,
                "secondary": discord.ButtonStyle.secondary,
                "success": discord.ButtonStyle.success,
                "danger": discord.ButtonStyle.danger
            }
            style = style_map.get(style_name, discord.ButtonStyle.secondary)
            
            # Create button based on type
            if btn_type == "previous":
                button = ui.Button(
                    emoji=emoji,
                    label=label,
                    style=style,
                    custom_id=f"prev_{self.server_id}_{self.channel_id}_{self.ai_name}"
                )
                button.callback = self._handle_previous
                self.add_item(button)
                
                # Add counter button after previous button
                self.counter_button = ui.Button(
                    label="Message 1/1",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                    custom_id=f"counter_{self.server_id}_{self.channel_id}_{self.ai_name}"
                )
                self.counter_button.callback = self._handle_counter_click
                self.add_item(self.counter_button)
                
            elif btn_type == "next":
                button = ui.Button(
                    emoji=emoji,
                    label=label,
                    style=style,
                    custom_id=f"next_{self.server_id}_{self.channel_id}_{self.ai_name}"
                )
                button.callback = self._handle_next
                self.add_item(button)
                
            elif btn_type == "regenerate":
                button = ui.Button(
                    emoji=emoji,
                    label=label,
                    style=style,
                    custom_id=f"regen_{self.server_id}_{self.channel_id}_{self.ai_name}"
                )
                button.callback = self._handle_regenerate
                self.add_item(button)
                
            elif btn_type == "delete":
                button = ui.Button(
                    emoji=emoji,
                    label=label,
                    style=style,
                    custom_id=f"del_{self.server_id}_{self.channel_id}_{self.ai_name}"
                )
                button.callback = self._handle_delete
                self.add_item(button)
                
            elif btn_type == "edit":
                button = ui.Button(
                    emoji=emoji,
                    label=label,
                    style=style,
                    custom_id=f"edit_{self.server_id}_{self.channel_id}_{self.ai_name}"
                )
                button.callback = self._handle_edit
                self.add_item(button)
    
    def _update_button_states(self):
        """Update button states based on current generation state."""
        try:
            response_manager = self.bot.message_pipeline.response_manager
            state = response_manager.get_state(self.server_id, self.channel_id, self.ai_name)
            info = state.get_info()
            
            # Ensure we never show 0 as total_count (minimum is 1)
            current_num = max(1, info['current_number'])
            total_count = max(1, info['total_count'])
            
            # Update button states
            for item in self.children:
                if isinstance(item, ui.Button):
                    custom_id = item.custom_id or ""
                    
                    # Disable previous if no previous generation
                    if custom_id.startswith("prev_"):
                        item.disabled = not info["has_previous"]
                    
                    # Disable next if no next generation
                    elif custom_id.startswith("next_"):
                        item.disabled = not info["has_next"]
                    
                    # Update counter button label with "Message X/Y" format
                    elif custom_id.startswith("counter_"):
                        item.label = f"Message {current_num}/{total_count}"
                    
        except Exception as e:
            log.error(f"Error updating button states: {e}")
    
    async def _handle_counter_click(self, interaction: discord.Interaction):
        """Counter button handler (non-interactive, just for display)."""
        # This button is disabled and just shows information
        pass
    
    async def _handle_previous(self, interaction: discord.Interaction):
        """Navigate to previous generation."""
        await interaction.response.defer()
        
        try:
            response_manager = self.bot.message_pipeline.response_manager
            
            # Navigate to previous
            prev_gen = response_manager.navigate(
                self.server_id,
                self.channel_id,
                self.ai_name,
                -1
            )
            
            if not prev_gen:
                await interaction.followup.send(
                    "❌ No previous generation available.",
                    ephemeral=True
                )
                return
            
            # Get channel
            channel = interaction.guild.get_channel(int(self.channel_id))
            if not channel:
                await interaction.followup.send(
                    "❌ Channel not found.",
                    ephemeral=True
                )
                return
            
            # Update messages in Discord
            from utils.message_sender import get_message_sender
            sender = get_message_sender()
            
            mode = self.session.get("mode", "webhook")
            webhook_url = self.session.get("webhook_url")
            
            # Get current generation's discord IDs to update
            state = response_manager.get_state(self.server_id, self.channel_id, self.ai_name)
            current_gen = state.get_current()
            info = state.get_info()
            
            if current_gen and current_gen.discord_ids:
                await sender.edit_messages(
                    channel=channel,
                    message_ids=current_gen.discord_ids,
                    new_text=prev_gen.text,
                    mode=mode,
                    webhook_url=webhook_url,
                    split_message_fn=None
                )
            
            # Update button states
            self._update_button_states()
            
            # Update the view
            await interaction.edit_original_response(view=self)
            
            log.info(f"Navigated to previous generation ({info['current_number']}/{info['total_count']}) for AI {self.ai_name}")
            
        except Exception as e:
            log.error(f"Error navigating to previous: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )
    
    async def _handle_next(self, interaction: discord.Interaction):
        """Navigate to next generation."""
        await interaction.response.defer()
        
        try:
            response_manager = self.bot.message_pipeline.response_manager
            
            # Navigate to next
            next_gen = response_manager.navigate(
                self.server_id,
                self.channel_id,
                self.ai_name,
                1
            )
            
            if not next_gen:
                await interaction.followup.send(
                    "❌ No next generation available.",
                    ephemeral=True
                )
                return
            
            # Get channel
            channel = interaction.guild.get_channel(int(self.channel_id))
            if not channel:
                await interaction.followup.send(
                    "❌ Channel not found.",
                    ephemeral=True
                )
                return
            
            # Update messages in Discord
            from utils.message_sender import get_message_sender
            sender = get_message_sender()
            
            mode = self.session.get("mode", "webhook")
            webhook_url = self.session.get("webhook_url")
            
            # Get current generation's discord IDs to update
            state = response_manager.get_state(self.server_id, self.channel_id, self.ai_name)
            current_gen = state.get_current()
            info = state.get_info()
            
            if current_gen and current_gen.discord_ids:
                await sender.edit_messages(
                    channel=channel,
                    message_ids=current_gen.discord_ids,
                    new_text=next_gen.text,
                    mode=mode,
                    webhook_url=webhook_url,
                    split_message_fn=None
                )
            
            # Update button states
            self._update_button_states()
            
            # Update the view
            await interaction.edit_original_response(view=self)
            
            log.info(f"Navigated to next generation ({info['current_number']}/{info['total_count']}) for AI {self.ai_name}")
            
        except Exception as e:
            log.error(f"Error navigating to next: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )
    
    async def _handle_regenerate(self, interaction: discord.Interaction):
        """Regenerate the current response by editing the existing message."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            response_manager = self.bot.message_pipeline.response_manager
            state = response_manager.get_state(self.server_id, self.channel_id, self.ai_name)
            current_gen = state.get_current()
            
            # Debug: Log state before regeneration
            info = state.get_info()
            log.info(
                f"Starting regeneration for AI {self.ai_name}: "
                f"current_gen={info['current_number']}/{info['total_count']}, "
                f"user_message={state.user_message[:50] if state.user_message else 'None'}..."
            )
            
            if not current_gen:
                await interaction.followup.send(
                    "❌ No message to regenerate.",
                    ephemeral=True
                )
                return
            
            if not state.user_message:
                await interaction.followup.send(
                    "❌ No user message found for regeneration.",
                    ephemeral=True
                )
                return
            
            # Get channel
            channel = interaction.guild.get_channel(int(self.channel_id))
            if not channel:
                await interaction.followup.send(
                    "❌ Channel not found.",
                    ephemeral=True
                )
                return
            
            # Edit message to show "Regenerating..." placeholder
            from utils.message_sender import get_message_sender
            sender = get_message_sender()
            
            mode = self.session.get("mode", "webhook")
            webhook_url = self.session.get("webhook_url")
            
            placeholder_id = await sender.set_generating_placeholder(
                channel=channel,
                message_ids=current_gen.discord_ids,
                mode=mode,
                webhook_url=webhook_url
            )
            
            if not placeholder_id:
                await interaction.followup.send(
                    "❌ Could not edit message for regeneration.",
                    ephemeral=True
                )
                return
            
            # Remove last 2 messages from history (user + assistant)
            from AI.chat_service import get_service
            chat_service = get_service()
            
            current_chat_id = self.session.get("chat_id", "default")
            history = chat_service.get_ai_history(
                self.server_id,
                self.channel_id,
                self.ai_name,
                current_chat_id
            )
            
            # extrac the actual user message BEFORE removing it
            # This ensures we use the edited version from ConversationStore
            actual_user_message = None
            if len(history) >= 2:
                # Find the last user message in history (edited version)
                for msg in reversed(history):
                    if msg["role"] == "user":
                        actual_user_message = msg["content"]
                        break
                
                # Now remove last 2 messages
                updated_history = history[:-2]
                await chat_service.set_ai_history(
                    self.server_id,
                    self.channel_id,
                    self.ai_name,
                    updated_history,
                    current_chat_id
                )
            
            # Use the EDITED message from ConversationStore
            # Fallback to state.user_message only if extraction failed
            user_msg_content = actual_user_message if actual_user_message else state.user_message
            
            # Log if we're using fallback
            if not actual_user_message:
                log.warning(
                    f"Could not extract user message from history for regeneration, "
                    f"using ResponseManager fallback for AI {self.ai_name}"
                )
            else:
                log.debug(
                    f"Using edited user message from ConversationStore for regeneration "
                    f"(length: {len(user_msg_content)})"
                )
            
            await interaction.followup.send(
                "🔄 Regenerating response...",
                ephemeral=True
            )
            
            # Add user message back to buffer for regeneration
            from messaging.buffer import PendingMessage
            import time as time_module
            
            regen_id = str(int(time_module.time() * 1000000))
            
            pending_msg = PendingMessage(
                content=user_msg_content,  # ✅ Uses edited version from ConversationStore
                author_id="0",
                author_name="User",
                author_display_name="User",
                timestamp=time_module.time(),
                message_id=regen_id,
                reply_to=None,
                raw_message=None
            )
            
            await self.bot.message_pipeline.buffer.add_message(
                self.server_id,
                self.channel_id,
                self.ai_name,
                pending_msg
            )
            
            # Store discord_ids from send_callback
            discord_ids = []
            
            # Generate new response and edit existing message
            async def send_callback(response_text, ids_list):
                """Edit existing message with new response."""
                # Edit the placeholder message with new content
                updated_ids = await sender.edit_messages(
                    channel=channel,
                    message_ids=[placeholder_id],
                    new_text=response_text,
                    mode=mode,
                    webhook_url=webhook_url,
                    split_message_fn=None
                )
                
                ids_list.extend(updated_ids)
                # NOTE: Don't create buttons here! ResponseManager hasn't been updated yet.
            
            result = await self.bot.message_pipeline.generate_response(
                self.server_id,
                self.channel_id,
                self.ai_name,
                self.session,
                chat_service,
                send_callback,
                is_regeneration=True  # Preserve existing generations
            )
            
            if result:
                response_text, result_discord_ids = result
                discord_ids.extend(result_discord_ids)
                
                # Debug: Log state after regeneration
                final_state = response_manager.get_state(self.server_id, self.channel_id, self.ai_name)
                final_info = final_state.get_info()
                log.info(
                    f"Regeneration complete for AI {self.ai_name}: "
                    f"final_gen={final_info['current_number']}/{final_info['total_count']}"
                )
                
                # NOW create buttons AFTER ResponseManager has been updated
                if discord_ids:
                    try:
                        from utils.message_actions import MessageActionsView
                        
                        new_view = MessageActionsView(
                            bot=self.bot,
                            server_id=self.server_id,
                            channel_id=self.channel_id,
                            ai_name=self.ai_name,
                            session=self.session,
                            timeout=None
                        )
                        
                        # Attach view to last message
                        from utils.message_cache import fetch_message_cached
                        
                        last_msg_id = discord_ids[-1]
                        last_msg = await fetch_message_cached(channel, last_msg_id)
                        if last_msg:
                            await last_msg.edit(view=new_view)
                        
                        log.debug(f"Reattached buttons after regeneration with correct state: {final_info['current_number']}/{final_info['total_count']}")
                        
                    except Exception as e:
                        log.error(f"Error reattaching buttons after regeneration: {e}")
            
        except Exception as e:
            log.error(f"Error during regeneration: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error during regeneration: {str(e)}",
                ephemeral=True
            )
    
    async def _handle_delete(self, interaction: discord.Interaction):
        """Delete the current message."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            response_manager = self.bot.message_pipeline.response_manager
            state = response_manager.get_state(self.server_id, self.channel_id, self.ai_name)
            current_gen = state.get_current()
            
            if not current_gen:
                await interaction.followup.send(
                    "❌ No message to delete.",
                    ephemeral=True
                )
                return
            
            # Get channel
            channel = interaction.guild.get_channel(int(self.channel_id))
            if not channel:
                await interaction.followup.send(
                    "❌ Channel not found.",
                    ephemeral=True
                )
                return
            
            # Delete messages from Discord
            deleted_count = 0
            from utils.message_cache import fetch_message_cached, get_message_cache
            cache = get_message_cache()
            
            for msg_id in current_gen.discord_ids:
                try:
                    msg = await fetch_message_cached(channel, msg_id)
                    if msg:
                        await msg.delete()
                        deleted_count += 1
                        # Invalidate cache after deletion
                        await cache.invalidate(self.channel_id, msg_id)
                except discord.NotFound:
                    log.warning(f"Message {msg_id} not found, skipping")
                except Exception as e:
                    log.error(f"Error deleting message {msg_id}: {e}")
            
            # Remove from ResponseManager
            response_manager.clear(self.server_id, self.channel_id, self.ai_name)
            
            # Remove only the assistant message from history that corresponds to this generation
            from AI.chat_service import get_service
            chat_service = get_service()
            
            current_chat_id = self.session.get("chat_id", "default")
            history = chat_service.get_ai_history(
                self.server_id,
                self.channel_id,
                self.ai_name,
                current_chat_id
            )
            
            # Find and remove the assistant message that matches the deleted discord_ids
            updated_history = []
            removed_assistant = False
            for msg in history:
                # Skip the assistant message that matches the deleted generation
                if msg["role"] == "assistant" and not removed_assistant:
                    # Check if this assistant message matches the deleted generation
                    # by comparing the text content
                    if msg["content"] == current_gen.text:
                        removed_assistant = True
                        continue  # Skip this message
                updated_history.append(msg)
            
            await chat_service.set_ai_history(
                self.server_id,
                self.channel_id,
                self.ai_name,
                updated_history,
                current_chat_id
            )
            
            await interaction.followup.send(
                f"✅ Deleted {deleted_count} message(s) from Discord and removed from history.",
                ephemeral=True
            )
            
            log.info(f"Message deleted for AI {self.ai_name} in channel {self.channel_id}")
            
        except Exception as e:
            log.error(f"Error deleting message: {e}", exc_info=True)
            await interaction.followup.send(
                f"❌ Error deleting message: {str(e)}",
                ephemeral=True
            )
    
    async def _handle_edit(self, interaction: discord.Interaction):
        """Open modal to edit the current message."""
        try:
            response_manager = self.bot.message_pipeline.response_manager
            state = response_manager.get_state(self.server_id, self.channel_id, self.ai_name)
            current_gen = state.get_current()
            
            if not current_gen:
                await interaction.response.send_message(
                    "❌ No message to edit.",
                    ephemeral=True
                )
                return
            
            # Open edit modal
            modal = EditMessageModal(
                bot=self.bot,
                server_id=self.server_id,
                channel_id=self.channel_id,
                ai_name=self.ai_name,
                current_text=current_gen.text,
                session=self.session
            )
            
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            log.error(f"Error opening edit modal: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )
    
    async def on_timeout(self):
        """Called when the view times out."""
        try:
            # Disable all buttons
            for item in self.children:
                if isinstance(item, ui.Button):
                    item.disabled = True
            
            log.debug(f"MessageActionsView timed out for AI {self.ai_name}")
            
        except Exception as e:
            log.error(f"Error handling view timeout: {e}")
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
        """Handle view errors."""
        log.error(f"View error: {error}", exc_info=True)
        try:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(error)}",
                ephemeral=True
            )
        except:
            pass
