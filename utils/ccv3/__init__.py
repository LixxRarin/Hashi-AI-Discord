"""
Character Cards V3 Support Module

This module provides complete support for Character Card V3 specification,
including parsing PNG/JSON/CHARX formats, CBS processing, and lorebook support.
"""

from .parser import (
    CharacterCardV3,
    parse_character_card,
    parse_png_card,
    parse_json_card,
    parse_charx_card,
    validate_card_v3
)

from .loader import (
    CharacterCardLoader,
    download_card,
    load_local_card,
    clear_card_cache,
    get_cache_info
)

from .cbs_processor import (
    process_cbs,
    replace_char_syntax,
    replace_user_syntax
)

from .lorebook import (
    get_active_lorebook_entries,
    process_lorebook
)

__all__ = [
    # Parser
    'CharacterCardV3',
    'parse_character_card',
    'parse_png_card',
    'parse_json_card',
    'parse_charx_card',
    'validate_card_v3',
    
    # Loader
    'CharacterCardLoader',
    'download_card',
    'load_local_card',
    'clear_card_cache',
    'get_cache_info',
    
    # CBS Processor
    'process_cbs',
    'replace_char_syntax',
    'replace_user_syntax',
    
    # Lorebook
    'get_active_lorebook_entries',
    'process_lorebook',
]
