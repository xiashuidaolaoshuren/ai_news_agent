"""Write the prototype's conversations into a SQLite file."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ai_news_agent.models import (
    ConnectorWarning,
    Digest,
    DigestEntry,
    FollowUpAction,
    NewsItem,
    RankedItem,
    SourceKind,
)
from ai_news_agent.repositories.digest_store import DigestStore
from ai_news_agent.repositories.session_store import SessionStore

_WEEKLY_PROMPT = (
    "What shipped in AI models and agent tooling this week? "
    "Focus on what I should actually learn from."
)
_GGUF_PROMPT = "What is a GGUF quant, and should I care?"
_GGUF_MARKDOWN = """### What a GGUF quant is

GGUF is the model file format used by **llama.cpp** and the tools built on it. A *quant* stores the weights at lower precision (for example `Q4_K_M`, about 4–5 bits per weight), so the model fits in far less memory.

- **Should you care?** Yes, if you run models locally on a consumer GPU or CPU.
- **Trade-off:** smaller files and lower VRAM use, with some quality loss that grows as the bit count drops.
- In today’s table, `abenzerps/Qwen-Image-2.1-Uncensored-GGUF` is a community GGUF quant of `Qwen/Qwen-Image-2.1`.

> Start with a Q4 or Q5 quant. Compare against the original only if output quality matters for your task.
"""


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _iso(value: str) -> str:
    return _utc(value).isoformat()


def write_prototype_demo(db_path: str | Path, *, force: bool = False) -> None:
    """Create the demo database. Refuses to replace an existing file unless force is set."""
    path = Path(db_path)
    if path.exists() and not force:
        raise FileExistsError(path)
    if path.exists():
        path.unlink()
    seed_prototype_demo(path)


def seed_prototype_demo(db_path: str | Path) -> None:
    """Insert the six prototype sessions. Existing files are replaced by the caller."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    digest_store = DigestStore(path)
    digest_store.init_schema()
    sessions = SessionStore(path)

    _create_session(
        sessions,
        "demo-s2",
        title=None,
        connector_names=None,
        items_per_source=None,
    )
    _create_session(
        sessions,
        "demo-s1",
        title="Open models & agent tools this week",
        connector_names=["juya", "huggingface", "github"],
        items_per_source=5,
    )
    _create_session(
        sessions,
        "demo-s3",
        title="Qwen-Image-2.1 follow-up",
        connector_names=["juya"],
        items_per_source=5,
    )
    _create_session(
        sessions,
        "demo-s4",
        title="Weekend Juya catch-up",
        connector_names=["juya"],
        items_per_source=5,
    )
    _create_session(
        sessions,
        "demo-s6",
        title="Agent tooling repos",
        connector_names=["github"],
        items_per_source=5,
    )
    _create_session(
        sessions,
        "demo-s5",
        title="Video generation models",
        connector_names=["huggingface"],
        items_per_source=5,
    )

    _seed_conversation(
        digest_store,
        sessions,
        session_id="demo-s1",
        prompt=_WEEKLY_PROMPT,
        connectors=["juya", "huggingface", "github"],
        when=_utc("2026-10-01T20:04:00"),
        followups=[(_GGUF_PROMPT, _GGUF_MARKDOWN, "2026-10-01T20:09:00")],
        message_times=[
            "2026-10-01T20:04:00",
            "2026-10-01T20:04:00",
            "2026-10-01T20:09:00",
            "2026-10-01T20:09:00",
        ],
        updated_at="2026-10-01T20:09:00",
    )
    _seed_conversation(
        digest_store,
        sessions,
        session_id="demo-s3",
        prompt="Summarize today’s Juya AI 早报",
        connectors=["juya"],
        when=_utc("2026-09-21T09:40:00"),
        followups=[],
        message_times=["2026-09-21T09:40:00", "2026-09-21T09:40:00"],
        updated_at="2026-09-21T09:40:00",
    )
    _seed_conversation(
        digest_store,
        sessions,
        session_id="demo-s4",
        prompt="Catch me up on Juya for the weekend",
        connectors=["juya"],
        when=_utc("2026-09-20T10:15:00"),
        followups=[],
        message_times=["2026-09-20T10:15:00", "2026-09-20T10:15:00"],
        updated_at="2026-09-20T10:15:00",
    )
    _seed_conversation(
        digest_store,
        sessions,
        session_id="demo-s6",
        prompt="Trending agent tooling on GitHub",
        connectors=["github"],
        when=_utc("2026-09-19T21:02:00"),
        followups=[],
        message_times=["2026-09-19T21:02:00", "2026-09-19T21:02:00"],
        updated_at="2026-09-19T21:02:00",
    )
    _seed_conversation(
        digest_store,
        sessions,
        session_id="demo-s5",
        prompt="Which video and multimodal models are trending?",
        connectors=["huggingface"],
        when=_utc("2026-09-17T18:30:00"),
        followups=[],
        message_times=["2026-09-17T18:30:00", "2026-09-17T18:30:00"],
        updated_at="2026-09-17T18:30:00",
    )
    _set_updated_at(path, "demo-s2", "2026-10-01T20:12:00")


