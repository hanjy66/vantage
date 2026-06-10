"""智谱 embedding-3 封装（同步、单一入口）。

设计：无 ZHIPUAI_API_KEY 或调用失败 → 返回 None，调用方据此回退（如 2-gram 召回）。
同步实现（urllib），供 kg_store 的同步函数直接调用；kg_store 本身在 asyncio.to_thread 内执行，
不阻塞事件循环。
"""

import json
import os
import urllib.request

ZHIPU_EMBEDDING_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
EMBEDDING_MODEL = "embedding-3"  # 维度 2048
_MAX_INPUT_CHARS = 3000


def embed(text: str, timeout: int = 30) -> list[float] | None:
    """对文本求 embedding；无 key / 空文本 / 任何异常 → None（调用方回退）。"""
    key = os.getenv("ZHIPUAI_API_KEY")
    if not key or not text:
        return None
    body = json.dumps(
        {"model": EMBEDDING_MODEL, "input": text[:_MAX_INPUT_CHARS]}
    ).encode("utf-8")
    req = urllib.request.Request(
        ZHIPU_EMBEDDING_URL,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        return resp["data"][0]["embedding"]
    except Exception:  # noqa: BLE001 — embedding 失败不应中断研究
        return None
