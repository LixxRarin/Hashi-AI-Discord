"""
Character Card V3 Parser

Handles parsing of Character Cards in PNG, JSON, and CHARX formats
according to the Character Card V3 specification.
"""

import base64
import json
import logging
import struct
import zlib
import zipfile
from io import BytesIO
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class CharacterCardV3:
    """
    Character Card V3 data structure.
    
    Represents a complete character card with all fields from the spec.
    """
    spec: str = "chara_card_v3"
    spec_version: str = "3.0"
    
    # Required fields from V2
    name: str = ""
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_mes: str = ""
    mes_example: str = ""
    
    # Optional fields from V2
    creator: str = ""
    character_version: str = ""
    tags: List[str] = field(default_factory=list)
    system_prompt: str = ""
    post_history_instructions: str = ""
    alternate_greetings: List[str] = field(default_factory=list)
    
    # V3 additions
    creator_notes: str = ""
    creator_notes_multilingual: Dict[str, str] = field(default_factory=dict)
    nickname: Optional[str] = None
    source: List[str] = field(default_factory=list)
    group_only_greetings: List[str] = field(default_factory=list)
    creation_date: Optional[int] = None
    modification_date: Optional[int] = None
    
    # Lorebook
    character_book: Optional[Dict[str, Any]] = None
    
    # Assets
    assets: List[Dict[str, str]] = field(default_factory=list)
    
    # Extensions (for app-specific data)
    extensions: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format matching the spec."""
        return {
            "spec": self.spec,
            "spec_version": self.spec_version,
            "data": {
                "name": self.name,
                "description": self.description,
                "personality": self.personality,
                "scenario": self.scenario,
                "first_mes": self.first_mes,
                "mes_example": self.mes_example,
                "creator": self.creator,
                "character_version": self.character_version,
                "tags": self.tags,
                "system_prompt": self.system_prompt,
                "post_history_instructions": self.post_history_instructions,
                "alternate_greetings": self.alternate_greetings,
                "creator_notes": self.creator_notes,
                "creator_notes_multilingual": self.creator_notes_multilingual,
                "nickname": self.nickname,
                "source": self.source,
                "group_only_greetings": self.group_only_greetings,
                "creation_date": self.creation_date,
                "modification_date": self.modification_date,
                "character_book": self.character_book,
                "assets": self.assets,
                "extensions": self.extensions,
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CharacterCardV3':
        """Create CharacterCardV3 from dictionary."""
        card_data = data.get("data", {})
        
        return cls(
            spec=data.get("spec", "chara_card_v3"),
            spec_version=data.get("spec_version", "3.0"),
            name=card_data.get("name", ""),
            description=card_data.get("description", ""),
            personality=card_data.get("personality", ""),
            scenario=card_data.get("scenario", ""),
            first_mes=card_data.get("first_mes", ""),
            mes_example=card_data.get("mes_example", ""),
            creator=card_data.get("creator", ""),
            character_version=card_data.get("character_version", ""),
            tags=card_data.get("tags", []),
            system_prompt=card_data.get("system_prompt", ""),
            post_history_instructions=card_data.get("post_history_instructions", ""),
            alternate_greetings=card_data.get("alternate_greetings", []),
            creator_notes=card_data.get("creator_notes", ""),
            creator_notes_multilingual=card_data.get("creator_notes_multilingual", {}),
            nickname=card_data.get("nickname"),
            source=card_data.get("source", []),
            group_only_greetings=card_data.get("group_only_greetings", []),
            creation_date=card_data.get("creation_date"),
            modification_date=card_data.get("modification_date"),
            character_book=card_data.get("character_book"),
            assets=card_data.get("assets", []),
            extensions=card_data.get("extensions", {}),
        )


def parse_character_card(data: Union[bytes, str, Dict]) -> Optional[CharacterCardV3]:
    """
    Auto-detect format and parse character card.
    
    Args:
        data: Can be bytes (PNG/CHARX), string (JSON), or dict
        
    Returns:
        CharacterCardV3 object or None if parsing fails
    """
    try:
        # If already a dict, parse directly
        if isinstance(data, dict):
            return CharacterCardV3.from_dict(data)
        
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


def parse_png_card(png_bytes: bytes) -> Optional[CharacterCardV3]:
    """
    Parse character card from PNG/APNG file.
    
    Extracts character card data from PNG text chunks:
    - tEXt: Uncompressed text (Latin-1)
    - zTXt: Compressed text (deflate)
    - iTXt: International text (UTF-8, optionally compressed)
    
    Searches for 'ccv3' (V3) or 'chara' (V2) keywords.
    
    Args:
        png_bytes: PNG file bytes
        
    Returns:
        CharacterCardV3 object or None
    """
    try:
        # Verify PNG signature
        if png_bytes[:8] != b'\x89PNG\r\n\x1a\n':
            log.error("Invalid PNG signature")
            return None
        
        # Track all chunks for diagnostic purposes
        all_chunks = []
        text_chunks_found = []
        
        # Parse PNG chunks
        offset = 8
        ccv3_data = None
        chara_data = None  # V2 fallback
        
        while offset < len(png_bytes):
            # Read chunk length and type
            if offset + 8 > len(png_bytes):
                break
            
            chunk_length = struct.unpack('>I', png_bytes[offset:offset+4])[0]
            chunk_type = png_bytes[offset+4:offset+8].decode('ascii', errors='ignore')
            
            # Track chunk for diagnostics
            all_chunks.append(chunk_type)
            
            # Read chunk data
            chunk_data_start = offset + 8
            chunk_data_end = chunk_data_start + chunk_length
            
            if chunk_data_end > len(png_bytes):
                break
            
            chunk_data = png_bytes[chunk_data_start:chunk_data_end]
            
            # Process text chunks
            if chunk_type == 'tEXt':
                # tEXt format: keyword\0text
                null_pos = chunk_data.find(b'\x00')
                if null_pos > 0:
                    keyword = chunk_data[:null_pos].decode('ascii', errors='ignore')
                    text_data = chunk_data[null_pos+1:]
                    text_chunks_found.append(f"tEXt:{keyword}")
                    
                    if keyword == 'ccv3':
                        ccv3_data = ('tEXt', text_data)
                        log.debug(f"Found ccv3 in tEXt chunk ({len(text_data)} bytes)")
                    elif keyword == 'chara':
                        chara_data = ('tEXt', text_data)
                        log.debug(f"Found chara in tEXt chunk ({len(text_data)} bytes)")
            
            elif chunk_type == 'zTXt':
                # zTXt format: keyword\0compression_method\compressed_data
                null_pos = chunk_data.find(b'\x00')
                if null_pos > 0:
                    keyword = chunk_data[:null_pos].decode('ascii', errors='ignore')
                    compression_method = chunk_data[null_pos+1]
                    compressed_data = chunk_data[null_pos+2:]
                    text_chunks_found.append(f"zTXt:{keyword}")
                    
                    if compression_method == 0:  # deflate
                        try:
                            text_data = zlib.decompress(compressed_data)
                            
                            if keyword == 'ccv3':
                                ccv3_data = ('zTXt', text_data)
                                log.debug(f"Found ccv3 in zTXt chunk ({len(text_data)} bytes decompressed)")
                            elif keyword == 'chara':
                                chara_data = ('zTXt', text_data)
                                log.debug(f"Found chara in zTXt chunk ({len(text_data)} bytes decompressed)")
                        except zlib.error as e:
                            log.warning(f"Failed to decompress zTXt chunk with keyword '{keyword}': {e}")
            
            elif chunk_type == 'iTXt':
                # iTXt format: keyword\0compression_flag\compression_method\language_tag\0translated_keyword\0text
                null_pos = chunk_data.find(b'\x00')
                if null_pos > 0:
                    keyword = chunk_data[:null_pos].decode('ascii', errors='ignore')
                    compression_flag = chunk_data[null_pos+1]
                    compression_method = chunk_data[null_pos+2]
                    
                    # Find language tag end
                    lang_start = null_pos + 3
                    lang_end = chunk_data.find(b'\x00', lang_start)
                    if lang_end > 0:
                        # Find translated keyword end
                        trans_end = chunk_data.find(b'\x00', lang_end + 1)
                        if trans_end > 0:
                            text_data_raw = chunk_data[trans_end+1:]
                            text_chunks_found.append(f"iTXt:{keyword}")
                            
                            # Decompress if needed
                            if compression_flag == 1 and compression_method == 0:
                                try:
                                    text_data = zlib.decompress(text_data_raw)
                                except zlib.error as e:
                                    log.warning(f"Failed to decompress iTXt chunk with keyword '{keyword}': {e}")
                                    continue
                            else:
                                text_data = text_data_raw
                            
                            if keyword == 'ccv3':
                                ccv3_data = ('iTXt', text_data)
                                log.debug(f"Found ccv3 in iTXt chunk ({len(text_data)} bytes)")
                            elif keyword == 'chara':
                                chara_data = ('iTXt', text_data)
                                log.debug(f"Found chara in iTXt chunk ({len(text_data)} bytes)")
            
            # Move to next chunk (length + type + data + CRC)
            offset = chunk_data_end + 4
        
        # Log diagnostic information
        unique_chunks = list(dict.fromkeys(all_chunks))  # Remove duplicates while preserving order
        log.debug(f"PNG chunks found: {', '.join(unique_chunks)}")
        if text_chunks_found:
            log.info(f"Text chunks found: {', '.join(text_chunks_found)}")
        else:
            log.warning("No text chunks (tEXt/zTXt/iTXt) found in PNG")
        
        # Try V3 first
        if ccv3_data:
            chunk_type, raw_data = ccv3_data
            try:
                # Decode base64
                json_str = base64.b64decode(raw_data).decode('utf-8')
                card_dict = json.loads(json_str)
                
                if validate_card_v3(card_dict):
                    log.info(f"Successfully parsed Character Card V3 from PNG ({chunk_type} chunk)")
                    return CharacterCardV3.from_dict(card_dict)
            except Exception as e:
                log.error(f"Error parsing ccv3 data from {chunk_type} chunk: {e}")
        
        # Fallback to V2
        if chara_data:
            chunk_type, raw_data = chara_data
            try:
                json_str = base64.b64decode(raw_data).decode('utf-8')
                card_dict = json.loads(json_str)
                
                # Convert V2 to V3 format
                log.info(f"Parsed Character Card V2 from PNG ({chunk_type} chunk), converting to V3")
                return convert_v2_to_v3(card_dict)
            except Exception as e:
                log.error(f"Error parsing chara data from {chunk_type} chunk: {e}")
        
        # Provide helpful error message
        if not text_chunks_found:
            log.error("No valid character card data found in PNG: No text chunks present. "
                     "This PNG may be a plain image without embedded character card metadata.")
        else:
            log.error(f"No valid character card data found in PNG. Text chunks found: {', '.join(text_chunks_found)}, "
                     f"but none contained 'ccv3' or 'chara' keywords.")
        return None
        
    except Exception as e:
        log.error(f"Error parsing PNG card: {e}")
        return None


def parse_json_card(json_str: str) -> Optional[CharacterCardV3]:
    """
    Parse character card from JSON string.
    
    Args:
        json_str: JSON string
        
    Returns:
        CharacterCardV3 object or None
    """
    try:
        card_dict = json.loads(json_str)
        
        # Check if V3
        if card_dict.get("spec") == "chara_card_v3":
            if validate_card_v3(card_dict):
                log.info("Successfully parsed Character Card V3 from JSON")
                return CharacterCardV3.from_dict(card_dict)
        
        # Try V2 conversion
        if "data" in card_dict or "name" in card_dict:
            log.info("Detected V2 format, converting to V3")
            return convert_v2_to_v3(card_dict)
        
        log.error("Invalid character card JSON format")
        return None
        
    except json.JSONDecodeError as e:
        log.error(f"Invalid JSON: {e}")
        return None
    except Exception as e:
        log.error(f"Error parsing JSON card: {e}")
        return None


def parse_charx_card(charx_bytes: bytes) -> Optional[CharacterCardV3]:
    """
    Parse character card from CHARX file (ZIP format).
    
    Extracts card.json and assets from the ZIP file.
    
    Args:
        charx_bytes: CHARX file bytes
        
    Returns:
        CharacterCardV3 object or None
    """
    try:
        with zipfile.ZipFile(BytesIO(charx_bytes), 'r') as zf:
            # Check for card.json at root
            if 'card.json' not in zf.namelist():
                log.error("card.json not found in CHARX file")
                return None
            
            # Read and parse card.json
            card_json = zf.read('card.json').decode('utf-8')
            card = parse_json_card(card_json)
            
            if card is None:
                return None
            
            # Note: Assets will be extracted by the loader module
            # Here we just parse the card structure
            
            log.info(f"Successfully parsed CHARX file with {len(zf.namelist())} files")
            return card
            
    except zipfile.BadZipFile:
        log.error("Invalid ZIP file (CHARX)")
        return None
    except Exception as e:
        log.error(f"Error parsing CHARX card: {e}")
        return None


def validate_card_v3(card_dict: Dict[str, Any]) -> bool:
    """
    Validate Character Card V3 structure.
    
    Args:
        card_dict: Card dictionary to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        # Check required top-level fields
        if card_dict.get("spec") != "chara_card_v3":
            log.warning("Invalid spec field")
            return False
        
        if "spec_version" not in card_dict:
            log.warning("Missing spec_version field")
            return False
        
        if "data" not in card_dict:
            log.error("Missing data field")
            return False
        
        data = card_dict["data"]
        
        # Check required data fields
        required_fields = ["name"]
        for field in required_fields:
            if field not in data:
                log.error(f"Missing required field: {field}")
                return False
        
        log.debug("Character card V3 validation passed")
        return True
        
    except Exception as e:
        log.error(f"Error validating card: {e}")
        return False


