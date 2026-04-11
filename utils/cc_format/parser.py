"""
Character Card Parser

Handles parsing of Character Cards in PNG, JSON, and CHARX formats
and dynamically detects whether they are V1, V2, or V3 format.
"""

import base64
import json
import logging
import struct
import zlib
import zipfile
from io import BytesIO
from typing import Dict, Any, Optional, List, Union

from .models import CharacterCard, CharacterCardV1, CharacterCardV2, CharacterCardV3

log = logging.getLogger(__name__)


def parse_character_card(data: Union[bytes, str, Dict]) -> Optional[CharacterCard]:
    """
    Auto-detect format and parse character card.
    
    Args:
        data: Can be bytes (PNG/CHARX), string (JSON), or dict
        
    Returns:
        CharacterCard object (V1, V2, or V3) or None if parsing fails
    """
    try:
        # If already a dict, parse directly
        if isinstance(data, dict):
            return dict_to_card(data)
        
        # If string, try JSON
        if isinstance(data, str):
            return parse_json_card(data)
        
        # If bytes, detect format
        if isinstance(data, bytes):
            # Check for PNG signature
            if data[:8] == b'\x89PNG\r\n\x1a\n':
                return parse_png_card(data)
            
            # Check for ZIP signature (CHARX)
            if data[:4] == b'PK\x03\x04':
                return parse_charx_card(data)
            
            # Try as JSON string
            try:
                json_str = data.decode('utf-8')
                return parse_json_card(json_str)
            except UnicodeDecodeError:
                pass
        
        log.error("Unable to detect character card format")
        return None
        
    except Exception as e:
        log.error(f"Error parsing character card: {e}")
        return None


def dict_to_card(card_dict: Dict[str, Any]) -> Optional[CharacterCard]:
    """Convert raw dictionary to the appropriate CharacterCard class."""
    spec = card_dict.get("spec", "")
    
    if spec == "chara_card_v3":
        return CharacterCardV3.from_dict(card_dict)
    elif spec == "chara_card_v2":
        return CharacterCardV2.from_dict(card_dict)
    
    # If no spec is defined, it might be V1. V1 doesn't have "data" wrap typically, but some systems wrap it anyway.
    if "data" in card_dict and "name" in card_dict["data"]:
        # Wrapped V1 (Treat as V2 fallback)
        return CharacterCardV2.from_dict(card_dict)
    elif "name" in card_dict:
        # Pure V1
        return CharacterCardV1.from_dict(card_dict)
        
    log.error("Invalid character card structure: missing 'spec' or 'name'")
    return None


def parse_png_card(png_bytes: bytes) -> Optional[CharacterCard]:
    """
    Parse character card from PNG/APNG file.
    
    Extracts character card data from PNG text chunks search for 'ccv3' or 'chara' keywords.
    
    Args:
        png_bytes: PNG file bytes
        
    Returns:
        CharacterCard object or None
    """
    try:
        if png_bytes[:8] != b'\x89PNG\r\n\x1a\n':
            log.error("Invalid PNG signature")
            return None
        
        offset = 8
        ccv3_data = None
        chara_data = None  # V1/V2 fallback
        
        while offset < len(png_bytes):
            if offset + 8 > len(png_bytes):
                break
            
            chunk_length = struct.unpack('>I', png_bytes[offset:offset+4])[0]
            chunk_type = png_bytes[offset+4:offset+8].decode('ascii', errors='ignore')
            
            chunk_data_start = offset + 8
            chunk_data_end = chunk_data_start + chunk_length
            
            if chunk_data_end > len(png_bytes):
                break
            
            chunk_data = png_bytes[chunk_data_start:chunk_data_end]
            
            if chunk_type == 'tEXt':
                null_pos = chunk_data.find(b'\x00')
                if null_pos > 0:
                    keyword = chunk_data[:null_pos].decode('ascii', errors='ignore')
                    text_data = chunk_data[null_pos+1:]
                    if keyword == 'ccv3':
                        ccv3_data = text_data
                    elif keyword == 'chara' and not chara_data:
                        chara_data = text_data
            
            elif chunk_type == 'zTXt':
                null_pos = chunk_data.find(b'\x00')
                if null_pos > 0:
                    keyword = chunk_data[:null_pos].decode('ascii', errors='ignore')
                    compression_method = chunk_data[null_pos+1]
                    compressed_data = chunk_data[null_pos+2:]
                    
                    if compression_method == 0:
                        try:
                            text_data = zlib.decompress(compressed_data)
                            if keyword == 'ccv3':
                                ccv3_data = text_data
                            elif keyword == 'chara' and not chara_data:
                                chara_data = text_data
                        except zlib.error:
                            pass
            
            elif chunk_type == 'iTXt':
                null_pos = chunk_data.find(b'\x00')
                if null_pos > 0:
                    keyword = chunk_data[:null_pos].decode('ascii', errors='ignore')
                    compression_flag = chunk_data[null_pos+1]
                    compression_method = chunk_data[null_pos+2]
                    
                    lang_start = null_pos + 3
                    lang_end = chunk_data.find(b'\x00', lang_start)
                    if lang_end > 0:
                        trans_end = chunk_data.find(b'\x00', lang_end + 1)
                        if trans_end > 0:
                            text_data_raw = chunk_data[trans_end+1:]
                            if compression_flag == 1 and compression_method == 0:
                                try:
                                    text_data = zlib.decompress(text_data_raw)
                                except zlib.error:
                                    text_data = None
                            else:
                                text_data = text_data_raw
                                
                            if text_data:
                                if keyword == 'ccv3':
                                    ccv3_data = text_data
                                elif keyword == 'chara' and not chara_data:
                                    chara_data = text_data
            
            offset = chunk_data_end + 4
        
        # Try V3 first
        if ccv3_data:
            try:
                json_str = base64.b64decode(ccv3_data).decode('utf-8')
                card_dict = json.loads(json_str)
                # If explicit ccv3 chunk, enforce V3 parsing even if spec is missing internally
                if "spec" not in card_dict:
                    card_dict["spec"] = "chara_card_v3"
                return dict_to_card(card_dict)
            except Exception as e:
                log.error(f"Error parsing ccv3 data from PNG: {e}")
        
        # Fallback to V1/V2
        if chara_data:
            try:
                json_str = base64.b64decode(chara_data).decode('utf-8')
                card_dict = json.loads(json_str)
                return dict_to_card(card_dict)
            except Exception as e:
                log.error(f"Error parsing chara data from PNG: {e}")
        
        log.error("No valid character card data found in PNG.")
        return None
        
    except Exception as e:
        log.error(f"Error parsing PNG card: {e}")
        return None


def parse_json_card(json_str: str) -> Optional[CharacterCard]:
    """Parse character card from JSON string."""
    try:
        card_dict = json.loads(json_str)
        return dict_to_card(card_dict)
    except json.JSONDecodeError as e:
        log.error(f"Invalid JSON: {e}")
        return None
    except Exception as e:
        log.error(f"Error parsing JSON card: {e}")
        return None


def parse_charx_card(charx_bytes: bytes) -> Optional[CharacterCard]:
    """Parse character card from CHARX file (ZIP format)."""
    try:
        with zipfile.ZipFile(BytesIO(charx_bytes), 'r') as zf:
            if 'card.json' not in zf.namelist():
                log.error("card.json not found in CHARX file")
                return None
            
            card_json = zf.read('card.json').decode('utf-8')
            return parse_json_card(card_json)
            
    except zipfile.BadZipFile:
        log.error("Invalid ZIP file (CHARX)")
        return None
    except Exception as e:
        log.error(f"Error parsing CHARX card: {e}")
        return None
