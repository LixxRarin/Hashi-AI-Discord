"""
Character Cards Management Functions
"""
import asyncio
import datetime
import logging
from typing import Dict, Any, Optional

from utils.persistence import read_json, write_json

log = logging.getLogger(__name__)


def get_character_cards_file() -> str:
    """
    Get the character cards file path from configuration.
    Import from func.py to avoid circular imports.
    
    Returns:
        str: Path to the character cards file
    """
    from utils.func import get_character_cards_file as _get_file
    return _get_file()

# This will be imported by func.py
session_cache: Dict[str, Any] = {}

async def load_character_cards() -> Dict[str, Dict[str, Any]]:
    """
    Load character cards registry from character_cards.json file.
    
    Returns:
        Dict[str, Dict[str, Any]]: Dictionary of character cards by server
    """
    return await asyncio.to_thread(read_json, get_character_cards_file()) or {}


async def save_character_cards(data: Dict[str, Dict[str, Any]]) -> None:
    """
    Save character cards registry to character_cards.json file.
    
    Args:
        data: Dictionary of character cards to save
    """
    await asyncio.to_thread(write_json, get_character_cards_file(), data)


def get_character_card(server_id: str, card_name: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific character card from the registry.
    
    Args:
        server_id: Server ID
        card_name: Character card name
        
    Returns:
        Optional[Dict[str, Any]]: Character card data or None if not found
    """
    cards = read_json(get_character_cards_file()) or {}
    return cards.get(server_id, {}).get(card_name)


async def register_character_card(
    server_id: str,
    card_name: str,
    card_data: Dict[str, Any],
    card_url: str,
    cache_path: str,
    registered_by: Optional[str] = None
) -> str:
    """
    Register a character card in the central registry.
    
    Args:
        server_id: Server ID
        card_name: Unique name for the card (usually character name)
        card_data: Character card data (from CharacterCardV3.to_dict())
        card_url: Original URL of the card
        cache_path: Path to cached card file (not directory)
        registered_by: User ID who registered it
        
    Returns:
        str: The registered card name (may be modified if duplicate)
    """
    cards = await load_character_cards()
    
    if server_id not in cards:
        cards[server_id] = {}
    
    # Check if a card with the same URL already exists
    for existing_card_name, existing_card_data in cards[server_id].items():
        if existing_card_data.get("card_url") == card_url:
            log.info(f"Card with URL '{card_url}' already registered as '{existing_card_name}' in server {server_id}")
            return existing_card_name
    
    # Generate unique name if card_name already exists
    original_name = card_name
    counter = 2
    while card_name in cards[server_id]:
        card_name = f"{original_name}_{counter}"
        counter += 1
    
    # Get filename from cache_path
    from pathlib import Path
    filename = Path(cache_path).name
    
    # Store only metadata, not the full card_data (which can be 3MB+)
    # The full data is in the cache file
    cards[server_id][card_name] = {
        "name": card_data.get("name", card_name),
        "nickname": card_data.get("nickname"),
        "creator": card_data.get("creator"),
        "character_version": card_data.get("character_version"),
        "spec": card_data.get("spec", "chara_card_v3"),
        "spec_version": card_data.get("spec_version", "3.0"),
        "card_url": card_url,
        "cache_path": cache_path,  # Now points to file, not directory
        "filename": filename,  # Store filename for easy reference
        "registered_at": datetime.datetime.utcnow().isoformat(),
        "registered_by": registered_by,
        "total_greetings": 1 + len(card_data.get("alternate_greetings") or [])
    }
    
    await save_character_cards(cards)
    log.info(f"Registered character card '{card_name}' -> {filename} in server {server_id}")
    return card_name


async def unregister_character_card(server_id: str, card_name: str) -> bool:
    """
    Remove a character card from the registry.
    
    Args:
        server_id: Server ID
        card_name: Character card name
        
    Returns:
        bool: True if removed successfully, False if not found
    """
    cards = await load_character_cards()
    
    if server_id not in cards or card_name not in cards[server_id]:
        log.warning(f"Character card '{card_name}' not found in server {server_id}")
        return False
    
    del cards[server_id][card_name]
    
    # Clean up empty server entries
    if not cards[server_id]:
        del cards[server_id]
    
    await save_character_cards(cards)
    log.info(f"Unregistered character card '{card_name}' from server {server_id}")
    return True


def list_character_cards(server_id: str) -> Dict[str, Any]:
    """
    List all character cards for a server.
    
    Args:
        server_id: Server ID
        
    Returns:
        Dict[str, Any]: Dictionary of server character cards
    """
    cards = read_json(get_character_cards_file()) or {}
    return cards.get(server_id, {})


def get_ais_using_card(server_id: str, card_name: str) -> list[tuple[str, str]]:
    """
    Return list of AIs using a specific character card.
    
    Args:
        server_id: Server ID
        card_name: Character card name
        
    Returns:
        list[tuple[str, str]]: List of tuples (channel_id, ai_name)
    """
    from utils.func import session_cache
    
    ais_using = []
    server_data = session_cache.get(server_id, {})
    channels_data = server_data.get("channels", {})
    
    for channel_id, channel_ais in channels_data.items():
        for ai_name, ai_session in channel_ais.items():
            if ai_session.get("character_card_name") == card_name:
                ais_using.append((channel_id, ai_name))
    
    return ais_using
