import asyncio
import time
import uuid
from typing import Dict, Any, Optional, Set, List

import aiohttp
import discord

import AI.openai_client as openai_client
import AI.deepseek_client as deepseek_client
from AI.chat_service import get_service
from AI.response_queue import get_queue
import utils.func as func


class discord_AI_bot:
    def __init__(self):
        """Initialize the bot's tracking variables."""
        # Track active response tasks by channel ID
        self.active_tasks: Dict[str, asyncio.Task] = {}

        self._typing_debounce_tasks: Dict[str, asyncio.Task] = {}
        self._typing_debounce_delay = 0.5  # 0.5 seconds

    async def sync_config(self, client):
        """
        Synchronize each webhook's profile (name and avatar) with cached data.
        
        No API calls are made during sync. Only uses cached data
        from character cards or session configuration.

        Args:
            client: The Discord client
        """
        func.log.info("Synchronizing webhook configurations (no API calls)")
        
        for server_id, server_info in func.session_cache.items():
            for channel_id, channel_data in server_info.get("channels", {}).items():
                # Process each AI in the channel
                for ai_name, session_data in channel_data.items():
                    webhook_url = session_data.get("webhook_url")
                    if not webhook_url:
                        continue
                    
                    try:
                        config = session_data.get("config", {})
                        use_display_name = config.get("use_card_ai_display_name", True)
                        
                        # Get webhook name from AI name or character card
                        webhook_name = ai_name
                        avatar_bytes = None
                        
                        # Try to get avatar from character card if available
                        card_data = session_data.get("character_card", {}).get("data", {})
                        if card_data:
                            # Use character card name if available
                            char_name = card_data.get("nickname") or card_data.get("name")
                            if char_name and use_display_name:
                                webhook_name = char_name
                            
                            # Try to load avatar from cached character card file
                            cache_path = session_data.get("character_card", {}).get("cache_path")
                            if cache_path:
                                try:
                                    from pathlib import Path
                                    card_file = Path(cache_path)
                                    
                                    if card_file.exists():
                                        # For PNG files, the file itself is the avatar
                                        with open(card_file, 'rb') as f:
                                            data = f.read()
                                        
                                        # Check if it's a PNG file
                                        if data[:8] == b'\x89PNG\r\n\x1a\n':
                                            avatar_bytes = data
                                            func.log.debug(f"Loaded avatar from PNG card file for AI {ai_name}")
                                        # For CHARX files, would need to extract from ZIP
                                        elif card_file.suffix.lower() == '.charx':
                                            import zipfile
                                            try:
                                                with zipfile.ZipFile(card_file, 'r') as zf:
                                                    # Look for avatar in assets
                                                    for name in zf.namelist():
                                                        if 'icon' in name.lower() or 'avatar' in name.lower():
                                                            avatar_bytes = zf.read(name)
                                                            func.log.debug(f"Extracted avatar from CHARX for AI {ai_name}")
                                                            break
                                            except Exception as e:
                                                func.log.debug(f"Failed to extract avatar from CHARX: {e}")
                                except Exception as e:
                                    func.log.debug(f"Could not load character card avatar: {e}")
                        
                        # Update webhook with cached data only
                        async with aiohttp.ClientSession() as http_session:
                            webhook_obj = discord.Webhook.from_url(webhook_url, session=http_session)
                            
                            if avatar_bytes:
                                await webhook_obj.edit(
                                    name=webhook_name,
                                    avatar=avatar_bytes,
                                    reason="Sync webhook info (cached)"
                                )
                            else:
                                await webhook_obj.edit(
                                    name=webhook_name,
                                    reason="Sync webhook info (cached)"
                                )
                            
                            func.log.info(
                                "Updated webhook for AI %s in channel %s (no API call)",
                                ai_name, channel_id
                            )
                    except Exception as e:
                        func.log.error(
                            "Failed to update webhook for AI %s in channel %s: %s",
                            ai_name, channel_id, e
                        )
        
        func.log.info("Webhook synchronization complete (0 API calls made)")

    async def _get_or_create_chat_id(self, session: Dict[str, Any], server_id: str, channel_id_str: str) -> Optional[str]:
        """
        Get or create a chat ID based on the provider.
        
        Args:
            session: The AI session data
            server_id: The server ID
            channel_id_str: The channel ID
            
        Returns:
            The chat ID or None if failed
        """
        provider = session.get("provider", "openai")
        create_new_chat = session.get("config", {}).get("new_chat_on_reset", False)
        
        if provider in ["openai", "deepseek"]:
            service = get_service()
            chat_id, _ = await service.new_chat_id(
                create_new_chat, session, server_id, channel_id_str
            )
        else:
            func.log.error(
                "Unsupported provider for chat_id creation: %s", provider)
            return None
        
        return chat_id

    def _split_message(self, text: str, max_length: int = 2000) -> List[str]:
        """
        Split a message into chunks that don't exceed Discord's character limit.
        Tries to split at natural boundaries (newlines, spaces) when possible.
        
        Args:
            text: The text to split
            max_length: Maximum length per chunk (default: 2000 for Discord)
            
        Returns:
            List of message chunks
        """
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # Split by lines first
        lines = text.split('\n')
        
        for line in lines:
            # If a single line is too long, split it by spaces
            if len(line) > max_length:
                words = line.split(' ')
                for word in words:
                    # If a single word is too long, hard split it
                    if len(word) > max_length:
                        # Add current chunk if it exists
                        if current_chunk:
                            chunks.append(current_chunk)
                            current_chunk = ""
                        
                        # Hard split the word
                        for i in range(0, len(word), max_length):
                            chunks.append(word[i:i + max_length])
                    else:
                        # Check if adding this word would exceed the limit
                        test_chunk = current_chunk + (' ' if current_chunk else '') + word
                        if len(test_chunk) > max_length:
                            if current_chunk:
                                chunks.append(current_chunk)
                            current_chunk = word
                        else:
                            current_chunk = test_chunk
            else:
                # Check if adding this line would exceed the limit
                test_chunk = current_chunk + ('\n' if current_chunk else '') + line
                if len(test_chunk) > max_length:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = line
                else:
                    current_chunk = test_chunk
        
        # Add the last chunk if it exists
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

    async def handle_regeneration_reaction(self, client, payload, response_manager):
        """
        Handle regeneration when user reacts with 🔄 on an AI message.
        Uses ResponseManager to find messages (searches all generations).
        
        Args:
            client: The Discord client
            payload: The reaction payload
            response_manager: The ResponseManager instance from message pipeline
        """
        try:
            message_id = str(payload.message_id)
            server_id = str(payload.guild_id)
            channel_id = str(payload.channel_id)
            
            # Find which AI owns this message by checking ResponseManager (all generations)
            ai_name = None
            generation_index = -1
            
            # Debug: Log all tracked messages
            func.log.debug(f"Looking for message {message_id} in ResponseManager")
            for srv_id, srv_data in response_manager._responses.items():
                if srv_id != server_id:
                    continue
                for ch_id, ch_data in srv_data.items():
                    if ch_id != channel_id:
                        continue
                    for ai, state in ch_data.items():
                        func.log.debug(f"AI {ai} has {len(state.generations)} generation(s)")
                        # Search through ALL generations, not just current
                        for idx, gen in enumerate(state.generations):
                            func.log.debug(f"Generation {idx} has discord_ids: {gen.discord_ids}")
                            if message_id in gen.discord_ids:
                                ai_name = ai
                                generation_index = idx
                                func.log.debug(f"Found message in AI {ai}, generation {idx}")
                                break
                        if ai_name:
                            break
                    if ai_name:
                        break
                if ai_name:
                    break
            
            if not ai_name:
                func.log.warning(f"Message {message_id} not found in ResponseManager")
                func.log.debug(f"Available AIs in channel: {list(response_manager._responses.get(server_id, {}).get(channel_id, {}).keys())}")
                return
            
            session_data = func.get_session_data(server_id, channel_id)
            if not session_data or ai_name not in session_data:
                func.log.debug(f"No session data for AI {ai_name}")
                return
            
            func.log.debug(f"Triggered for AI {ai_name} in channel {channel_id} (generation {generation_index + 1})")
            
            # Get channel and session
            channel = client.get_channel(int(channel_id))
            if not channel:
                func.log.error(f"Channel {channel_id} not found")
                return
            
            session = session_data[ai_name]
            chat_id = session.get("chat_id", "default")
            
            # Get the state and the specific generation
            state = response_manager.get_state(server_id, channel_id, ai_name)
            
            if generation_index < 0 or generation_index >= len(state.generations):
                func.log.warning(f"Invalid generation index {generation_index} for AI {ai_name}")
                return
            
            target_generation = state.generations[generation_index]
            
            # Edit first message to "Gerando..." instead of deleting
            from utils.message_sender import get_message_sender
            sender = get_message_sender()
            
            placeholder_msg_id = await sender.set_generating_placeholder(
                channel=channel,
                message_ids=target_generation.discord_ids,
                mode=session.get("mode", "webhook"),
                webhook_url=session.get("webhook_url")
            )
            
            func.log.debug(f"Set placeholder 'Generating...' for AI {ai_name} (message: {placeholder_msg_id})")
            
            # Get conversation store and find the message in history
            from messaging.store import get_store
            store = get_store()
            history = await store.get_full_history(server_id, channel_id, ai_name, chat_id)
            
            # Find the assistant message in history that matches this generation
            message_index = -1
            for i, msg in enumerate(history):
                if msg.role == "assistant" and msg.discord_ids:
                    # Check if any discord_id from history matches the target generation
                    if any(did in target_generation.discord_ids for did in msg.discord_ids):
                        message_index = i
                        break
            
            # Truncate history at the found message
            if message_index > 0:
                # Keep messages before the user message that triggered this response
                # (message_index - 1 is the user message, so we keep everything before it)
                messages_to_keep = history[:message_index - 1] if message_index > 0 else []
                
                await store.clear_history(server_id, channel_id, ai_name, chat_id, keep_greeting=False)
                
                for msg in messages_to_keep:
                    if msg.role == "user":
                        await store.add_user_message(
                            server_id, channel_id, ai_name,
                            msg.content, msg.discord_id or "", chat_id
                        )
                    else:
                        await store.add_assistant_message(
                            server_id, channel_id, ai_name,
                            msg.content, msg.discord_ids or [], chat_id,
                            short_id=msg.short_id
                        )
                
                func.log.debug(f"Truncated history at message index {message_index} for AI {ai_name}")
            elif len(history) >= 2:
                # Fallback: if not found in history, remove last 2 messages
                updated_history = history[:-2]
                await store.clear_history(server_id, channel_id, ai_name, chat_id, keep_greeting=False)
                
                for msg in updated_history:
                    if msg.role == "user":
                        await store.add_user_message(
                            server_id, channel_id, ai_name,
                            msg.content, msg.discord_id or "", chat_id
                        )
                    else:
                        await store.add_assistant_message(
                            server_id, channel_id, ai_name,
                            msg.content, msg.discord_ids or [], chat_id,
                            short_id=msg.short_id
                        )
                
                func.log.debug(f"Removed last 2 messages from history for AI {ai_name} (fallback)")
            
            # Trigger regeneration using the user message from ResponseManager state
            if state.user_message:
                func.log.info(f"Triggering regeneration for AI {ai_name} with user message: {state.user_message[:50]}...")
                
                # Get the message pipeline from the bot
                if hasattr(client, 'message_pipeline'):
                    pipeline = client.message_pipeline
                    
                    # Add user message back to buffer for regeneration
                    from messaging.buffer import PendingMessage
                    import time as time_module
                    
                    # Generate unique numeric ID for regeneration (timestamp-based)
                    regen_id = str(int(time_module.time() * 1000000))
                    
                    pending_msg = PendingMessage(
                        content=state.user_message,
                        author_id="0",  # Placeholder
                        author_name="User",
                        author_display_name="User",  # Required parameter
                        timestamp=time.time(),
                        message_id=regen_id,  # Unique numeric ID
                        reply_to=None,
                        raw_message=None
                    )
                    
                    await pipeline.buffer.add_message(
                        server_id,
                        channel_id,
                        ai_name,
                        pending_msg
                    )
                    
                    # Create a callback for sending to Discord using centralized MessageSender
                    async def send_callback(response_text, ids_list):
                        """Edit existing message or send new response to Discord."""
                        from utils.message_sender import get_message_sender
                        sender = get_message_sender()
                        
                        # Try to edit existing message if placeholder was set
                        if placeholder_msg_id:
                            discord_ids = await sender.edit_messages(
                                channel=channel,
                                message_ids=[placeholder_msg_id],
                                new_text=response_text,
                                mode=session.get("mode", "webhook"),
                                webhook_url=session.get("webhook_url"),
                                split_message_fn=self._split_message
                            )
                        else:
                            # Fallback: create new messages if editing failed
                            discord_ids = await sender.send(
                                response_text=response_text,
                                channel=channel,
                                session=session,
                                split_message_fn=self._split_message
                            )
                        
                        ids_list.extend(discord_ids)
                    
                    # Generate new response
                    from AI.chat_service import get_service
                    chat_service = get_service()
                    
                    result = await pipeline.generate_response(
                        server_id,
                        channel_id,
                        ai_name,
                        session,
                        chat_service,
                        send_callback
                    )
                    
                    if result:
                        response, discord_ids = result
                        # Update reactions using ReactionManager
                        # Old messages already deleted, so pass empty list
                        if session.get("config", {}).get("auto_add_generation_reactions", False):
                            try:
                                from utils.reaction_manager import get_reaction_manager
                                reaction_mgr = get_reaction_manager()
                                await reaction_mgr.update_reactions(
                                    channel=channel,
                                    old_message_ids=[],  # Already deleted above
                                    new_message_ids=discord_ids
                                )
                            except Exception as e:
                                func.log.error("Error managing reactions: %s", e)
                    
                    func.log.info(f"Regeneration complete for AI {ai_name}")
                else:
                    func.log.error("Message pipeline not found on bot instance")
            else:
                func.log.warning(f"No user message found for regeneration for AI {ai_name}")
                
        except Exception as e:
            func.log.error(f"Error in handle_regeneration_reaction: {e}")
    
 
    
    async def handle_generation_navigation(self, client, payload, emoji, response_manager):
        """
        Handle navigation between different generations using reactions.
        Uses the new ResponseManager system!
        
        Args:
            client: The Discord bot instance
            payload: The reaction payload
            emoji: The emoji used (◀️ or ▶️)
            response_manager: The ResponseManager instance from message pipeline
        """
        try:
            server_id = str(payload.guild_id)
            channel_id = str(payload.channel_id)
            message_id = str(payload.message_id)
            
            # Find which AI owns this message
            ai_name = None
            for srv_id, srv_data in response_manager._responses.items():
                if srv_id != server_id:
                    continue
                for ch_id, ch_data in srv_data.items():
                    if ch_id != channel_id:
                        continue
                    for ai, state in ch_data.items():
                        current = state.get_current()
                        if current and message_id in current.discord_ids:
                            ai_name = ai
                            break
                    if ai_name:
                        break
                if ai_name:
                    break
            
            if not ai_name:
                func.log.warning(f"Message {message_id} not found in ResponseManager, ignoring")
                return
            
            # Navigate in ResponseManager
            direction = -1 if emoji == "◀️" else 1
            
            # Get current state before navigation
            state = response_manager.get_state(server_id, channel_id, ai_name)
            old_index = state.current_index
            
            # Navigate
            new_generation = response_manager.navigate(server_id, channel_id, ai_name, direction)
            
            if not new_generation:
                func.log.debug(f"No {'previous' if direction == -1 else 'next'} generation available for AI {ai_name}")
                return
            
            # Get generation info for feedback
            gen_info = response_manager.get_info(server_id, channel_id, ai_name)
            
            # Get channel and session
            channel = client.get_channel(int(channel_id))
            if not channel:
                func.log.error(f"Channel {channel_id} not found")
                return
            
            session_data = func.get_session_data(server_id, channel_id)
            if not session_data or ai_name not in session_data:
                func.log.error(f"Session data not found for AI {ai_name}")
                return
            
            session = session_data[ai_name]
            
            # Edit old messages to show "Generating..." instead of deleting
            placeholder_msg_id = None
            if 0 <= old_index < len(state.generations):
                old_gen = state.generations[old_index]
                
                from utils.message_sender import get_message_sender
                sender = get_message_sender()
                
                placeholder_msg_id = await sender.set_generating_placeholder(
                    channel=channel,
                    message_ids=old_gen.discord_ids,
                    mode=session.get("mode", "webhook"),
                    webhook_url=session.get("webhook_url")
                )
                
                func.log.debug(f"Set placeholder 'Generating...' for navigation (message: {placeholder_msg_id})")
            
            # Prepare new generation text
            response_text = new_generation.text
            
            # Add generation indicator
            generation_indicator = f"_[{gen_info['current_number']}/{gen_info['total_count']}]_\n\n"
            response_text_with_indicator = generation_indicator + response_text
            
            # Edit existing message or send new one
            from utils.message_sender import get_message_sender
            sender = get_message_sender()
            
            if placeholder_msg_id:
                # Edit existing message
                new_discord_ids = await sender.edit_messages(
                    channel=channel,
                    message_ids=[placeholder_msg_id],
                    new_text=response_text_with_indicator,
                    mode=session.get("mode", "webhook"),
                    webhook_url=session.get("webhook_url"),
                    split_message_fn=self._split_message
                )
            else:
                # Fallback: create new messages if editing failed
                new_discord_ids = await sender.send(
                    response_text=response_text_with_indicator,
                    channel=channel,
                    session=session,
                    split_message_fn=self._split_message
                )
            
            # Update the generation's discord_ids with the new ones
            new_generation.discord_ids = new_discord_ids
            
            # Update reactions using ReactionManager
            if new_discord_ids:
                try:
                    from utils.reaction_manager import get_reaction_manager
                    reaction_mgr = get_reaction_manager()
                    await reaction_mgr.update_reactions(
                        channel=channel,
                        old_message_ids=[],  # Already deleted above
                        new_message_ids=new_discord_ids
                    )
                except Exception as e:
                    func.log.error(f"Error managing reactions: {e}")
            
            func.log.info(f"Navigated to generation {gen_info['current_number']}/{gen_info['total_count']} for AI {ai_name}")
            
        except Exception as e:
            func.log.error(f"Error in handle_generation_navigation_v2: {e}")
    
