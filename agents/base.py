from abc import ABC, abstractmethod
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class BaseSkill(ABC):
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.tools = []

    @abstractmethod
    async def execute(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a specific tool within this skill."""
        pass

    def get_schema(self) -> List[Dict[str, Any]]:
        """Return the JSON schema for the tools in this skill."""
        return self.tools

class SkillRegistry:
    def __init__(self):
        self.skills: Dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill):
        self.skills[skill.name] = skill
        logger.info(f"Registered skill: {skill.name}")

    def get_skill(self, name: str) -> BaseSkill:
        return self.skills.get(name)

    def get_all_tools(self) -> List[Dict[str, Any]]:
        all_tools = []
        for skill in self.skills.values():
            all_tools.extend(skill.get_schema())
        return all_tools

registry = SkillRegistry()
