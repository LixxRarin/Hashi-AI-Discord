"""
Lorebook Processor

Handles lorebook entry activation and processing according to
Character Card V3 specification.
"""

import logging
import re
from typing import Dict, Any, List, Callable, Optional

log = logging.getLogger(__name__)


class LorebookProcessor:
    """
    Processes lorebook entries for character cards.
    """
    
    def __init__(self):
        """Initialize the lorebook processor."""
        pass
    
    def get_active_entries(
        self,
        lorebook: Dict[str, Any],
        recent_messages: List[str],
        scan_depth: Optional[int] = None,
        token_budget: Optional[int] = None,
        count_tokens_fn: Optional[Callable[[str, str], int]] = None,
        model: str = "gpt-3.5-turbo",
        hidden_keys: Optional[List[str]] = None
    ) -> List[str]:
        """
        Get active lorebook entries based on recent messages.
        
        Args:
            lorebook: Lorebook object from character card
            recent_messages: List of recent messages to scan
            scan_depth: Number of messages to scan (None = use lorebook default)
            token_budget: Token limit for entries (None = use lorebook default)
            count_tokens_fn: Function to count tokens
            model: Model name for token counting
            hidden_keys: Hidden keys from {{hidden_key:X}} CBS for recursive scanning
            
        Returns:
            List of entry contents to include in prompt
        """
        if not lorebook or not lorebook.get("entries"):
            return []
        
        try:
            # Get scan depth
            if scan_depth is None:
                scan_depth = lorebook.get("scan_depth", 10)
            
            # Get token budget
            if token_budget is None:
                token_budget = lorebook.get("token_budget", 2000)
            
            # Combine recent messages for scanning
            messages_to_scan = recent_messages[-scan_depth:] if scan_depth > 0 else recent_messages
            scan_text = "\n".join(messages_to_scan).lower()
            
            # Add hidden keys to scan text if recursive scanning is enabled
            if hidden_keys and lorebook.get("recursive_scanning", False):
                scan_text += "\n" + "\n".join(hidden_keys).lower()
                log.debug(f"Added {len(hidden_keys)} hidden keys for recursive lorebook scanning")
            
            # Find active entries
            active_entries = []
            
            for entry in lorebook["entries"]:
                if not entry.get("enabled", True):
                    continue
                
                # Check if entry should be activated
                if self._should_activate(entry, scan_text):
                    active_entries.append(entry)
            
            # Sort by insertion_order
            active_entries.sort(key=lambda e: e.get("insertion_order", 0))
            
            # Apply token budget if count function provided
            if count_tokens_fn and token_budget:
                active_entries = self._apply_token_budget(
                    active_entries,
                    token_budget,
                    count_tokens_fn,
                    model
                )
            
            # Extract content
            contents = [entry["content"] for entry in active_entries if entry.get("content")]
            
            log.debug(f"Activated {len(contents)} lorebook entries")
            return contents
            
        except Exception as e:
            log.error(f"Error processing lorebook: {e}")
            return []
    
    def _should_activate(self, entry: Dict[str, Any], scan_text: str) -> bool:
        """
        Check if a lorebook entry should be activated.
        
        Args:
            entry: Lorebook entry
            scan_text: Text to scan (lowercase)
            
        Returns:
            True if entry should be activated
        """
        try:
            # Constant entries are always active
            if entry.get("constant", False):
                return True
            
            # Check if using regex
            use_regex = entry.get("use_regex", False)
            keys = entry.get("keys", [])
            
            if not keys:
                return False
            
            # Case sensitivity
            case_sensitive = entry.get("case_sensitive", False)
            
            if use_regex:
                # Regex matching
                for key in keys:
                    try:
                        flags = 0 if case_sensitive else re.IGNORECASE
                        if re.search(key, scan_text, flags=flags):
                            return True
                    except re.error as e:
                        log.warning(f"Invalid regex pattern '{key}': {e}")
                        continue
            else:
                # Simple string matching
                for key in keys:
                    search_key = key if case_sensitive else key.lower()
                    search_text = scan_text if case_sensitive else scan_text.lower()
                    
                    if search_key in search_text:
                        # Check secondary keys if selective
                        if entry.get("selective", False):
                            secondary_keys = entry.get("secondary_keys", [])
                            if secondary_keys:
                                # All secondary keys must match
                                for sec_key in secondary_keys:
                                    sec_search = sec_key if case_sensitive else sec_key.lower()
                                    if sec_search not in search_text:
                                        return False
                        return True
            
            return False
            
        except Exception as e:
            log.error(f"Error checking entry activation: {e}")
            return False
    
    def _apply_token_budget(
        self,
        entries: List[Dict[str, Any]],
        token_budget: int,
        count_tokens_fn: Callable[[str, str], int],
        model: str
    ) -> List[Dict[str, Any]]:
        """
        Apply token budget to entries, removing lowest priority if needed.
        
        Args:
            entries: List of active entries
            token_budget: Maximum tokens allowed
            count_tokens_fn: Function to count tokens
            model: Model name
            
        Returns:
            Filtered list of entries within budget
        """
        try:
            # Calculate tokens for each entry
            entries_with_tokens = []
            for entry in entries:
                content = entry.get("content", "")
                tokens = count_tokens_fn(content, model)
                entries_with_tokens.append({
                    "entry": entry,
                    "tokens": tokens
                })
            
            # Sort by priority (higher priority first)
            # If no priority field, use insertion_order (lower = higher priority)
            entries_with_tokens.sort(
                key=lambda e: (
                    -e["entry"].get("priority", 100),  # Higher priority first
                    e["entry"].get("insertion_order", 0)  # Lower insertion_order first
                )
            )
            
            # Select entries within budget
            selected = []
            total_tokens = 0
            
            for item in entries_with_tokens:
                if total_tokens + item["tokens"] <= token_budget:
                    selected.append(item["entry"])
                    total_tokens += item["tokens"]
                else:
                    log.debug(f"Skipping entry due to token budget: {total_tokens + item['tokens']} > {token_budget}")
            
            # Re-sort by insertion_order for final output
            selected.sort(key=lambda e: e.get("insertion_order", 0))
            
            return selected
            
        except Exception as e:
            log.error(f"Error applying token budget: {e}")
            return entries


