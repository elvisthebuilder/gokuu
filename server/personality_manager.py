import os
import json
import logging
from typing import Dict, Optional, List

logger = logging.getLogger("PersonalityManager")

class PersonalityManager:
    """Manages custom personas mapped to channels or session IDs."""
    
    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir:
            self.storage_dir = storage_dir
        else:
            # Use a global persistent directory instead of the source tree
            # This ensures personas survive git pulls and application updates
            self.storage_dir = os.path.expanduser("~/.goku/personalities")
            
        self.mapping_file = os.path.join(self.storage_dir, "mapping.json")
        os.makedirs(self.storage_dir, exist_ok=True)
        
        # Migration from legacy location if it exists
        self._migrate_legacy_data()
        self._ensure_mapping_file()

    def _migrate_legacy_data(self):
        """Move data from server/personalities (legacy) to ~/.goku/personalities."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        legacy_dir = os.path.join(base_dir, "server", "personalities")
        
        if os.path.exists(legacy_dir) and legacy_dir != self.storage_dir:
            import shutil
            try:
                for item in os.listdir(legacy_dir):
                    s = os.path.join(legacy_dir, item)
                    d = os.path.join(self.storage_dir, item)
                    if os.path.isfile(s) and not os.path.exists(d):
                        shutil.copy2(s, d)
                logger.info(f"Migrated legacy personalities from {legacy_dir}")
            except Exception as e:
                logger.error(f"Migration error: {e}")
        
    def _ensure_mapping_file(self):
        if not os.path.exists(self.mapping_file):
            with open(self.mapping_file, "w") as f:
                json.dump({}, f)
                
    def _load_mappings(self) -> Dict[str, str]:
        try:
            with open(self.mapping_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load personality mappings: {e}")
            return {}
            
    def _save_mappings(self, mappings: Dict[str, str]):
        try:
            with open(self.mapping_file, "w") as f:
                json.dump(mappings, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save personality mappings: {e}")

    def list_personalities(self) -> List[str]:
        """Return a list of available personality names (without .md)."""
        if not os.path.exists(self.storage_dir):
            return []
        files = [f for f in os.listdir(self.storage_dir) if f.endswith(".md")]
        return [f.replace(".md", "") for f in files]

    def get_personality_text(self, name: str) -> Optional[str]:
        """Read the content of a personality markdown file."""
        path = os.path.join(self.storage_dir, f"{name}.md")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Error reading personality '{name}': {e}")
            return None
            
    def save_personality(self, name: str, content: str) -> bool:
        """Save a new or updated personality to disk."""
        path = os.path.join(self.storage_dir, f"{name}.md")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content.strip())
            return True
        except Exception as e:
            logger.error(f"Error saving personality '{name}': {e}")
            return False

    def delete_personality(self, name: str) -> bool:
        """Delete a personality file and remove any mappings to it."""
        path = os.path.join(self.storage_dir, f"{name}.md")
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                logger.error(f"Error deleting personality '{name}': {e}")
                return False
                
        # Clean up mappings
        mappings = self._load_mappings()
        to_delete = [k for k, v in mappings.items() if v == name]
        if to_delete:
            for k in to_delete:
                mappings.pop(k, None)
            self._save_mappings(mappings)
            
        return True

    def assign_personality(self, target: str, name: str) -> bool:
        """Assign a personality to a specific source (e.g., 'whatsapp') or session (e.g., 'whatsapp:123')."""
        # Ensure the personality exists
        if name not in self.list_personalities():
            logger.error(f"Cannot assign unknown personality: {name}")
            return False
            
        mappings = self._load_mappings()
        mappings[target] = name
        self._save_mappings(mappings)
        return True

    def get_assigned_personality_for(self, source: str, session_id: str) -> Optional[str]:
        """Resolve the personality text based on priority (session_id > source)."""
        mappings = self._load_mappings()
        
        # 1. Try highly specific mapping first (e.g., 'whatsapp:123456789')
        specific_key = f"{source}:{session_id}"
        if specific_key in mappings:
            return self.get_personality_text(mappings[specific_key])
            
        # 2. Try generic source mapping (e.g., 'whatsapp')
        if source in mappings:
            return self.get_personality_text(mappings[source])
            
        # 3. Try global default fallback
        if "default" in mappings:
            return self.get_personality_text(mappings["default"])
            
        return None
        
    def get_all_mappings(self) -> Dict[str, str]:
        """Return the current mapping dictionary."""
        return self._load_mappings()

personality_manager = PersonalityManager()
