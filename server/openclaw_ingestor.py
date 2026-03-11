import os
import re
from typing import List, Dict, Any

try:
    import yaml  # pyre-ignore[21]
except ImportError:
    yaml = None  # type: ignore[assignment]

class OpenClawIngestor:
    def __init__(self, openclaw_root: str):
        self.openclaw_root = openclaw_root
        self.agent_dir = os.path.join(openclaw_root, "agents")
        self.skill_dir = os.path.join(openclaw_root, "skills")

    def list_skills(self) -> List[Dict[str, str]]:
        skills = []
        for d in [self.agent_dir, self.skill_dir]:
            if os.path.exists(d):
                for skill_name in os.listdir(d):
                    if os.path.isdir(os.path.join(d, skill_name)):
                        skills.append({"name": skill_name, "path": os.path.join(d, skill_name)})
        return skills

    def parse_skill(self, skill_name: str, skill_path: str = None) -> Dict[str, Any]:
        if not skill_path:
            # Fallback for legacy calls
            for d in [self.agent_dir, self.skill_dir]:
                p = os.path.join(d, skill_name, "SKILL.md")
                if os.path.exists(p):
                    skill_path = os.path.dirname(p)
                    break
        
        if not skill_path:
            return {}

        file_path = os.path.join(skill_path, "SKILL.md")
        if not os.path.exists(file_path):
            return {}

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract frontmatter
        frontmatter = {}
        fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            try:
                if yaml is not None:
                    frontmatter = yaml.safe_load(fm_match.group(1))
            except Exception:
                pass
            end_pos: int = fm_match.end()
            body = content[end_pos:]  # pyre-ignore[6]
            body = body.strip()
        else:
            body = content.strip()

        return {
            "name": frontmatter.get("name", skill_name),
            "description": frontmatter.get("description", ""),
            "instructions": body,
            "metadata": frontmatter.get("metadata", {})
        }

    def generate_tool_definitions(self) -> List[Dict[str, Any]]:
        tools = []
        for skill_meta in self.list_skills():
            skill_info = self.parse_skill(skill_meta["name"], skill_meta["path"])
            if not skill_info or not skill_info.get("description"):
                continue

            # Check if it's an agent or a general skill based on its location
            is_agent = "agents" in skill_meta["path"]
            tool_name = f"openclaw_agent_{skill_info['name']}" if is_agent else f"openclaw_skill_{skill_info['name']}"
            
            tool = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": skill_info["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_intent": {
                                "type": "string",
                                "description": f"The specific request for the {skill_info['name']} {'agent' if is_agent else 'skill'}."
                            }
                        },
                        "required": ["user_intent"]
                    }
                },
                "instructions": skill_info["instructions"]
            }
            tools.append(tool)
        return tools

if __name__ == "__main__":
    # Test parity
    ingestor = OpenClawIngestor("/home/elvisthebuilder/Documents/Dev/goku/openclaw")
    defs = ingestor.generate_tool_definitions()
    print(f"Found {len(defs)} tools.")
    for i, d in enumerate(defs):
        if i >= 5:
            break
        print(f"Tool: {d['name']} - {d['description']}")
