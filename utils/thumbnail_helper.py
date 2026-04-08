"""
Helper utilities for handling thumbnails in Discord embeds.
Provides functionality to upload images and get Discord CDN URLs.
"""
import discord
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


async def upload_thumbnail_to_discord(
    channel: discord.TextChannel,
    image_path: str,
    server_id: str = None
) -> Optional[str]:
    """
    Upload an image to Discord and return its CDN URL.
    
    This is a workaround for using thumbnails with pagination.
    Discord doesn't allow editing attachments, so we upload the image
    first to get a permanent CDN URL that can be used in all embeds.
    
    Args:
        channel: Discord channel (fallback if no debug channel)
        image_path: Path to the image file
        server_id: Server ID to find debug channel (optional)
    
    Returns:
        Discord CDN URL of the uploaded image, or None if upload fails
    
    Example:
        >>> cdn_url = await upload_thumbnail_to_discord(channel, "character.png", server_id="123")
        >>> embed.set_thumbnail(url=cdn_url)
    """
    try:
        # Validate file exists
        path = Path(image_path)
        if not path.exists():
            log.warning(f"Thumbnail file not found: {image_path}")
            return None
        
        # Only support PNG files for character cards
        if path.suffix.lower() != '.png':
            log.debug(f"Skipping non-PNG thumbnail: {image_path}")
            return None
        
        # Determine target channel
        target_channel = channel  # Default fallback
        is_debug_channel = False

        if server_id:
            # Try to get debug channel for this server
            try:
                import utils.func as func
                from utils.data_paths import DataPaths
                import os

                data_paths = DataPaths()
                debug_config_file = data_paths.get_debug_config_file(server_id)

                if os.path.exists(debug_config_file):
                    server_config = func.read_json(debug_config_file) or {}

                    if server_config.get("enabled", False) and server_config.get("debug_channel_id"):
                        debug_channel_id = server_config["debug_channel_id"]
                        debug_channel = channel.guild.get_channel(int(debug_channel_id))

                        if debug_channel:
                            target_channel = debug_channel
                            is_debug_channel = True
                            log.debug(f"Using debug channel {debug_channel_id} for thumbnail upload")
            except Exception as e:
                log.debug(f"Could not get debug channel: {e}")
                pass  # Use fallback channel

        # Upload image to Discord
        file = discord.File(image_path, filename="thumbnail.png")

        # Send to target channel
        temp_message = await target_channel.send(file=file)

        # Extract CDN URL from the uploaded attachment
        if temp_message.attachments:
            cdn_url = temp_message.attachments[0].url

            # IMPORTANT: Only delete if NOT in debug channel
            if is_debug_channel:
                # Keep the message in debug channel - DO NOT DELETE
                log.debug(f"Uploaded thumbnail to debug channel (kept message with attachment)")
            else:
                # Delete the message in normal channels
                try:
                    await temp_message.delete()
                    log.debug("Uploaded thumbnail to Discord CDN (deleted temp message)")
                except discord.HTTPException:
                    pass  # Ignore if we can't delete

            return cdn_url
        else:
            log.warning("No attachments found in uploaded message")
            return None
            
    except discord.HTTPException as e:
        log.error(f"Failed to upload thumbnail to Discord: {e}")
        return None
    except Exception as e:
        log.error(f"Unexpected error uploading thumbnail: {e}", exc_info=True)
        return None


async def get_character_card_thumbnail_url(
    channel: discord.TextChannel,
    session: dict,
    server_id: str = None
) -> Optional[str]:
    """
    Get Discord CDN URL for a character card thumbnail.
    
    Args:
        channel: Discord channel for temporary upload
        session: AI session data containing character_card info
        server_id: Server ID to find debug channel (optional)
    
    Returns:
        Discord CDN URL or None if no thumbnail available
    
    Example:
        >>> thumbnail_url = await get_character_card_thumbnail_url(channel, session, server_id="123")
        >>> if thumbnail_url:
        ...     embed.set_thumbnail(url=thumbnail_url)
    """
    cache_path = session.get("character_card", {}).get("cache_path")
    
    if not cache_path:
        return None
    
    return await upload_thumbnail_to_discord(channel, cache_path, server_id=server_id)
