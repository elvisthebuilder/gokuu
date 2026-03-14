# 🗺️ Goku AI Roadmap: The Future of Intelligence

This document outlines the long-term vision for Goku's evolution, focusing on making memory, reasoning, and multimodal interactions feel native and superhuman.

## 🧠 Phase 1: Advanced Information Management

### 1.1 Hybrid Search (Semantic + Keyword)
- **Goal**: Allow Goku to find specific IDs, code symbols, and exact technical terms that semantic (vector) search often misses.
- **Tech**: Implement BM25 keyword search alongside Qdrant vector search and use Reciprocal Rank Fusion (RRF) to merge results.

### 1.2 Memory Consolidation (The "Brain Sweep")
- **Goal**: Prevent memory noise by summarizing short-term logs into long-term facts.
- **Tech**: A background "Curator Agent" that periodically analyzes raw conversation vectors and distills them into high-level persona insights (e.g., *"User prefers Node.js over Python for backend tasks"*).

### 1.3 Neural Reranking
- **Goal**: Increase retrieval precision by filtering out "false positive" memory hits.
- **Tech**: Fetch top 20 candidates from Qdrant, then use a lightweight cross-encoder (or a fast Gemini-Flash call) to select the most relevant 5 snippets for the current context.

## 🎨 Phase 2: User Sovereignty & Control

### 2.1 "Edit My Brain" (Web Dashboard)
- **Goal**: Allow users to browse, correct, or delete what Goku "knows" about them.
- **Tech**: A dedicated UI in the dashboard that lists memories from Qdrant and maps them back to editable text entries.

### 2.2 Local-First Privacy (Optional)
- **Goal**: Support users who want 100% offline memory.
- **Tech**: Optional switch to local Ollama/Llama-CPP embeddings for the memory engine, bypassing the cloud for sensitive indexed data.

## 📸 Phase 3: Deep Multimodal Reasoning

### 3.1 Temporal Video Analysis
- **Goal**: Allow Goku to "watch" videos sent over WhatsApp/Telegram and remember events over time.
- **Tech**: Frame extraction and video embedding support via Gemini Multimodal.

### 3.2 Proactive Context Awarenes
- **Goal**: Goku initiates contact when a remembered deadline or event is approaching.
- **Tech**: Integration between `VectorMemory` and `APScheduler` (Task Poller).

---
*Goku is evolving. This roadmap is a living document.*
