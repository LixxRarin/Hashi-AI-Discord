import os

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from packaging import version

import utils.func as func

# Set up ruamel.yaml in round-trip mode (preserves order and comments)
yaml = YAML(typ='rt')
yaml.preserve_quotes = True
yaml.encoding = "utf-8"

# Default configuration content
DEFAULT_CONFIG_CONTENT = r"""version: "1.4.1" # Don't touch here

# Discord Bot Configuration
Discord:
  token: "YOUR_DISCORD_BOT_TOKEN"
  # This is the token used to authenticate your bot with Discord.
  # Keep this token secure and do not share it publicly.

# Data Files Configuration
Data:
  session_file: "data/session.json"
  # Path to the file where session data is stored.
  # This file stores the active AI sessions for each channel.

  conversations_file: "data/conversations.json"
  # Path to the unified conversations file.
  # This file stores ALL conversation history, message tracking, and generation cache.
  # Replaces: conversation_history.json, message_tracking.json, generation_cache.json

  api_connections_file: "data/api_connections.json"
  # Path to the file where API connections are stored.
  # This file stores the API keys, models, and LLM parameters for each connection.

  character_cards_file: "data/character_cards.json"
  # Path to the file where character cards registry is stored.
  # This file stores the mapping of character cards to AIs.

  debug_config_file: "data/debug_config.json"
  # Path to the file where debug configuration is stored.
  # This file stores the debug settings for each server.

# Bot Interaction Settings
Options:
  
  auto_update: true
  # If true, the program will check for a new update every time it starts up.
  # For releases or commits, this depends on how you run the bot.
  
  repo_url: "https://github.com/LixxRarin/Hashi-AI-Discord.git"
  # This is the repository where the program will check and update.
  # Only touch this if you know what you're doing here!

  repo_branch: "main"
  # This is the branch where the program will check and update.
  # Only touch this if you know what you're doing here!

  debug_mode: false
  # Enable debug mode for troubleshooting.
  # When true, the bot will log detailed information about its processes in the console.
  # This mode should be off in production to avoid excessive logging.

# Discord Rich Presence Configuration
# This feature displays custom status on YOUR Discord profile (the user running the bot)
# Uses discord-rpc library for full feature support including clickable URLs
# To use this feature, you need to create a Discord Application at:
# https://discord.com/developers/applications
RichPresence:
  
  enabled: false
  # Enable or disable Rich Presence.
  # If disabled, no RPC will be shown on your profile.
  
  application_id: ""
  # Your Discord Application ID (Client ID) from the Developer Portal.
  # Create an application at: https://discord.com/developers/applications
  
  # Activity Configuration
  activity_type: "playing"
  # Type of activity shown in Rich Presence.
  # Options: "playing", "watching", "listening", "competing"
  # Examples:
  #   "playing" -> "Playing {details}"
  #   "watching" -> "Watching {details}"
  #   "listening" -> "Listening to {details}"
  #   "competing" -> "Competing in {details}"
  
  status_display_type: "name"
  # Controls which field is displayed in the user's status bar.
  # Options: "name", "state", "details"
  # - "name": Shows the application name from Developer Portal (default)
  # - "state": Shows the state field
  # - "details": Shows the details field
  
  # Customizable text fields (supports dynamic variables)
  # Available variables: {server_count}, {ai_count}, {channel_count}, {version}, {uptime}
  details: "Running Hashi AI Bot"
  # First line of text shown in your Rich Presence.
  
  details_url: ""
  # Make the details text clickable (optional).
  # When users click the details text, this URL will open in their browser.
  # Example: "https://github.com/LixxRarin/Hashi-AI-Discord"
  
  state: "Serving {server_count} servers | {ai_count} AIs active"
  # Second line of text shown in your Rich Presence.
  # This example shows dynamic server and AI counts.
  
  state_url: ""
  # Make the state text clickable (optional).
  # When users click the state text, this URL will open in their browser.
  # Example: "https://discord.gg/YOUR_INVITE"
  
  show_timer: true
  # Show elapsed time counter (e.g., "02:34:15 elapsed").
  # This displays how long the bot has been running.
  
  # Buttons (maximum 2 allowed by Discord)
  # Each button needs a label and a valid HTTPS URL
  # Important: You cannot click or see your own buttons, only other users can see and click them!
  buttons:
    - label: "GitHub Repository"
      url: "https://github.com/LixxRarin/Hashi-AI-Discord"
    # - label: "Join Discord"
    #   url: "https://discord.gg/YOUR_INVITE"
  
  # Images (optional - must be uploaded to Discord Developer Portal first)
  # Go to your application > Rich Presence > Art Assets to upload images
  large_image: ""
  # Name of the large image asset (leave empty to disable).
  
  large_text: "Hashi AI Discord Bot v{version}"
  # Hover text for the large image (supports variables).
  
  large_url: ""
  # Make the large image clickable (optional).
  # When users click the image, this URL will open in their browser.
  # Example: "https://github.com/LixxRarin/Hashi-AI-Discord"
  
  small_image: ""
  # Name of the small image asset (leave empty to disable).
  
  small_text: ""
  # Hover text for the small image (supports variables).
  
  small_url: ""
  # Make the small image clickable (optional).
  # When users click the image, this URL will open in their browser.
  
  update_interval: 60
  # How often to update the Rich Presence (in seconds).
  # Updates dynamic variables like server count and AI count.
  # Minimum recommended: 15 seconds to avoid rate limits.
"""


