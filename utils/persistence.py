"""
Persistence Utilities

This module provides generic persistence functions for JSON data with support
for debounced saving and file locking. It consolidates persistence logic from
both func.py and openai_client.py.

Classes:
    - PersistenceManager: Manages file persistence with debouncing

Functions:
    - read_json: Read JSON file (moved from func.py)
    - write_json: Write JSON file (moved from func.py)
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional


# Get logger
log = logging.getLogger(__name__)


def read_json(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Reads and returns the content of a JSON file.
    
    This function was moved from utils/func.py to centralize persistence logic.

    Args:
        file_path: Path to the JSON file

    Returns:
        Optional[Dict[str, Any]]: JSON content or None if error
    """
    try:
        with open(file_path, 'r', encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        write_json(file_path, {})
        return {}
    except json.JSONDecodeError:
        log.error(
            "Error decoding JSON file '%s'. Creating new file.", file_path)
        write_json(file_path, {})
        return {}
    except Exception as e:
        log.error("Error reading JSON file '%s': %s", file_path, e)
        return None


def write_json(file_path: str, data: Dict[str, Any]) -> None:
    """
    Writes the provided data to a JSON file.
    
    This function was moved from utils/func.py to centralize persistence logic.

    Args:
        file_path: Path to the JSON file
        data: Data to write
    """
    try:
        with open(file_path, 'w', encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception as e:
        log.error("Error saving JSON file '%s': %s", file_path, e)

class PersistenceManager:
    """
    Manages file persistence with debounced saving.
    
    This class consolidates the persistence logic from openai_client.py
    and makes it reusable for any type of data (conversation history,
    session data, cache, etc.).
    
    Features:
    - Async file operations
    - Debounced saving (batches rapid updates)
    - Automatic error handling
    
    Example:
        >>> manager = PersistenceManager("conversation_history.json")
        >>> await manager.load()
        >>> data = {"server1": {"channel1": {"ai1": [...]}}}
        >>> await manager.save(data)  # Debounced save
    """
    
    def __init__(self, file_path: str, debounce_delay: float = 1.0):
        """
        Initialize the persistence manager.
        
        Args:
            file_path: Path to the JSON file
            debounce_delay: Delay in seconds before saving (default: 1.0)
        """
        self.file_path = file_path
        self.debounce_delay = debounce_delay
        self._save_task: Optional[asyncio.Task] = None
    
    def _load_sync(self) -> Dict[str, Any]:
        """
        Synchronously load data from file.
        
        Returns:
            The data dictionary
        """
        if not os.path.exists(self.file_path):
            return {}
        
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                log.debug(f"Loaded data from {self.file_path}")
                return data
        except json.JSONDecodeError as e:
            log.error(f"Error decoding {self.file_path}: {e}")
            return {}
        except Exception as e:
            log.error(f"Error loading {self.file_path}: {e}")
            return {}
    
    def _save_sync(self, data: Dict[str, Any]) -> bool:
        """
        Synchronously save data to file.
        
        Args:
            data: The data to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log.debug(f"Saved data to {self.file_path}")
            return True
        except Exception as e:
            log.error(f"Error saving {self.file_path}: {e}")
            return False
    
    async def load(self) -> Dict[str, Any]:
        """
        Load data from file asynchronously.
        
        Returns:
            The data dictionary
        """
        return await asyncio.to_thread(self._load_sync)
    
    async def save_immediate(self, data: Dict[str, Any]) -> bool:
        """
        Save data immediately without debouncing.
        
        Args:
            data: The data to save
            
        Returns:
            True if successful, False otherwise
        """
        return await asyncio.to_thread(self._save_sync, data)
    
    async def _save_debounced(self, data: Dict[str, Any]) -> None:
        """
        Save data with a delay to batch multiple rapid updates.
        
        Args:
            data: The data to save
        """
        await asyncio.sleep(self.debounce_delay)
        await self.save_immediate(data)
    
    def schedule_save(self, data: Dict[str, Any]) -> None:
        """
        Schedule a debounced save operation.
        
        If a save is already scheduled, it will be cancelled and rescheduled.
        This allows batching multiple rapid updates into a single save.
        
        Args:
            data: The data to save
        """
        # Cancel previous save task if it exists and hasn't completed
        if self._save_task and not self._save_task.done():
            self._save_task.cancel()
        
        # Schedule new save task
        self._save_task = asyncio.create_task(self._save_debounced(data))
    
    async def save(self, data: Dict[str, Any], immediate: bool = False) -> bool:
        """
        Save data to file.
        
        Args:
            data: The data to save
            immediate: If True, save immediately. If False, use debouncing.
            
        Returns:
            True if immediate save was successful, None if debounced
        """
        if immediate:
            return await self.save_immediate(data)
        else:
            self.schedule_save(data)
            return None
