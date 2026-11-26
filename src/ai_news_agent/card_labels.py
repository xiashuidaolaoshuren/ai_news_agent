"""English and Simplified Chinese labels for digest cards and caveats.

Only digest content and card chrome use these tables. Titles, quotations, model
names and other identifiers stay as collected.
"""

from __future__ import annotations

from ai_news_agent.models import SourceKind

__all__ = ["CardLang", "card_lang", "legacy_card_lang", "text"]

CardLang = str

_CAVEATS: dict[str, dict[str, str]] = {
    "en": {
        "hf_popularity": (
            "Hub trending reflects popularity, not model quality or fitness for your use case."
        ),
        "low_confidence": (
            "Source metadata is limited or low-confidence; summaries may omit unavailable details."
        ),
        "no_snippet": "No excerpt/snippet available; summary is metadata-only.",
        "unrecognized_follow_up": "Unrecognized follow_up_action={value}; defaulted to read.",
        "zhihu_discovery": (
            "Zhihu result is discovery-only; thin evidence may limit summary depth."
        ),
        "rank": "Rank {rank}",
        "family_heading": "Family card · {title}",
        "missing_evidence": "Hub stats and card snippet are not available for this saved item.",
        "col_trending": "Trending",
        "col_downloads": "30-day downloads",
        "col_likes": "Likes",
        "col_pipeline": "Pipeline",
        "hub_stats": "Hub stats",
        "not_saved": "Not saved",
        "also": "Also",
        "from_model_card": "From the model card",
        "reading_numbers": "Reading these numbers",
        "related": "Related",
        "source": "Source",
        "model_page": "model page for `{source_id}`",
        "saved_snippet": "Snippet is from the model card saved with this digest.",
        "live_snippet": (
            "Snippet is from a live Hub model card fetched after digest time; "
            "Trending, Downloads, and Likes remain digest-time values."
        ),
        "model_card_unavailable": (
            "Live Hub model card was unavailable; showing digest-time evidence only."
        ),
        "digest_item": "Digest item {rank}: {title}",
        "field_url": "URL",
        "field_summary": "Summary",
        "field_why": "Why it matters",
        "field_caveat": "Confidence caveat",
        "colon": ": ",
        "story_heading": "Item {rank} · {title}",
        "bulletin": "Bulletin #{number}",
        "summary_label": "Summary",
        "juya_why": "Key point",
        "detail": "Detail",
        "related_links": "Related links",
        "original": "Original",
        "bulletin_link": "Bulletin",
        "note": "Note",
        "lens_line": "Lens: {value}",
        "author_source_both": "Author/source: {author} ({source})",
        "author_source_one": "Author/source: {value}",
        "relevance_line": "Search relevance: {value}",
        "zhihu_why": "Why it matters",
        "excerpt_heading": "Source excerpt",
        "notes_heading": "Notes",
        "original_link": "Original link",
        "zhihu_original": "Zhihu original",
        "zhihu_thin_card": (
            "This Zhihu result is discovery-oriented; evidence is thin, so summary depth may be limited."
        ),
        "zhihu_freshness": (
            "Search relevance is official search relevance, not a popularity or freshness signal."
        ),
    },
    "zh-CN": {
        "hf_popularity": "Hub 热度反映的是受欢迎程度，不代表模型质量或是否适合你的使用场景。",
        "low_confidence": "来源元数据有限或置信度较低；摘要可能遗漏不可用的细节。",
        "no_snippet": "没有可用的原文摘录；摘要仅基于元数据。",
        "unrecognized_follow_up": "无法识别的 follow_up_action={value}；已默认为 read。",
        "zhihu_discovery": "知乎结果为发现导向；证据较薄，摘要深度可能有限。",
        "rank": "排名 {rank}",
        "family_heading": "家族卡片 · {title}",
        "missing_evidence": "此已保存条目没有 Hub 数据和模型卡片摘录。",
        "col_trending": "热度",
        "col_downloads": "30 天下载",
        "col_likes": "点赞",
        "col_pipeline": "任务类型",
        "hub_stats": "Hub 数据",
        "not_saved": "未保存",
        "also": "同系列",
        "from_model_card": "来自模型卡片",
        "reading_numbers": "如何理解这些数字",
        "related": "相关",
        "source": "来源",
        "model_page": "模型页面：`{source_id}`",
        "saved_snippet": "摘录来自随此摘要保存的模型卡片。",
        "live_snippet": "摘录来自摘要生成后实时获取的 Hub 模型卡片；热度、下载量和点赞数仍为摘要生成时的数值。",
        "model_card_unavailable": "无法获取实时 Hub 模型卡片；仅显示摘要生成时的证据。",
        "digest_item": "第 {rank} 条：{title}",
        "field_url": "链接",
        "field_summary": "摘要",
        "field_why": "为什么重要",
        "field_caveat": "注意",
        "colon": "：",
        "story_heading": "第 {rank} 条 · {title}",
        "bulletin": "简报 #{number}",
        "summary_label": "摘要",
        "juya_why": "要点",
        "detail": "详情",
        "related_links": "相关链接",
        "original": "原文",
        "bulletin_link": "简报",
        "note": "注意",
        "lens_line": "镜头：{value}",
        "author_source_both": "作者/来源：{author}（{source}）",
        "author_source_one": "作者/来源：{value}",
        "relevance_line": "搜索相关性：{value}",
        "zhihu_why": "为什么值得看",
        "excerpt_heading": "原文摘录",
        "notes_heading": "说明",
        "original_link": "原文链接",
        "zhihu_original": "知乎原文",
        "zhihu_thin_card": "该知乎结果为发现导向；证据较薄，摘要深度可能有限。",
        "zhihu_freshness": "搜索相关性是官方搜索相关性，不是热度或时效性指标。",
    },
}


def card_lang(language: str | None) -> CardLang:
    """Map a stored or requested language onto a supported card language."""
    return "zh-CN" if language == "zh-CN" else "en"


def legacy_card_lang(language: str | None, source_kind: SourceKind | None) -> CardLang:
    """Entries saved before a language was stored: Juya and Zhihu cards stay Chinese."""
    if language in ("en", "zh-CN"):
        return card_lang(language)
    if source_kind in (SourceKind.JUYA, SourceKind.ZHIHU):
        return "zh-CN"
    return "en"


def text(lang: CardLang, key: str, **values: str) -> str:
    return _CAVEATS[lang][key].format(**values)
