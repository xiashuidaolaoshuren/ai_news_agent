"""Canonical source registry and connector factory for CLI and API entrypoints."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from ai_news_agent.connectors.base import ConnectorRequest, ConnectorResult, SourceConnector
from ai_news_agent.credentials import CredentialsProvider
from ai_news_agent.models import ConnectorWarning
from ai_news_agent.connectors.bilibili import BilibiliConnector
from ai_news_agent.connectors.github import GitHubConnector
from ai_news_agent.connectors.huggingface import HuggingFaceConnector
from ai_news_agent.connectors.juya import JuyaConnector
from ai_news_agent.connectors.openrouter import OpenRouterConnector
from ai_news_agent.connectors.zhihu import ZhihuConnector
from ai_news_agent.models import NewsItem, SourceKind

ALLOWED_SOURCES: frozenset[str] = frozenset(
    {"juya", "github", "bilibili", "huggingface", "openrouter", "zhihu"}
)
DEFAULT_SOURCE_NAMES: tuple[str, ...] = ("juya",)


class FakeDigestModel:
    """Matches summarizer contract: ``generate_entry_fields``."""

    def generate_entry_fields(self, context: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        return {
            "summary": "Fake summary",
            "why_it_matters": "Because tests need it",
            "background_knowledge": "N/A",
            "follow_up_action": "read",
        }


class FakeGitHubConnector:
    """Deterministic offline stand-in for GitHub."""

    def name(self) -> str:
        return "github"

    async def collect(self, request) -> ConnectorResult:  # noqa: ANN001
        now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
        items = [
            NewsItem(
                source=SourceKind.GITHUB,
                source_id="fake-github-1",
                url="https://example.com/fake-github",
                title="Fake GitHub repo",
                collected_at=now,
                stars_or_views=1280,
                language="Python",
                source_evidence={
                    "owner_name": "demo-org",
                    "owner_type": "organisation",
                    "owner_profile_url": "https://github.com/demo-org",
                    "owner_avatar_url": "https://avatars.example.com/demo-org.png",
                    "preview_image_url": "https://opengraph.example.com/fake-github.png",
                    "stars_today": 42,
                },
            ),
            NewsItem(
                source=SourceKind.GITHUB,
                source_id="fake-github-2",
                url="https://example.com/fake-github-2",
                title="Fake GitHub agent toolkit",
                collected_at=now,
                stars_or_views=97,
                language="TypeScript",
                source_evidence={
                    "owner_name": "octocat",
                    "owner_type": "person",
                    "owner_profile_url": "https://github.com/octocat",
                },
            ),
            NewsItem(
                source=SourceKind.GITHUB,
                source_id="fake-github-3",
                url="https://example.com/fake-github-3",
                title="Fake GitHub notebook",
                collected_at=now,
            ),
        ]
        return ConnectorResult(items=items, warnings=[], raw_count=len(items))


class FakeBilibiliConnector:
    """Deterministic offline stand-in for Bilibili."""

    def name(self) -> str:
        return "bilibili"

    async def collect(self, request) -> ConnectorResult:  # noqa: ANN001
        return ConnectorResult(items=[], warnings=[], raw_count=0)


class FakeJuyaConnector:
    """Deterministic offline stand-in for Juya."""

    def name(self) -> str:
        return "juya"

    async def collect(self, request) -> ConnectorResult:  # noqa: ANN001
        now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
        if getattr(request, "juya_item_mode", None) == "stories":
            issue_id = "fake-juya-issue-1"
            issue_url = "https://daily.juya.uk/fake-juya"
            stories = []
            for number, title in (
                (1, "Fake Juya story one"),
                (2, "Fake Juya story two"),
            ):
                stories.append(
                    NewsItem(
                        source=SourceKind.JUYA,
                        source_id=f"juya-story-{issue_id}-{number}",
                        url=f"{issue_url}#story-{number}",
                        title=title,
                        collected_at=now,
                        raw_snippet=f"Evidence for {title}",
                        tags=["juya", "juya-story"],
                        source_evidence={
                            "juya_item_type": "story",
                            "story_number": number,
                            "story_section": "要闻",
                            "story_identity": f"{issue_id}:{number}",
                            "issue_id": issue_id,
                            "issue_url": issue_url,
                            "issue_date": "2026-05-18",
                            "issue_cover_url": "https://assets.juya.uk/cover/fake.png",
                        },
                    )
                )
            return ConnectorResult(items=stories, warnings=[], raw_count=len(stories))

        item = NewsItem(
            source=SourceKind.JUYA,
            source_id="fake-juya-1",
            url="https://daily.juya.uk/fake-juya",
            title="Fake Juya bulletin",
            collected_at=now,
            source_evidence={
                "juya_item_type": "issue",
                "issue_id": "fake-juya-1",
                "issue_url": "https://daily.juya.uk/fake-juya",
                "issue_date": "2026-05-18",
                "issue_cover_url": "https://assets.example.com/juya/fake-cover.png",
                "issue_lead_title": "Fake Juya lead headline",
            },
        )
        return ConnectorResult(items=[item], warnings=[], raw_count=1)


class FakeHuggingFaceConnector:
    """Deterministic offline stand-in for Hugging Face."""

    def name(self) -> str:
        return "huggingface"

    async def collect(self, request) -> ConnectorResult:  # noqa: ANN001
        now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
        items = [
            NewsItem(
                source=SourceKind.HUGGINGFACE,
                source_id="fake-huggingface-1",
                url="https://huggingface.co/fake-model",
                title="Fake Hugging Face model",
                collected_at=now,
                source_evidence={
                    "owner_name": "demo-org",
                    "owner_type": "organisation",
                    "owner_profile_url": "https://huggingface.co/demo-org",
                    "base_model": "meta-llama/Llama-3.1-8B",
                    "pipeline_tag": "text-generation",
                    "downloads_30d": 1234,
                    "likes": 56,
                },
            ),
            NewsItem(
                source=SourceKind.HUGGINGFACE,
                source_id="fake-huggingface-2",
                url="https://huggingface.co/fake-model-2",
                title="Fake Hugging Face quantized model",
                collected_at=now,
            ),
        ]
        return ConnectorResult(items=items, warnings=[], raw_count=len(items))


class FakeZhihuConnector:
    """Deterministic offline stand-in for Zhihu."""

    def name(self) -> str:
        return "zhihu"

    async def collect(self, request) -> ConnectorResult:  # noqa: ANN001
        now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC)
        item = NewsItem(
            source=SourceKind.ZHIHU,
            source_id="fake-zhihu-1",
            url="https://www.zhihu.com/question/fake-zhihu",
            title="Fake Zhihu insight",
            collected_at=now,
        )
        return ConnectorResult(items=[item], warnings=[], raw_count=1)


class FakeOpenRouterConnector:
    """Deterministic offline stand-in for OpenRouter."""

    def name(self) -> str:
        return "openrouter"

    async def collect(self, request) -> ConnectorResult:  # noqa: ANN001
        now = datetime.now(UTC)
        published = now - timedelta(hours=2)
        free_item = NewsItem(
            source=SourceKind.OPENROUTER,
            source_id="vendor/free-model:free",
            url="https://openrouter.ai/vendor/free-model:free",
            title="Fake free OpenRouter model",
            published_at=published,
            collected_at=now,
            source_evidence={
                "free_token_pricing": True,
                "prompt_price_per_million": "0",
                "completion_price_per_million": "0",
            },
        )
        priced_item = NewsItem(
            source=SourceKind.OPENROUTER,
            source_id="vendor/paid-model",
            url="https://openrouter.ai/vendor/paid-model",
            title="Fake priced OpenRouter model",
            published_at=published,
            collected_at=now,
            source_evidence={
                "free_token_pricing": False,
                "prompt_price_per_million": "0.12",
                "completion_price_per_million": "0.25",
            },
        )
        return ConnectorResult(items=[free_item, priced_item], warnings=[], raw_count=2)


def parse_sources_csv(value: str | None) -> list[str]:
    if value is None or value.strip() == "":
        return []
    return [part.strip().lower() for part in value.split(",") if part.strip()]


def normalize_source_names(names: Sequence[str]) -> list[str]:
    """Validate and dedupe source names, preserving order."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = str(raw).strip().lower()
        if not name:
            continue
        if name not in ALLOWED_SOURCES:
            raise ValueError(
                f"Unknown source {name!r}; allowed: {', '.join(sorted(ALLOWED_SOURCES))}"
            )
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    if not out:
        raise ValueError("At least one source must be selected")
    return out


