"""
Media Processor Module

Handles image processing for vision-capable LLM models.
"""

import asyncio
import base64
import logging
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse

import aiohttp


logger = logging.getLogger(__name__)


class ImageProcessor:
    """Processes images for vision-capable LLM models."""
    
    SUPPORTED_FORMATS = [
        "image/jpeg",
        "image/jpg", 
        "image/png",
        "image/gif",
        "image/webp"
    ]
    
    DISCORD_CDN_DOMAINS = [
        "cdn.discordapp.com",
        "media.discordapp.net"
    ]
    
    def __init__(self):
        self.download_timeout = 10  # seconds
    
    def validate_url(self, url: str) -> bool:
        """
        Validate that URL is from Discord CDN for security.
        
        Args:
            url: Image URL to validate
            
        Returns:
            True if URL is valid and from Discord CDN
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc in self.DISCORD_CDN_DOMAINS
        except Exception as e:
            logger.warning(f"Failed to parse image URL: {e}")
            return False
    
    def validate_image(self, content_type: str, size: int, max_size_mb: int) -> Tuple[bool, Optional[str]]:
        """
        Validate image format and size.
        
        Args:
            content_type: MIME type of the image
            size: Size in bytes
            max_size_mb: Maximum allowed size in MB
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check format
        if content_type.lower() not in self.SUPPORTED_FORMATS:
            return False, f"Unsupported image format: {content_type}"
        
        # Check size
        max_size_bytes = max_size_mb * 1024 * 1024
        if size > max_size_bytes:
            return False, f"Image too large: {size / (1024*1024):.1f}MB (max: {max_size_mb}MB)"
        
        return True, None
    
    async def download_image(self, url: str, max_size_mb: int) -> Optional[bytes]:
        """
        Download image from URL with timeout and size validation.
        
        Args:
            url: Image URL
            max_size_mb: Maximum allowed size in MB
            
        Returns:
            Image data as bytes, or None if download failed
        """
        try:
            timeout = aiohttp.ClientTimeout(total=self.download_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to download image: HTTP {response.status}")
                        return None
                    
                    # Check content type
                    content_type = response.headers.get('Content-Type', '').lower()
                    content_length = int(response.headers.get('Content-Length', 0))
                    
                    # Validate before downloading
                    is_valid, error = self.validate_image(content_type, content_length, max_size_mb)
                    if not is_valid:
                        logger.warning(f"Image validation failed: {error}")
                        return None
                    
                    # Download
                    image_data = await response.read()
                    return image_data
                    
        except asyncio.TimeoutError:
            logger.warning(f"Image download timeout after {self.download_timeout}s")
            return None
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None
    
    def encode_base64(self, image_data: bytes) -> str:
        """
        Encode image data to base64 string.
        
        Args:
            image_data: Raw image bytes
            
        Returns:
            Base64 encoded string
        """
        return base64.b64encode(image_data).decode('utf-8')
    
    async def process_image(
        self,
        attachment: Dict[str, Any],
        config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single image attachment.
        
        Args:
            attachment: Discord attachment dict with url, content_type, size, filename
            config: Vision configuration with max_image_size, vision_detail
            
        Returns:
            Processed image dict with url, base64, format, detail, or None if failed
        """
        url = attachment.get('url')
        content_type = attachment.get('content_type', '').lower()
        size = attachment.get('size', 0)
        filename = attachment.get('filename', 'unknown')
        
        # Validate URL
        if not self.validate_url(url):
            logger.warning(f"Rejected image from non-Discord URL: {url}")
            return None
        
        # Get config
        max_size_mb = config.get('max_image_size', 20)
        detail = config.get('vision_detail', 'auto')
        
        # Validate image
        is_valid, error = self.validate_image(content_type, size, max_size_mb)
        if not is_valid:
            logger.info(f"Skipping invalid image {filename}: {error}")
            return None
        
        # Download image
        image_data = await self.download_image(url, max_size_mb)
        if not image_data:
            logger.warning(f"Failed to download image: {filename}")
            return None
        
        # Encode to base64
        base64_data = self.encode_base64(image_data)
        
        logger.info(f"Processed image: {filename} ({size / 1024:.1f}KB)")
        
        return {
            'url': url,
            'base64': base64_data,
            'format': content_type,
            'detail': detail,
            'filename': filename,
            'size': size
        }


class MediaProcessor:
    """Main processor for image content."""
    
    def __init__(self):
        self.image_processor = ImageProcessor()
    
    async def process_attachments(
        self,
        attachments: List[Dict[str, Any]],
        vision_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process image attachments.
        
        Args:
            attachments: List of Discord attachment dicts
            vision_config: Vision configuration dict
            
        Returns:
            Dict with:
                - images: List of processed image dicts
                - errors: List of error messages
        """
        images = []
        errors = []
        
        # Check if vision is enabled
        vision_enabled = vision_config.get('vision_enabled', False)
        
        if not vision_enabled:
            logger.debug("Vision disabled, skipping image processing")
            return {'images': [], 'errors': []}
        
        # Limit number of images
        max_images = 5
        image_count = 0
        
        for attachment in attachments:
            content_type = attachment.get('content_type', '').lower()
            
            # Process images only
            if content_type.startswith('image/'):
                if image_count >= max_images:
                    logger.warning(f"Maximum images ({max_images}) reached, skipping remaining")
                    break
                
                try:
                    processed_image = await self.image_processor.process_image(
                        attachment=attachment,
                        config=vision_config
                    )
                    if processed_image:
                        images.append(processed_image)
                        image_count += 1
                except Exception as e:
                    error_msg = f"Error processing image {attachment.get('filename')}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
        
        logger.info(f"Processed {len(images)} images")
        
        return {
            'images': images,
            'errors': errors
        }
