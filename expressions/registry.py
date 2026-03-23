"""
Expression Registry - Central Management System

This module provides the ExpressionRegistry class, which manages all
registered expressions and coordinates their processing.
"""

from typing import Dict, List, Optional, Set
import logging

from .base import BaseExpression, ExpressionResult

log = logging.getLogger(__name__)


class ExpressionRegistry:
    """
    Central registry for managing advanced expressions.
    
    The registry:
    - Stores all available expressions
    - Provides lookup by name
    - Coordinates processing of text through multiple expressions
    - Manages expression priorities and dependencies
    
    Usage:
        registry = ExpressionRegistry()
        registry.register(ReplyExpression())
        registry.register(ReactionExpression())
        
        result = registry.process_text(response, config)
    """
    
    def __init__(self):
        """Initialize an empty registry."""
        self._expressions: Dict[str, BaseExpression] = {}
        self._processing_order: List[str] = []
    
    def register(self, expression: BaseExpression) -> None:
        """
        Register a new expression.
        
        Args:
            expression: Expression instance to register
            
        Raises:
            ValueError: If an expression with the same name is already registered
        """
        if expression.name in self._expressions:
            log.warning(
                f"Expression '{expression.name}' is already registered. "
                f"Replacing with new instance."
            )
        
        self._expressions[expression.name] = expression
        
        # Add to processing order if not already there
        if expression.name not in self._processing_order:
            self._processing_order.append(expression.name)
        
        log.debug(f"Registered expression: {expression.name} ({expression.display_name})")
    
    def unregister(self, name: str) -> bool:
        """
        Unregister an expression by name.
        
        Args:
            name: Name of the expression to unregister
            
        Returns:
            True if unregistered, False if not found
        """
        if name in self._expressions:
            del self._expressions[name]
            if name in self._processing_order:
                self._processing_order.remove(name)
            log.debug(f"Unregistered expression: {name}")
            return True
        return False
    
    def get(self, name: str) -> Optional[BaseExpression]:
        """
        Get an expression by name.
        
        Args:
            name: Name of the expression
            
        Returns:
            Expression instance or None if not found
        """
        return self._expressions.get(name)
    
    def get_all(self) -> List[BaseExpression]:
        """
        Get all registered expressions.
        
        Returns:
            List of all expression instances
        """
        return list(self._expressions.values())
    
    def get_all_names(self) -> List[str]:
        """
        Get names of all registered expressions.
        
        Returns:
            List of expression names
        """
        return list(self._expressions.keys())
    
    def get_enabled(self, config: Dict) -> List[BaseExpression]:
        """
        Get all expressions that are enabled in the configuration.
        
        Args:
            config: AI configuration dictionary
            
        Returns:
            List of enabled expression instances
        """
        enabled = []
        for expr in self._expressions.values():
            if expr.is_enabled(config):
                enabled.append(expr)
        return enabled
    
    def get_enabled_names(self, config: Dict) -> List[str]:
        """
        Get names of all enabled expressions.
        
        Args:
            config: AI configuration dictionary
            
        Returns:
            List of enabled expression names
        """
        return [expr.name for expr in self.get_enabled(config)]
    
    def set_processing_order(self, order: List[str]) -> None:
        """
        Set the order in which expressions are processed.
        
        This is important because some expressions may depend on others
        or need to be processed first (e.g., ignore system).
        
        Args:
            order: List of expression names in desired processing order
            
        Raises:
            ValueError: If any name in order is not registered
        """
        # Validate all names are registered
        for name in order:
            if name not in self._expressions:
                raise ValueError(f"Expression '{name}' is not registered")
        
        # Check for missing expressions
        registered_names = set(self._expressions.keys())
        order_names = set(order)
        missing = registered_names - order_names
        
        if missing:
            log.warning(
                f"Processing order is missing expressions: {missing}. "
                f"They will be appended to the end."
            )
            order = order + list(missing)
        
        self._processing_order = order
        log.debug(f"Processing order set to: {order}")
    
    def get_processing_order(self) -> List[str]:
        """
        Get the current processing order.
        
        Returns:
            List of expression names in processing order
        """
        return self._processing_order.copy()
    
    def process_text(
        self,
        text: str,
        config: Dict,
        expression_names: Optional[List[str]] = None
    ) -> ExpressionResult:
        """
        Process text through enabled expressions.
        
        This is the main entry point for expression processing. It:
        1. Gets all enabled expressions (or specified ones)
        2. Processes them in the defined order
        3. Merges results into a single ExpressionResult
        
        Args:
            text: Text to process
            config: AI configuration dictionary
            expression_names: Optional list of specific expressions to process
                            If None, all enabled expressions are processed
            
        Returns:
            Merged ExpressionResult from all processed expressions
        """
        if not text:
            return ExpressionResult()
        
        # Determine which expressions to process
        if expression_names:
            # Process specific expressions
            expressions_to_process = []
            for name in expression_names:
                expr = self.get(name)
                if expr and expr.is_enabled(config):
                    expressions_to_process.append(expr)
                elif expr:
                    log.debug(f"Expression '{name}' is disabled, skipping")
                else:
                    log.warning(f"Expression '{name}' not found in registry")
        else:
            # Process all enabled expressions
            expressions_to_process = self.get_enabled(config)
        
        if not expressions_to_process:
            log.debug("No enabled expressions to process")
            return ExpressionResult()
        
        # Sort by processing order
        expressions_to_process.sort(
            key=lambda e: self._processing_order.index(e.name)
            if e.name in self._processing_order
            else len(self._processing_order)
        )
        
        # Process each expression
        merged_result = ExpressionResult()
        
        for expr in expressions_to_process:
            if not expr.has_syntax(text):
                continue
            
            try:
                result = expr.parse(text, config)
                merged_result.merge(result)
                
                log.debug(
                    f"Processed {expr.name}: "
                    f"skip={result.should_skip}, "
                    f"segments={len(result.text_segments)}, "
                    f"reactions={len(result.reactions)}"
                )
                
                # If should_skip is True, stop processing
                if result.should_skip:
                    log.debug(f"Expression '{expr.name}' set should_skip=True, stopping")
                    break
                
            except Exception as e:
                log.error(f"Error processing expression '{expr.name}': {e}", exc_info=True)
                # Continue processing other expressions
        
        return merged_result
    
    def has_any_syntax(self, text: str, config: Dict) -> bool:
        """
        Check if text contains syntax from any enabled expression.
        
        Args:
            text: Text to check
            config: AI configuration dictionary
            
        Returns:
            True if any enabled expression has syntax in text
        """
        if not text:
            return False
        
        for expr in self.get_enabled(config):
            if expr.has_syntax(text):
                return True
        
        return False
    
    def remove_all_syntax(self, text: str, config: Dict) -> str:
        """
        Remove syntax from all enabled expressions.
        
        Useful for cleaning text when expressions are disabled or
        for fallback scenarios.
        
        Args:
            text: Text to clean
            config: AI configuration dictionary
            
        Returns:
            Text with all expression syntax removed
        """
        if not text:
            return text
        
        cleaned = text
        for expr in self.get_enabled(config):
            if expr.has_syntax(cleaned):
                cleaned = expr.remove_syntax(cleaned)
        
        return cleaned
    
    def get_prompts(self, config: Dict) -> Dict[str, str]:
        """
        Get prompts for all enabled expressions.
        
        Args:
            config: AI configuration dictionary
            
        Returns:
            Dictionary mapping expression names to their prompts
        """
        prompts = {}
        for expr in self.get_enabled(config):
            prompt = expr.get_prompt(config)
            if prompt:
                prompts[expr.name] = prompt
        return prompts
    
    def validate_config(self, config: Dict) -> Dict[str, tuple]:
        """
        Validate configuration for all expressions.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            Dictionary mapping expression names to (is_valid, message) tuples
        """
        results = {}
        for expr in self._expressions.values():
            is_valid, message = expr.validate_config(config)
            results[expr.name] = (is_valid, message)
        return results
    
    def __len__(self) -> int:
        """Return number of registered expressions."""
        return len(self._expressions)
    
    def __contains__(self, name: str) -> bool:
        """Check if an expression is registered."""
        return name in self._expressions
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<ExpressionRegistry: {len(self)} expressions registered>"


# Global registry instance
_global_registry: Optional[ExpressionRegistry] = None


def get_expression_registry() -> ExpressionRegistry:
    """
    Get the global expression registry instance.
    
    This ensures a single registry is used throughout the application.
    
    Returns:
        Global ExpressionRegistry instance
    """
    global _global_registry
    
    if _global_registry is None:
        _global_registry = ExpressionRegistry()
        log.debug("Created global expression registry")
    
    return _global_registry


def reset_registry() -> None:
    """
    Reset the global registry (mainly for testing).
    
    Warning: This will unregister all expressions!
    """
    global _global_registry
    _global_registry = None
    log.debug("Reset global expression registry")
