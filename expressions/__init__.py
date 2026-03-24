"""
Advanced Expressions System

This module provides a unified, extensible system for LLM-Discord interactions.
It replaces the scattered system implementations (reply_parser, reaction_parser, ignore_parser)
with a modular, plugin-based architecture.

Key Components:
- BaseExpression: Abstract base class for all expressions
- ExpressionResult: Standardized result format
- ExpressionRegistry: Central registry for managing expressions

Usage:
    from expressions import get_expression_registry
    
    registry = get_expression_registry()
    result = registry.process_text(response, config)
    
    if result.should_skip:
        # Handle ignore
    
    for message_id, text in result.text_segments:
        # Handle replies
    
    for message_id, emoji in result.reactions:
        # Handle reactions
"""

import logging

from .base import BaseExpression, ExpressionResult
from .registry import ExpressionRegistry, get_expression_registry

# Import all expression implementations
from .reply_expression import ReplyExpression
from .reaction_expression import ReactionExpression
from .ignore_expression import IgnoreExpression
from .poll_expression import PollExpression
from .block_expression import BlockExpression
from .embed_expression import EmbedExpression

log = logging.getLogger(__name__)

__all__ = [
    'BaseExpression',
    'ExpressionResult',
    'ExpressionRegistry',
    'get_expression_registry',
    'ReplyExpression',
    'ReactionExpression',
    'IgnoreExpression',
    'PollExpression',
    'BlockExpression',
    'EmbedExpression',
]

__version__ = '1.0.1'


def _register_builtin_expressions():
    """
    Register all built-in expressions with the global registry.
    
    This is called automatically when the module is imported.
    The processing order is important:
    1. Ignore - should be checked first (can skip entire message)
    2. Poll - creates polls (needs to be before reply/block)
    3. Block - processes content blocks
    4. Embed - creates embeds
    5. Reply - processes text segments
    6. Reaction - adds reactions to messages
    """
    registry = get_expression_registry()
    
    # Register expressions
    ignore_expr = IgnoreExpression()
    poll_expr = PollExpression()
    block_expr = BlockExpression()
    embed_expr = EmbedExpression()
    reply_expr = ReplyExpression()
    reaction_expr = ReactionExpression()
    
    registry.register(ignore_expr)
    registry.register(poll_expr)
    registry.register(block_expr)
    registry.register(embed_expr)
    registry.register(reply_expr)
    registry.register(reaction_expr)
    
    # Set processing order (important!)
    # Ignore should be first because it can skip the entire message
    # Poll, Block, Embed should be before Reply (they affect message structure)
    registry.set_processing_order(['ignore', 'poll', 'block', 'embed', 'reply', 'reaction'])
    
    log.debug(
        f"Registered {len(registry)} built-in expressions: "
        f"{', '.join(registry.get_all_names())}"
    )


# Auto-register built-in expressions when module is imported
_register_builtin_expressions()