_BILIBILI_CREDENTIAL_NAMES: tuple[str, ...] = (
    "BILIBILI_SESSDATA",
    "BILIBILI_BILI_JCT",
    "BILIBILI_BUVID3",
)


class _BlockedConnector:
    """Connector placeholder when a saved credential override is unreadable."""

    def __init__(self, source_name: str) -> None:
        self._source_name = source_name

    def name(self) -> str:
        return self._source_name

    async def collect(self, request: ConnectorRequest) -> ConnectorResult:  # noqa: ARG002
        return ConnectorResult(
            items=[],
            warnings=[
                ConnectorWarning(
                    connector=self._source_name,
                    code="credential_unreadable",
                    message=(
                        f"{self._source_name} credentials are unreadable; "
                        "restore AI_NEWS_AGENT_SECRET_KEY or replace the override in Settings."
                    ),
                )
            ],
            raw_count=0,
        )


def build_bilibili_credential(provider: CredentialsProvider) -> tuple[str | None, object | None]:
    """Return ``(status, Credential)`` where status is unreadable, ok, or unset."""
    from bilibili_api import Credential

    parts = [provider.resolve(name) for name in _BILIBILI_CREDENTIAL_NAMES]
    if any(part.status == "unreadable" for part in parts):
        return "unreadable", None
    if all(part.status == "unset" for part in parts):
        return "unset", None
    sess = parts[0].value or ""
    jct = parts[1].value or ""
    buvid = parts[2].value or ""
    if not sess and not jct and not buvid:
        return "unset", None
    return "ok", Credential(sessdata=sess, bili_jct=jct, buvid3=buvid)


