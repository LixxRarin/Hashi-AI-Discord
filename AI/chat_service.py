"""
Chat Service - Business Logic Orchestrator

Orchestrates AI interactions, managing conversation flow, message preparation,
and response processing.
"""

import asyncio
import uuid
import re
from typing import Dict, Any, Tuple, Optional, List

import utils.func as func
import utils.text_processor as text_processor

# Import AI module to trigger provider registration
import AI
from AI.provider_registry import get_registry

# Import character cards support
from utils.ccv3 import process_cbs, process_lorebook


class ChatService:
    """Central orchestrator for AI operations including conversation history, message preparation, and response processing."""
    
    def __init__(self):
        """Initialize the chat service."""
        from messaging.store import get_store
        self.store = get_store()
        self.registry = get_registry()
    
    @property
    def history_manager(self):
        """
        Expose store as history_manager.
        
        Existing code calls service.history_manager.list_chat_ids() etc,
        so this property makes those calls work.
        """
        return self.store
    
    def get_ai_history(self, server_id: str, channel_id: str, ai_name: str, chat_id: str = "default") -> List[Dict[str, str]]:
        """Get conversation history for a specific AI and chat."""
        try:
            chat = self.store._data.get(server_id, {}).get(channel_id, {}).get(ai_name, {}).get("chats", {}).get(chat_id)
            
            if chat:
                if hasattr(chat, 'get_messages_for_api'):
                    history = chat.get_messages_for_api()
                elif hasattr(chat, 'messages'):
                    history = [{"role": msg.role, "content": msg.content} for msg in chat.messages]
                elif isinstance(chat, dict) and "messages" in chat:
                    history = [{"role": msg["role"], "content": msg["content"]} for msg in chat["messages"]]
                else:
                    history = []
                return history
            
            return []
            
        except Exception as e:
            func.log.error(f"Error reading from unified store: {e}")
            return []
    
    async def set_ai_history(self, server_id: str, channel_id: str, ai_name: str, messages: List[Dict[str, str]], chat_id: str = "default", immediate: bool = False) -> bool:
        """Set conversation history for a specific AI and chat.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            messages: List of messages to set
            chat_id: Chat ID
            immediate: If True, save immediately to disk
            
        Returns:
            True if successful and persisted
        """
        success = await self.store.clear_history(server_id, channel_id, ai_name, chat_id, keep_greeting=False, immediate=immediate)
        
        if not success:
            return False
        
        for msg in messages:
            if msg["role"] == "user":
                await self.store.add_user_message(server_id, channel_id, ai_name, msg["content"], "system", chat_id)
            elif msg["role"] == "assistant":
                await self.store.add_assistant_message(server_id, channel_id, ai_name, msg["content"], [], chat_id, short_id=None)
        
        if immediate:
            return await self.store.save_immediate()
        return True
    
    async def append_to_history(self, server_id: str, channel_id: str, ai_name: str, role: str, content: str, chat_id: str = "default") -> None:
        """Append a message to the conversation history."""
        # Get session to check save_thinking_in_history setting
        channel_data = func.get_session_data(server_id, channel_id)
        session = channel_data.get(ai_name) if channel_data else None
        
        # Filter thinking tags if needed for assistant messages
        if role == "assistant" and session:
            # Get save_thinking_in_history from connection
            save_thinking = True  # Default
            connection_name = session.get("api_connection")
            if connection_name:
                connection = func.get_api_connection(server_id, connection_name)
                if connection:
                    save_thinking = connection.get("save_thinking_in_history", True)
            else:
                # Fallback to session config
                config = session.get("config", {})
                save_thinking = config.get("save_thinking_in_history", True)
            
            # If we shouldn't save thinking, strip thinking tags
            if not save_thinking:
                # Get thinking patterns from connection or use defaults
                thinking_patterns = [
                    r'<think>.*?</think>',
                    r'<thinking>.*?</thinking>',
                    r'<thought>.*?</thought>',
                    r'<reasoning>.*?</reasoning>'
                ]
                if connection_name:
                    connection = func.get_api_connection(server_id, connection_name)
                    if connection:
                        thinking_patterns = connection.get("thinking_tag_patterns", thinking_patterns)
                
                content = text_processor.clean_ai_response(
                    content,
                    thinking_patterns=thinking_patterns,
                    remove_emojis=False,
                    custom_patterns=[]
                )
        
        if role == "user":
            await self.store.add_user_message(server_id, channel_id, ai_name, content, "system", chat_id)
        elif role == "assistant":
            await self.store.add_assistant_message(server_id, channel_id, ai_name, content, [], chat_id, short_id=None)
    
    async def clear_ai_history(self, server_id: str, channel_id: str, ai_name: str, chat_id: Optional[str] = None, keep_greeting: bool = True, immediate: bool = False) -> bool:
        """Clear conversation history for a specific AI. If chat_id is None, clears all chats.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            chat_id: Chat ID (None = clear all chats)
            keep_greeting: Keep first assistant message
            immediate: If True, save immediately to disk
            
        Returns:
            True if successful
        """
        success = await self.store.clear_history(server_id, channel_id, ai_name, chat_id, keep_greeting=False, immediate=immediate)
        
        if not success:
            return False
        
        if success and keep_greeting:
            # Regenerate greeting from character card
            # Get session to access character card
            channel_data = func.get_session_data(server_id, channel_id)
            if channel_data and ai_name in channel_data:
                session = channel_data[ai_name]
                card_data = (session.get("character_card") or {}).get("data", {})
                
                if card_data:
                    # Get greeting from character card
                    config = session.get("config", {})
                    greeting_index = config.get("greeting_index", 0)
                    
                    greeting_text = None
                    if greeting_index == 0:
                        greeting_text = card_data.get("first_mes")
                    else:
                        alt_greetings = card_data.get("alternate_greetings") or []
                        if 0 <= greeting_index - 1 < len(alt_greetings):
                            greeting_text = alt_greetings[greeting_index - 1]
                    
                    if greeting_text:
                        char_name = card_data.get("nickname") or card_data.get("name", ai_name)
                        user_name = "{{user}}"
                        greeting_text = process_cbs(greeting_text, char_name, user_name, session)
                        
                        target_chat_id = chat_id if chat_id else "default"
                        await self.append_to_history(server_id, channel_id, ai_name, "assistant", greeting_text, target_chat_id)
                    else:
                        func.log.warning(f"No greeting text found for AI {ai_name}")
            
            if immediate:
                return await self.store.save_immediate()
        
        return success
    
    def _get_client(self, provider: str):
        """Get the appropriate client for the provider using the registry."""
        try:
            return self.registry.get_client(provider)
        except ValueError as e:
            available = ', '.join(self.registry.list_providers())
            raise ValueError(
                f"Unsupported provider: {provider}. "
                f"Available providers: {available}"
            )
    
    def _process_template(self, template: str, variables: Dict[str, str]) -> str:
        """
        Process template string replacing {{variable}} with values.
        
        Args:
            template: Template string with {{variable}} placeholders
            variables: Dictionary of variable names and their values
            
        Returns:
            Processed string with variables replaced
        """
        result = template
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result
    
    def _build_context_components(
        self,
        config: Dict,
        card_data: Dict,
        char_name: str,
        user_name: str,
        session: Dict,
        ai_name: str,
        chat_id: str,
        client,
        model: str,
        server_id: str,
        channel_id: str
    ) -> Dict[str, Optional[str]]:
        """
        Build all context components as a dictionary.
        
        Args:
            config: AI configuration
            card_data: Character card data
            char_name: Character name
            user_name: User name for CBS
            session: Session data
            ai_name: AI name
            chat_id: Chat ID
            client: AI client
            model: Model name
            server_id: Server ID
            channel_id: Channel ID
            
        Returns:
            Dictionary mapping component names to their content (None if disabled/empty)
        """
        components = {}
        
        # Character description
        description = card_data.get("description", "")
        if description:
            description = process_cbs(description, char_name, user_name, session)
            components["character_description"] = description
        else:
            components["character_description"] = None
        
        # System message
        system_message = config.get("system_message")
        if system_message:
            system_message = process_cbs(system_message, char_name, user_name, session)
            components["system_message"] = system_message
        else:
            components["system_message"] = None
        
        # Lorebook entries
        if config.get("use_lorebook", True) and card_data.get("character_book"):
            history = self.get_ai_history(server_id, channel_id, ai_name, chat_id)
            recent_messages = [msg.get("content", "") for msg in history[-10:]]
            
            lorebook_entries = process_lorebook(
                session,
                recent_messages,
                count_tokens_fn=client.count_tokens,
                model=model
            )
            
            if lorebook_entries:
                lorebook_content = "\n\n".join([
                    process_cbs(entry, char_name, user_name, session)
                    for entry in lorebook_entries
                ])
                components["lorebook_entries"] = lorebook_content
            else:
                components["lorebook_entries"] = None
        else:
            components["lorebook_entries"] = None
        
        # Memory prompt
        if config.get("enable_memory_system", False):
            from AI.tools.memory_tools import read_memory_content, _load_memory
            
            memory_content = read_memory_content(server_id, channel_id, ai_name, chat_id)
            memory_data = _load_memory(server_id, channel_id, ai_name, chat_id)
            memory_count = len(memory_data)
            
            # Always inject memory prompt when system is enabled, even if no memories yet
            if not memory_content:
                memory_content = "No memories saved yet."
            
            # Process memory prompt template
            memory_prompt_template = config.get("memory_prompt", "{{memory}}")
            memory_prompt = self._process_template(memory_prompt_template, {
                "memory": memory_content,
                "char": char_name,
                "user": user_name,
                "memory_count": str(memory_count),
                "ai_name": ai_name
            })
            components["memory_prompt"] = memory_prompt
            func.log.debug(f"Injected memory prompt for {ai_name}/{chat_id} ({memory_count} entries)")
        else:
            components["memory_prompt"] = None
        
        # Tool calling prompt
        tool_config = config.get("tool_calling", {})
        if tool_config.get("enabled", False):
            tool_prompt_template = config.get("tool_calling_prompt", "")
            if tool_prompt_template:
                tool_prompt = self._process_template(tool_prompt_template, {
                    "char": char_name,
                    "user": user_name
                })
                components["tool_calling_prompt"] = tool_prompt
                func.log.debug(f"Injected tool calling prompt for {ai_name}")
            else:
                components["tool_calling_prompt"] = None
        else:
            components["tool_calling_prompt"] = None
        
        # Reply prompt
        if config.get("enable_reply_system", False):
            reply_prompt = config.get("reply_prompt")
            if reply_prompt:
                reply_prompt = process_cbs(reply_prompt, char_name, user_name, session)
                components["reply_prompt"] = reply_prompt
            else:
                components["reply_prompt"] = None
        else:
            components["reply_prompt"] = None
        
        # Ignore prompt
        if config.get("enable_ignore_system", False):
            ignore_prompt = config.get("ignore_prompt")
            if ignore_prompt:
                ignore_prompt = process_cbs(ignore_prompt, char_name, user_name, session)
                components["ignore_prompt"] = ignore_prompt
            else:
                components["ignore_prompt"] = None
        else:
            components["ignore_prompt"] = None
        
        return components
    
    def _prepare_messages(
        self,
        user_content: str,
        server_id: str,
        channel_id: str,
        ai_name: str,
        session: Dict[str, Any],
        model: str,
        client,
        message_author=None,
        chat_id: str = "default",
        images: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, str]]:
        """Prepare messages for the API call including system prompts, history, and current message."""
        config = session.get("config", {})
        llm_params = client.get_llm_params(session, server_id)
        conv_messages = []
        
        card_data = (session.get("character_card") or {}).get("data", {})
        char_name = card_data.get("nickname") or card_data.get("name", ai_name)
        user_name = self._get_user_name_for_cbs(config, message_author)
        
        # Build all context components
        components = self._build_context_components(
            config, card_data, char_name, user_name, session,
            ai_name, chat_id, client, model, server_id, channel_id
        )
        
        # Get context order from config (with default fallback)
        context_order = config.get("context_order", [
            "character_description", "system_message", "lorebook_entries",
            "memory_prompt", "tool_calling_prompt", "reply_prompt", "ignore_prompt",
            "conversation_history", "user_message"
        ])
        
        # Process context order
        history_position = None
        user_message_position = None
        
        for i, component_name in enumerate(context_order):
            if component_name == "conversation_history":
                history_position = len(conv_messages)
            elif component_name == "user_message":
                user_message_position = len(conv_messages)
            else:
                # Add system component if it exists
                component_content = components.get(component_name)
                if component_content:
                    conv_messages.append({"role": "system", "content": component_content})
                    func.log.debug(f"Injected context: {component_name}")
        
        # Get conversation history
        history = self.get_ai_history(server_id, channel_id, ai_name, chat_id)
        
        # Token management
        context_size = llm_params.get("context_size", 4096)
        max_tokens = llm_params.get("max_tokens", 1000)
        
        # Validate and adjust max_tokens to prevent negative history space
        max_allowed_tokens = int(context_size * 0.5)
        if max_tokens > max_allowed_tokens:
            func.log.warning(
                f"max_tokens ({max_tokens}) exceeds 50% of context_size ({context_size}). "
                f"Adjusting to {max_allowed_tokens} to allow history inclusion."
            )
            max_tokens = max_allowed_tokens
        
        # Process user content
        user_content_processed = process_cbs(user_content, char_name, user_name, session)
        reserve = max_tokens + client.count_tokens(user_content_processed, model)
        
        # Calculate tokens used by system messages
        system_tokens = sum(
            client.count_tokens(msg["content"], model)
            for msg in conv_messages
        )
        
        available_for_history = context_size - system_tokens - reserve
        
        if available_for_history <= 0:
            func.log.warning(
                f"No space for history! System messages ({system_tokens} tokens) + "
                f"reserve ({reserve} tokens) exceed context size ({context_size} tokens). "
                f"Consider reducing max_tokens or using a model with larger context."
            )
        
        # Truncate ONLY conversation_history to fit available space
        truncated_history = client.truncate_history_by_tokens(
            history, "", context_size - system_tokens, model, reserve,
            client.count_tokens
        )
        
        # Check if we should add current message (avoid duplicates)
        # Always add if there are images, since images make it unique
        should_add_current = True
        if truncated_history and truncated_history[-1]["role"] == "user" and not images:
            last_history_content = truncated_history[-1]["content"]
            if user_content_processed in last_history_content or last_history_content in user_content_processed:
                should_add_current = False
                func.log.debug("Skipping duplicate user message (no images)")
        
        # Insert history and user message at their configured positions
        # If positions weren't specified, add them at the end
        if history_position is not None:
            # Insert history at specified position
            for msg in truncated_history:
                conv_messages.insert(history_position, msg)
                history_position += 1
        else:
            # Add at end if not specified
            conv_messages.extend(truncated_history)
        
        if should_add_current:
            # Create user message
            user_message = {"role": "user", "content": user_content_processed}
            
            # If images are provided AND vision is supported, create multimodal content
            if images and client.supports_vision():
                from utils.ai_config_manager import get_vision_config
                vision_config = get_vision_config(session, server_id)
                
                if vision_config.get('vision_enabled', False):
                    provider = session.get("provider", "openai")
                    
                    # Ollama uses a different format (separate 'images' field)
                    if provider == "ollama":
                        text_content, images_array = client.prepare_multimodal_content(
                            user_content_processed, images
                        )
                        user_message["content"] = text_content
                        user_message["images"] = images_array
                        func.log.info(f"Attached {len(images_array)} images to Ollama message")
                    else:
                        # Claude/OpenAI use multimodal content arrays
                        user_message["content"] = client.prepare_multimodal_content(
                            user_content_processed, images
                        )
                        func.log.info(f"Attached {len(images)} images to message")
                else:
                    func.log.debug("Images provided but vision_enabled=False, skipping")
            
            # Insert message at appropriate position
            if user_message_position is not None:
                # Insert at specified position (adjust for history if needed)
                if history_position is not None and user_message_position > history_position:
                    user_message_position += len(truncated_history)
                conv_messages.insert(user_message_position, user_message)
            else:
                # Add at end if not specified
                conv_messages.append(user_message)
        
        func.log.debug(f"Prepared {len(conv_messages)} messages for {ai_name} (context order: {len(context_order)} components)")
        
        return conv_messages
    
    def _get_user_name_for_cbs(self, config: Dict[str, Any], message_author) -> str:
        """Get the user name to use for {{user}} CBS replacement."""
        replacement_mode = config.get("user_syntax_replacement", "none")
        
        if replacement_mode == "none" or not message_author:
            return "{{user}}"
        
        if replacement_mode == "username":
            return message_author.name
        
        if replacement_mode == "display_name":
            return message_author.global_name or message_author.name
        
        if replacement_mode == "mention":
            return f"<@{message_author.id}>"
        
        if replacement_mode == "id":
            return str(message_author.id)
        
        return "{{user}}"
    
    def _handle_llm_error(self, error, session: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        """
        Process an LLM error based on configuration.
        
        Args:
            error: LLMError object with error information
            session: AI session with configuration
            
        Returns:
            tuple[display_message, history_message]:
                - display_message: Message to send to Discord (None = don't send)
                - history_message: Message to save in history (None = don't save)
        """
        config = session.get("config", {})
        error_mode = config.get("error_handling_mode", "friendly")
        save_in_history = config.get("save_errors_in_history", False)
        send_to_chat = config.get("send_errors_to_chat", True)
        
        # Determine the formatted error message based on mode
        if error_mode == "detailed":
            formatted_error = error.to_detailed_string()
        elif error_mode == "silent":
            formatted_error = None
        else:  # "friendly" or any other value
            formatted_error = error.to_friendly_string()
        
        # Determine what to send to chat
        display_message = None
        if send_to_chat and formatted_error and error_mode != "silent":
            display_message = formatted_error
        
        # Determine what to save in history
        history_message = None
        if save_in_history and formatted_error:
            history_message = formatted_error
        
        # Log the error
        if display_message is None and history_message is None:
            func.log.debug(f"Error suppressed (not sent or saved): {error.to_detailed_string()}")
        elif display_message is None:
            func.log.debug(f"Error saved to history but not sent to chat: {error.to_detailed_string()}")
        elif history_message is None:
            func.log.debug(f"Error sent to chat but not saved to history: {error.to_detailed_string()}")
        
        return (display_message, history_message)
    
    def _post_process_response(
        self,
        raw_response: str,
        user_content: str,
        server_id: str,
        channel_id: str,
        ai_name: str,
        session: Dict[str, Any],
        client,
        chat_id: str = "default"
    ) -> str:
        """Post-process the API response: check for errors, clean response, and apply display filters."""
        from AI.error_types import LLMError
        
        config = session.get("config", {})
        llm_params = client.get_llm_params(session, server_id)
        
        # Check if response is a structured error
        if LLMError.is_error_response(raw_response):
            error = LLMError.from_string(raw_response)
            if error:
                display_msg, history_msg = self._handle_llm_error(error, session)
                # Return special marker that pipeline can detect
                # Format: __ERROR_CONTROL__:display|history
                # Empty parts mean None (don't send/save)
                display_part = display_msg if display_msg else ""
                history_part = history_msg if history_msg else ""
                return f"__ERROR_CONTROL__:{display_part}|{history_part}"
        
        # Legacy error detection by patterns (for backward compatibility)
        is_error = False
        error_patterns = [
            "An error occurred while generating a response",
            "I'm sorry, but I couldn't generate a response",
            "I'm sorry, but I don't have a response at the moment",
            "I'm having trouble connecting",
            "I'm receiving too many requests"
        ]
        
        for pattern in error_patterns:
            response_start = raw_response.strip()[:100].lower()
            is_short = len(raw_response.strip()) < 150
            has_quotes = '"' in raw_response or "'" in raw_response
            
            if (pattern.lower() in response_start and is_short and not has_quotes):
                is_error = True
                func.log.warning(f"Detected error response for AI {ai_name} (legacy pattern)")
                break
        
        if is_error:
            # Create generic error and process it
            error = LLMError(
                error_type="UnknownError",
                error_message="Error detected by pattern matching",
                friendly_message=raw_response
            )
            display_msg, history_msg = self._handle_llm_error(error, session)
            return ("__ERROR__", display_msg, history_msg)
        
        cleaned_response = text_processor.clean_ai_response(
            raw_response,
            thinking_patterns=llm_params.get("thinking_tag_patterns", [
                r'<think>.*?</think>',
                r'<thinking>.*?</thinking>',
                r'<thought>.*?</thought>',
                r'<reasoning>.*?</reasoning>'
            ]),
            remove_emojis=config.get("remove_ai_emoji", False),
            custom_patterns=config.get("remove_ai_text_from", []),
            remove_reply_syntax=False
        )
        
        # Apply display cleaning based on settings
        display_response = raw_response
        if llm_params.get("hide_thinking_tags", True):
            display_response = text_processor.clean_ai_response(
                raw_response,
                thinking_patterns=llm_params.get("thinking_tag_patterns", [
                    r'<think>.*?</think>',
                    r'<thinking>.*?</thinking>',
                    r'<thought>.*?</thought>',
                    r'<reasoning>.*?</reasoning>'
                ]),
                remove_emojis=config.get("remove_ai_emoji", False),
                custom_patterns=config.get("remove_ai_text_from", []),
                remove_reply_syntax=False
            )
        else:
            if config.get("remove_ai_emoji", False):
                display_response = text_processor.remove_emoji(display_response)
            custom_patterns = config.get("remove_ai_text_from", [])
            display_response = text_processor.apply_custom_patterns(display_response, custom_patterns)
        
        return display_response
    
    async def new_chat_id(
        self,
        create_new: bool,
        session: Dict[str, Any],
        server_id: str,
        channel_id_str: str,
        desired_chat_id: str = "default"
    ) -> Tuple[Optional[str], Optional[Any]]:
        """Creates a new chat session if required.
        
        Args:
            create_new: If True, creates a new UUID chat. If False, uses desired_chat_id.
            session: AI session data
            server_id: Server ID
            channel_id_str: Channel ID
            desired_chat_id: Chat ID to use when create_new=False (default: "default")
            
        Returns:
            Tuple of (chat_id, greeting_obj)
        """
        provider = session.get("provider", "openai")
        
        if self.registry.is_registered(provider):
            existing_chat_id = session.get("chat_id")
            if existing_chat_id and not create_new:
                func.log.info(
                    "Using existing chat_id for channel %s: %s",
                    channel_id_str, existing_chat_id
                )
                return existing_chat_id, None
            
            try:
                # If create_new=True, generate UUID. Otherwise, use desired_chat_id
                if create_new:
                    new_id = str(uuid.uuid4())
                    func.log.info("New Chat ID created for channel %s: %s", channel_id_str, new_id)
                else:
                    new_id = desired_chat_id
                    func.log.info("Using desired chat_id for channel %s: %s", channel_id_str, new_id)
                
                session["chat_id"] = new_id
                session["setup_has_already"] = False
                
                # Update session data directly
                channel_data = func.get_session_data(server_id, channel_id_str)
                if channel_data:
                    ai_name = await self._get_ai_name_from_session(server_id, channel_id_str, session)
                    channel_data[ai_name] = session
                    await func.update_session_data(server_id, channel_id_str, channel_data)
                
                greeting_obj = None
                if session.get("config", {}).get("send_the_greeting_message"):
                    ai_name = await self._get_ai_name_from_session(server_id, channel_id_str, session)
                    # Pass the new_id to _generate_greeting so greeting is saved to correct chat
                    greeting_obj = await self._generate_greeting(session, server_id, channel_id_str, ai_name, new_id)
                
                return new_id, greeting_obj
                
            except Exception as e:
                func.log.error("Failed to create new chat session for channel %s: %s", channel_id_str, e)
                return None, None
        else:
            raise ValueError(f"Unsupported provider: {provider}")
    
    async def _get_ai_name_from_session(self, server_id: str, channel_id: str, target_session: Dict[str, Any]) -> str:
        """Helper to find AI name from session object."""
        channel_data = func.get_session_data(server_id, channel_id)
        if channel_data:
            for ai_name, session_data in channel_data.items():
                if session_data == target_session:
                    return ai_name
        return "AI"
    
    async def _generate_greeting(
        self,
        session: Dict[str, Any],
        server_id: str,
        channel_id: str,
        ai_name: str,
        chat_id: str = "default"
    ) -> Optional[Any]:
        """Gets greeting message from character card only."""
        config = session.get("config", {})
        
        try:
            card_data = (session.get("character_card") or {}).get("data", {})
            greeting_index = config.get("greeting_index", 0)
            
            greeting_text = None
            
            if card_data:
                if greeting_index == 0:
                    greeting_text = card_data.get("first_mes")
                else:
                    alt_greetings = card_data.get("alternate_greetings") or []
                    if 0 <= greeting_index - 1 < len(alt_greetings):
                        greeting_text = alt_greetings[greeting_index - 1]
                    else:
                        func.log.warning(f"Invalid greeting_index {greeting_index} for {ai_name}")
                        greeting_text = card_data.get("first_mes")
            
            if greeting_text and greeting_text.strip():
                char_name = card_data.get("nickname") or card_data.get("name", ai_name)
                user_name = self._get_user_name_for_cbs(config, None)
                greeting_text = process_cbs(greeting_text, char_name, user_name, session)
                
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create task but don't await (we're in sync context)
                        asyncio.create_task(self.append_to_history(server_id, channel_id, ai_name, "assistant", greeting_text, chat_id))
                    else:
                        # Run in new event loop
                        asyncio.run(self.append_to_history(server_id, channel_id, ai_name, "assistant", greeting_text, chat_id))
                except Exception as e:
                    func.log.error(f"Error saving greeting to history: {e}")
                
                class GreetingObj:
                    def get_primary_candidate(self):
                        class Candidate:
                            text = greeting_text
                        return Candidate()
                
                return GreetingObj()
            
            return None
                    
        except Exception as e:
            func.log.error(f"Error getting greeting: {e}")
            return None
    
    async def initialize_session_messages(
        self,
        session: Dict[str, Any],
        server_id: str,
        channel_id: str,
        chat_id: str = "default"
    ) -> Optional[str]:
        """Initializes and returns the greeting message for a session."""
        greeting_message = None
        
        if session.get("setup_has_already", False):
            func.log.debug("Session for channel %s already set up, skipping initialization", channel_id)
            return None
        
        create_new_chat = session.get("config", {}).get("new_chat_on_reset", False)
        ai_name = await self._get_ai_name_from_session(server_id, channel_id, session)
        
        # Pass desired_chat_id to ensure greeting is saved to the correct chat
        new_chat_id, greeting_obj = await self.new_chat_id(
            create_new_chat, session, server_id, channel_id, desired_chat_id=chat_id
        )
        
        if new_chat_id is None:
            func.log.critical("No valid chat ID available for channel %s", channel_id)
            return None
        
        try:
            if greeting_obj is not None and session.get("config", {}).get("send_the_greeting_message"):
                greeting_message = greeting_obj.get_primary_candidate().text
                func.log.debug("AI greeting message for channel %s: %s", channel_id, greeting_message)
                for pattern in session.get("config", {}).get("remove_ai_text_from", []):
                    greeting_message = re.sub(pattern, '', greeting_message, flags=re.MULTILINE).strip()
                    
        except Exception as e:
            func.log.critical("Error during chat session initialization for channel %s: %s", channel_id, e)
            return None
        
        return greeting_message
    
    async def generate_response(
        self,
        message,
        server_id: str,
        channel_id: str,
        ai_name: str,
        chat_id: str = "default",
        session: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generates a response from the appropriate AI provider with optional vision support."""
        
        if session is None:
            channel_data = func.get_session_data(server_id, channel_id)
            if not channel_data:
                func.log.error("No session data found for channel %s", channel_id)
                return "Error: No session data found."
            session = channel_data.get(ai_name) or next(iter(channel_data.values()))
        
        provider = session.get("provider", "openai")
        client = self._get_client(provider)
        
        # Process images from message attachments if vision is enabled
        processed_images = []
        
        
        if hasattr(message, 'attachments') and message.attachments:
            func.log.info(f"Found {len(message.attachments)} attachment(s) in message")
            
            from messaging.processor import MessageProcessor
            processor = MessageProcessor()
            
            # Create a PendingMessage-like object for processing
            class AttachmentMessage:
                def __init__(self, attachments):
                    self.attachments = attachments
            
            temp_message = AttachmentMessage(message.attachments)
            processed_images = await processor.process_message_images(temp_message, session, server_id)
            
            if processed_images:
                func.log.info(f"Processed {len(processed_images)} images for vision analysis")
            else:
                func.log.warning(f"No images processed from {len(message.attachments)} attachment(s) - vision may be disabled or no valid images found")

        
        # Get message content
        if hasattr(message, 'content'):
            formatted_data = message.content
        else:
            func.log.error(f"No message content available for AI {ai_name}")
            return "I'm sorry, but I couldn't process your message."
        
        
        try:
            default_model = "deepseek-chat" if provider == "deepseek" else "gpt-3.5-turbo"
            model = client.resolve_model(session, server_id, default_model)
            
            # Log images being passed to _prepare_messages
            if processed_images:
                func.log.debug(f"Passing {len(processed_images)} images to _prepare_messages()")
            
            prepared_messages = self._prepare_messages(
                formatted_data, server_id, channel_id, ai_name, session, model, client,
                message_author=message.author if hasattr(message, 'author') else None,
                chat_id=chat_id,
                images=processed_images if processed_images else None
            )
            
            # Log final message structure
            if processed_images:
                last_msg = prepared_messages[-1] if prepared_messages else None
                if last_msg and last_msg.get('role') == 'user':
                    content = last_msg.get('content')
                    if isinstance(content, list):
                        func.log.debug(f"Final user message has multimodal content with {len(content)} blocks")
                    elif isinstance(content, str):
                        func.log.warning(f"Final user message is TEXT ONLY (images not attached!)")
                    else:
                        func.log.error(f"Unexpected content type: {type(content)}")
            
            tools = None
            tool_context = None
            config = session.get("config", {})
            tool_config = config.get("tool_calling", {})
            
            if tool_config.get("enabled", False):
                from AI.tools import get_tool_definitions
                from AI.tool_executor import get_executor
                
                allowed_tools = tool_config.get("allowed_tools", ["all"])
                tools = get_tool_definitions(allowed_tools)
                
                executor = get_executor()
                guild = message.guild if hasattr(message, 'guild') else None
                bot_client = getattr(message, '_bot_client', None)
                tool_context = executor.prepare_context(
                    server_id, channel_id, ai_name, chat_id, guild, session,
                    bot_client=bot_client,
                    message=message
                )
            
            # Images are already included in prepared_messages via _prepare_messages()
            raw_response = await client.generate_response(
                prepared_messages, session, server_id,
                tools=tools,
                tool_context=tool_context
            )
            
            # Check if response is a structured error before post-processing
            from AI.error_types import LLMError
            if LLMError.is_error_response(raw_response):
                error = LLMError.from_string(raw_response)
                if error:
                    display_msg, history_msg = self._handle_llm_error(error, session)
                    # Return special marker: __ERROR_CONTROL__:display|history
                    display_part = display_msg if display_msg else ""
                    history_part = history_msg if history_msg else ""
                    return f"__ERROR_CONTROL__:{display_part}|{history_part}"
            
            final_response = self._post_process_response(
                raw_response, formatted_data, server_id, channel_id, ai_name, session, client, chat_id
            )
            
            # Check if post-processing returned an error marker
            if isinstance(final_response, str) and final_response.startswith("__ERROR_CONTROL__:"):
                return final_response
            
            return final_response
            
        except Exception as e:
            func.log.error(f"Error in generate_response: {e}")
            # Create structured error for unexpected exceptions
            from AI.error_types import LLMError
            error = LLMError(
                error_type=type(e).__name__,
                error_message=str(e),
                friendly_message="An error occurred while generating a response. Please try again later."
            )
            display_msg, history_msg = self._handle_llm_error(error, session)
            # Return special marker: __ERROR_CONTROL__:display|history
            display_part = display_msg if display_msg else ""
            history_part = history_msg if history_msg else ""
            return f"__ERROR_CONTROL__:{display_part}|{history_part}"


_service = ChatService()


def get_service() -> ChatService:
    """Get the global chat service instance."""
    return _service
