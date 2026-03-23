"""
Base Classes for Advanced Expressions System

This module defines the core interfaces and data structures for the expressions system.
All expression implementations must inherit from BaseExpression.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field
import logging

log = logging.getLogger(__name__)


@dataclass
class ExpressionResult:
    """
    Result of processing an expression.
    
    This standardized format allows different expressions to communicate
    their results in a consistent way.
    
    Attributes:
        should_skip: If True, the message should not be sent (used by ignore system)
        text_segments: List of (message_id, text) tuples for replies
                      message_id can be None for non-reply messages
        reactions: List of (message_id, emoji) tuples for reactions
        metadata: Additional data specific to the expression
    """
    should_skip: bool = False
    text_segments: List[Tuple[Optional[str], str]] = field(default_factory=list)
    reactions: List[Tuple[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def merge(self, other: 'ExpressionResult') -> None:
        """
        Merge another result into this one.
        
        Args:
            other: Another ExpressionResult to merge
        """
        if other.should_skip:
            self.should_skip = True
        self.text_segments.extend(other.text_segments)
        self.reactions.extend(other.reactions)
        self.metadata.update(other.metadata)


class BaseExpression(ABC):
    """
    Abstract base class for all advanced expressions.
    
    An expression is a system that allows the LLM to interact with Discord
    in specific ways (e.g., replying to messages, reacting with emojis, etc.).
    
    To create a new expression:
    1. Inherit from this class
    2. Implement all abstract methods
    3. Register it in the ExpressionRegistry
    
    Example:
        class MyExpression(BaseExpression):
            @property
            def name(self) -> str:
                return "my_expression"
            
            # ... implement other methods
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique identifier for this expression.
        
        Used in configuration keys and registry lookups.
        Should be lowercase, no spaces (e.g., 'reply', 'reaction', 'ignore').
        
        Returns:
            Unique name string
        """
        pass
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """
        Human-readable name for this expression.
        
        Used in UI, commands, and documentation.
        
        Returns:
            Display name (e.g., 'Reply System', 'Reaction System')
        """
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """
        Brief description of what this expression does.
        
        Used in help text and documentation.
        
        Returns:
            Description string
        """
        pass
    
    @property
    @abstractmethod
    def syntax_pattern(self) -> str:
        """
        Regex pattern that matches this expression's syntax.
        
        Used for quick detection of expression presence in text.
        
        Returns:
            Regex pattern string (e.g., r'<REPLY:(\d+)>')
        """
        pass
    
    @property
    def config_key(self) -> str:
        """
        Configuration key for enabling/disabling this expression.
        
        Default: 'enable_{name}_system'
        Override if you need a different key.
        
        Returns:
            Configuration key string
        """
        return f"enable_{self.name}_system"
    
    @property
    def prompt_key(self) -> str:
        """
        Configuration key for this expression's prompt.
        
        Default: '{name}_prompt'
        Override if you need a different key.
        
        Returns:
            Prompt key string
        """
        return f"{self.name}_prompt"
    
    @property
    def icon(self) -> str:
        """
        Emoji icon representing this expression.
        
        Used in UI for visual identification.
        Override to customize.
        
        Returns:
            Emoji string (default: '🔧')
        """
        return "🔧"
    
    @abstractmethod
    def has_syntax(self, text: str) -> bool:
        """
        Check if text contains this expression's syntax.
        
        This should be a fast check, typically using regex search.
        
        Args:
            text: Text to check
            
        Returns:
            True if syntax is present, False otherwise
        """
        pass
    
    @abstractmethod
    def parse(self, text: str, config: Dict[str, Any]) -> ExpressionResult:
        """
        Parse text and extract expression data.
        
        This is the main processing method. It should:
        1. Extract all instances of the expression syntax
        2. Validate the extracted data
        3. Return an ExpressionResult with the processed data
        
        Args:
            text: Text to parse
            config: AI configuration dictionary
            
        Returns:
            ExpressionResult with parsed data
        """
        pass
    
    @abstractmethod
    def remove_syntax(self, text: str) -> str:
        """
        Remove this expression's syntax from text.
        
        Used for cleaning text before sending to Discord or
        when the expression system is disabled.
        
        Args:
            text: Text containing expression syntax
            
        Returns:
            Text with syntax removed
        """
        pass
    
    def get_default_prompt(self) -> str:
        """
        Get the default prompt for this expression.
        
        This prompt is injected into the LLM context to teach it
        how to use this expression.
        
        Override to provide a default prompt.
        
        Returns:
            Default prompt string (empty by default)
        """
        return ""
    
    def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate configuration for this expression.
        
        Override to add custom validation logic.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        return True, "Valid"
    
    def is_enabled(self, config: Dict[str, Any]) -> bool:
        """
        Check if this expression is enabled in the configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            True if enabled, False otherwise
        """
        advanced_expr = config.get("advanced_expressions", {})
        if self.name in advanced_expr:
            return advanced_expr[self.name].get("enabled", False)
        return False
    
    def get_prompt(self, config: Dict[str, Any]) -> str:
        """
        Get the prompt for this expression from configuration.
        
        Args:
            config: Configuration dictionary
            
        Returns:
            Prompt string (default prompt if not configured)
        """
        advanced_expr = config.get("advanced_expressions", {})
        if self.name in advanced_expr:
            prompt = advanced_expr[self.name].get("prompt")
            if prompt:
                return prompt
        
        # Use default prompt
        return self.get_default_prompt()
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<{self.__class__.__name__}: {self.name}>"
