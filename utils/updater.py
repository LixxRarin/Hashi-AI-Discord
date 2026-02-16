import json
import os
import sys
import time
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from colorama import Fore, init, Style
from packaging import version

import utils.func as func
from utils.config_updater import ConfigManager

# Initialize colorama for cross-platform colored output
init(autoreset=True)

# Ensure version.txt exists
if not os.path.exists("version.txt"):
    with open("version.txt", "w", encoding="utf-8") as file:
        file.write("1.2.1\n")


def update_session_file(file_path: Optional[str] = None) -> None:
    """
    Update the session.json file:
    - Add missing keys to existing AI sessions (with default values)
    - Remove deprecated keys from sessions
    - Clean up null channel data
    - Remove obsolete LLM parameters from config (now in api_connections.json)
    - DO NOT overwrite existing values
    """
    # Get file path from config if not provided
    if file_path is None:
        file_path = func.get_session_file()

    # Check if the session file exists; if not, create an empty session data dictionary
    if not os.path.exists(file_path):
        func.log.info(f"Session file '{file_path}' does not exist. Creating a new file.")
        session_data = {}
    else:
        # Load existing session data
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                session_data = json.load(f)
            except json.JSONDecodeError:
                func.log.warning("Error: JSON file is not properly formatted. Creating a new empty session data.")
                session_data = {}

    # Iterate over each server in the session data
    for server_id, server_data in session_data.items():
        func.log.debug(f"Processing server: {server_id}")
        
        # Only update if the server has a 'channels' key
        if "channels" not in server_data:
            func.log.debug(f"No channels found for server: {server_id}. Skipping.")
            continue
            
        channels = server_data["channels"]
        channels_to_remove = []
        
        for channel_id, channel_data in channels.items():
            # If channel data is null, mark it for removal
            if channel_data is None:
                func.log.info(f"Channel {channel_id} has null data. It will be removed.")
                channels_to_remove.append(channel_id)
                continue
            
            func.log.debug(f"Processing channel: {channel_id}")
            
            # Process each AI in the channel
            for ai_name, ai_data in channel_data.items():
                if ai_data is None:
                    continue
                    
                func.log.debug(f"Processing AI '{ai_name}' in channel: {channel_id}")
                
                # Ensure provider field exists
                if "provider" not in ai_data:
                    detected_provider = _detect_provider_from_session(ai_data)
                    ai_data["provider"] = detected_provider
                    func.log.info(f"Set provider to '{detected_provider}' for AI '{ai_name}'")
                
                # Get default model based on the AI's provider
                ai_provider = ai_data.get("provider", "openai")
                default_ai_model = func.get_default_ai_session(provider=ai_provider)
                
                # Only add missing keys, do not overwrite existing values
                for key, default_value in default_ai_model.items():
                    if key not in ai_data:
                        ai_data[key] = default_value() if callable(default_value) else default_value
                    # For nested config dict, sync keys but do not overwrite existing values
                    if key == "config" and isinstance(ai_data.get(key), dict):
                        for ckey, cdefault in default_ai_model["config"].items():
                            if ckey not in ai_data["config"]:
                                ai_data["config"][ckey] = cdefault
                
                # Preserve fields from the API connections system and character cards
                preserved_fields = {"api_connection", "character_card", "character_card_name"}
                
                # Remove extra keys not in the default model (but preserve special fields)
                keys_to_keep = set(default_ai_model.keys()) | preserved_fields
                for key in list(ai_data.keys()):
                    if key not in keys_to_keep:
                        func.log.debug(f"Removing deprecated key '{key}' from AI '{ai_name}'")
                        del ai_data[key]
                
                # Clean up config: remove obsolete LLM parameters (now in api_connections.json)
                if "config" in ai_data and isinstance(ai_data["config"], dict):
                    config_keys_to_keep = set(default_ai_model["config"].keys())
                    llm_params_to_remove = {
                        "max_tokens", "temperature", "top_p",
                        "frequency_penalty", "presence_penalty",
                        "context_size", "think_switch", "think_depth",
                        "hide_thinking_tags", "thinking_tag_patterns"
                    }
                    
                    for ckey in list(ai_data["config"].keys()):
                        if ckey not in config_keys_to_keep:
                            if ckey in llm_params_to_remove:
                                func.log.info(
                                    f"Removing LLM parameter '{ckey}' from AI '{ai_name}' config "
                                    f"(now managed in api_connections.json)"
                                )
                            else:
                                func.log.debug(f"Removing deprecated config key '{ckey}' from AI '{ai_name}'")
                            del ai_data["config"][ckey]
                
                # Warning for sessions without api_connection
                if not ai_data.get("api_connection"):
                    func.log.warning(
                        f"AI '{ai_name}' in channel {channel_id} has no api_connection. "
                        f"Please create an API connection with /new_api and configure with /setup."
                    )
                        
        # Remove channels that had null data
        for channel_id in channels_to_remove:
            del channels[channel_id]

    # Write the updated session data back to the JSON file
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=4, ensure_ascii=False)

    func.log.debug("Session file updated successfully.")


