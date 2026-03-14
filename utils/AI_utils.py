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
        func.log.info("Synchronizing webhook configurations")
        
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
    
