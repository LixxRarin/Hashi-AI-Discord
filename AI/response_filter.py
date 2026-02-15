"""
Response Filter - Intelligent conversation analysis using LLM with Tool Calling.

This module provides a filter that uses an LLM to decide whether an AI should
respond to cached messages based on conversation context and flow.
"""

import asyncio
import json
from typing import Dict, Any, Tuple
import utils.func as func
from AI.provider_registry import get_registry


class ResponseFilter:
    """Uses LLM with Structured Outputs to decide if AI should respond."""
    
    def __init__(self):
        self.registry = get_registry()
        # Sleep mode state tracking: {(server_id, channel_id, ai_name): {consecutive_refusals: int, in_sleep_mode: bool, last_activity: float}}
        self.sleep_state = {}
        # Cleanup tracking to prevent memory leaks
        self._last_cleanup = 0.0  # Timestamp of last cleanup
        self._cleanup_interval = 3600  # Check every 1 hour
        self._max_inactive_time = 86400  # Remove states inactive for 24 hours
        # Load persisted sleep states from ResponseManager
        self._load_sleep_states()
    
    async def _cleanup_old_states(self):
        """
        Remove sleep states that have been inactive for too long.
        
        This prevents memory leaks from accumulating states for inactive channels.
        Called periodically during should_respond() checks.
        """
        import time
        
        now = time.time()
        
        # Only cleanup if interval has passed
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        # Find states to remove
        to_remove = []
        for key, state in self.sleep_state.items():
            last_activity = state.get("last_activity", 0)
            if now - last_activity > self._max_inactive_time:
                to_remove.append(key)
        
        # Remove old states
        for key in to_remove:
            del self.sleep_state[key]
        
        self._last_cleanup = now
        
        if to_remove:
            func.log.info(
                f"[SLEEP MODE CLEANUP] Removed {len(to_remove)} inactive sleep states "
                f"(inactive > {self._max_inactive_time/3600:.1f} hours)"
            )
    
    def _load_sleep_states(self):
        """Load sleep states from ResponseManager on initialization."""
        try:
            from messaging.response import get_response_manager
            response_manager = get_response_manager()
            
            for server_id, server_data in response_manager._responses.items():
                for channel_id, channel_data in server_data.items():
                    for ai_name, state in channel_data.items():
                        if state.sleep_state:
                            state_key = (server_id, channel_id, ai_name)
                            self.sleep_state[state_key] = state.sleep_state.copy()
            
            if self.sleep_state:
                func.log.info(f"Loaded {len(self.sleep_state)} sleep states from persistence")
        except Exception as e:
            func.log.debug(f"Could not load sleep states: {e}")
    
    def _save_sleep_state(self, server_id: str, channel_id: str, ai_name: str):
        """Save sleep state to ResponseManager for persistence."""
        try:
            from messaging.response import get_response_manager
            response_manager = get_response_manager()
            
            state_key = (server_id, channel_id, ai_name)
            if state_key in self.sleep_state:
                # Get or create ResponseState
                resp_state = response_manager._ensure_path(server_id, channel_id, ai_name)
                resp_state.sleep_state = self.sleep_state[state_key].copy()
        except Exception as e:
            func.log.debug(f"Could not save sleep state: {e}")
    
    # JSON Schema for Structured Outputs
    ANALYSIS_SCHEMA = {
        "type": "object",
        "properties": {
            "should_respond": {
                "type": "boolean",
                "description": "Whether AI should respond"
            },
            "confidence": {
                "type": "number",
                "description": "Confidence (0.0-1.0)",
                "minimum": 0.0,
                "maximum": 1.0
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation"
            },
            "conversation_type": {
                "type": "string",
                "enum": ["direct_question", "continuation", "side_conversation", "unclear"],
                "description": "Conversation type"
            }
        },
        "required": ["should_respond", "confidence", "reasoning", "conversation_type"],
        "additionalProperties": False
    }
    
    async def should_respond(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        session: Dict[str, Any],
        cached_messages: str,
        conversation_history: list,
        is_mentioned: bool = False,
        is_reply_to_bot: bool = False
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Analyze if AI should respond to cached messages.
        
        Implements sleep mode: After N consecutive refusals, the AI enters sleep mode
        and only wakes up when mentioned or replied to.
        
        Args:
            server_id: Discord server ID
            channel_id: Discord channel ID
            ai_name: Name of the AI
            session: AI session data
            cached_messages: Formatted cached messages
            conversation_history: Recent conversation history
            is_mentioned: Whether the bot was mentioned in the message
            is_reply_to_bot: Whether the message is a reply to the bot
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (should_respond, analysis_details)
        """
        config = session.get("config", {})
        
        # If filter is disabled, always respond
        if not config.get("use_response_filter", False):
            return True, {"reason": "Filter disabled", "confidence": 1.0}
        
        # Periodic cleanup of old states (prevents memory leaks)
        await self._cleanup_old_states()
        
        # Get sleep mode configuration
        sleep_mode_enabled = config.get("sleep_mode_enabled", False)
        sleep_mode_threshold = config.get("sleep_mode_threshold", 5)
        
        # Create state key for this AI
        state_key = (server_id, channel_id, ai_name)
        
        # Initialize state if not exists
        import time
        if state_key not in self.sleep_state:
            self.sleep_state[state_key] = {
                "consecutive_refusals": 0,
                "in_sleep_mode": False,
                "last_activity": time.time()
            }
        
        state = self.sleep_state[state_key]
        
        # Update last activity timestamp
        state["last_activity"] = time.time()
        
        # Check if in sleep mode
        if sleep_mode_enabled and state["in_sleep_mode"]:
            # Wake up if mentioned or replied to
            if is_mentioned or is_reply_to_bot:
                func.log.info(
                    f"[SLEEP MODE] AI {ai_name} waking up - "
                    f"{'mentioned' if is_mentioned else 'replied to'}"
                )
                state["in_sleep_mode"] = False
                state["consecutive_refusals"] = 0
                self._save_sleep_state(server_id, channel_id, ai_name)
                
                # Don't pass through normal filter logic which might refuse again
                return True, {
                    "should_respond": True,
                    "confidence": 1.0,
                    "reasoning": f"AI woke up from sleep mode ({'mentioned' if is_mentioned else 'replied to'})",
                    "conversation_type": "direct_question"
                }
            else:
                # Stay asleep
                func.log.debug(
                    f"[SLEEP MODE] AI {ai_name} staying asleep - not mentioned or replied to"
                )
                return False, {
                    "should_respond": False,
                    "confidence": 1.0,
                    "reasoning": "AI is in sleep mode (not mentioned or replied to)",
                    "conversation_type": "sleep_mode"
                }
        
        filter_conn_name = config.get("response_filter_api_connection")
        if not filter_conn_name:
            func.log.warning(f"Response filter enabled but no API connection configured for {ai_name}")
            return self._fallback(config)
        
        filter_conn = func.get_api_connection(server_id, filter_conn_name)
        if not filter_conn:
            func.log.error(f"Filter connection '{filter_conn_name}' not found")
            return self._fallback(config)
        
        # Verify provider supports Tool Calling
        provider = filter_conn.get("provider", "")
        if provider not in ["openai", "deepseek"]:
            func.log.error(
                f"Provider '{provider}' doesn't support Tool Calling. "
                f"Response filter requires OpenAI or DeepSeek."
            )
            return self._fallback(config)
        
        prompt = self._build_prompt(ai_name, cached_messages, conversation_history)
        
        timeout = config.get("response_filter_timeout", 5.0)
        try:
            async with asyncio.timeout(timeout):
                analysis = await self._call_filter_llm(filter_conn, prompt, server_id)
                
                func.log.debug(
                    f"Response Filter [{ai_name}]: "
                    f"respond={analysis['should_respond']}, "
                    f"confidence={analysis['confidence']:.2f}, "
                    f"type={analysis['conversation_type']}"
                )
                
                # Sleep mode logic: Track refusals and enter sleep mode if threshold reached
                if sleep_mode_enabled:
                    if analysis["should_respond"]:
                        # Reset counter on successful response
                        if state["consecutive_refusals"] > 0:
                            func.log.debug(
                                f"[SLEEP MODE] AI {ai_name} responding - resetting refusal counter "
                                f"(was {state['consecutive_refusals']})"
                            )
                        state["consecutive_refusals"] = 0
                        state["in_sleep_mode"] = False
                        self._save_sleep_state(server_id, channel_id, ai_name)
                    else:
                        # Increment refusal counter
                        state["consecutive_refusals"] += 1
                        func.log.debug(
                            f"[SLEEP MODE] AI {ai_name} refused to respond - "
                            f"consecutive refusals: {state['consecutive_refusals']}/{sleep_mode_threshold}"
                        )
                        
                        # Check if threshold reached
                        if state["consecutive_refusals"] >= sleep_mode_threshold:
                            state["in_sleep_mode"] = True
                            self._save_sleep_state(server_id, channel_id, ai_name)
                            func.log.warning(
                                f"[SLEEP MODE] AI {ai_name} entering sleep mode after "
                                f"{state['consecutive_refusals']} consecutive refusals. "
                                f"Will only wake up when mentioned or replied to."
                            )
                
                return analysis["should_respond"], analysis
                
        except asyncio.TimeoutError:
            func.log.warning(f"Response filter timeout for {ai_name}")
            return self._fallback(config)
        except Exception as e:
            func.log.error(f"Response filter error for {ai_name}: {e}")
            return self._fallback(config)
    
    def _build_prompt(self, ai_name: str, cached_messages: str, history: list) -> str:
        """
        Build analysis prompt for the filter LLM.
        
        Args:
            ai_name: Name of the AI
            cached_messages: New messages not yet responded to
            history: Recent conversation history
            
        Returns:
            str: Formatted prompt for analysis
        """
        history_text = ""
        if history:
            for msg in history[-10:]:
                role = msg.get("role", "").upper()
                content = msg.get("content", "")[:200]
                history_text += f"{role}: {content}\n"
        
        return f"""You are analyzing a Discord conversation to decide if the AI should respond.

AI Name: {ai_name}

Recent Conversation History:
{history_text if history_text else "(No recent history)"}

New Messages (not yet responded to):
{cached_messages}

Analyze and decide:
1. Are users talking TO the AI or AMONG themselves?
2. Is the AI being directly addressed or mentioned?
3. Is this a continuation of an ongoing conversation with the AI?
4. Would a response be appropriate and expected?

Consider:
- Direct mentions (@{ai_name}) or questions to the AI
- Conversation flow and context
- Whether users are having a side conversation
- If the AI was recently active in this conversation

Provide your decision in the required JSON format."""
    
    async def _call_filter_llm(
        self,
        connection: Dict[str, Any],
        prompt: str,
        server_id: str
    ) -> Dict[str, Any]:
        """
        Call LLM with Structured Outputs to analyze conversation.
        
        Tries json_schema first, falls back to json_object if not supported.
        
        Args:
            connection: API connection configuration
            prompt: Analysis prompt
            server_id: Discord server ID
            
        Returns:
            Dict[str, Any]: Analysis result following the schema
            
        Raises:
            ValueError: If provider not supported or response invalid
        """
        from openai import AsyncOpenAI
        
        provider = connection.get("provider", "openai")
        if provider not in ["openai", "deepseek"]:
            raise ValueError(f"Provider {provider} not supported for response filter")
        
        # Get API credentials from connection
        api_key = connection.get("api_key")
        base_url = connection.get("base_url")
        model = connection.get("model")
        
        if not api_key or not model:
            raise ValueError("Connection missing required fields (api_key, model)")
        
        # Create client directly with connection data
        client_kwargs = {"api_key": api_key, "timeout": 60.0}
        if base_url:
            client_kwargs["base_url"] = base_url
        
        client = AsyncOpenAI(**client_kwargs)
        
        # Enhanced prompt with JSON format instructions
        system_prompt = """You are a conversation analyzer. Analyze the conversation and provide a structured decision.

You MUST respond with a valid JSON object with these exact fields:
- should_respond (boolean): Whether the AI should respond
- confidence (number 0.0-1.0): Your confidence in this decision
- reasoning (string): Brief explanation of your decision
- conversation_type (string): One of: "direct_question", "continuation", "side_conversation", "unclear"

Example response:
{"should_respond": true, "confidence": 0.9, "reasoning": "User directly asked the AI a question", "conversation_type": "direct_question"}"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        try:
            # Build API parameters
            # Use max_tokens from connection config, with reasonable default for reasoning models
            max_tokens = connection.get("max_tokens", 3000)
            api_params = {
                "model": model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": max_tokens,
            }
            
            # Try to disable reasoning for faster, cheaper responses
            # Some models require reasoning and will reject this parameter
            try_disable_reasoning = True
            
            # Try with json_schema first (strict structured outputs)
            try:
                func.log.debug(f"Trying json_schema mode for model: {model}")
                
                # Try to disable reasoning if this is the first attempt
                if try_disable_reasoning:
                    api_params["extra_body"] = {
                        "reasoning": {
                            "effort": "none"
                        }
                    }
                    func.log.debug("Attempting to disable reasoning for filter call")
                
                api_params["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "conversation_analysis",
                        "strict": True,
                        "schema": self.ANALYSIS_SCHEMA
                    }
                }
                response = await client.chat.completions.create(**api_params)
                func.log.debug("json_schema mode succeeded")
                
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check if error is about reasoning being mandatory
                if "reasoning is mandatory" in error_msg or "cannot be disabled" in error_msg:
                    func.log.warning(f"Model requires reasoning, retrying without disabling it")
                    # Remove reasoning control and retry
                    if "extra_body" in api_params:
                        del api_params["extra_body"]
                    try:
                        response = await client.chat.completions.create(**api_params)
                        func.log.debug("json_schema mode succeeded (with mandatory reasoning)")
                    except Exception as e2:
                        # If still failing, try json_object mode
                        func.log.warning(f"json_schema mode failed ({e2}), falling back to json_object mode")
                        api_params["response_format"] = {"type": "json_object"}
                        response = await client.chat.completions.create(**api_params)
                        func.log.debug("json_object mode succeeded")
                else:
                    # Other error, try json_object mode
                    func.log.warning(f"json_schema mode failed ({e}), falling back to json_object mode")
                    if "extra_body" in api_params:
                        del api_params["extra_body"]
                    api_params["response_format"] = {"type": "json_object"}
                    response = await client.chat.completions.create(**api_params)
                    func.log.debug("json_object mode succeeded")
            
            # Parse JSON response
            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            
            # Check if content is empty (common with reasoning models that hit token limit)
            if not content or not content.strip():
                # Check if there's reasoning content that consumed all tokens
                reasoning = getattr(response.choices[0].message, 'reasoning', None)
                usage = getattr(response, 'usage', None)
                reasoning_tokens = getattr(usage, 'reasoning_tokens', 0) if usage else 0
                
                if reasoning_tokens > 0 or finish_reason == 'length':
                    func.log.error(
                        f"Model hit token limit (finish_reason={finish_reason}, "
                        f"reasoning_tokens={reasoning_tokens}). "
                        f"The reasoning model consumed all tokens thinking and produced no JSON output. "
                        f"SOLUTION: Use a non-reasoning model (like gpt-4o-mini, gpt-3.5-turbo, or deepseek-chat) "
                        f"for the response filter, or significantly increase max_tokens."
                    )
                else:
                    func.log.error(f"Empty content from model. Full response: {response}")
                raise ValueError("Empty response from filter LLM - model hit token limit")
            
            func.log.debug(f"Raw response content: {content[:200]}")
            
            result = json.loads(content)
            
            # Validate required fields
            required_fields = ["should_respond", "confidence", "reasoning", "conversation_type"]
            missing_fields = [f for f in required_fields if f not in result]
            if missing_fields:
                func.log.error(f"Missing required fields: {missing_fields}. Response: {result}")
                raise ValueError(f"Response missing required fields: {missing_fields}")
            
            func.log.debug(f"Filter analysis result: {result}")
            
            return result
            
        finally:
            await client.close()
    
    def _fallback(self, config: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Fallback behavior when filter fails.
        
        Args:
            config: AI configuration
            
        Returns:
            Tuple[bool, Dict[str, Any]]: (should_respond, fallback_info)
        """
        fallback = config.get("response_filter_fallback", "respond")
        should_respond = (fallback == "respond")
        
        return should_respond, {
            "should_respond": should_respond,
            "confidence": 0.5,
            "reasoning": f"Fallback: {fallback}",
            "conversation_type": "unclear"
        }


# Singleton instance
_response_filter = ResponseFilter()


def get_response_filter() -> ResponseFilter:
    """
    Get the singleton ResponseFilter instance.
    
    Returns:
        ResponseFilter: The global response filter instance
    """
    return _response_filter
