"""
Poll Tools - Discord Poll Query and Voting Functions

This module provides tools for querying Discord poll information and voting.
The LLM can use these tools to check poll results, status, details, and vote in polls.
"""

import logging
from typing import Dict, Any, Optional, List
import discord

log = logging.getLogger(__name__)


async def get_poll_info(
    message_id: str,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Query poll results directly from Discord API.
    
    This tool allows the LLM to check poll results, vote counts,
    and poll status without needing local storage.
    
    Args:
        message_id: Discord message ID (short ID #N or full Discord ID)
        context: Context containing channel, server_id, ai_name for ID conversion
        
    Returns:
        Dict with poll information:
        {
            "question": "Poll question",
            "options": [
                {"text": "Option 1", "votes": 5},
                {"text": "Option 2", "votes": 3}
            ],
            "total_votes": 8,
            "is_finalized": False,
            "allow_multiselect": False,
            "expires_at": "2026-03-25T13:00:00Z"
        }
        
        Or error dict:
        {
            "error": "Error message"
        }
    """
    try:
        # Get context data
        bot_client = context.get("bot_client")
        server_id = context.get("server_id")
        channel_id = context.get("channel_id")
        ai_name = context.get("ai_name")
        
        if not bot_client:
            return {"error": "Bot client not available in context"}
        
        # Convert short ID to Discord ID if needed
        discord_id = message_id
        
        if len(message_id) < 17:  # Short ID (Discord IDs are 17-20 digits)
            if not server_id or not ai_name:
                return {
                    "error": f"Short ID {message_id} provided but missing server_id or ai_name for conversion"
                }
            
            # Convert short ID to Discord ID
            from messaging.short_id_manager import get_short_id_manager_sync
            
            manager = get_short_id_manager_sync()
            discord_id = await manager.get_discord_id(
                server_id, channel_id, ai_name, int(message_id)
            )
            
            if not discord_id:
                return {
                    "error": f"Short ID #{message_id} not found in mapping. The message may be too old or from a different channel."
                }
            
            log.debug(f"Converted short ID #{message_id} to Discord ID {discord_id}")
        
        # Get the channel
        try:
            channel = bot_client.get_channel(int(channel_id))
            if not channel:
                # Try fetching if not in cache
                channel = await bot_client.fetch_channel(int(channel_id))
            
            if not channel:
                return {"error": f"Channel {channel_id} not found"}
        
        except Exception as e:
            log.error(f"Error getting channel: {e}")
            return {"error": f"Failed to access channel: {str(e)}"}
        
        # Fetch the message
        try:
            message = await channel.fetch_message(int(discord_id))
        except discord.NotFound:
            return {"error": f"Message {discord_id} not found. It may have been deleted."}
        except discord.Forbidden:
            return {"error": "Bot doesn't have permission to read message history"}
        except Exception as e:
            log.error(f"Error fetching message: {e}")
            return {"error": f"Failed to fetch message: {str(e)}"}
        
        # Check if message has a poll
        if not hasattr(message, 'poll') or message.poll is None:
            return {"error": "This message doesn't contain a poll"}
        
        poll = message.poll
        
        # Extract poll information
        try:
            # Get poll question
            question = poll.question.text if hasattr(poll.question, 'text') else str(poll.question)
            
            # Get poll options with vote counts and voters
            options = []
            total_votes = 0
            
            for answer in poll.answers:
                # Get answer text
                answer_text = answer.text if hasattr(answer, 'text') else str(answer)
                
                # Get vote count
                vote_count = answer.vote_count if hasattr(answer, 'vote_count') else 0
                
                option_data = {
                    "text": answer_text,
                    "votes": vote_count
                }
                
                # Fetch voters for this answer
                try:
                    voters = []
                    voter_limit = 50  # Limit to prevent huge responses
                    
                    # answer.voters() returns an async iterator
                    async for user in answer.voters():
                        if len(voters) >= voter_limit:
                            option_data["voters_truncated"] = True
                            option_data["voters_shown"] = voter_limit
                            break
                        
                        voters.append({
                            "id": str(user.id),
                            "name": user.name,
                            "display_name": user.display_name if hasattr(user, 'display_name') else user.name
                        })
                    
                    option_data["voters"] = voters
                    
                except Exception as e:
                    log.warning(f"Failed to fetch voters for option '{answer_text}': {e}")
                    option_data["voters"] = []
                    option_data["voters_error"] = "Failed to fetch voters"
                
                options.append(option_data)
                total_votes += vote_count
            
            # Get poll status
            is_finalized = poll.is_finalized() if hasattr(poll, 'is_finalized') else False
            
            # Get multiselect setting (discord.py 2.7+ uses 'multiple' attribute)
            allow_multiselect = poll.multiple if hasattr(poll, 'multiple') else False
            
            # Get expiry time
            expires_at = None
            if hasattr(poll, 'expiry'):
                if poll.expiry:
                    expires_at = poll.expiry.isoformat()
            
            # Build result
            result = {
                "question": question,
                "options": options,
                "total_votes": total_votes,
                "is_finalized": is_finalized,
                "allow_multiselect": allow_multiselect,
                "expires_at": expires_at
            }
            
            # Add winning option(s) if there are votes
            if total_votes > 0:
                max_votes = max(opt["votes"] for opt in options)
                winners = [opt["text"] for opt in options if opt["votes"] == max_votes]
                
                if len(winners) == 1:
                    result["winning_option"] = winners[0]
                    result["winning_votes"] = max_votes
                else:
                    result["tied_options"] = winners
                    result["tied_votes"] = max_votes
            
            log.info(f"Retrieved poll info: '{question}' with {total_votes} total votes")
            
            return result
        
        except Exception as e:
            log.error(f"Error extracting poll data: {e}", exc_info=True)
            return {"error": f"Failed to extract poll data: {str(e)}"}
    
    except Exception as e:
        log.error(f"Error in get_poll_info: {e}", exc_info=True)
        return {"error": f"Unexpected error: {str(e)}"}
