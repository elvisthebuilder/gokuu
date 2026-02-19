import os
from dotenv import load_dotenv
from typing import Optional, Dict

class ConfigManager:
    def __init__(self, env_path=None):
        if env_path:
            self.env_path = env_path
        else:
            # Default to .env in the package root (parent of server/)
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.env_path = os.path.join(base_dir, ".env")

    def set_key(self, key: str, value: str):
        """Update or add a key in the .env file."""
        lines = []
        if os.path.exists(self.env_path):
            with open(self.env_path, "r") as f:
                lines = f.readlines()
        
        new_lines = []
        updated = False
        for line in lines:
            if line.startswith(f"{key}="):
                new_lines.append(f"{key}={value}\n")
                updated = True
            else:
                new_lines.append(line)
        
        if not updated:
            new_lines.append(f"{key}={value}\n")
            
        with open(self.env_path, "w") as f:
            f.writelines(new_lines)
            
        # Refresh environment
        os.environ[key] = value
        load_dotenv(self.env_path, override=True)

    def get_key(self, key: str, default: str = "") -> str:
        """Read a single key from environment."""
        load_dotenv(self.env_path, override=True)
        return os.getenv(key, default)

    def delete_key(self, key: str):
        """Remove a key from .env file and environment."""
        if not os.path.exists(self.env_path):
            return
        with open(self.env_path, "r") as f:
            lines = f.readlines()
        with open(self.env_path, "w") as f:
            for line in lines:
                if not line.startswith(f"{key}="):
                    f.write(line)
        os.environ.pop(key, None)

    def get_all_keys(self) -> Dict[str, str]:
        """Return all keys from .env with values masked."""
        load_dotenv(self.env_path, override=True)
        result = {}
        if not os.path.exists(self.env_path):
            return result
        with open(self.env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    result[key.strip()] = value.strip()
        return result

    def mask_value(self, value: str) -> str:
        """Mask a sensitive value for display."""
        if not value or len(value) < 8:
            return "****"
        return value[:4] + "•" * (len(value) - 8) + value[-4:]

    def get_config(self):
        """Returns current configuration summary."""
        load_dotenv(self.env_path, override=True)
        return {
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
            "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", ""),
            "GITHUB_TOKEN": os.getenv("GITHUB_TOKEN", ""),
            "HF_TOKEN": os.getenv("HF_TOKEN", ""),
            "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            "GOKU_MODEL": os.getenv("GOKU_MODEL", "default")
        }

    def reset_all(self):
        """Clear all keys from .env."""
        if os.path.exists(self.env_path):
            with open(self.env_path, "w") as f:
                f.write("# Goku Configuration\n")

config_manager = ConfigManager()
