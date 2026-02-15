"""
Character Card Loader

Handles downloading, caching, and loading of character cards from URLs.
Saves files with their original filenames directly in character_cards/ folder.
"""

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse, unquote

import aiohttp

from .parser import CharacterCardV3, parse_character_card

log = logging.getLogger(__name__)

# Cache directory
CACHE_DIR = Path("character_cards")
CACHE_DIR.mkdir(exist_ok=True)


class CharacterCardLoader:
    """
    Manages loading and caching of character cards.
    Saves files with their original filenames from URLs.
    """
    
    def __init__(self, cache_dir: Path = CACHE_DIR):
        """
        Initialize the loader.
        
        Args:
            cache_dir: Directory for caching cards
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)
    
    def _extract_filename_from_url(self, url: str) -> str:
        """
        Extract the original filename from URL.
        
        Args:
            url: URL to extract filename from
            
        Returns:
            Original filename from URL
        """
        parsed = urlparse(url)
        path = unquote(parsed.path)
        filename = os.path.basename(path)
        
        # If no filename, generate one from URL hash
        if not filename:
            url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
            filename = f"card_{url_hash}.png"
        
        return filename
    
    async def load_card(
        self,
        url: str,
        force_reload: bool = False
    ) -> Optional[Tuple[CharacterCardV3, str]]:
        """
        Load a character card from URL or cache.
        Downloads and saves file with original filename.
        
        Args:
            url: URL to the character card (PNG/JSON/CHARX)
            force_reload: Force re-download even if cached
            
        Returns:
            Tuple of (CharacterCardV3, file_path) or None
        """
        try:
            # Extract filename from URL
            filename = self._extract_filename_from_url(url)
            file_path = self.cache_dir / filename
            
            # Check cache first
            if not force_reload and file_path.exists():
                log.info(f"Loading card from cache: {filename}")
                try:
                    with open(file_path, 'rb') as f:
                        raw_data = f.read()
                    
                    # Parse on-demand
                    card = parse_character_card(raw_data)
                    if card:
                        return card, str(file_path)
                except Exception as e:
                    log.error(f"Error loading from cache: {e}")
                    # Continue to re-download
            
            # Download card
            log.info(f"Downloading card from: {url}")
            card_data = await self.download_card(url)
            
            if card_data is None:
                return None
            
            # Parse card FIRST (before saving)
            card = parse_character_card(card_data)
            
            if card is None:
                log.error(f"Failed to parse downloaded card from {url}")
                log.error(f"Downloaded {len(card_data)} bytes but content is not a valid character card")
                # Don't save invalid files
                return None
            
            # Only save if parsing succeeded
            with open(file_path, 'wb') as f:
                f.write(card_data)
            
            log.info(f"Saved valid card: {filename} ({len(card_data)} bytes)")
            log.info(f"Successfully loaded card: {card.name}")
            return card, str(file_path)
            
        except Exception as e:
            log.error(f"Error loading card: {e}")
            return None
    
    async def download_card(self, url: str, max_retries: int = 3) -> Optional[bytes]:
        """
        Download character card from URL with retry logic.
        
        Args:
            url: URL to download from
            max_retries: Maximum number of retry attempts
            
        Returns:
            Card data as bytes or None
        """
        # Validate URL
        parsed = urlparse(url)
        if parsed.scheme not in ['http', 'https']:
            log.error(f"Invalid URL scheme: {parsed.scheme}")
            return None
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Download with timeout and proper headers
                timeout = aiohttp.ClientTimeout(total=60, connect=15, sock_read=30)
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': '*/*',
                }
                
                # Use default connector with better settings for stability
                connector = aiohttp.TCPConnector(
                    force_close=False,
                    enable_cleanup_closed=True,
                    ttl_dns_cache=300
                )
                
                async with aiohttp.ClientSession(
                    timeout=timeout,
                    headers=headers,
                    connector=connector
                ) as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            log.error(f"HTTP {response.status} when downloading card")
                            return None
                        
                        # Check content length (limit to 50MB)
                        content_length = response.headers.get('Content-Length')
                        if content_length and int(content_length) > 50 * 1024 * 1024:
                            log.error("Card file too large (>50MB)")
                            return None
                        
                        card_data = await response.read()
                        log.info(f"Downloaded {len(card_data)} bytes (attempt {attempt + 1})")
                        return card_data
                        
            except asyncio.TimeoutError as e:
                last_error = f"Timeout (attempt {attempt + 1}/{max_retries})"
                log.warning(f"Timeout downloading card (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                    
            except aiohttp.ServerDisconnectedError as e:
                last_error = f"Server disconnected (attempt {attempt + 1}/{max_retries})"
                log.warning(f"Server disconnected (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                    
            except aiohttp.ClientError as e:
                last_error = f"Network error: {e}"
                log.warning(f"Network error downloading card (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                    
            except Exception as e:
                last_error = f"Unexpected error: {e}"
                log.error(f"Error downloading card (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
        
        log.error(f"Failed to download card after {max_retries} attempts. Last error: {last_error}")
        return None
    
    def clear_cache(self, filename: Optional[str] = None) -> bool:
        """
        Clear card cache.
        
        Args:
            filename: Specific file to clear, or None to clear all
            
        Returns:
            True if cleared successfully
        """
        try:
            if filename:
                # Clear specific file
                file_path = self.cache_dir / filename
                if file_path.exists():
                    file_path.unlink()
                    log.info(f"Cleared cache for: {filename}")
                    return True
                else:
                    log.warning(f"File not found: {filename}")
                    return False
            else:
                # Clear all cache
                for file_path in self.cache_dir.iterdir():
                    if file_path.is_file():
                        file_path.unlink()
                log.info("Cleared all card cache")
                return True
                    
        except Exception as e:
            log.error(f"Error clearing cache: {e}")
            return False
    
    def get_cache_info(self) -> Dict[str, Any]:
        """
        Get information about cached cards.
        
        Returns:
            Dictionary with cache statistics
        """
        try:
            cached_files = []
            total_size = 0
            
            for file_path in self.cache_dir.iterdir():
                if not file_path.is_file():
                    continue
                
                file_size = file_path.stat().st_size
                total_size += file_size
                
                cached_files.append({
                    "filename": file_path.name,
                    "size_bytes": file_size,
                    "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })
            
            return {
                "total_files": len(cached_files),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "files": cached_files
            }
            
        except Exception as e:
            log.error(f"Error getting cache info: {e}")
            return {"error": str(e)}


# Global loader instance
_loader = CharacterCardLoader()


async def load_local_card(file_path: str) -> Optional[Tuple[CharacterCardV3, str]]:
    """
    Load a character card from a local file.
    
    Args:
        file_path: Path to the local character card file
        
    Returns:
        Tuple of (CharacterCardV3, file_path) or None if failed
    """
    try:
        path = Path(file_path)
        
        if not path.exists():
            log.error(f"Character card file not found: {file_path}")
            return None
        
        log.info(f"Loading local character card: {file_path}")
        
        with open(path, 'rb') as f:
            raw_data = f.read()
        
        # Parse the card
        card = parse_character_card(raw_data)
        
        if card is None:
            log.error(f"Failed to parse character card from: {file_path}")
            return None
        
        log.info(f"Successfully loaded local card: {card.name}")
        return card, str(path)
        
    except Exception as e:
        log.error(f"Error loading local card: {e}")
        return None


async def download_card(url: str, force_reload: bool = False) -> Optional[Tuple[CharacterCardV3, str]]:
    """
    Download and cache a character card.
    
    Args:
        url: URL to the character card
        force_reload: Force re-download
        
    Returns:
        Tuple of (CharacterCardV3, file_path) or None
    """
    return await _loader.load_card(url, force_reload)


def clear_card_cache(filename: Optional[str] = None) -> bool:
    """
    Clear card cache.
    
    Args:
        filename: Specific file to clear, or None to clear all
        
    Returns:
        True if cleared successfully
    """
    return _loader.clear_cache(filename)


def get_cache_info() -> Dict[str, Any]:
    """
    Get information about cached cards.
    
    Returns:
        Dictionary with cache statistics
    """
    return _loader.get_cache_info()
