<div align="center">

# VANTAGE Research

**A multi-agent RAG platform for deep research — going beyond retrieval Q&A to produce traceable, auditable, reusable research reports.**

[中文](README.md) · **English**

<sub>Planning / parallel retrieval / cross-model audit / deterministic visualization / cross-session knowledge graph · fully SSE-streamed</sub>

![Vantage cockpit overview](assets/screenshots/01-cockpit-overview.png)

</div>

> 🚧 A full English README is in progress. For now, the [中文 README](README.md) is the complete reference — the screenshots, architecture diagram, model-routing table, and quick-start commands there are language-agnostic.

---

## What it is

Vantage turns "deep research" into a **multi-agent pipeline**: clarify intent → write a research brief → a supervisor decomposes the work → multiple researcher sub-agents retrieve **in parallel** → results are synthesized → **a different-provider model audits and scores** the draft → it auto-**escalates and rewrites** when below bar → the format is adapted → **charts and architecture diagrams are rendered deterministically**.

What makes it more than "just search":

- **Can you trust the answer?** The writer (DeepSeek) and the auditor (Kimi) are **different providers** that don't vouch for each other; failing audits trigger an automatic rewrite with a stronger reasoning model.
- **Are sources fabricated?** Citations use a **whitelist + programmatic append**, keeping inline `[n]` markers aligned with the source list even if the body is truncated by model output limits.
- **Do charts break or go missing?** The model only produces **structured specs** (ChartSpec / ArchSpec); charts and Mermaid diagrams are **rendered by code**, eliminating flakiness.
- **Can past research be reused?** Every run lands in a **knowledge graph** (semantic recall); new topics are **deduplicated** against history before triggering fresh work.

Forked from [`langchain-ai/open_deep_research`](https://github.com/langchain-ai/open_deep_research), with mode injection, cross-model audit, deterministic artifacts, a knowledge graph, and a production-grade frontend cockpit layered on top.

## Quick start

See the [中文 README](README.md#快速开始) for full setup. In short: copy `.env.example` → `.env` and fill keys, then:

```powershell
uv sync
uv run uvicorn server.app:app --reload --port 8000   # backend
cd frontend; npm install; npm run dev                # frontend → http://localhost:3000
```

## License

[MIT](LICENSE). Baseline forked from [langchain-ai/open_deep_research](https://github.com/langchain-ai/open_deep_research).