def convert_v2_to_v3(v2_card: Dict[str, Any]) -> Optional[CharacterCardV3]:
    """
    Convert Character Card V2 to V3 format.
    
    Args:
        v2_card: V2 card dictionary
        
    Returns:
        CharacterCardV3 object or None
    """
    try:
        # V2 can have data at root or in 'data' field
        if "data" in v2_card:
            data = v2_card["data"]
        else:
            data = v2_card
        
        # Create V3 card with V2 data
        card = CharacterCardV3(
            spec="chara_card_v3",
            spec_version="3.0",
            name=data.get("name", ""),
            description=data.get("description", ""),
            personality=data.get("personality", ""),
            scenario=data.get("scenario", ""),
            first_mes=data.get("first_mes", ""),
            mes_example=data.get("mes_example", ""),
            creator=data.get("creator", ""),
            character_version=data.get("character_version", ""),
            tags=data.get("tags", []),
            system_prompt=data.get("system_prompt", ""),
            post_history_instructions=data.get("post_history_instructions", ""),
            alternate_greetings=data.get("alternate_greetings", []),
            creator_notes=data.get("creator_notes", ""),
            character_book=data.get("character_book"),
            extensions=data.get("extensions", {}),
        )
        
        # Add default icon asset if not present
        if not card.assets:
            card.assets = [{
                "type": "icon",
                "uri": "ccdefault:",
                "name": "main",
                "ext": "png"
            }]
        
        log.info(f"Converted V2 card '{card.name}' to V3 format")
        return card
        
    except Exception as e:
        log.error(f"Error converting V2 to V3: {e}")
        return None
