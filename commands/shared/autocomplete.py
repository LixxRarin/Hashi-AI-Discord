"""
Shared autocomplete functions for Discord commands.

This module centralizes all autocomplete logic to eliminate duplication
across command modules.
"""
from typing import List

import discord
from discord import app_commands

import utils.func as func
from AI.chat_service import get_service


class AutocompleteHelpers:
    """Shared autocomplete functions for all command cogs."""
    
    @staticmethod
    async def ai_name_all(
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """
        Autocomplete for ALL AI names in the server.
        
        Shows all AIs regardless of whether they have character cards.
        """
        try:
            server_id = str(interaction.guild.id)
            all_server_data = func.session_cache.get(server_id, {}).get("channels", {})
            
            if not all_server_data:
                return []
            
            choices = []
            for channel_id_str, channel_data in all_server_data.items():
                channel_obj = interaction.guild.get_channel(int(channel_id_str))
                channel_name = channel_obj.name if channel_obj else f"Deleted Channel ({channel_id_str})"

                for ai_name, ai_data in channel_data.items():
                    if current.lower() in ai_name.lower():
                        provider = ai_data.get("provider", "openai").upper()
                        display_name = f"{ai_name} [{provider}] (#{channel_name})"
                        choices.append(app_commands.Choice(name=display_name[:100], value=ai_name))
            
            return choices[:25]
        except Exception as e:
            func.log.error(f"Error in ai_name_all autocomplete: {e}")
            return []
    
    @staticmethod
    async def ai_name_with_cards(
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """
        Autocomplete for AI names that have character cards.
        
        Only shows AIs that have a character_card configured.
        """
        try:
            server_id = str(interaction.guild.id)
            all_server_data = func.session_cache.get(server_id, {}).get("channels", {})
            
            if not all_server_data:
                return []
            
            choices = []
            for channel_id_str, channel_data in all_server_data.items():
                channel_obj = interaction.guild.get_channel(int(channel_id_str))
                channel_name = channel_obj.name if channel_obj else f"Deleted Channel ({channel_id_str})"

                for ai_name, ai_data in channel_data.items():
                    # Only show AIs with character cards
                    if not ai_data.get("character_card"):
                        continue
                    
                    if current.lower() in ai_name.lower():
                        provider = ai_data.get("provider", "openai").upper()
                        display_name = f"{ai_name} [{provider}] (#{channel_name})"
                        choices.append(app_commands.Choice(name=display_name[:100], value=ai_name))
            
            return choices[:25]
        except Exception as e:
            func.log.error(f"Error in ai_name_with_cards autocomplete: {e}")
            return []
    
    @staticmethod
    async def card_name(
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """
        Autocomplete for registered character card names.
        
        Includes the default card option and all registered cards.
        """
        try:
            server_id = str(interaction.guild.id)
            cards = func.list_character_cards(server_id)
            
            choices = []
            
            # Add registered cards
            for card_name, card_info in cards.items():
                if current.lower() in card_name.lower():
                    char_name = card_info.get("name", card_name)
                    # Avoid duplication when card_name equals char_name
                    if card_name == char_name:
                        display_name = card_name
                    else:
                        display_name = f"{card_name} ({char_name})"
                    choices.append(app_commands.Choice(name=display_name[:100], value=card_name))
            
            return choices[:25]
        except Exception as e:
            func.log.error(f"Error in card_name autocomplete: {e}")
            return []
    
    @staticmethod
    async def connection_name(
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """
        Autocomplete for API connection names.
        
        Shows all configured API connections with their provider and model.
        """
        try:
            server_id = str(interaction.guild.id)
            connections = func.list_api_connections(server_id)
            
            if not connections:
                return []
            
            choices = []
            for conn_name, conn_data in connections.items():
                if current.lower() in conn_name.lower():
                    provider = conn_data.get("provider", "unknown").upper()
                    model = conn_data.get("model", "unknown")
                    display_name = f"{conn_name} [{provider}] ({model})"
                    choices.append(app_commands.Choice(name=display_name[:100], value=conn_name))
            
            return choices[:25]
        except Exception as e:
            func.log.error(f"Error in connection_name autocomplete: {e}")
            return []
    
    @staticmethod
    async def chat_id(
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """
        Autocomplete for chat IDs.
        
        Shows available chat sessions for the selected AI.
        Requires ai_name to be set in the command context.
        """
        try:
            server_id = str(interaction.guild.id)
            # Get ai_name from the current command context
            ai_name = interaction.namespace.ai_name
            if not ai_name:
                return []
            
            # Find the AI's channel
            found_ai_data = func.get_ai_session_data_from_all_channels(server_id, ai_name)
            if not found_ai_data:
                return []
            
            found_channel_id, session = found_ai_data
            
            # Get available chat_ids
            service = get_service()
            chat_ids = service.history_manager.list_chat_ids(server_id, found_channel_id, ai_name)
            
            choices = []
            for cid in chat_ids:
                if current.lower() in cid.lower():
                    # Get chat info
                    info = service.history_manager.get_chat_info(server_id, found_channel_id, ai_name, cid)
                    msg_count = info.get("message_count", 0)
                    display_name = f"{cid[:30]}... ({msg_count} msgs)" if len(cid) > 30 else f"{cid} ({msg_count} msgs)"
                    choices.append(app_commands.Choice(name=display_name, value=cid))
            
            return choices[:25]
        except Exception as e:
            func.log.error(f"Error in chat_id autocomplete: {e}")
            return []
