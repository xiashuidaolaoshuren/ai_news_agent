"""Tests for readable Hugging Face model-card excerpts."""

from __future__ import annotations

from ai_news_agent.huggingface_model_card import normalize_model_card_snippet

_SOURCE = "https://huggingface.co/moonshotai/Kimi-K3.1-Pro"


def test_normalize_model_card_keeps_introduction_and_specs_without_layout_html() -> None:
    raw = """\
<div align="center">
<picture>
<img src="assets/kimi-logo.png" alt="Kimi logo">
</picture>
</div>

1. Model Introduction
Kimi K3.1 Pro is an open-weight, natively multimodal agentic model.

2. Model Summary
<div align="center">
<table>
<tbody>
<tr>
<td align="center"><strong>Architecture</strong></td>
<td align="center">Mixture-of-Experts (MoE)</td>
</tr>
<tr>
<td align="center"><strong>Total Parameters</strong></td>
<td align="center">2.8T</td>
</tr>
</tbody>
</table>
</div>
"""
    out = normalize_model_card_snippet(raw, source_url=_SOURCE)

    assert "Kimi K3.1 Pro is an open-weight" in out
    assert "**Architecture**" in out
    assert "Mixture-of-Experts (MoE)" in out
    assert "**Total Parameters**" in out
    assert "2.8T" in out
    assert "|" in out
    for tag in ("<div", "<table", "<td", "<picture", "<strong"):
        assert tag not in out


def test_normalize_model_card_preserves_plain_markdown() -> None:
    raw = """\
# Title

Overview with **bold** and *italic* and `code`.

- first
- second

| A | B |
| --- | --- |
| 1 | 2 |

[docs](https://example.com/docs)
"""
    out = normalize_model_card_snippet(raw, source_url=_SOURCE)

    assert "# Title" in out
    assert "**bold**" in out
    assert "*italic*" in out
    assert "`code`" in out
    assert "- first" in out
    assert "| A | B |" in out
    assert "[docs](https://example.com/docs)" in out


def test_normalize_model_card_strips_yaml_frontmatter() -> None:
    raw = "---\nlibrary_name: transformers\nlicense: other\n---\n\n# Title\n\nBody text."
    out = normalize_model_card_snippet(raw, source_url=_SOURCE)

    assert "# Title" in out
    assert "Body text." in out
    assert "library_name:" not in out
    assert "license:" not in out


def test_normalize_model_card_strips_crlf_frontmatter_and_metadata_only_cards() -> None:
    crlf = "---\r\nlibrary_name: transformers\r\n---\r\n\r\nBody text."
    out = normalize_model_card_snippet(crlf, source_url=_SOURCE)
    assert out == "Body text."
    assert "library_name:" not in out

    metadata_only = "---\nlibrary_name: transformers\nlicense: other\n---\n"
    assert normalize_model_card_snippet(metadata_only, source_url=_SOURCE) == ""


def test_normalize_model_card_keeps_html_examples_inside_code_literal() -> None:
    raw = """\
Before

```html
<div align="center"><strong>Keep</strong></div>
```

Inline `<td>cell</td>` stays literal.
"""
    out = normalize_model_card_snippet(raw, source_url=_SOURCE)

    assert '<div align="center"><strong>Keep</strong></div>' in out
    assert "`<td>cell</td>`" in out
    assert "**Keep**" not in out


def test_normalize_model_card_decodes_html_entities() -> None:
    out = normalize_model_card_snippet("<p>AT&amp;T &lt;model&gt;</p>", source_url=_SOURCE)

    assert "AT&T <model>" in out
    assert "&amp;" not in out
    assert "<p" not in out


def test_normalize_model_card_drops_an_unfinished_trailing_tag() -> None:
    raw = 'Model overview.\n<td align="center" style="vertical'
    out = normalize_model_card_snippet(raw, source_url=_SOURCE)

    assert "Model overview." in out
    assert "<td" not in out
    assert "vertical" not in out


def test_normalize_model_card_drops_decoration_and_keeps_safe_links() -> None:
    raw = """\
<a href="https://img.shields.io/badge/Chat-Kimi"><img alt="Chat" src="badge.svg"></a>
<a href="https://www.kimi.ai"><img alt="Homepage" src="logo.svg">Homepage</a>
<a href="docs/guide.md">API Quickstart</a>
<a href="javascript:alert(1)">unsafe</a>
<script>alert(1)</script>
<style>.x{background:url(track.png)}</style>
<p>Useful model description.</p>
"""
    out = normalize_model_card_snippet(raw, source_url=_SOURCE)

    assert "Useful model description." in out
    assert "img.shields.io" not in out
    assert "badge.svg" not in out
    assert "logo.svg" not in out
    assert "<img" not in out
    assert "<script" not in out
    assert "alert(1)" not in out
    assert "javascript:" not in out
    assert "track.png" not in out
    assert "[Homepage](https://www.kimi.ai)" in out
    assert (
        "[API Quickstart](https://huggingface.co/moonshotai/Kimi-K3.1-Pro/blob/main/docs/guide.md)"
        in out
    )
    assert "unsafe" in out


def test_normalize_model_card_bounds_long_content_at_complete_blocks() -> None:
    paragraph = " ".join(f"word{index}" for index in range(80))
    raw = "\n\n".join(paragraph for _ in range(8))
    out = normalize_model_card_snippet(raw, source_url=_SOURCE, max_chars=500)

    assert len(out) <= 500
    assert "[Excerpt shortened. Read the full model card.](" in out
    assert out.endswith(")")
    assert not out.split("Excerpt shortened")[0].rstrip().endswith("word")
    assert out.count("word0") < 8


def test_normalize_model_card_bounds_without_breaking_markdown_structures() -> None:
    rows = "\n".join(f"| specification {index} | value {index} |" for index in range(30))
    table = f"| Name | Value |\n| --- | --- |\n{rows}"
    code = "```python\n" + ("print('line')\n" * 40) + "```"
    link = "[documentation](https://example.com/very/long/documentation/path)"
    raw = "\n\n".join((table, code, link, "final paragraph " * 40))
    out = normalize_model_card_snippet(raw, source_url=_SOURCE, max_chars=700)

    assert len(out) <= 700
    assert out.count("```") % 2 == 0
    assert "[documentation](https://example.com/very/long/documentation/path)" in out or (
        "documentation" not in out.split("Excerpt shortened")[0]
    )
    body = out.split("Excerpt shortened")[0]
    for line in body.splitlines():
        if line.startswith("|"):
            assert line.endswith("|")


def test_normalize_model_card_is_idempotent_after_bounding() -> None:
    raw = "<p>" + ("Useful model information. " * 300) + "</p>"
    once = normalize_model_card_snippet(raw, source_url=_SOURCE, max_chars=600)
    twice = normalize_model_card_snippet(once, source_url=_SOURCE, max_chars=600)

    assert twice == once
