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
            "built-in search tools (prefixed with 'mcp_search__') FIRST. These are your configured search providers "
            "(DuckDuckGo, Brave, Google). Only fall back to bash with curl if the search tools fail or are unavailable.\n"
            "9. THOUGHT PROCESS: You MUST think step-by-step before answering or taking action. "
            "START YOUR RESPONSE WITH A <thought> BLOCK. "
            "Enclose your internal reasoning in <thought>...</thought> tags. "
            "The user will see these thoughts in real-time to understand your process. "
            "Even for simple greetings, use a brief thought block (e.g. <thought>User said hi, I should greet back warmly.</thought>)."
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
        # yield {"type": "thought", "content": "Searching vector memory for relevant context..."}
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
        # yield {"type": "thought", "content": "Checking available MCP tools (Git, Search, Shell)..."}
        all_tools = await mcp_manager.get_all_tools()
        
        # yield {"type": "thought", "content": "Routing to best model (Hybrid Online/Offline)..."}

        # 3. Execution Loop
        yield {"type": "thought", "content": "..."}
        
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
                response_stream = await router.get_response(
                    model=self.model_override or "default",
                    messages=self.history, 
                    tools=llm_tools if llm_tools else None,
                    stream=True
                )
            except Exception as e:
                logger.error(f"Routing Error: {str(e)}")
                yield {"type": "thought", "content": f"⚠️ System Switch: {str(e)}"}
                raise e
            
            # Streaming Loop
            full_content = ""
            tool_calls_accumulator = {} # index -> tool_call object
            
            # State tracking for thought parsing
            inside_thought = False
            thought_buffer = ""
            
            async for chunk in response_stream:
                if not chunk.choices: continue
                
                delta = chunk.choices[0].delta
                
                # 1. Handle Text Content with <thought> parsing
                if hasattr(delta, "thinking") and delta.thinking:
                    thought_buffer += delta.thinking
                    yield {"type": "thought", "content": thought_buffer}

                if delta.content:
                    text_chunk = delta.content
                    full_content += text_chunk
                    
                    # Robust State Machine for Tags
                    # Support both <thought> (our prompt) and <think> (DeepSeek/Ollama native)
                    
                    combined = thought_buffer + text_chunk if inside_thought else text_chunk
                    
                    # Check for opening tags
                    start_tag = None
                    if "<thought>" in text_chunk: start_tag = "<thought>"
                    elif "<think>" in text_chunk: start_tag = "<think>"
                    
                    if not inside_thought and start_tag:
                        inside_thought = True
                        pre, post = text_chunk.split(start_tag, 1)
                        # pre is message content, post is thought start
                        thought_buffer = post
                        text_chunk = "" # Consumed
                        
                    # Check for closing tags
                    end_tag = None
                    if "</thought>" in combined: end_tag = "</thought>"
                    elif "</think>" in combined: end_tag = "</think>"
                    
                    if inside_thought and end_tag and end_tag in combined:
                        inside_thought = False
                        pre, post = combined.split(end_tag, 1)
                        
                        # Yield the final thought content
                        if pre:
                            yield {"type": "thought", "content": pre}
                        
                        thought_buffer = ""
                        # post is message content
                        text_chunk = post
                        # combined is consumed
                    
                    if inside_thought:
                        # Append new chunk to buffer and yield
                        if text_chunk:
                            thought_buffer += text_chunk
                            yield {"type": "thought", "content": thought_buffer}
                    else:
                        pass
                
                # 2. Handle Tool Calls (Accumulate parts)
                if delta.tool_calls:
                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index
                        if idx not in tool_calls_accumulator:
                            tool_calls_accumulator[idx] = {
                                "id": tc_chunk.id,
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            }
                        
                        # Append pieces
                        if tc_chunk.id: 
                            tool_calls_accumulator[idx]["id"] = tc_chunk.id
                        if tc_chunk.function.name:
                            tool_calls_accumulator[idx]["function"]["name"] += tc_chunk.function.name
                        if tc_chunk.function.arguments:
                            tool_calls_accumulator[idx]["function"]["arguments"] += tc_chunk.function.arguments

            # Clean content for history: Remove <thought> tags?
            # Ideally we keep them for context, or remove them to save tokens/clean history.
            # Let's keep them so the model has context of its own reasoning.
            
            # Reconstruct full response object for history
            final_tool_calls = []
            if tool_calls_accumulator:
                # Sort by index to maintain order
                sorted_indices = sorted(tool_calls_accumulator.keys())
                for idx in sorted_indices:
                    tc = tool_calls_accumulator[idx]
                    # Create object resembling litellm tool call
                    tool_obj = type('tool_call', (), {
                        'id': tc['id'],
                        'type': 'function',
                        'function': type('func', (), {
                            'name': tc['function']['name'],
                            'arguments': tc['function']['arguments']
                        })()
                    })()
                    final_tool_calls.append(tool_obj)

            # Create message dict for history
            msg_dict = {
                "role": "assistant",
                "content": full_content,
            }
            if final_tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    } for tc in final_tool_calls
                ]
            
            self.history.append(msg_dict)
            content = full_content
            
            # clean_content for UI display (strip thoughts)
            import re
            # Regex improves to catch unclosed tags at end of string
            clean_content = re.sub(r'<(thought|think)>.*?(</\1>|$)', '', full_content, flags=re.DOTALL).strip()
            
            # Map final_tool_calls back to what the loop expects
            # Create a mock msg_response object to minimize refactoring downstream logic
            class MockMessage:
                 def __init__(self, content, tool_calls):
                      self.content = content
                      self.tool_calls = tool_calls
            
            msg_response = MockMessage(clean_content, final_tool_calls)

            if not msg_response.tool_calls:
                # No tool calls — is this a final answer or mid-execution narration?
                if turn == 0 or not clean_content:
                    # First turn or empty response — this is a final answer
                    if clean_content:
                        yield {
                            "type": "message",
                            "role": "agent",
                            "content": clean_content
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
                    is_question = "?" in clean_content and len(clean_content) < 200 # Heuristic for a short question
                    
                    if has_pending_permission or is_question:
                        # Legitimate question or permission request — let the user respond
                        if clean_content:
                            yield {
                                "type": "message",
                                "role": "agent",
                                "content": clean_content
                            }
                        break
                    
                    # Progress narration (e.g. "Let me try a different approach")
                    # Yield as a thought so it stays in the Thinking panel
                    if clean_content:
                        yield {
                            "type": "thought",
                            "content": clean_content
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
                if clean_content:
                    yield {
                        "type": "message",
                        "role": "agent",
                        "content": clean_content
                    }
                
                # If there's a question, stop and wait for answer BEFORE running tools
                is_question = "?" in clean_content and len(clean_content) < 400
                if is_question:
                    # Append a hint to history so the model knows it's waiting
                    self.history.append({
                        "role": "user", 
                        "content": "[SYSTEM: Waiting for user response to the above question before proceeding with tools.]"
                    })
                    break

            # Prep for tool processing: Prioritize planning.
            # If the model sends multiple tools (e.g. bash + manage_tasks), we MUST
            # execute the plan first and ignore the others to wait for approval.
            tool_calls = msg_response.tool_calls
            
            def get_tool_action(tc):
                try:
                    args = tc.function.arguments
                    if isinstance(args, str):
                        data = json.loads(args)
                        if isinstance(data, str): # Double encoded
                            data = json.loads(data)
                        return data.get("action")
                    return args.get("action")
                except:
                    return None

            planning_call = next((tc for tc in tool_calls if tc.function.name == "manage_tasks" and get_tool_action(tc) == "add"), None)
            
            # If we are planning, only process the planning call and stop.
            active_tool_calls = [planning_call] if planning_call else tool_calls

            for tool_call in active_tool_calls:
                tool_name = tool_call.function.name
                
                # Robust argument parsing
                try:
                    raw_args = tool_call.function.arguments
                    tool_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    # If it's still a string after one jump (double encoded), jump again
                    if isinstance(tool_args, str):
                        tool_args = json.loads(tool_args)
                    if not isinstance(tool_args, dict):
                        tool_args = {}
                except Exception as e:
                    logger.error(f"Failed to parse tool args: {e}")
                    tool_args = {}

                if tool_name == "manage_tasks":
                    action = tool_args.get("action")
                    if action == "add":
                        new_tasks = tool_args.get("tasks", [])
                        self.tasks.extend(new_tasks)
                    elif action == "update":
                        idx = tool_args.get("index")
                        status = tool_args.get("status")
                        if isinstance(idx, int) and 0 <= idx < len(self.tasks):
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
