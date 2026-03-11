import subprocess
import os
from typing import Dict, Any
from .base import BaseSkill
import logging

logger = logging.getLogger(__name__)

class ShellSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="shell",
            description="Allows executing shell commands in the terminal."
        )
        self.tools = [
            {
                "name": "shell__run_command",
                "description": "Execute a shell command.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The command to run."},
                        "cwd": {"type": "string", "description": "Directory to run command in."}
                    },
                    "required": ["command"]
                }
            }
        ]

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> Any:
        if tool_name == "shell__run_command":
            command = args.get("command")
            cwd = args.get("cwd", os.getcwd())
            
            # Simple safety check (expand this for production)
            forbidden = ["rm -rf /", "mkfs", "dd if=/dev/zero"]
            if any(f in command for f in forbidden):
                return "Error: Command is dangerous and blocked."

            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                return {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode
                }
            except Exception as e:
                return f"Error executing command: {str(e)}"
        return f"Tool {tool_name} not found in shell skill."