def merge_ordered(user_cfg, default_cfg):
    """
    Merges two CommentedMaps while preserving the order defined in default_cfg.

    For each key in default_cfg:
      - If the key exists in user_cfg, use its value.
      - If both values are dictionaries, merge them recursively.
      - Otherwise, fall back to the default value.

    Extra keys present in user_cfg that are not in default_cfg are discarded.

    Additionally, comment attributes (if present) are preserved from either configuration.
    """
    merged = CommentedMap()
    for key, default_val in default_cfg.items():
        # If the user configuration contains the key, process its value
        if key in user_cfg:
            user_val = user_cfg[key]
            # If both default and user values are dictionaries, merge them recursively
            if isinstance(default_val, dict) and isinstance(user_val, dict):
                merged[key] = merge_ordered(user_val, default_val)
            else:
                # Use the user's value if it's not a dictionary or cannot be merged recursively
                merged[key] = user_val
        else:
            # If the key is missing in the user configuration, use the default value
            merged[key] = default_val

        # Preserve comment attributes if available in user_cfg; otherwise, fall back to default_cfg comments
        if hasattr(user_cfg, 'ca') and key in user_cfg.ca.items:
            merged.ca.items[key] = user_cfg.ca.items.get(key)
        elif hasattr(default_cfg, 'ca') and key in default_cfg.ca.items:
            merged.ca.items[key] = default_cfg.ca.items.get(key)
    return merged


class ConfigManager:
    def __init__(self, config_file="config.yml"):
        """
        Initializes the configuration manager.

        - Loads the default configuration from DEFAULT_CONFIG_CONTENT.
        - Attempts to load the user configuration from the given file.
        """
        self.config_file = config_file
        self.default_config = yaml.load(DEFAULT_CONFIG_CONTENT)
        self.user_config = self.load_user_config()

    def load_user_config(self):
        """
        Loads the user configuration from the file.

        Returns:
            The parsed configuration if the file exists and is valid,
            otherwise returns None.
        """
        if not os.path.exists(self.config_file):
            return None
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return yaml.load(f)
        except Exception as e:
            # Log error if loading the configuration fails
            func.log.error("Error loading user configuration: %s", e)
            return None

    def is_version_outdated(self):
        """
        Checks whether the user configuration is outdated compared to the default configuration.

        Returns:
            True if:
              - The user configuration does not have a version.
              - The user's version is less than the default version.
            False otherwise.
        """
        user_version = self.user_config.get(
            "version") if self.user_config else None
        default_version = self.default_config.get("version")
        if user_version is None:
            # Log a warning if no version is found in the user configuration
            func.log.warning(
                "No version found in user configuration. Assuming outdated.")
            return True
        return version.parse(user_version) < version.parse(default_version)

    def merge_configs(self):
        """
        Merges the user configuration with the default configuration.

        This method:
          - Preserves the order of keys as defined in the default configuration.
          - Discards any extra keys that are not present in the default configuration.
          - Updates the root "version" key to match the default configuration.
        """
        if self.user_config is None:
            return self.default_config
        merged = merge_ordered(self.user_config, self.default_config)
        # Ensure the "version" key is updated to the default version
        merged["version"] = self.default_config.get("version")
        return merged

    async def check_and_update(self):
        """
        Checks if the configuration file exists and whether it is up-to-date.

        This method performs the following:
          - If the configuration file does not exist, it creates one using the default configuration.
          - If the user configuration is outdated (based on version comparison), it updates the file.
          - Logs all actions including successes, warnings, and errors.
        """
        if self.user_config is None:
            func.log.warning(
                "Configuration file '%s' not found. Creating a new one...", self.config_file)
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    yaml.dump(self.default_config, f)
                func.log.info(
                    "Configuration file '%s' created successfully!", self.config_file)
            except Exception as e:
                func.log.critical(
                    "Failed to create configuration file: %s", e)
            return

        if self.is_version_outdated():
            func.log.warning("Updating configuration '%s' to version %s",
                             self.config_file, self.default_config.get("version"))
            updated_config = self.merge_configs()
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    yaml.dump(updated_config, f)
                func.log.info(
                    "Configuration file '%s' updated successfully!", self.config_file)
            except Exception as e:
                func.log.critical(
                    "Failed to update configuration file: %s", e)
        else:
            func.log.info(
                "Configuration file '%s' is up-to-date.", self.config_file)