def _detect_provider_from_session(session_data: Dict[str, Any]) -> str:
    """
    Detect the provider from session data based on model name or base_url.
    
    Args:
        session_data: Session data dictionary
        
    Returns:
        str: Detected provider name ("openai", "deepseek", etc.)
    """
    # Check base_url for provider hints
    base_url = session_data.get("base_url", "")
    if base_url:
        if "deepseek" in base_url.lower():
            return "deepseek"
    
    # Check model name for provider hints
    model = session_data.get("model", "")
    if model:
        if "deepseek" in model.lower():
            return "deepseek"
        if "gpt" in model.lower() or "o1" in model.lower():
            return "openai"
    
    # Default to openai as the most common provider
    func.log.debug("Could not detect provider from session data, defaulting to 'openai'")
    return "openai"


class AutoUpdater:
    """
    Automatic updater for Python source code via Git.
    
    Checks for updates on a specified branch and applies them automatically
    using git fetch and reset operations. Only supports git-based updates
    for Python source code.
    """
    
    def __init__(self, repo_url: str, current_version: str, branch: str = "main"):
        """
        Initialize the AutoUpdater for git-based updates.

        :param repo_url: Git repository URL (e.g., git@github.com:username/repo.git)
        :param current_version: Current version of the program (e.g., "1.0.2")
        :param branch: Branch to check for updates (default: "main")
        """
        self.repo_url = repo_url
        self.current_version = current_version
        self.branch = branch
        self.script_dir = Path(__file__).parent.parent.resolve()  # Go up one level from utils/

    def check_and_update(self, force: bool = False) -> None:
        """
        Check for updates and apply them if available via git.
        
        :param force: Force update even if no new version is detected
        """
        if os.environ.get("SKIP_AUTOUPDATE") == "1":
            func.log.info("Skipping update check to avoid infinite restart loop.")
            return

        if force:
            func.log.info("Forcing source code update...")
            try:
                if not (self.script_dir / '.git').exists():
                    func.log.error("Cannot force update: Not a git repository.")
                    return
                subprocess.run(['git', 'fetch', 'origin', self.branch],
                               check=True, cwd=self.script_dir, capture_output=True)
                if self._update_from_commit():
                    func.log.info("Source update applied; restarting program.")
                    self._restart_program()
            except subprocess.CalledProcessError as e:
                func.log.error(f"Failed to fetch before forced update: {e.stderr.decode().strip() if e.stderr else e}")
            return

        update_available = self._is_source_update_available()
        if update_available:
            func.log.info("New source code version detected. Updating...")
            if self._update_from_commit():
                func.log.info("Source update applied; restarting program.")
                self._restart_program()
        else:
            func.log.info("Source code is up to date.")

    def _is_source_update_available(self) -> bool:
        """
        Check if a source code update is available via git.
        
        :return: True if update is available, False otherwise
        """
        try:
            if not (self.script_dir / '.git').exists():
                func.log.warning("Not a git repository, cannot check for updates.")
                return False

            # Fetch the latest info from the remote without applying changes
            subprocess.run(['git', 'fetch', 'origin', self.branch],
                           check=True, cwd=self.script_dir, capture_output=True)

            # Get the local commit hash
            local_hash_proc = subprocess.run(
                ['git', 'rev-parse', 'HEAD'], check=True, cwd=self.script_dir, capture_output=True, text=True)
            local_hash = local_hash_proc.stdout.strip()

            # Get the remote commit hash
            remote_hash_proc = subprocess.run(
                ['git', 'rev-parse', f'origin/{self.branch}'], check=True, cwd=self.script_dir, capture_output=True, text=True)
            remote_hash = remote_hash_proc.stdout.strip()

            # Compare hashes
            if local_hash != remote_hash:
                func.log.debug(
                    f"Update available: Local hash {local_hash[:7]} != Remote hash {remote_hash[:7]}")
                return True

            return False
        except subprocess.CalledProcessError as e:
            func.log.error(
                f"Failed to check for source update: {e.stderr.decode().strip() if e.stderr else e}")
            return False
        except Exception as e:
            func.log.error(
                f"An unexpected error occurred while checking for source update: {e}")
            return False

    def _update_from_commit(self) -> bool:
        """
        Update source code from git commit.
        
        :return: True if successful, False otherwise
        """
        try:
            subprocess.run(['git', 'reset', '--hard', f'origin/{self.branch}'],
                           check=True, cwd=self.script_dir, capture_output=True)
            func.log.info("Code updated via Git (branch: %s)", self.branch)
            return True
        except Exception as e:
            func.log.error("Source update failed: %s", e)
            return False

    def _restart_program(self) -> None:
        """
        Restart the Python program after update.
        """
        new_env = os.environ.copy()
        new_env["SKIP_AUTOUPDATE"] = "1"
        subprocess.Popen([sys.executable] + sys.argv, env=new_env)
        sys.exit(0)


