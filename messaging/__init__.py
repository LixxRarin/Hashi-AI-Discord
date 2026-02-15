"""
Messaging System - Unified Message Pipeline

This module provides a clean, efficient messaging system that replaces
the fragmented cache/history/tracking system with a unified pipeline.

Components:
- MessageIntake: Validates and filters incoming messages
- MessageBuffer: In-memory buffer for pending messages
- TimingController: Centralized timing logic
- MessageProcessor: Formats messages for API
- ConversationStore: Unified conversation storage
- ResponseManager: Manages AI responses and regeneration
- MessagePipeline: Main orchestrator

Usage:
    from messaging import get_pipeline
    
    pipeline = get_pipeline()
    await pipeline.process_message(discord_message)
"""

from messaging.pipeline import MessagePipeline, get_pipeline, init_pipeline

__all__ = ['MessagePipeline', 'get_pipeline', 'init_pipeline']
__version__ = '2.0.0'