def _create_session(
    sessions: SessionStore,
    session_id: str,
    *,
    title: str | None,
    connector_names: list[str] | None,
    items_per_source: int | None,
) -> None:
    sessions.create_session(
        session_id,
        title=title,
        connector_names=connector_names,
        items_per_source=items_per_source,
    )


def _seed_conversation(
    digest_store: DigestStore,
    sessions: SessionStore,
    *,
    session_id: str,
    prompt: str,
    connectors: list[str],
    when: datetime,
    followups: list[tuple[str, str, str]],
    message_times: list[str],
    updated_at: str,
) -> None:
    user_id = sessions.insert_message(session_id, role="user", content=prompt)
    request_id = f"{session_id}-digest"
    sessions.create_request(
        session_id,
        request_id,
        user_message_id=user_id,
        correlation_id=request_id,
    )
    run_id = _save_session_digest(
        digest_store,
        session_id=session_id,
        request_id=request_id,
        connectors=connectors,
        when=when,
    )
    assistant_id = sessions.insert_message(
        session_id,
        role="assistant",
        content="Digest ready.",
        run_id=run_id,
    )
    sessions.mark_terminal(
        session_id,
        request_id,
        status="succeeded",
        assistant_message_id=assistant_id,
    )
    for question, answer, _stamp in followups:
        sessions.insert_message(session_id, role="user", content=question)
        sessions.insert_message(session_id, role="assistant", content=answer)
    _set_updated_at(digest_store.db_path, session_id, updated_at)
    _set_message_times(digest_store.db_path, session_id, message_times)


def _save_session_digest(
    digest_store: DigestStore,
    *,
    session_id: str,
    request_id: str,
    connectors: list[str],
    when: datetime,
) -> int:
    items, entries, warnings, topics = _digest_rows(session_id, when)
    return digest_store.save_digest_bundle(
        requested_at=when,
        timeframe="week",
        topics=topics,
        connector_names=connectors,
        items=items,
        warnings=warnings,
        ranked=[
            RankedItem(item=item, score_total=1.0, selected=True, selection_reason="demo")
            for item in items
        ],
        digest=Digest(generated_at=when, entries=entries, topics=topics, timeframe="week"),
        session_id=session_id,
        request_id=request_id,
    )


