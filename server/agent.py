import json
from server.config_manager import config_manager as config_mgr
import logging
import asyncio
import os
from typing import List, Dict, Any, AsyncGenerator
from server.lite_router import router
from server.mcp_manager import mcp_manager
from server.memory import memory
from server.openclaw_ingestor import OpenClawIngestor

logger = logging.getLogger(__name__)

class GokuAgent:
    async def get_models(self, provider: str = None):
        return await router.get_available_models(provider)

    def __init__(self):
        self.system_prompt = (
            "You are GOKU — a high-performance AI terminal agent built for precise execution, "
            "intelligent planning, and resilient problem solving.\n\n"

            "You operate as an autonomous collaborator whose goal is to complete user objectives "
            "efficiently, safely, and with minimal user effort.\n\n"

            "━━━━━━━━━━━━━━━━━━\n"
            "CORE OPERATING PRINCIPLES\n"
            "━━━━━━━━━━━━━━━━━━\n\n"

            "1️⃣ PERSISTENCE & RECOVERY\n"
            "• Never stop after the first failure.\n"
            "• If a command fails, investigate using tools like `pwd`, `ls`, or `find`.\n"
            "• Try at least THREE logical recovery approaches before asking the user for help.\n\n"

            "2️⃣ PLAN BEFORE EXECUTION (MANDATORY)\n"
            "For ANY multi-step or complex request:\n"
            "• FIRST create a plan using `manage_tasks`.\n"
            "• Present the plan clearly.\n"
            "• STOP and wait for user approval.\n"
            "• DO NOT execute tasks until approval is received.\n\n"
            "Execution may proceed immediately ONLY for simple, single-step tasks.\n\n"

            "3️⃣ EXECUTION DISCIPLINE\n"
            "• Act immediately using tools when action is required.\n"
            "• Do NOT narrate intentions without executing.\n"
            "• Continue execution until:\n"
            "  - the task is complete\n"
            "  - approval is required\n"
            "  - permission is required\n"
            "  - critical ambiguity blocks progress\n\n"

            "4️⃣ SMART ENVIRONMENT ORIENTATION\n"
            "If system structure is unknown:\n"
            "• run `whoami` and `pwd`\n"
            "• verify paths before using them\n"
            "• never assume filesystem structure\n\n"

            "5️⃣ SAFETY & PERMISSIONS\n"
            "• The system enforces permission checks automatically.\n"
            "• Execute operations directly unless the security layer requests approval.\n"
            "• If approval is required, clearly explain the action and ask the user.\n\n"

            "6️⃣ MINIMIZE USER EFFORT\n"
            "• Take full ownership of research and execution.\n"
            "• Chain tool usage intelligently.\n"
            "• Avoid making the user perform steps you can do.\n\n"

            "7️⃣ TOOL & SEARCH PRIORITY\n"
            "When information is needed:\n"
            "1. Use configured search tools (`mcp_search__*`) first.\n"
            "2. Use alternative tools if necessary.\n"
            "3. Use shell/curl only as a fallback.\n\n"

            "8️⃣ TOOL FAILURE STRATEGY\n"
            "If a tool fails:\n"
            "• retry with adjusted parameters\n"
            "• try alternative tools\n"
            "• attempt another logical approach\n"
            "• escalate only after multiple failures\n\n"

            "9️⃣ THOUGHTFUL REASONING\n"
            "Think step-by-step before acting.\n"
            "Use brief reasoning only when clarity is needed.\n"
            "Avoid long internal explanations.\n\n"

            "🔟 CLEAR & VISIBLE PLANNING\n"
            "When presenting plans:\n"
            "• use headers, bullets, and separators\n"
            "• ensure tasks are readable and visible\n"
            "• reduce formatting only if the user requests less verbosity\n\n"

            "11️⃣ LOOP & STALL AWARENESS\n"
            "If progress stalls or actions repeat:\n"
            "• stop immediately\n"
            "• break the loop\n"
            "• ask the user for clarification\n"
            "• deliver the requested output instead of repeating actions\n\n"

            "12️⃣ SELF-CORRECTION\n"
            "If you make a mistake:\n"
            "• acknowledge briefly\n"
            "• correct immediately\n"
            "• continue without unnecessary apologies\n\n"

            "13️⃣ USER INTENT PRIORITY\n"
            "System guardrails guide behavior, but the user’s objective always takes priority.\n"
            "If instructions conflict with the user's goal, prioritize fulfilling the request safely.\n\n"

            "14️⃣ EFFICIENCY & FOCUS\n"
            "• Prefer efficient tools and minimal steps.\n"
            "• Avoid redundant actions.\n"
            "• Avoid unnecessary verbosity.\n\n"

            "15️⃣ FILE ANALYSIS & FEEDBACK\n"
            "When the user sends a file (image, video, document, etc.) for analysis:\n"
            "• NEVER just reply 'done', 'finished', 'analysis complete', or 'Waiting for your next request'.\n"
            "• Provide a natural, insightful summary of what the file contains.\n"
            "• If the user sent ONLY a file with no message, analyze it and RESPOND CONVERSATIONALLY:\n"
            "  - Describe what you see/found (e.g. 'This looks like a Python script that handles user authentication...')\n"
            "  - EXPECT TO CONTINUE THE CONVERSATION. Ask a specific question about what you just analyzed (e.g. 'Do you want me to refactor this script?' or 'Should I explain how the login flow works?').\n"
            "• NEVER use generic robotic sign-offs like 'Let me know if you need anything else' or 'Waiting for instructions'. Take the initiative.\n"
            "• If the user sent a file WITH a message, address their specific request.\n"
            "• FOR IMAGES: You have Native Vision capabilities! Never try to write Python scripts (like pytesseract or OpenCV) to 'see' an image. You can see it natively. Only use python scripts for image manipulation, NOT for basic viewing or reading text.\n"
            "• FOR VIDEOS/DOCS: Use native Python libraries (e.g. cv2, PyPDF2, pdfplumber) to parse content over slow bash commands.\n"
            "• If the analysis will take a while, output a message FIRST (e.g. '⏳ Analyzing your file...') to let the user know.\n\n"
            
            "16️⃣ COMPLETION CRITERIA\n"
            "Continue working until:\n"
            "✔ the objective is complete\n"
            "✔ the user requests a stop\n"
            "✔ approval or clarification is required\n\n"

            "**CONVERSATIONAL COMPLETION (CRITICAL)**:\n"
            "• NEVER just reply 'done', 'finished', 'complete', 'fixed', or 'resolved'.\n"
            "• ALWAYS provide a brief, conversational summary of what was accomplished.\n"
            "• Example Good: 'I've checked the directory and found the `uploads` folder as requested.'\n"
            "• Example Bad: 'Finished.' or 'Done.'\n"
            "• NEVER say 'Waiting for your next request'. Just provide the result naturally.\n\n"
            
            "17️⃣ CLARIFICATION & AMBIGUITY\n"
            "• If a user request is missing critical information, ASK for it immediately.\n"
            "• If you don't understand a message, state what you're confused about and ask for clarification.\n"
            "• **PAUSE & RESUME**: It is perfectly fine to stop mid-execution (after any tool call) if you reach a point where you need user input to proceed. Your history is preserved, so you can continue the task seamlessly once the user responds.\n"
            "• When asking for clarification, be specific about what you need (e.g., 'Which directory should I check?' or 'Should I overwrite the existing file?').\n\n"

            "18️⃣ GREETINGS VS COMMANDS\n"
            "• Treat brief, ambiguous words like 'man', 'bro', 'yo', 'hi', or 'hey' as **GREETINGS or SLANG**, not as Linux commands (e.g., do not run the `man` command unless the user explicitly asks for a manual page).\n"
            "• If a user input overlaps with a technical term but lacks context, prioritize a conversational response or ask for clarification.\n\n"

            "19️⃣ NEVER ASSUME (STRICT RULE)\n"
            "• **NEVER ASSUME** the user's intent if the message is ambiguous.\n"
            "• If you have ANY doubt about what the user wants, you MUST ask for clarification before taking any action.\n"
            "• Guessing the user's intent is a failure. Clarifying is a success.\n\n"

            "Your mission: execute intelligently, recover gracefully, and deliver complete results with minimal friction."
        )

        self.history: List[Dict[str, Any]] = []
        self.tasks: List[Dict[str, str]] = []
        self.model_override: str | None = None

        # Loop detection
        self._system_instruction_count: int = 0
        self._last_response_hash: str | None = None
        self._loop_detected: bool = False

        # Narration tracking
        self._narration_retries: int = 0
        self._current_thought: str = ""

        # Security state
        self.approved_hashes: set[str] = set()
        self.pending_hashes: set[str] = set()
        self.trusted_tools: set[str] = set()

        # Self-correction memory: store lessons learned
        self._lessons_learned: List[Dict[str, str]] = []

    def clear_history(self):
        self.history = []
        self.tasks = []
        self._system_instruction_count = 0
        self._last_response_hash = None
        self._loop_detected = False

    def _format_plan(self, tasks: List[Dict[str, str]]) -> str:
        """Always returns highly formatted plan with headers, emojis, tables."""
        if not tasks:
            return "No tasks planned."
        
        lines = ["\n---\n", "## 📋 TASK PLAN\n", "---\n"]
        
        # Status emojis
        status_emoji = {"todo": "⏳", "in_progress": "🔄", "done": "✅"}
        
        # Create table
        lines.append("| # | Status | Task |")
        lines.append("|---|--------|------|")
        
        for i, task in enumerate(tasks):
            status = task.get("status", "todo")
            desc = task.get("desc", task.get("title", "Untitled"))
            emoji = status_emoji.get(status, "⏳")
            lines.append(f"| {i+1} | {emoji} {status} | {desc} |")
        
        lines.append("\n---\n")
        return "\n".join(lines)

    def _format_task_update(self, tasks: List[Dict[str, str]]) -> str:
        """Format task list for display with enhanced visibility."""
        return self._format_plan(tasks)

    def _detect_loop(self, content: str, tool_calls: list) -> bool:
        """Detect if we're stuck in a system instruction loop."""
        import hashlib
        
        # Create hash of current response
        current_hash = hashlib.md5((content + str(len(tool_calls) if tool_calls else 0)).encode()).hexdigest()
        
        # Check for repeated responses
        if current_hash == self._last_response_hash:
            self._system_instruction_count += 1
        else:
            self._system_instruction_count = 0
            self._last_response_hash = current_hash
        
        # If we've repeated 2+ times, we're in a loop
        if self._system_instruction_count >= 2:
            self._loop_detected = True
            return True
        
        return False

    def _add_lesson(self, lesson: str, context: str = ""):
        """Store a lesson learned for future reference."""
        self._lessons_learned.append({
            "lesson": lesson,
            "context": context
        })
        logger.info(f"Lesson learned: {lesson}")

    def _get_environment_context(self, source: str) -> str:
        """Build environment-specific system prompt additions based on the interface."""
        import datetime
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")
        
        base = (
            "\n━━━━━━━━━━━━━━━━━━\n"
            "ENVIRONMENT & TIME AWARENESS\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"🕒 CURRENT LOCAL TIME: {current_time}\n\n"
        )

        sandboxing = (
            "🔒 SANDBOXING, CLARIFICATION & SCHEDULING RULES:\n"
            "• Before executing any command that modifies files, installs packages, or changes system state, "
            "briefly confirm your understanding of the user's intent.\n"
            "• If the user's request is ambiguous or you are unsure about scope, ASK for clarification BEFORE executing.\n"
            "• Never assume destructive intent — prefer the safest interpretation.\n"
            "• Always state what you are about to do before doing it for impactful operations.\n"
            "• SCHEDULING: If asked to schedule a task/reminder, use the `bash` tool (e.g. `at`, `cron`, or background `sleep`) to execute it. Note that Telegram bots cannot proactively message the user from a background bash script easily, so warn the user if scheduling notifications via Telegram.\n\n"
        )

        if source == "cli":
            env = (
                "📍 CURRENT INTERFACE: CLI Terminal\n"
                "• The user is interacting via an interactive terminal session.\n"
                "• You have full access to bash, file tools, and all MCP tools.\n"
                "• Output is rendered with Rich markdown — use headers, bold, tables, and code blocks freely.\n"
                "• The user can see real-time tool execution and thinking updates.\n\n"
            )
        elif source == "web":
            env = (
                "📍 CURRENT INTERFACE: Web Dashboard\n"
                "• The user is interacting via the Goku Web Dashboard in a browser.\n"
                "• You have full access to bash, file tools, and all MCP tools.\n"
                "• Output is rendered as HTML/markdown — use headers, bold, code blocks, and formatting.\n"
                "• The user can see a split view with your responses and an intelligence/thinking log panel.\n\n"
            )
        elif source == "telegram":
            env = (
                "📍 CURRENT INTERFACE: Telegram Messenger\n"
                "• The user is chatting via Telegram — a mobile messaging app.\n"
                "• You still have full access to bash, file tools, and MCP tools.\n"
                "• Your output will be auto-converted to Telegram MarkdownV2 for rich formatting.\n\n"
                "📝 TELEGRAM FORMATTING GUIDELINES:\n"
                "• Use **bold text** for emphasis and section headers (e.g. **🔧 Setup**).\n"
                "• Use bullet points (- or •) for lists — they render cleanly on mobile.\n"
                "• Use `inline code` for commands, file names, and technical terms.\n"
                "• Use fenced code blocks (```) for code snippets — keep them short.\n"
                "• Use emoji as section labels (🔍, ✅, ⚠️, 💡) to improve scannability.\n"
                "• Keep paragraphs short (2-3 sentences max) for mobile readability.\n"
                "• AVOID markdown tables — they don't render in Telegram. Use bullet lists instead.\n"
                "• AVOID deeply nested formatting or complex markdown structures.\n"
                "• Messages over 4096 characters will be split, so be concise when possible.\n"
                "• The user may be on mobile — be extra clear and ask for confirmation before multi-step operations.\n\n"
            )
        else:
            env = (
                f"📍 CURRENT INTERFACE: {source}\n"
            "• Interface type is unknown — adapt formatting to be universally readable.\n\n"
            )

        return base + env + sandboxing

    async def run_agent(self, user_text: str, source: str = "cli") -> AsyncGenerator[Dict[str, Any], None]:
        """Runs the agent loop and yields thoughts, messages, and tool results.
        
        Args:
            user_text: The user's input message.
            source: The interface source — 'cli', 'web', or 'telegram'.
        """
        if not user_text:
            return

        self._narration_retries = 0  # Reset per-query
        self._current_thought = ""   # Reset thought buffer for this query
        self._system_instruction_count = 0  # Reset loop detection
        self._loop_detected = False

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
        
        # Include lessons learned in context
        if self._lessons_learned:
            lessons_context = "\n".join([f"- {l['lesson']}" for l in self._lessons_learned[-5:]])  # Last 5 lessons
            context_str = json.dumps(context) + f"\n\nRecent Lessons Learned:\n{lessons_context}"
        else:
            context_str = json.dumps(context)
        
        # Build environment-aware system prompt
        env_context = self._get_environment_context(source)
        full_system_prompt = f"{self.system_prompt}\n\n{env_context}\n\nRetrieved Context: {context_str}"
        
        # Ensure we have a system message if history is empty
        if not self.history:
            self.history.append({"role": "system", "content": full_system_prompt})
        else:
            # Update the existing system message if it exists
            if self.history[0]["role"] == "system":
                self.history[0]["content"] = full_system_prompt

        # Parse potential image attachments for Vision models
        import re
        import base64
        import mimetypes
        import os
        
        photo_pattern = r'\[Photo Received:\s*(.+?)\]'
        photos = re.findall(photo_pattern, user_text)
        
        if photos:
            content_array = []
            clean_text = re.sub(photo_pattern, '', user_text).strip()
            
            # Keep track of file paths so LLM knows what it's looking at
            paths_text = " ".join([f"[Image File: {p}]" for p in photos])
            
            if not clean_text:
                clean_text = f"Please analyze this image. {paths_text}"
            else:
                clean_text = f"{paths_text}\n{clean_text}"
            
            content_array.append({"type": "text", "text": clean_text})
            
            for path in photos:
                if os.path.exists(path):
                    mime_type, _ = mimetypes.guess_type(path)
                    mime_type = mime_type or 'image/jpeg'
                    try:
                        # Resize the image to prevent payload size limit errors
                        from PIL import Image
                        import io
                        
                        max_dimension = 800
                        with Image.open(path) as img:
                            # Convert to RGB if necessary (e.g. for PNGs with transparency)
                            if img.mode != 'RGB':
                                img = img.convert('RGB')
                                
                            # Resize if it's too large, keeping aspect ratio
                            if img.width > max_dimension or img.height > max_dimension:
                                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                                
                            # Save back to a buffer
                            buffer = io.BytesIO()
                            img.save(buffer, format="JPEG", quality=85)
                            b64_img = base64.b64encode(buffer.getvalue()).decode('utf-8')
                            mime_type = "image/jpeg"
                            
                        content_array.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{b64_img}"}
                        })
                    except Exception as e:
                        logger.error(f"Failed to load image for vision: {e}")
                        content_array.append({"type": "text", "text": f"[Error loading image: {path}]"})
            
            self.history.append({"role": "user", "content": content_array})
        else:
            self.history.append({"role": "user", "content": user_text})
        
        # 2. MCP & Model Routing
        # yield {"type": "thought", "content": "Checking available MCP tools (Git, Search, Shell)..."}
        all_tools = await mcp_manager.get_all_tools()
        
        # yield {"type": "thought", "content": "Routing to best model (Hybrid Online/Offline)..."}

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

        # Add Telegram-specific tools
        if source == "telegram":
            llm_tools.append({
                "type": "function",
                "function": {
                    "name": "schedule_telegram_message",
                    "description": "Schedule a message to be sent via Telegram in the future. EXCLUSIVE to Telegram interface. Use this INSTEAD of bash sleep/at commands for scheduling.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "delay_seconds": {
                                "type": "number",
                                "description": "The number of seconds from now to send the message. Max 1 year."
                            },
                            "message_text": {
                                "type": "string",
                                "description": "The exact message to send to the user."
                            }
                        },
                        "required": ["delay_seconds", "message_text"]
                    }
                }
            })
            llm_tools.append({
                "type": "function",
                "function": {
                    "name": "send_telegram_file",
                    "description": "Send a local file from the server directly to the user over Telegram. Use this when the user asks for a file, script, or document you generated.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "The absolute or relative path to the file you want to send."
                            },
                            "caption": {
                                "type": "string",
                                "description": "Optional text to send along with the file."
                            }
                        },
                        "required": ["file_path"]
                    }
                }
            })

        # Load skills from the skills directory
        try:
            # Assuming the project root is current working directory
            ingestor = OpenClawIngestor(os.getcwd())
            skill_tools = ingestor.generate_tool_definitions()
            for st in skill_tools:
                # Skill tools might have additional instructions in st['instructions']
                # We can append these to the system prompt or handle them separately
                llm_tools.append({
                    "type": st["type"],
                    "function": st["function"]
                })
                logger.info(f"Loaded skill tool: {st['function']['name']}")
        except Exception as e:
            logger.error(f"Failed to load skills: {e}")

        max_turns = 50 
        for turn in range(max_turns):
            if turn == 0:
                yield {"type": "thought", "content": "..."}
            # Retry loop for automatic reconnection
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Choose model based on whether vision is required
                    target_model = self.model_override or "default"
                    if photos:
                        vision_override = config_mgr.get_key("GOKU_VISION_MODEL", "")
                        if vision_override:
                            target_model = vision_override
                            
                    response_stream = await router.get_response(
                        model=target_model,
                        messages=self.history, 
                        tools=llm_tools if llm_tools else None,
                        stream=True
                    )
                    break # Success, exit retry loop
                except Exception as e:
                    import asyncio
                    error_msg = str(e).strip()
                    logger.error(f"Routing Error (Attempt {attempt+1}/{max_retries}): {error_msg}")
                    
                    if attempt < max_retries - 1:
                        yield {"type": "thought", "content": f"⚠️ Network/API issue ({error_msg}). Retrying in 5 seconds..."}
                        await asyncio.sleep(5)
                    else:
                        yield {"type": "thought", "content": f"❌ Connection failed after {max_retries} attempts."}
                        
                        # INJECT ERROR INTO HISTORY so the model is aware next turn
                        self.history.append({
                            "role": "system",
                            "content": f"[SYSTEM NOTIFICATION: A network or API error occurred while trying to process your last action. Error details: {error_msg}. Acknowledge this issue to the user and ask if they'd like you to try again or take a different approach.]"
                        })
                        
                        # Yield simple error message to user instead of raising stack trace
                        yield {
                            "type": "message",
                            "role": "agent",
                            "content": f"I ran into a technical issue: {error_msg}. I've saved the context of this error."
                        }
                        return # Gracefully terminate generator
            
            # Streaming Loop
            full_content = ""
            tool_calls_accumulator = {} # index -> tool_call object
            
            # Rolling Buffer Parser
            import re
            
            async for chunk in response_stream:
                if not chunk.choices: continue
                delta = chunk.choices[0].delta
                
                # 1. Handle Native Thinking (Ollama think=True)
                if hasattr(delta, "thinking") and delta.thinking:
                    self._current_thought += delta.thinking
                    yield {"type": "thought", "content": self._current_thought}

                # 2. Handle Text Content with <thought> tags
                if delta.content:
                    text_chunk = delta.content
                    full_content += text_chunk
                    
                    # Regex to find all thought blocks
                    pattern = r'<(thought|think)>(.*?)(?:</\1>|$)'
                    matches = list(re.finditer(pattern, full_content, re.DOTALL))
                    
                    if matches:
                        last_match = matches[-1]
                        # Is the last tag closed?
                        is_closed = f"</{last_match.group(1)}>" in full_content[last_match.start():]
                        
                        # Current thinking is the content of the last tag
                        raw_thought = last_match.group(2)
                        
                        # SCRUBBER: Remove partial or full tags that leak into the buffer
                        # This prevents showing "</thou" or "<thought>" inside the thinking panel
                        scrubbed_thought = re.sub(r'</?(thought|think)>?.*$', '', raw_thought, flags=re.IGNORECASE).strip()
                        
                        if scrubbed_thought:
                            self._current_thought = scrubbed_thought
                            yield {"type": "thought", "content": self._current_thought}
                        
                        if is_closed:
                            # If tag is closed, message content might be starting
                            # But we don't yield 'message' events inside the loop to prevent flickering
                            pass
                    else:
                        # No tags found, everything is potentially message content
                        # We don't yield deltas here to keep the UI clean; 
                        # the turn-end logic will yield the final message.
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
                        
                        # Append pieces safely (some providers send None instead of '')
                        if getattr(tc_chunk, "id", None): 
                            tool_calls_accumulator[idx]["id"] = tc_chunk.id
                        
                        func = getattr(tc_chunk, "function", None)
                        if func:
                            if getattr(func, "name", None) and not tool_calls_accumulator[idx]["function"]["name"]:
                                tool_calls_accumulator[idx]["function"]["name"] = func.name
                            if getattr(func, "arguments", None):
                                tool_calls_accumulator[idx]["function"]["arguments"] += func.arguments

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
            
            # LOOP DETECTION: Check if we're stuck
            if self._detect_loop(clean_content, final_tool_calls):
                # Break out of the loop - ask user what they need
                yield {"type": "thought", "content": "⚠️ Loop detected - breaking out to ask user for guidance."}
                yield {
                    "type": "message",
                    "role": "agent",
                    "content": "I notice I may be stuck in a loop. What do you actually need from me right now?"
                }
                self._add_lesson("Loop detected and broken - user redirected", clean_content[:100])
                break
            
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
                    else:
                        # Provide a fallback message so the UI/Bot doesn't say "No textual output"
                        yield {
                            "type": "message",
                            "role": "agent",
                            "content": "I've completed the task as requested. Please let me know if you need anything else!"
                        }
                    break
                else:
                    # Mid-execution: is this a permission question, completion, or just progress narration?
                    has_pending_permission = hasattr(self, "pending_hashes") and self.pending_hashes
                    # Smarter question check: must contain a question mark
                    # We also allow longer questions now to capture detailed mid-task clarification requests
                    is_question = "?" in clean_content
                    # Check if this is a completion signal (Done/Fixed/Finished/etc.)
                    completion_markers = ["done", "finished", "complete", "completed", "fixed", "resolved", "ready", "all set"]
                    clean_lower = clean_content.lower().strip()
                    # Strip trailing punctuation for better matching
                    clean_lower_no_punct = clean_lower.rstrip('.!?')
                    is_completion = (
                        len(clean_content) < 100 and 
                        (clean_lower_no_punct in completion_markers or
                         any(clean_lower_no_punct == marker for marker in completion_markers))
                        and False # DISABLED: Force model to be more conversational even if it says "done"
                    )
                    
                    # Instead of a hard break on "Finished", we only break if it looks like a real ending
                    # or if the model has genuinely stopped streaming and we have content.
                    is_completion = False # Let the model's natural end or specific questions handle the break
                    
                    if has_pending_permission or is_question or is_completion:
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
                            "content": clean_content
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
                self._system_instruction_count = 0  # Reset loop detection on tool use
                if clean_content:
                    yield {
                        "type": "message",
                        "role": "agent",
                        "content": clean_content
                    }
                
                # If there's a question, stop and wait for answer BEFORE running tools
                # Refined: Only if it's a short question or ends with ?
                is_question = "?" in clean_content.strip()[-5:] and len(clean_content) < 400
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
                    logger.error(f"Failed to parse tool args via json.loads: {e}. Attempting recovery.")
                    tool_args = {}
                    
                    # Auto-recovery for malformed JSON from open-source models
                    import re
                    raw = str(raw_args)
                    
                    # Try to extract the two main args for schedule_telegram_message manually
                    if tool_name == "schedule_telegram_message":
                        try:
                            # Use regex to find delay_seconds (number) and message_text (string)
                            delay_match = re.search(r'"delay_seconds"\s*:\s*(\d+(\.\d+)?)', raw)
                            msg_match = re.search(r'"message_text"\s*:\s*"([^"]+)"', raw)
                            
                            if delay_match:
                                tool_args["delay_seconds"] = float(delay_match.group(1))
                            if msg_match:
                                tool_args["message_text"] = msg_match.group(1)
                                
                                tool_args = {} # Recovery failed
                        except Exception as regex_e:
                            logger.error(f"Regex recovery failed: {regex_e}")
                            
                    # If all recovery failed, inject the parsing error into history
                    if not tool_args and raw_args:
                        error_text = f"Failed to parse your JSON arguments for {tool_name}. Error: {e}. Raw input: {raw_args}"
                        logger.error(error_text)
                        
                        self.history.append({
                            "role": "system",
                            "content": f"[SYSTEM NOTIFICATION: {error_text}. Please fix your JSON formatting and try calling the tool again.]"
                        })
                        
                        # Tell user about the hiccup and let model retry next turn
                        yield {
                            "type": "thought",
                            "content": f"❌ JSON Parsing error on {tool_name}. Retrying..."
                        }
                        
                        # We skip executing this malformed tool
                        continue

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
                    
                    # Use formatted plan for visibility
                    formatted_plan = self._format_plan(self.tasks)
                    yield {"type": "task_update", "tasks": self.tasks}
                    result = {"status": "success", "message": f"Tasks {action}ed", "formatted": formatted_plan}

                    if action == "add":
                        # Multi-step plan created. Yield and break turn loop to wait for user approval.
                        yield {
                            "type": "message",
                            "role": "agent",
                            "content": f"I've created a plan for this request. Please review the plan above. Shall I proceed?{formatted_plan}"
                        }
                        # We must append the tool result to history or LLM might get confused in next turn
                        messages_append = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": json.dumps(result)
                        }
                        self.history.append(messages_append)
                        
                        # Yield the result to UI as well
                        yield {
                            "type": "tool_result",
                            "name": tool_name,
                            "content": result
                        }
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
                            
                            yield {"type": "thought", "content": f"🔐 Permission required for {tool_name}. Asking user..."}
                            
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
                        if tool_name == "schedule_telegram_message":
                            from server import telegram_bot
                            result = await telegram_bot.schedule_telegram_message(tool_args)
                        elif tool_name.startswith("openclaw_"):
                            is_agent_tool = tool_name.startswith("openclaw_agent_")
                            skill_name = tool_name.replace("openclaw_agent_", "").replace("openclaw_skill_", "")
                            user_intent = tool_args.get("user_intent", "")
                            
                            # Find the skill instructions
                            ingestor = OpenClawIngestor(os.getcwd())
                            # Search both for the specific skill name
                            skill_info = {}
                            for meta in ingestor.list_skills():
                                if meta["name"] == skill_name:
                                    skill_info = ingestor.parse_skill(skill_name, meta["path"])
                                    break
                            
                            instructions = skill_info.get("instructions", "")

                            # Spawn background task
                            asyncio.create_task(self.run_subagent_background(skill_name, instructions, user_intent, source))
                            
                            type_label = "Agent" if is_agent_tool else "Skill"
                            result = {
                                "status": "dispatched",
                                "message": f"{type_label} @{skill_name} has been summoned and is working in the background. I will notify you when it reports back."
                            }
                            yield {"type": "thought", "content": f"🚀 Dispatched {type_label} @{skill_name}..."}
                        else:
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

    async def run_subagent_background(self, skill_name: str, instructions: str, user_intent: str, source: str):
        """Runs a sub-agent in the background and reports results back to the main agent's history."""
        try:
            logger.info(f"Starting background sub-agent: @{skill_name}")
            # Create a fresh agent for the sub-task
            sub_agent = GokuAgent()
            # Specialization: Prepend skill instructions to the core GOKU prompt
            sub_agent.system_prompt = f"### 🤖 SPECIALIZED ROLE: @{skill_name}\n{instructions}\n\n" + sub_agent.system_prompt
            
            report_content = f"### 📊 Report from @{skill_name}\n\n"
            
            # Run the agent
            gen = sub_agent.run_agent(user_intent, source=source)
            try:
                while True:
                    event = await anext(gen)
                    if event["type"] == "message":
                        report_content += event["content"]
            except StopAsyncIteration:
                pass
            
            # Inject report into main history
            notification = f"[BACKGROUND REPORT FROM @{skill_name}]:\n{report_content}"
            self.history.append({
                "role": "system",
                "content": notification
            })
            
            logger.info(f"Sub-agent @{skill_name} finished. Injected into history.")

            # Notify user via Telegram if that was the source
            if source == "telegram":
                from server import telegram_bot
                await telegram_bot.send_telegram_notification(
                    f"✅ **@{skill_name} has finished its task!**\n\n{report_content}"
                )
                
        except Exception as e:
            logger.error(f"Error in background sub-agent @{skill_name}: {e}")
            self.history.append({
                "role": "system",
                "content": f"[SYSTEM ERROR]: Sub-agent @{skill_name} failed: {e}"
            })

agent = GokuAgent()
