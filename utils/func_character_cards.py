"""
Character Cards Management Functions - Wrapper for backward compatibility
"""
from character_cards.manager import (
    register_character_card,
    unregister_character_card,
    list_character_cards,
    get_character_card,
    get_ais_using_card,
    delete_server_character_cards
)

# Re-export all functions for backward compatibility
__all__ = [
    'register_character_card',
    'unregister_character_card',
    'list_character_cards',
    'get_character_card',
    'get_ais_using_card',
    'delete_server_character_cards'
]

