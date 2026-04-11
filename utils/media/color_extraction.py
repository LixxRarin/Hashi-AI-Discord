"""
Color Extraction Utilities

Extracts dominant colors from images for dynamic embed styling.
"""

import logging
from typing import Optional, Tuple
from io import BytesIO

import discord
import aiohttp

log = logging.getLogger(__name__)


async def get_dominant_color_from_url(image_url: str) -> Optional[discord.Color]:
    """
    Extract the dominant color from an image URL.
    
    Args:
        image_url: URL of the image to analyze
        
    Returns:
        discord.Color object with the dominant color, or None if extraction fails
    """
    try:
        # Download image
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    log.warning(f"Failed to download image from {image_url}: HTTP {response.status}")
                    return None
                
                image_data = await response.read()
        
        # Extract color
        return await _extract_dominant_color(image_data)
        
    except Exception as e:
        log.error(f"Error extracting color from URL {image_url}: {e}")
        return None


async def _extract_dominant_color(image_data: bytes) -> Optional[discord.Color]:
    """
    Extract dominant color from image bytes using PIL.
    
    Uses a simple algorithm:
    1. Resize image to small size for performance
    2. Convert to RGB
    3. Get color palette
    4. Find most common color (excluding very dark/light colors)
    
    Args:
        image_data: Raw image bytes
        
    Returns:
        discord.Color object with the dominant color
    """
    try:
        from PIL import Image
        
        # Open image
        img = Image.open(BytesIO(image_data))
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Resize to small size for faster processing
        img = img.resize((150, 150), Image.Resampling.LANCZOS)
        
        # Get colors and their counts
        colors = img.getcolors(img.size[0] * img.size[1])
        
        if not colors:
            return None
        
        # Sort by frequency
        colors.sort(key=lambda x: x[0], reverse=True)
        
        # Find the most vibrant/saturated color (skip very dark or very light colors)
        for count, (r, g, b) in colors:
            # Skip colors that are too dark (close to black)
            if r < 30 and g < 30 and b < 30:
                continue
            
            # Skip colors that are too light (close to white)
            if r > 225 and g > 225 and b > 225:
                continue
            
            # Skip colors that are too gray (low saturation)
            max_val = max(r, g, b)
            min_val = min(r, g, b)
            saturation = (max_val - min_val) / max_val if max_val > 0 else 0
            
            if saturation < 0.2:  # Skip low saturation colors
                continue
            
            # Found a good color
            return discord.Color.from_rgb(r, g, b)
        
        # Fallback: use the most common color even if it's not vibrant
        _, (r, g, b) = colors[0]
        return discord.Color.from_rgb(r, g, b)
        
    except Exception as e:
        log.error(f"Error extracting dominant color: {e}")
        return None


def enhance_color_vibrancy(color: discord.Color, factor: float = 1.3) -> discord.Color:
    """
    Enhance the vibrancy/saturation of a color.
    
    Args:
        color: Original discord.Color
        factor: Saturation multiplier (>1 increases saturation)
        
    Returns:
        Enhanced discord.Color
    """
    try:
        r, g, b = color.r, color.g, color.b
        
        # Convert to HSV
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        diff = max_val - min_val
        
        if diff == 0:
            return color  # Gray color, can't enhance
        
        # Calculate saturation
        saturation = diff / max_val if max_val > 0 else 0
        
        # Enhance saturation
        new_saturation = min(saturation * factor, 1.0)
        
        # Convert back to RGB
        if max_val == r:
            hue = ((g - b) / diff) % 6
        elif max_val == g:
            hue = ((b - r) / diff) + 2
        else:
            hue = ((r - g) / diff) + 4
        
        hue = hue / 6.0
        
        # HSV to RGB conversion
        def hsv_to_rgb(h: float, s: float, v: float) -> Tuple[int, int, int]:
            i = int(h * 6)
            f = h * 6 - i
            p = v * (1 - s)
            q = v * (1 - f * s)
            t = v * (1 - (1 - f) * s)
            
            i = i % 6
            if i == 0:
                return int(v * 255), int(t * 255), int(p * 255)
            if i == 1:
                return int(q * 255), int(v * 255), int(p * 255)
            if i == 2:
                return int(p * 255), int(v * 255), int(t * 255)
            if i == 3:
                return int(p * 255), int(q * 255), int(v * 255)
            if i == 4:
                return int(t * 255), int(p * 255), int(v * 255)
            return int(v * 255), int(p * 255), int(q * 255)
        
        new_r, new_g, new_b = hsv_to_rgb(hue, new_saturation, max_val / 255.0)
        return discord.Color.from_rgb(new_r, new_g, new_b)
        
    except Exception as e:
        log.error(f"Error enhancing color vibrancy: {e}")
        return color  # Return original on error
