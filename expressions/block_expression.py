"""
Block Expression - Content Grouping System

This module provides the Block expression, which allows the LLM to send
content as a single message, ignoring line-by-line mode.

Syntax: <BLOCK>content</BLOCK>

The tags are removed before sending to Discord but kept in conversation history.

Example:
    <BLOCK>
    ```python
    def hello():
        print("Hello!")
    ```
    </BLOCK>
    
Behavior:
    - When send_message_line_by_line = true: Block content sent as single message
    - When send_message_line_by_line = false: Tags ignored (no effect)
    - Tags removed from Discord messages
    - Tags kept in conversation history
"""

import re
from typing import Dict, Any, List, Tuple
import logging

from .base import BaseExpression, ExpressionResult

log = logging.getLogger(__name__)


class BlockExpression(BaseExpression):
    """
    Block System - Allows AI to group content that should stay together.
    
    This expression enables the LLM to override line-by-line sending for
    specific content blocks (code, formatted text, etc.).
    """
    
    # Regex pattern to capture <BLOCK>content</BLOCK>
    # DOTALL flag makes . match newlines
    BLOCK_PATTERN = r'<BLOCK>(.*?)</BLOCK>'
    
    @property
    def name(self) -> str:
        return "block"
    
    @property
    def display_name(self) -> str:
        return "Block System"
    
    @property
    def description(self) -> str:
        return "Allows AI to group content that should be sent as a single message"
    
    @property
    def syntax_pattern(self) -> str:
        return self.BLOCK_PATTERN
    
    @property
    def icon(self) -> str:
        return "📦"
    
    def has_syntax(self, text: str) -> bool:
        """Check if text contains block syntax."""
        if not text:
            return False
        return bool(re.search(self.BLOCK_PATTERN, text, re.DOTALL))
    
    def parse(self, text: str, config: Dict[str, Any]) -> ExpressionResult:
        """
        Parse block syntax and extract block positions.
        
        Args:
            text: Text containing block syntax
            config: AI configuration
            
        Returns:
            ExpressionResult with metadata about block positions
        """
        blocks = self.extract_blocks(text)
        
        return ExpressionResult(
            metadata={
                "expression": "block",
                "blocks": blocks,
                "block_count": len(blocks)
            }
        )
    
    def remove_syntax(self, text: str) -> str:
        """
        Remove block tags but keep content.
        
        This is used when sending to Discord (users don't see tags).
        
        Args:
            text: Text containing block syntax
            
        Returns:
            Text with <BLOCK> and </BLOCK> tags removed
        """
        if not text:
            return text
        
        # Remove opening and closing tags
        cleaned = re.sub(r'<BLOCK>', '', text, flags=re.DOTALL)
        cleaned = re.sub(r'</BLOCK>', '', cleaned, flags=re.DOTALL)
        
        return cleaned
    
    def get_default_prompt(self) -> str:
        """Get the default prompt for the block system."""
        return """Block Syntax: <BLOCK>content</BLOCK>

Send content as a single message, ignoring line-by-line mode.

WHEN TO USE:
- Code snippets that must stay together
- Formatted content (lists, tables)
- Long explanations as one message

BEHAVIOR:
- Tags are REMOVED before sending to Discord (users don't see them)
- Tags are KEPT in conversation history (you remember them)
- Only works when line-by-line mode is enabled

EXAMPLE:
Here's the code:

<BLOCK>
```python
def hello():
    print("Hello!")
```
</BLOCK>

Hope this helps!

Result: 3 messages sent, but tags invisible to users."""
    
    def extract_blocks(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract all blocks from text with their positions.
        
        Args:
            text: Text containing block syntax
            
        Returns:
            List of dicts with block information:
            [
                {
                    "start": 10,  # Start position in original text
                    "end": 50,    # End position in original text
                    "content": "block content without tags",
                    "full_match": "<BLOCK>content</BLOCK>"
                }
            ]
        """
        if not text:
            return []
        
        blocks = []
        
        for match in re.finditer(self.BLOCK_PATTERN, text, re.DOTALL):
            block_info = {
                "start": match.start(),
                "end": match.end(),
                "content": match.group(1),  # Content without tags
                "full_match": match.group(0)  # Full match with tags
            }
            blocks.append(block_info)
        
        if blocks:
            log.debug(f"Found {len(blocks)} block(s) in text")
        
        return blocks
    
    def split_text_with_blocks(
        self,
        text: str,
        send_line_by_line: bool
    ) -> List[Tuple[str, bool]]:
        """
        Split text into segments, marking which are blocks.
        
        This is used by message_sender to know which parts to keep together.
        
        Args:
            text: Text containing block syntax
            send_line_by_line: Whether line-by-line mode is enabled
            
        Returns:
            List of tuples (content, is_block):
            [
                ("Line 1", False),
                ("Block content", True),
                ("Line 2", False)
            ]
        """
        if not send_line_by_line:
            # Line-by-line disabled, blocks have no effect
            # Just remove tags and return as single segment
            cleaned = self.remove_syntax(text)
            return [(cleaned, False)]
        
        if not self.has_syntax(text):
            # No blocks, return as-is
            return [(text, False)]
        
        segments = []
        last_end = 0
        
        # Find all blocks
        for match in re.finditer(self.BLOCK_PATTERN, text, re.DOTALL):
            # Add text before this block (if any)
            if match.start() > last_end:
                before_text = text[last_end:match.start()]
                if before_text.strip():
                    segments.append((before_text, False))
            
            # Add the block content (without tags)
            block_content = match.group(1)
            if block_content.strip():
                segments.append((block_content, True))
            
            last_end = match.end()
        
        # Add remaining text after last block (if any)
        if last_end < len(text):
            after_text = text[last_end:]
            if after_text.strip():
                segments.append((after_text, False))
        
        return segments
    
    def validate_syntax(self, text: str) -> Tuple[bool, str]:
        """
        Validate block syntax in text.
        
        Args:
            text: Text to validate
            
        Returns:
            Tuple of (is_valid: bool, reason: str)
        """
        if not text:
            return False, "Empty text"
        
        if not self.has_syntax(text):
            return True, "No block syntax (valid)"
        
        # Check for unclosed blocks
        open_count = len(re.findall(r'<BLOCK>', text, re.DOTALL))
        close_count = len(re.findall(r'</BLOCK>', text, re.DOTALL))
        
        if open_count != close_count:
            return False, f"Mismatched block tags: {open_count} opening, {close_count} closing"
        
        # Check for nested blocks (not supported)
        blocks = self.extract_blocks(text)
        for i, block in enumerate(blocks):
            # Check if this block's content contains another block tag
            if '<BLOCK>' in block['content'] or '</BLOCK>' in block['content']:
                return False, f"Nested blocks are not supported (block {i+1})"
        
        return True, "Valid block syntax"
