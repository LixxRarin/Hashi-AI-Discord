"""
Reaction Expression - LLM Reaction System

This module provides the Reaction expression, which allows the LLM to react
to specific messages on Discord using the <REACTION:ID|emoji> syntax.

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

Migrated from: utils/reaction_parser.py
"""

import re
from typing import List, Tuple, Dict, Any
import logging

from .base import BaseExpression, ExpressionResult

log = logging.getLogger(__name__)


class ReactionExpression(BaseExpression):
    """
    Reaction System - Allows AI to react to messages with emojis.
    
    This expression enables the LLM to add emoji reactions to messages
    using the <REACTION:ID|emoji> syntax.
    """
    
    # Regex pattern to capture <REACTION:message_id|emoji>
    # Captures: message_id (digits) and emoji (anything except >)
    REACTION_PATTERN = r'<REACTION:(\d+)\|([^>]+)>'
    
    @property
    def name(self) -> str:
        return "reaction"
    
    @property
    def display_name(self) -> str:
        return "Reaction System"
    
    @property
    def description(self) -> str:
        return "Allows AI to react to messages with emojis using <REACTION:ID|emoji> syntax"
    
    @property
    def syntax_pattern(self) -> str:
        return self.REACTION_PATTERN
    
    @property
    def icon(self) -> str:
        return "😊"
    
    def has_syntax(self, text: str) -> bool:
        """Check if text contains reaction syntax."""
        if not text:
            return False
        return bool(re.search(self.REACTION_PATTERN, text))
    
    def parse(self, text: str, config: Dict[str, Any]) -> ExpressionResult:
        """
        Parse reaction syntax and extract reactions.
        
        Args:
            text: Text containing reaction syntax
            config: AI configuration (not used for reaction parsing)
            
        Returns:
            ExpressionResult with reactions populated
        """
        reactions = self.parse_reactions(text)
        
        return ExpressionResult(
            reactions=reactions,
            metadata={"expression": "reaction", "reaction_count": len(reactions)}
        )
    
    def remove_syntax(self, text: str) -> str:
        """
        Remove all reaction syntax from text.
        
        Also cleans up extra whitespace left behind.
        """
        if not text:
            return text
        
        # Remove all reaction tags
        cleaned = re.sub(self.REACTION_PATTERN, '', text)
        
        # Clean up extra whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def get_default_prompt(self) -> str:
        """Get the default prompt for the reaction system."""
        return """Reaction Syntax: <REACTION:ID|emoji>

You can react to messages using emojis to express quick emotions or acknowledgments.

WHEN TO USE REACTIONS:

Use reactions when:
- Acknowledging a message without needing a full response
- Expressing quick emotions (agreement, celebration, sympathy)
- Showing you've seen/read something important
- Adding emotional context to your response
- Multiple people share content worth reacting to

AVOID reactions when:
- A proper text response is more appropriate
- The conversation requires detailed explanation
- You're unsure what the user wants

EMOJI TYPES:
- Standard emojis: Use unicode directly (👍, 😊, ❤️, 🎉, etc.)
- Custom server emojis: Use :emoji_name: format (e.g., :happy:, :thumbsup:)

EXAMPLES:
- <REACTION:5|👍> Great idea!
- <REACTION:3|❤️> <REACTION:3|🎉>
- <REACTION:8|:happy:> That's awesome!
- Just reacting: <REACTION:2|😊>

Rules:
1. You can use multiple reactions in one response
2. Reactions can be combined with text or used alone
3. Use the message's short ID (#1, #2, etc.) that you see in the context
4. Invalid emojis will be silently ignored (no error shown to user)"""
    
    def parse_reactions(self, text: str) -> List[Tuple[str, str]]:
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
        
        matches = re.findall(self.REACTION_PATTERN, text)
        
        if matches:
            log.debug(f"Found {len(matches)} reaction(s) in text")
        
        return matches
    
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
            >>> ReactionExpression.validate_message_id("5")
            True
            >>> ReactionExpression.validate_message_id("123456789012345678")
            True
            >>> ReactionExpression.validate_message_id("abc")
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
    
    def extract_message_ids(self, text: str) -> List[str]:
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
        matches = re.findall(self.REACTION_PATTERN, text)
        return [message_id for message_id, _ in matches]
    
    def validate_reaction_syntax(self, text: str) -> Tuple[bool, str]:
        """
        Validate reaction syntax in text.
        
        Returns a tuple of (is_valid, reason).
        
        Args:
            text: Text to validate
            
        Returns:
            Tuple of (is_valid: bool, reason: str)
            
        Examples:
            >>> expr = ReactionExpression()
            >>> expr.validate_reaction_syntax("<REACTION:5|👍>")
            (True, "Valid reaction syntax")
            >>> expr.validate_reaction_syntax("<REACTION:abc|👍>")
            (False, "Invalid message ID: abc")
        """
        if not text:
            return False, "Empty text"
        
        if not self.has_syntax(text):
            return False, "No reaction syntax found"
        
        reactions = self.parse_reactions(text)
        
        if not reactions:
            return False, "Failed to parse reactions"
        
        # Validate each message ID
        for message_id, emoji in reactions:
            if not self.validate_message_id(message_id):
                return False, f"Invalid message ID: {message_id}"
            
            if not emoji or emoji.isspace():
                return False, f"Empty emoji for message {message_id}"
        
        return True, "Valid reaction syntax"
