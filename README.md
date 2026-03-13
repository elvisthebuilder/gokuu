# Goku CLI Agent v2.5 🐉

Goku is an intelligent terminal agent designed for high-performance development and workflow orchestration. It leverages MCP tools, long-term vector memory, and multi-agent "Departmental" pipelines to solve complex tasks directly from your terminal, WhatsApp, or Telegram.

## 🚀 What's New in v2.5
- **Departmental Evolution Flow (DEF)**: A multi-agent pipeline system (Health, Audit, Implement, Research) that manages complex, multi-step engineering tasks autonomously.
- **Premium Messaging Design**: High-fidelity ASCII tables and bulletproof markdown formatting for WhatsApp and Telegram.
- **Diagnostic Logging**: Clean CLI experience with persistent file-based logging (`goku logs`).
- **Resilient Tool Logic**: Advanced JSON salvage mechanism to recover from malformed or concatenated LLM tool calls.

## 🏗️ Architecture

```mermaid
graph TD
    CLI[Goku CLI] --> Agent[Main Orchestrator]
    Agent --> DEF[Departmental Pipelines]
    Agent --> Memory[Vector Memory]
    Agent --> Channel[WhatsApp/Telegram]
    
    DEF --> Health[Health Check]
    DEF --> Implement[Implementation]
    DEF --> Audit[Code Audit]
    
    Agent --> MCP[MCP Servers]
    MCP --> Bash[Native Bash]
    MCP --> Files[File System]
```

## 🛠️ Setup & Installation

### One-Liner Installation
Run the following command to install Goku globally on your system:

```bash
curl -sSL https://raw.githubusercontent.com/elvisthebuilder/gokuu/main/install.sh | bash
```

> [!NOTE]
> Make sure `~/.local/bin` is in your `PATH`. If not, add `export PATH="$PATH:$HOME/.local/bin"` to your `.bashrc` or `.zshrc`.

## ⌨️ How to Use

### Global Commands
- `goku cli`   - Start the interactive terminal agent
- `goku web`   - Launch the high-fidelity web dashboard
- `goku logs`  - View diagnostic logs (WhatsApp/Telegram activity)
- `goku update` - Pull the latest version and re-install

## 🛡️ Security & Safety
Goku is designed with a **Safety First** approach:
- **Thought Transparency**: See exactly why the agent is taking an action in real-time.
- **Local Control**: Runs natively in your environment without external containers.
- **Human-in-the-Loop**: Interactive confirmation for sensitive tool executions.

## 🤝 Contributing
We welcome contributions! Please follow the standard fork and pull request workflow.