def _connector_for_name(
    name: str,
    *,
    fake: bool,
    credentials: CredentialsProvider | None,
) -> SourceConnector:
    if fake:
        fake_map: dict[str, SourceConnector] = {
            "juya": FakeJuyaConnector(),
            "github": FakeGitHubConnector(),
            "bilibili": FakeBilibiliConnector(),
            "huggingface": FakeHuggingFaceConnector(),
            "openrouter": FakeOpenRouterConnector(),
            "zhihu": FakeZhihuConnector(),
        }
        return fake_map[name]

    if credentials is None:
        live_map: dict[str, SourceConnector] = {
            "juya": JuyaConnector(),
            "github": GitHubConnector(preview_enrichment=True, trending_enrichment=True),
            "bilibili": BilibiliConnector(),
            "huggingface": HuggingFaceConnector(owner_enrichment=True),
            "openrouter": OpenRouterConnector(),
            "zhihu": ZhihuConnector(),
        }
        return live_map[name]

    if name == "github":
        resolved = credentials.resolve("GITHUB_TOKEN")
        if resolved.status == "unreadable":
            return _BlockedConnector("github")
        return GitHubConnector(
            preview_enrichment=True,
            trending_enrichment=True,
            token=resolved.value,
        )
    if name == "huggingface":
        resolved = credentials.resolve("HUGGINGFACE_TOKEN")
        if resolved.status == "unreadable":
            return _BlockedConnector("huggingface")
        return HuggingFaceConnector(owner_enrichment=True, token=resolved.value)
    if name == "zhihu":
        resolved = credentials.resolve("ZHIHU_ACCESS_SECRET")
        if resolved.status == "unreadable":
            return _BlockedConnector("zhihu")
        return ZhihuConnector(token=resolved.value)
    if name == "bilibili":
        status, cred = build_bilibili_credential(credentials)
        if status == "unreadable":
            return _BlockedConnector("bilibili")
        if status == "unset" or cred is None:
            return BilibiliConnector()
        return BilibiliConnector(credential=cred)
    if name == "openrouter":
        return OpenRouterConnector()
    return JuyaConnector()


def build_connectors(
    *,
    fake: bool,
    names: Sequence[str],
    credentials: CredentialsProvider | None = None,
) -> list[SourceConnector]:
    """Return ordered connectors matching ``names``."""
    selected = normalize_source_names(names)
    return [_connector_for_name(name, fake=fake, credentials=credentials) for name in selected]


def resolve_connector_names(connector_names: list[str] | None) -> list[str]:
    if connector_names is None:
        return list(DEFAULT_SOURCE_NAMES)
    return list(connector_names)


def build_connector_factory(
    *,
    fake: bool,
    name: str,
    credentials: CredentialsProvider | None = None,
) -> Callable[[], SourceConnector]:
    """Return a zero-arg factory that builds a fresh connector per call."""
    validated = normalize_source_names([name])[0]

    def _factory() -> SourceConnector:
        return build_connectors(
            fake=fake,
            names=[validated],
            credentials=credentials,
        )[0]

    return _factory


__all__ = [
    "ALLOWED_SOURCES",
    "DEFAULT_SOURCE_NAMES",
    "FakeBilibiliConnector",
    "FakeDigestModel",
    "FakeGitHubConnector",
    "FakeHuggingFaceConnector",
    "FakeJuyaConnector",
    "FakeOpenRouterConnector",
    "FakeZhihuConnector",
    "build_connector_factory",
    "build_connectors",
    "normalize_source_names",
    "parse_sources_csv",
    "resolve_connector_names",
]
