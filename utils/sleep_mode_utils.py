"""
Sleep Mode Utilities - Shared Sleep Mode Logic
"""

import re
import logging
from typing import Dict, Any, List, Optional, Tuple

log = logging.getLogger(__name__)


def is_in_sleep_mode(
    server_id: str,
    channel_id: str,
    ai_name: str
) -> bool:
    """
    Check if AI is currently in sleep mode.
    
    Args:
        server_id: Server ID
        channel_id: Channel ID
        ai_name: AI name
        
    Returns:
        True if AI is in sleep mode, False otherwise
    """
    try:
        from AI.response_filter import get_response_filter
        
        response_filter = get_response_filter()
        state_key = (server_id, channel_id, ai_name)
        
        if state_key not in response_filter.sleep_state:
            return False
        
        state = response_filter.sleep_state[state_key]
        return state.get("in_sleep_mode", False)
        
    except Exception as e:
        log.error(f"Error checking sleep mode: {e}")
        return False


def check_wakeup_patterns(
    message_content: str,
    ai_name: str,
    is_mentioned: bool,
    is_reply_to_bot: bool,
    patterns: List[str]
) -> bool:
    """
    Check if message matches any wake-up pattern.

    This function is extracted from MessagePipeline._check_wakeup_patterns
    to be reusable by both pipeline and timing controller.

    Args:
        message_content: The message content to check
        ai_name: Name of the AI
        is_mentioned: Whether AI was mentioned
        is_reply_to_bot: Whether message is a reply to bot
        patterns: List of wake-up patterns (placeholders or regex)

    Returns:
        True if any pattern matches

    Examples:
        >>> check_wakeup_patterns("Hello @bot", "bot", True, False, ["{ai_mention}"])
        True
        >>> check_wakeup_patterns("Hello", "bot", False, False, ["{ai_mention}"])
        False
    """

    if not patterns:
        # Default behavior: wake on mention or reply
        result = is_mentioned or is_reply_to_bot
        return result
    
    for pattern in patterns:
        # Handle special placeholders
        if pattern == "{ai_mention}":
            if is_mentioned:
                return True
        elif pattern == "{reply}":
            if is_reply_to_bot:
                return True
        elif pattern == "{ai_name}":
            # Check if AI name appears in message (case-insensitive)
            # Remove emojis and special chars from AI name for flexible matching
            # This handles cases like "Hashi 🐏" matching "hashi"
            ai_name_clean = re.sub(r'[^\w\s]', '', ai_name).strip()

            # Try matching the full name first
            if re.search(re.escape(ai_name), message_content, re.IGNORECASE):
                return True

            # Try matching the cleaned name (without emojis/special chars)
            if ai_name_clean and re.search(r'\b' + re.escape(ai_name_clean) + r'\b', message_content, re.IGNORECASE):
                return True

            # Try matching individual words from the AI name
            # This handles multi-word names like "Hashi Bot"
            words = ai_name_clean.split()
            for word in words:
                if len(word) >= 3:  # Only match words with 3+ chars to avoid false positives
                    if re.search(r'\b' + re.escape(word) + r'\b', message_content, re.IGNORECASE):
                        return True
        else:
            # Treat as regex pattern
            try:
                if re.search(pattern, message_content, re.IGNORECASE):
                    return True
            except re.error as e:
                log.warning(f"Invalid wake-up regex pattern '{pattern}': {e}")
                continue

    return False


