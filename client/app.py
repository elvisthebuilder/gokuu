import asyncio
import typer # type: ignore
import questionary # type: ignore
from rich.console import Console # type: ignore
from rich.live import Live # type: ignore
from rich.panel import Panel # type: ignore
from rich.markdown import Markdown # type: ignore
from rich.spinner import Spinner # type: ignore
from rich.text import Text # type: ignore
from rich.table import Table # type: ignore
from rich import print as rprint # type: ignore
import sys
import os
import logging
import re

# Setup file logging for v2.5
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "goku.log")
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Configure root logger: File is DEBUG, Console is ERROR (for a clean UI)
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)

# Console handler for critical errors only
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)
root_logger.addHandler(console_handler)

# Silence LiteLLM's noisy tracebacks
logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
logging.getLogger("litellm").setLevel(logging.CRITICAL)
logging.getLogger("LiteLLM Router").setLevel(logging.CRITICAL)
logging.getLogger("LiteLLM Proxy").setLevel(logging.CRITICAL)

# Enable debug logging for our trace modules (captured in file)
logging.getLogger("WhatsAppBot").setLevel(logging.DEBUG)
logging.getLogger("ChannelManager").setLevel(logging.DEBUG)

# Add parent directory to sys.path to allow importing from server
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.agent import agent # type: ignore
from server.memory import memory # type: ignore
from server.lite_router import router # type: ignore
from server.config_manager import config_manager # type: ignore
from server.whatsapp_bot import whatsapp_bot # type: ignore

# Prompt Toolkit for rich input
from prompt_toolkit import PromptSession # type: ignore
from prompt_toolkit.history import InMemoryHistory # type: ignore
from prompt_toolkit.styles import Style # type: ignore
from prompt_toolkit.lexers import PygmentsLexer # type: ignore
from pygments.lexer import RegexLexer # type: ignore
from pygments.token import Token # type: ignore

class GokuLexer(RegexLexer):
    """Highlight commands in yellow, text in default."""
    tokens = {
        'root': [
            (r'^/[a-zA-Z0-9-]+', Token.Keyword),
            (r'^(exit|quit|status|config)', Token.Keyword),
            (r'.', Token.Text),
        ]
    }

goku_style = Style.from_dict({
    'keyword': 'ansiyellow bold',
    'text': '', # Default terminal color
})

class ExecutionManager:
    """Manages state for tool execution confirmation."""
    def __init__(self):
        self.cache = set()
        self.session_allowlist = set()
        self.live_ctx = None

exec_manager = ExecutionManager()

def validate_phone(text: str) -> bool | str:
    """Validate phone number is in E.164 format (+ prefixed)."""
    if not text:
        return True
    # Standard E.164 regex: + followed by 1-15 digits
    if not re.match(r"^\+[1-9]\d{1,14}$", text.strip().replace(" ", "")):
        return "Invalid E.164 format (e.g., +233201234567)"
    return True

def validate_phone_list(text: str) -> bool | str:
    """Validate a comma-separated list of E.164 numbers."""
    if not text or text.strip() == "*":
        return True
    parts = [p.strip() for p in text.split(",")]
    for p in parts:
        res = validate_phone(p)
        if res is not True:
            return f"Invalid number '{p}': {res}"
    return True

async def confirm_execution(tool_name: str, args: dict) -> bool:
    """Non-blocking execution confirmation."""
    cmd = args.get("command", str(args))
    
    # Check cache (prevent repetitive prompts)
    if cmd in exec_manager.cache:
        return True
        
    # Check Session Trust (allow user to whitelist tool)
    if tool_name in exec_manager.session_allowlist:
        return True
    
    # Handle Live display conflict
    live = exec_manager.live_ctx
    if live and live.is_started:
        live.stop()
        
    try:
        rprint(f"\n[bold green]Goku[/]: I would like to run this command:")
        rprint(f"[cyan]{cmd}[/cyan]")
        
        answer = await questionary.select(
            "Do you approve?",
            choices=[
                "Yes",
                f"Yes (Trust {tool_name} for this session)",
                "No"
            ],
            default="Yes"
        ).ask_async()
        
        if not answer or answer == "No": 
            return False
        
        if "Trust" in answer:
            exec_manager.session_allowlist.add(tool_name)
            
        exec_manager.cache.add(cmd)
        return True
    finally:
        if live and not live.is_started:
            live.start()
    
    return True # Explicit fallback

# Register security callback
# agent.confirmation_callback = confirm_execution

app = typer.Typer(help="Goku CLI Agent")
console = Console()

def get_status_str():
    """Returns a formatted status string for the current infrastructure."""
    status = []
    
    # AI Provider
    providers = router.available_providers
    if providers:
        status.append(f"[bold green]LLM:[/] {', '.join(providers)}")
    else:
        status.append("[bold yellow]LLM:[/] Local (Ollama)")

    # Model
    try:
        model_name = router.get_default_model()
        status.append(f"[bold cyan]MODEL:[/] {model_name}")
    except Exception:
        status.append("[bold dim]MODEL:[/] Unknown")
        
    # Memory
    if getattr(memory, "online", False):
        status.append("[bold green]MEM:[/] Online")
    else:
        status.append("[bold dim]MEM:[/] Offline")
        
    return " | ".join(status)

async def run_chat(query: str):
    console.print(Panel(f"[bold blue]User:[/bold blue] {query}", border_style="blue"))
    
    with Live(console=console, refresh_per_second=10) as live:
        # Inject live context into confirmation callback so it can pause updates
        exec_manager.live_ctx = live
        
        last_thought = ""
        try:
            async for event in agent.run_agent(query, source="cli"):
                if event["type"] == "thought" and event["content"]:
                    if not live.is_started: live.start()
                    last_thought = event['content']
                    thought_spinner = Spinner("dots", text=Text(last_thought, style="dim"), style="cyan")
                    live.update(Panel(thought_spinner, title="💭 Thinking", border_style="dim", title_align="left"))
                
                elif event["type"] == "message":
                    live.stop()
                    console.print(Panel(Markdown(event["content"]), title="[bold green]GOKU[/bold green]", border_style="green", title_align="left"))
                
                elif event["type"] == "tool_call":
                    if not live.is_started: live.start()
                    # Show both thought and execution
                    content = []
                    if last_thought:
                        content.append(Panel(Text(last_thought, style="dim"), title="💭 Thoughts", border_style="dim"))
                    
                    exec_spinner = Spinner("dots", text=Text.from_markup(f" Executing: [bold yellow]{event['name']}[/bold yellow]"), style="yellow")
                    content.append(Panel(exec_spinner, title="🛠️  Executing", border_style="yellow"))
                    
                    from rich.console import Group # type: ignore
                    live.update(Group(*content))
                
                elif event["type"] == "task_update":
                    # Render task list in a side panel or dedicated area
                    task_text = ""
                    for i, t in enumerate(event["tasks"]):
                        marker = "[green]✓[/]" if t.get("status") == "done" else "[blue]>[/]" if t.get("status") == "in_progress" else "[dim]•[/]"
                        desc = t.get("desc") or t.get("description") or t.get("task") or t.get("content") or "Unknown task"
                        task_text += f"{marker} {desc}\n"
                    
                    # We print the plan so it stays in history, but we don't stop Live if we don't have to
                    # Actually console.print in the middle of Live might be messy.
                    live.stop()
                    console.print(Panel(task_text.strip(), title="📋 GOKU'S PLAN", border_style="cyan", title_align="left"))
                    live.start()
                
                elif event["type"] == "tool_result":
                    # Optionally show a quick success/fail indicator if not planning
                    pass
        except Exception as e:
            live.stop()
            # If it's a known API error, don't show the full traceback here, just re-raise
            # so the interactive loop can show a clean panel and switch providers.
            err_msg = str(e)
            if any(x in err_msg.lower() for x in ["rate limit", "401", "auth", "unauthorized", "exhausted"]):
                raise e
            
            # For other unexpected errors, show a simplified panel
            console.print(Panel(f"[bold red]Error:[/bold red] {err_msg}", border_style="red", title="SYSTEM ERROR"))
            raise e