def _digest_rows(
    session_id: str,
    when: datetime,
) -> tuple[list[NewsItem], list[DigestEntry], list[ConnectorWarning], list[str]]:
    if session_id == "demo-s1":
        rows = [*_JUYA_ROWS, *_HF_ROWS, *_GITHUB_ROWS]
        warnings = [
            ConnectorWarning(
                connector="zhihu",
                code="empty",
                message=(
                    "Connector returned no items for this request. "
                    "Other sources completed normally."
                ),
            ),
            ConnectorWarning(
                connector="bilibili",
                code="timeout",
                message="Request timed out. 0 of 5 items returned; other sources completed normally.",
            ),
        ]
    else:
        rows = _ARCHIVED_ROWS[session_id]
        warnings = []
    items: list[NewsItem] = []
    entries: list[DigestEntry] = []
    topics: list[str] = []
    for row in rows:
        item, entry = _row_to_models(row, when)
        items.append(item)
        entries.append(entry)
        topic = row.get("topic")
        if isinstance(topic, str) and topic not in topics:
            topics.append(topic)
    return items, entries, warnings, topics or ["Headlines"]


def _row_to_models(row: dict[str, object], when: datetime) -> tuple[NewsItem, DigestEntry]:
    kind = SourceKind(str(row["kind"]))
    source_id = str(row["source_id"])
    title = str(row["title"])
    url = str(row["url"])
    evidence = row.get("evidence")
    item = NewsItem(
        source=kind,
        source_id=source_id,
        url=url,
        title=title,
        collected_at=when,
        language=row.get("language") if isinstance(row.get("language"), str) else None,
        stars_or_views=row.get("stars") if isinstance(row.get("stars"), int) else None,
        source_evidence=evidence if isinstance(evidence, dict) else {},
    )
    entry = DigestEntry(
        source_kind=kind,
        source_id=source_id,
        title=title,
        source_name=str(row["source_name"]),
        source_url=url,
        summary=str(row["summary"]),
        why_it_matters=str(row["why"]),
        background_knowledge="",
        follow_up_action=FollowUpAction.READ,
    )
    return item, entry


_DEMO_ASSETS = "https://demo-assets.local"


def _demo_avatar(filename: str) -> str:
    return f"{_DEMO_ASSETS}/avatars/{filename}"


def _demo_preview(filename: str) -> str:
    return f"{_DEMO_ASSETS}/previews/{filename}"


_JUYA_ISSUE = {
    "juya_item_type": "story",
    "issue_id": "juya-2026-10-01",
    "issue_date": "2026-10-01",
    "issue_url": "https://daily.juya.uk",
    "issue_cover_url": _demo_preview("juya-cover-20261001.png"),
    "issue_lead_title": "Google 发布 Gemini 4 Argon",
    "story_original_url": "https://daily.juya.uk",
}

_JUYA_ROWS: list[dict[str, object]] = [
    {
        "kind": "juya",
        "source_id": "juya-2026-10-01-1",
        "title": "Google 发布 Gemini 4 Argon",
        "url": "https://daily.juya.uk",
        "source_name": "AI 早报 2026-10-01",
        "summary": "Google released Gemini 4 Argon. Lead story and cover of the 10-01 issue.",
        "why": "A new Gemini generation moves the comparison baseline; expect this month’s benchmark claims to cite it.",
        "topic": "Headlines",
        "evidence": {**_JUYA_ISSUE, "story_section": "Headlines", "story_number": 1},
    },
    {
        "kind": "juya",
        "source_id": "juya-2026-10-01-2",
        "title": "哔哩哔哩发布并开源 Index Translate 多语言翻译模型系列",
        "url": "https://daily.juya.uk",
        "source_name": "AI 早报 2026-10-01",
        "summary": "Bilibili released and open-sourced Index Translate, a series of multilingual translation models.",
        "why": "Open translation weights you can run locally and compare against hosted translation APIs.",
        "topic": "Model releases",
        "evidence": {**_JUYA_ISSUE, "story_section": "Model releases", "story_number": 2},
    },
    {
        "kind": "juya",
        "source_id": "juya-2026-10-01-3",
        "title": "蚂蚁百灵发布 Ling 3.1 flash，开放两周免费体验",
        "url": "https://daily.juya.uk",
        "source_name": "AI 早报 2026-10-01",
        "summary": "Ant Group’s Ling team released Ling 3.1 flash, with a two-week free trial.",
        "why": "A free window is a low-cost chance to test a fast model on your own prompts.",
        "topic": "Model releases",
        "evidence": {**_JUYA_ISSUE, "story_section": "Model releases", "story_number": 3},
    },
    {
        "kind": "juya",
        "source_id": "juya-2026-10-01-4",
        "title": "MiniMax 上线 M Plan 订阅，Token Plan 停止新购",
        "url": "https://daily.juya.uk",
        "source_name": "AI 早报 2026-10-01",
        "summary": "MiniMax launched an M Plan subscription and stopped selling its Token Plan to new buyers.",
        "why": "If you call MiniMax from your own projects, check how the pricing change affects you.",
        "topic": "Industry",
        "evidence": {**_JUYA_ISSUE, "story_section": "Industry", "story_number": 4},
    },
    {
        "kind": "juya",
        "source_id": "juya-2026-10-01-5",
        "title": "Space Bunny Alpha 匿名测试期延长至 10 月 5 日",
        "url": "https://daily.juya.uk",
        "source_name": "AI 早报 2026-10-01",
        "summary": "The anonymous test period for Space Bunny Alpha was extended to October 5.",
        "why": "Anonymous test models often precede a named release; worth trying while the window is open.",
        "topic": "Model releases",
        "evidence": {**_JUYA_ISSUE, "story_section": "Model releases", "story_number": 5},
    },
]

