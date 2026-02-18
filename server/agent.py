import json
import logging
import asyncio
from typing import List, Dict, Any, AsyncGenerator
from server.lite_router import router
from server.mcp_manager import mcp_manager
from server.memory import memory

logger = logging.getLogger(__name__)

class GokuAgent:
    async def get_models(self, provider: str = None):
        return await router.get_available_models(provider)

    def __init__(self):
        self.system_prompt = (
            "You are GOKU, a superior AI terminal agent designed for high-fidelity collaboration, "
            "directly inspired by the intelligence and proactive nature of 'Antigravity'.\n\n"
            "CORE PRINCIPLES:\n"
            "1. PERSISTENCE: Never give up after a single failure. If a command fails or a path is not found, "
            "use `pwd`, `ls`, or `find` to map the environment and self-correct. Exhaust at least 3 logical "
            "approaches before asking the user for help.\n"
            "2. PLAN FIRST: For ANY multi-step request, you MUST use `manage_tasks` to create a visible plan before executing any other tools. "
            "After adding tasks with `manage_tasks`, YOU MUST STOP and wait for the user to approve the plan. do not combine planning and execution in one turn. "
            "Update the task status as you progress.\n"
            "3. SMART ORIENTATION: If you don't know the system structure, run `whoami` and `pwd` to orient yourself. "
            "Don't guess paths; verify them.\n"
            "4. SAFETY: The system handles permission checks automatically for destructive operations. "
            "You do NOT need to ask the user for permission or confirmation before running commands. Just execute.\n"
            "5. ACT, DON'T NARRATE: NEVER send a message like 'Let me try X' or 'I'll search for Y' without "
            "ALSO making the tool call in the same response. If you want to explain what you're doing mid-execution, include "
            "the explanation AND the tool call together. NEVER pause mid-task to wait for the user to say 'okay' — "
            "just keep executing until you have a final answer or need significant user guidance. "
            "(Note: This does NOT apply to Principle #2; planning ALWAYS requires a pause for approval.)\n"
            "6. NO SPOON-FEEDING: Minimize the work the user has to do. If they give you a goal, take full "
            "ownership of the research and execution. Chain multiple tool calls as needed.\n"
            "7. INTEGRATIONS: You are connected to Telegram via a local bot. You can receive and reply to messages there.\n"
            "8. SEARCH PRIORITY: When the user asks you to search or look something up, ALWAYS use your "
            "built-in search tools (prefixed with 'mcp_search__') FIRST. These are your configured search providers "
            "(DuckDuckGo, Brave, Google). Only fall back to bash with curl if the search tools fail or are unavailable."
        )
        self.history: List[Dict[str, Any]] = []
        self.tasks: List[Dict[str, str]] = [] # [{"desc": "...", "status": "todo|in_progress|done"}]
        self.model_override = None

    def clear_history(self):
        self.history = []
        self.tasks = []

    async def run_agent(self, user_text: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Runs the agent loop and yields thoughts, messages, and tool results."""
        if not user_text:
            return

        self._narration_retries = 0  # Reset per-query

        # Conversational Security: Check for approval of pending actions
        try:
            if not hasattr(self, "approved_hashes"): self.approved_hashes = set()
            if not hasattr(self, "pending_hashes"): self.pending_hashes = set()
            
            if self.pending_hashes:
                lower_text = user_text.lower().strip()
                # Heuristic for approval (Simple keywords, covers 90% of cases)
                if any(x in lower_text for x in ["yes", "y", "ok", "okay", "sure", "go", "proceed", "approve", "do it", "fine", "go ahead", "go on"]):
                    self.approved_hashes.update(self.pending_hashes)
                    # Session-level trust: approve the tool NAME so future calls skip permission
                    if not hasattr(self, "trusted_tools"): self.trusted_tools = set()
                    for h in self.pending_hashes:
                        tool_name_from_hash = h.split(":", 1)[0]
                        self.trusted_tools.add(tool_name_from_hash)
                    self.pending_hashes.clear()
                    # yield {"type": "thought", "content": "✅ Permission granted by user."}
                elif any(x in lower_text for x in ["no", "n", "stop", "cancel", "don't"]):
                    self.pending_hashes.clear()
                    # yield {"type": "thought", "content": "❌ Permission denied by user."}
        except Exception as e:
            logger.error(f"Security state error: {e}")

        # 1. Retrieval
        yield {"type": "thought", "content": "Searching vector memory for relevant context..."}
        context = await memory.search_memory(user_text)
        
        # Update system prompt with latest context
        full_system_prompt = f"{self.system_prompt} Retrieved Context: {json.dumps(context)}"
        
        # Ensure we have a system message if history is empty
        if not self.history:
            self.history.append({"role": "system", "content": full_system_prompt})
        else:
            # Update the existing system message if it exists
            if self.history[0]["role"] == "system":
                self.history[0]["content"] = full_system_prompt

        self.history.append({"role": "user", "content": user_text})
        
        # 2. MCP & Model Routing
        yield {"type": "thought", "content": "Checking available MCP tools (Git, Search, Shell)..."}
        all_tools = await mcp_manager.get_all_tools()
        
        yield {"type": "thought", "content": "Routing to best model (Hybrid Online/Offline)..."}

        # 3. Execution Loop
        llm_tools = [
            {"type": t["type"], "function": t["function"]} 
            for t in all_tools if "type" in t and "function" in t
        ]
        
        # Add internal task management tool
        llm_tools.append({
            "type": "function",
            "function": {
                "name": "manage_tasks",
                "description": "Manage your internal task list. Use this to create a plan for complex requests.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["add", "update", "clear"]},
                        "tasks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "desc": {"type": "string"},
                                    "status": {"type": "string", "enum": ["todo", "in_progress", "done"]}
                                }
                            }
                        },
                        "index": {"type": "integer"},
                        "status": {"type": "string", "enum": ["todo", "in_progress", "done"]}
                    },
                    "required": ["action"]
                }
            }
        })

        max_turns = 10 
        for turn in range(max_turns):
            try:
                response = await router.get_response(
                    model=self.model_override or "default",
                    messages=self.history, 
                    tools=llm_tools if llm_tools else None,
                    stream=False
                )
            except Exception as e:
                logger.error(f"Routing Error: {str(e)}")
                yield {"type": "thought", "content": f"⚠️ System Switch: {str(e)}"}
                raise e
            
            msg_response = response.choices[0].message
            # LiteLLM message response conversion
            msg_dict = {
                "role": "assistant",
                "content": getattr(msg_response, "content", None),
            }
            if msg_response.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    } for tc in msg_response.tool_calls
                ]
            
            self.history.append(msg_dict)

            content = getattr(msg_response, "content", None)
            
            if not msg_response.tool_calls:
                # No tool calls — is this a final answer or mid-execution narration?
                if turn == 0 or not content:
                    # First turn or empty response — this is a final answer
                    if content:
                        yield {
                            "type": "message",
                            "role": "agent",
                            "content": content
                        }
                    elif turn == 0:
                        # Only show the "empty response" error if it happens on the very first turn
                        yield {
                            "type": "message",
                            "role": "agent",
                            "content": "_[System: Received empty response from model. Please try a more specific query.]_"
                        }
                    # If turn > 0 and no content/tools, we just assume the agent is done
                    break
                else:
                    # Mid-execution: is this a permission question or just progress narration?
                    has_pending_permission = hasattr(self, "pending_hashes") and self.pending_hashes
                    is_question = "?" in content and len(content) < 200 # Heuristic for a short question
                    
                    if has_pending_permission or is_question:
                        # Legitimate question or permission request — let the user respond
                        yield {
                            "type": "message",
                            "role": "agent",
                            "content": content
                        }
                        break
                    
                    # Progress narration (e.g. "Let me try a different approach")
                    # Yield as a thought so it stays in the Thinking panel
                    yield {
                        "type": "thought",
                        "content": content
                    }
                    
                    # Track retries to prevent loops
                    self._narration_retries += 1
                    if self._narration_retries >= 3:
                        # Fallback: if it keeps narrating, show it as a message and stop
                        yield {
                            "type": "message",
                            "role": "agent",
                            "content": content
                        }
                        break
                    
                    # Nudge: tell the LLM to skip the chatter and ACT
                    self.history.append({
                        "role": "user",
                        "content": "[SYSTEM: Progress acknowledged. Proceed with your next step using a tool call NOW. Do not describe what you will do — just execute. If you are finished, just say so.]"
                    })
                    continue
            else:
                # Has tool calls — yield content if present, reset retry counter
                self._narration_retries = 0
                if content:
                    yield {
                        "type": "message",
                        "role": "agent",
                        "content": content
                    }

            # Prep for tool processing: Prioritize planning.
            # If the model sends multiple tools (e.g. bash + manage_tasks), we MUST
            # execute the plan first and ignore the others to wait for approval.
            tool_calls = msg_response.tool_calls
            planning_call = next((tc for tc in tool_calls if tc.function.name == "manage_tasks" and json.loads(tc.function.arguments).get("action") == "add"), None)
            
            # If we are planning, only process the planning call and stop.
            active_tool_calls = [planning_call] if planning_call else tool_calls

            for tool_call in active_tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                if tool_name == "manage_tasks":
                    action = tool_args.get("action")
                    if action == "add":
                        new_tasks = tool_args.get("tasks", [])
                        self.tasks.extend(new_tasks)
                    elif action == "update":
                        idx = tool_args.get("index")
                        status = tool_args.get("status")
                        if 0 <= idx < len(self.tasks):
                            self.tasks[idx]["status"] = status
                    elif action == "clear":
                        self.tasks = []
                    
                    yield {"type": "task_update", "tasks": self.tasks}
                    result = {"status": "success", "message": f"Tasks {action}ed"}

                    if action == "add":
                        # Multi-step plan created. Yield and break turn loop to wait for user approval.
                        yield {
                            "type": "message",
                            "role": "agent",
                            "content": "I've created a plan for this request. Please review the plan above. Shall I proceed?"
                        }
                        # We must append the tool result to history or LLM might get confused in next turn
                        messages_append = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": json.dumps(result)
                        }
                        self.history.append(messages_append)
                        return # Exit the entire run_agent loop to force user interaction
                else:
                    yield {"type": "thought", "content": f"Executing process: {tool_name}..."}
                    
                    yield {
                        "type": "tool_call",
                        "name": tool_name,
                        "args": tool_args
                    }

                    try:
                        # Security Check
                        tool_hash = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                        is_sensitive = mcp_manager.is_sensitive(tool_name, tool_args)
                        
                        # Init state just in case
                        if not hasattr(self, "approved_hashes"): self.approved_hashes = set()
                        if not hasattr(self, "trusted_tools"): self.trusted_tools = set()
                        
                        if is_sensitive and tool_name not in self.trusted_tools and tool_hash not in self.approved_hashes:
                            # Mark as pending
                            self.pending_hashes.add(tool_hash)
                            
                            # Instruct LLM to ask user
                            result = "SYSTEM_REQUIREMENT: You must explain what this command does and ask the user for explicit permission to run it (e.g. 'I need to run bash... Is that ok?'). Do not run the command again until the user says yes. stop_and_ask_user()"
                            
                            yield {"type": "thought", "content": f"🔒 Permission required for {tool_name}. Asking user..."}
                            
                            # Return result to model so it can ask
                            yield {
                                "type": "tool_result",
                                "name": tool_name,
                                "content": result
                            }

                            messages_append = {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_name,
                                "content": json.dumps(result)
                            }
                            self.history.append(messages_append)
                            continue
                        
                        # Execute Tool
                        result = await mcp_manager.call_tool(tool_name, tool_args)
                    except Exception as e:
                        logger.error(f"Tool Execution Error: {str(e)}")
                        yield {"type": "thought", "content": f"❌ Error in {tool_name}: {str(e)}"}
                        result = f"Error: {str(e)}"
                
                yield {
                    "type": "tool_result",
                    "name": tool_name,
                    "content": result
                }

                messages_append = {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": json.dumps(result)
                }
                self.history.append(messages_append)

        await memory.add_memory(user_text, {"type": "user_query"})

agent = GokuAgent()
