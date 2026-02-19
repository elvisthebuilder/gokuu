import os
import logging
import json
import httpx
import litellm
from litellm import acompletion
from typing import List, Dict, Any, Generator, Optional

logger = logging.getLogger(__name__)

class LiteRouter:
    def __init__(self):
        # Configure LiteLLM
        litellm.telemetry = False
        litellm.drop_params = True
        litellm.suppress_debug_info = True
        os.environ["LITELLM_LOG"] = "ERROR"  # Suppress Give Feedback messages
        self.http_client = httpx.AsyncClient(timeout=10.0)

    @property
    def available_providers(self) -> List[str]:
        """Dynamically detect available providers based on environment.
        Env var mapping aligned with OpenClaw's model-auth.ts."""
        providers = []
        
        def has_key(key):
            val = os.getenv(key)
            return val is not None and len(val.strip()) > 0

        # --- Core providers ---
        if has_key("OPENAI_API_KEY"):
            providers.append("openai")
        if has_key("ANTHROPIC_API_KEY") or has_key("ANTHROPIC_OAUTH_TOKEN"):
            providers.append("anthropic")
        if has_key("GEMINI_API_KEY") or has_key("GOOGLE_API_KEY"):
            providers.append("google")
            # Sync for litellm
            if has_key("GOOGLE_API_KEY") and not has_key("GEMINI_API_KEY"):
                os.environ["GEMINI_API_KEY"] = os.getenv("GOOGLE_API_KEY", "")
        if has_key("GROQ_API_KEY"):
            providers.append("groq")
        if has_key("XAI_API_KEY"):
            providers.append("xai")
        if has_key("OPENROUTER_API_KEY"):
            providers.append("openrouter")
        if has_key("DEEPSEEK_API_KEY"):
            providers.append("deepseek")
        if has_key("MISTRAL_API_KEY"):
            providers.append("mistral")
        if has_key("PERPLEXITY_API_KEY"):
            providers.append("perplexity")
        if has_key("COHERE_API_KEY"):
            providers.append("cohere")

        # --- GitHub Copilot ---
        if has_key("GITHUB_TOKEN") or has_key("COPILOT_GITHUB_TOKEN") or has_key("GH_TOKEN"):
            providers.append("github")
            token = os.getenv("COPILOT_GITHUB_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
            if token:
                os.environ["GITHUB_API_KEY"] = token

        # --- OpenClaw-aligned providers (model-auth.ts envMap) ---
        if has_key("MINIMAX_API_KEY") or has_key("MINIMAX_OAUTH_TOKEN"):
            providers.append("minimax")
        if has_key("MOONSHOT_API_KEY"):
            providers.append("moonshot")
        if has_key("QIANFAN_API_KEY"):
            providers.append("qianfan")
        if has_key("XIAOMI_API_KEY"):
            providers.append("xiaomi")
        if has_key("VENICE_API_KEY"):
            providers.append("venice")
        if has_key("TOGETHER_API_KEY"):
            providers.append("together")
        if has_key("LITELLM_API_KEY"):
            providers.append("litellm")
        if has_key("SYNTHETIC_API_KEY"):
            providers.append("synthetic")
        if has_key("NVIDIA_API_KEY"):
            providers.append("nvidia")
        if has_key("CHUTES_API_KEY") or has_key("CHUTES_OAUTH_TOKEN"):
            providers.append("chutes")
        if has_key("QWEN_PORTAL_API_KEY") or has_key("QWEN_OAUTH_TOKEN"):
            providers.append("qwen")
        if has_key("ZAI_API_KEY") or has_key("Z_AI_API_KEY"):
            providers.append("zai")
        if has_key("HF_TOKEN") or has_key("HUGGINGFACE_HUB_TOKEN"):
            providers.append("huggingface")
        if has_key("OPENCODE_API_KEY") or has_key("OPENCODE_ZEN_API_KEY"):
            providers.append("opencode")
        if has_key("AI_GATEWAY_API_KEY"):
            providers.append("ai-gateway")
        if has_key("CLOUDFLARE_AI_GATEWAY_API_KEY"):
            providers.append("cloudflare-ai-gateway")

        # --- Local providers ---
        if has_key("VLLM_BASE_URL") or has_key("VLLM_API_KEY"):
            providers.append("vllm")
        if has_key("OLLAMA_BASE_URL"):
            providers.append("ollama")
        if has_key("CUSTOM_BASE_URL") or has_key("CUSTOM_API_KEY"):
            providers.append("custom")
        
        if not providers:
             logger.warning("No AI provider keys or Ollama URL detected in environment.")
        return providers


    def discover_ollama_models(self) -> List[str]:
        """Query Ollama /api/tags to discover available models (OpenClaw pattern)."""
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        if base.lower().endswith("/v1"):
            base = base[:-3]
        try:
            import httpx
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{base}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("models", [])
                    return [m["name"] for m in models if "name" in m]
        except Exception as e:
            logger.warning(f"Failed to discover Ollama models: {e}")
        return []

    def get_default_model(self) -> str:
        """Pick the best available model based on keys or env override."""
        # Check for explicit override
        env_model = os.getenv("GOKU_MODEL")
        if env_model and env_model != "default":
            logger.info(f"Using GOKU_MODEL override: {env_model}")
            return env_model

        available = self.available_providers
        
        # Prioritize Ollama when explicitly configured (OpenClaw pattern)
        # Dynamically discover which model is actually available
        if "ollama" in available:
            models = self.discover_ollama_models()
            if models:
                return f"ollama/{models[0]}"
            logger.warning("Ollama configured but no models found. Run: ollama pull <model>")

        if "openai" in available:
            return "gpt-4o"
        if "anthropic" in available:
            return "claude-3-5-sonnet-20240620"
        if "github" in available:
            return "github/gpt-4o"
        if "google" in available:
            return "gemini/gemini-1.5-flash"
        if "groq" in available:
            return "groq/llama-3.3-70b-versatile"
        if "openrouter" in available:
            return "openrouter/anthropic/claude-3.5-sonnet"
        if "huggingface" in available:
            return "huggingface/meta-llama/Llama-3.2-3B-Instruct"
        
        # Last resort — ask Ollama anyway
        return "ollama/default"

    def normalize_model(self, model: str) -> str:
        """Automatically prefix models with provider if missing."""
        m = model.lower()
        if "/" in m: return model
        
        # Prefix extraction logic
        if m.startswith("gpt-"): return f"openai/{model}"
        if m.startswith("claude-"): return f"anthropic/{model}"
        if m.startswith("gemini-"): return f"gemini/{model}"
        if m.startswith("llama-") or m.startswith("mixtral-"):
            if "groq" in self.available_providers: return f"groq/{model}"
            return f"huggingface/{model}"
        
        available = self.available_providers
        if "openai" in available and m in ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]:
            return f"openai/{model}"
        if "anthropic" in available and m.startswith("claude"):
            return f"anthropic/{model}"
            
        return model

    async def get_available_models(self, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch available models from the provider's API."""
        available = self.available_providers
        if not provider:
            # If no provider specified, try the default or current one
            model = self.get_default_model()
            provider = model.split("/")[0] if "/" in model else "openai"

        results = []
        try:
            if provider == "openrouter":
                key = os.getenv("OPENROUTER_API_KEY")
                resp = await self.http_client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {key}"} if key else {}
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    for m in data:
                        results.append({
                            "id": f"openrouter/{m['id']}",
                            "name": m.get("name", m["id"]),
                            "context": m.get("context_length")
                        })
            elif provider == "ollama":
                base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
                resp = await self.http_client.get(f"{base_url}/api/tags")
                if resp.status_code == 200:
                    data = resp.json().get("models", [])
                    for m in data:
                        results.append({
                            "id": f"ollama/{m['name']}",
                            "name": m['name'],
                            "size": m.get("size")
                        })
            elif provider == "huggingface":
                # Static list for HF or search if token exists
                key = os.getenv("HUGGINGFACE_API_KEY")
                if key:
                    # Search trending models or something similar
                    # For now just return a few popular ones + litellm list
                    pass
                
            # Fallback to litellm's static list for known providers
            if not results:
                # Use litellm.models_by_provider or similar if available
                # For now, return a few defaults for common ones
                defaults = {
                    "openai": ["gpt-4o", "gpt-4o-mini"],
                    "anthropic": ["claude-3-5-sonnet-20240620", "claude-3-opus-20240229"],
                    "google": ["gemini/gemini-1.5-flash", "gemini/gemini-1.5-pro"],
                    "groq": ["groq/llama-3.3-70b-versatile", "groq/mixtral-8x7b-32768"],
                    "github": ["github/gpt-4o", "github/claude-3-5-sonnet"]
                }
                if provider in defaults:
                    for m in defaults[provider]:
                        results.append({"id": m, "name": m})
        except Exception as e:
            logger.error(f"Error fetching models for {provider}: {e}")
            
        return results

    async def _ollama_chat(self, model: str, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> Any:
        """Direct Ollama /api/chat call — follows OpenClaw's native API pattern."""
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        # Strip /v1 suffix if present (OpenClaw pattern: resolveOllamaApiBase)
        base = base.rstrip("/")
        if base.lower().endswith("/v1"):
            base = base[:-3]
        
        chat_url = f"{base}/api/chat"
        model_name = model.replace("ollama/", "", 1)
        
        # Build Ollama native request body
        # Standardize messages for Ollama (tool arguments as dict, not string)
        import copy
        ollama_messages = copy.deepcopy(messages)
        for msg in ollama_messages:
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    args = func.get("arguments")
                    if isinstance(args, str):
                        try:
                            # Ollama expects dict arguments, not JSON string
                            func["arguments"] = json.loads(args)
                        except:
                            pass

        body = {
            "model": model_name,
            "messages": ollama_messages,
            "stream": False,
            "options": {"num_ctx": 65536}
        }
        if tools:
            body["tools"] = tools
        
        logger.info(f"Ollama direct call: {chat_url} model={model_name}")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(chat_url, json=body)
            if resp.status_code != 200:
                error_text = resp.text
                if resp.status_code == 404 and "not found" in error_text.lower():
                    raise Exception(f"Local model '{model_name}' not found. Please run: ollama pull {model_name}")
                raise Exception(f"Ollama API error {resp.status_code}: {error_text}")
            
            data = resp.json()
        
        # Convert Ollama native response to litellm-compatible format
        # so the rest of agent.py can process it uniformly
        content = data.get("message", {}).get("content", "")
        tool_calls_raw = data.get("message", {}).get("tool_calls", [])
        
        # Build a mock litellm-style response object
        class OllamaChoice:
            def __init__(self, content, tool_calls, finish_reason):
                self.message = type('msg', (), {
                    'content': content,
                    'tool_calls': tool_calls,
                    'role': 'assistant'
                })()
                self.finish_reason = finish_reason
        
        class OllamaResponse:
            def __init__(self, content, tool_calls_raw, model_name):
                # Convert tool calls to litellm format
                converted_tools = []
                for tc in tool_calls_raw:
                    func = tc.get("function", {})
                    tool_obj = type('tool_call', (), {
                        'id': f"ollama_call_{id(tc)}",
                        'type': 'function',
                        'function': type('func', (), {
                            'name': func.get('name', ''),
                            'arguments': json.dumps(func.get('arguments', {}))
                        })()
                    })()
                    converted_tools.append(tool_obj)
                
                finish = "tool_calls" if converted_tools else "stop"
                self.choices = [OllamaChoice(content, converted_tools or None, finish)]
                self.model = model_name
                self.usage = type('usage', (), {
                    'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0
                })()
                self.id = f"ollama-{id(self)}"
                self.created = 0
        
        return OllamaResponse(content, tool_calls_raw, model_name)

    async def _ollama_chat_stream(self, model: str, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None) -> Any:
        """Streaming version of Ollama chat."""
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        # Strip /v1 suffix if present
        base = base.rstrip("/")
        if base.lower().endswith("/v1"):
            base = base[:-3]
        
        chat_url = f"{base}/api/chat"
        model_name = model.replace("ollama/", "", 1)
        
        # Build Ollama native request body
        import copy
        ollama_messages = copy.deepcopy(messages)
        for msg in ollama_messages:
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    args = func.get("arguments")
                    if isinstance(args, str):
                        try:
                            # Ollama expects dict arguments, not JSON string
                            func["arguments"] = json.loads(args)
                        except:
                            pass

        body = {
            "model": model_name,
            "messages": ollama_messages,
            "stream": True,
            "options": {"num_ctx": 65536},
            "think": True # Enable native thinking for supporting models
        }
        if tools:
            body["tools"] = tools
        
        logger.info(f"Ollama streaming call: {chat_url} model={model_name}")
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", chat_url, json=body) as resp:
                if resp.status_code != 200:
                    error_text = await resp.read()
                    raise Exception(f"Ollama API error {resp.status_code}: {error_text.decode()}")
                
                async for line in resp.aiter_lines():
                    if not line: continue
                    try:
                        chunk = json.loads(line)
                    except:
                        continue
                        
                    msg = chunk.get("message", {})
                    content = msg.get("content", "")
                    thinking = msg.get("thinking", "") # Capture native thinking field
                    tool_calls_raw = msg.get("tool_calls", [])
                    done = chunk.get("done", False)
                    
                    # Convert to litellm-style delta object
                    class Delta:
                        def __init__(self, content, thinking, tool_calls, role):
                            self.content = content
                            self.thinking = thinking
                            self.tool_calls = tool_calls
                            self.role = role

                    class Choice:
                        def __init__(self, delta, finish_reason):
                            self.delta = delta
                            self.finish_reason = finish_reason

                    class Chunk:
                        def __init__(self, choice):
                            self.choices = [choice]

                    # Convert tool calls to litellm delta format if any
                    converted_tools = []
                    if tool_calls_raw:
                        for i, tc in enumerate(tool_calls_raw):
                            func = tc.get("function", {})
                            tool_obj = type('tool_call_chunk', (), {
                                'index': i,
                                'id': f"ollama_call_{id(tc)}",
                                'type': 'function',
                                'function': type('func', (), {
                                    'name': func.get('name'),
                                    'arguments': json.dumps(func.get('arguments', {}))
                                })()
                            })()
                            converted_tools.append(tool_obj)
                    
                    finish_reason = "stop" if done else None
                    if converted_tools:
                         finish_reason = "tool_calls" if done else None

                    yield Chunk(Choice(Delta(content, thinking, converted_tools or None, "assistant"), finish_reason))

    async def get_response(self, model: str, messages: List[Dict[str, str]], tools: List[Dict[str, Any]] = None, stream: bool = True) -> Any:
        try:
            # Use detected default if no specific model requested
            if not model or model == "default":
                model = self.get_default_model()
            else:
                model = self.normalize_model(model)
            
            # Direct Ollama call — bypass litellm entirely (OpenClaw pattern)
            if model.startswith("ollama/"):
                if stream:
                    return self._ollama_chat_stream(model, messages, tools)
                else:
                    return await self._ollama_chat(model, messages, tools)
            
            # Detect currently available providers
            available = self.available_providers
            
            # Build dynamic fallbacks for cloud providers
            fallbacks = []
            if "openai" in available and model != "gpt-4o":
                fallbacks.append("gpt-4o")
            if "anthropic" in available and model != "claude-3-5-sonnet-20240620":
                fallbacks.append("claude-3-5-sonnet-20240620")
            if "github" in available and not model.startswith("github/"):
                fallbacks.append("github/gpt-4o")
            if "google" in available and not model.startswith("gemini/"):
                fallbacks.append("gemini/gemini-1.5-flash")
            if "groq" in available and not model.startswith("groq/"):
                fallbacks.append("groq/llama-3.3-70b-versatile")
            if "openrouter" in available and not model.startswith("openrouter/"):
                fallbacks.append("openrouter/anthropic/claude-3.5-sonnet")
            if "huggingface" in available and not model.startswith("huggingface/"):
                fallbacks.append("huggingface/meta-llama/Llama-3.2-3B-Instruct")
            
            # Sync GitHub key for LiteLLM
            if (model.startswith("github/") or any(f.startswith("github/") for f in fallbacks)) and not os.environ.get("GITHUB_API_KEY"):
                os.environ["GITHUB_API_KEY"] = os.getenv("GITHUB_TOKEN", "")

            logger.info(f"LiteRouter: Attempting {model} (Fallbacks: {fallbacks})")

            kwargs = {
                "model": model,
                "messages": messages,
                "stream": stream
            }
            if fallbacks:
                kwargs["fallbacks"] = fallbacks
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            return await acompletion(**kwargs)
        except litellm.AuthenticationError as e:
            fallback_local = "ollama/default"
            if os.getenv("OLLAMA_BASE_URL"):
                ollama_models = self.discover_ollama_models()
                fallback_local = f"ollama/{ollama_models[0]}" if ollama_models else "ollama/default"
            
            try:
                from rich import print as rprint
                rprint(f"[bold yellow]⚠️  Auth failed: {model}. Falling back to {fallback_local}...[/bold yellow]")
            except ImportError:
                print(f"⚠️  Auth failed: {model}. Falling back to {fallback_local}...")
            
            # If cloud auth fails and Ollama is available, fall back to it
            if os.getenv("OLLAMA_BASE_URL"):
                try:
                    if stream:
                         return self._ollama_chat_stream(fallback_local, messages, tools)
                    return await self._ollama_chat(fallback_local, messages, tools)
                except Exception as local_err:
                    logger.error(f"Critical: Local fallback also failed: {str(local_err)}")
                    raise Exception(f"All providers failed. Cloud: Auth Error. Local: {str(local_err)}")
            
            raise Exception("Authentication Failed. Please check your API key.")

        except Exception as e:
            logger.error(f"Error in LiteRouter: {str(e)}")
            err_msg = str(e).lower()
            is_auth_error = any(x in err_msg for x in ["401", "api key", "credentials", "unauthorized", "bad credentials"])
            
            # If cloud auth fails and Ollama is available, fall back to it
            if is_auth_error and not model.startswith("ollama/") and os.getenv("OLLAMA_BASE_URL"):
                # Discover actual available model (OpenClaw pattern)
                ollama_models = self.discover_ollama_models()
                fallback_local = f"ollama/{ollama_models[0]}" if ollama_models else "ollama/default"
                
                try:
                    from rich import print as rprint
                    rprint(f"[bold yellow]⚠️  Auth failed: {model}. Falling back to {fallback_local}...[/bold yellow]")
                except ImportError:
                    print(f"⚠️  Auth failed: {model}. Falling back to {fallback_local}...")
                
                try:
                    if stream:
                         return self._ollama_chat_stream(fallback_local, messages, tools)
                    return await self._ollama_chat(fallback_local, messages, tools)
                except Exception as local_err:
                    logger.error(f"Critical: Local fallback also failed: {str(local_err)}")
                    raise Exception(f"All providers failed. Cloud: auth error. Local: {str(local_err)}")
            
            if is_auth_error:
                raise Exception(f"Authentication Failed for {model}. Please verify your API key.")
            
            # Special handling for missing Ollama models
            if "not found" in err_msg and "ollama" in err_msg:
                model_name = model.replace("ollama/", "")
                raise Exception(f"Local model '{model_name}' not found. Please run: ollama pull {model_name}")
                
            raise e

router = LiteRouter()