_HF_ROWS: list[dict[str, object]] = [
    {
        "kind": "huggingface",
        "source_id": "Edge0/Audio8-ASR-Infinite",
        "title": "Edge0/Audio8-ASR-Infinite",
        "url": "https://huggingface.co/Edge0/Audio8-ASR-Infinite",
        "source_name": "Hugging Face",
        "summary": "automatic-speech-recognition · trending 1,479 · 27,228 downloads (30 days).",
        "why": "A trending speech model to compare against hosted transcription.",
        "topic": "Model releases",
        "evidence": {
            "owner_name": "Edge0",
            "owner_type": "organisation",
            "owner_profile_url": "https://huggingface.co/Edge0",
            "owner_avatar_url": _demo_avatar("hf-Edge0.webp"),
            "trending_score": 1479,
            "downloads_30d": 27228,
            "likes": 1989,
            "pipeline_tag": "automatic-speech-recognition",
        },
    },
    {
        "kind": "huggingface",
        "source_id": "convaiinnovations/laya",
        "title": "convaiinnovations/laya",
        "url": "https://huggingface.co/convaiinnovations/laya",
        "source_name": "Hugging Face",
        "summary": "text-classification · trending 1,293.",
        "why": "A compact classification model that is climbing the trending list.",
        "topic": "Model releases",
        "evidence": {
            "owner_name": "convaiinnovations",
            "owner_type": "organisation",
            "owner_profile_url": "https://huggingface.co/convaiinnovations",
            "owner_avatar_url": _demo_avatar("hf-convaiinnovations.webp"),
            "trending_score": 1293,
            "downloads_30d": 0,
            "likes": 4739,
            "pipeline_tag": "text-classification",
        },
    },
    {
        "kind": "huggingface",
        "source_id": "XingChen-AGI/TeleOCR",
        "title": "XingChen-AGI/TeleOCR",
        "url": "https://huggingface.co/XingChen-AGI/TeleOCR",
        "source_name": "Hugging Face",
        "summary": "image-text-to-text · trending 851 · 31,584 downloads (30 days).",
        "why": "OCR weights you can try on your own documents.",
        "topic": "Model releases",
        "evidence": {
            "owner_name": "XingChen-AGI",
            "owner_type": "organisation",
            "owner_profile_url": "https://huggingface.co/XingChen-AGI",
            "owner_avatar_url": _demo_avatar("hf-XingChen-AGI.webp"),
            "trending_score": 851,
            "downloads_30d": 31584,
            "likes": 1129,
            "pipeline_tag": "image-text-to-text",
        },
    },
    {
        "kind": "huggingface",
        "source_id": "abenzerps/Qwen-Image-2.1-Uncensored-GGUF",
        "title": "abenzerps/Qwen-Image-2.1-Uncensored-GGUF",
        "url": "https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF",
        "source_name": "Hugging Face",
        "summary": "GGUF quant of Qwen-Image-2.1 · trending 816 · 1,303,476 downloads (30 days).",
        "why": "A community quant of Qwen-Image-2.1 for local image generation.",
        "topic": "Model releases",
        "evidence": {
            "owner_name": "abenzerps",
            "owner_type": "person",
            "owner_profile_url": "https://huggingface.co/abenzerps",
            "trending_score": 816,
            "downloads_30d": 1303476,
            "likes": 2626,
            "pipeline_tag": "text-to-image",
            "base_model": "Qwen/Qwen-Image-2.1",
            "family_variants": [
                {
                    "source_id": "Qwen/Qwen-Image-2.1",
                    "title": "Qwen/Qwen-Image-2.1",
                    "url": "https://huggingface.co/Qwen/Qwen-Image-2.1",
                }
            ],
        },
    },
    {
        "kind": "huggingface",
        "source_id": "Contrastive-LM/CLM-v0.1-8B",
        "title": "Contrastive-LM/CLM-v0.1-8B",
        "url": "https://huggingface.co/Contrastive-LM/CLM-v0.1-8B",
        "source_name": "Hugging Face",
        "summary": "text-ranking · trending 498 · fine-tune of Qwen/Qwen3-8B.",
        "why": "A small fine-tune to compare with its base model.",
        "topic": "Model releases",
        "evidence": {
            "owner_name": "Contrastive-LM",
            "owner_type": "organisation",
            "owner_profile_url": "https://huggingface.co/Contrastive-LM",
            "owner_avatar_url": _demo_avatar("hf-Contrastive-LM.webp"),
            "trending_score": 498,
            "downloads_30d": 2720,
            "likes": 583,
            "pipeline_tag": "text-ranking",
            "base_model": "Qwen/Qwen3-8B",
        },
    },
]

