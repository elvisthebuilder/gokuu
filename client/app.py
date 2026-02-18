import asyncio
import typer
import questionary
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.text import Text
from rich.table import Table
from rich import print as rprint
import sys
import os
import logging

# Silence LiteLLM's noisy tracebacks — Goku handles errors gracefully
logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
logging.getLogger("litellm").setLevel(logging.CRITICAL)
logging.getLogger("LiteLLM Router").setLevel(logging.CRITICAL)
logging.getLogger("LiteLLM Proxy").setLevel(logging.CRITICAL)

# Add parent directory to sys.path to allow importing from server
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.agent import agent
from server.memory import memory
from server.lite_router import router
from server.config_manager import config_manager

# Prompt Toolkit for rich input
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.styles import Style
from prompt_toolkit.lexers import PygmentsLexer
from pygments.lexer import RegexLexer
from pygments.token import Token

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

async def confirm_execution(tool_name: str, args: dict) -> bool:
    """Non-blocking execution confirmation."""
    cmd = args.get("command", str(args))
    
    # Check cache (prevent repetitive prompts)
    if not hasattr(confirm_execution, "cache"):
        confirm_execution.cache = set()
    if cmd in confirm_execution.cache:
        return True
        
    # Check Session Trust (allow user to whitelist tool)
    if not hasattr(confirm_execution, "session_allowlist"):
        confirm_execution.session_allowlist = set()
    if tool_name in confirm_execution.session_allowlist:
        return True
    
    # Handle Live display conflict
    live = getattr(confirm_execution, "live_ctx", None)
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
        
        if answer == "No": return False
        
        if "Trust" in answer:
            confirm_execution.session_allowlist.add(tool_name)
            
        confirm_execution.cache.add(cmd)
        return True
    finally:
        if live and not live.is_started:
            live.start()

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
        confirm_execution.live_ctx = live
        try:
            async for event in agent.run_agent(query):
                if event["type"] == "thought":
                    if not live.is_started: live.start()
                    thought_spinner = Spinner("dots", text=Text(event['content'], style="dim"), style="cyan")
                    live.update(Panel(thought_spinner, title="💭 Thinking", border_style="dim", title_align="left"))
                
                elif event["type"] == "message":
                    live.stop()
                    console.print(Panel(Markdown(event["content"]), title="[bold green]GOKU[/bold green]", border_style="green", title_align="left"))
                    # Don't restart Live immediately if we want to show the message cleanly
                    # The next event (thought or tool) will restart it if needed
                    # live.start()
                
                elif event["type"] == "tool_call":
                    live.start() # Ensure live is running
                    exec_spinner = Spinner("dots", text=Text.from_markup(f" Executing: [bold yellow]{event['name']}[/bold yellow]"), style="yellow")
                    live.update(Panel(exec_spinner, title="🛠️  Executing", subtitle=f"[dim]{event['name']}[/dim]", border_style="yellow", title_align="left", subtitle_align="right"))
                
                elif event["type"] == "task_update":
                    # Render task list in a side panel or dedicated area
                    task_text = ""
                    for i, t in enumerate(event["tasks"]):
                        marker = "[green]✓[/]" if t["status"] == "done" else "[blue]>[/]" if t["status"] == "in_progress" else "[dim]•[/]"
                        task_text += f"{marker} {t['desc']}\n"
                    
                    live.stop()
                    console.print(Panel(task_text.strip(), title="📋 GOKU'S PLAN", border_style="cyan", title_align="left"))
                    live.start()
                
                elif event["type"] == "tool_result":
                    # Tool results are usually handled internally by agent, 
                    # but we could show them if they are too big/important.
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
            import httpx
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
    elif "Google" in selection: agent.model_override = "gemini/gemini-1.5-flash"
    elif "xAI" in selection: agent.model_override = "xai/grok-2-latest"
    elif "OpenRouter" in selection: agent.model_override = "openrouter/anthropic/claude-3.5-sonnet"
    elif "Qwen" in selection: agent.model_override = "qwen/qwen-turbo"
    elif "Z.AI" in selection: agent.model_override = "zai/glm-4"
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
        elif "Memory" in section:
            await configure_memory()
        elif "Model Preferences" in section:
            await configure_model_prefs()
        elif "View Current" in section:
            view_current_config()
        elif "Reset" in section:
            await reset_config()


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
    rprint(Panel("[bold green]🐉 GOKU CLI AGENT v1.0[/bold green]\nType [bold red]'exit'[/bold red] to quit or [bold cyan]'status'[/bold cyan] for info.", border_style="green"))
    
    # Run the main async loop
    try:
        asyncio.run(interactive_loop())
    except (KeyboardInterrupt, EOFError):
        rprint("\n[dim]Goodbye![/dim]")

async def interactive_loop():
    """Main async loop for the interactive session."""
    # Start Telegram Bot if configured
    telegram_token = config_manager.get_key("TELEGRAM_BOT_TOKEN")
    if telegram_token:
        try:
            from server.telegram_bot import start_telegram_bot
            # Run in background
            asyncio.create_task(start_telegram_bot(telegram_token))
            rprint("[dim]📱 Telegram bot started in background[/dim]")
        except Exception as e:
            rprint(f"[red]Failed to start Telegram Bot: {e}[/red]")

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
                elif provider == "google": agent.model_override = "gemini/gemini-1.5-flash"
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
                token = config_manager.get_key("TELEGRAM_BOT_TOKEN")
                status = "✅ Online" if token else "🚫 Not Configured"
                rprint(f"[bold green]🏓 Pong! Agent is active.[/bold green]")
                rprint(f"[dim]Telegram Bot: {status}[/dim]")
                continue

            elif cmd == "/config":
                await goku_config_menu()
                continue
            
            elif cmd == "/help":
                table = Table(title="Available Commands", title_style="bold magenta", header_style="bold cyan", box=None)
                table.add_column("Command", style="bold yellow")
                table.add_column("Description", style="white")
                table.add_row("/help", "Show this help message")
                table.add_row("/ping", "Check agent status")
                table.add_row("/config", "Open configuration menu")
                table.add_row("/provider [name]", "Switch AI provider (openai, anthropic, ollama...)")
                table.add_row("/models [provider]", "List available models")
                table.add_row("/model [name]", "Switch specific model")
                table.add_row("/set-key [k] [v]", "Set API key or env var")
                table.add_row("/reset", "Clear chat history")
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
                if questionary.confirm("Would you like to switch to a different AI brain?").ask():
                    if switch_provider_menu():
                        rprint("[dim]Provider updated. You can retry your command now.[/dim]")
            else:
                # For non-recoverable logic crashes, maybe show more detail if needed, but still keep it clean.
                rprint(Panel(f"[bold red]CRASH DETECTED:[/bold red] {str(e)}", border_style="red"))

if __name__ == "__main__":
    app()
