"""plan 017 — 面经链接旁路抽取（牛客/知乎全保留、去重、排除其它域名）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from open_deep_research.deep_researcher import (
    _INTERVIEW_LINK_HOSTS,
    _build_sources_section,
    _extract_interview_links,
    _extract_source_allowlist,
)


def test_extracts_only_interview_hosts_and_dedupes():
    raw = (
        "--- SOURCE 1: 字节AI面经 ---\nURL: https://www.nowcoder.com/feed/main/detail/abc\n"
        "--- SOURCE 2: 普通新闻 ---\nURL: https://news.qq.com/a/123\n"
        "--- SOURCE 3: Kimi面经 知乎 ---\nURL: https://zhuanlan.zhihu.com/p/999\n"
        "--- SOURCE 4: 重复 ---\nURL: https://www.nowcoder.com/feed/main/detail/abc\n"
    )
    out = _extract_interview_links(raw)
    assert "nowcoder.com/feed/main/detail/abc" in out
    assert "zhuanlan.zhihu.com/p/999" in out
    assert "news.qq.com" not in out  # 非面经域名排除
    assert out.count("nowcoder.com/feed/main/detail/abc") == 1  # 去重


def test_caps_links_at_30():
    raw = "\n".join(
        f"--- SOURCE {i}: 面经{i} ---\nURL: https://www.nowcoder.com/p/{i}" for i in range(60)
    )
    out = _extract_interview_links(raw)
    # 上限 30：60 条只保留前 30，避免链接淹没报告
    assert out.count("nowcoder.com/p/") == 30


def test_empty_returns_hint_not_fabrication():
    out = _extract_interview_links("--- SOURCE 1: 新闻 ---\nURL: https://example.com/x")
    assert "未检索到面经链接" in out


def test_interview_links_are_clickable_markdown():
    """面经链接以 markdown 可点击格式输出（程序化追加进章节六）。"""
    raw = "--- SOURCE 1: 字节AI面经 ---\nURL: https://www.nowcoder.com/feed/main/detail/x"
    out = _extract_interview_links(raw)
    assert "[字节AI面经](https://www.nowcoder.com/feed/main/detail/x)" in out


def test_build_sources_section_numbered_clickable_and_aligned():
    """程序化「## 来源」：可点击、编号与白名单同序（正文 [n] 对齐），面试模式排除面经域名。"""
    raw = (
        "--- SOURCE 1: 牛客面经 ---\nURL: https://www.nowcoder.com/x\n"
        "--- SOURCE 2: 36氪 ---\nURL: https://36kr.com/p/1\n"
        "--- SOURCE 3: 搜狐 ---\nURL: https://sohu.com/a/2\n"
    )
    allow = _extract_source_allowlist(raw, exclude_hosts=_INTERVIEW_LINK_HOSTS)
    section = _build_sources_section(raw, exclude_hosts=_INTERVIEW_LINK_HOSTS)
    assert section.startswith("## 来源")
    # 可点击且排除面经域名
    assert "[36氪](https://36kr.com/p/1)" in section
    assert "nowcoder.com" not in section
    # 编号与白名单一致：白名单 [1] 是 36氪，来源 [1] 也必须是 36氪
    assert "[1] 36氪" in allow and "[1] [36氪]" in section


def test_build_sources_section_empty_when_no_urls():
    assert _build_sources_section("没有任何链接的纯文本") == ""


def test_source_allowlist_excludes_interview_hosts():
    """面试模式下，面经域名要从数据来源白名单排除（它们走 interview_links 单独通道）。

    回归：80+ 面经链接会挤占来源编号，把真正的数据来源挤出前 50，导致正文 [n] 引用与
    末尾「来源」列表对不上。排除后白名单只剩数据来源，编号才对得齐。
    """
    raw = (
        "--- SOURCE 1: 字节面经 牛客 ---\nURL: https://www.nowcoder.com/feed/main/detail/aaa\n"
        "--- SOURCE 2: 36氪数据 ---\nURL: https://36kr.com/p/123\n"
        "--- SOURCE 3: Kimi面经 知乎 ---\nURL: https://zhuanlan.zhihu.com/p/999\n"
        "--- SOURCE 4: 搜狐财经 ---\nURL: https://business.sohu.com/a/456\n"
    )
    # 面试模式：排除面经域名
    out_interview = _extract_source_allowlist(raw, exclude_hosts=_INTERVIEW_LINK_HOSTS)
    assert "36kr.com/p/123" in out_interview
    assert "sohu.com/a/456" in out_interview
    assert "nowcoder.com" not in out_interview
    assert "zhihu.com" not in out_interview
    # 通用模式（不排除）：zhihu 等仍是合法数据来源，全保留
    out_general = _extract_source_allowlist(raw)
    assert "nowcoder.com" in out_general
    assert "zhihu.com" in out_general