def return_version() -> str:
    """
    Read and return the current version from version.txt.
    
    :return: Version string, defaults to "1.2.0" if file not found
    """
    try:
        with open("version.txt", 'r', encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        func.log.warning("version.txt not found, returning default version")
        return "1.2.0"
    except Exception as e:
        func.log.error(f"Error reading version.txt: {e}")
        return "1.2.0"


def startup_screen() -> None:
    """
    Display the startup banner with project information.
    Shows dynamically registered AI providers from the registry.
    """
    # Clear screen (cross-platform)
    os.system("cls" if os.name == "nt" else "clear")
    
    # Try to get dynamic provider information
    provider_info = _get_provider_info()
    
    # Build and display banner (title and labels in bold)
    banner = f"""{Style.BRIGHT}{Fore.WHITE}「 Project Hashi: Powering Discord Bot Personalities 」{Style.RESET_ALL}
{Fore.YELLOW}▶ {Style.BRIGHT}{Fore.WHITE}Description:{Style.RESET_ALL} Multi-provider AI Discord bot
{provider_info}
{Fore.YELLOW}▶ {Style.BRIGHT}{Fore.WHITE}Creator:{Style.RESET_ALL} LixxRarin
{Fore.YELLOW}▶ {Style.BRIGHT}{Fore.WHITE}GitHub:{Style.RESET_ALL} https://github.com/LixxRarin/Hashi-AI-Discord
{Fore.YELLOW}▶ {Style.BRIGHT}{Fore.WHITE}Version:{Style.RESET_ALL} {return_version()}
"""
    # Display banner to console
    sys.stdout.write(banner + "\n")
    sys.stdout.flush()
    time.sleep(2)


def _get_provider_info() -> str:
    """
    Get formatted provider information from the registry.
    
    :return: Formatted provider info string
    """
    try:
        # Import AI module to ensure providers are registered
        import AI
        from AI.provider_registry import get_registry
        
        registry = get_registry()
        providers_metadata = registry.get_all_metadata()
        provider_count = registry.get_provider_count()
        
        # Build provider list with colors and icons
        if providers_metadata and provider_count > 0:
            provider_parts = []
            color_map = {
                "green": Fore.GREEN,
                "blue": Fore.CYAN,
                "cyan": Fore.CYAN,
                "red": Fore.RED,
                "magenta": Fore.MAGENTA,
                "yellow": Fore.YELLOW,
                "white": Fore.WHITE,
                "orange": Fore.LIGHTYELLOW_EX,
                "purple": Fore.LIGHTMAGENTA_EX,
            }
            
            for name, metadata in providers_metadata.items():
                color = color_map.get(metadata.color.lower(), Fore.WHITE)
                icon = metadata.icon if metadata.icon else "●"
                display_name = metadata.display_name
                provider_parts.append(f"{color}{icon} {display_name}{Fore.WHITE}")
            
            providers_line = ", ".join(provider_parts)
            return f"{Fore.YELLOW}▶ {Style.BRIGHT}{Fore.WHITE}Providers{Style.RESET_ALL} ({provider_count}): {providers_line}"
        else:
            return f"{Fore.YELLOW}▶ {Style.BRIGHT}{Fore.WHITE}Providers:{Style.RESET_ALL} {Fore.RED}None registered{Fore.WHITE}"
            
    except Exception as e:
        # Fallback if registry is not available
        func.log.debug(f"Could not load provider registry for startup screen: {e}")
        # Return a simple static list as fallback
        return f"{Fore.YELLOW}▶ {Style.BRIGHT}{Fore.WHITE}Providers:{Style.RESET_ALL} {Fore.GREEN}🟢 OpenAI{Fore.WHITE}, {Fore.CYAN}🐋 DeepSeek{Fore.WHITE}"



async def boot() -> None:
    """
    Main boot sequence: display banner, update files, and check for updates.
    """
    startup_screen()
    update_session_file()

    # Manage and update the configuration file
    config_manager = ConfigManager()
    await config_manager.check_and_update()

    # Check for force update flag from command line
    force_update = "--force-update" in sys.argv

    # Initialize AutoUpdater using configuration data
    updater = AutoUpdater(
        repo_url=func.config_yaml["Options"]["repo_url"],
        current_version=return_version(),
        branch=func.config_yaml["Options"].get("repo_branch", "main")
    )
    # Run update if auto_update is enabled or if forced
    if func.config_yaml["Options"].get("auto_update", False) or force_update:
        updater.check_and_update(force=force_update)


# Only run boot sequence if this file is executed directly
if __name__ == "__main__":
    asyncio.run(boot())
