"""
Helper utilities for handling thumbnails in Discord embeds with intelligent CDN caching.

Provides functionality to:
- Extract avatar URLs from character cards
- Validate CDN URLs before reuse
- Upload images to CDN cache channel
- Cache thumbnail URLs to avoid repeated uploads
"""
import asyncio
import discord
import logging
import aiohttp
import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


def get_avatar_url_from_card(character_card_data: dict) -> Optional[str]:
    """
    Extract avatar URL from character card data.
    
    Checks in order:
    1. data.avatar (direct field)
    2. data.assets[type="icon"] (first found)
    3. extensions.chub.avatar (if exists)
    
    Args:
        character_card_data: Character card data dictionary
        
    Returns:
        Avatar URL or None if not found
    """
    try:
        data = character_card_data.get("data", {})
        
        # Option 1: Direct avatar field
        if "avatar" in data and isinstance(data["avatar"], str):
            if data["avatar"].startswith("http"):
                log.debug(f"Found avatar URL in data.avatar: {data['avatar'][:50]}...")
                return data["avatar"]
        
        # Option 2: Assets with type="icon"
        assets = data.get("assets", [])
        for asset in assets:
            if asset.get("type") == "icon":
                uri = asset.get("uri", "")
                if uri.startswith("http"):
                    log.debug(f"Found avatar URL in assets: {uri[:50]}...")
                    return uri
        
        # Option 3: Extensions (e.g., chub)
        extensions = data.get("extensions", {})
        chub = extensions.get("chub", {})
        if "avatar" in chub and isinstance(chub["avatar"], str):
            if chub["avatar"].startswith("http"):
                log.debug(f"Found avatar URL in extensions.chub: {chub['avatar'][:50]}...")
                return chub["avatar"]
        
        log.debug("No avatar URL found in character card")
        return None
        
    except Exception as e:
        log.error(f"Error extracting avatar URL from card: {e}")
        return None


