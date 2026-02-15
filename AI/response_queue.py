"""
Response Queue - Infrastructure Layer

This module handles asynchronous queue processing for AI responses.
It's pure infrastructure - no business logic, just queue management.

Classes:
    - ResponseQueue: Manages async queue processing with concurrency control
"""

import asyncio
from typing import Dict, Any, Callable, Awaitable

import utils.func as func


class ResponseQueue:
    """
    Manages asynchronous processing of AI response requests.
    """
    
    def __init__(self, max_concurrent: int = 3):
        """
        Initialize the response queue.
        
        Args:
            max_concurrent: Maximum number of concurrent API calls (ignored, kept for compatibility)
        """
        self.queue = asyncio.Queue()
        self._processing = False
    
    async def queue_request(
        self,
        server_id: str,
        channel_id: str,
        message,
        ai_name: str,
        chat_id: str,
        callback: Callable[[str], Awaitable[None]],
        request_handler: Callable[..., Awaitable[str]]
    ) -> bool:
        """
        Queue a response request to be processed.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            message: Discord message object
            ai_name: AI name
            chat_id: Chat session ID
            callback: Async callback function to receive the response
            request_handler: Function that will generate the response
            
        Returns:
            bool: Always True (kept for compatibility)
        """
        await self.queue.put({
            "server_id": server_id,
            "channel_id": channel_id,
            "message": message,
            "ai_name": ai_name,
            "chat_id": chat_id,
            "callback": callback,
            "request_handler": request_handler
        })
        func.log.debug(f"Queued AI response request for AI {ai_name} in channel {channel_id}")
        return True
    
    async def process_queue(self):
        """
        Background task to process the response queue.
        
        This runs continuously, processing requests as they come in.
        """
        func.log.info("Starting AI response queue processor")
        self._processing = True
        
        while self._processing:
            try:
                task_data = await self.queue.get()
                
                server_id = task_data["server_id"]
                channel_id = task_data["channel_id"]
                message = task_data["message"]
                ai_name = task_data["ai_name"]
                chat_id = task_data["chat_id"]
                callback = task_data["callback"]
                request_handler = task_data["request_handler"]
                
                func.log.debug(f"Processing AI response for channel {channel_id}")
                
                try:
                    # Call the request handler to generate the response
                    func.log.debug(
                        f"[QUEUE] Generating response for AI {ai_name} in channel {channel_id}"
                    )
                    
                    response = await request_handler(
                        message=message,
                        server_id=server_id,
                        channel_id=channel_id,
                        ai_name=ai_name,
                        chat_id=chat_id
                    )
                    
                    func.log.debug(
                        f"[QUEUE] Response generated for AI {ai_name}: "
                        f"{'None (cache empty)' if response is None else f'{len(response)} chars'}"
                    )
                    
                    # Call back with the response
                    await callback(response)
                    
                except Exception as e:
                    func.log.error(f"Error processing response for channel {channel_id}: {e}")
                    try:
                        await callback(f"I'm sorry, but I encountered an error: {str(e)}")
                    except Exception:
                        pass
                finally:
                    self.queue.task_done()
                    func.log.debug(f"Completed AI response for channel {channel_id}")
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                func.log.error(f"Critical error in process_queue: {e}")
                try:
                    self.queue.task_done()
                except Exception:
                    pass
                await asyncio.sleep(1)
    
    def stop_processing(self):
        """Stop the queue processor."""
        self._processing = False
        func.log.info("Stopping AI response queue processor")
    
    def get_queue_size(self) -> int:
        """Get the current queue size."""
        return self.queue.qsize()
    
    def is_processing(self) -> bool:
        """Check if the queue is currently processing."""
        return self._processing


_global_queue = ResponseQueue()


def get_queue() -> ResponseQueue:
    """Get the global response queue instance."""
    return _global_queue
