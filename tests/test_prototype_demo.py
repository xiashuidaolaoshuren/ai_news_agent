"""Prototype demo database seeder."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ai_news_agent.repositories.digest_store import DigestStore
from ai_news_agent.repositories.session_store import SessionStore


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def test_seed_creates_prototype_sessions(tmp_path: Path) -> None:
    from ai_news_agent.dev.prototype_demo import seed_prototype_demo

    db_path = tmp_path / "prototype.sqlite"
    seed_prototype_demo(db_path)

    store = DigestStore(db_path)
    store.init_schema()
    sessions = {session.id: session for session in SessionStore(db_path).list_sessions()}
    stats = SessionStore(db_path).get_session_request_stats()

    assert set(sessions) == {
        "demo-s1",
        "demo-s2",
        "demo-s3",
        "demo-s4",
        "demo-s5",
        "demo-s6",
    }
    assert sessions["demo-s2"].title is None
    assert sessions["demo-s2"].connector_names is None
    assert sessions["demo-s2"].items_per_source is None
    assert stats.get("demo-s2") is None
    assert SessionStore(db_path).list_messages("demo-s2") == []

    assert sessions["demo-s1"].title == "Open models & agent tools this week"
    assert sessions["demo-s1"].connector_names == ["juya", "huggingface", "github"]
    assert sessions["demo-s1"].items_per_source == 5
    assert sessions["demo-s1"].updated_at == _at("2026-10-01T20:09:00")
    assert stats["demo-s1"].digest_count == 1

    assert sessions["demo-s3"].title == "Qwen-Image-2.1 follow-up"
    assert sessions["demo-s3"].connector_names == ["juya"]
    assert sessions["demo-s3"].updated_at == _at("2026-09-21T09:40:00")
    assert sessions["demo-s4"].title == "Weekend Juya catch-up"
    assert sessions["demo-s4"].connector_names == ["juya"]
    assert sessions["demo-s4"].updated_at == _at("2026-09-20T10:15:00")
    assert sessions["demo-s6"].title == "Agent tooling repos"
    assert sessions["demo-s6"].connector_names == ["github"]
    assert sessions["demo-s6"].updated_at == _at("2026-09-19T21:02:00")
    assert sessions["demo-s5"].title == "Video generation models"
    assert sessions["demo-s5"].connector_names == ["huggingface"]
    assert sessions["demo-s5"].updated_at == _at("2026-09-17T18:30:00")
    assert sessions["demo-s2"].updated_at == _at("2026-10-01T20:12:00")
    for session_id in ("demo-s3", "demo-s4", "demo-s5", "demo-s6"):
        assert sessions[session_id].items_per_source == 5
        assert stats[session_id].digest_count == 1
        assert stats[session_id].active_request_id is None

    messages = SessionStore(db_path).list_messages("demo-s1")
    assert [message.role for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert messages[0].content == (
        "What shipped in AI models and agent tooling this week? "
        "Focus on what I should actually learn from."
    )
    assert messages[0].created_at == _at("2026-10-01T20:04:00")
    assert messages[1].run_id is not None
    assert messages[2].content == "What is a GGUF quant, and should I care?"
    assert messages[2].created_at == _at("2026-10-01T20:09:00")
    assert messages[3].run_id is None
    assert "GGUF" in messages[3].content
    assert messages[3].created_at == _at("2026-10-01T20:09:00")

    prompts = {
        "demo-s3": "Summarize today’s Juya AI 早报",
        "demo-s4": "Catch me up on Juya for the weekend",
        "demo-s6": "Trending agent tooling on GitHub",
        "demo-s5": "Which video and multimodal models are trending?",
    }
    for session_id, prompt in prompts.items():
        archived = SessionStore(db_path).list_messages(session_id)
        assert [message.role for message in archived] == ["user", "assistant"]
        assert archived[0].content == prompt
        assert archived[1].run_id is not None


def _digest_message(db_path: Path, session_id: str) -> dict:
    from fastapi.testclient import TestClient

    from ai_news_agent.api.app import create_app
    from ai_news_agent.services.composition import build_application

    client = TestClient(create_app(build_application(fake=True, db_path=db_path)))
    response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert response.status_code == 200
    digest_messages = [
        message
        for message in response.json()["messages"]
        if message["role"] == "assistant" and message["digest"] is not None
    ]
    assert len(digest_messages) == 1
    return digest_messages[0]


def test_seed_stores_prototype_digest_evidence(tmp_path: Path) -> None:
    from ai_news_agent.dev.prototype_demo import seed_prototype_demo

    db_path = tmp_path / "prototype.sqlite"
    seed_prototype_demo(db_path)
    digest = _digest_message(db_path, "demo-s1")
    entries = digest["digest"]["entries"]
    by_kind: dict[str, list[dict]] = {}
    for entry in entries:
        by_kind.setdefault(entry["source_kind"], []).append(entry)

    assert [entry["title"] for entry in by_kind["juya"]] == [
        "Google 发布 Gemini 4 Argon",
        "哔哩哔哩发布并开源 Index Translate 多语言翻译模型系列",
        "蚂蚁百灵发布 Ling 3.1 flash，开放两周免费体验",
        "MiniMax 上线 M Plan 订阅，Token Plan 停止新购",
        "Space Bunny Alpha 匿名测试期延长至 10 月 5 日",
    ]
    lead = by_kind["juya"][0]
    assert lead["item_type"] == "story"
    assert lead["issue"]["date"] == "2026-10-01"
    assert lead["issue"]["lead_title"] == "Google 发布 Gemini 4 Argon"
    assert (
        lead["issue"]["cover_url"]
        == "https://demo-assets.local/previews/juya-cover-20261001.png"
    )
    assert lead["story"]["section"] == "Headlines"

    edge0 = next(
        entry for entry in by_kind["huggingface"] if entry["title"] == "Edge0/Audio8-ASR-Infinite"
    )
    assert edge0["owner"]["avatar_url"] == "https://demo-assets.local/avatars/hf-Edge0.webp"

    gguf = next(
        entry
        for entry in by_kind["huggingface"]
        if entry["title"] == "abenzerps/Qwen-Image-2.1-Uncensored-GGUF"
    )
    assert gguf["base_model"] == "Qwen/Qwen-Image-2.1"
    assert gguf["trending_score"] == 816
    assert gguf["downloads_30d"] == 1303476
    assert gguf["pipeline_tag"] == "text-to-image"
    assert gguf["owner"]["type"] == "person"
    assert gguf["owner"]["avatar_url"] is None

    openshell = next(entry for entry in by_kind["github"] if entry["title"] == "NVIDIA/OpenShell")
    assert openshell["language"] == "Rust"
    assert openshell["stars"] == 13659
    assert openshell["stars_today"] == 2503
    assert openshell["owner"]["name"] == "NVIDIA"
    assert openshell["owner"]["type"] == "organisation"
    assert (
        openshell["preview_image_url"]
        == "https://demo-assets.local/previews/gh-og-NVIDIA-OpenShell.png"
    )
    assert (
        openshell["owner"]["avatar_url"] == "https://demo-assets.local/avatars/gh-NVIDIA.png"
    )

    skills = next(entry for entry in by_kind["github"] if entry["title"] == "mattpocock/skills")
    assert (
        skills["preview_image_url"]
        == "https://demo-assets.local/previews/gh-og-mattpocock-skills.png"
    )

    warning_text = {warning["connector"]: warning["message"] for warning in digest["warnings"]}
    assert "no items" in warning_text["zhihu"]
    assert "timed out" in warning_text["bilibili"]

    qwen = _digest_message(db_path, "demo-s3")
    qwen_entries = qwen["digest"]["entries"]
    assert qwen_entries[0]["title"] == "Qwen开源图形生成与编辑模型Qwen-Image-2.1"
    assert (
        qwen_entries[0]["issue"]["cover_url"]
        == "https://demo-assets.local/previews/juya-cover-20260921.png"
    )
    assert qwen_entries[0]["story"]["number"] == 1
    assert qwen_entries[2]["story"]["number"] == 4
    weekend = _digest_message(db_path, "demo-s4")
    assert weekend["digest"]["entries"][0]["title"].startswith("DeepSeek API")
    assert (
        weekend["digest"]["entries"][0]["issue"]["cover_url"]
        == "https://demo-assets.local/previews/juya-cover-20260920.png"
    )
    repos = _digest_message(db_path, "demo-s6")
    assert [entry["title"] for entry in repos["digest"]["entries"]] == [
        "obra/superpowers",
        "earendil-works/pi",
    ]
    assert (
        repos["digest"]["entries"][0]["owner"]["avatar_url"]
        == "https://demo-assets.local/avatars/gh-obra.png"
    )
    assert (
        repos["digest"]["entries"][0]["preview_image_url"]
        == "https://demo-assets.local/previews/gh-og-obra-superpowers.png"
    )
    video = _digest_message(db_path, "demo-s5")
    assert video["digest"]["entries"][0]["title"] == "Lightricks/LTX-2.5"
    assert video["digest"]["entries"][0]["downloads_30d"] == 1588619
    assert (
        video["digest"]["entries"][0]["owner"]["avatar_url"]
        == "https://demo-assets.local/avatars/hf-Lightricks.png"
    )
    assert (
        video["digest"]["entries"][1]["owner"]["avatar_url"]
        == "https://demo-assets.local/avatars/hf-Qwen.jpeg"
    )


def test_seed_is_searchable(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from ai_news_agent.api.app import create_app
    from ai_news_agent.dev.prototype_demo import seed_prototype_demo
    from ai_news_agent.services.composition import build_application

    db_path = tmp_path / "prototype.sqlite"
    seed_prototype_demo(db_path)
    client = TestClient(create_app(build_application(fake=True, db_path=db_path)))

    history = client.get("/api/v1/history/search", params={"text": "qwen"})
    assert history.status_code == 200
    matches = history.json()["matches"]
    assert matches
    assert any("Qwen" in match["title"] for match in matches)
    shown = client.get(f"/api/v1/history/{matches[0]['ref']['token']}")
    assert shown.status_code == 200
    assert shown.json()["entry"]["title"] == matches[0]["title"]

    sessions = client.get("/api/v1/sessions/search", params={"q": "GGUF"})
    assert sessions.status_code == 200
    hits = sessions.json()["hits"]
    assert [hit["session_id"] for hit in hits] == ["demo-s1"]
    assert "GGUF" in hits[0]["excerpt"]


def test_demo_db_writes_and_refuses_overwrite(tmp_path: Path, monkeypatch) -> None:
    from ai_news_agent.cli import main
    from ai_news_agent.repositories.session_store import SessionStore

    monkeypatch.chdir(tmp_path)
    assert main(["demo-db"]) == 0
    db_path = tmp_path / ".demo" / "prototype.sqlite"
    assert db_path.is_file()
    original = db_path.read_bytes()
    assert len(SessionStore(db_path).list_sessions()) == 6

    assert main(["demo-db"]) == 2
    assert db_path.read_bytes() == original

    assert main(["demo-db", "--force"]) == 0
    assert len(SessionStore(db_path).list_sessions()) == 6

    custom = tmp_path / "custom.sqlite"
    assert main(["demo-db", "--db-path", str(custom), "--force"]) == 0
    assert len(SessionStore(custom).list_sessions()) == 6
