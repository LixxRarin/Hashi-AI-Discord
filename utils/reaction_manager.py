"""
Reaction Manager - Navigation Reaction Management

This module manages navigation reactions (◀️, ▶️, 🔄) on AI messages,
ensuring that only the most recent generation has active reactions.

Key Features:
- Remove reactions from old messages
- Add reactions to new messages
- Robust error handling
- Support for multiple messages per generation
"""

import logging
import discord
from typing import List, Optional

log = logging.getLogger(__name__)


class ReactionManager:
    """
    Manages navigation reactions between response generations.
    
    Ensures that only the most recent generation has active reactions,
    automatically removing reactions from previous generations.
    
    Example:
        manager = ReactionManager()
        await manager.update_reactions(
            channel=channel,
            old_message_ids=["123", "456"],
            new_message_ids=["789"]
        )
    """
    
    DEFAULT_REACTIONS = ["◀️", "▶️", "🔄"]
    
    def __init__(self):
        """Initialize the reaction manager."""
        pass
    
    async def update_reactions(
        self,
        channel: discord.TextChannel,
        old_message_ids: List[str],
        new_message_ids: List[str],
        reactions: Optional[List[str]] = None
    ) -> None:
        """
        Updates reactions: removes from old messages, adds to new ones.
        
        Args:
            channel: Discord channel
            old_message_ids: IDs of old messages (remove reactions)
            new_message_ids: IDs of new messages (add reactions)
            reactions: List of emojis (default: ["◀️", "▶️", "🔄"])
        """
        if reactions is None:
            reactions = self.DEFAULT_REACTIONS
        
        # Remove reactions from old messages
        await self._remove_reactions(channel, old_message_ids, reactions)
        
        # Add reactions to new messages (only on the last one)
        await self._add_reactions(channel, new_message_ids, reactions)
    
    async def _remove_reactions(
        self,
        channel: discord.TextChannel,
        message_ids: List[str],
        reactions: List[str]
    ) -> None:
        """
        Removes specific reactions from a list of messages.
        
        Args:
            channel: Discord channel
            message_ids: Message IDs
            reactions: List of emojis to remove
        """
        for msg_id in message_ids:
            try:
                message = await channel.fetch_message(int(msg_id))
                
                # Remove each reaction
                for emoji in reactions:
                    try:
                        await message.clear_reaction(emoji)
                    except discord.HTTPException as e:
                        # Reaction may not exist, ignore
                        log.debug(f"Could not remove reaction {emoji} from message {msg_id}: {e}")
                
                log.debug(f"Removed reactions from message {msg_id}")
                
            except discord.NotFound:
                log.debug(f"Message {msg_id} not found (may have been deleted)")
            except discord.Forbidden:
                log.warning(f"No permission to remove reactions from message {msg_id}")
            except Exception as e:
                log.error(f"Error removing reactions from message {msg_id}: {e}")
    
    async def _add_reactions(
        self,
        channel: discord.TextChannel,
        message_ids: List[str],
        reactions: List[str]
    ) -> None:
        """
        Adds reactions to the last message in the list.
        
        Args:
            channel: Discord channel
            message_ids: Message IDs (only the last one will receive reactions)
            reactions: List of emojis to add
        """
        if not message_ids:
            return
        
        # Add reactions only to the last message
        last_msg_id = message_ids[-1]
        
        try:
            message = await channel.fetch_message(int(last_msg_id))
            
            # Add each reaction
            for emoji in reactions:
                try:
                    await message.add_reaction(emoji)
                except discord.HTTPException as e:
                    log.warning(f"Could not add reaction {emoji} to message {last_msg_id}: {e}")
            
            log.debug(f"Added reactions to message {last_msg_id}")
            
        except discord.NotFound:
            log.warning(f"Message {last_msg_id} not found (may have been deleted)")
        except discord.Forbidden:
            log.warning(f"No permission to add reactions to message {last_msg_id}")
        except Exception as e:
            log.error(f"Error adding reactions to message {last_msg_id}: {e}")


# Global manager instance
_global_manager: Optional[ReactionManager] = None


def get_reaction_manager() -> ReactionManager:
    """Get the global reaction manager instance."""
    global _global_manager
    if _global_manager is None:
        _global_manager = ReactionManager()
    return _global_manager
