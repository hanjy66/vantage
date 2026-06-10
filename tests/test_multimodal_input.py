"""plan 009 Phase A unit tests — 多模态输入处理。"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))


# ─── multimodal.py 工具函数测试（无 LLM，无文件系统） ─────────────────────────

def test_purpose_prompts_all_keys_exist():
    from open_deep_research.multimodal import PURPOSE_PROMPTS
    for key in ("jd", "competitor_ui", "reference", "auto"):
        assert key in PURPOSE_PROMPTS
        assert len(PURPOSE_PROMPTS[key]) > 20


def test_image_ext_mapping():
    from open_deep_research.multimodal import image_ext
    assert image_ext("photo.jpg") == "jpeg"
    assert image_ext("screenshot.PNG") == "png"
    assert image_ext("anim.gif") == "gif"
    assert image_ext("unknown.bmp") == "png"  # fallback


def test_to_base64_roundtrip():
    from open_deep_research.multimodal import to_base64
    import base64
    data = b"hello world"
    assert base64.b64decode(to_base64(data)) == data


# ─── ingest_attachments 节点测试（mock LLM） ─────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_passthrough_no_attachments(monkeypatch):
    """无附件时直接 passthrough 到 clarify_with_user，不修改 state。"""
    from open_deep_research import deep_researcher

    state = {"attachments": [], "messages": [], "ingested_context": ""}
    config = {"configurable": {}}

    result = await deep_researcher.ingest_attachments(state, config)
    assert result.goto == "clarify_with_user"
    assert not result.update  # 无 state 更新


@pytest.mark.asyncio
async def test_ingest_passthrough_disabled(monkeypatch):
    """enable_multimodal_input=False 时 passthrough，即使有附件。"""
    from open_deep_research import deep_researcher

    state = {
        "attachments": [{"type": "image", "path": "x.png", "purpose": "auto"}],
        "messages": [],
    }
    config = {"configurable": {"enable_multimodal_input": False}}

    result = await deep_researcher.ingest_attachments(state, config)
    assert result.goto == "clarify_with_user"


@pytest.mark.asyncio
async def test_ingest_image_injected_as_message(monkeypatch):
    """图片附件处理后，ingested_context 被注入为 HumanMessage。"""
    from open_deep_research import deep_researcher

    # mock process_attachment 返回固定内容
    async def fake_process(attachment, model, cfg):
        return f"[图片内容 — {attachment['purpose']}]\n产品主界面有搜索栏和推荐流。"

    monkeypatch.setattr(deep_researcher, "process_attachment", fake_process)

    state = {
        "attachments": [{"type": "image", "path": "ui.png", "purpose": "competitor_ui"}],
        "messages": [],
        "ingested_context": "",
    }
    config = {"configurable": {}}

    result = await deep_researcher.ingest_attachments(state, config)
    assert result.goto == "clarify_with_user"
    assert "ingested_context" in result.update
    assert "产品主界面" in result.update["ingested_context"]
    # messages 应包含一条 HumanMessage
    msgs = result.update.get("messages", [])
    assert len(msgs) == 1
    assert "用户上传资料摘要" in msgs[0].content


@pytest.mark.asyncio
async def test_ingest_truncates_excess_images(monkeypatch):
    """超过 max_attachment_images 的图片被截断。"""
    from open_deep_research import deep_researcher

    calls: list[dict] = []

    async def fake_process(attachment, model, cfg):
        calls.append(attachment)
        return f"[图片 {attachment['path']}]"

    monkeypatch.setattr(deep_researcher, "process_attachment", fake_process)

    # 3 PDFs + 8 images，max_attachment_images=5
    attachments = [{"type": "pdf", "path": f"doc{i}.pdf", "purpose": "jd"} for i in range(3)]
    attachments += [{"type": "image", "path": f"img{i}.png", "purpose": "auto"} for i in range(8)]

    state = {"attachments": attachments, "messages": []}
    config = {"configurable": {"max_attachment_images": 5}}

    await deep_researcher.ingest_attachments(state, config)
    # 3 PDFs 全保留 + 5 images（截断 3 张）= 8
    assert len(calls) == 8
    pdf_calls = [c for c in calls if c["type"] == "pdf"]
    img_calls = [c for c in calls if c["type"] != "pdf"]
    assert len(pdf_calls) == 3
    assert len(img_calls) == 5


@pytest.mark.asyncio
async def test_ingest_failed_attachments_skipped(monkeypatch):
    """解析失败的附件被过滤，不注入进 messages。"""
    from open_deep_research import deep_researcher

    async def fake_process(attachment, model, cfg):
        return "[附件解析失败: timeout]"

    monkeypatch.setattr(deep_researcher, "process_attachment", fake_process)

    state = {
        "attachments": [{"type": "image", "path": "bad.png", "purpose": "auto"}],
        "messages": [],
    }
    config = {"configurable": {}}

    result = await deep_researcher.ingest_attachments(state, config)
    assert result.goto == "clarify_with_user"
    # 没有有效内容，不追加 message
    assert result.update.get("ingested_context", "") == ""
    assert not result.update.get("messages")