# Global processor instance
_processor = LorebookProcessor()


def get_active_lorebook_entries(
    lorebook: Dict[str, Any],
    recent_messages: List[str],
    scan_depth: Optional[int] = None,
    token_budget: Optional[int] = None,
    count_tokens_fn: Optional[Callable[[str, str], int]] = None,
    model: str = "gpt-3.5-turbo",
    hidden_keys: Optional[List[str]] = None
) -> List[str]:
    """
    Get active lorebook entries.
    
    Args:
        lorebook: Lorebook object
        recent_messages: Recent messages to scan
        scan_depth: Scan depth
        token_budget: Token budget
        count_tokens_fn: Token counting function
        model: Model name
        hidden_keys: Hidden keys from {{hidden_key:X}} for recursive scanning
        
    Returns:
        List of entry contents
    """
    return _processor.get_active_entries(
        lorebook,
        recent_messages,
        scan_depth,
        token_budget,
        count_tokens_fn,
        model,
        hidden_keys
    )


def process_lorebook(
    session: Dict[str, Any],
    recent_messages: List[str],
    count_tokens_fn: Optional[Callable[[str, str], int]] = None,
    model: str = "gpt-3.5-turbo"
) -> List[str]:
    """
    Process lorebook from session character card.
    
    Args:
        session: Session data with character_card
        recent_messages: Recent messages
        count_tokens_fn: Token counting function
        model: Model name
        
    Returns:
        List of active entry contents
    """
    try:
        # Get character card from session
        card_data = session.get("character_card", {}).get("data", {})
        lorebook = card_data.get("character_book")
        
        if not lorebook:
            return []
        
        # Get config
        config = session.get("config", {})
        use_lorebook = config.get("use_lorebook", True)
        
        if not use_lorebook:
            return []
        
        # Get scan depth from config or lorebook
        scan_depth = config.get("lorebook_scan_depth") or lorebook.get("scan_depth", 10)
        
        # Get hidden keys from session (extracted during CBS processing)
        hidden_keys = session.get('_hidden_keys', [])
        
        # Get active entries
        return get_active_lorebook_entries(
            lorebook,
            recent_messages,
            scan_depth=scan_depth,
            count_tokens_fn=count_tokens_fn,
            model=model,
            hidden_keys=hidden_keys
        )
        
    except Exception as e:
        log.error(f"Error processing lorebook from session: {e}")
        return []
