# Skill Template (Goku Evolution Protocol)

Follow this structure when creating new specialized skills for Goku.

## Frontmatter (YAML in SKILL.md)
```yaml
name: [Skill Name]
description: [One sentence describing what this agent is an expert in]
```

## Content Structure
1. **Purpose**: Define exactly what the agent should accomplish.
2. **Core Directives**: 3-5 non-negotiable rules for the agent's behavior.
3. **Tool Access**: Remind the agent it uses Goku's bash/MCP tools to act.
4. **Output Format**: How it should report back (summaries, diffs, etc.).

## Self-Improvement Protocol
Include this section in every new skill:
"Every time you complete a task, use the `learn_lesson` tool to record what worked and what didn't. This data will be used to evolve your instructions."
