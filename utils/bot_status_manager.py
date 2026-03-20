"""
Bot Status Manager - Manages Discord bot status based on AI sleep states

This module tracks when AIs enter/exit sleep mode and updates the bot's
Discord status accordingly:
- If ANY AI is in sleep mode → Bot status = Idle (moon/away)
- If ALL AIs are awake → Bot status = Online (green)
"""

import asyncio
import logging
from typing import Optional, Set, Tuple

import discord

log = logging.getLogger(__name__)


class BotStatusManager:
    """
    Manages the Discord bot's status based on AI sleep states.
    
    The bot's status reflects the collective state of all AIs:
    - Idle (moon): At least one AI is in sleep mode
    - Online (green): All AIs are awake
    """
    
    def __init__(self, bot_client):
        """
        Initialize the Bot Status Manager.
        
        Args:
            bot_client: The Discord bot instance
        """
        self.bot = bot_client
        self.sleeping_ais: Set[Tuple[str, str, str]] = set()  # (server_id, channel_id, ai_name)
        self.lock = asyncio.Lock()  # Thread-safety for concurrent operations
        self._initialized = False
    
    async def on_ai_sleep(self, server_id: str, channel_id: str, ai_name: str) -> None:
        """
        Called when an AI enters sleep mode.
        
        If this is the first AI to sleep, changes bot status to Idle.
        
        Args:
            server_id: Discord server ID
            channel_id: Discord channel ID
            ai_name: Name of the AI
        """
        async with self.lock:
            was_empty = len(self.sleeping_ais) == 0
            state_key = (server_id, channel_id, ai_name)
            
            # Add to sleeping set (idempotent)
            self.sleeping_ais.add(state_key)
            
            # If this is the first AI to sleep, change bot status to Idle
            if was_empty and len(self.sleeping_ais) > 0:
                await self._set_idle()
                log.info(
                    f"Bot status changed to IDLE - AI {ai_name} entered sleep mode "
                    f"({len(self.sleeping_ais)} AI(s) sleeping)"
                )
            else:
                log.debug(
                    f"AI {ai_name} entered sleep mode "
                    f"({len(self.sleeping_ais)} AI(s) sleeping, bot already idle)"
                )
    
    async def on_ai_wake(self, server_id: str, channel_id: str, ai_name: str) -> None:
        """
        Called when an AI wakes up from sleep mode.
        
        If this is the last AI to wake, changes bot status to Online.
        
        Args:
            server_id: Discord server ID
            channel_id: Discord channel ID
            ai_name: Name of the AI
        """
        async with self.lock:
            state_key = (server_id, channel_id, ai_name)
            
            # Remove from sleeping set (idempotent)
            self.sleeping_ais.discard(state_key)
            
            # If all AIs are now awake, change bot status to Online
            if len(self.sleeping_ais) == 0:
                await self._set_online()
                log.info(
                    f"Bot status changed to ONLINE - AI {ai_name} woke up "
                    f"(all AIs now awake)"
                )
            else:
                log.debug(
                    f"AI {ai_name} woke up "
                    f"({len(self.sleeping_ais)} AI(s) still sleeping, bot remains idle)"
                )
    
    async def _set_idle(self) -> None:
        """
        Change bot status to Idle (moon/away icon).
        
        This is called when the first AI enters sleep mode.
        """
        try:
            await self.bot.change_presence(status=discord.Status.idle)
            log.info("Bot status changed to IDLE (sleep mode active)")
        except Exception as e:
            log.error(f"Failed to change bot status to Idle: {e}")
    
    async def _set_online(self) -> None:
        """
        Change bot status to Online (green icon).
        
        This is called when the last AI wakes up from sleep mode.
        """
        try:
            await self.bot.change_presence(status=discord.Status.online)
            log.info("Bot status changed to ONLINE (all AIs awake)")
        except Exception as e:
            log.error(f"Failed to change bot status to Online: {e}")
    
    async def initialize_from_sleep_states(self) -> None:
        """
        Initialize the sleeping AIs counter from existing sleep states.
        
        This is called during bot startup to restore the correct status
        based on persisted sleep states.
        """
        if self._initialized:
            log.debug("Bot Status Manager already initialized")
            return
        
        try:
            from AI.response_filter import get_response_filter
            response_filter = get_response_filter()
            
            # Scan all sleep states and add sleeping AIs to our set
            for state_key, state in response_filter.sleep_state.items():
                if state.get("in_sleep_mode", False):
                    server_id, channel_id, ai_name = state_key
                    self.sleeping_ais.add(state_key)
            
            # Update bot status based on initial state
            if len(self.sleeping_ais) > 0:
                await self._set_idle()
                log.info(
                    f"Bot Status Manager initialized with {len(self.sleeping_ais)} AI(s) "
                    f"in sleep mode - bot status set to IDLE"
                )
            else:
                await self._set_online()
                log.info(
                    "Bot Status Manager initialized with all AIs awake - "
                    "bot status set to ONLINE"
                )
            
            self._initialized = True
            
        except Exception as e:
            log.error(f"Failed to initialize Bot Status Manager: {e}")
            log.warning("Bot will continue with default Online status")
    
    def get_sleeping_count(self) -> int:
        """
        Get the current number of AIs in sleep mode.
        
        Returns:
            int: Number of sleeping AIs
        """
        return len(self.sleeping_ais)
    
    def is_any_ai_sleeping(self) -> bool:
        """
        Check if any AI is currently in sleep mode.
        
        Returns:
            bool: True if at least one AI is sleeping
        """
        return len(self.sleeping_ais) > 0


# Singleton instance
_bot_status_manager: Optional[BotStatusManager] = None


def get_bot_status_manager() -> Optional[BotStatusManager]:
    """
    Get the global BotStatusManager instance.
    
    Returns:
        BotStatusManager or None: The global instance, or None if not initialized
    """
    return _bot_status_manager


def set_bot_status_manager(manager: BotStatusManager) -> None:
    """
    Set the global BotStatusManager instance.
    
    Args:
        manager: The BotStatusManager instance to set as global
    """
    global _bot_status_manager
    _bot_status_manager = manager
    log.debug("Bot Status Manager singleton set")
