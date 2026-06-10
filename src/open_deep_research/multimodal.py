"""plan 009 Phase A: 多模态输入处理 — PDF 文本提取 + 图片 vision 分析。

架构原则（context firewall）：
  所有附件在此模块转成纯文本，下游节点（DeepSeek writer / Gemini critic）完全无感知。
  vision 复用已有 Gemini Flash，零新增模型 key。
"""

import asyncio
import base64
from pathlib import Path

import fitz  # pymupdf

from langchain_core.messages import HumanMessage

# 单次 vision 调用的硬超时（秒）：防止 vision 端点卡死拖垮整个 /jd-gap / /stream 请求
VISION_TIMEOUT_S = 75

# ─── purpose 差异化 vision 提示词 ────────────────────────────────────────────

PURPOSE_PROMPTS: dict[str, str] = {
    "jd": (
        "你是一个职位描述分析专家。请提取这份 JD 中的所有关键信息：\n"
        "1. 岗位职责（逐条列出）\n"
        "2. 任职要求（学历/经验/技能）\n"
        "3. 技术关键词和技能栈\n"
        "4. 业务背景与团队信息\n"
        "保留所有具体要求和数字指标，不要概括省略。"
    ),
    "competitor_ui": (
        "你是一个产品分析专家。请分析这个产品界面截图：\n"
        "1. 核心功能模块与页面布局\n"
        "2. UI 设计风格与主要交互模式\n"
        "3. 信息架构与用户路径\n"
        "4. 与主流竞品的差异化特征\n"
        "5. 可观察到的产品迭代方向或设计决策\n"
        "尽量具体，描述你在截图中实际看到的内容。"
    ),
    "reference": (
        "请完整提取这张图片/截图中的所有关键信息：\n"
        "- 文字内容（逐段）\n"
        "- 数据表格（保持行列结构）\n"
        "- 图表中的数据点和趋势\n"
        "- 关键结论和标注\n"
        "保持原有结构，不要遗漏任何具体数字或专有名词。"
    ),
    "auto": (
        "请提取这张图片/截图中的所有关键信息，"
        "包括文字、数据、图表和关键结论，以结构化方式输出。"
    ),
}


# ─── PDF 处理 ─────────────────────────────────────────────────────────────────

def extract_pdf_text(path: str) -> tuple[str, bool]:
    """提取 PDF 文本层。返回 (text, has_text)。

    has_text=False 表示扫描件（无文本层），需走 vision fallback。
    """
    doc = fitz.open(path)
    pages: list[str] = []
    for page in doc:
        t = page.get_text("text").strip()
        if t:
            pages.append(t)
    doc.close()
    full = "\n\n".join(pages)
    return full, len(full.strip()) > 50


def render_pdf_to_images(path: str, max_pages: int = 3) -> list[bytes]:
    """将 PDF 每页渲染成 PNG bytes（供扫描件 vision fallback）。"""
    doc = fitz.open(path)
    imgs: list[bytes] = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        pix = page.get_pixmap(dpi=150)
        imgs.append(pix.tobytes("png"))
    doc.close()
    return imgs


# ─── 图片工具 ─────────────────────────────────────────────────────────────────

def read_image_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def image_ext(path: str) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    return {"jpg": "jpeg", "jpeg": "jpeg", "png": "png",
            "gif": "gif", "webp": "webp"}.get(suffix, "png")


# ─── Vision 分析 ──────────────────────────────────────────────────────────────

async def analyze_image_bytes(
    img_bytes: bytes,
    ext: str,
    purpose: str,
    configurable_model,
    model_config: dict,
) -> str:
    """用 vision 模型分析图片 bytes，返回提取的文字内容。"""
    prompt = PURPOSE_PROMPTS.get(purpose, PURPOSE_PROMPTS["auto"])
    b64 = to_base64(img_bytes)
    msg = HumanMessage(content=[
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{b64}"}},
    ])
    # 硬超时：vision 端点偶发卡死时不能让整个请求无限挂起（前端会 "Failed to fetch"）。
    # 超时抛 TimeoutError → 上层 process_attachment 捕获 → 返回占位串，请求正常 200 收尾。
    resp = await asyncio.wait_for(
        configurable_model.with_config(model_config).ainvoke([msg]),
        timeout=VISION_TIMEOUT_S,
    )
    return resp.content


# ─── 单附件处理入口 ───────────────────────────────────────────────────────────

async def process_attachment(
    attachment: dict,
    configurable_model,
    model_config: dict,
) -> str:
    """处理单个附件，返回提取的纯文本。

    attachment: {"type": "pdf"|"image", "path": str, "purpose": str}
    失败时返回占位字符串，不抛出。
    """
    atype = attachment.get("type", "auto")
    path = attachment.get("path", "")
    purpose = attachment.get("purpose", "auto")

    if not path:
        return ""

    try:
        if atype == "pdf":
            text, has_text = await asyncio.to_thread(extract_pdf_text, path)
            if has_text:
                return f"[PDF 文本内容]\n{text}"
            # 扫描件 fallback
            imgs = await asyncio.to_thread(render_pdf_to_images, path)
            if not imgs:
                return "[附件解析失败: PDF 无文本层且无法渲染页面]"
            parts = []
            for i, img_bytes in enumerate(imgs):
                page_text = await analyze_image_bytes(
                    img_bytes, "png", purpose, configurable_model, model_config
                )
                parts.append(f"[第 {i + 1} 页]\n{page_text}")
            return "[扫描件 PDF — vision 提取]\n\n" + "\n\n".join(parts)

        else:  # image
            img_bytes = await asyncio.to_thread(read_image_bytes, path)
            ext = image_ext(path)
            text = await analyze_image_bytes(
                img_bytes, ext, purpose, configurable_model, model_config
            )
            return f"[图片内容 — {purpose}]\n{text}"

    except Exception as e:
        return f"[附件解析失败: {e}]"
