"""
Vision Utils - Shared utilities for processing images for vision

This module provides utilities for downloading and processing images
(avatars, emojis, stickers) so the LLM can visually analyze them.
"""

import logging
import base64
from typing import Dict, Any, Optional
from utils.media_processor import ImageProcessor
from utils.ai_config_manager import get_vision_config

log = logging.getLogger(__name__)


async def fetch_image_for_vision(
    url: str,
    context: Dict[str, Any],
    image_type: str = "image"
) -> Optional[Dict[str, Any]]:
    """
    Download and process an image for LLM vision.
    
    This function:
    1. Checks if vision is enabled in config
    2. Validates the URL (security check - must be Discord CDN)
    3. Downloads the image with size limits
    4. Converts to base64
    5. Returns dict with _vision_image flag for tool_executor
    
    Args:
        url: Image URL (must be from Discord CDN)
        context: Context with session and server_id for vision config
        image_type: Type description (e.g., "avatar", "emoji", "sticker")
        
    Returns:
        Dict with base64, format, _vision_image flag, or None if failed/disabled
    """
    # Check if vision is enabled
    session = context.get("session", {})
    server_id = context.get("server_id")
    
    if not session or not server_id:
        log.debug("Vision fetch skipped: missing session or server_id")
        return None
    
    vision_config = get_vision_config(session, server_id)
    
    if not vision_config.get('vision_enabled', False):
        log.debug("Vision fetch skipped: vision_enabled=False")
        return None
    
    # Get max image size from config
    max_size_mb = vision_config.get('max_image_size', 20)
    detail = vision_config.get('vision_detail', 'auto')
    
    try:
        # Initialize processor
        processor = ImageProcessor()
        
        # Validate URL (security check)
        if not processor.validate_url(url):
            log.warning(f"Vision fetch failed: URL not from Discord CDN: {url}")
            return None
        
        # Download image
        image_data = await processor.download_image(url, max_size_mb)
        
        if not image_data:
            log.warning(f"Vision fetch failed: Could not download {image_type} from {url}")
            return None
        
        # Convert to base64
        base64_data = base64.b64encode(image_data).decode('utf-8')
        
        # Determine format from URL
        image_format = "image/png"
        if url.endswith('.jpg') or url.endswith('.jpeg'):
            image_format = "image/jpeg"
        elif url.endswith('.gif'):
            image_format = "image/gif"
        elif url.endswith('.webp'):
            image_format = "image/webp"
        
        log.info(f"Successfully fetched {image_type} for vision: {len(image_data)} bytes")
        
        return {
            "base64": base64_data,
            "format": image_format,
            "detail": detail,
            "_vision_image": True,  # Flag for tool_executor to extract
            "url": url,
            "type": image_type
        }
    
    except Exception as e:
        log.error(f"Error fetching {image_type} for vision: {e}", exc_info=True)
        return None
