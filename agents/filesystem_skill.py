import os
from typing import Dict, Any
from .base import BaseSkill
import logging

logger = logging.getLogger(__name__)

class FilesystemSkill(BaseSkill):
    def __init__(self):
        super().__init__(
            name="filesystem",
            description="Read, write, and manage files on the system."
        )
        self.tools = [
            {
                "name": "filesystem__read_file",
                "description": "Read the contents of a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to the file."}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "filesystem__write_file",
                "description": "Write content to a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to the file."},
                        "content": {"type": "string", "description": "Content to write."}
                    },
                    "required": ["path", "content"]
                }
            }
        ]

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> Any:
        path = args.get("path")
        if not path:
            return "Error: Path is required."

        if tool_name == "filesystem__read_file":
            try:
                with open(path, "r") as f:
                    return f.read()
            except Exception as e:
                return f"Error reading file: {str(e)}"
        
        elif tool_name == "filesystem__write_file":
            content = args.get("content", "")
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as f:
                    f.write(content)
                return f"Successfully wrote to {path}"
            except Exception as e:
                return f"Error writing file: {str(e)}"
        
        return f"Tool {tool_name} not found in filesystem skill."