async def validate_cdn_url(url: str, timeout: int = 5) -> bool:
    """
    Validate if a CDN URL is still accessible.
    
    Uses HTTP HEAD request to check without downloading the full image.
    
    Args:
        url: URL to validate
        timeout: Request timeout in seconds
        
    Returns:
        True if URL is accessible (HTTP 200), False otherwise
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                is_valid = response.status == 200
                if is_valid:
                    log.debug(f"URL validation successful: {url[:50]}...")
                else:
                    log.warning(f"URL validation failed (HTTP {response.status}): {url[:50]}...")
                return is_valid
    except asyncio.TimeoutError:
        log.warning(f"URL validation timeout: {url[:50]}...")
        return False
    except Exception as e:
        log.debug(f"URL validation error: {e}")
        return False


async def upload_to_cdn_cache(
    channel: discord.TextChannel,
    image_path: str,
    server_id: str
) -> Optional[str]:
    """
    Upload image to CDN cache channel (or temporary if not configured).
    
    Workflow:
    1. Check if cdn_cache_channel_id is configured
    2. If yes, upload to that channel and keep message
    3. If no, upload to provided channel and delete message (old behavior)
    4. Return Discord CDN URL
    
    Args:
        channel: Fallback Discord channel
        image_path: Path to image file
        server_id: Server ID for config lookup
        
    Returns:
        Discord CDN URL or None if upload fails
    """
    try:
        # Validate file exists
        path = Path(image_path)
        if not path.exists():
            log.warning(f"Image file not found: {image_path}")
            return None
        
        # Only support PNG files for character cards
        if path.suffix.lower() != '.png':
            log.debug(f"Skipping non-PNG file: {image_path}")
            return None
        
        # Load debug config to check for CDN cache channel
        import utils.func as func
        from utils.core.paths import DataPaths
        
        data_paths = DataPaths()
        debug_config_file = data_paths.get_debug_config_file(server_id)
        
        target_channel = channel
        keep_message = False
        
        if os.path.exists(debug_config_file):
            server_config = func.read_json(debug_config_file) or {}
            cdn_channel_id = server_config.get("cdn_cache_channel_id")
            
            if cdn_channel_id:
                # Try to get CDN cache channel
                cdn_channel = channel.guild.get_channel(int(cdn_channel_id))
                if cdn_channel:
                    target_channel = cdn_channel
                    keep_message = True
                    log.debug(f"Using CDN cache channel {cdn_channel_id} for upload")
                else:
                    log.warning(f"CDN cache channel {cdn_channel_id} not found, using fallback")
        
        # Upload image
        file = discord.File(image_path, filename="thumbnail.png")
        message = await target_channel.send(file=file)
        
        # Extract CDN URL
        if message.attachments:
            cdn_url = message.attachments[0].url
            
            # Delete message if not using cache channel
            if not keep_message:
                try:
                    await message.delete()
                    log.debug("Uploaded thumbnail (temporary, deleted message)")
                except discord.HTTPException:
                    pass  # Ignore if we can't delete
            else:
                log.debug(f"Uploaded thumbnail to CDN cache channel (kept message)")
            
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


async def update_thumbnail_cache(
    server_id: str,
    card_name: str,
    cdn_url: str
) -> bool:
    """
    Update thumbnail cache in character_cards.json.
    
    Adds/updates:
    - thumbnail_cdn_url: Discord CDN URL
    - thumbnail_last_validated: ISO 8601 timestamp
    
    Args:
        server_id: Server ID
        card_name: Character card name
        cdn_url: Discord CDN URL to cache
        
    Returns:
        True if update successful, False otherwise
    """
    try:
        import utils.func as func
        from utils.core.paths import DataPaths
        
        data_paths = DataPaths()
        cards_file = data_paths.get_character_cards_file(server_id)
        
        if not os.path.exists(cards_file):
            log.warning(f"Character cards file not found: {cards_file}")
            return False
        
        # Load cards
        cards = func.read_json(cards_file) or {}
        
        if card_name not in cards:
            log.warning(f"Card '{card_name}' not found in registry")
            return False
        
        # Update cache fields
        cards[card_name]["thumbnail_cdn_url"] = cdn_url
        cards[card_name]["thumbnail_last_validated"] = datetime.utcnow().isoformat() + "Z"
        
        # Save
        func.write_json(cards_file, cards)
        log.info(f"Updated thumbnail cache for card '{card_name}'")
        return True
        
    except Exception as e:
        log.error(f"Error updating thumbnail cache: {e}")
        return False


async def get_thumbnail_for_card_registry(
    channel: discord.TextChannel,
    card_name: str,
    server_id: str
) -> Optional[str]:
    """
    Get thumbnail URL for a card from registry with intelligent caching.
    
    This function is optimized for commands that work with card registry data
    (like /list_cards, /remove_card) rather than AI session data.
    
    Priority flow:
    1. Check if character card has avatar URL field
    2. If yes, validate avatar URL
    3. If avatar URL valid, use it
    4. If avatar URL invalid/missing, check cache in character_cards.json
    5. If cache exists, validate it (always, no time-based caching)
    6. If cache valid, use it
    7. If cache invalid/missing, upload and cache
    
    Args:
        channel: Discord channel (fallback for upload)
        card_name: Character card name in registry
        server_id: Server ID
        
    Returns:
        Discord CDN URL or avatar URL, or None if all methods fail
    """
    try:
        import utils.func as func
        from utils.core.paths import DataPaths
        
        data_paths = DataPaths()
        cards_file = data_paths.get_character_cards_file(server_id)
        
        if not os.path.exists(cards_file):
            log.debug(f"Character cards file not found: {cards_file}")
            return None
        
        # Load card from registry
        cards = func.read_json(cards_file) or {}
        card_info = cards.get(card_name)
        
        if not card_info:
            log.warning(f"Card '{card_name}' not found in registry")
            return None
        
        # Step 1: Check for avatar URL in character card data
        # Wrap card_info in expected format for get_avatar_url_from_card
        card_data = {"data": card_info}
        avatar_url = get_avatar_url_from_card(card_data)
        
        if avatar_url:
            log.debug("Found avatar URL in character card, validating...")
            if await validate_cdn_url(avatar_url):
                log.info("Using avatar URL from character card")
                return avatar_url
            else:
                log.warning("Avatar URL validation failed, falling back to cache")
        
        # Step 2: Check cache in character_cards.json
        cached_url = card_info.get("thumbnail_cdn_url")
        
        if cached_url:
            # Always validate cached URLs dynamically
            log.debug("Validating cached URL...")
            if await validate_cdn_url(cached_url):
                log.info("Using cached thumbnail URL")
                # Update validation timestamp for tracking
                await update_thumbnail_cache(server_id, card_name, cached_url)
                return cached_url
            else:
                log.warning("Cached URL validation failed, will re-upload")
        
        # Step 3: Upload and cache
        cache_path = card_info.get("cache_path")
        if not cache_path:
            log.debug("No cache path available for upload")
            return None
        
        log.info("Uploading thumbnail to CDN cache...")
        cdn_url = await upload_to_cdn_cache(channel, cache_path, server_id)
        
        if cdn_url:
            # Save to cache
            await update_thumbnail_cache(server_id, card_name, cdn_url)
        
        return cdn_url
        
    except Exception as e:
        log.error(f"Error getting thumbnail for card registry: {e}", exc_info=True)
        return None


async def get_thumbnail_url(
    channel: discord.TextChannel,
    session: dict,
    server_id: str
) -> Optional[str]:
    """
    Get thumbnail URL with intelligent caching and validation.
    
    Priority flow:
    1. Check if character card has avatar URL field
    2. If yes, validate avatar URL
    3. If avatar URL valid, use it
    4. If avatar URL invalid/missing, check cache in character_cards.json
    5. If cache exists, validate it
    6. If cache valid, use it
    7. If cache invalid/missing, upload and cache
    
    Args:
        channel: Discord channel (fallback for upload)
        session: AI session data containing character_card info
        server_id: Server ID
        
    Returns:
        Discord CDN URL or None if all methods fail
    """
    try:
        # Get character card data
        character_card = session.get("character_card")
        if not character_card:
            log.debug("No character card in session")
            return None
        
        card_name = session.get("character_card_name")
        cache_path = character_card.get("cache_path")
        
        # Step 1: Check for avatar URL in character card
        avatar_url = get_avatar_url_from_card(character_card)
        if avatar_url:
            log.debug("Found avatar URL in character card, validating...")
            if await validate_cdn_url(avatar_url):
                log.info("Using avatar URL from character card")
                return avatar_url
            else:
                log.warning("Avatar URL validation failed, falling back to cache")
        
        # Step 2: Check cache in character_cards.json
        if card_name:
            import utils.func as func
            from utils.core.paths import DataPaths
            
            data_paths = DataPaths()
            cards_file = data_paths.get_character_cards_file(server_id)
            
            if os.path.exists(cards_file):
                cards = func.read_json(cards_file) or {}
                card_info = cards.get(card_name, {})
                
                cached_url = card_info.get("thumbnail_cdn_url")
                
                if cached_url:
                    # Always validate cached URLs dynamically
                    log.debug("Validating cached URL...")
                    if await validate_cdn_url(cached_url):
                        log.info("Using cached thumbnail URL")
                        # Update validation timestamp for tracking
                        await update_thumbnail_cache(server_id, card_name, cached_url)
                        return cached_url
                    else:
                        log.warning("Cached URL validation failed, will re-upload")
        
        # Step 3: Upload and cache
        if not cache_path:
            log.debug("No cache path available for upload")
            return None
        
        log.info("Uploading thumbnail to CDN cache...")
        cdn_url = await upload_to_cdn_cache(channel, cache_path, server_id)
        
        if cdn_url and card_name:
            # Save to cache
            await update_thumbnail_cache(server_id, card_name, cdn_url)
        
        return cdn_url
        
    except Exception as e:
        log.error(f"Error getting thumbnail URL: {e}", exc_info=True)
        return None
