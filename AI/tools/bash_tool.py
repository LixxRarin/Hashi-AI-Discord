"""
Bash Tool - Execute bash commands in isolated Docker containers

This tool allows the LLM to execute bash commands in isolated Docker containers
with persistent or ephemeral modes.
"""

import logging
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)


async def bash_tool(
    command: str,
    mode: Optional[str] = None,
    reset: Optional[bool] = None,
    timeout: Optional[int] = None,
    working_dir: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Execute a bash command in an isolated Docker container.
    
    This tool provides a sandboxed environment for running bash commands with:
    - Persistent containers per chat session (default)
    - Ephemeral containers for one-time execution
    - Resource limits (CPU, RAM, disk)
    - Network access (configurable)
    - Automatic cleanup
    
    Args:
        command: Bash command to execute
        mode: "persistent" (default) or "ephemeral"
        reset: Reset container before executing (persistent mode only)
        timeout: Command timeout in seconds (default: from config)
        working_dir: Working directory for command execution (default: /workspace)
        context: Context information (chat_id, config, etc.)
        
    Returns:
        Dict with execution results:
        - success: bool - Whether command succeeded (exit_code == 0)
        - stdout: str - Standard output
        - stderr: str - Standard error
        - exit_code: int - Command exit code
        - execution_time: float - Execution time in seconds
        - container_id: str - Container ID (short form)
        - mode: str - Execution mode used
        
    Examples:
        # Simple command
        bash_tool(command="echo 'Hello World'")
        
        # Install package and use it
        bash_tool(command="apt-get update && apt-get install -y curl")
        bash_tool(command="curl -I https://example.com")
        
        # Create and run a Python script
        bash_tool(command="echo 'print(2+2)' > test.py && python3 test.py")
        
        # Reset environment
        bash_tool(command="ls", reset=True)
        
        # One-time execution (ephemeral)
        bash_tool(command="whoami", mode="ephemeral")
    """
    if context is None:
        return {"error": "No context provided"}
    
    # Validate command
    if not command or not isinstance(command, str):
        return {
            "error": "Invalid command: must be a non-empty string",
            "success": False
        }
    
    # Get configuration
    session = context.get("session", {})
    config = session.get("config", {})
    bash_config = config.get("bash_tool", {})
    
    # Check if bash_tool is enabled
    if not bash_config.get("enabled", True):
        return {
            "error": "bash_tool is disabled in configuration",
            "success": False
        }
    
    # Get chat_id for persistent containers
    chat_id = context.get("chat_id", "default")
    
    # Set defaults
    if mode is None:
        mode = bash_config.get("default_mode", "persistent")
    
    if reset is None:
        reset = False
    
    if working_dir is None:
        working_dir = "/workspace"
    
    log.info(f"bash_tool called: chat_id={chat_id}, mode={mode}, reset={reset}")
    log.debug(f"Command: {command[:200]}")
    
    try:
        # Get container manager
        from utils.container_manager import get_container_manager
        manager = get_container_manager(bash_config)
        
        # Execute command
        result = await manager.execute_command(
            chat_id=chat_id,
            command=command,
            mode=mode,
            reset=reset,
            timeout=timeout,
            working_dir=working_dir,
            context=context
        )
        
        # Add helpful context to result
        if result.get("success"):
            log.info(f"Command succeeded: exit_code=0, time={result.get('execution_time')}s")
        else:
            log.warning(
                f"Command failed: exit_code={result.get('exit_code')}, "
                f"stderr={result.get('stderr', '')[:100]}"
            )
        
        return result
        
    except RuntimeError as e:
        # Docker not installed or connection failed
        error_msg = str(e)
        log.error(f"Runtime error in bash_tool: {error_msg}")
        return {
            "error": error_msg,
            "success": False,
            "stdout": "",
            "stderr": error_msg,
            "exit_code": -1
        }
    
    except Exception as e:
        # Unexpected error
        error_msg = f"Unexpected error in bash_tool: {str(e)}"
        log.error(error_msg, exc_info=True)
        return {
            "error": error_msg,
            "success": False,
            "stdout": "",
            "stderr": error_msg,
            "exit_code": -1
        }
