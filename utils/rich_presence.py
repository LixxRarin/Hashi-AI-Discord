"""
Discord Rich Presence Manager for Hashi AI Bot

This module manages Discord Rich Presence (RPC) that appears on the profile
of the user running the bot.
"""

import asyncio
import time
from typing import Optional, Dict, Any

import utils.func as func


class RichPresenceManager:
    """Manages Discord Rich Presence for the bot."""
    
    def __init__(self, bot):
        """
        Initialize the Rich Presence Manager.
        
        Args:
            bot: The Discord bot instance
        """
        self.bot = bot
        self.rpc = None
        self.config = None
        self.start_time = int(time.time())
        self.update_task = None
        self.connected = False
        self.application_id = None
        
        # Load configuration
        self._load_config()
    
    def _load_config(self) -> None:
        """Load Rich Presence configuration from config.yml."""
        try:
            config_yaml = func.config_yaml
            self.config = config_yaml.get("RichPresence", {})
            
            if not self.config:
                func.log.debug("No RichPresence configuration found in config.yml")
                self.config = {"enabled": False}
        except Exception as e:
            func.log.warning(f"Failed to load RichPresence config: {e}")
            self.config = {"enabled": False}
    
    def is_enabled(self) -> bool:
        """Check if Rich Presence is enabled in configuration."""
        return self.config.get("enabled", False)
    
    async def connect(self) -> bool:
        """
        Connect to Discord Rich Presence.
        
        Returns:
            True if connection successful, False otherwise
        """
        if not self.is_enabled():
            func.log.debug("Rich Presence is disabled in config.yml")
            return False
        
        self.application_id = self.config.get("application_id", "").strip()
        if not self.application_id:
            func.log.warning(
                "Rich Presence is enabled but no application_id provided. "
                "Create a Discord Application at https://discord.com/developers/applications"
            )
            return False
        
        try:
            # Import discord-rpc (might not be installed)
            try:
                import discordrpc
                self.discordrpc = discordrpc  # Store for reconnection
            except ImportError:
                func.log.warning(
                    "discord-rpc library not found. Install it with: pip install discord-rpc"
                )
                return False
            
            # Initialize RPC connection (connects automatically)
            # output=False silences the library's internal logs
            loop = asyncio.get_event_loop()
            self.rpc = await loop.run_in_executor(
                None,
                lambda: discordrpc.RPC(app_id=int(self.application_id), output=False)
            )
            
            self.connected = True
            
            func.log.info("Discord Rich Presence connected successfully!")

            # Initial presence update
            await self.update_presence()
            
            # Start update loop
            await self.start_update_loop()
            
            return True
            
        except Exception as e:
            func.log.warning(f"Failed to connect to Discord RPC: {e}")
            func.log.debug(
                "Make sure Discord is running and the application_id is correct. "
                "The bot will continue running without Rich Presence."
            )
            self.connected = False
            return False
    
    async def reconnect(self) -> bool:
        """
        Attempt to reconnect to Discord RPC.
        
        Returns:
            True if reconnection successful, False otherwise
        """
        if not self.discordrpc or not self.application_id:
            return False
        
        try:
            func.log.info("Attempting to reconnect Discord Rich Presence...")
            
            # Close old connection if exists
            if self.rpc:
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self.rpc.disconnect)
                except:
                    pass
            
            # Create new connection (connects automatically)
            loop = asyncio.get_event_loop()
            self.rpc = await loop.run_in_executor(
                None,
                lambda: self.discordrpc.RPC(app_id=int(self.application_id), output=False)
            )
            
            self.connected = True
            func.log.info("Discord Rich Presence reconnected successfully!")
            
            # Update presence immediately
            await self.update_presence()
            
            return True
            
        except Exception as e:
            func.log.warning(f"Failed to reconnect Discord RPC: {e}")
            self.connected = False
            return False
    
    def _get_dynamic_data(self) -> Dict[str, Any]:
        """
        Collect dynamic data from the bot for variable substitution.
        
        Returns:
            Dictionary with dynamic values
        """
        try:
            # Count servers
            server_count = len(self.bot.guilds)
            
            # Count total AIs and channels with AIs
            ai_count = 0
            channel_count = 0
            
            for server_id, server_data in func.session_cache.items():
                channels = server_data.get("channels", {})
                for channel_id, channel_data in channels.items():
                    if channel_data:  # Channel has AIs
                        channel_count += 1
                        ai_count += len(channel_data)
            
            # Get version
            try:
                with open("version.txt", "r") as f:
                    version = f.read().strip()
            except:
                version = "Unknown"
            
            # Calculate uptime
            uptime_seconds = int(time.time() - self.start_time)
            hours = uptime_seconds // 3600
            minutes = (uptime_seconds % 3600) // 60
            uptime = f"{hours:02d}:{minutes:02d}"
            
            return {
                "server_count": server_count,
                "ai_count": ai_count,
                "channel_count": channel_count,
                "version": version,
                "uptime": uptime
            }
        except Exception as e:
            func.log.debug(f"Error collecting dynamic data: {e}")
            return {
                "server_count": 0,
                "ai_count": 0,
                "channel_count": 0,
                "version": "Unknown",
                "uptime": "00:00"
            }
    
    def _format_text(self, text: str, data: Dict[str, Any]) -> str:
        """
        Format text by replacing variables with dynamic values.
        
        Args:
            text: Text with variables like {server_count}
            data: Dictionary with variable values
        
        Returns:
            Formatted text with variables replaced
        """
        if not text:
            return ""
        
        try:
            return text.format(**data)
        except KeyError as e:
            func.log.warning(f"Unknown variable in RichPresence text: {e}")
            return text
        except Exception as e:
            func.log.debug(f"Error formatting RichPresence text: {e}")
            return text
    
    async def update_presence(self) -> bool:
        """
        Update the Rich Presence with current data.
        
        Returns:
            True if update successful, False otherwise
        """
        if not self.connected or not self.rpc:
            return False
        
        try:
            # Get dynamic data
            data = self._get_dynamic_data()
            
            # Format text fields
            details = self._format_text(self.config.get("details", ""), data)
            state = self._format_text(self.config.get("state", ""), data)
            
            # Prepare update parameters
            update_params = {}
            
            # Add activity type (Playing, Watching, Listening, Competing)
            activity_type_str = self.config.get("activity_type", "").lower()
            if activity_type_str:
                try:
                    from discordrpc import Activity
                    activity_type_map = {
                        "playing": Activity.Playing,
                        "listening": Activity.Listening,
                        "watching": Activity.Watching,
                        "competing": Activity.Competing
                    }
                    if activity_type_str in activity_type_map:
                        update_params["act_type"] = activity_type_map[activity_type_str]
                except Exception as e:
                    func.log.debug(f"Failed to set activity type: {e}")
            
            # Add status_display_type (controls which field shows in status)
            status_display_str = self.config.get("status_display_type", "").lower()
            if status_display_str:
                try:
                    from discordrpc import StatusDisplay
                    status_display_map = {
                        "name": StatusDisplay.Name,
                        "state": StatusDisplay.State,
                        "details": StatusDisplay.Details
                    }
                    if status_display_str in status_display_map:
                        update_params["status_type"] = status_display_map[status_display_str]
                except Exception as e:
                    func.log.debug(f"Failed to set status display type: {e}")
            
            # Add details and state
            if details:
                update_params["details"] = details
                # Add clickable URL for details (NOW WORKS with discord-rpc!)
                details_url = self.config.get("details_url", "").strip()
                if details_url:
                    update_params["details_url"] = details_url
            
            if state:
                update_params["state"] = state
                # Add clickable URL for state (NOW WORKS with discord-rpc!)
                state_url = self.config.get("state_url", "").strip()
                if state_url:
                    update_params["state_url"] = state_url
            
            # Add timer if enabled
            if self.config.get("show_timer", False):
                update_params["ts_start"] = self.start_time
            
            # Add buttons (max 2) - discord-rpc uses Button objects
            buttons_config = self.config.get("buttons", [])
            if buttons_config and isinstance(buttons_config, list):
                try:
                    from discordrpc import Button
                    valid_buttons = []
                    for btn in buttons_config[:2]:  # Max 2 buttons
                        if isinstance(btn, dict) and "label" in btn and "url" in btn:
                            label = btn["label"].strip()
                            url = btn["url"].strip()
                            if label and url:
                                valid_buttons.append(Button(label, url))
                    
                    if valid_buttons:
                        update_params["buttons"] = valid_buttons
                except Exception as e:
                    func.log.debug(f"Failed to set buttons: {e}")
            
            # Add large image
            large_image = self.config.get("large_image", "").strip()
            if large_image:
                update_params["large_image"] = large_image
                
                large_text = self._format_text(
                    self.config.get("large_text", ""), data
                )
                if large_text:
                    update_params["large_text"] = large_text
                
                # Add clickable URL for large image (NOW WORKS with discord-rpc!)
                large_url = self.config.get("large_url", "").strip()
                if large_url:
                    update_params["large_url"] = large_url
            
            # Add small image
            small_image = self.config.get("small_image", "").strip()
            if small_image:
                update_params["small_image"] = small_image
                
                small_text = self._format_text(
                    self.config.get("small_text", ""), data
                )
                if small_text:
                    update_params["small_text"] = small_text
                
                # Add clickable URL for small image (NOW WORKS with discord-rpc!)
                small_url = self.config.get("small_url", "").strip()
                if small_url:
                    update_params["small_url"] = small_url
            
            # Update presence using discord-rpc's set_activity method
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.rpc.set_activity(**update_params))
            
            return True
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check if it's a disconnection error
            if "pipe" in error_msg or "closed" in error_msg or "discord" in error_msg:
                func.log.warning("Discord RPC disconnected. Attempting to reconnect...")
                self.connected = False
                
                # Try to reconnect
                reconnected = await self.reconnect()
                if reconnected:
                    return True
                else:
                    func.log.warning("Failed to reconnect. Will retry on next update.")
                    return False
            else:
                func.log.warning(f"Failed to update Rich Presence: {e}")
                return False
    
    async def start_update_loop(self) -> None:
        """Start the automatic update loop."""
        if self.update_task and not self.update_task.done():
            func.log.debug("Update loop already running")
            return
        
        self.update_task = asyncio.create_task(self._update_loop())
        func.log.debug("Rich Presence update loop started")
    
    async def _update_loop(self) -> None:
        """Background task that periodically updates the Rich Presence."""
        update_interval = self.config.get("update_interval", 60)
        
        # Ensure minimum interval to avoid rate limits
        if update_interval < 15:
            func.log.warning(
                f"RichPresence update_interval ({update_interval}s) is too low. "
                "Using minimum of 15 seconds to avoid rate limits."
            )
            update_interval = 15
        
        while self.is_enabled():
            try:
                await asyncio.sleep(update_interval)
                
                # Try to update, reconnect if needed
                if not self.connected:
                    await self.reconnect()
                else:
                    await self.update_presence()
                    
            except asyncio.CancelledError:
                func.log.debug("Rich Presence update loop cancelled")
                break
            except Exception as e:
                func.log.warning(f"Error in Rich Presence update loop: {e}")
                # Continue loop even if update fails
    
    async def stop(self) -> None:
        """Stop Rich Presence and disconnect."""
        if not self.connected:
            return
        
        try:
            # Cancel update loop
            if self.update_task and not self.update_task.done():
                self.update_task.cancel()
                try:
                    await self.update_task
                except asyncio.CancelledError:
                    pass
            
            # Disconnect RPC
            if self.rpc:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self.rpc.disconnect)
                func.log.info("Discord Rich Presence disconnected")
            
            self.connected = False
            self.rpc = None
            
        except Exception as e:
            func.log.warning(f"Error stopping Rich Presence: {e}")


# Global instance
_rpc_manager: Optional[RichPresenceManager] = None


def get_rpc_manager() -> Optional[RichPresenceManager]:
    """Get the global RichPresenceManager instance."""
    return _rpc_manager


def set_rpc_manager(manager: RichPresenceManager) -> None:
    """Set the global RichPresenceManager instance."""
    global _rpc_manager
    _rpc_manager = manager
