"""
Message Processor - Message Formatting for API

Handles formatting of messages for AI API calls, including template
application and CBS processing.
"""

import logging
import datetime
from typing import Dict, Any, List, Optional
from messaging.buffer import PendingMessage
from messaging.short_id_manager import get_short_id_manager_sync
from utils.media_processor import MediaProcessor

log = logging.getLogger(__name__)


class MessageProcessor:
    """
    Processes and formats messages for AI API calls.
    
    This replaces the scattered formatting logic from:
    - capture_message() in func.py
    - format_to_send() in func.py
    - _prepare_messages() in chat_service.py
    
    Example:
        processor = MessageProcessor()
        formatted = processor.format_messages(
            pending_messages, session, message_author
        )
    """
    
    def __init__(self):
        """Initialize the message processor."""
        self.short_id_manager = get_short_id_manager_sync()
        self.media_processor = MediaProcessor()
    
    async def _apply_template(
        self,
        template: str,
        message: PendingMessage,
        session: Dict[str, Any],
        reply_message: Optional[PendingMessage] = None
    ) -> str:
        """
        Apply formatting template to a message.
        
        Args:
            template: Template string with placeholders
            message: Message to format
            session: AI session (for server/channel/ai_name context)
            reply_message: Optional reply message
            
        Returns:
            Formatted message string
        """
        # Get context for short ID generation
        server_id = session.get("server_id", "unknown")
        channel_id = session.get("channel_id", "unknown")
        ai_name = session.get("ai_name", "unknown")
        
        # Generate short ID for this message
        short_id = await self.short_id_manager.get_short_id(
            server_id, channel_id, ai_name, message.message_id
        )
        
        # Build message content with attachments/stickers
        message_content = message.content
        
        # Add attachment information
        if hasattr(message, 'attachments') and message.attachments:
            for att in message.attachments:
                filename = att.get('filename', 'file')
                url = att.get('url', '')
                message_content += f"\n[Anexo: {filename}]({url})"
        
        # Add sticker information
        if hasattr(message, 'stickers') and message.stickers:
            for sticker in message.stickers:
                name = sticker.get('name', 'sticker')
                url = sticker.get('url', '')
                message_content += f"\n[{name}]({url})"
        
        # Prepare template variables
        syntax = {
            "time": datetime.datetime.fromtimestamp(message.timestamp).strftime("%H:%M"),
            "username": message.author_name,  # @lixxrarin (for mentions)
            "name": message.author_display_name,  # Rarin (display name)
            "message": message_content,
            "message_id": message.message_id,  # Full Discord ID (17-20 digits)
            "short_id": short_id  # Short ID (sequential integer)
        }
        
        # Add reply information if available
        if reply_message:
            # Generate short ID for reply target
            reply_short_id = await self.short_id_manager.get_short_id(
                server_id, channel_id, ai_name, reply_message.message_id
            )
            
            # Generate quote for reply (shows original message content)
            # Truncate if too long to save tokens
            quoted_content = reply_message.content[:100]
            if len(reply_message.content) > 100:
                quoted_content += "..."
            
            # Determine author for quote
            # author_display_name is set in pipeline.py:
            # - For bot messages: uses AI name (e.g., "Hashi")
            # - For user messages: uses user's display name
            quote_author = reply_message.author_display_name or reply_message.author_name or "Unknown"
            
            # Format quote as markdown quote
            quote_line = f"> {quote_author}: {quoted_content}\n"
            
            syntax.update({
                "reply_username": reply_message.author_name,  # @kaio12385
                "reply_name": reply_message.author_display_name,  # Kaio
                "reply_message": reply_message.content,
                "reply_message_id": reply_message.message_id,  # Full Discord ID
                "reply_short_id": reply_short_id,  # Short ID
                "quote": quote_line  # Quote of original message
            })
        else:
            # No reply - add empty quote
            syntax["quote"] = ""
        
        try:
            return template.format(**syntax)
        except KeyError as e:
            log.warning("Template formatting error: %s", e)
            return f"[{syntax['time']}] {syntax['name']} #{short_id}: {syntax['message']}"
    
    async def format_single_message(
        self,
        message: PendingMessage,
        session: Dict[str, Any],
        reply_message: Optional[PendingMessage] = None
    ) -> str:
        """
        Format a single message using session configuration.
        
        Args:
            message: Message to format
            session: AI session configuration
            reply_message: Optional reply message
            
        Returns:
            Formatted message string
        """
        config = session.get("config", {})
        
        # Choose template based on whether it's a reply
        if reply_message:
            template = config.get(
                "user_reply_format_syntax",
                "┌ @{reply_username} ({reply_name}) [ID: {reply_message_id}]: {reply_message}\n"
                "└ [{time}] @{username} ({name}) [ID: {message_id}]: {message}"
            )
        else:
            template = config.get(
                "user_format_syntax",
                "[{time}] @{username} ({name}) [ID: {message_id}]: {message}"
            )
        
        return await self._apply_template(template, message, session, reply_message)
    
    async def process_message_images(
        self,
        message: PendingMessage,
        session: Dict[str, Any],
        server_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Process images from a message using MediaProcessor.
        
        Args:
            message: Message with potential image attachments
            session: AI session configuration
            server_id: Server ID for API connection resolution
            
        Returns:
            List of processed image dicts
        """
        # Check if message has attachments
        if not hasattr(message, 'attachments') or not message.attachments:
            return []
        
        # Get vision configuration from API connection or fallback to session config
        vision_config = {
            'vision_enabled': False,
            'vision_detail': 'auto',
            'max_image_size': 20
        }
        
        # Try to get from API connection first
        if server_id:
            connection_name = session.get("api_connection")
            if connection_name:
                import utils.func as func
                connection = func.get_api_connection(server_id, connection_name)
                if connection:
                    vision_config = {
                        'vision_enabled': connection.get('vision_enabled', False),
                        'vision_detail': connection.get('vision_detail', 'auto'),
                        'max_image_size': connection.get('max_image_size', 20)
                    }
        
        # Fallback to session config if no API connection
        if not vision_config.get('vision_enabled'):
            config = session.get("config", {})
            vision_config = {
                'vision_enabled': config.get('vision_enabled', False),
                'vision_detail': config.get('vision_detail', 'auto'),
                'max_image_size': config.get('max_image_size', 20)
            }
        
        # Process attachments
        result = await self.media_processor.process_attachments(
            attachments=message.attachments,
            vision_config=vision_config
        )
        
        return result.get('images', [])
    
    async def format_message_with_media(
        self,
        message: PendingMessage,
        session: Dict[str, Any],
        reply_message: Optional[PendingMessage] = None
    ) -> Dict[str, Any]:
        """
        Format a message with both text and images.
        
        Args:
            message: Message to format
            session: AI session configuration
            reply_message: Optional reply message
            
        Returns:
            Dict with 'text' and 'images' keys
        """
        # Format text
        text = await self.format_single_message(message, session, reply_message)
        
        # Process images
        images = await self.process_message_images(message, session)
        
        return {
            'text': text,
            'images': images,
            'has_images': len(images) > 0
        }
    
    async def format_messages(
        self,
        messages: List[PendingMessage],
        session: Dict[str, Any]
    ) -> str:
        """
        Format multiple messages into a single string.
        
        Args:
            messages: List of messages to format
            session: AI session configuration
            
        Returns:
            Combined formatted message string
        """
        if not messages:
            return ""
        
        formatted_messages = []
        
        for message in messages:
            # Check if message has a reply
            reply_message = None
            if message.reply_to:
                # Find the reply message in the list
                for msg in messages:
                    if msg.message_id == message.reply_to:
                        reply_message = msg
                        break
            
            # Use format_single_message which handles template selection
            formatted = await self.format_single_message(message, session, reply_message)
            formatted_messages.append(formatted)
        
        return "\n".join(formatted_messages)
    
    def process_cbs(
        self,
        text: str,
        session: Dict[str, Any],
        message_author: Optional[Any] = None
    ) -> str:
        """
        Process Character Book Syntax (CBS) in text.
        
        Args:
            text: Text to process
            session: AI session configuration
            message_author: Discord message author (for {{user}} replacement)
            
        Returns:
            Processed text with CBS replaced
        """
        try:
            from utils.ccv3 import process_cbs
            
            # Get character card data
            card_data = (session.get("character_card") or {}).get("data", {})
            char_name = card_data.get("nickname") or card_data.get("name", "AI")
            
            # Determine user name based on config
            config = session.get("config", {})
            replacement_mode = config.get("user_syntax_replacement", "none")
            
            if replacement_mode == "none" or not message_author:
                user_name = "{{user}}"
            elif replacement_mode == "username":
                user_name = message_author.name
            elif replacement_mode == "display_name":
                user_name = message_author.global_name or message_author.name
            elif replacement_mode == "mention":
                user_name = f"<@{message_author.id}>"
            elif replacement_mode == "id":
                user_name = str(message_author.id)
            else:
                user_name = "{{user}}"
            
            # Process CBS
            return process_cbs(text, char_name, user_name, session)
            
        except Exception as e:
            log.error("Error processing CBS: %s", e)
            return text
    
    async def prepare_for_api(
        self,
        messages: List[PendingMessage],
        session: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        message_author: Optional[Any] = None
    ) -> List[Dict[str, str]]:
        """
        Prepare complete message list for API call.
        
        This combines:
        1. System messages (character description, system prompt)
        2. Conversation history
        3. Current pending messages
        
        Args:
            messages: Pending messages from buffer
            session: AI session configuration
            conversation_history: Previous conversation history
            message_author: Discord message author
            
        Returns:
            List of messages ready for API
        """
        api_messages = []
        config = session.get("config", {})
        card_data = (session.get("character_card") or {}).get("data", {})
        
        # 1. Add character description (if available)
        description = card_data.get("description", "")
        if description:
            description = self.process_cbs(description, session, message_author)
            api_messages.append({"role": "system", "content": description})
        
        # 2. Add system message (configuration)
        system_message = config.get("system_message")
        if system_message:
            system_message = self.process_cbs(system_message, session, message_author)
            api_messages.append({"role": "system", "content": system_message})
        
        # 3. Add reply prompt (if enabled)
        if config.get("enable_reply_system", False):
            reply_prompt = config.get("reply_prompt")
            if reply_prompt:
                reply_prompt = self.process_cbs(reply_prompt, session, message_author)
                api_messages.append({"role": "system", "content": reply_prompt})
        
        # 4. Add conversation history
        api_messages.extend(conversation_history)
        
        # 5. Add current pending messages
        if messages:
            formatted_content = await self.format_messages(messages, session)
            formatted_content = self.process_cbs(formatted_content, session, message_author)
            api_messages.append({"role": "user", "content": formatted_content})
        
        return api_messages
    
    def extract_message_ids(self, formatted_content: str) -> List[str]:
        """
        Extract message IDs from formatted content.
        
        This is useful for tracking which messages were processed.
        
        Args:
            formatted_content: Formatted message string
            
        Returns:
            List of message IDs found in content
        """
        import re
        message_ids = re.findall(r'ID:\s*(\d+)', formatted_content)
        return message_ids
    
    def clean_response(
        self,
        response: str,
        session: Dict[str, Any]
    ) -> str:
        """
        Clean AI response before saving to history.
        
        Respects save_thinking_in_history setting - only removes thinking tags if disabled.
        Always preserves reply tags.
        
        Args:
            response: Raw AI response
            session: AI session configuration
            
        Returns:
            Cleaned response
        """
        try:
            import utils.text_processor as text_processor
            import utils.func as func
            
            config = session.get("config", {})
            server_id = session.get("server_id", "")
            
            # Get save_thinking_in_history from connection
            save_thinking = True  # Default
            connection_name = session.get("api_connection")
            if connection_name and server_id:
                connection = func.get_api_connection(server_id, connection_name)
                if connection:
                    save_thinking = connection.get("save_thinking_in_history", True)
            else:
                # Fallback to session config
                save_thinking = config.get("save_thinking_in_history", True)
            
            # Only remove thinking tags if save_thinking_in_history is False
            if not save_thinking:
                # Get thinking tag patterns from API connection or config
                from utils.func import get_thinking_config
                hide_thinking, thinking_patterns = get_thinking_config(
                    session,
                    server_id
                )
                
                # Clean response (remove thinking tags, keep reply tags)
                cleaned = text_processor.clean_ai_response(
                    response,
                    thinking_patterns=thinking_patterns,
                    remove_emojis=config.get("remove_ai_emoji", False),
                    custom_patterns=config.get("remove_ai_text_from", []),
                    remove_reply_syntax=False  # Keep reply tags in history!
                )
                return cleaned
            else:
                # Keep thinking tags, but still apply other cleaning if needed
                cleaned = response
                if config.get("remove_ai_emoji", False):
                    cleaned = text_processor.remove_emoji(cleaned)
                custom_patterns = config.get("remove_ai_text_from", [])
                if custom_patterns:
                    cleaned = text_processor.apply_custom_patterns(cleaned, custom_patterns)
                return cleaned
            
        except Exception as e:
            log.error("Error cleaning response: %s", e)
            return response
    
    def prepare_for_display(
        self,
        response: str,
        session: Dict[str, Any]
    ) -> str:
        """
        Prepare AI response for display (removes thinking tags).
        
        Args:
            response: Raw AI response
            session: AI session configuration
            
        Returns:
            Response ready for display
        """
        try:
            import utils.text_processor as text_processor
            
            config = session.get("config", {})
            
            # Get thinking tag patterns
            from utils.func import get_thinking_config
            hide_thinking, thinking_patterns = get_thinking_config(
                session,
                session.get("server_id", "")
            )
            
            if hide_thinking:
                # Remove thinking tags but keep reply tags for parsing
                display_response = text_processor.clean_ai_response(
                    response,
                    thinking_patterns=thinking_patterns,
                    remove_emojis=config.get("remove_ai_emoji", False),
                    custom_patterns=config.get("remove_ai_text_from", []),
                    remove_reply_syntax=False  # Keep for parsing!
                )
            else:
                # Only remove emojis and custom patterns
                display_response = response
                if config.get("remove_ai_emoji", False):
                    display_response = text_processor.remove_emoji(display_response)
                custom_patterns = config.get("remove_ai_text_from", [])
                display_response = text_processor.apply_custom_patterns(
                    display_response, custom_patterns
                )
            
            return display_response
            
        except Exception as e:
            log.error("Error preparing response for display: %s", e)
            return response


# Global processor instance
_global_processor: Optional[MessageProcessor] = None


def get_processor() -> MessageProcessor:
    """Get the global message processor instance."""
    global _global_processor
    if _global_processor is None:
        _global_processor = MessageProcessor()
    return _global_processor
