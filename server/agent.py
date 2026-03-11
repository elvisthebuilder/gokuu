import json
from server.config_manager import config_manager as config_mgr # type: ignore
import logging
import asyncio
import os
import re # type: ignore
import base64 # type: ignore
import mimetypes # type: ignore
import datetime # type: ignore
import hashlib # type: ignore
from PIL import Image # type: ignore
import io
MAX_IMAGE_DIMENSION = 800
from typing import List, Dict, Any, AsyncGenerator, cast, Optional
from types import SimpleNamespace
from server.lite_router import router # type: ignore
from server.mcp_manager import mcp_manager # type: ignore
from server.memory import memory # type: ignore
from server.openclaw_ingestor import OpenClawIngestor # type: ignore

logger = logging.getLogger(__name__)

class GokuAgent:
    async def get_models(self, provider: str | None = None):
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
            "• avoid using 'silent' flags like `curl -s` unless output is truly irrelevant, as it blocks your ability to confirm success\n"
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

            "20️⃣ VOICE & AUDIO CAPABILITIES\n"
            "• You are powered by **ElevenLabs** for all Text-to-Speech (TTS) and Speech-to-Text (STT) operations.\n"
            "• Use the `mcp_voice__list_voices` and `mcp_voice__set_active_voice` tools to manage your voice persona.\n"
            "• Never suggest using legacy tools like `espeak`, `festival`, or `gtts`. Always use ElevenLabs.\n"
            "• When a user sends a voice note, your response will automatically be converted to a voice note if you were summoned via voice.\n\n"

            "Your mission: execute intelligently, recover gracefully, and deliver complete results with minimal friction."
        )

        self.histories: Dict[str, List[Dict[str, Any]]] = {}
        self.session_tasks: Dict[str, List[Dict[str, str]]] = {}
        self.model_override: str | None = None

        # Session-specific state tracking
        self.session_loop_data: Dict[str, Dict[str, Any]] = {}
        self.session_thoughts: Dict[str, str] = {}

        # Security state
        self.approved_hashes: set[str] = set()
        self.pending_hashes: set[str] = set()
        self.trusted_tools: set[str] = set()

        # Self-correction memory: store lessons learned
        self._lessons_learned: List[Dict[str, str]] = []

    def clear_history(self, session_id: str = "default"):
        self.histories[session_id] = []
        self.session_tasks[session_id] = []
        self.session_loop_data.pop(session_id, None)
        self.session_thoughts.pop(session_id, None)

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

    def _detect_loop(self, session_id: str, content: str, tool_calls: list) -> bool:
        """Detect if we're stuck in a system instruction loop for a specific session."""
        if session_id not in self.session_loop_data:
            self.session_loop_data[session_id] = {"count": 0, "hash": None}
            
        # Create hash of current response
        current_hash = hashlib.md5((content + str(len(tool_calls) if tool_calls else 0)).encode()).hexdigest()
        
        # Check for repeated responses
        if current_hash == self.session_loop_data[session_id]["hash"]:
            self.session_loop_data[session_id]["count"] += 1
        else:
            self.session_loop_data[session_id]["count"] = 0
            self.session_loop_data[session_id]["hash"] = current_hash
        
        # If we've repeated 2+ times, we're in a loop
        if self.session_loop_data[session_id]["count"] >= 2:
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

    async def _analyze_image_externally(self, path: str, provider: str) -> str:
        """Analyze an image using a dedicated external vision provider."""
        if not os.path.exists(path):
            return f"[Error: Image file not found at {path}]"
            
        try:
            # Prepare image data
            with Image.open(path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                if img.width > MAX_IMAGE_DIMENSION or img.height > MAX_IMAGE_DIMENSION:
                    img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
                
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85)
                b64_img = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            model = "gpt-4o" if provider == "openai" else config_mgr.get_key("GOKU_VISION_MODEL", "gemini/gemini-3-flash")
            
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this image in detail. Focus on text, objects, and overall context. Be concise but thorough."},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
                        }
                    ]
                }
            ]
            
            # Non-streaming call for description
            response = await router.get_response(model=model, messages=messages, stream=False)
            description = response.choices[0].message.content
            return description
        except Exception as e:
            logger.error(f"External vision error ({provider}): {e}")
            return f"[Error during external vision analysis: {e}]"

    async def run_agent(self, user_text: str, source: str = "cli", session_id: str = "default") -> AsyncGenerator[Dict[str, Any], None]:
        """Runs the agent loop and yields thoughts, messages, and tool results.
        
        Args:
            user_text: The user's input message.
            source: The interface source — 'cli', 'web', or 'telegram'.
            session_id: The ID for the conversation session (e.g. chat_id).
        """
        if not user_text:
            return

        # Initialize session state if first time
        if session_id not in self.histories:
            self.histories[session_id] = []
        if session_id not in self.session_tasks:
            self.session_tasks[session_id] = []
            
        self.session_thoughts[session_id] = ""   # Reset thought buffer for this query

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
            learned = cast(List[Dict[str, str]], self._lessons_learned)
            lessons_context = "\n".join([f"- {cast(Dict[str, str], l)['lesson']}" for l in cast(Any, learned)[-5:]])  # Last 5 lessons
            context_str = json.dumps(context) + f"\n\nRecent Lessons Learned:\n{lessons_context}"
        else:
            context_str = json.dumps(context)
        
        # Build environment-aware system prompt
        env_context = self._get_environment_context(source)
        full_system_prompt = f"{self.system_prompt}\n\n{env_context}\n\nRetrieved Context: {context_str}"
        
        # Ensure we have a system message if history is empty
        if not self.histories[session_id]:
            self.histories[session_id].append({"role": "system", "content": full_system_prompt})
        else:
            # Update the existing system message if it exists
            if self.histories[session_id][0]["role"] == "system":
                self.histories[session_id][0]["content"] = full_system_prompt

        # Local history reference for current loop
        history = self.histories[session_id]

        # Parse potential image attachments for Vision models
        photo_pattern = r'\[Photo Received:\s*(.+?)\]'
        photos = re.findall(photo_pattern, user_text) # type: ignore
        
        if photos:
            vision_provider = config_mgr.get_key("VISION_PROVIDER", "default").lower()
            content_array: List[Dict[str, Any]] = []
            clean_text = re.sub(photo_pattern, '', user_text).strip() # type: ignore
            
            # Keep track of file paths so LLM knows what it's looking at
            paths_text = " ".join([f"[Image File: {p}]" for p in photos])
            
            if not clean_text:
                clean_text = f"Please analyze this image. {paths_text}"
            else:
                clean_text = f"{paths_text}\n{clean_text}"
            
            content_array.append({"type": "text", "text": clean_text})
            
            for path in photos:
                if not os.path.exists(path):
                    content_array.append({"type": "text", "text": f"[Error: Image file not found: {path}]"})
                    continue

                if vision_provider in ["google", "openai"]:
                    # Offload vision to external dedicated provider
                    yield {"type": "thought", "content": f"📸 Analyzing image at {os.path.basename(path)} with {vision_provider.capitalize()}..."}
                    description = await self._analyze_image_externally(path, vision_provider)
                    content_array.append({"type": "text", "text": f"[Visual context from {vision_provider.capitalize()}: {description}]"})
                else:
                    # Native Vision: Send base64 to core model
                    mime_type, _ = mimetypes.guess_type(path)
                    mime_type = mime_type or 'image/jpeg'
                    try:
                        # Resize the image to prevent payload size limit errors
                        with Image.open(path) as img: # type: ignore
                            # Convert to RGB if necessary (e.g. for PNGs with transparency)
                            if img.mode != 'RGB':
                                img = img.convert('RGB')
                                
                            # Resize if it's too large, keeping aspect ratio
                            if img.width > MAX_IMAGE_DIMENSION or img.height > MAX_IMAGE_DIMENSION:
                                img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
                                
                            # Save back to a buffer
                            buffer = io.BytesIO() # type: ignore
                            img.save(buffer, format="JPEG", quality=85)
                            b64_img = base64.b64encode(buffer.getvalue()).decode('utf-8') # type: ignore
                            mime_type = "image/jpeg"
                            
                        content_array.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{b64_img}"}
                        })
                    except Exception as e:
                        logger.error(f"Failed to load image for vision: {e}")
                        content_array.append({"type": "text", "text": f"[Error loading image: {path}]"})
            
            history.append({"role": "user", "content": content_array})
        else:
            history.append({"role": "user", "content": user_text})
        
        # 2. MCP & Model Routing
        all_tools = await mcp_manager.get_all_tools()
        
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

        if source == "telegram":
            llm_tools.append({
                "type": "function",
                "function": {
                    "name": "schedule_telegram_message",
                    "description": "Schedule a message to be sent via Telegram in the future. EXCLUSIVE to Telegram interface. Use this INSTEAD of bash sleep/at commands for scheduling.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "delay_seconds": {"type": "number"},
                            "message_text": {"type": "string"}
                        },
                        "required": ["delay_seconds", "message_text"]
                    }
                }
            })
            llm_tools.append({
                "type": "function",
                "function": {
                    "name": "send_telegram_file",
                    "description": "Send a local file to the user over Telegram.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "caption": {"type": "string"}
                        },
                        "required": ["file_path"]
                    }
                }
            })

        llm_tools.append({
            "type": "function",
            "function": {
                "name": "see_image",
                "description": "Look at an image file stored locally.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "question": {"type": "string"}
                    },
                    "required": ["path"]
                }
            }
        })

        # Load skills
        try:
            ingestor = OpenClawIngestor(os.getcwd())
            skill_tools = ingestor.generate_tool_definitions()
            for st in skill_tools:
                llm_tools.append({"type": st["type"], "function": st["function"]})
        except Exception as e:
            logger.error(f"Failed to load skills: {e}")

        max_turns = 50 
        for turn in range(max_turns):
            if turn == 0: yield {"type": "thought", "content": "..."}
            max_retries = 3
            try:
                target_model = self.model_override or "default"
                if photos:
                    vision_override = config_mgr.get_key("GOKU_VISION_MODEL", "")
                    if vision_override: target_model = vision_override
                        
                response_stream = await router.get_response(
                    model=target_model,
                    messages=history, 
                    tools=llm_tools if llm_tools else None,
                    stream=True
                )
            except Exception as e:
                error_msg = str(e).strip()
                logger.error(f"Routing Error: {error_msg}")
                self.histories[session_id].append({
                    "role": "system",
                    "content": f"[SYSTEM ERROR: {error_msg}]"
                })
                yield {"type": "message", "role": "agent", "content": f"Technical issue: {error_msg}"}
                return
            
            full_content = ""
            tool_calls_accumulator: Dict[int, Any] = {}
            
            async for chunk in response_stream:
                if not chunk.choices: continue
                delta = chunk.choices[0].delta
                
                if hasattr(delta, "thinking") and delta.thinking:
                    thought = cast(str, delta.thinking)
                    self.session_thoughts[session_id] = self.session_thoughts.get(session_id, "") + thought
                    yield {"type": "thought", "content": self.session_thoughts[session_id]}

                if delta.content:
                    text_chunk = cast(str, delta.content)
                    full_content = str(full_content) + text_chunk
                    pattern = r'<(thought|think)>(.*?)(?:</\1>|$)'
                    matches = list(re.finditer(pattern, full_content, re.DOTALL)) # type: ignore
                    if matches:
                        last_match = matches[-1]
                        is_closed = f"</{last_match.group(1)}>" in cast(Any, full_content)[int(last_match.start()):]
                        scrubbed_thought = re.sub(r'</?(thought|think)>?.*$', '', last_match.group(2), flags=re.IGNORECASE).strip()
                        if scrubbed_thought:
                            self.session_thoughts[session_id] = scrubbed_thought
                            yield {"type": "thought", "content": self.session_thoughts[session_id]}
                
                if delta.tool_calls:
                    for tc_chunk in delta.tool_calls:
                        idx = int(tc_chunk.index)
                        if idx not in tool_calls_accumulator:
                            tool_calls_accumulator[idx] = {"id": tc_chunk.id, "type": "function", "function": {"name": "", "arguments": ""}}
                        
                        target_tc = cast(Dict[str, Any], tool_calls_accumulator[idx])
                        if tc_chunk.id: 
                            target_tc["id"] = tc_chunk.id
                        func = getattr(tc_chunk, "function", None)
                        if func:
                            target_func = cast(Dict[str, str], target_tc["function"])
                            if getattr(func, "name", None) and not target_func["name"]:
                                target_func["name"] = cast(str, func.name)
                            if getattr(func, "arguments", None):
                                arg_chunk = cast(str, func.arguments)
                                target_func["arguments"] = str(target_func["arguments"]) + arg_chunk

            final_tool_calls = []
            if tool_calls_accumulator:
                for idx in sorted(tool_calls_accumulator.keys()):
                    tc = tool_calls_accumulator[idx]
                    tool_obj = SimpleNamespace(
                        id=tc['id'],
                        type='function',
                        function=SimpleNamespace(
                            name=tc['function']['name'],
                            arguments=tc['function']['arguments']
                        )
                    )
                    final_tool_calls.append(tool_obj)

            msg_dict: Dict[str, Any] = {"role": "assistant", "content": full_content}
            if final_tool_calls:
                msg_dict["tool_calls"] = [{"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in final_tool_calls]
            
            self.histories[session_id].append(msg_dict)
            clean_content = re.sub(r'<(thought|think)>.*?(</\1>|$)', '', full_content, flags=re.DOTALL).strip() # type: ignore
            
            if self._detect_loop(session_id, clean_content, final_tool_calls):
                yield {"type": "thought", "content": "⚠️ Loop detected - breaking."}
                yield {"type": "message", "role": "agent", "content": "I notice I may be stuck in a loop. What do you actually need from me right now?"}
                break

            loop_data = self.session_loop_data[session_id]
            if not final_tool_calls:
                if turn == 0 or not clean_content:
                    if clean_content: yield {"type": "message", "role": "agent", "content": clean_content}
                    elif turn == 0: yield {"type": "message", "role": "agent", "content": "_[System: Empty response]_"}
                    else: yield {"type": "message", "role": "agent", "content": "Task complete!"}
                    break
                else:
                    if "?" in clean_content or (hasattr(self, "pending_hashes") and self.pending_hashes):
                        if clean_content: yield {"type": "message", "role": "agent", "content": clean_content}
                        break
                    
                    if clean_content: yield {"type": "thought", "content": clean_content}
                    loop_data["narration_retries"] = loop_data.get("narration_retries", 0) + 1
                    if loop_data["narration_retries"] >= 3:
                        yield {"type": "message", "role": "agent", "content": clean_content}
                        break
                    
                    self.histories[session_id].append({"role": "user", "content": "[SYSTEM: Proceed with tool call NOW.]"})
                    continue
            else:
                loop_data["narration_retries"] = 0
                if "count" in loop_data: loop_data["count"] = 0
                if clean_content: yield {"type": "message", "role": "agent", "content": clean_content}
                
                # Check for questions before tools
                if "?" in cast(Any, clean_content.strip())[-5:] and len(clean_content) < 400:
                    self.histories[session_id].append({"role": "user", "content": "[SYSTEM: Waiting for user answer to question.]"})
                    break

            # Execute Tools
            for tool_call in final_tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                    if isinstance(tool_args, str): tool_args = json.loads(tool_args)
                except Exception as e:
                    logger.error(f"JSON error: {e}")
                    self.histories[session_id].append({"role": "system", "content": f"[SYSTEM: JSON Error in {tool_name}]"})
                    continue

                if tool_name == "manage_tasks":
                    tasks = self.session_tasks[session_id]
                    action = tool_args.get("action")
                    if action == "add": tasks.extend(tool_args.get("tasks", []))
                    elif action == "update":
                        idx = tool_args.get("index")
                        if isinstance(idx, int) and 0 <= idx < len(tasks): tasks[idx]["status"] = tool_args.get("status")
                    elif action == "clear": self.session_tasks[session_id] = []
                    
                    formatted_plan = self._format_plan(tasks)
                    yield {"type": "task_update", "tasks": tasks}
                    result = {"status": "success", "message": f"Tasks {action}ed", "formatted": formatted_plan}
                    
                    self.histories[session_id].append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": json.dumps(result)})
                    if action == "add":
                        yield {"type": "message", "role": "agent", "content": f"Plan created: {formatted_plan}\nProceed?"}
                        return
                else:
                    yield {"type": "thought", "content": f"Running {tool_name}..."}
                    yield {"type": "tool_call", "name": tool_name, "args": tool_args}
                    
                    try:
                        # Security Check
                        tool_hash = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                        if mcp_manager.is_sensitive(tool_name, tool_args) and tool_name not in self.trusted_tools and tool_hash not in self.approved_hashes:
                            self.pending_hashes.add(tool_hash)
                            result = "SYSTEM_REQUIREMENT: Ask user for permission."
                            yield {"type": "thought", "content": "🔐 Permission needed."}
                            self.histories[session_id].append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": json.dumps(result)})
                            continue

                        # Implementation of special tools
                        if tool_name == "see_image":
                            path = tool_args.get("path")
                            if not path or not os.path.exists(path): result = {"error": "File not found"}
                            else:
                                vision_provider = config_mgr.get_key("VISION_PROVIDER", "default").lower()
                                if vision_provider in ["google", "openai"]:
                                    desc = await self._analyze_image_externally(path, vision_provider)
                                    self.histories[session_id].append({"role": "user", "content": f"[Vision: {path}] {desc}"})
                                    result = {"status": "success", "details": desc}
                                else:
                                    # Native vision placeholder logic
                                    result = {"status": "success", "message": "Analyzing image natively..."}
                        elif tool_name == "schedule_telegram_message":
                            from server import telegram_bot # type: ignore
                            result = await telegram_bot.schedule_telegram_message(tool_args)
                        elif tool_name.startswith("openclaw_"):
                            skill_name = tool_name.replace("openclaw_agent_", "").replace("openclaw_skill_", "")
                            user_intent = tool_args.get("user_intent", "")
                            ingestor = OpenClawIngestor(os.getcwd())
                            skill_info = next((ingestor.parse_skill(m["name"], m["path"]) for m in ingestor.list_skills() if m["name"] == skill_name), {})
                            asyncio.create_task(self.run_subagent_background(skill_name, skill_info.get("instructions", ""), user_intent, source, session_id))
                            result = {"status": "dispatched", "message": f"@{skill_name} is working in background."}
                        else:
                            result = await mcp_manager.call_tool(tool_name, tool_args)
                    except Exception as e:
                        logger.error(f"Tool error: {e}")
                        result = f"Error: {e}"

                    self.histories[session_id].append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": json.dumps(result)})
                    yield {"type": "tool_result", "name": tool_name, "content": result}

        await memory.add_memory(user_text, {"type": "user_query"})

    async def run_subagent_background(self, skill_name: str, instructions: str, user_intent: str, source: str, session_id: str = "default"):
        try:
            logger.info(f"Sub-agent start: @{skill_name}")
            sub_agent = GokuAgent()
            sub_agent.system_prompt = f"### ROLE: @{skill_name}\n{instructions}\n\n" + sub_agent.system_prompt
            report_content = f"### Report from @{skill_name}\n\n"
            gen = sub_agent.run_agent(user_intent, source=source, session_id=session_id)
            try:
                while True:
                    event = await anext(gen)
                    if event["type"] == "message":
                        msg_content = cast(str, event["content"])
                        report_content = str(report_content) + msg_content
            except StopAsyncIteration: pass
            
            self.histories[session_id].append({"role": "system", "content": f"[REPORT FROM @{skill_name}]:\n{report_content}"})
            if source == "telegram":
                from server import telegram_bot # type: ignore
                await telegram_bot.send_telegram_notification(f"✅ @{skill_name} finished!\n\n{report_content}")
        except Exception as e:
            logger.error(f"Sub-agent error: {e}")
            self.histories[session_id].append({"role": "system", "content": f"[ERROR]: Sub-agent @{skill_name} failed: {e}"})

agent = GokuAgent()
