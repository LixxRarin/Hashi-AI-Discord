"""
Timing Controller - Centralized Timing Logic

This module centralizes ALL timing-related decisions in one place,
replacing the scattered logic across multiple files.

Key Features:
- Unified delay management
- Typing detection
- Message threshold checking
- Processing state awareness
- Configurable per-AI settings
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Constants
MONITOR_CHECK_INTERVAL = 0.5  # seconds between monitoring checks


@dataclass
class TimingConfig:
    """Configuration for timing behavior."""
    delay_for_generation: float = 4.0  # Seconds to wait before responding (reduced from 5.0)
    cache_count_threshold: int = 5  # Number of messages before auto-respond
    engaged_message_threshold: int = 2  # Minimum messages for engaged mode
    engaged_delay: float = 2.5  # Reduced delay for active conversations
    typing_detection_enabled: bool = True  # Detect user typing
    typing_grace_period: float = 2.0  # Extra seconds after typing stops
    
    @classmethod
    def from_session(cls, session: Dict[str, Any]) -> 'TimingConfig':
        """Create from session configuration."""
        config = session.get("config", {})
        return cls(
            delay_for_generation=config.get("delay_for_generation", 4.0),
            cache_count_threshold=config.get("cache_count_threshold", 5),
            engaged_message_threshold=config.get("engaged_message_threshold", 2),
            engaged_delay=config.get("engaged_delay", 2.5),
            typing_detection_enabled=True,
            typing_grace_period=2.0
        )


class TimingController:
    """
    Centralized timing controller for AI responses.
    
    This replaces the scattered timing logic from:
    - monitor_inactivity()
    - time_typing()
    - AI_send_message() delay checks
    - cache_count_threshold checks
    
    All timing decisions now go through this single controller.
    
    Example:
        controller = TimingController()
        should_respond = await controller.should_respond(
            server_id, channel_id, ai_name, session, buffer
        )
        if should_respond:
            # Generate response
            pass
    """
    
    def __init__(self):
        """Initialize the timing controller."""
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._last_check: Dict[str, float] = {}
        self._last_response_time: Dict[str, float] = {}  # Track when responses were sent
        self._response_lock = asyncio.Lock()  # Thread safety for response time tracking

    def _get_task_key(self, server_id: str, channel_id: str, ai_name: str) -> str:
        """Generate unique key for monitoring task."""
        return f"{server_id}_{channel_id}_{ai_name}"
    
    async def mark_response_sent(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> None:
        """
        Mark that a response was just sent.
        
        This starts a cooldown period where the count threshold is ignored,
        preventing rapid successive API calls.
        
        Thread-safe operation using asyncio.Lock.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
        """
        async with self._response_lock:
            key = self._get_task_key(server_id, channel_id, ai_name)
            self._last_response_time[key] = time.time()
    
    async def should_respond(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        session: Dict[str, Any],
        buffer,  # MessageBuffer instance
        force: bool = False
    ) -> bool:
        """
        Centralized decision: should the AI respond now?
        
        This considers:
        - Time since last message
        - Number of pending messages
        - User typing status
        - Processing state
        - Error state
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            session: AI session data
            buffer: MessageBuffer instance
            force: Force response regardless of timing
            
        Returns:
            True if AI should respond now
        """
        if force:
            return True
        
        # Check if already processing
        is_processing = await buffer.is_processing(server_id, channel_id, ai_name)
        if is_processing:
            return False
        
        # Check if last response was an error (prevent retry loops)
        if session.get("last_response_was_error", False):
            return False
        
        # Get timing configuration
        config = TimingConfig.from_session(session)
        
        # Get buffer state
        message_count = await buffer.get_count(server_id, channel_id, ai_name)
        if message_count == 0:
            return False
        
        last_activity = await buffer.get_last_activity(server_id, channel_id, ai_name)
        time_since_last = time.time() - last_activity
        
        # Check if user is still typing
        if config.typing_detection_enabled:
            is_typing = await buffer.is_typing(server_id, channel_id, ai_name)
            if is_typing:
                return False
        
        # Check if we just responded (cooldown logic to prevent spam)
        # Thread-safe access to response time tracking
        key = self._get_task_key(server_id, channel_id, ai_name)
        async with self._response_lock:
            if key in self._last_response_time:
                time_since_response = time.time() - self._last_response_time[key]
                
                # If we responded recently, ONLY use time-based trigger
                # Ignore count threshold to prevent rapid successive API calls
                if time_since_response < config.delay_for_generation:
                    # Only respond if time delay is met
                    should_respond_time = time_since_last >= config.delay_for_generation
                    if should_respond_time:
                        log.debug(
                            "AI %s responding (cooldown active, time-based): time=%.1fs",
                            ai_name, time_since_last
                        )
                    return should_respond_time
                else:
                    # Cooldown expired, clear the marker
                    del self._last_response_time[key]
        
        # Normal logic: respond if either condition is met
        should_respond_time = time_since_last >= config.delay_for_generation
        should_respond_count = message_count >= config.cache_count_threshold
        
        # Engaged conversation mode (2+ messages with shorter delay)
        # This creates a "zone" for active conversations that respond faster
        should_respond_engaged = (
            message_count >= config.engaged_message_threshold and
            time_since_last >= config.engaged_delay
        )
        
        if should_respond_time or should_respond_count or should_respond_engaged:
            log.debug(
                "AI %s responding: time=%.1fs/%ds, count=%d/%d, engaged=%s",
                ai_name, time_since_last, int(config.delay_for_generation),
                message_count, config.cache_count_threshold, should_respond_engaged
            )
            return True
        
        return False
    
    async def wait_for_response_window(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        session: Dict[str, Any],
        buffer,  # MessageBuffer instance
        check_interval: float = 0.5
    ) -> bool:
        """
        Wait for the appropriate time to respond, checking continuously.
        
        This replaces the complex delay logic in AI_send_message() that
        checks for typing during the delay period.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            session: AI session data
            buffer: MessageBuffer instance
            check_interval: How often to check (seconds)
            
        Returns:
            True if should proceed with response, False if cancelled
        """
        config = TimingConfig.from_session(session)
        initial_last_activity = await buffer.get_last_activity(
            server_id, channel_id, ai_name
        )
        
        checks_needed = int(config.delay_for_generation / check_interval)
        
        for check_num in range(checks_needed):
            await asyncio.sleep(check_interval)
            
            # Check if new activity occurred
            current_last_activity = await buffer.get_last_activity(
                server_id, channel_id, ai_name
            )
            
            if current_last_activity > initial_last_activity:
                # Reset timer
                initial_last_activity = current_last_activity
                check_num = 0
                
                # Wait full delay again
                for remaining_check in range(checks_needed):
                    await asyncio.sleep(check_interval)
                    
                    # Check again
                    current_last_activity = await buffer.get_last_activity(
                        server_id, channel_id, ai_name
                    )
                    
                    if current_last_activity > initial_last_activity:
                        return False
                
                break
        
        return True
    
    async def start_monitoring(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        session: Dict[str, Any],
        buffer,  # MessageBuffer instance
        response_callback: Callable[[], Awaitable[None]]
    ) -> None:
        """
        Start monitoring for auto-response triggers.
        
        This replaces the monitor_inactivity() function with a cleaner
        implementation that uses the centralized timing logic.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            session: AI session data
            buffer: MessageBuffer instance
            response_callback: Async function to call when should respond
        """
        task_key = self._get_task_key(server_id, channel_id, ai_name)
        
        # Check if there's already a monitoring task running
        if task_key in self._monitoring_tasks:
            old_task = self._monitoring_tasks[task_key]
            if not old_task.done():
                # Don't cancel or replace existing monitoring task
                # It will continue monitoring and respond when appropriate
                return
        
        # Start new monitoring task
        async def monitor():
            try:
                while True:
                    await asyncio.sleep(MONITOR_CHECK_INTERVAL)
                    
                    # Check if should respond
                    should_respond = await self.should_respond(
                        server_id, channel_id, ai_name, session, buffer
                    )
                    
                    if should_respond:
                        # Call response callback with try/finally to ensure cleanup
                        try:
                            # Call response callback (makes API call)
                            await response_callback()
                        finally:
                            # Mark that we just responded (starts cooldown to prevent spam)
                            # This is in finally to ensure it runs even if callback fails
                            await self.mark_response_sent(server_id, channel_id, ai_name)
                        
                        # Check if there are still messages in buffer
                        remaining_count = await buffer.get_count(server_id, channel_id, ai_name)
                        if remaining_count > 0:
                            # Continue monitoring (cooldown will prevent immediate re-response)
                            continue
                        else:
                            # No more messages, stop monitoring
                            break
                        
            except asyncio.CancelledError:
                pass
            except Exception as e:
                log.error("Error in monitoring for AI %s: %s", ai_name, e)
        
        self._monitoring_tasks[task_key] = asyncio.create_task(monitor())
    
    async def stop_monitoring(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str
    ) -> None:
        """
        Stop monitoring for an AI and cleanup associated resources.
        
        This includes cancelling the monitoring task and cleaning up
        any cooldown markers to prevent memory leaks.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
        """
        task_key = self._get_task_key(server_id, channel_id, ai_name)
        
        if task_key in self._monitoring_tasks:
            task = self._monitoring_tasks[task_key]
            if not task.done():
                task.cancel()
            del self._monitoring_tasks[task_key]
            
            # Cleanup cooldown marker to prevent memory leak
            async with self._response_lock:
                if task_key in self._last_response_time:
                    del self._last_response_time[task_key]
    
    async def stop_all_monitoring(self) -> None:
        """
        Stop all monitoring tasks and cleanup associated resources.
        
        This includes cancelling all monitoring tasks and cleaning up
        all cooldown markers to prevent memory leaks.
        """
        for task in self._monitoring_tasks.values():
            if not task.done():
                task.cancel()
        self._monitoring_tasks.clear()
        
        # Cleanup all cooldown markers
        async with self._response_lock:
            self._last_response_time.clear()
        
        log.debug("Stopped all monitoring tasks")
    
    async def update_typing_activity(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        buffer,  # MessageBuffer instance
        typing_duration: float = 8
    ) -> None:
        """
        Update typing activity for an AI.
        
        This replaces the time_typing() function with a cleaner
        implementation that updates the buffer directly.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            buffer: MessageBuffer instance
            typing_duration: How long to consider user as typing (seconds)
        """
        typing_until = time.time() + typing_duration
        await buffer.update_typing(server_id, channel_id, ai_name, typing_until)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get timing controller statistics.
        
        Returns:
            Dictionary with stats
        """
        active_monitors = sum(
            1 for task in self._monitoring_tasks.values()
            if not task.done()
        )
        
        return {
            "active_monitors": active_monitors,
            "total_tasks": len(self._monitoring_tasks)
        }


# Global controller instance
_global_controller: Optional[TimingController] = None


def get_timing_controller() -> TimingController:
    """Get the global timing controller instance."""
    global _global_controller
    if _global_controller is None:
        _global_controller = TimingController()
    return _global_controller
