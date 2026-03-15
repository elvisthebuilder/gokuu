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
from typing import List, Dict, Any, AsyncGenerator, cast, Optional, Callable, Awaitable
from types import SimpleNamespace
from server.lite_router import router # type: ignore
from server.mcp_manager import mcp_manager # type: ignore
from server.memory import memory # type: ignore
from server.openclaw_ingestor import OpenClawIngestor # type: ignore
from server.personality_manager import personality_manager # type: ignore

logger = logging.getLogger(__name__)

class GokuAgent:
    async def get_models(self, provider: str | None = None):
        return await router.get_available_models(provider)

    def __init__(self, is_sub_agent: bool = False):
        self.is_sub_agent = is_sub_agent
        self.session_reacted: Dict[str, bool] = {}
        self._skill_definitions: Optional[List[Dict[str, Any]]] = None
        self._last_skill_refresh: float = 0.0
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
            "  - Describe what you see/found (e.g. 'This looks like a Python script that handles user authentication...')\n\n"
            "16️⃣ META-MANAGEMENT & EVOLUTION\n"
            "• You are the CAPTAIN of an evolving team. If a task is too large for a single turn (e.g. repo-wide refactor, deep research), DELEGATE to a sub-agent using `@meta_manager` or a specific specialist like `@coder`.\n"
            "• If you find yourself repeatedly performing a task for which no skill exists, ask the `@meta_manager` to create one.\n"
            "• Use the `learn_lesson` tool to record mission-critical insights for your sub-agents.\n"
            "  - EXPECT TO CONTINUE THE CONVERSATION. Ask a specific question about what you just analyzed (e.g. 'Do you want me to refactor this script?' or 'Should I explain how the login flow works?').\n"
            "• NEVER use generic robotic sign-offs like 'Let me know if you need anything else' or 'Waiting for instructions'. Take the initiative.\n"
            "• If the user sent a file WITH a message, address their specific request.\n"
            "• FOR IMAGES: You have Native Vision capabilities! Never try to write Python scripts (like pytesseract or OpenCV) to 'see' an image. You can see it natively. Only use python scripts for image manipulation, NOT for basic viewing or reading text.\n"
            "• FOR VIDEOS/DOCS: ALWAYS use the `mcp_document__parse_document` tool first. It is the most robust way to read content. Only if it fails or is unavailable should you fall back to native Python libraries (e.g. markitdown, python-docx, pdfplumber) or shell commands.\n"
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
        self.session_persona_state: Dict[str, Dict[str, Any]] = {}  # Tracks /persona conversational state

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

    def _trim_history(self, session_id: str, max_messages: int = 20):
        """Keep history within limits while preserving the system prompt."""
        history = self.histories.get(session_id, [])
        if len(history) <= max_messages:
            return

        # Keep the first message (System Prompt) and the last N-1 messages
        system_msg = history[0] if history and history[0].get("role") == "system" else None
        
        if system_msg:
            trimmed = [system_msg] + history[-(max_messages - 1):]
        else:
            trimmed = history[-max_messages:]
            
        self.histories[session_id] = trimmed
        logger.debug(f"Trimmed history for {session_id} to {len(trimmed)} messages.")

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
            
        # Create hash of current response including tool name/args to allow progress
        tool_sig = ""
        if tool_calls:
            for tc in tool_calls:
                tool_sig += f"{tc.function.name}({tc.function.arguments})"
        
        current_hash = hashlib.md5((content + tool_sig).encode()).hexdigest()
        
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

    def _get_environment_context(self, source: str, is_group: bool = False) -> str:
        """Build environment-specific system prompt additions based on the interface."""
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")
        
        base = (
            "\n━━━━━━━━━━━━━━━━━━\n"
            "ENVIRONMENT & TIME AWARENESS\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"🕒 CURRENT LOCAL TIME: {current_time}\n"
            f"👥 CHAT TYPE: {'Group/Channel' if is_group else 'Private Direct Message'}\n\n"
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
        elif source == "whatsapp":
            env = (
                "📍 CURRENT INTERFACE: WhatsApp Messenger\n"
                "• The user is chatting via WhatsApp — a high-speed mobile messaging app.\n"
                "• Your output will be auto-converted to WhatsApp native markdown.\n"
                "• Use *bold text* for headers and emphasis.\n"
                "• Use _italics_ for secondary notes or sub-labels.\n"
                "• Use `inline code` for filenames or single commands.\n"
                "• Use triple backticks (```) for code blocks — these are natively scrollable.\n"
                "• USE TABLES freely — they will be auto-formatted into premium monospaced blocks.\n"
                "• Keep layout clean and vertical for mobile ease.\n\n"
            )
        elif source == "telegram":
            env = (
                "📍 CURRENT INTERFACE: Telegram Messenger\n"
                "• The user is chatting via Telegram — a mobile messaging app.\n"
                "• Your output will be auto-converted to Telegram MarkdownV2 for rich formatting.\n\n"
                "📝 TELEGRAM FORMATTING GUIDELINES:\n"
                "• Use **bold text** for emphasis and section headers (e.g. **🔧 Setup**).\n"
                "• Use bullet points (- or •) for lists — they render cleanly on mobile.\n"
                "• Use `inline code` for commands, file names, and technical terms.\n"
                "• Use fenced code blocks (```) for code snippets — keep them short.\n"
                "• USE TABLES freely — they will be auto-formatted into premium monospaced blocks.\n"
                "• Use emoji as section labels (🔍, ✅, ⚠️, 💡) to improve scannability.\n"
                "• Keep paragraphs short (2-3 sentences max) for mobile readability.\n"
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
            
            model = "gpt-4o" if provider == "openai" else config_mgr.get_key("GOKU_VISION_MODEL", "gemini/gemini-2.5-flash")
            
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

    async def run_agent(self, user_text: str, source: str = "cli", session_id: str = "default", react_fn: Optional[Callable[[str], Awaitable[Any]]] = None, is_group: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        """Runs the agent loop and yields thoughts, messages, and tool results."""
        self._trim_history(session_id)
            source: The interface source — 'cli', 'web', or 'telegram'.
            session_id: The ID for the conversation session (e.g. chat_id).
            react_fn: An optional asynchronous function to send a reaction to the user's message.
        """
        if not user_text:
            return

        # Initialize session state if first time
        if session_id not in self.histories:
            self.histories[session_id] = []
        if session_id not in self.session_tasks:
            self.session_tasks[session_id] = []
        if session_id not in self.session_persona_state:
            self.session_persona_state[session_id] = {"active": False, "step": None, "data": {}}
            
        self.session_thoughts[session_id] = ""   # Reset thought buffer for this query

        # --- PERSONA INTERACTIVE MENU LOGIC ---
        p_state = self.session_persona_state[session_id]
        clean_text = user_text.strip()
        
        if clean_text.lower() == "/persona" or clean_text.lower() == "/personalities":
            p_state["active"] = True
            p_state["step"] = "main_menu"
            p_state["data"] = {}
            menu = (
                "🎭 **Goku Personality Manager**\n\n"
                "What would you like to do?\n\n"
                "1️⃣ **Create** a new personality\n\n"
                "2️⃣ **List** existing personalities & mappings\n\n"
                "3️⃣ **Modify** a personality\n\n"
                "4️⃣ **Delete** a personality\n\n"
                "0️⃣ **Cancel**\n\n"
                "_Reply with a number (1-4) or 'cancel'_"
            )
            yield {"type": "message", "role": "agent", "content": menu}
            return

        if p_state["active"]:
            step = p_state["step"]
            lower_text = clean_text.lower()
            
            if lower_text in ["0", "cancel", "exit", "quit"]:
                p_state["active"] = False
                yield {"type": "message", "role": "agent", "content": "🚫 Persona configuration cancelled."}
                return

            # --- MAIN MENU ROUTING ---
            if step == "main_menu":
                if lower_text in ["1", "create", "1️⃣"]:
                    p_state["step"] = "create_method"
                    yield {"type": "message", "role": "agent", "content": "🛠️ **Create Personality**\n\nHow do you want to build this?\n1️⃣ **Goku's Help (Recommended)** - Just give me a rough idea, and I'll expand it into a professional prompt.\n2️⃣ **Manual** - You write the exact system prompt yourself.\n\n_Reply 1 or 2_"}
                    return
                elif lower_text in ["2", "list", "2️⃣"]:
                    personas = personality_manager.list_personalities()
                    mappings = personality_manager.get_all_mappings()
                    if not personas:
                        yield {"type": "message", "role": "agent", "content": "📂 You don't have any custom personalities yet. Use `/persona` and choose 'Create'."}
                    else:
                        msg = "📂 **Your Personalities:**\n\n"
                        for p in personas:
                            assigned_to = [k for k, v in mappings.items() if v == p]
                            targets = ", ".join(assigned_to) if assigned_to else "None (Unassigned)"
                            msg += f"• **{p}**\n  ↳ _Mapped to:_ `{targets}`\n\n"
                        yield {"type": "message", "role": "agent", "content": msg}
                    p_state["active"] = False
                    return
                elif lower_text in ["3", "modify", "3️⃣"]:
                    personas = personality_manager.list_personalities()
                    if not personas:
                        yield {"type": "message", "role": "agent", "content": "📂 You don't have any custom personalities to modify."}
                        p_state["active"] = False
                        return
                    p_state["step"] = "modify_select"
                    msg = "✏️ **Modify Personality**\n\nWhich one would you like to modify?\n" + "\n".join([f"• `{p}`" for p in personas]) + "\n\n_Reply with the name._"
                    yield {"type": "message", "role": "agent", "content": msg}
                    return
                elif lower_text in ["4", "delete", "4️⃣"]:
                    personas = personality_manager.list_personalities()
                    if not personas:
                        yield {"type": "message", "role": "agent", "content": "📂 You don't have any custom personalities to delete."}
                        p_state["active"] = False
                        return
                    p_state["step"] = "delete_select"
                    msg = "🗑️ **Delete Personality**\n\nWhich one would you like to delete?\n" + "\n".join([f"• `{p}`" for p in personas]) + "\n\n_Reply with the name._"
                    yield {"type": "message", "role": "agent", "content": msg}
                    return
                else:
                    yield {"type": "message", "role": "agent", "content": "⚠️ Invalid option. Reply 1-4 or 'cancel'."}
                    return
            
            # --- CREATE FLOW ---
            elif step == "create_method":
                if lower_text in ["1", "goku's help", "1️⃣"]:
                    p_state["step"] = "create_auto_idea"
                    yield {"type": "message", "role": "agent", "content": "🧠 **Goku's Help**\n\nTell me roughly how you want this personality to act. (e.g., 'A sarcastic pirate who writes Python' or 'A strict project manager')."}
                    return
                elif lower_text in ["2", "manual", "2️⃣"]:
                    p_state["step"] = "create_manual_prompt"
                    yield {"type": "message", "role": "agent", "content": "✍️ **Manual Entry**\n\nPlease paste the EXACT system prompt you want this personality to use."}
                    return
                else:
                    yield {"type": "message", "role": "agent", "content": "⚠️ Invalid option. Reply 1 or 2."}
                    return
                    
            elif step == "create_auto_idea":
                yield {"type": "thought", "content": "Thinking about how to expand the user's idea into a robust system prompt..."}
                try:
                    # Ask the LLM to generate the prompt
                    sys_prompt = "You are an expert prompt engineer. The user will give you a rough idea for an AI persona. Your job is to write a highly detailed, professional 'system prompt' (instructing an AI how to act) based on their idea. Do not include any conversational filler, JUST return the raw system prompt text."
                    response = await router.get_response(
                        model=config_mgr.get_key("GOKU_MODEL", "gemini/gemini-2.5-flash"),
                        messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": clean_text}],
                        stream=False
                    )
                    generated_prompt = response.choices[0].message.content.strip() # type: ignore
                    p_state["data"]["prompt"] = generated_prompt
                    p_state["step"] = "create_name"
                    yield {"type": "message", "role": "agent", "content": f"✨ **Generated Prompt:**\n\n```\n{generated_prompt}\n```\n\nLooks good! What should we **NAME** this personality? (e.g., 'pirate', 'manager' — no spaces)"}
                    return
                except Exception as e:
                    yield {"type": "message", "role": "agent", "content": f"⚠️ Failed to generate prompt: {e}. Let's cancel for now."}
                    p_state["active"] = False
                    return
                    
            elif step == "create_manual_prompt":
                p_state["data"]["prompt"] = clean_text
                p_state["step"] = "create_name"
                yield {"type": "message", "role": "agent", "content": "✅ Prompt saved.\n\nWhat should we **NAME** this personality? (e.g., 'custom_dev' — no spaces)"}
                return
                
            elif step == "create_name":
                name = clean_text.replace(" ", "_").lower()
                p_state["data"]["name"] = name
                p_state["step"] = "create_assign"
                yield {"type": "message", "role": "agent", "content": f"🏷️ Name set to `{name}`.\n\nFinally, which **CHANNEL** should use this personality?\n\nExamples:\n• `whatsapp` (Applies to all WhatsApp chats)\n• `telegram` (Applies to all Telegram chats)\n• `{source}:{session_id}` (Applies ONLY to this specific chat)\n• `none` (Save for later)\n\n_Reply with the channel target._"}
                return
                
            elif step == "create_assign":
                name = p_state["data"]["name"]
                prompt = p_state["data"]["prompt"]
                target = clean_text.lower()
                
                # Save the file
                success = personality_manager.save_personality(name, prompt)
                if not success:
                    yield {"type": "message", "role": "agent", "content": "❌ Failed to save the personality file to disk."}
                    p_state["active"] = False
                    return
                    
                msg = f"🎉 **Success!** Personality `{name}` has been saved."
                if target != "none":
                    personality_manager.assign_personality(target, name)
                    msg += f"\n🔗 And it has been mapped to: `{target}`."
                    
                yield {"type": "message", "role": "agent", "content": msg}
                p_state["active"] = False
                return

            # --- MODIFY FLOW ---
            elif step == "modify_select":
                if clean_text not in personality_manager.list_personalities():
                    yield {"type": "message", "role": "agent", "content": f"⚠️ Personality `{clean_text}` not found. Please type a valid name or 'cancel'."}
                    return
                p_state["data"]["name"] = clean_text
                p_state["step"] = "modify_action"
                yield {"type": "message", "role": "agent", "content": f"⚙️ Selected `{clean_text}`.\n\nWhat do you want to change?\n1️⃣ **Update Prompt** (Overwrite text)\n2️⃣ **Re-assign Channel** (Change mapping)\n\n_Reply 1 or 2_"}
                return
                
            elif step == "modify_action":
                if lower_text in ["1", "1️⃣"]:
                    p_state["step"] = "modify_prompt"
                    yield {"type": "message", "role": "agent", "content": "✍️ Please send the NEW system prompt for this personality."}
                    return
                elif lower_text in ["2", "2️⃣"]:
                    p_state["step"] = "modify_assign"
                    yield {"type": "message", "role": "agent", "content": f"🔗 Currently, this personality applies to: `{', '.join([k for k,v in personality_manager.get_all_mappings().items() if v == p_state['data']['name']]) or 'None'}`\n\nWhat channel should it apply to now? (e.g., 'whatsapp', 'telegram', '{source}:{session_id}')"}
                    return
                else:
                    yield {"type": "message", "role": "agent", "content": "⚠️ Invalid option. Reply 1 or 2."}
                    return
                    
            elif step == "modify_prompt":
                name = p_state["data"]["name"]
                success = personality_manager.save_personality(name, clean_text)
                if success:
                    yield {"type": "message", "role": "agent", "content": f"✅ The prompt for `{name}` has been successfully updated!"}
                else:
                    yield {"type": "message", "role": "agent", "content": "❌ Failed to update the file on disk."}
                p_state["active"] = False
                return
                
            elif step == "modify_assign":
                name = p_state["data"]["name"]
                target = clean_text.lower()
                
                # To cleanly "re-assign", we first remove old mappings for this persona, then add the new one.
                mappings = personality_manager.get_all_mappings()
                to_delete = [k for k, v in mappings.items() if v == name]
                for k in to_delete:
                    del mappings[k]
                personality_manager._save_mappings(mappings)
                
                if target != "none":
                    personality_manager.assign_personality(target, name)
                    yield {"type": "message", "role": "agent", "content": f"✅ `{name}` is now exclusively mapped to `{target}`."}
                else:
                    yield {"type": "message", "role": "agent", "content": f"✅ `{name}` has been unassigned and is stored safely."}
                p_state["active"] = False
                return

            # --- DELETE FLOW ---
            elif step == "delete_select":
                if clean_text not in personality_manager.list_personalities():
                    yield {"type": "message", "role": "agent", "content": f"⚠️ Personality `{clean_text}` not found. Please type a valid name or 'cancel'."}
                    return
                success = personality_manager.delete_personality(clean_text)
                if success:
                    yield {"type": "message", "role": "agent", "content": f"🗑️ `{clean_text}` and its mappings have been deleted forever."}
                else:
                    yield {"type": "message", "role": "agent", "content": f"❌ Failed to delete `{clean_text}`."}
                p_state["active"] = False
                return
                
            # Failsafe
            p_state["active"] = False
            return
        # --- END PERSONA LOGIC ---

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

        # 1. Resolve active persona name for memory scoping
        # Get the NAME of the assigned persona (not its content). We use the mappings
        # to find which named persona is active, defaulting to 'goku_default' for bare sessions.
        from server.memory import GOKU_DEFAULT_PERSONA  # type: ignore
        active_persona_name: str = GOKU_DEFAULT_PERSONA
        all_mappings = personality_manager.get_all_mappings()
        for mapped_target, mapped_persona_name in all_mappings.items():
            if session_id == mapped_target or source == mapped_target:
                active_persona_name = str(mapped_persona_name)
                break

        # 2. Retrieve past context from THIS persona's isolated memory
        context = await memory.search_memory(user_text, persona_name=active_persona_name)
        
        # Include lessons learned in context
        if self._lessons_learned:
            learned = cast(List[Dict[str, str]], self._lessons_learned)
            lessons_context = "\n".join([f"- {cast(Dict[str, str], l)['lesson']}" for l in cast(Any, learned)[-5:]])  # Last 5 lessons
            context_str = json.dumps(context) + f"\n\nRecent Lessons Learned:\n{lessons_context}"
        else:
            context_str = json.dumps(context) if context else ""
        
        # Check for custom personality mapping
        custom_persona = personality_manager.get_assigned_personality_for(source, session_id)
        if custom_persona:
            base_prompt = custom_persona
        else:
            base_prompt = self.system_prompt
            
        # Build environment-aware system prompt with memory context
        env_context = self._get_environment_context(source, is_group=is_group)
        memory_section = f"\n\n---\n🧠 **Relevant Memory ({active_persona_name}):**\n{context_str}" if context_str else ""
        full_system_prompt = f"{base_prompt}\n\n{env_context}{memory_section}"
        
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

        llm_tools.append({
            "type": "function",
            "function": {
                "name": "learn_lesson",
                "description": "Record a lesson learned or mission-critical insight for a specific skill context. This helps the team improve over time.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lesson": {"type": "string", "description": "The insight or pattern discovered."},
                        "skill_context": {"type": "string", "description": "The skill name (e.g. 'coder', 'researcher', 'meta_manager') this lesson applies to."}
                    },
                    "required": ["lesson", "skill_context"]
                }
            }
        })

        if react_fn:
            llm_tools.append({
                "type": "function",
                "function": {
                    "name": "react_to_message",
                    "description": "React to the current message with an emoji (e.g., 👍, 😂, 🎉, ❤️, 😮, 😢). Use this ONCE to set the final reaction for the current message. Sequential calls overwrite each other, so only use for your final reaction choice.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "emoji": {"type": "string", "description": "The emoji character to use for the reaction."}
                        },
                        "required": ["emoji"]
                    }
                }
            })

        # DEF Pipeline Tools
        llm_tools.extend([
            {
                "type": "function",
                "function": {
                    "name": "submit_to_audit",
                    "description": "Submit a report or proposal to the Audit Department for review. Use this as your final action if you are `@health` or `@research`.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "report": {"type": "string", "description": "The detailed findings, vulnerabilities, or research proposals."}
                        },
                        "required": ["report"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "request_user_approval",
                    "description": "Submit an audited implementation plan for user approval. Use this as your final action if you are `@audit`. **NEVER implementation code yourself.**",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "audit_report": {"type": "string", "description": "The detailed verdict and step-by-step implementation plan."}
                        },
                        "required": ["audit_report"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "schedule_implementation",
                    "description": "Schedule an approved job for a specific time. Use this when the user says 'Schedule this for [Time]'.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "job_id": {"type": "string", "description": "The ID of the job to schedule."},
                            "scheduled_time_iso": {"type": "string", "description": "The ISO-8601 timestamp for when execution should begin (e.g., 2026-03-14T03:00:00Z)."}
                        },
                        "required": ["job_id", "scheduled_time_iso"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "complete_implementation",
                    "description": "Mark a background implementation job as successfully completed. Use this as your final action if you are `@implement`.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string", "description": "Summary of exactly what was changed and verified."}
                        },
                        "required": ["summary"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "dispatch_implementation",
                    "description": "Dispatch the Implementer agent to execute an approved job IMMEDIATELY. Use this when the user says 'Yes' or 'Go ahead' to a pending proposal.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "job_id": {"type": "string", "description": "The ID of the job to execute."}
                        },
                        "required": ["job_id"]
                    }
                }
            }
        ])

        # Load cached or refresh skills
        llm_tools.extend(self._get_skill_definitions())

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
                    thought_chunk = str(delta.thinking)
                    thoughts_map = getattr(self, "session_thoughts", {})
                    current_thoughts = thoughts_map.get(session_id, "")
                    thoughts_map[session_id] = current_thoughts + thought_chunk  # type: ignore[index]
                    yield {"type": "thought", "content": thoughts_map[session_id]}

                if delta.content:
                    text_chunk = cast(str, delta.content)
                    full_content = str(full_content) + text_chunk
                    pattern = r'<(thought|think)>(.*?)(?:</\1>|$)'
                    matches = list(re.finditer(pattern, full_content, re.DOTALL)) # type: ignore
                    if matches:
                        last_match = matches[-1]
                        scrubbed_thought = re.sub(r'</?(thought|think)>?.*$', '', last_match.group(2), flags=re.IGNORECASE).strip()
                        if scrubbed_thought:
                            thoughts_map = getattr(self, "session_thoughts", {})
                            thoughts_map[session_id] = str(scrubbed_thought)  # type: ignore[index]
                            yield {"type": "thought", "content": thoughts_map[session_id]}
                
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
                    
                    # Ensure arguments are a valid JSON string (Ollama can sometimes cut off strings)
                    args_str = tc['function']['arguments']
                    if isinstance(args_str, str) and args_str.strip():
                        try:
                            json.loads(args_str)
                        except json.JSONDecodeError:
                            # If it's malformed, try to append a closing brace, or just default to empty
                            if not args_str.strip().endswith('}'): args_str += '}'
                            try:
                                json.loads(args_str)
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to salvage tool arguments, defaulting to empty: {args_str}")
                                args_str = "{}"
                    else:
                        args_str = "{}"
                        
                    tool_obj = SimpleNamespace(
                        id=tc['id'],
                        type='function',
                        function=SimpleNamespace(
                            name=tc['function']['name'],
                            arguments=args_str
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
                    elif turn == 0: 
                        if self.session_reacted.get(session_id):
                            # Agent chose to react only, don't send default text
                            break
                        yield {"type": "message", "role": "agent", "content": "_[System: Empty response]_"}
                    else: 
                        if self.session_reacted.get(session_id):
                            break
                        yield {"type": "message", "role": "agent", "content": "Task complete!"}
                    break
                else:
                    if "?" in clean_content or (hasattr(self, "pending_hashes") and self.pending_hashes):
                        if clean_content: yield {"type": "message", "role": "agent", "content": clean_content}
                        break
                    
                    if clean_content: yield {"type": "thought", "content": clean_content}
                    
                    # If we've already reacted, we're likely done and just being polite/chatty.
                    # Don't force a tool call if we've already acknowledged the message.
                    if self.session_reacted.get(session_id):
                        break

                    loop_data["narration_retries"] = loop_data.get("narration_retries", 0) + 1
                    if loop_data["narration_retries"] >= 3:
                        yield {"type": "message", "role": "agent", "content": clean_content}
                        break
                    
                    self.histories[session_id].append({"role": "user", "content": "[SYSTEM: Proceed with tool call NOW.]"})
                    continue
            else:
                loop_data["narration_retries"] = 0
                if "count" in loop_data: loop_data["count"] = 0
                # We intentionally do NOT yield `clean_content` as a `message` here if tools are present for sub-agents.
                # LLMs often output conversational filler like "Let me scan this file now..." before the JSON.
                # We yield it as a thought instead, so it is logged but not sent to the end-user.
                if self.is_sub_agent:
                    if clean_content: yield {"type": "thought", "content": f"Agent pre-tool text: {clean_content}"}
                else:
                    if clean_content: yield {"type": "message", "role": "agent", "content": clean_content}
                
                # Check for questions before tools
                if "?" in cast(Any, clean_content.strip())[-5:] and len(clean_content) < 400:
                    self.histories[session_id].append({"role": "user", "content": "[SYSTEM: Waiting for user answer to question.]"})
                    break

            # Execute Tools
            for tool_call in final_tool_calls:
                tool_name = tool_call.function.name
                tool_args = {}
                try:
                    raw_args = tool_call.function.arguments
                    if isinstance(raw_args, dict):
                        tool_args = raw_args
                    elif isinstance(raw_args, str) and raw_args.strip():
                        # Try to parse stringified JSON
                        try:
                            parsed = json.loads(raw_args)
                            if isinstance(parsed, str):
                                # Sometimes Ollama double-stringifies it
                                tool_args = json.loads(parsed)
                            else:
                                tool_args = parsed
                        except json.JSONDecodeError:
                            # LLMs (especially Ollama) sometimes concatenate multiple JSON objects:
                            # e.g. {"cmd":"..."} {"cmd":"..."} {"cmd":"..."}
                            # We extract just the FIRST complete {...} block using bracket counting.
                            raw_str: str = str(raw_args)
                            depth = 0
                            start = raw_str.find("{")
                            if start != -1:
                                for ci, ch in enumerate(raw_str[start:], start): # type: ignore
                                    if ch == "{":
                                        depth += 1
                                    elif ch == "}":
                                        depth -= 1
                                        if depth == 0:
                                            first_json = raw_str[start:ci + 1] # type: ignore
                                            try:
                                                tool_args = json.loads(first_json)
                                                logger.debug(f"Salvaged first JSON object from concatenated args for {tool_name}")
                                            except Exception:
                                                logger.warning(f"Failed to salvage tool arguments, defaulting to empty: {raw_args}")
                                            break
                except Exception as e:
                    logger.warning(f"Could not parse tool arguments for {tool_name}, defaulting to empty dict. Error: {e}")
                    tool_args = {}
                if tool_name == "manage_tasks":
                    tasks = self.session_tasks[session_id]
                    action = tool_args.get("action")
                    if action == "add": tasks.extend(tool_args.get("tasks", []))
                    elif action == "update":
                        idx = tool_args.get("index")
                        if isinstance(idx, int) and 0 <= idx < len(tasks): 
                            cast(Dict[str, Any], tasks[idx])["status"] = tool_args.get("status")
                    elif action == "clear": self.session_tasks[session_id] = []
                    
                    formatted_plan = self._format_plan(tasks)
                    yield {"type": "task_update", "tasks": tasks}
                    result = {"status": "success", "message": f"Tasks {action}ed", "formatted": formatted_plan}
                    
                    self.histories[session_id].append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": json.dumps(result)})
                    if action == "add":
                        yield {"type": "message", "role": "agent", "content": f"Plan created: {formatted_plan}\nProceed?"}
                        return
                else:
                    # yield {"type": "thought", "content": f"Running {tool_name}..."} # Removed to stop spam
                    yield {"type": "thought", "content": f"🔧 Working..."} # Send a single generic thought, bots can deduplicate or ignore
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
                        elif tool_name == "react_to_message":
                            emoji = tool_args.get("emoji")
                            if react_fn is not None and emoji:
                                await cast(Callable[[str], Awaitable[Any]], react_fn)(emoji)
                                self.session_reacted[session_id] = True
                                result = {"status": "success", "message": f"Reacted with {emoji}"}
                            else:
                                result = {"error": "Reactions not supported on this channel or missing emoji"}
                        elif tool_name == "learn_lesson":
                            lesson = tool_args.get("lesson")
                            skill_context = tool_args.get("skill_context", "general")
                            if lesson:
                                lesson_dir = os.path.join(os.getcwd(), "agents", skill_context, "lessons")
                                os.makedirs(lesson_dir, exist_ok=True)
                                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                lesson_path = os.path.join(lesson_dir, f"lesson_{timestamp}.md")
                                with open(lesson_path, "w") as f:
                                    f.write(f"# Lesson Learned: {timestamp}\n\n{lesson}\n")
                                result = {"status": "success", "message": f"Lesson recorded for {skill_context}"}
                            else:
                                result = {"error": "Missing 'lesson' content"}
                        elif tool_name == "schedule_telegram_message":
                            from server import telegram_bot # type: ignore
                            result = await telegram_bot.schedule_telegram_message(tool_args)
                        elif tool_name == "submit_to_audit":
                            report = tool_args.get("report", "")
                            from server.job_tracker import job_tracker # type: ignore
                            job_id = f"job_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                            job_tracker.create_job(job_id, "audit", {"report": report})
                            asyncio.create_task(self.run_subagent_background("department_audit", "Review this report.", report, source, session_id))
                            result = {"status": "success", "message": f"Report submitted to Audit. Job ID: {job_id}"}
                        elif tool_name == "request_user_approval":
                            audit_report = tool_args.get("audit_report", "")
                            from server.job_tracker import job_tracker # type: ignore
                            # In a real flow, we'd pass the actual job ID here. For now, we create a new approval job.
                            job_id = f"approval_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                            job_tracker.create_job(job_id, "implement", {"plan": audit_report})
                            job_tracker.update_job_status(job_id, "AWAITING_APPROVAL")
                            result = {"status": "success", "message": "Approval requested. Stopping execution until user approves."}
                        elif tool_name == "schedule_implementation":
                            job_id = tool_args.get("job_id", "")
                            scheduled_time_iso = tool_args.get("scheduled_time_iso", "")
                            from server.job_tracker import job_tracker # type: ignore
                            success = job_tracker.schedule_job(job_id, scheduled_time_iso)
                            if success:
                                result = {"status": "success", "message": f"Job {job_id} successfully scheduled for {scheduled_time_iso}."}
                            else:
                                result = {"status": "error", "message": f"Failed to schedule job {job_id}. Verify the ID exists."}
                        elif tool_name == "dispatch_implementation":
                            job_id = tool_args.get("job_id", "")
                            from server.job_tracker import job_tracker # type: ignore
                            job = job_tracker.get_job(job_id)
                            if job and job["status"] in ["AWAITING_APPROVAL", "SCHEDULED", "PENDING"]:
                                job_tracker.update_job_status(job_id, "RUNNING")
                                asyncio.create_task(self.run_subagent_background(
                                    "department_implement", 
                                    "Execute the approved plan.", 
                                    str(job.get("payload", {})), 
                                    source, 
                                    job_id
                                ))
                                result = {"status": "success", "message": f"Job {job_id} dispatched to the Implementer."}
                            else:
                                result = {"status": "error", "message": f"Failed to dispatch job. Job {job_id} not found or not in a valid state."}
                        elif tool_name == "complete_implementation":
                            summary = tool_args.get("summary", "")
                            result = {"status": "success", "message": f"Implementation marked complete: {summary[:50]}..."}
                        elif tool_name.startswith("openclaw_"):
                            skill_name = tool_name.replace("openclaw_agent_", "").replace("openclaw_skill_", "")
                            user_intent = tool_args.get("user_intent", "")
                            ingestor = OpenClawIngestor(os.getcwd())
                            skill_info = next((ingestor.parse_skill(m["name"], m["path"]) for m in ingestor.list_skills() if m["name"] == skill_name), {})
                            asyncio.create_task(self.run_subagent_background(skill_name, skill_info.get("instructions", ""), user_intent, source, session_id))
                            result = {"status": "dispatched", "message": f"@{skill_name} is working in background."}
                        else:
                            try:
                                result = await asyncio.wait_for(mcp_manager.call_tool(tool_name, tool_args), timeout=60.0)
                            except asyncio.TimeoutError:
                                logger.error(f"Tool timeout: {tool_name} took longer than 60s.")
                                result = {"status": "error", "message": f"Tool '{tool_name}' timed out after 60 seconds."}
                    except Exception as e:
                        logger.error(f"Tool error: {e}")
                        result = f"Error: {e}"

                    self.histories[session_id].append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": json.dumps(result)})
                    yield {"type": "tool_result", "name": tool_name, "content": result}

        # Detect file attachments from the message text for embedding
        # Matches patterns like [Document: /path/to/file.pdf] or [File: ...]
        file_pattern = r'\[(?:Document|File|PDF|Doc)\s*(?:Received)?:\s*(.+?)\]'
        file_paths = re.findall(file_pattern, user_text)  # type: ignore
        file_to_embed = file_paths[0] if file_paths else None

        # Store this interaction into the persona's isolated memory collection
        await memory.add_memory(
            text=user_text,
            images=photos if photos else None,
            file_path=file_to_embed,
            metadata={"type": "user_query", "source": source, "session_id": session_id},
            persona_name=active_persona_name,
        )

    async def run_subagent_background(self, skill_name: str, instructions: str, user_intent: str, source: str, session_id: str = "default"):
        try:
            logger.info(f"Sub-agent start: @{skill_name}")
            # Inject Lessons Learned if available
            lessons_dir = os.path.join(os.getcwd(), "agents", skill_name, "lessons")
            lessons_list: List[str] = []
            if os.path.exists(lessons_dir):
                all_files = os.listdir(lessons_dir)
                sorted_files = sorted(all_files, reverse=True)
                top_files: List[str] = sorted_files[:5] # type: ignore # Last 5 lessons
                for f_name in top_files:
                    if f_name.endswith(".md"):
                        with open(os.path.join(lessons_dir, f_name), "r") as f:
                            lessons_list.append(f"\n---\n{f.read()}")
            
            lessons_text = "".join(lessons_list)
            
            sub_agent = GokuAgent(is_sub_agent=True)
            lesson_prompt = f"\n\n### RECENT LESSONS LEARNED:\n{lessons_text}" if lessons_text else ""
            sub_agent.system_prompt = f"### ROLE: @{skill_name}\n{instructions}{lesson_prompt}\n\n" + sub_agent.system_prompt
            
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

    def _get_skill_definitions(self) -> List[Dict[str, Any]]:
        """Retrieve tool definitions from cache or refresh if necessary."""
        import time
        now = time.time()
        
        # Refresh cache every 10 minutes to auto-detect new MCP/Goku skills
        if self._skill_definitions is None or (now - self._last_skill_refresh) > 600:
            logger.info("Initializing/Refreshing skill definitions cache...")
            tools = []
            try:
                ingestor = OpenClawIngestor(os.getcwd())
                skill_tools = ingestor.generate_tool_definitions()
                for st in skill_tools:
                    tools.append({"type": st.get("type", "function"), "function": st["function"]})
                self._skill_definitions = tools
                self._last_skill_refresh = now
            except Exception as e:
                logger.error(f"Failed to load skills during refresh: {e}")
                return self._skill_definitions or []
        
        return self._skill_definitions or []

agent = GokuAgent()
