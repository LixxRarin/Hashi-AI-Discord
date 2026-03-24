"""
Poll Expression - Discord Poll Creation System

This module provides the Poll expression, which allows the LLM to create
Discord polls and query their results via function calling.

Syntax: <POLL:duration_hours:allow_multiple|question|option1|option2|...>

The LLM controls all parameters: duration, multiple choice, and options.

Example:
    <POLL:24:false|Favorite language?|Python|JavaScript|Rust|Go>
    <POLL:48:true|Interests? (pick multiple)|Tech|Art|Music|Sports>
    
Query Results:
    Use get_poll_info(message_id) function to check poll results.
"""

import re
from typing import Dict, Any, List, Tuple, Optional
import logging

from .base import BaseExpression, ExpressionResult

log = logging.getLogger(__name__)


class PollExpression(BaseExpression):
    """
    Poll System - Allows AI to create Discord polls and query results.
    
    This expression enables the LLM to create polls with full control over
    duration, multiple choice, and options.
    """
    
    # Regex pattern to capture <POLL:duration:multiple|question|options...>
    # Format: <POLL:24:false|Question?|Opt1|Opt2|Opt3>
    POLL_PATTERN = r'<POLL:(\d+):(true|false)\|([^|]+)(\|[^>]+)+>'
    
    # Discord limits
    MIN_OPTIONS = 2
    MAX_OPTIONS = 10
    MIN_DURATION_HOURS = 1
    MAX_DURATION_HOURS = 168  # 7 days
    
    @property
    def name(self) -> str:
        return "poll"
    
    @property
    def display_name(self) -> str:
        return "Poll System"
    
    @property
    def description(self) -> str:
        return "Allows AI to create Discord polls and query results via function calling"
    
    @property
    def syntax_pattern(self) -> str:
        return self.POLL_PATTERN
    
    @property
    def icon(self) -> str:
        return "🗳️"
    
    def has_syntax(self, text: str) -> bool:
        """Check if text contains poll syntax."""
        if not text:
            return False
        return bool(re.search(self.POLL_PATTERN, text))
    
    def parse(self, text: str, config: Dict[str, Any]) -> ExpressionResult:
        """
        Parse poll syntax and extract poll data.
        
        Args:
            text: Text containing poll syntax
            config: AI configuration
            
        Returns:
            ExpressionResult with metadata about polls
        """
        polls = self.extract_polls(text)
        
        return ExpressionResult(
            metadata={
                "expression": "poll",
                "polls": polls,
                "poll_count": len(polls)
            }
        )
    
    def remove_syntax(self, text: str) -> str:
        """
        Remove poll tags from text.
        
        Args:
            text: Text containing poll syntax
            
        Returns:
            Text with poll tags removed
        """
        if not text:
            return text
        
        return re.sub(self.POLL_PATTERN, '', text).strip()
    
    def get_default_prompt(self) -> str:
        """Get the default prompt for the poll system."""
        return """Poll Syntax: <POLL:duration_hours:allow_multiple|question|option1|option2|...>

Create polls to gather community opinions.

PARAMETERS (YOU control these):
- duration_hours: 1-168 (1 hour to 7 days)
- allow_multiple: true/false (multiple choice?)
- question: Your poll question
- options: 2-10 options (Discord limit)

EXAMPLES:
<POLL:24:false|Favorite language?|Python|JavaScript|Rust|Go>
<POLL:48:true|Interests? (pick multiple)|Tech|Art|Music|Sports>
<POLL:1:false|Lunch today?|Pizza|Burger|Salad>

QUERYING RESULTS:
Use get_poll_info(message_id) to check results anytime.
Returns vote counts, status, and which option is winning."""
    
    def extract_polls(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract all polls from text with validation.
        
        Args:
            text: Text containing poll syntax
            
        Returns:
            List of dicts with poll information:
            [
                {
                    "duration_hours": 24,
                    "allow_multiple": False,
                    "question": "Question?",
                    "options": ["Opt1", "Opt2", "Opt3"],
                    "valid": True,
                    "error": None
                }
            ]
        """
        if not text:
            return []
        
        polls = []
        
        for match in re.finditer(self.POLL_PATTERN, text):
            try:
                # Extract components
                duration_str = match.group(1)
                allow_multiple_str = match.group(2)
                question = match.group(3).strip()
                
                # Extract options (everything after question, split by |)
                # Split at most 2 times to get: <POLL:duration:multiple | question | all_options>
                options_part = match.group(0).split('|', 2)[2]  # Get everything after question
                options_part = options_part.rstrip('>')  # Remove closing >
                options = [opt.strip() for opt in options_part.split('|') if opt.strip()]
                
                # Parse parameters
                duration_hours = int(duration_str)
                allow_multiple = allow_multiple_str.lower() == 'true'
                
                # Validate
                is_valid, error = self.validate_poll_data(
                    duration_hours, question, options
                )
                
                poll_data = {
                    "duration_hours": duration_hours,
                    "allow_multiple": allow_multiple,
                    "question": question,
                    "options": options,
                    "valid": is_valid,
                    "error": error,
                    "raw_match": match.group(0)
                }
                
                polls.append(poll_data)
                
                if is_valid:
                    log.info(
                        f"Parsed valid poll: '{question}' with {len(options)} options, "
                        f"{duration_hours}h duration, multiple={allow_multiple}"
                    )
                else:
                    log.warning(f"Invalid poll syntax: {error}")
                
            except Exception as e:
                log.error(f"Error parsing poll: {e}", exc_info=True)
                polls.append({
                    "valid": False,
                    "error": f"Parse error: {str(e)}",
                    "raw_match": match.group(0)
                })
        
        return polls
    
    def validate_poll_data(
        self,
        duration_hours: int,
        question: str,
        options: List[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate poll parameters against Discord limits.
        
        Args:
            duration_hours: Poll duration in hours
            question: Poll question
            options: List of poll options
            
        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
        """
        # Validate duration
        if duration_hours < self.MIN_DURATION_HOURS:
            return False, f"Duration must be at least {self.MIN_DURATION_HOURS} hour"
        
        if duration_hours > self.MAX_DURATION_HOURS:
            return False, f"Duration cannot exceed {self.MAX_DURATION_HOURS} hours (7 days)"
        
        # Validate question
        if not question or not question.strip():
            return False, "Question cannot be empty"
        
        if len(question) > 300:
            return False, f"Question too long ({len(question)} chars, max 300)"
        
        # Validate options
        if len(options) < self.MIN_OPTIONS:
            return False, f"Poll must have at least {self.MIN_OPTIONS} options"
        
        if len(options) > self.MAX_OPTIONS:
            return False, f"Poll cannot have more than {self.MAX_OPTIONS} options"
        
        # Check for empty options
        for i, option in enumerate(options):
            if not option or not option.strip():
                return False, f"Option {i+1} is empty"
            
            if len(option) > 55:
                return False, f"Option {i+1} too long ({len(option)} chars, max 55)"
        
        # Check for duplicate options
        unique_options = set(opt.lower() for opt in options)
        if len(unique_options) < len(options):
            return False, "Poll has duplicate options"
        
        return True, None
    
    def get_poll_by_position(self, text: str, position: int = 0) -> Optional[Dict[str, Any]]:
        """
        Get a specific poll from text by position.
        
        Args:
            text: Text containing poll syntax
            position: Which poll to get (0-indexed)
            
        Returns:
            Poll data dict or None if not found
        """
        polls = self.extract_polls(text)
        
        if 0 <= position < len(polls):
            return polls[position]
        
        return None
    
    def validate_syntax(self, text: str) -> Tuple[bool, str]:
        """
        Validate poll syntax in text.
        
        Args:
            text: Text to validate
            
        Returns:
            Tuple of (is_valid: bool, reason: str)
        """
        if not text:
            return False, "Empty text"
        
        if not self.has_syntax(text):
            return True, "No poll syntax (valid)"
        
        polls = self.extract_polls(text)
        
        if not polls:
            return False, "Failed to parse polls"
        
        # Check if all polls are valid
        invalid_polls = [p for p in polls if not p.get('valid', False)]
        
        if invalid_polls:
            errors = [p.get('error', 'Unknown error') for p in invalid_polls]
            return False, f"Invalid poll(s): {'; '.join(errors)}"
        
        return True, f"Valid poll syntax ({len(polls)} poll(s))"
