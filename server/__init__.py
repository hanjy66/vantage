"""ADRP Research Control Room — 薄后端适配层（plan 010 Step 2）。

只新增 FastAPI + SSE，把 LangGraph 的事件流转给前端。
核心 graph（src/open_deep_research）零改动，仅被调用。
"""