@app.command()
def chat(query: str = typer.Argument(None, help="The query to send to Goku")):
    """Chat with Goku terminal agent."""
    if not query:
        rprint("[bold red]Error:[/bold red] Please provide a query.")
        raise typer.Exit()
    
    asyncio.run(run_chat(query))

async def setup_wizard():
    """Interactive wizard to configure AI providers."""
    rprint(Panel("[bold green]🐉 GOKU SETUP WIZARD[/bold green]\nLet's configure your AI provider.", border_style="green"))
    
    providers = [
        "OpenAI (Codex OAuth + API key)",
        "Anthropic (setup-token + API key)",
        "Chutes (OAuth)",
        "vLLM (Local/self-hosted OpenAI-compatible)",
        "MiniMax (M2.5 (recommended))",
        "Moonshot AI (Kimi K2.5) (Kimi K2.5 + Kimi Coding)",
        "Google (Gemini API key + OAuth)",
        "xAI (Grok) (API key)",
        "OpenRouter (API key)",
        "Qwen (OAuth)",
        "Z.AI (GLM Coding Plan / Global / CN)",
        "Qianfan (API key)",
        "Copilot (GitHub + local proxy)",
        "Vercel AI Gateway (API key)",
        "OpenCode Zen (API key)",
        "Xiaomi (API key)",
        "Synthetic (Anthropic-compatible (multi-model))",
        "Together AI (API key)",
        "Hugging Face (Inference API (HF token))",
        "Venice AI (Privacy-focused (uncensored models))",
        "LiteLLM (Unified LLM gateway (100+ providers))",
        "Cloudflare AI Gateway (Account ID + Gateway ID + API key)",
        "Custom Provider (Any OpenAI or Anthropic compatible endpoint)",
        "Ollama (Local Models)"
    ]
    provider = await questionary.select(
        "Select your primary AI Provider:",
        choices=providers
    ).ask_async()
    
    if not provider:
        return

    if "OpenAI" in provider:
        key = await questionary.password("Enter OpenAI API Key (sk-...):").ask_async()
        if key: config_manager.set_key("OPENAI_API_KEY", key)
    elif "Anthropic" in provider:
        key = await questionary.password("Enter Anthropic API Key (sk-ant-...):").ask_async()
        if key: config_manager.set_key("ANTHROPIC_API_KEY", key)
    elif "Chutes" in provider:
        key = await questionary.password("Enter Chutes API Key/Token:").ask_async()
        if key: config_manager.set_key("CHUTES_API_KEY", key)
    elif "vLLM" in provider:
        url = await questionary.text("Enter vLLM Base URL (e.g. http://localhost:8000/v1):").ask_async()
        if url: config_manager.set_key("VLLM_BASE_URL", url)
        key = await questionary.password("Enter vLLM API Key (optional):").ask_async()
        if key: config_manager.set_key("VLLM_API_KEY", key)
    elif "MiniMax" in provider:
        key = await questionary.password("Enter MiniMax API Key:").ask_async()
        if key: config_manager.set_key("MINIMAX_API_KEY", key)
    elif "Moonshot" in provider:
        key = await questionary.password("Enter Moonshot API Key:").ask_async()
        if key: config_manager.set_key("MOONSHOT_API_KEY", key)
    elif "Google" in provider:
        key = await questionary.password("Enter Google API Key:").ask_async()
        if key: config_manager.set_key("GOOGLE_API_KEY", key)
    elif "xAI" in provider:
        key = await questionary.password("Enter xAI API Key:").ask_async()
        if key: config_manager.set_key("XAI_API_KEY", key)
    elif "OpenRouter" in provider:
        key = await questionary.password("Enter OpenRouter API Key (sk-or-...):").ask_async()
        if key: config_manager.set_key("OPENROUTER_API_KEY", key)
    elif "Qwen" in provider:
        key = await questionary.password("Enter Qwen API Key:").ask_async()
        if key: config_manager.set_key("QWEN_API_KEY", key)
    elif "Z.AI" in provider:
        key = await questionary.password("Enter Z.AI API Key:").ask_async()
        if key: config_manager.set_key("ZAI_API_KEY", key)
    elif "Qianfan" in provider:
        key = await questionary.password("Enter Qianfan API Key:").ask_async()
        if key: config_manager.set_key("QIANFAN_API_KEY", key)
    elif "Copilot" in provider:
        key = await questionary.password("Enter GitHub Token (ghp_...):").ask_async()
        if key: config_manager.set_key("GITHUB_TOKEN", key)
    elif "Vercel" in provider:
        key = await questionary.password("Enter Vercel AI Gateway Key:").ask_async()
        if key: config_manager.set_key("VERCEL_AI_GATEWAY_API_KEY", key)
    elif "OpenCode Zen" in provider:
        key = await questionary.password("Enter OpenCode Zen Key:").ask_async()
        if key: config_manager.set_key("OPENCODE_ZEN_API_KEY", key)
    elif "Xiaomi" in provider:
        key = await questionary.password("Enter Xiaomi API Key:").ask_async()
        if key: config_manager.set_key("XIAOMI_API_KEY", key)
    elif "Synthetic" in provider:
        key = await questionary.password("Enter Synthetic API Key:").ask_async()
        if key: config_manager.set_key("SYNTHETIC_API_KEY", key)
    elif "Together" in provider:
        key = await questionary.password("Enter Together AI Key:").ask_async()
        if key: config_manager.set_key("TOGETHERAI_API_KEY", key)
    elif "Hugging Face" in provider:
        key = await questionary.password("Enter Hugging Face API Token (hf_...):").ask_async()
        if key: config_manager.set_key("HUGGINGFACE_API_KEY", key)
    elif "Venice" in provider:
        key = await questionary.password("Enter Venice API Key:").ask_async()
        if key: config_manager.set_key("VENICE_API_KEY", key)
    elif "LiteLLM" in provider:
        key = await questionary.password("Enter LiteLLM API Key:").ask_async()
        if key: config_manager.set_key("LITELLM_API_KEY", key)
    elif "Cloudflare" in provider:
        key = await questionary.password("Enter Cloudflare API Key:").ask_async()
        if key: config_manager.set_key("CLOUDFLARE_API_KEY", key)
        acc = await questionary.text("Enter Cloudflare Account ID:").ask_async()
        if acc: config_manager.set_key("CLOUDFLARE_ACCOUNT_ID", acc)
        gate = await questionary.text("Enter Cloudflare Gateway ID:").ask_async()
        if gate: config_manager.set_key("CLOUDFLARE_GATEWAY_ID", gate)
    elif "Custom" in provider:
        url = await questionary.text("Enter Custom API Base URL:").ask_async()
        if url: config_manager.set_key("CUSTOM_BASE_URL", url)
        key = await questionary.password("Enter Custom API Key:").ask_async()
        if key: config_manager.set_key("CUSTOM_API_KEY", key)
    elif "Ollama" in provider:
        # Check if default ollama is reachable & discover models (OpenClaw pattern)
        try:
            import httpx # type: ignore
            with httpx.Client(timeout=3.0) as client:
                resp = client.get("http://localhost:11434/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m["name"] for m in data.get("models", []) if "name" in m]
                    if models:
                        rprint(f"[bold green]Detected local Ollama instance with {len(models)} model(s).[/bold green]")
                        config_manager.set_key("OLLAMA_BASE_URL", "http://localhost:11434")
                        selected_model = models[0]
                        if len(models) > 1:
                            selected_model = await questionary.select(
                                "Select Ollama model:", choices=models
                            ).ask_async() or models[0]
                        agent.model_override = f"ollama/{selected_model}"
                        rprint(f"[bold green]Configuration updated! Using Ollama ({selected_model})[/bold green]")
                        return
                    else:
                        rprint("[yellow]Ollama is running but no models found. Pull one first: ollama pull <model>[/yellow]")
        except Exception:
            pass
            
        url = await questionary.text("Enter Ollama Base URL:", default="http://localhost:11434").ask_async()
        if url: 
            config_manager.set_key("OLLAMA_BASE_URL", url)
            # Discover models from the provided URL
            discovered = router.discover_ollama_models()
            if discovered:
                selected_model = discovered[0]
                if len(discovered) > 1:
                    selected_model = await questionary.select(
                        "Select Ollama model:", choices=discovered
                    ).ask_async() or discovered[0]
                agent.model_override = f"ollama/{selected_model}"
                rprint(f"[bold green]Configuration updated! Using Ollama ({selected_model})[/bold green]")
            else:
                rprint("[yellow]Could not discover models. Pull one first: ollama pull <model>[/yellow]")
        
    rprint("[bold green]Configuration updated![/bold green]")

async def switch_provider_menu():
    """Interactive menu to switch providers or configure a new one."""
    available = router.available_providers
    
    choices = []
    if "openai" in available: choices.append("OpenAI (Codex OAuth + API key)")
    if "anthropic" in available: choices.append("Anthropic (setup-token + API key)")
    if "chutes" in available: choices.append("Chutes (OAuth)")
    if "vllm" in available: choices.append("vLLM (Local/self-hosted OpenAI-compatible)")
    if "minimax" in available: choices.append("MiniMax (M2.5 (recommended))")
    if "moonshot" in available: choices.append("Moonshot AI (Kimi K2.5) (Kimi K2.5 + Kimi Coding)")
    if "google" in available: choices.append("Google (Gemini API key + OAuth)")
    if "xai" in available: choices.append("xAI (Grok) (API key)")
    if "openrouter" in available: choices.append("OpenRouter (API key)")
    if "qwen" in available: choices.append("Qwen (OAuth)")
    if "zai" in available: choices.append("Z.AI (GLM Coding Plan / Global / CN)")
    if "qianfan" in available: choices.append("Qianfan (API key)")
    if "github" in available: choices.append("Copilot (GitHub + local proxy)")
    if "ai-gateway" in available: choices.append("Vercel AI Gateway (API key)")
    if "opencode-zen" in available: choices.append("OpenCode Zen (API key)")
    if "xiaomi" in available: choices.append("Xiaomi (API key)")
    if "synthetic" in available: choices.append("Synthetic (Anthropic-compatible (multi-model))")
    if "together" in available: choices.append("Together AI (API key)")
    if "huggingface" in available: choices.append("Hugging Face (Inference API (HF token))")
    if "venice" in available: choices.append("Venice AI (Privacy-focused (uncensored models))")
    if "litellm" in available: choices.append("LiteLLM (Unified LLM gateway (100+ providers))")
    if "cloudflare-ai-gateway" in available: choices.append("Cloudflare AI Gateway (Account ID + Gateway ID + API key)")
    if "custom" in available: choices.append("Custom Provider (Any OpenAI or Anthropic compatible endpoint)")
    choices.append("[New] Configure a new provider...")
    choices.append("Cancel")

    selection = await questionary.select(
        "Choose an AI brain to switch to:",
        choices=choices
    ).ask_async()

    if not selection or selection == "Cancel":
        return False

    if "Configure" in selection:
        await setup_wizard()
        return True
    
    if "OpenAI" in selection: agent.model_override = "gpt-4o"
    elif "Anthropic" in selection: agent.model_override = "claude-3-5-sonnet-20240620"
    elif "Chutes" in selection: agent.model_override = "chutes/default"
    elif "vLLM" in selection: agent.model_override = "vllm/default"
    elif "MiniMax" in selection: agent.model_override = "minimax/MiniMax-M2.5"
    elif "Moonshot" in selection: agent.model_override = "moonshot/kimi-k2.5"
    elif "Google" in selection: agent.model_override = "gemini/gemini-3.1-pro-preview"
    elif "xAI" in selection: agent.model_override = "xai/grok-2-latest"
    elif "OpenRouter" in selection: agent.model_override = "openrouter/anthropic/claude-3.5-sonnet"
    elif "Qwen" in selection: agent.model_override = "qwen/qwen-turbo"
    elif "Z.AI" in selection: agent.model_override = "zai/glm-4v"
    elif "Qianfan" in selection: agent.model_override = "qianfan/eb-4"
    elif "Copilot" in selection: agent.model_override = "github/gpt-4o"
    elif "Vercel" in selection: agent.model_override = "ai-gateway/default"
    elif "OpenCode Zen" in selection: agent.model_override = "opencode-zen/default"
    elif "Xiaomi" in selection: agent.model_override = "xiaomi/mimo-v2-flash"
    elif "Synthetic" in selection: agent.model_override = "synthetic/default"
    elif "Together" in selection: agent.model_override = "together/meta-llama/Llama-3.3-70B-Instruct-Turbo"
    elif "Hugging Face" in selection: agent.model_override = "huggingface/meta-llama/Llama-3.2-3B-Instruct"
    elif "Venice" in selection: agent.model_override = "venice/default"
    elif "LiteLLM" in selection: agent.model_override = "litellm/default"
    elif "Cloudflare" in selection: agent.model_override = "cloudflare/default"
    elif "Custom" in selection: agent.model_override = "custom/default"
    elif "Ollama" in selection:
        discovered = router.discover_ollama_models()
        agent.model_override = f"ollama/{discovered[0]}" if discovered else "ollama/default"
    
    rprint(f"[bold green]Goku successfully switched to {selection}![/bold green]")
    return True

async def configure_integrations():
    """Configure third-party integrations — the Jarvis essentials."""
    while True:
        rprint(Panel("[bold green]🔗 INTEGRATIONS[/bold green]\nConnect Goku to your favorite services.", border_style="cyan"))
        
        # Show status of each integration
        integrations = [
            ("🐙 GitHub", "GITHUB_TOKEN", "Repo access, PRs, Issues, Actions"),
            ("💬 Slack", "SLACK_BOT_TOKEN", "Send/receive messages, channel management"),
            ("📝 Notion", "NOTION_API_KEY", "Read & write workspace pages"),
            ("🎵 Spotify", "SPOTIFY_CLIENT_ID", "Now playing, playlist & playback control"),
            ("📊 Linear", "LINEAR_API_KEY", "Issue tracking & project management"),
            ("🔧 Jira", "JIRA_API_TOKEN", "Issue tracking & sprint management"),
            ("💬 Discord", "DISCORD_BOT_TOKEN", "Bot messaging & server management"),
            ("📱 Telegram", "TELEGRAM_BOT_TOKEN", "Bot notifications & messaging"),
            ("📱 WhatsApp", "WHATSAPP_LINKED", "QR-code based WhatsApp client"),
            ("🎙️ ElevenLabs", "ELEVENLABS_API_KEY", "Highly realistic Text-to-Speech & Speech-to-Text"),
            ("⚡ Groq", "GROQ_API_KEY", "Ultra-fast Speech-to-Text inference (optional)"),
        ]
        
        choices = []
        for label, key, desc in integrations:
            status = "✅" if config_manager.get_key(key) else "⬚ "
            choices.append(f"{status} {label} — {desc}")
        choices.append("⬅️  Back")
        
        selection = await questionary.select("Select integration to configure:", choices=choices).ask_async()
        if not selection or "Back" in selection:
            return
        
        if "GitHub" in selection:
            rprint("[bold cyan]🐙 GitHub Integration[/bold cyan]")
            rprint("[dim]Get a token at: https://github.com/settings/tokens[/dim]")
            rprint("[dim]Scopes needed: repo, read:org, read:user[/dim]")
            token = await questionary.password("Enter GitHub Personal Access Token:").ask_async()
            if token:
                config_manager.set_key("GITHUB_TOKEN", token)
                os.environ["GITHUB_API_KEY"] = token
                rprint("[bold green]✅ GitHub connected![/bold green]")
        
        elif "Slack" in selection:
            rprint("[bold cyan]💬 Slack Integration[/bold cyan]")
            rprint("[dim]Create a Slack App at: https://api.slack.com/apps[/dim]")
            rprint("[dim]Scopes needed: chat:write, channels:read, channels:history[/dim]")
            token = await questionary.password("Enter Slack Bot Token (xoxb-...):").ask_async()
            if token:
                config_manager.set_key("SLACK_BOT_TOKEN", token)
                channel = await questionary.text("Default Slack channel (e.g. #general):", default="#general").ask_async()
                if channel:
                    config_manager.set_key("SLACK_DEFAULT_CHANNEL", channel)
                rprint("[bold green]✅ Slack connected![/bold green]")
        
        elif "Notion" in selection:
            rprint("[bold cyan]📝 Notion Integration[/bold cyan]")
            rprint("[dim]Create integration at: https://www.notion.so/my-integrations[/dim]")
            key = await questionary.password("Enter Notion API Key (secret_...):").ask_async()
            if key:
                config_manager.set_key("NOTION_API_KEY", key)
                workspace = await questionary.text("Notion Workspace ID (optional):").ask_async()
                if workspace:
                    config_manager.set_key("NOTION_WORKSPACE_ID", workspace)
                rprint("[bold green]✅ Notion connected![/bold green]")
        
        elif "Spotify" in selection:
            rprint("[bold cyan]🎵 Spotify Integration[/bold cyan]")
            rprint("[dim]Create app at: https://developer.spotify.com/dashboard[/dim]")
            rprint("[dim]Set redirect URI to: http://localhost:8888/callback[/dim]")
            client_id = await questionary.text("Enter Spotify Client ID:").ask_async()
            if client_id:
                config_manager.set_key("SPOTIFY_CLIENT_ID", client_id)
                client_secret = await questionary.password("Enter Spotify Client Secret:").ask_async()
                if client_secret:
                    config_manager.set_key("SPOTIFY_CLIENT_SECRET", client_secret)
                rprint("[bold green]✅ Spotify connected![/bold green]")
        
        elif "Linear" in selection:
            rprint("[bold cyan]📊 Linear Integration[/bold cyan]")
            rprint("[dim]Get API key at: https://linear.app/settings/api[/dim]")
            key = await questionary.password("Enter Linear API Key:").ask_async()
            if key:
                config_manager.set_key("LINEAR_API_KEY", key)
                rprint("[bold green]✅ Linear connected![/bold green]")
        
        elif "Jira" in selection:
            rprint("[bold cyan]🔧 Jira Integration[/bold cyan]")
            rprint("[dim]Get API token at: https://id.atlassian.com/manage-profile/security/api-tokens[/dim]")
            base_url = await questionary.text("Enter Jira Base URL (e.g. https://yourteam.atlassian.net):").ask_async()
            if base_url:
                config_manager.set_key("JIRA_BASE_URL", base_url)
                email = await questionary.text("Enter Jira Email:").ask_async()
                if email:
                    config_manager.set_key("JIRA_EMAIL", email)
                token = await questionary.password("Enter Jira API Token:").ask_async()
                if token:
                    config_manager.set_key("JIRA_API_TOKEN", token)
                rprint("[bold green]✅ Jira connected![/bold green]")
        
        elif "Discord" in selection:
            rprint("[bold cyan]💬 Discord Integration[/bold cyan]")
            rprint("[dim]Create bot at: https://discord.com/developers/applications[/dim]")
            rprint("[dim]Enable Message Content Intent in Bot settings[/dim]")
            token = await questionary.password("Enter Discord Bot Token:").ask_async()
            if token:
                config_manager.set_key("DISCORD_BOT_TOKEN", token)
                guild = await questionary.text("Default Guild/Server ID (optional):").ask_async()
                if guild:
                    config_manager.set_key("DISCORD_GUILD_ID", guild)
                rprint("[bold green]✅ Discord connected![/bold green]")
        
        elif "Telegram" in selection:
            rprint("[bold cyan]📱 Telegram Integration[/bold cyan]")
            rprint("[dim]Create bot via @BotFather on Telegram[/dim]")
            token = await questionary.password("Enter Telegram Bot Token:").ask_async()
            if token:
                config_manager.set_key("TELEGRAM_BOT_TOKEN", token)
                chat_id = await questionary.text("Default Chat ID (optional):").ask_async()
                if chat_id:
                    config_manager.set_key("TELEGRAM_CHAT_ID", chat_id)
                rprint("[bold green]✅ Telegram connected![/bold green]")
        
        elif "ElevenLabs" in selection:
            rprint("[bold cyan]🎙️ ElevenLabs Integration[/bold cyan]")
            rprint("[dim]Get API key at: https://elevenlabs.io/app/api-keys[/dim]")
            key = await questionary.password("Enter ElevenLabs API Key:").ask_async()
            if key:
                config_manager.set_key("ELEVENLABS_API_KEY", key)
                rprint("[bold green]✅ ElevenLabs connected for Voice Support![/bold green]")
                
        elif "Groq" in selection:
            rprint("[bold cyan]⚡ Groq Integration[/bold cyan]")
            rprint("[dim]Get API key at: https://console.groq.com/keys[/dim]")
            rprint("[dim]Note: Excellent for ultra-fast Whisper speech-to-text[/dim]")
            key = await questionary.password("Enter Groq API Key (gsk_...):").ask_async()
            if key:
                config_manager.set_key("GROQ_API_KEY", key)
                rprint("[bold green]✅ Groq connected![/bold green]")
        
        elif "WhatsApp" in selection:
            rprint("[bold cyan]📱 WhatsApp Integration (QR-Code Based)[/bold cyan]")
            is_linked = config_manager.get_key("WHATSAPP_LINKED") == "true"
            status = "Linked ✅" if is_linked else "Not Linked ⬚"
            rprint(f"Status: [bold]{status}[/bold]\n")

            if is_linked:
                re_link = await questionary.confirm("Already linked. Do you want to re-link (re-scan QR)?", default=False).ask_async()
                if not re_link:
                    continue
                config_manager.delete_key("WHATSAPP_LINKED")

            rprint("[dim]Starting WhatsApp client... a QR code will appear below.[/dim]")
            rprint("[dim]Open WhatsApp → Linked Devices → Link a Device and scan the code.[/dim]\n")

            import threading
            import time
            from server.whatsapp_bot import whatsapp_bot # type: ignore

            # Start the bot in a background thread (it's blocking)
            bot_thread = threading.Thread(target=whatsapp_bot.start, daemon=True)
            bot_thread.start()

            # Wait for QR to be generated (up to 15 seconds)
            qr_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads", "whatsapp_qr.png")
            waited = 0
            while not os.path.exists(qr_path) and waited < 15:
                await asyncio.sleep(1)
                waited += 1
                rprint(f"[dim]Waiting for QR ({waited}s)...[/dim]")

            if os.path.exists(qr_path):
                try:
                    import segno # type: ignore
                    # Re-read the QR data from segno isn't doable directly,
                    # but the image was saved — show its path and try ASCII-art via the stored .txt fallback
                    txt_qr = qr_path.replace(".png", ".txt")
                    if os.path.exists(txt_qr):
                        with open(txt_qr) as f:
                            qr_data = f.read().strip()
                        qr = segno.make(qr_data)
                        qr.terminal(compact=True)
                    else:
                        rprint(f"[bold green]QR image saved:[/bold green] [yellow]{qr_path}[/yellow]")
                        rprint("[dim]Open the image and scan it with WhatsApp.[/dim]")
                except Exception:
                    rprint(f"[bold green]QR image saved:[/bold green] [yellow]{qr_path}[/yellow]")
                    rprint("[dim]Open the image and scan it with WhatsApp.[/dim]")

                # Wait up to 60 seconds for the connection — check multiple indicators
                rprint("\n[dim]Waiting for connection (up to 60 seconds)...[/dim]")
                connected = False
                for _ in range(60):
                    # Check our flag, or the client's internal flag, or env key
                    client_connected = getattr(getattr(whatsapp_bot, 'client', None), 'connected', False)
                    env_linked = config_manager.get_key("WHATSAPP_LINKED") == "true"
                    if whatsapp_bot.is_connected or client_connected or env_linked:
                        connected = True
                        # Sync state across all indicators
                        whatsapp_bot.is_connected = True
                        config_manager.set_key("WHATSAPP_LINKED", "true")
                        break
                    await asyncio.sleep(1)

                if connected:
                    # Clean up QR files since they're now stale
                    for f in [qr_path, qr_path.replace(".png", ".txt")]:
                        try: os.remove(f)
                        except: pass
                    rprint("\n[bold green]✅ WhatsApp connected successfully![/bold green]")
                    
                    # POST-LINK SETUP WIZARD (OpenClaw style)
                    rprint("\n[bold cyan]🔧 Initial Channel Setup[/bold cyan]")
                    policy = await questionary.select(
                        "How should Goku handle new WhatsApp DMs?",
                        choices=[
                            {"name": "Allowlist (Recommended: Only specific numbers)", "value": "allowlist"},
                            {"name": "Open (Respond to everyone)", "value": "open"},
                            {"name": "Disabled (Ignore all DMs)", "value": "disabled"}
                        ]
                    ).ask_async()
                    config_manager.set_key("WHATSAPP_DM_POLICY", policy)
                    
                    if policy == "allowlist":
                        numbers = await questionary.text(
                            "Enter allowed phone numbers (comma-separated E.164, e.g., +233201234567):",
                            placeholder="+233201234567",
                            validate=validate_phone_list
                        ).ask_async()
                        if numbers:
                            config_manager.set_key("WHATSAPP_ALLOW_FROM", numbers)
                    
                    owner_num = await questionary.text(
                        "Enter your phone number (Owner Number) to always bypass filters (E.164):",
                        placeholder="+23320XXXXXXX",
                        validate=validate_phone
                    ).ask_async()
                    if owner_num:
                        config_manager.set_key("GOKU_OWNER_NUMBER", owner_num)
                    
                    group_policy = await questionary.select(
                        "How should Goku behave in WhatsApp Groups?",
                        choices=[
                            {"name": "Mentions Only (Responds when '@bot' or 'Goku' is seen)", "value": "mentions"},
                            {"name": "Open (Responds to all messages in groups)", "value": "open"},
                            {"name": "Disabled (Ignore all group messages)", "value": "disabled"}
                        ]
                    ).ask_async()
                    config_manager.set_key("WHATSAPP_GROUP_POLICY", group_policy)
                    rprint("[bold green]WhatsApp configuration complete![/bold green]")
                else:
                    rprint("\n[yellow]⏱ Timed out. Check the server logs — if you see 'Login event: success', the connection worked. Run `goku config` and re-open WhatsApp to confirm.[/yellow]")
            else:
                rprint("[red]Failed to generate QR code. Is the server running?[/red]")

            await questionary.text("Press Enter to go back...").ask_async()


async def goku_channels_menu():
    """Dedicated menu to manage communication channels (WhatsApp, Telegram)."""
    while True:
        rprint(Panel(
            "[bold cyan]📱 CHANNEL MANAGEMENT[/bold cyan]\n"
            "[dim]Manage how Goku communicates with the world.[/dim]",
            border_style="cyan"
        ))
        
        wa_linked = config_manager.get_key("WHATSAPP_LINKED") == "true"
        wa_policy = config_manager.get_key("WHATSAPP_DM_POLICY", "allowlist")
        wa_status = f"[green]Linked[/] (Policy: {wa_policy})" if wa_linked else "[dim]Not Linked[/]"
        
        tg_token = config_manager.get_key("TELEGRAM_BOT_TOKEN")
        tg_status = "[green]Active[/]" if tg_token else "[dim]Not Configured[/]"
        
        owner_num = config_manager.get_key("GOKU_OWNER_NUMBER", "Not Set")
        owner_status = f"[green]{owner_num}[/]" if owner_num != "Not Set" else "[dim]Not Set[/]"
        
        choice = await questionary.select(
            "Select a channel to manage:",
            choices=[
                f"WhatsApp — {wa_status}",
                f"Telegram — {tg_status}",
                f"👤 Owner Number — {owner_status}",
                "⬅️  Back"
            ]
        ).ask_async()
        
        if not choice or "Back" in choice:
            break
            
        if "WhatsApp" in choice:
            sub = await questionary.select(
                "WhatsApp Settings:",
                choices=[
                    "Link / Re-link (QR Login)",
                    "Set DM Policy (Open/Allowlist/Disabled)",
                    "Manage Allowlist (Phone Numbers)",
                    "Set Group Policy (Mentions/Open/Disabled)",
                    "Reset WhatsApp Session (Logout)",
                    "Done"
                ]
            ).ask_async()
            
            if sub == "Link / Re-link (QR Login)":
                # Trigger the existing WhatsApp config logic
                # For simplicity, we just call a dedicated function or reuse the block
                # I'll extract the WhatsApp login logic to a helper later if needed
                # For now, let's just use the integrations menu version
                await configure_integrations() # This is a bit clumsy, but works for now
            elif sub == "Set DM Policy (Open/Allowlist/Disabled)":
                p = await questionary.select("Policy:", choices=["allowlist", "open", "disabled"]).ask_async()
                if p: config_manager.set_key("WHATSAPP_DM_POLICY", p)
            elif sub == "Manage Allowlist (Phone Numbers)":
                curr = config_manager.get_key("WHATSAPP_ALLOW_FROM", "")
                ns = await questionary.text(
                    "Allowed numbers (comma separated):", 
                    default=curr,
                    validate=validate_phone_list
                ).ask_async()
                if ns is not None: config_manager.set_key("WHATSAPP_ALLOW_FROM", ns)
            elif sub == "Set Group Policy (Mentions/Open/Disabled)":
                p = await questionary.select("Group Policy:", choices=["mentions", "open", "disabled"]).ask_async()
                if p: config_manager.set_key("WHATSAPP_GROUP_POLICY", p)
            elif sub == "Reset WhatsApp Session (Logout)":
                confirm = await questionary.confirm("Are you sure you want to delete your WhatsApp session? You will need to re-link with a QR code.").ask_async()
                if confirm:
                    success = whatsapp_bot.logout()
                    if success: rprint("[bold green]WhatsApp session cleared. Restart Goku to link fresh.[/bold green]")
                    else: rprint("[bold red]Failed to clear session. Check server logs.[/bold red]")
                
        elif "Telegram" in choice:
            token = await questionary.password("Telegram Bot Token:", default=tg_token).ask_async()
            if token: config_manager.set_key("TELEGRAM_BOT_TOKEN", token)
            
        elif "Owner Number" in choice:
            curr = config_manager.get_key("GOKU_OWNER_NUMBER", "")
            new_num = await questionary.text(
                "Enter your number (E.164) to bypass all filters:", 
                default=curr,
                validate=validate_phone
            ).ask_async()
            if new_num is not None: config_manager.set_key("GOKU_OWNER_NUMBER", new_num)


async def configure_mcp_servers():
    """Configure MCP server endpoints."""
    rprint(Panel("[bold green]🔧 MCP SERVERS[/bold green]\nConfigure tool server endpoints.", border_style="cyan"))
    
    git_url = await questionary.text(
        "Git MCP Server URL:", 
        default=config_manager.get_key("MCP_GIT_URL", "http://localhost:8080")
    ).ask_async()
    if git_url:
        config_manager.set_key("MCP_GIT_URL", git_url)
    
    search_url = await questionary.text(
        "Search MCP Server URL:", 
        default=config_manager.get_key("MCP_SEARCH_URL", "http://localhost:8081")
    ).ask_async()
    if search_url:
        config_manager.set_key("MCP_SEARCH_URL", search_url)
    
    rprint("[bold green]✅ MCP Servers updated![/bold green]")


async def configure_search():
    """Configure search provider."""
    rprint(Panel("[bold green]🔍 SEARCH PROVIDER[/bold green]\nChoose your search backend.", border_style="cyan"))
    
    current = config_manager.get_key("SEARCH_PROVIDER", "duckduckgo")
    provider = await questionary.select(
        "Select search provider:",
        choices=[
            "DuckDuckGo (Free, no API key needed)",
            "Brave Search (API key required)",
            "Google Search (API key + CX ID required)",
        ],
        default="DuckDuckGo (Free, no API key needed)" if current == "duckduckgo" else "Brave Search (API key required)" if current == "brave" else "Google Search (API key + CX ID required)"
    ).ask_async()
    
    if not provider:
        return
    
    if "DuckDuckGo" in provider:
        config_manager.set_key("SEARCH_PROVIDER", "duckduckgo")
    elif "Brave" in provider:
        config_manager.set_key("SEARCH_PROVIDER", "brave")
        key = await questionary.password("Enter Brave Search API Key:").ask_async()
        if key:
            config_manager.set_key("BRAVE_API_KEY", key)
    elif "Google" in provider:
        config_manager.set_key("SEARCH_PROVIDER", "google")
        key = await questionary.password("Enter Google Search API Key:").ask_async()
        if key:
            config_manager.set_key("GOOGLE_SEARCH_KEY", key)
        cx = await questionary.text("Enter Google Custom Search CX ID:").ask_async()
        if cx:
            config_manager.set_key("GOOGLE_SEARCH_CX", cx)
    
    rprint("[bold green]✅ Search provider updated![/bold green]")


async def configure_vision_provider():
    """Configure dedicated vision model."""
    rprint(Panel("[bold green]📸 VISION PROVIDER[/bold green]\nConfigure a dedicated model for analyzing images.", border_style="cyan"))
    
    current_provider = config_manager.get_key("VISION_PROVIDER", "default")
    
    provider = await questionary.select(
        "Select Vision Provider:",
        choices=[
            "Default (Goku Core Model handles images)",
            "OpenAI (Use GPT-4o for vision)",
            "Google (Use Gemini 2.5 Flash for vision)",
            "Cancel"
        ],
        default=f"Default (Goku Core Model handles images)" if current_provider == "default" else 
                f"OpenAI (Use GPT-4o for vision)" if current_provider == "openai" else
                f"Google (Use Gemini 2.5 Flash for vision)" if current_provider == "google" else "Cancel"
    ).ask_async()
    
    if not provider or provider == "Cancel":
        return

    if "Default" in provider:
        config_manager.set_key("VISION_PROVIDER", "default")
        rprint("[bold yellow]🧹 Vision provider set to Default. Core model will handle images.[/bold yellow]")
    elif "OpenAI" in provider:
        config_manager.set_key("VISION_PROVIDER", "openai")
        # Check for key
        if not config_manager.get_key("OPENAI_API_KEY"):
            rprint("[yellow]OpenAI selected but OPENAI_API_KEY is missing.[/yellow]")
            key = await questionary.password("Enter OpenAI API Key (sk-...):").ask_async()
            if key:
                config_manager.set_key("OPENAI_API_KEY", key)
        rprint("[bold green]✅ Vision provider set to OpenAI (GPT-4o).[/bold green]")
    elif "Google" in provider:
        config_manager.set_key("VISION_PROVIDER", "google")
        # Check for key
        if not config_manager.get_key("GOOGLE_API_KEY"):
            rprint("[yellow]Google selected but GOOGLE_API_KEY is missing.[/yellow]")
            key = await questionary.password("Enter Google API Key:").ask_async()
            if key:
                config_manager.set_key("GOOGLE_API_KEY", key)
                # LiteLLM also uses GEMINI_API_KEY frequently
                config_manager.set_key("GEMINI_API_KEY", key)
        rprint("[bold green]✅ Vision provider set to Google (Gemini 1.5 Flash).[/bold green]")


async def configure_memory():
    """Configure vector memory (Qdrant)."""
    rprint(Panel("[bold green]💾 MEMORY (Qdrant)[/bold green]\nConfigure vector memory for long-term context.", border_style="cyan"))
    
    enabled = await questionary.confirm(
        "Enable vector memory?",
        default=config_manager.get_key("GOKU_MEMORY_ENABLED", "true") == "true"
    ).ask_async()
    
    config_manager.set_key("GOKU_MEMORY_ENABLED", "true" if enabled else "false")
    
    if enabled:
        url = await questionary.text(
            "Qdrant URL:",
            default=config_manager.get_key("QDRANT_URL", "http://localhost:6333")
        ).ask_async()
        if url:
            config_manager.set_key("QDRANT_URL", url)
    
    rprint("[bold green]✅ Memory settings updated![/bold green]")


async def configure_model_prefs():
    """Configure model preferences."""
    rprint(Panel("[bold green]🎛️  MODEL PREFERENCES[/bold green]\nTune how your AI brain operates.", border_style="cyan"))
    
    # Default model
    current_model = config_manager.get_key("GOKU_MODEL", "default")
    model = await questionary.text(
        "Default model (e.g. ollama/kimi-k2.5:cloud, gpt-4o):",
        default=current_model if current_model != "default" else ""
    ).ask_async()
    if model:
        config_manager.set_key("GOKU_MODEL", model)
    
    # Temperature
    current_temp = config_manager.get_key("GOKU_TEMPERATURE", "0.7")
    temp = await questionary.text(
        "Temperature (0.0 = precise, 1.0 = creative):",
        default=current_temp
    ).ask_async()
    if temp:
        config_manager.set_key("GOKU_TEMPERATURE", temp)
    
    # Max tokens
    current_tokens = config_manager.get_key("GOKU_MAX_TOKENS", "4096")
    tokens = await questionary.text(
        "Max output tokens:",
        default=current_tokens
    ).ask_async()
    if tokens:
        config_manager.set_key("GOKU_MAX_TOKENS", tokens)
    
    rprint("[bold green]✅ Model preferences updated![/bold green]")


def view_current_config():
    """Display current configuration with masked values."""
    rprint(Panel("[bold green]📋 CURRENT CONFIGURATION[/bold green]", border_style="cyan"))
    
    all_keys = config_manager.get_all_keys()
    if not all_keys:
        rprint("[yellow]No configuration found. Run 'config' to set up.[/yellow]")
        return
    
    table = Table(title="Goku Configuration", title_style="bold magenta", header_style="bold cyan")
    table.add_column("Key", style="green", min_width=25)
    table.add_column("Value", style="white")
    table.add_column("Status", justify="center")
    
    for key, value in sorted(all_keys.items()):
        # Mask sensitive values (anything with KEY, TOKEN, SECRET in name)
        is_sensitive = any(s in key.upper() for s in ["KEY", "TOKEN", "SECRET", "PASSWORD"])
        display_value = config_manager.mask_value(value) if is_sensitive else value
        status = "[green]✅[/green]" if value else "[red]❌[/red]"
        table.add_row(key, display_value, status)
    
    console.print(table)


async def reset_config():
    """Reset all configuration."""
    if await questionary.confirm(
        "⚠️  This will clear ALL configuration. Are you sure?",
        default=False
    ).ask_async():
        config_manager.reset_all()
        rprint("[bold yellow]🗑️  Configuration reset. Run 'config' to set up again.[/bold yellow]")
    else:
        rprint("[dim]Reset cancelled.[/dim]")


async def goku_config_menu():
    """Main Goku configuration center — the Jarvis control panel."""
    while True:
        rprint(Panel(
            "[bold green]🐉 GOKU CONFIGURATION CENTER[/bold green]\n"
            "[dim]Your personal Jarvis — configure everything from here.[/dim]",
            border_style="green"
        ))
        
        section = await questionary.select(
            "What would you like to configure?",
            choices=[
                "🧠 AI Provider           — Switch or add API keys",
                "🔗 Integrations           — GitHub, Slack, Notion, Spotify & more",
                "🔧 MCP Servers            — Git, Search, Shell endpoints",
                "🔍 Search Provider        — Brave / Google / DuckDuckGo",
                "📸 Vision Provider        — Dedicated model for viewing images",
                "💾 Memory (Qdrant)        — Vector memory for long-term context",
                "🎛️  Model Preferences      — Default model, temperature, tokens",
                "📋 View Current Config",
                "🗑️  Reset Config",
                "⬅️  Done",
            ]
        ).ask_async()
        
        if not section or "Done" in section:
            return
        
        if "AI Provider" in section:
            await setup_wizard()
        elif "Integrations" in section:
            await configure_integrations()
        elif "MCP Servers" in section:
            await configure_mcp_servers()
        elif "Search Provider" in section:
            await configure_search()
        elif "Vision Provider" in section:
            await configure_vision_provider()
        elif "Memory" in section:
            await configure_memory()
        elif "Model Preferences" in section:
            await configure_model_prefs()
        elif "View Current" in section:
            view_current_config()
        elif "Reset" in section:
            await reset_config()


@app.command()
def logs(lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show")):
    """View Goku diagnostic logs."""
    if not os.path.exists(LOG_FILE):
        rprint("[yellow]No log file found yet.[/yellow]")
        return
    
    rprint(Panel(f"[bold green]📜 GOKU DIAGNOSTIC LOGS[/bold green] (Last {lines} lines)", border_style="cyan"))
    try:
        with open(LOG_FILE, "r") as f:
            all_lines = f.readlines()
            start_idx = max(0, len(all_lines) - lines)
            last_lines = [all_lines[i] for i in range(start_idx, len(all_lines))]
            for line in last_lines:
                # Colorize based on level
                if "ERROR" in line: rprint(f"[red]{line.strip()}[/red]")
                elif "WARNING" in line: rprint(f"[yellow]{line.strip()}[/yellow]")
                elif "DEBUG" in line: rprint(f"[dim]{line.strip()}[/dim]")
                else: rprint(line.strip())
    except Exception as e:
        rprint(f"[red]Failed to read logs: {e}[/red]")

@app.command()
def update():
    """Update Goku to the latest version via git."""
    rprint("[bold green]⬇️  Checking for updates...[/bold green]")
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    update_sh = os.path.join(script_dir, "goku.sh")
    
    if not os.path.exists(update_sh):
        rprint("[red]Global wrapper goku.sh not found. Please pull manually.[/red]")
        return

    # Call the existing update logic in goku.sh
    import subprocess
    try:
        subprocess.run(["bash", update_sh, "update"], check=True)
    except Exception as e:
        rprint(f"[red]Update failed: {e}[/red]")

@app.command()
def config():
    """Open Goku configuration center."""
    try:
        asyncio.run(goku_config_menu())
    except Exception as e:
        rprint(f"[red]Failed to start config menu: {e}[/red]")

@app.command()
def interactive():
    """Start an interactive chat session with Goku."""
    # Run wizard if no providers found
    if not router.available_providers:
        rprint("[bold yellow]No AI provider keys detected. Goku requires a brain to function.[/bold yellow]")
        try:
            asyncio.run(setup_wizard())
        except Exception as e:
            rprint(f"[red]Wizard failed: {e}[/red]")
        # Re-check after wizard
        if not router.available_providers:
            rprint("[bold red]No provider configured. Exiting.[/bold red]")
            return

    console.clear()
    rprint(Panel("[bold green]🐉 GOKU CLI AGENT v2.5[/bold green]\nType [bold red]'exit'[/bold red] to quit or [bold cyan]'status'[/bold cyan] for info.", border_style="green"))
    
    # Run the main async loop
    try:
        asyncio.run(interactive_loop())
    except (KeyboardInterrupt, EOFError):
        rprint("\n[dim]Goodbye![/dim]")

async def interactive_loop():
    """Main async loop for the interactive session."""
    # Note: Telegram and WhatsApp bots are now managed by 'server/gateway.py'.
    # Running them here would cause conflicts (e.g., WhatsApp StreamReplaced error).
    # The CLI now focused purely on terminal interaction.
    
    # Initialize session with history and lexer
    session = PromptSession(
        history=InMemoryHistory(),
        lexer=PygmentsLexer(GokuLexer),
        style=goku_style
    )

    while True:
        try:
            # Rich input loop - yields to event loop (Telegram bot) while waiting
            query = await session.prompt_async("You: ")
        except (EOFError, KeyboardInterrupt):
             # Handle Ctrl+C/D gracefully
            break
            
        if not query: continue
        query = query.strip()
        
        if query.startswith("/"):
            parts = query.split(" ", 2)
            cmd = parts[0].lower()
            
            if cmd == "/provider":
                if len(parts) < 2:
                    rprint("[yellow]Usage: /provider [openai|anthropic|github|ollama][/yellow]")
                    continue
                provider = parts[1].lower()
                if provider == "openai": agent.model_override = "gpt-4o"
                elif provider == "anthropic": agent.model_override = "claude-3-5-sonnet-20240620"
                elif provider == "github": agent.model_override = "github/gpt-4o"
                elif provider == "google": agent.model_override = "gemini/gemini-3.1-pro-preview"
                elif provider == "groq": agent.model_override = "groq/llama-3.3-70b-versatile"
                elif provider == "openrouter": agent.model_override = "openrouter/anthropic/claude-3.5-sonnet"
                elif provider == "huggingface": agent.model_override = "huggingface/meta-llama/Llama-3.2-3B-Instruct"
                elif provider == "perplexity": agent.model_override = "perplexity/sonar-reasoning"
                elif provider == "mistral": agent.model_override = "mistral/mistral-large-latest"
                elif provider == "ollama":
                    discovered = router.discover_ollama_models()
                    agent.model_override = f"ollama/{discovered[0]}" if discovered else "ollama/default"
                else: rprint(f"[red]Unknown provider: {provider}[/red]")
                rprint(f"[bold green]Switching to {provider} ({agent.model_override})[/bold green]")
                continue
            
            elif cmd == "/models":
                provider = parts[1].lower() if len(parts) > 1 else None
                with console.status("[bold cyan]Fetching available models...[/bold cyan]"):
                    models = await agent.get_models(provider)
                
                if not models:
                    rprint("[yellow]No models found. Ensure your API key is correct.[/yellow]")
                    continue
                
                table = Table(title=f"Available Models ({provider or 'current'})", title_style="bold magenta", header_style="bold cyan")
                table.add_column("Model ID", style="green")
                for m in models[:20]: # Limit to 20
                    table.add_row(str(m))
                if len(models) > 20:
                    table.add_row(f"... and {len(models) - 20} more")
                console.print(table)
                continue

            elif cmd == "/model":
                if len(parts) < 2:
                    rprint("[yellow]Usage: /model [model_name][/yellow]")
                    continue
                agent.model_override = parts[1]
                rprint(f"[bold green]Model switched to {agent.model_override}[/bold green]")
                continue

            elif cmd == "/set-key":
                if len(parts) < 3:
                     rprint("[yellow]Usage: /set-key KEY_NAME VALUE[/yellow]")
                     continue
                key_name = parts[1].upper()
                key_val = parts[2]
                config_manager.set_key(key_name, key_val)
                rprint(f"[bold green]Set {key_name} successfully.[/bold green]")
                continue
            
            elif cmd == "/reset":
                agent.history = []
                # Clear memory? Not yet.
                rprint("[bold green]Chat history cleared.[/bold green]")
                continue

            elif cmd == "/ping":
                # Telegram status
                tg_token = config_manager.get_key("TELEGRAM_BOT_TOKEN")
                tg_status = "✅ Online" if tg_token else "🚫 Not Configured"
                
                # WhatsApp status
                wa_linked = config_manager.get_key("WHATSAPP_LINKED") == "true"
                wa_status = "✅ Linked" if wa_linked else "⬚ Not Linked"
                
                rprint(f"[bold green]🏓 Pong! Agent is active.[/bold green]")
                rprint(f"[dim]Telegram Bot: {tg_status}[/dim]")
                rprint(f"[dim]WhatsApp Bot: {wa_status}[/dim]")
                continue

            elif cmd == "/view":
                if len(parts) < 2:
                    rprint("[yellow]Usage: /view [image_path] [optional question][/yellow]")
                    continue
                path = parts[1]
                if not os.path.exists(path):
                    rprint(f"[red]Error: File not found at {path}[/red]")
                    continue
                
                additional_query = parts[2] if len(parts) > 2 else "Analyze this image."
                query = f"[Photo Received: {path}] {additional_query}"
                # Fall through to run_chat(query)
                pass

            elif cmd == "/channels":
                await goku_channels_menu()
                continue

            elif cmd == "/persona":
                # Fall through to run_chat(query) so agent handles the /persona wizard
                pass

            elif cmd == "/config":
                await goku_config_menu()
                continue
            
            elif cmd == "/help":
                table = Table(title="Available Commands", title_style="bold magenta", header_style="bold cyan", box=None)
                table.add_column("Command", style="bold yellow")
                table.add_column("Description", style="white")
                table.add_row("/help", "Show this help message")
                table.add_row("/ping", "Check agent status")
                table.add_row("/channels", "Manage communication channels")
                table.add_row("/config", "Open configuration menu")
                table.add_row("/provider [name]", "Switch AI provider (openai, anthropic, ollama...)")
                table.add_row("/models [provider]", "List available models")
                table.add_row("/model [name]", "Switch specific model")
                table.add_row("/set-key [k] [v]", "Set API key or env var")
                table.add_row("/reset", "Clear chat history")
                table.add_row("/persona", "Manage AI personalities (Create/Assign)")
                table.add_row("/view [path]", "Send an image to Goku (Native Vision)")
                table.add_row("status", "Show agent status")
                table.add_row("exit / quit", "Exit agent")
                console.print(table)
                continue

            elif cmd in ["exit", "quit"]:
                rprint("[bold green]Goodbye! 👋[/bold green]")
                sys.exit(0)

            else:
                rprint(f"[red]Unknown command: {cmd}[/red]")
                continue
        
        # Regular chat message
        if query.lower() in ["exit", "quit"]:
            break
        elif query.lower() == "status":
            rprint(Panel(get_status_str(), title="Goku Status", border_style="blue"))
            continue
        elif query.lower() == "clear":
             console.clear()
             continue
        elif query.lower() == "config":
            await goku_config_menu()
            continue
            
        if not query:
            continue
            
        try:
            await run_chat(query)
        except Exception as e:
            # We already handled the live.stop() and thought suppression inside run_chat.
            # Now we just decide if we want to show the recovery menu.
            err_str = str(e).lower()
            is_api_err = any(x in err_str for x in ["rate limit", "401", "400", "auth", "unauthorized", "exhausted", "bad request", "invalid"])
            
            if is_api_err:
                # Don't show a long traceback, run_chat already printed a clean error panel if it wasn't swallowed.
                if await questionary.confirm("Would you like to switch to a different AI brain?").ask_async():
                    if switch_provider_menu():
                        rprint("[dim]Provider updated. You can retry your command now.[/dim]")
            else:
                # For non-recoverable logic crashes, maybe show more detail if needed, but still keep it clean.
                rprint(Panel(f"[bold red]CRASH DETECTED:[/bold red] {str(e)}", border_style="red"))

if __name__ == "__main__":
    app()
