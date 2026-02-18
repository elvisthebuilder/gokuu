import os
import yaml
import re
from typing import List, Dict, Any

class OpenClawIngestor:
    def __init__(self, openclaw_root: str):
        self.openclaw_root = openclaw_root
        self.skills_dir = os.path.join(openclaw_root, "skills")

    def list_skills(self) -> List[str]:
        if not os.path.exists(self.skills_dir):
            return []
        return [d for d in os.listdir(self.skills_dir) if os.path.isdir(os.path.join(self.skills_dir, d))]

    def parse_skill(self, skill_name: str) -> Dict[str, Any]:
        skill_path = os.path.join(self.skills_dir, skill_name, "SKILL.md")
        if not os.path.exists(skill_path):
            return {}

        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract frontmatter
        frontmatter = {}
        fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            try:
                frontmatter = yaml.safe_load(fm_match.group(1))
            except yaml.YAMLError:
                pass
            body = content[fm_match.end():].strip()
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
        for skill_name in self.list_skills():
            skill_info = self.parse_skill(skill_name)
            if not skill_info or not skill_info.get("description"):
                continue

            tool = {
                "type": "function",
                "function": {
                    "name": f"openclaw_{skill_info['name']}",
                    "description": skill_info["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_intent": {
                                "type": "string",
                                "description": f"The specific request for the {skill_info['name']} skill."
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
    for d in defs[:5]:
        print(f"Tool: {d['name']} - {d['description']}")