_GITHUB_ROWS: list[dict[str, object]] = [
    {
        "kind": "github",
        "source_id": "NVIDIA/OpenShell",
        "title": "NVIDIA/OpenShell",
        "url": "https://github.com/NVIDIA/OpenShell",
        "source_name": "Rust · 13,659 ★ · +2,503 today",
        "summary": "OpenShell is the safe, private runtime for autonomous AI agents.",
        "why": "Sandboxed runtimes are becoming the standard answer to letting an agent run commands.",
        "topic": "Developer ecosystem",
        "language": "Rust",
        "stars": 13659,
        "evidence": {
            "owner_name": "NVIDIA",
            "owner_type": "organisation",
            "owner_profile_url": "https://github.com/NVIDIA",
            "owner_avatar_url": _demo_avatar("gh-NVIDIA.png"),
            "preview_image_url": _demo_preview("gh-og-NVIDIA-OpenShell.png"),
            "stars_today": 2503,
        },
    },
    {
        "kind": "github",
        "source_id": "DietrichGebert/ponytail",
        "title": "DietrichGebert/ponytail",
        "url": "https://github.com/DietrichGebert/ponytail",
        "source_name": "JavaScript · 149,759 ★ · +1,179 today",
        "summary": "Makes your AI agent think like the laziest senior dev in the room.",
        "why": "A compact example of steering agent behaviour with instructions alone.",
        "topic": "Developer ecosystem",
        "language": "JavaScript",
        "stars": 149759,
        "evidence": {
            "owner_name": "DietrichGebert",
            "owner_type": "person",
            "owner_profile_url": "https://github.com/DietrichGebert",
            "owner_avatar_url": _demo_avatar("gh-DietrichGebert.png"),
            "stars_today": 1179,
        },
    },
    {
        "kind": "github",
        "source_id": "mattpocock/skills",
        "title": "mattpocock/skills",
        "url": "https://github.com/mattpocock/skills",
        "source_name": "Shell · 273,407 ★ · +888 today",
        "summary": "Skills for Real Engineers. Straight from my .agents directory.",
        "why": "A concrete reference for how to structure reusable agent skill files.",
        "topic": "Developer ecosystem",
        "language": "Shell",
        "stars": 273407,
        "evidence": {
            "owner_name": "mattpocock",
            "owner_type": "person",
            "owner_profile_url": "https://github.com/mattpocock",
            "owner_avatar_url": _demo_avatar("gh-mattpocock.png"),
            "preview_image_url": _demo_preview("gh-og-mattpocock-skills.png"),
            "stars_today": 888,
        },
    },
    {
        "kind": "github",
        "source_id": "mvschwarz/openrig",
        "title": "mvschwarz/openrig",
        "url": "https://github.com/mvschwarz/openrig",
        "source_name": "TypeScript · 3,333 ★ · +640 today",
        "summary": "Build your own network of agents from Claude Code, Codex and Pi.",
        "why": "Shows one practical pattern for long-lived multi-agent teams with shared context.",
        "topic": "Developer ecosystem",
        "language": "TypeScript",
        "stars": 3333,
        "evidence": {
            "owner_name": "mvschwarz",
            "owner_type": "person",
            "owner_profile_url": "https://github.com/mvschwarz",
            "owner_avatar_url": _demo_avatar("gh-mvschwarz.png"),
            "stars_today": 640,
        },
    },
    {
        "kind": "github",
        "source_id": "mksglu/context-mode",
        "title": "mksglu/context-mode",
        "url": "https://github.com/mksglu/context-mode",
        "source_name": "TypeScript · 24,650 ★ · +357 today",
        "summary": "Context window optimization for AI coding agents.",
        "why": "Context budgeting is a recurring bottleneck; this is a hands-on way to learn the techniques.",
        "topic": "Developer ecosystem",
        "language": "TypeScript",
        "stars": 24650,
        "evidence": {
            "owner_name": "mksglu",
            "owner_type": "person",
            "owner_profile_url": "https://github.com/mksglu",
            "owner_avatar_url": _demo_avatar("gh-mksglu.png"),
            "stars_today": 357,
        },
    },
]


