"""
Reaction Parser - LLM Reaction System

This module provides functionality to parse and process the reaction syntax
that the LLM uses to react to specific messages on Discord.

Syntax: <REACTION:message_id|emoji>

Supports both short IDs and full Discord IDs:
- Short ID: <REACTION:1|👍>
- Full ID: <REACTION:123456789|😊>

Emoji types:
- Standard unicode: <REACTION:5|👍>
- Custom server emoji: <REACTION:5|:happy:>

Example:
    <REACTION:5|👍> Great idea!
    
Multiple reactions:
    <REACTION:5|👍> <REACTION:5|:happy:> <REACTION:7|😊>
"""

import re
from typing import List, Tuple, Optional
import logging

log = logging.getLogger(__name__)


class ReactionParser:
    """Parser to extract and process LLM reaction syntax."""
    
    # Regex pattern to capture <REACTION:message_id|emoji>
    # Captures: message_id (digits) and emoji (anything except >)
    REACTION_PATTERN = r'<REACTION:(\d+)\|([^>]+)>'
    
    @staticmethod
    def parse_reactions(text: str) -> List[Tuple[str, str]]:
        """
        Extract all reactions from text.
        
        Args:
            text: LLM response text that may contain reaction syntax
            
        Returns:
            List of tuples (message_id, emoji)
            
        Examples:
            Input: "<REACTION:5|👍> Hello! <REACTION:7|:happy:>"
            Output: [("5", "👍"), ("7", ":happy:")]
            
            Input: "Hello everyone!"
            Output: []
            
            Input: "<REACTION:5|👍> <REACTION:5|❤️>"
            Output: [("5", "👍"), ("5", "❤️")]
        """
        if not text:
            return []
        
        matches = re.findall(ReactionParser.REACTION_PATTERN, text)
        
        if matches:
            log.debug(f"Found {len(matches)} reaction(s) in text")
        
        return matches
    
    @staticmethod
    def has_reaction_syntax(text: str) -> bool:
        """
        Check if text contains reaction syntax.
        
        Args:
            text: Text to check
            
        Returns:
            True if contains reaction syntax, False otherwise
            
        Examples:
            >>> ReactionParser.has_reaction_syntax("<REACTION:5|👍>")
            True
            >>> ReactionParser.has_reaction_syntax("Hello world")
            False
        """
        if not text:
            return False
        
        return bool(re.search(ReactionParser.REACTION_PATTERN, text))
    
    @staticmethod
    def remove_reaction_syntax(text: str) -> str:
        """
        Remove all reaction syntax from text, leaving only content.
        
        Useful for cleaning text before sending to Discord.
        
        Args:
            text: Text with reaction syntax
            
        Returns:
            Text without reaction syntax
            
        Examples:
            Input: "<REACTION:5|👍> Hello! <REACTION:7|:happy:>"
            Output: "Hello!"
            
            Input: "<REACTION:5|👍>"
            Output: ""
            
            Input: "Hello <REACTION:5|👍> world"
            Output: "Hello  world"
        """
        if not text:
            return text
        
        # Remove all reaction tags
        cleaned = re.sub(ReactionParser.REACTION_PATTERN, '', text)
        
        # Clean up extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    @staticmethod
    def validate_message_id(message_id: str, allow_short_ids: bool = True) -> bool:
        """
        Validate if a message_id has valid format (numeric).
        
        Args:
            message_id: Message ID to validate
            allow_short_ids: Whether to accept short IDs (1-16 digits)
            
        Returns:
            True if ID is valid, False otherwise
            
        Examples:
            >>> ReactionParser.validate_message_id("5")
            True
            >>> ReactionParser.validate_message_id("123456789012345678")
            True
            >>> ReactionParser.validate_message_id("abc")
            False
        """
        if not message_id:
            return False
        
        # Check if numeric
        if not message_id.isdigit():
            return False
        
        id_len = len(message_id)
        
        # Short IDs: 1-16 digits (below Discord's 17-20 digit range)
        if allow_short_ids and 1 <= id_len <= 16:
            return True
        
        # Full Discord IDs: 17-20 digits (snowflakes)
        if 17 <= id_len <= 20:
            return True
        
        return False
    
    @staticmethod
    def extract_message_ids(text: str) -> List[str]:
        """
        Extract all message IDs from text without processing emojis.
        
        Useful for quick validation or logging.
        
        Args:
            text: Text containing reaction syntax
            
        Returns:
            List of message IDs found
            
        Examples:
            Input: "<REACTION:5|👍> Hello! <REACTION:7|:happy:>"
            Output: ["5", "7"]
            
            Input: "<REACTION:5|👍> <REACTION:5|❤️>"
            Output: ["5", "5"]
        """
        matches = re.findall(ReactionParser.REACTION_PATTERN, text)
        return [message_id for message_id, _ in matches]
    
    @staticmethod
    def validate_reaction_syntax(text: str) -> Tuple[bool, str]:
        """
        Validate reaction syntax in text.
        
        Returns a tuple of (is_valid, reason).
        
        Args:
            text: Text to validate
            
        Returns:
            Tuple of (is_valid: bool, reason: str)
            
        Examples:
            >>> ReactionParser.validate_reaction_syntax("<REACTION:5|👍>")
            (True, "Valid reaction syntax")
            >>> ReactionParser.validate_reaction_syntax("<REACTION:abc|👍>")
            (False, "Invalid message ID: abc")
        """
        if not text:
            return False, "Empty text"
        
        if not ReactionParser.has_reaction_syntax(text):
            return False, "No reaction syntax found"
        
        reactions = ReactionParser.parse_reactions(text)
        
        if not reactions:
            return False, "Failed to parse reactions"
        
        # Validate each message ID
        for message_id, emoji in reactions:
            if not ReactionParser.validate_message_id(message_id):
                return False, f"Invalid message ID: {message_id}"
            
            if not emoji or emoji.isspace():
                return False, f"Empty emoji for message {message_id}"
        
        return True, "Valid reaction syntax"


# Convenience functions for common use cases

def parse_reactions(response: str) -> List[Tuple[str, str]]:
    """
    Quick function to parse reactions from a response.
    
    This is the main function to use in the pipeline.
    
    Args:
        response: LLM response text
        
    Returns:
        List of (message_id, emoji) tuples
    """
    return ReactionParser.parse_reactions(response)


def has_reactions(response: str) -> bool:
    """
    Quick check if a response contains reactions.
    
    Args:
        response: LLM response text
        
    Returns:
        True if response contains reaction syntax
    """
    return ReactionParser.has_reaction_syntax(response)


def clean_reactions(response: str) -> str:
    """
    Remove reaction syntax from response.
    
    Args:
        response: LLM response text
        
    Returns:
        Text without reaction syntax
    """
    return ReactionParser.remove_reaction_syntax(response)
