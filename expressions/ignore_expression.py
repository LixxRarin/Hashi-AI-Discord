"""
Ignore Expression - LLM Ignore System

This module provides the Ignore expression, which allows the LLM to indicate
it should not send a message to the channel using the <IGNORE> tag.

Syntax: <IGNORE>

When the LLM detects that a conversation is not directed at it or has nothing
useful to contribute, it can output ONLY the <IGNORE> tag, and no message
will be sent to Discord.

Correct usage (pure ignore):
    <IGNORE>
    <thinking>...</thinking>\n\n<IGNORE>  # Thinking tags are stripped
    
Incorrect usage (impure ignore - nothing sent, nothing saved):
    <IGNORE> Sorry, I can't help with that  # Not sent to Discord, not saved to history
    I think <IGNORE> would be best here     # Not sent to Discord, not saved to history

Behavior:
- Pure ignore: Not sent to Discord, saved to history as <IGNORE>
- Impure ignore: Not sent to Discord, not saved to history

Migrated from: utils/ignore_parser.py
"""

import re
from typing import Optional, Dict, Any, Tuple
import logging

from .base import BaseExpression, ExpressionResult

log = logging.getLogger(__name__)


class IgnoreExpression(BaseExpression):
    """
    Ignore System - Allows AI to skip responding.
    
    This expression enables the LLM to decide during generation that it
    should not send a message. This is useful for natural conversation flow
    where the AI recognizes it shouldn't respond.
    
    Behavior:
    - Pure ignore (<IGNORE> only): Not sent to Discord, saved to history as <IGNORE>
    - Impure ignore (<IGNORE> + content): Not sent to Discord, not saved to history
    
    Thinking tags (<thinking>, <think>, etc.) are stripped before checking,
    so "<thinking>...</thinking>\n\n<IGNORE>" is treated as pure ignore.
    """
    
    # Regex pattern to detect <IGNORE> tag (case-insensitive)
    IGNORE_PATTERN = re.compile(r'<ignore>', re.IGNORECASE)
    
    # Regex pattern to validate pure <IGNORE> (only whitespace allowed)
    PURE_IGNORE_PATTERN = re.compile(r'^\s*<ignore>\s*$', re.IGNORECASE)
    
    @property
    def name(self) -> str:
        return "ignore"
    
    @property
    def display_name(self) -> str:
        return "Ignore System"
    
    @property
    def description(self) -> str:
        return "Allows AI to skip responding using <IGNORE> tag"
    
    @property
    def syntax_pattern(self) -> str:
        return r'<ignore>'
    
    @property
    def icon(self) -> str:
        return "🚫"
    
    def has_syntax(self, text: str) -> bool:
        """
        Check if text contains the <IGNORE> tag anywhere.
        
        This does NOT validate if it's a pure ignore - just checks presence.
        """
        if not text:
            return False
        return bool(self.IGNORE_PATTERN.search(text))
    
    def parse(self, text: str, config: Dict[str, Any]) -> ExpressionResult:
        """
        Parse ignore syntax and determine if message should be skipped.
        
        - Pure ignore: message is skipped (not sent to Discord, saved to history as <IGNORE>)
        - Impure ignore: message is skipped (not sent to Discord, not saved to history)
        
        Args:
            text: Text to check for ignore tag
            config: AI configuration (not used for ignore parsing)
            
        Returns:
            ExpressionResult with should_skip=True for both pure and impure ignore
        """
        is_pure = self.is_pure_ignore(text)
        has_ignore = self.has_syntax(text)
        
        if is_pure:
            log.debug("Detected pure <IGNORE> tag - message will be skipped")
            return ExpressionResult(
                should_skip=True,
                metadata={
                    "expression": "ignore",
                    "ignore_type": "pure",
                    "reason": "Pure ignore tag detected"
                }
            )
        
        if has_ignore:
            # Impure ignore: has <IGNORE> but with additional content
            # Don't send to Discord, don't save to history
            log.warning(
                "Found <IGNORE> tag with additional content - "
                "message will be skipped and not saved to history. "
                "Use ONLY <IGNORE> to skip responding and save to history."
            )
            return ExpressionResult(
                should_skip=True,
                metadata={
                    "expression": "ignore",
                    "ignore_type": "impure",
                    "reason": "Impure ignore tag detected (has additional content)"
                }
            )
        
        return ExpressionResult(
            should_skip=False,
            metadata={"expression": "ignore", "reason": "No ignore tag"}
        )
    
    def remove_syntax(self, text: str) -> str:
        """
        Remove all <IGNORE> tags from text.
        
        Useful for cleaning up text that contains ignore tags
        but isn't a pure ignore.
        """
        if not text:
            return text
        return self.IGNORE_PATTERN.sub('', text).strip()
    
    def get_default_prompt(self) -> str:
        """Get the default prompt for the ignore system."""
        return """Ignore Syntax:

You can use <IGNORE> when you detect conversations not directed at you.

When to use <IGNORE>:
- Users are talking among themselves
- Conversation is not directed at you
- You have nothing useful to contribute
- A complement to the user's previous sentence that does not need to be responded to (e.g., emoji)
- Context makes it clear you shouldn't respond

IMPORTANT: When you decide not to respond, output ONLY: <IGNORE>
Do not add any other text or explanation.

If you add text with <IGNORE>, the message will not be sent to Discord and will not be saved to history.
Example: "<IGNORE> Sorry" will not send anything and will not be saved."""
    
    def is_pure_ignore(self, text: str) -> bool:
        """
        Check if text is ONLY the <IGNORE> tag (with optional whitespace).
        
        Thinking tags are stripped before checking, so:
        - "<IGNORE>" → True
        - "<thinking>...</thinking>\n\n<IGNORE>" → True (thinking stripped)
        - "<IGNORE> Sorry" → False
        - "<thinking>...</thinking>\n\n<IGNORE> Sorry" → False
        
        This is the strict validation used to determine if the LLM wants
        to skip sending a message.
        
        Args:
            text: Text to validate
            
        Returns:
            True if text is pure <IGNORE>, False otherwise
            
        Examples:
            >>> expr = IgnoreExpression()
            >>> expr.is_pure_ignore("<IGNORE>")
            True
            >>> expr.is_pure_ignore("  <ignore>  ")
            True
            >>> expr.is_pure_ignore("<IGNORE>\\n")
            True
            >>> expr.is_pure_ignore("<thinking>...</thinking>\\n\\n<IGNORE>")
            True
            >>> expr.is_pure_ignore("<IGNORE> Sorry")
            False
            >>> expr.is_pure_ignore("I think <IGNORE>")
            False
        """
        if not text:
            return False
        
        # Import here to avoid circular dependency
        from utils.text.processor import remove_thinking_tags
        
        # Strip thinking tags first (they don't count as "content")
        text_without_thinking = remove_thinking_tags(text)
        
        # Check if it matches the pure ignore pattern
        is_pure = bool(self.PURE_IGNORE_PATTERN.match(text_without_thinking))
        
        if is_pure:
            log.debug("Detected pure <IGNORE> tag in response")
        elif self.has_syntax(text):
            log.warning("Found <IGNORE> tag with additional content - treating as impure!")
        
        return is_pure
    
    def normalize_ignore(self, text: str) -> Optional[str]:
        """
        Normalize <IGNORE> tag to standard format.
        
        If text is a pure ignore, returns normalized "<IGNORE>".
        Otherwise returns None.
        
        Args:
            text: Text to normalize
            
        Returns:
            "<IGNORE>" if pure ignore, None otherwise
            
        Examples:
            >>> expr = IgnoreExpression()
            >>> expr.normalize_ignore("  <ignore>  ")
            "<IGNORE>"
            >>> expr.normalize_ignore("<IGNORE> text")
            None
        """
        if self.is_pure_ignore(text):
            return "<IGNORE>"
        return None
    
    def validate_ignore_response(self, text: str) -> Tuple[bool, str]:
        """
        Validate an LLM response for ignore handling.
        
        Returns a tuple of (should_ignore, reason).
        
        Args:
            text: LLM response text
            
        Returns:
            Tuple of (should_ignore: bool, reason: str)
            
        Examples:
            >>> expr = IgnoreExpression()
            >>> expr.validate_ignore_response("<IGNORE>")
            (True, "Pure ignore tag detected")
            >>> expr.validate_ignore_response("<IGNORE> Sorry")
            (False, "Ignore tag found but with additional content")
            >>> expr.validate_ignore_response("Hello")
            (False, "No ignore tag found")
        """
        if not text:
            return False, "Empty response"
        
        if self.is_pure_ignore(text):
            return True, "Pure ignore tag detected"
        
        if self.has_syntax(text):
            return False, "Ignore tag found but with additional content"
        
        return False, "No ignore tag found"
    
    def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate configuration for ignore system.
        
        Checks for mutual exclusivity with response filter.
        """
        # Check if both ignore system and response filter are enabled
        ignore_enabled = self.is_enabled(config)
        filter_enabled = config.get("use_response_filter", False)
        
        if ignore_enabled and filter_enabled:
            return False, "Ignore system and response filter are mutually exclusive"
        
        return True, "Valid"