def _archived_juya(date: str, number: int, title: str, topic: str, summary: str) -> dict[str, object]:
    return {
        "kind": "juya",
        "source_id": f"juya-{date}-{number}",
        "title": title,
        "url": "https://daily.juya.uk",
        "source_name": f"AI 早报 {date}",
        "summary": summary,
        "why": f"From AI 早报 {date}.",
        "topic": topic,
        "evidence": {
            "juya_item_type": "story",
            "issue_id": f"juya-{date}",
            "issue_date": date,
            "issue_url": "https://daily.juya.uk",
            "issue_lead_title": title if number == 1 else None,
            "story_section": topic,
            "story_original_url": "https://daily.juya.uk",
            "story_number": number,
        },
    }


_ARCHIVED_ROWS: dict[str, list[dict[str, object]]] = {
    "demo-s3": [
        _archived_juya(
            "2026-09-21",
            1,
            "Qwen开源图形生成与编辑模型Qwen-Image-2.1",
            "Model releases",
            "From AI 早报 2026-09-21, item #1.",
        ),
        _archived_juya(
            "2026-09-21",
            2,
            "阶跃发布 Step 5 Preview，目前已全量开放",
            "Headlines",
            "From AI 早报 2026-09-21, item #2.",
        ),
        _archived_juya(
            "2026-09-21",
            4,
            "Google开源Agentic编排器AX，支持有状态任务暂停与恢复",
            "Developer ecosystem",
            "From AI 早报 2026-09-21, item #4.",
        ),
        _archived_juya(
            "2026-09-21",
            5,
            "腾讯开源端到端文档解析模型WeVisDoc",
            "Model releases",
            "From AI 早报 2026-09-21, item #5.",
        ),
    ],
    "demo-s4": [
        _archived_juya(
            "2026-09-20",
            1,
            "DeepSeek API明确节假日及调休周末全天按空闲时段计费",
            "Developer ecosystem",
            "From AI 早报 2026-09-20, item #1.",
        ),
        _archived_juya(
            "2026-09-20",
            4,
            "千问发布Qwen3.8-LiveTranslate",
            "Model releases",
            "From AI 早报 2026-09-20, item #4.",
        ),
    ],
    "demo-s6": [
        {
            "kind": "github",
            "source_id": "obra/superpowers",
            "title": "obra/superpowers",
            "url": "https://github.com/obra/superpowers",
            "source_name": "GitHub",
            "summary": "An agentic skills framework & software development methodology that works.",
            "why": "A reference for agent skill workflows.",
            "topic": "Developer ecosystem",
            "evidence": {
                "owner_name": "obra",
                "owner_type": "person",
                "owner_profile_url": "https://github.com/obra",
            },
        },
        {
            "kind": "github",
            "source_id": "earendil-works/pi",
            "title": "earendil-works/pi",
            "url": "https://github.com/earendil-works/pi",
            "source_name": "GitHub",
            "summary": "AI agent toolkit: unified LLM API, agent loop, TUI, coding agent CLI.",
            "why": "A toolkit that covers the agent loop and a coding CLI.",
            "topic": "Developer ecosystem",
            "evidence": {
                "owner_name": "earendil-works",
                "owner_type": "organisation",
                "owner_profile_url": "https://github.com/earendil-works",
            },
        },
    ],
    "demo-s5": [
        {
            "kind": "huggingface",
            "source_id": "Lightricks/LTX-2.5",
            "title": "Lightricks/LTX-2.5",
            "url": "https://huggingface.co/Lightricks/LTX-2.5",
            "source_name": "Hugging Face",
            "summary": "image-to-video · 1,588,619 downloads (30 days) · 5,781 likes.",
            "why": "A video model with a large recent download count.",
            "topic": "Model releases",
            "evidence": {
                "owner_name": "Lightricks",
                "owner_type": "organisation",
                "owner_profile_url": "https://huggingface.co/Lightricks",
                "pipeline_tag": "image-to-video",
                "downloads_30d": 1588619,
                "likes": 5781,
            },
        },
        {
            "kind": "huggingface",
            "source_id": "Qwen/Qwen3.8-27B",
            "title": "Qwen/Qwen3.8-27B",
            "url": "https://huggingface.co/Qwen/Qwen3.8-27B",
            "source_name": "Hugging Face",
            "summary": "image-text-to-text · 6,950,834 downloads (30 days) · 16,687 likes.",
            "why": "A multimodal Qwen release with a large download count.",
            "topic": "Model releases",
            "evidence": {
                "owner_name": "Qwen",
                "owner_type": "organisation",
                "owner_profile_url": "https://huggingface.co/Qwen",
                "pipeline_tag": "image-text-to-text",
                "downloads_30d": 6950834,
                "likes": 16687,
            },
        },
    ],
}


def _set_updated_at(db_path: Path, session_id: str, stamp: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (_iso(stamp), session_id),
        )


def _set_message_times(db_path: Path, session_id: str, stamps: list[str]) -> None:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id FROM session_messages
            WHERE session_id = ?
            ORDER BY sequence ASC
            """,
            (session_id,),
        ).fetchall()
        if len(rows) != len(stamps):
            raise ValueError(f"{session_id} has {len(rows)} messages, expected {len(stamps)}")
        for row, stamp in zip(rows, stamps, strict=True):
            conn.execute(
                "UPDATE session_messages SET created_at = ? WHERE id = ?",
                (_iso(stamp), row[0]),
            )
