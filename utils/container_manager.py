"""
Container Manager - Manages Docker containers for bash_tool

This module provides container lifecycle management for executing bash commands
in isolated Docker environments. Supports persistent and ephemeral modes.
"""

import asyncio
import io
import logging
import os
import tarfile
import time
from typing import Dict, Optional, Any, List, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime

# Docker imports with error handling
try:
    import docker
    from docker.errors import NotFound, APIError, Conflict
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None
    NotFound = Exception
    APIError = Exception
    Conflict = Exception

log = logging.getLogger(__name__)


@dataclass
class ContainerInfo:
    """Information about a managed container."""
    container_id: str
    chat_id: str
    created_at: float
    last_used: float
    command_count: int = 0
    mode: str = "persistent"  # persistent | ephemeral
    
    def update_usage(self):
        """Update last used timestamp and increment command count."""
        self.last_used = time.time()
        self.command_count += 1


class ContainerManager:
    """
    Manages Docker containers for bash command execution.
    
    Features:
    - Persistent containers per chat_id
    - Ephemeral containers (one-time use)
    - Resource limits (CPU, RAM, disk)
    - Automatic cleanup of inactive containers
    - Error handling and recovery
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the container manager.
        
        Args:
            config: Configuration dictionary with bash_tool settings
        """
        self.config = config
        self.containers: Dict[str, ContainerInfo] = {}  # chat_id -> ContainerInfo
        self.ephemeral_by_session: Dict[str, List[Tuple[str, float]]] = {}  # session_key -> [(container_id, timestamp)]
        self.docker_client = None
        self._initialized = False
        self._cleanup_task = None
        
        log.info("ContainerManager initialized")
    
    async def initialize(self):
        """Initialize Docker client and start cleanup task."""
        if self._initialized:
            return
        
        try:
            import docker
            self.docker_client = docker.from_env()
            
            # Test Docker connection (run in thread to avoid blocking)
            await asyncio.to_thread(self.docker_client.ping)
            log.info("Docker connection established")
            
            # Discover and reattach to existing containers
            await self._discover_existing_containers()
            
            # Start ephemeral cleanup loop
            if not self._cleanup_task:
                self._cleanup_task = asyncio.create_task(self._ephemeral_cleanup_loop())
                log.info("Started ephemeral container cleanup task")
            
            self._initialized = True
            
        except ImportError:
            log.error("Docker library not installed. Install with: pip install docker")
            raise RuntimeError(
                "Docker library not installed. Please install it with: pip install docker"
            )
        except Exception as e:
            log.error(f"Failed to connect to Docker: {e}")
            raise RuntimeError(
                f"Failed to connect to Docker: {e}\n"
                "Make sure Docker is installed and running.\n"
                "Windows: Install Docker Desktop and enable WSL2\n"
                "Linux: Install docker.io and start the service"
            )
    
    async def _safe_remove_container(self, container_id: str, force: bool = True) -> bool:
        """
        Safely remove a container with proper error handling.
        
        Args:
            container_id: Container ID or name
            force: Force removal even if running
            
        Returns:
            True if removed successfully, False otherwise
        """
        try:
            container = await asyncio.to_thread(self.docker_client.containers.get, container_id)
            
            # Try to stop first (ignore if already stopped)
            try:
                await asyncio.to_thread(container.stop, timeout=5)
            except NotFound:
                pass  # Container already removed
            except APIError as e:
                if "is not running" not in str(e).lower():
                    log.warning(f"Error stopping container {container_id[:12]}: {e}")
            
            # Remove with force flag
            await asyncio.to_thread(container.remove, force=force)
            log.debug(f"Container {container_id[:12]} removed successfully")
            return True
            
        except NotFound:
            log.debug(f"Container {container_id[:12]} not found (already removed)")
            return True  # Consider it success if already gone
            
        except APIError as e:
            log.error(f"Docker API error removing container {container_id[:12]}: {e}")
            return False
            
        except Exception as e:
            log.error(f"Unexpected error removing container {container_id[:12]}: {e}")
            return False
    
    async def _cleanup_orphaned_containers(self, name_pattern: str) -> int:
        """
        Remove orphaned containers matching the name pattern.
        
        Args:
            name_pattern: Container name pattern to match
            
        Returns:
            Number of containers removed
        """
        cleaned = 0
        try:
            # List all containers with our label
            filters = {"label": "managed_by=hashi-bash-tool"}
            containers = await asyncio.to_thread(
                self.docker_client.containers.list,
                all=True,
                filters=filters
            )
            
            for container in containers:
                if name_pattern in container.name:
                    log.info(f"Found orphaned container: {container.name}")
                    if await self._safe_remove_container(container.id):
                        cleaned += 1
            
            if cleaned > 0:
                log.info(f"Cleaned up {cleaned} orphaned containers")
                
        except Exception as e:
            log.warning(f"Error during orphaned container cleanup: {e}")
        
        return cleaned
    
    async def _discover_existing_containers(self):
        """
        Discover and reattach to existing persistent containers.
        
        Called during initialization to restore state after bot restart.
        This allows containers to persist across bot restarts, preserving
        installed packages and files.
        """
        try:
            # List all containers with our label
            filters = {"label": "managed_by=hashi-bash-tool"}
            containers = await asyncio.to_thread(
                self.docker_client.containers.list,
                all=True,
                filters=filters
            )
            
            discovered = 0
            restarted = 0
            removed = 0
            
            for container in containers:
                name = container.name
                
                # Only process persistent containers (skip ephemeral)
                if not name.startswith("hashi-bash-") or "ephemeral" in name:
                    continue
                
                # Extract chat_id from container name
                # Format: hashi-bash-{chat_id}
                chat_id = name.replace("hashi-bash-", "")
                
                # Check container status
                status = container.status
                
                if status == "running":
                    # Container is healthy, reattach
                    self.containers[chat_id] = ContainerInfo(
                        container_id=container.id,
                        chat_id=chat_id,
                        created_at=time.time(),  # Use current time as we don't have original
                        last_used=time.time(),
                        mode="persistent"
                    )
                    discovered += 1
                    log.info(f"Reattached to running container: {name} ({container.id[:12]})")
                    
                elif status in ["exited", "stopped"]:
                    # Container stopped, try to restart
                    try:
                        await asyncio.to_thread(container.start)
                        self.containers[chat_id] = ContainerInfo(
                            container_id=container.id,
                            chat_id=chat_id,
                            created_at=time.time(),
                            last_used=time.time(),
                            mode="persistent"
                        )
                        restarted += 1
                        log.info(f"Restarted stopped container: {name} ({container.id[:12]})")
                    except Exception as e:
                        log.warning(f"Failed to restart container {name}: {e}, will remove")
                        await self._safe_remove_container(container.id)
                        removed += 1
                        
                else:
                    # Container in bad state (dead, error, etc.), remove it
                    log.warning(f"Removing container in bad state: {name} (status: {status})")
                    await self._safe_remove_container(container.id)
                    removed += 1
            
            log.info(
                f"Container discovery complete: "
                f"{discovered} reattached, {restarted} restarted, {removed} removed"
            )
            
        except Exception as e:
            log.error(f"Error during container discovery: {e}", exc_info=True)
    
    def _make_session_key(self, context: Dict[str, Any]) -> str:
        """
        Create unique session key from context.
        
        Args:
            context: Context dictionary with server_id, channel_id, ai_name, chat_id
            
        Returns:
            Session key string
        """
        server_id = context.get("server_id", "unknown")
        channel_id = context.get("channel_id", "unknown")
        ai_name = context.get("ai_name", "unknown")
        chat_id = context.get("chat_id", "default")
        
        return f"{server_id}:{channel_id}:{ai_name}:{chat_id}"
    
    async def cleanup_ephemeral_for_session(
        self,
        server_id: str,
        channel_id: str,
        ai_name: str,
        chat_id: str = "default"
    ) -> int:
        """
        Cleanup ephemeral containers for a specific session.
        
        Called when LLM finishes responding.
        
        Args:
            server_id: Server ID
            channel_id: Channel ID
            ai_name: AI name
            chat_id: Chat ID
            
        Returns:
            Number of containers cleaned up
        """
        session_key = f"{server_id}:{channel_id}:{ai_name}:{chat_id}"
        
        if session_key not in self.ephemeral_by_session:
            return 0
        
        containers = self.ephemeral_by_session[session_key]
        cleaned = 0
        
        log.info(f"Cleaning up {len(containers)} ephemeral containers for session {session_key}")
        
        for container_id, _ in containers:
            if await self._safe_remove_container(container_id):
                cleaned += 1
        
        # Clear the list
        del self.ephemeral_by_session[session_key]
        
        log.info(f"Cleaned up {cleaned}/{len(containers)} ephemeral containers")
        return cleaned
    
    async def _cleanup_orphaned_ephemeral(self):
        """Cleanup ephemeral containers that were never cleaned up (fallback)."""
        max_age = self.config.get("ephemeral_orphan_timeout", 600)  # 10 minutes default
        current_time = time.time()
        cleaned = 0
        
        for session_key in list(self.ephemeral_by_session.keys()):
            containers = self.ephemeral_by_session[session_key]
            remaining = []
            
            for container_id, created_time in containers:
                age = current_time - created_time
                
                if age > max_age:
                    log.warning(
                        f"Cleaning up orphaned ephemeral container {container_id[:12]} "
                        f"(age: {age:.0f}s, session: {session_key})"
                    )
                    if await self._safe_remove_container(container_id):
                        cleaned += 1
                else:
                    remaining.append((container_id, created_time))
            
            # Update or remove session
            if remaining:
                self.ephemeral_by_session[session_key] = remaining
            else:
                del self.ephemeral_by_session[session_key]
        
        if cleaned > 0:
            log.info(f"Cleaned up {cleaned} orphaned ephemeral containers")
        
        return cleaned
    
    async def _ephemeral_cleanup_loop(self):
        """Background task to cleanup orphaned ephemeral containers."""
        cleanup_interval = self.config.get("ephemeral_cleanup_interval", 60)  # 1 minute default
        
        log.info(f"Starting ephemeral cleanup loop (interval: {cleanup_interval}s)")
        
        while True:
            try:
                await asyncio.sleep(cleanup_interval)
                await self._cleanup_orphaned_ephemeral()
            except asyncio.CancelledError:
                log.info("Ephemeral cleanup loop cancelled")
                break
            except Exception as e:
                log.error(f"Error in ephemeral cleanup loop: {e}", exc_info=True)
    
    async def execute_command(
        self,
        chat_id: str,
        command: str,
        mode: str = "persistent",
        reset: bool = False,
        timeout: Optional[int] = None,
        working_dir: str = "/workspace",
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a bash command in a container.
        
        Args:
            chat_id: Chat session ID
            command: Bash command to execute
            mode: "persistent" or "ephemeral"
            reset: Reset container before executing
            timeout: Command timeout in seconds (None = use config default)
            working_dir: Working directory for command execution
            context: Context information (for ephemeral container tracking)
            
        Returns:
            Dict with execution results
        """
        await self.initialize()
        
        start_time = time.time()
        
        try:
            # Get or create container
            if mode == "ephemeral":
                container = await self._create_ephemeral_container()
                container_id = container.id
            else:
                # Persistent mode
                if reset:
                    # Explicit reset requested - remove old and create new
                    await self.reset_container(chat_id)
                
                container_info = self.containers.get(chat_id)
                if not container_info:
                    # Container doesn't exist - create new one (no cleanup needed)
                    container = await self._create_persistent_container(chat_id)
                    container_id = container.id
                else:
                    container_id = container_info.container_id
                    try:
                        container = await asyncio.to_thread(self.docker_client.containers.get, container_id)
                        # Check if container is running
                        if container.status != "running":
                            log.warning(f"Container {container_id[:12]} not running (status: {container.status}), recreating")
                            await self.reset_container(chat_id)
                            container_info = self.containers[chat_id]
                            container = await asyncio.to_thread(self.docker_client.containers.get, container_info.container_id)
                    except NotFound:
                        log.warning(f"Container {container_id[:12]} not found in Docker, recreating")
                        await self.reset_container(chat_id)
                        container_info = self.containers[chat_id]
                        container = await asyncio.to_thread(self.docker_client.containers.get, container_info.container_id)
                    except APIError as e:
                        log.error(f"Docker API error accessing container {container_id[:12]}: {e}")
                        log.info("Attempting to recreate container")
                        await self.reset_container(chat_id)
                        container_info = self.containers[chat_id]
                        container = await asyncio.to_thread(self.docker_client.containers.get, container_info.container_id)
            
            # Execute command
            timeout_value = timeout or self.config.get("command_timeout", 1800)
            
            log.info(f"Executing command in container {container_id[:12]}: {command[:100]}")
            
            # Create workspace directory if it doesn't exist (run in thread)
            try:
                await asyncio.to_thread(
                    container.exec_run,
                    f"mkdir -p {working_dir}",
                    user="root"
                )
            except:
                pass  # Ignore if already exists
            
            # Execute the actual command (run in thread to avoid blocking event loop)
            # Use array format to avoid shell quote escaping issues
            exec_result = await asyncio.to_thread(
                container.exec_run,
                ["bash", "-c", f"cd {working_dir} && {command}"],
                demux=True,
                user="root"
            )
            
            exit_code = exec_result.exit_code
            stdout_bytes, stderr_bytes = exec_result.output
            
            stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
            stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""
            
            execution_time = time.time() - start_time
            
            # Update container usage stats
            if mode == "persistent" and chat_id in self.containers:
                self.containers[chat_id].update_usage()
            
            # Register ephemeral container for deferred cleanup
            if mode == "ephemeral":
                # Get context to create session key
                context_dict = context if context else {}
                session_key = self._make_session_key(context_dict)
                
                # Register container with timestamp
                if session_key not in self.ephemeral_by_session:
                    self.ephemeral_by_session[session_key] = []
                
                self.ephemeral_by_session[session_key].append((container_id, time.time()))
                log.debug(
                    f"Registered ephemeral container {container_id[:12]} for session {session_key} "
                    f"(will be cleaned up when LLM finishes responding)"
                )
            
            # Get container info for metadata
            container_info = self.containers.get(chat_id) if mode == "persistent" else None
            
            result = {
                "success": exit_code == 0,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "execution_time": round(execution_time, 3),
                "container_id": container_id[:12],
                "mode": mode,
                # Additional metadata for debug embeds
                "command_count": container_info.command_count if container_info else None,
                "container_uptime": time.time() - container_info.created_at if container_info else None,
            }
            
            log.info(
                f"Command executed: exit_code={exit_code}, "
                f"time={execution_time:.2f}s, mode={mode}"
            )
            
            return result
            
        except Exception as e:
            log.error(f"Error executing command: {e}", exc_info=True)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Error executing command: {str(e)}",
                "exit_code": -1,
                "execution_time": round(time.time() - start_time, 3),
                "container_id": "error",
                "mode": mode,
                "error": str(e)
            }
    
    async def _create_persistent_container(self, chat_id: str):
        """Create a new persistent container for a chat session."""
        log.info(f"Creating persistent container for chat_id: {chat_id}")
        
        container = await self._create_container(f"hashi-bash-{chat_id}")
        
        # Store container info
        self.containers[chat_id] = ContainerInfo(
            container_id=container.id,
            chat_id=chat_id,
            created_at=time.time(),
            last_used=time.time(),
            mode="persistent"
        )
        
        log.info(f"Persistent container created: {container.id[:12]}")
        return container
    
    async def _create_ephemeral_container(self):
        """Create a new ephemeral container (one-time use)."""
        timestamp = int(time.time() * 1000)
        container = await self._create_container(f"hashi-bash-ephemeral-{timestamp}")
        log.debug(f"Ephemeral container created: {container.id[:12]}")
        return container
    
    async def _create_container(self, name: str):
        """
        Create a Docker container with configured resource limits.
        
        Args:
            name: Container name
            
        Returns:
            Docker container object
        """
        image = self.config.get("image", "ubuntu:22.04")
        cpu_limit = self.config.get("cpu_limit", "1.0")
        memory_limit = self.config.get("memory_limit", "512m")
        disk_limit = self.config.get("disk_limit", "2g")
        network_enabled = self.config.get("network_enabled", True)
        
        # Ensure image is pulled (run in thread to avoid blocking)
        try:
            await asyncio.to_thread(self.docker_client.images.get, image)
        except:
            log.info(f"Pulling Docker image: {image}")
            await asyncio.to_thread(self.docker_client.images.pull, image)
        
        # Container configuration
        container_config = {
            "image": image,
            "name": name,
            "detach": True,
            "tty": True,
            "stdin_open": True,
            "command": "/bin/bash",
            "cpu_quota": int(float(cpu_limit) * 100000),
            "cpu_period": 100000,
            "mem_limit": memory_limit,
            "storage_opt": {"size": disk_limit},
            "security_opt": ["no-new-privileges"],
            "cap_drop": ["ALL"],
            "cap_add": ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID", "NET_BIND_SERVICE"],
            "remove": False,
            "labels": {
                "managed_by": "hashi-bash-tool",
                "created_at": str(int(time.time()))
            }
        }
        
        # Network configuration
        if not network_enabled:
            container_config["network_mode"] = "none"
        
        try:
            # Run container creation in thread to avoid blocking
            container = await asyncio.to_thread(self.docker_client.containers.run, **container_config)
            log.debug(f"Container {name} created with limits: CPU={cpu_limit}, RAM={memory_limit}, Disk={disk_limit}")
            return container
            
        except Conflict as e:
            # Container with this name already exists - try to remove it and retry
            log.warning(f"Container name conflict for '{name}': {e}")
            log.info(f"Attempting to remove existing container and retry")
            
            try:
                # Try to get and remove the conflicting container
                existing = await asyncio.to_thread(self.docker_client.containers.get, name)
                await self._safe_remove_container(existing.id)
                
                # Retry creation
                container = await asyncio.to_thread(self.docker_client.containers.run, **container_config)
                log.info(f"Container {name} created successfully after removing conflict")
                return container
                
            except Exception as retry_error:
                log.error(f"Failed to resolve container name conflict: {retry_error}")
                raise RuntimeError(f"Container name '{name}' is in use and could not be removed") from retry_error
        
        except APIError as e:
            log.error(f"Docker API error creating container '{name}': {e}")
            raise RuntimeError(f"Docker API error: {e}") from e
            
        except Exception as e:
            log.error(f"Unexpected error creating container '{name}': {e}")
            raise
    
    async def reset_container(self, chat_id: str) -> bool:
        """
        Reset a container (remove old and create new).
        
        Only called when explicitly requested via reset=True.
        
        Args:
            chat_id: Chat session ID
            
        Returns:
            True if successful
        """
        log.info(f"Resetting container for chat_id: {chat_id}")
        
        # Remove old container if exists
        if chat_id in self.containers:
            old_container_id = self.containers[chat_id].container_id
            await self._safe_remove_container(old_container_id)
            del self.containers[chat_id]
        
        # Note: We don't cleanup orphaned containers here anymore.
        # Orphan cleanup only happens during initialization via _discover_existing_containers.
        # This prevents removing valid containers during normal operation.
        # If a name conflict occurs, _create_container handles it automatically.
        
        # Create new container
        await self._create_persistent_container(chat_id)
        return True
    
    async def cleanup_all(self) -> int:
        """
        Clean up all managed containers.
        
        Returns:
            Number of containers cleaned up
        """
        log.info("Cleaning up all managed containers")
        cleaned = 0
        
        for chat_id in list(self.containers.keys()):
            info = self.containers[chat_id]
            if await self._safe_remove_container(info.container_id):
                del self.containers[chat_id]
                cleaned += 1
            else:
                log.warning(f"Failed to cleanup container for chat_id: {chat_id}")
        
        log.info(f"Cleaned up {cleaned} containers")
        return cleaned
    
    async def shutdown(self):
        """Shutdown the container manager and cleanup resources."""
        log.info("Shutting down ContainerManager")
        
        # Cleanup all containers if configured
        if self.config.get("auto_cleanup_on_shutdown", False):
            log.info("Auto cleanup on shutdown enabled, removing all containers")
            await self.cleanup_all()
        else:
            log.info(f"Auto cleanup disabled, leaving {len(self.containers)} containers running")
        
        log.info("ContainerManager shutdown complete")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about managed containers."""
        total_commands = sum(info.command_count for info in self.containers.values())
        
        return {
            "active_containers": len(self.containers),
            "total_commands_executed": total_commands,
            "containers": [
                {
                    "chat_id": info.chat_id,
                    "container_id": info.container_id[:12],
                    "created_at": datetime.fromtimestamp(info.created_at).isoformat(),
                    "last_used": datetime.fromtimestamp(info.last_used).isoformat(),
                    "command_count": info.command_count,
                    "age_hours": round((time.time() - info.created_at) / 3600, 2)
                }
                for info in self.containers.values()
            ]
        }
    
    def _validate_container_path(self, path: str, allowed_base: str = "/workspace") -> bool:
        """
        Validate if path is within allowed directory (security check).
        
        Args:
            path: Path to validate
            allowed_base: Base directory that must contain the path
            
        Returns:
            True if path is safe, False otherwise
        """
        # Normalize path to resolve .. and .
        normalized = os.path.normpath(path)
        
        # Ensure it starts with allowed base
        # Also prevent absolute paths outside workspace
        if not normalized.startswith(allowed_base):
            return False
        
        # Additional check: no .. after normalization
        if ".." in normalized:
            return False
        
        return True
    
    async def list_files(
        self,
        chat_id: str,
        path: str = "/workspace",
        recursive: bool = False,
        pattern: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List files in container directory.
        
        Args:
            chat_id: Chat session ID
            path: Directory path to list
            recursive: List recursively
            pattern: Optional filename pattern (e.g., "*.py")
            
        Returns:
            Dict with file list and metadata
        """
        await self.initialize()
        
        # Validate path
        if not self._validate_container_path(path):
            return {
                "error": f"Invalid path: {path}. Must be within /workspace",
                "files": []
            }
        
        try:
            # Get container
            container_info = self.containers.get(chat_id)
            if not container_info:
                return {
                    "error": f"No container found for chat_id: {chat_id}",
                    "files": []
                }
            
            container = await asyncio.to_thread(
                self.docker_client.containers.get,
                container_info.container_id
            )
            
            # Build find command
            if recursive:
                if pattern:
                    cmd = f"find {path} -type f -name '{pattern}' 2>/dev/null || true"
                else:
                    cmd = f"find {path} -type f 2>/dev/null || true"
            else:
                if pattern:
                    cmd = f"find {path} -maxdepth 1 -type f -name '{pattern}' 2>/dev/null || true"
                else:
                    cmd = f"find {path} -maxdepth 1 -type f 2>/dev/null || true"
            
            # Execute command
            # Use array format to avoid shell quote escaping issues
            result = await asyncio.to_thread(
                container.exec_run,
                ["bash", "-c", cmd],
                user="root"
            )
            
            if result.exit_code != 0:
                return {
                    "error": f"Failed to list files: {result.output.decode('utf-8', errors='replace')}",
                    "files": []
                }
            
            # Parse output
            output = result.output.decode('utf-8', errors='replace').strip()
            files = [f.strip() for f in output.split('\n') if f.strip()]
            
            # Get file sizes
            file_info = []
            for file_path in files:
                try:
                    size_result = await asyncio.to_thread(
                        container.exec_run,
                        f"stat -c %s {file_path}",
                        user="root"
                    )
                    if size_result.exit_code == 0:
                        size = int(size_result.output.decode('utf-8', errors='replace').strip())
                        file_info.append({
                            "path": file_path,
                            "name": os.path.basename(file_path),
                            "size": size
                        })
                except:
                    file_info.append({
                        "path": file_path,
                        "name": os.path.basename(file_path),
                        "size": 0
                    })
            
            return {
                "files": file_info,
                "total": len(file_info),
                "path": path,
                "recursive": recursive
            }
            
        except Exception as e:
            log.error(f"Error listing files in container: {e}", exc_info=True)
            return {
                "error": f"Failed to list files: {str(e)}",
                "files": []
            }
    
    async def read_file(
        self,
        chat_id: str,
        path: str,
        max_size: int = 10 * 1024 * 1024  # 10MB default
    ) -> Dict[str, Any]:
        """
        Read file content from container.
        
        Args:
            chat_id: Chat session ID
            path: File path in container
            max_size: Maximum file size to read (bytes)
            
        Returns:
            Dict with file content or error
        """
        await self.initialize()
        
        # Validate path
        if not self._validate_container_path(path):
            return {
                "error": f"Invalid path: {path}. Must be within /workspace"
            }
        
        try:
            # Get container
            container_info = self.containers.get(chat_id)
            if not container_info:
                return {
                    "error": f"No container found for chat_id: {chat_id}"
                }
            
            container = await asyncio.to_thread(
                self.docker_client.containers.get,
                container_info.container_id
            )
            
            # Check if file exists and get size
            stat_result = await asyncio.to_thread(
                container.exec_run,
                f"stat -c '%s %F' {path}",
                user="root"
            )
            
            if stat_result.exit_code != 0:
                return {
                    "error": f"File not found: {path}"
                }
            
            stat_output = stat_result.output.decode('utf-8', errors='replace').strip()
            parts = stat_output.split(' ', 1)
            file_size = int(parts[0])
            file_type = parts[1] if len(parts) > 1 else ""
            
            if "directory" in file_type.lower():
                return {
                    "error": f"Path is a directory, not a file: {path}"
                }
            
            if file_size > max_size:
                return {
                    "error": f"File too large: {file_size} bytes (max: {max_size} bytes)",
                    "size": file_size,
                    "max_size": max_size
                }
            
            # Read file using get_archive (safer for binary files)
            bits, stat = await asyncio.to_thread(
                container.get_archive,
                path
            )
            
            # Extract from tar
            tar_stream = io.BytesIO()
            for chunk in bits:
                tar_stream.write(chunk)
            tar_stream.seek(0)
            
            with tarfile.open(fileobj=tar_stream) as tar:
                members = tar.getmembers()
                if not members:
                    return {"error": "File is empty or could not be read"}
                
                file_member = members[0]
                file_obj = tar.extractfile(file_member)
                if not file_obj:
                    return {"error": "Could not extract file content"}
                
                content_bytes = file_obj.read()
            
            # Try to decode as text
            try:
                content_text = content_bytes.decode('utf-8')
                is_text = True
            except UnicodeDecodeError:
                content_text = None
                is_text = False
            
            result = {
                "path": path,
                "name": os.path.basename(path),
                "size": file_size,
                "is_text": is_text
            }
            
            if is_text:
                result["content"] = content_text
                result["encoding"] = "utf-8"
            else:
                # For binary files, return base64
                import base64
                result["content_base64"] = base64.b64encode(content_bytes).decode('ascii')
                result["encoding"] = "base64"
            
            return result
            
        except Exception as e:
            log.error(f"Error reading file from container: {e}", exc_info=True)
            return {
                "error": f"Failed to read file: {str(e)}"
            }
    
    async def write_file(
        self,
        chat_id: str,
        path: str,
        content: Union[str, bytes],
        encoding: str = "utf-8"
    ) -> Dict[str, Any]:
        """
        Write file to container.
        
        Args:
            chat_id: Chat session ID
            path: File path in container
            content: File content (str or bytes)
            encoding: Encoding for string content
            
        Returns:
            Dict with success status
        """
        await self.initialize()
        
        # Validate path
        if not self._validate_container_path(path):
            return {
                "error": f"Invalid path: {path}. Must be within /workspace",
                "success": False
            }
        
        try:
            # Get container
            container_info = self.containers.get(chat_id)
            if not container_info:
                return {
                    "error": f"No container found for chat_id: {chat_id}",
                    "success": False
                }
            
            container = await asyncio.to_thread(
                self.docker_client.containers.get,
                container_info.container_id
            )
            
            # Convert content to bytes
            if isinstance(content, str):
                content_bytes = content.encode(encoding)
            else:
                content_bytes = content
            
            # Create tar archive with file
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                file_data = io.BytesIO(content_bytes)
                tarinfo = tarfile.TarInfo(name=os.path.basename(path))
                tarinfo.size = len(content_bytes)
                tarinfo.mtime = time.time()
                tar.addfile(tarinfo, file_data)
            
            tar_stream.seek(0)
            
            # Ensure parent directory exists
            parent_dir = os.path.dirname(path)
            if parent_dir:
                await asyncio.to_thread(
                    container.exec_run,
                    f"mkdir -p {parent_dir}",
                    user="root"
                )
            
            # Upload file
            await asyncio.to_thread(
                container.put_archive,
                parent_dir if parent_dir else "/",
                tar_stream.read()
            )
            
            return {
                "success": True,
                "path": path,
                "bytes_written": len(content_bytes)
            }
            
        except Exception as e:
            log.error(f"Error writing file to container: {e}", exc_info=True)
            return {
                "error": f"Failed to write file: {str(e)}",
                "success": False
            }
    
    async def extract_file(
        self,
        chat_id: str,
        path: str,
        max_size: int = 8 * 1024 * 1024  # 8MB (Discord limit for bots)
    ) -> Dict[str, Any]:
        """
        Extract file from container for sending to Discord.
        
        Args:
            chat_id: Chat session ID
            path: File path in container
            max_size: Maximum file size (Discord limit: 8MB for bots)
            
        Returns:
            Dict with file bytes and metadata, or error
        """
        await self.initialize()
        
        # Validate path
        if not self._validate_container_path(path):
            return {
                "error": f"Invalid path: {path}. Must be within /workspace"
            }
        
        try:
            # Get container
            container_info = self.containers.get(chat_id)
            if not container_info:
                return {
                    "error": f"No container found for chat_id: {chat_id}"
                }
            
            container = await asyncio.to_thread(
                self.docker_client.containers.get,
                container_info.container_id
            )
            
            # Check if file exists and get size
            stat_result = await asyncio.to_thread(
                container.exec_run,
                f"stat -c '%s %F' {path}",
                user="root"
            )
            
            if stat_result.exit_code != 0:
                return {
                    "error": f"File not found: {path}"
                }
            
            stat_output = stat_result.output.decode('utf-8', errors='replace').strip()
            parts = stat_output.split(' ', 1)
            file_size = int(parts[0])
            file_type = parts[1] if len(parts) > 1 else ""
            
            if "directory" in file_type.lower():
                return {
                    "error": f"Path is a directory, not a file: {path}"
                }
            
            if file_size > max_size:
                return {
                    "error": f"File too large for Discord: {file_size} bytes (max: {max_size} bytes)",
                    "size": file_size,
                    "max_size": max_size,
                    "suggestion": "Consider compressing the file or splitting it into smaller parts"
                }
            
            # Extract file using get_archive
            bits, stat = await asyncio.to_thread(
                container.get_archive,
                path
            )
            
            # Extract from tar
            tar_stream = io.BytesIO()
            for chunk in bits:
                tar_stream.write(chunk)
            tar_stream.seek(0)
            
            with tarfile.open(fileobj=tar_stream) as tar:
                members = tar.getmembers()
                if not members:
                    return {"error": "File is empty or could not be read"}
                
                file_member = members[0]
                file_obj = tar.extractfile(file_member)
                if not file_obj:
                    return {"error": "Could not extract file content"}
                
                file_bytes = file_obj.read()
            
            return {
                "success": True,
                "filename": os.path.basename(path),
                "bytes": file_bytes,
                "size": len(file_bytes),
                "path": path
            }
            
        except Exception as e:
            log.error(f"Error extracting file from container: {e}", exc_info=True)
            return {
                "error": f"Failed to extract file: {str(e)}"
            }


# Global container manager instance
_manager: Optional[ContainerManager] = None


def get_container_manager(config: Dict[str, Any]) -> ContainerManager:
    """Get or create the global container manager instance."""
    global _manager
    if _manager is None:
        _manager = ContainerManager(config)
    return _manager
