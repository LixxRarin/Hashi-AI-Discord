"""
Ignore Parser - LLM Ignore System

This module provides functionality to parse and detect the <IGNORE> tag
that the LLM uses to indicate it should not send a message to the channel.

Syntax: <IGNORE>

When the LLM detects that a conversation is not directed at it or has nothing
useful to contribute, it can output ONLY the <IGNORE> tag, and no message
will be sent to Discord.

Example:
    <IGNORE>
    
Invalid examples (will be treated as normal messages):
    <IGNORE> Sorry, I can't help with that
    I think <IGNORE> would be best here
"""

import re
from typing import Optional
import logging

log = logging.getLogger(__name__)


class IgnoreParser:
    """Parser to detect and validate the <IGNORE> tag in LLM responses."""
    
    # Regex pattern to detect <IGNORE> tag (case-insensitive)
    IGNORE_PATTERN = re.compile(r'<ignore>', re.IGNORECASE)
    
    # Regex pattern to validate pure <IGNORE> (only whitespace allowed)
    PURE_IGNORE_PATTERN = re.compile(r'^\s*<ignore>\s*$', re.IGNORECASE)
    
    @staticmethod
    def has_ignore_tag(text: str) -> bool:
        """
        Check if text contains the <IGNORE> tag anywhere.
        
        This does NOT validate if it's a pure ignore - just checks presence.
        
        Args:
            text: Text to check
            
        Returns:
            True if <IGNORE> tag is present, False otherwise
            
        Examples:
            >>> IgnoreParser.has_ignore_tag("<IGNORE>")
            True
            >>> IgnoreParser.has_ignore_tag("<ignore>")
            True
            >>> IgnoreParser.has_ignore_tag("Hello <IGNORE> world")
            True
            >>> IgnoreParser.has_ignore_tag("Hello world")
            False
        """
        if not text:
            return False
        
        return bool(IgnoreParser.IGNORE_PATTERN.search(text))
    
    @staticmethod
    def is_pure_ignore(text: str) -> bool:
        """
        Check if text is ONLY the <IGNORE> tag (with optional whitespace).
        
        This is the strict validation used to determine if the LLM wants
        to skip sending a message.
        
        Args:
            text: Text to validate
            
        Returns:
            True if text is pure <IGNORE>, False otherwise
            
        Examples:
            >>> IgnoreParser.is_pure_ignore("<IGNORE>")
            True
            >>> IgnoreParser.is_pure_ignore("  <ignore>  ")
            True
            >>> IgnoreParser.is_pure_ignore("<IGNORE>\\n")
            True
            >>> IgnoreParser.is_pure_ignore("<IGNORE> Sorry")
            False
            >>> IgnoreParser.is_pure_ignore("I think <IGNORE>")
            False
        """
        if not text:
            return False
        
        # Check if it matches the pure ignore pattern
        is_pure = bool(IgnoreParser.PURE_IGNORE_PATTERN.match(text))
        
        if is_pure:
            log.debug(f"Detected pure <IGNORE> tag in response")
        elif IgnoreParser.has_ignore_tag(text):
            log.warning(
                f"Found <IGNORE> tag but with additional content - "
                f"treating as normal message: '{text[:100]}'"
            )
        
        return is_pure
    
    @staticmethod
    def normalize_ignore(text: str) -> Optional[str]:
        """
        Normalize <IGNORE> tag to standard format.
        
        If text is a pure ignore, returns normalized "<IGNORE>".
        Otherwise returns None.
        
        Args:
            text: Text to normalize
            
        Returns:
            "<IGNORE>" if pure ignore, None otherwise
            
        Examples:
            >>> IgnoreParser.normalize_ignore("  <ignore>  ")
            "<IGNORE>"
            >>> IgnoreParser.normalize_ignore("<IGNORE> text")
            None
        """
        if IgnoreParser.is_pure_ignore(text):
            return "<IGNORE>"
        return None
    
    @staticmethod
    def remove_ignore_tag(text: str) -> str:
        """
        Remove all <IGNORE> tags from text.
        
        Useful for cleaning up text that contains ignore tags
        but isn't a pure ignore.
        
        Args:
            text: Text to clean
            
        Returns:
            Text with <IGNORE> tags removed
            
        Examples:
            >>> IgnoreParser.remove_ignore_tag("Hello <IGNORE> world")
            "Hello  world"
            >>> IgnoreParser.remove_ignore_tag("<IGNORE>")
            ""
        """
        return IgnoreParser.IGNORE_PATTERN.sub('', text).strip()
    
    @staticmethod
    def validate_ignore_response(text: str) -> tuple[bool, str]:
        """
        Validate an LLM response for ignore handling.
        
        Returns a tuple of (should_ignore, reason).
        
        Args:
            text: LLM response text
            
        Returns:
            Tuple of (should_ignore: bool, reason: str)
            
        Examples:
            >>> IgnoreParser.validate_ignore_response("<IGNORE>")
            (True, "Pure ignore tag detected")
            >>> IgnoreParser.validate_ignore_response("<IGNORE> Sorry")
            (False, "Ignore tag found but with additional content")
            >>> IgnoreParser.validate_ignore_response("Hello")
            (False, "No ignore tag found")
        """
        if not text:
            return False, "Empty response"
        
        if IgnoreParser.is_pure_ignore(text):
            return True, "Pure ignore tag detected"
        
        if IgnoreParser.has_ignore_tag(text):
            return False, "Ignore tag found but with additional content"
        
        return False, "No ignore tag found"


# Convenience functions for common use cases

def should_ignore_response(response: str) -> bool:
    """
    Quick check if a response should be ignored.
    
    This is the main function to use in the pipeline.
    
    Args:
        response: LLM response text
        
    Returns:
        True if response should be ignored (not sent to Discord)
    """
    return IgnoreParser.is_pure_ignore(response)


def get_ignore_reason(response: str) -> Optional[str]:
    """
    Get the reason why a response would or wouldn't be ignored.
    
    Useful for logging and debugging.
    
    Args:
        response: LLM response text
        
    Returns:
        Reason string, or None if no ignore tag present
    """
    should_ignore, reason = IgnoreParser.validate_ignore_response(response)
    return reason if should_ignore or IgnoreParser.has_ignore_tag(response) else None
