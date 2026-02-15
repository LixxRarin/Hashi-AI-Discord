"""
Webhook utilities for Discord bot operations.

Handles webhook creation, deletion, and message sending with automatic splitting.
"""
from typing import List, Optional

import aiohttp
import discord

import utils.func as func


class WebhookUtils:
    """Utilities for webhook operations."""
    
    @staticmethod
    async def send_message(
        url: str,
        message: str,
        session_config: dict,
        return_messages: bool = False
    ) -> Optional[List]:
        """
        Send a message via webhook with automatic splitting for messages >2000 characters.
        
        Args:
            url: Webhook URL
            message: Message content to send
            session_config: Session configuration (contains send_message_line_by_line setting)
            return_messages: If True, return list of sent message objects
            
        Returns:
            List of sent message objects if return_messages=True, None otherwise
        """
        sent_messages = []
        
        try:
            async with aiohttp.ClientSession() as session:
                webhook_obj = discord.Webhook.from_url(url, session=session)
                
                if session_config.get("config", {}).get("send_message_line_by_line", False):
                    # Send line by line
                    lines = message.split('\n')
                    for line in lines:
                        if line.strip():
                            # Split line if it exceeds Discord's limit
                            line_chunks = WebhookUtils.split_text(line)
                            for chunk in line_chunks:
                                try:
                                    sent_msg = await webhook_obj.send(chunk, wait=True)
                                    if return_messages:
                                        sent_messages.append(sent_msg)
                                except discord.HTTPException as e:
                                    func.log.error(f"Failed to send webhook line chunk: {e}")
                else:
                    # Send as complete message(s)
                    message_chunks = WebhookUtils.split_text(message)
                    for chunk in message_chunks:
                        try:
                            sent_msg = await webhook_obj.send(chunk, wait=True)
                            if return_messages:
                                sent_messages.append(sent_msg)
                        except discord.HTTPException as e:
                            func.log.error(f"Failed to send webhook message chunk: {e}")
            
            return sent_messages if return_messages else None
            
        except Exception as e:
            func.log.error(f"Error sending webhook message: {e}")
            return sent_messages if return_messages else None
    
    @staticmethod
    async def create_webhook(
        channel: discord.TextChannel,
        name: str,
        avatar_bytes: Optional[bytes] = None
    ) -> Optional[str]:
        """
        Create a webhook in the specified channel.
        
        Args:
            channel: Discord text channel to create webhook in
            name: Name for the webhook
            avatar_bytes: Optional avatar image bytes
            
        Returns:
            Webhook URL if successful, None otherwise
        """
        try:
            webhook_obj = await channel.create_webhook(
                name=name,
                avatar=avatar_bytes if avatar_bytes else None,
                reason=f"Webhook - {name}"
            )
            func.log.debug(f"Created webhook with URL: {webhook_obj.url}")
            return webhook_obj.url
            
        except discord.Forbidden:
            func.log.error(f"No permission to create webhooks in channel {channel.id}")
            return None
        except discord.HTTPException as e:
            func.log.error(f"HTTP error creating webhook: {e}")
            return None
        except Exception as e:
            func.log.error(f"Error creating webhook: {e}")
            return None
    
    @staticmethod
    async def edit_webhook(
        url: str,
        name: Optional[str] = None,
        avatar_bytes: Optional[bytes] = None
    ) -> bool:
        """
        Edit an existing webhook.
        
        Args:
            url: Webhook URL
            name: New name for the webhook (optional)
            avatar_bytes: New avatar image bytes (optional)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            async with aiohttp.ClientSession() as session:
                webhook_obj = discord.Webhook.from_url(url, session=session)
                
                kwargs = {}
                if name is not None:
                    kwargs['name'] = name
                if avatar_bytes is not None:
                    kwargs['avatar'] = avatar_bytes
                
                if kwargs:
                    await webhook_obj.edit(**kwargs)
                    func.log.debug(f"Edited webhook: {url}")
                    return True
                    
            return False
            
        except Exception as e:
            func.log.error(f"Error editing webhook: {e}")
            return False
    
    @staticmethod
    async def delete_webhook(url: str) -> bool:
        """
        Delete a webhook by URL.
        
        Args:
            url: Webhook URL to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            async with aiohttp.ClientSession() as session:
                webhook_obj = discord.Webhook.from_url(url, session=session)
                await webhook_obj.delete()
                func.log.debug(f"Deleted webhook: {url}")
                return True
                
        except Exception as e:
            func.log.error(f"Error deleting webhook: {e}")
            return False
    
    @staticmethod
    def split_text(text: str, max_len: int = 2000) -> List[str]:
        """
        Split text into chunks that don't exceed Discord's message length limit.
        
        Tries to split at newlines first, then spaces, then hard splits if necessary.
        
        Args:
            text: Text to split
            max_len: Maximum length per chunk (default: 2000 for Discord)
            
        Returns:
            List of text chunks
        """
        if len(text) <= max_len:
            return [text]
        
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            
            # Try to split at newline
            split_pos = text.rfind('\n', 0, max_len)
            if split_pos == -1:
                # Try to split at space
                split_pos = text.rfind(' ', 0, max_len)
            if split_pos == -1:
                # Hard split
                split_pos = max_len
            
            chunks.append(text[:split_pos])
            text = text[split_pos:].lstrip()
        
        return chunks
