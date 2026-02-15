"""
Avatar utilities for character cards and webhooks.

Handles fetching and extracting avatar images from various sources.
"""
import zipfile
from pathlib import Path
from typing import Optional

import aiohttp

import utils.func as func


class AvatarUtils:
    """Utilities for avatar extraction and manipulation."""
    
    @staticmethod
    async def fetch_from_url(url: str) -> Optional[bytes]:
        """
        Fetch avatar image from URL.
        
        Args:
            url: URL to fetch the avatar from
            
        Returns:
            Avatar image bytes, or None if fetch failed
        """
        if not url:
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.read()
                    func.log.warning(f"Failed to fetch avatar from URL: HTTP {response.status}")
                    return None
        except Exception as e:
            func.log.error(f"Error fetching avatar from URL: {e}")
            return None
    
    @staticmethod
    async def extract_from_card(cache_path: str) -> Optional[bytes]:
        """
        Extract avatar from character card file.
        
        Supports PNG and CHARX formats.
        
        Args:
            cache_path: Path to the cached character card file
            
        Returns:
            Avatar image bytes, or None if extraction failed
        """
        try:
            card_file = Path(cache_path)
            
            if not card_file.exists():
                func.log.warning(f"Card file not found: {cache_path}")
                return None
            
            # For PNG files, the file itself is the avatar
            if card_file.suffix.lower() == '.png':
                return await AvatarUtils.extract_from_png(str(card_file))
            
            # For CHARX files, extract from ZIP
            elif card_file.suffix.lower() == '.charx':
                return await AvatarUtils.extract_from_charx(str(card_file))
            
            else:
                func.log.warning(f"Unsupported card file format: {card_file.suffix}")
                return None
                
        except Exception as e:
            func.log.error(f"Error extracting avatar from card file: {e}")
            return None
    
    @staticmethod
    async def extract_from_png(file_path: str) -> Optional[bytes]:
        """
        Extract avatar from PNG character card file.
        
        For PNG files, the entire file is the avatar image.
        
        Args:
            file_path: Path to the PNG file
            
        Returns:
            Avatar image bytes
        """
        try:
            with open(file_path, 'rb') as f:
                return f.read()
        except Exception as e:
            func.log.error(f"Error reading PNG file: {e}")
            return None
    
    @staticmethod
    async def extract_from_charx(file_path: str) -> Optional[bytes]:
        """
        Extract avatar from CHARX (ZIP) character card file.
        
        Looks for files with 'icon' or 'avatar' in the name within the ZIP.
        
        Args:
            file_path: Path to the CHARX file
            
        Returns:
            Avatar image bytes, or None if not found
        """
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                # Look for avatar in assets
                for name in zf.namelist():
                    if 'icon' in name.lower() or 'avatar' in name.lower():
                        avatar_bytes = zf.read(name)
                        func.log.debug(f"Extracted avatar from CHARX: {name}")
                        return avatar_bytes
                
                func.log.warning("No avatar found in CHARX file")
                return None
                
        except zipfile.BadZipFile:
            func.log.error(f"Invalid CHARX file (not a valid ZIP): {file_path}")
            return None
        except Exception as e:
            func.log.error(f"Error extracting avatar from CHARX: {e}")
            return None