async def should_wake_from_sleep(
    server_id: str,
    channel_id: str,
    ai_name: str,
    session: Dict[str, Any],
    pending_messages: List[Any],
    bot_user_id: Optional[int] = None
) -> Tuple[bool, bool]:
    """
    Check if AI is in sleep mode and if it should wake up.
    
    This is the main function used by TimingController to determine
    if a response should be triggered when AI is in sleep mode.
    
    Args:
        server_id: Server ID
        channel_id: Channel ID
        ai_name: AI name
        session: AI session data
        pending_messages: List of pending messages to check
        bot_user_id: Bot user ID for checking mentions
        
    Returns:
        Tuple of (is_in_sleep: bool, should_wake: bool)
        - is_in_sleep: True if AI is currently in sleep mode
        - should_wake: True if AI should wake up (wake-up pattern found)
        
    Examples:
        >>> # AI not in sleep mode
        >>> should_wake_from_sleep(...) 
        (False, False)  # Not in sleep, normal processing
        
        >>> # AI in sleep mode, no wake-up pattern
        >>> should_wake_from_sleep(...)
        (True, False)  # In sleep, stay asleep
        
        >>> # AI in sleep mode, wake-up pattern found
        >>> should_wake_from_sleep(...)
        (True, True)  # In sleep, should wake up
    """
    config = session.get("config", {})
    
    # Check if ignore system and sleep mode are enabled
    from expressions import get_expression_registry
    registry = get_expression_registry()
    ignore_expr = registry.get('ignore')
    
    if not ignore_expr or not ignore_expr.is_enabled(config):
        return (False, False)  # Not using sleep mode
    
    if not config.get("sleep_mode_enabled", False):
        return (False, False)  # Sleep mode disabled
    
    # Check if AI is in sleep mode
    in_sleep = is_in_sleep_mode(server_id, channel_id, ai_name)
    
    if not in_sleep:
        return (False, False)  # Not in sleep mode
    
    # AI is in sleep mode, check if should wake up
    if not pending_messages:
        return (True, False)  # In sleep, no messages to check
    
    # Get wake-up patterns from config
    wakeup_patterns = config.get("sleep_wakeup_patterns", ["{ai_mention}", "{reply}"])
    
    # Check messages for wake-up patterns
    is_mentioned = False
    is_reply_to_bot = False
    message_content = ""
    
    if bot_user_id:
        for msg in pending_messages:
            message_content += msg.content + " "
            if hasattr(msg, 'raw_message') and msg.raw_message:
                # Check if bot is mentioned
                if hasattr(msg.raw_message, 'mentions'):
                    is_mentioned = is_mentioned or any(
                        m.id == bot_user_id for m in msg.raw_message.mentions
                    )
                
                # Check if message is a reply to bot
                if hasattr(msg.raw_message, 'reference') and msg.raw_message.reference:
                    try:
                        from utils.message_cache import fetch_message_cached
                        ref_msg_id = msg.raw_message.reference.message_id
                        ref_msg = await fetch_message_cached(
                            msg.raw_message.channel,
                            str(ref_msg_id)
                        )
                        if ref_msg and ref_msg.author.id == bot_user_id:
                            is_reply_to_bot = True
                    except Exception as e:
                        # This prevents false wake-ups from spam
                        log.debug(f"Could not verify reply target: {e}")
                        pass
    
    # Check if any wake-up pattern matches
    should_wake = check_wakeup_patterns(
        message_content,
        ai_name,
        is_mentioned,
        is_reply_to_bot,
        wakeup_patterns
    )
    
    return (True, should_wake)


def get_sleep_state_info(
    server_id: str,
    channel_id: str,
    ai_name: str
) -> Dict[str, Any]:
    """
    Get detailed sleep state information for debugging.
    
    Args:
        server_id: Server ID
        channel_id: Channel ID
        ai_name: AI name
        
    Returns:
        Dictionary with sleep state info
    """
    try:
        from AI.response_filter import get_response_filter
        
        response_filter = get_response_filter()
        state_key = (server_id, channel_id, ai_name)
        
        if state_key not in response_filter.sleep_state:
            return {
                "exists": False,
                "in_sleep_mode": False,
                "consecutive_refusals": 0,
                "last_activity": None
            }
        
        state = response_filter.sleep_state[state_key]
        return {
            "exists": True,
            "in_sleep_mode": state.get("in_sleep_mode", False),
            "consecutive_refusals": state.get("consecutive_refusals", 0),
            "last_activity": state.get("last_activity", None)
        }
        
    except Exception as e:
        log.error(f"Error getting sleep state info: {e}")
        return {
            "exists": False,
            "error": str(e)
        }
