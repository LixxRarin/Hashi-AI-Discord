"""
Text Processing Utilities

This module provides text cleaning and processing functions that are reusable
across different AI providers. It consolidates duplicated text cleaning logic
from openai_client.py into a single, maintainable location.

Functions:
    - remove_emoji: Remove emoji characters from text
    - clean_ai_response: Comprehensive AI response cleaning
    - remove_thinking_tags: Remove thinking/reasoning tags
    - apply_custom_patterns: Apply custom regex patterns
    - remove_reply_tags: Remove Discord reply syntax tags
"""

import re
from typing import List, Optional


def remove_emoji(text: str) -> str:
    """
    Removes emoji characters from the given text, including Discord custom emojis.
    
    This function was moved from utils/func.py to centralize text processing.

    Args:
        text: Text to process

    Returns:
        str: Text with emojis removed
    """
    # Regex pattern for Unicode emojis
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"   # Symbols & pictographs
        "\U0001F680-\U0001F6FF"   # Transport & map symbols
        "\U0001F700-\U0001F77F"   # Alchemical symbols
        "\U0001F780-\U0001F7FF"   # Geometric shapes extended
        "\U0001F800-\U0001F8FF"   # Supplemental arrows-C
        "\U0001F900-\U0001F9FF"   # Supplemental symbols and pictographs
        "\U0001FA00-\U0001FA6F"   # Chess symbols, etc.
        "\U0001FA70-\U0001FAFF"   # Symbols and pictographs extended-A
        "\U00002702-\U000027B0"   # Dingbats
        "\U000024C2-\U0001F251"   # Enclosed characters
        "]+", flags=re.UNICODE)

    # Regex pattern for Discord custom emojis (static and animated)
    discord_emoji_pattern = re.compile(r"<a?:\w+:\d+>")

    # Remove all emojis from the text
    text = re.sub(emoji_pattern, "", text)
    text = re.sub(discord_emoji_pattern, "", text)

    return text.strip()


def remove_thinking_tags(
    text: str,
    thinking_patterns: Optional[List[str]] = None
) -> str:
    """
    Remove thinking/reasoning tags from AI response.
    
    Args:
        text: Text to clean
        thinking_patterns: List of regex patterns for thinking tags.
                          If None, uses default patterns.
    
    Returns:
        str: Text with thinking tags removed
    """
    if thinking_patterns is None:
        thinking_patterns = [
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
            r'<thought>.*?</thought>',
            r'<reasoning>.*?</reasoning>'
        ]
    
    for pattern in thinking_patterns:
        text = re.sub(pattern, '', text, flags=re.DOTALL | re.MULTILINE)
    
    return text


def remove_reply_tags(text: str) -> str:
    """
    Remove Discord reply syntax tags from text.
    
    Reply tags like <REPLY:message_id> are used for Discord formatting
    but should not be saved in conversation history.
    
    Args:
        text: Text containing reply tags
        
    Returns:
        str: Text with reply tags removed
        
    Example:
        >>> remove_reply_tags("<REPLY:123456789> Hello!")
        'Hello!'
        >>> remove_reply_tags("<REPLY:111> Hi! <REPLY:222> Bye!")
        'Hi! Bye!'
    """
    # Pattern matches <REPLY:digits> followed by optional whitespace
    reply_pattern = r'<REPLY:\d+>\s*'
    return re.sub(reply_pattern, '', text).strip()


def apply_custom_patterns(
    text: str,
    custom_patterns: Optional[List[str]] = None
) -> str:
    """
    Apply custom regex patterns to remove specific text.
    
    Args:
        text: Text to process
        custom_patterns: List of regex patterns to remove
    
    Returns:
        str: Text with patterns removed
    """
    if not custom_patterns:
        return text
    
    for pattern in custom_patterns:
        text = re.sub(pattern, '', text, flags=re.MULTILINE).strip()
    
    return text


def clean_ai_response(
    text: str,
    thinking_patterns: Optional[List[str]] = None,
    remove_emojis: bool = True,
    custom_patterns: Optional[List[str]] = None,
    remove_reply_syntax: bool = True
) -> str:
    """
    Comprehensive cleaning of AI response text.
    
    This function consolidates the duplicated cleaning logic that appeared
    4 times in openai_client.py (lines 716, 855, 1073, 1131).
    
    Cleaning steps:
    1. Remove thinking/reasoning tags
    2. Remove Discord reply syntax tags (for history storage)
    3. Clean up excessive whitespace
    4. Remove emojis (if enabled)
    5. Apply custom removal patterns
    
    Args:
        text: AI response text to clean
        thinking_patterns: List of regex patterns for thinking tags.
                          If None, uses default patterns.
        remove_emojis: Whether to remove emoji characters
        custom_patterns: List of custom regex patterns to remove
        remove_reply_syntax: Whether to remove <REPLY:message_id> tags (default: True)
    
    Returns:
        str: Cleaned text
    
    Example:
        >>> text = "<thinking>Let me think...</thinking><REPLY:123> Hello! 😊"
        >>> clean_ai_response(text, remove_emojis=True)
        'Hello!'
    """
    # Step 1: Remove thinking tags
    text = remove_thinking_tags(text, thinking_patterns)
    
    # Step 2: Remove reply syntax tags (should not be in history)
    if remove_reply_syntax:
        text = remove_reply_tags(text)
    
    # Step 3: Clean up excessive whitespace (3+ newlines -> 2 newlines)
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text).strip()
    
    # Step 4: Remove emojis if configured
    if remove_emojis:
        text = remove_emoji(text)
    
    # Step 5: Apply custom removal patterns
    text = apply_custom_patterns(text, custom_patterns)
    
    return text


def clean_ai_response_from_config(
    text: str,
    llm_params: dict,
    config: dict
) -> str:
    """
    Clean AI response using configuration dictionaries.
    
    This is a convenience wrapper around clean_ai_response() that extracts
    the necessary parameters from LLM params and config dictionaries.
    
    Args:
        text: AI response text to clean
        llm_params: LLM parameters dictionary (contains thinking_tag_patterns)
        config: Session config dictionary (contains remove_ai_emoji, remove_ai_text_from)
    
    Returns:
        str: Cleaned text
    
    Example:
        >>> llm_params = {"thinking_tag_patterns": ["<think>.*?</think>"]}
        >>> config = {"remove_ai_emoji": True, "remove_ai_text_from": [r'\\*[^*]*\\*']}
        >>> clean_ai_response_from_config(text, llm_params, config)
    """
    return clean_ai_response(
        text=text,
        thinking_patterns=llm_params.get("thinking_tag_patterns", [
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
            r'<thought>.*?</thought>',
            r'<reasoning>.*?</reasoning>'
        ]),
        remove_emojis=config.get("remove_ai_emoji", False),
        custom_patterns=config.get("remove_ai_text_from", [])
    )
