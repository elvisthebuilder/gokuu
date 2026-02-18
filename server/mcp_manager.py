import os
import httpx
import json
import logging
import subprocess
from typing import List, Dict, Any
from server.openclaw_ingestor import OpenClawIngestor

logger = logging.getLogger(__name__)

class MCPManager:
    def __init__(self):
        self.servers = {
            "git": os.getenv("MCP_GIT_URL", "http://localhost:8080"),
            "search": os.getenv("MCP_SEARCH_URL", "http://localhost:8081"),
        }
        self.openclaw_root = "/home/elvisthebuilder/Documents/Dev/goku/openclaw"
        self.openclaw_ingestor = OpenClawIngestor(self.openclaw_root)

    async def get_all_tools(self) -> List[Dict[str, Any]]:
        all_tools = []
        async with httpx.AsyncClient() as client:
            for name, url in self.servers.items():
                try:
                    response = await client.get(f"{url}/tools", timeout=5.0)
                    if response.status_code == 200:
                        tools = response.json()
                        # Namespace tools to avoid collisions
                        for tool in tools:
                            tool["name"] = f"mcp_{name}__{tool['name']}"
                        all_tools.extend(tools)
                except Exception:
                    # Silence errors for external MCP servers when offline
                    pass
        
        # Add Native Bash tool (Superior feature)
        all_tools.append({
            "type": "function",
            "function": {
                "name": "bash",
                "description": "Execute a bash command in the local terminal. Use this to fulfill OpenClaw skill instructions or perform system tasks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The exact bash command to execute."
                        }
                    },
                    "required": ["command"]
                }
            },
            "source": "native"
        })



        # Add OpenClaw tools
        try:
            claw_tools = self.openclaw_ingestor.generate_tool_definitions()
            for tool in claw_tools:
                # Add source metadata
                tool["source"] = "openclaw"
                all_tools.append(tool)
        except Exception as e:
            logger.error(f"Error ingesting OpenClaw skills: {str(e)}")
            
        return all_tools



    def is_sensitive(self, tool_name: str, args: Dict[str, Any]) -> bool:
        """Determine if a tool call requires user confirmation.
        
        Pure blocklist approach: only flag genuinely catastrophic operations.
        Everything else runs freely — like Antigravity.
        """
        if tool_name == "bash":
            cmd = args.get("command", "").strip()
            if not cmd:
                return False
            
            # 1. Block high-risk system commands (command must be exact match or follow space)
            dangerous_commands = ["sudo", "mkfs", "fdisk", "parted", "shutdown", "reboot", "poweroff"]
            base_cmd = cmd.split()[0]
            if base_cmd in dangerous_commands:
                return True
            
            # 2. Block catastrophic deletion patterns
            # Note: We allow deleting specific files, but block recursive deletions of critical paths
            catastrophic_patterns = [
                "rm -rf /", "rm -rf ~", "rm -rf .", 
                "rm -rf /home", "rm -rf /etc", "rm -rf /var",
                "rm -rf * /", # Common typo danger
            ]
            if any(pattern in cmd for pattern in catastrophic_patterns):
                return True

            # 3. Block low-level disk/system manipulation
            system_manipulation = [
                "dd if=", "> /dev/", ":(){ :|:& };:", 
                "chmod -R 777 /", "chown -R root /"
            ]
            if any(pattern in cmd for pattern in system_manipulation):
                return True
            
            return False
            
        return False

    async def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        if not hasattr(self, "cwd"):
            self.cwd = os.getcwd()
            
        # 1. Determine the source based on the tool name prefix
        if tool_name == "bash":
            server_name = "native"
        elif tool_name.startswith("openclaw_"):
            server_name = "openclaw"
        elif "__" in tool_name and tool_name.startswith("mcp_"):
            # Format: mcp_provider__real_tool_name
            parts = tool_name.split("__", 1)
            server_name = parts[0].replace("mcp_", "")
            tool_name = parts[1]
        else:
            return f"Error: Could not determine source for tool '{tool_name}'"

        # 2. Handle Native Tools
        if server_name == "native" and tool_name == "bash":
            raw_command = args.get("command")
            if not raw_command:
                return "Error: No 'command' argument provided for bash."
            
            # Wrap command to persist directory and capture final CWD
            # We use a subshell to execute the command, then print the CWD
            full_command = f"cd {self.cwd} && ({raw_command}) && pwd"
            
            try:
                result = subprocess.run(full_command, shell=True, capture_output=True, text=True, timeout=30.0)
                
                output = result.stdout.strip().split("\n")
                if output:
                    new_cwd = output[-1].strip()
                    if os.path.isdir(new_cwd):
                        self.cwd = new_cwd
                    # The actual output is everything except the last line (the pwd)
                    actual_stdout = "\n".join(output[:-1])
                else:
                    actual_stdout = result.stdout

                return {
                    "stdout": actual_stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode,
                    "cwd": self.cwd
                }
            except Exception as e:
                return f"Error executing bash: {str(e)}"

        # 3. Handle OpenClaw Ingested Tools
        if server_name == "openclaw":
            all_tools = await self.get_all_tools()
            tool = next((t for t in all_tools if t["function"]["name"] == tool_name), None)
            if tool:
                return {
                    "status": "success",
                    "instructions": tool.get("instructions", ""),
                    "metadata": tool.get("metadata", {}),
                    "note": "Use the 'bash' tool to execute the suggested commands."
                }
            return f"Error: OpenClaw tool '{tool_name}' not found."

        # 4. Handle External MCP Tools
        url = self.servers.get(server_name)
        if not url:
            return f"Error: MCP server '{server_name}' is not configured."

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{url}/call",
                    json={"name": tool_name, "arguments": args},
                    timeout=30.0
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    return f"Error from MCP server ({server_name}): {response.text}"
            except Exception as e:
                logger.error(f"Error calling MCP tool {tool_name} on {server_name}: {str(e)}")
                return f"Error executing MCP tool: {str(e)}"

mcp_manager = MCPManager()
