"""Bounded fetch of one authorized research source (research plan R4)."""

from __future__ import annotations

import asyncio
import ssl

import httpcore
from httpcore._backends.base import AsyncNetworkBackend, AsyncNetworkStream

from ai_news_agent.models import SourceKind
from ai_news_agent.research_scope import (
    ApprovedResearchScope,
    ResearchScopeEntry,
)
from ai_news_agent.tools.schemas import ToolObservationStatus


def _entry(
    *,
    source_url: str = "https://github.com/acme/widget",
) -> ResearchScopeEntry:
    return ResearchScopeEntry(
        source_kind=SourceKind.GITHUB,
        source_id="acme/widget",
        source_url=source_url,
        subject_id="acme/widget",
    )


def _developer_scope() -> ApprovedResearchScope:
    return ApprovedResearchScope(
        source_kind=SourceKind.GITHUB,
        source_id="acme/widget",
        subject_id="acme/widget",
        publisher="Acme developer docs",
        relationship="original_developer",
        entry_point="https://acme.example/docs/widget/install",
        project_path="/docs/widget",
    )


def test_denied_or_unverified_url_refuses_without_resolving() -> None:
    from ai_news_agent.research_fetch import fetch_research_source

    resolved: list[str] = []

    async def resolver(host: str, port: int) -> list[str]:
        resolved.append(host)
        return ["1.1.1.1"]

    async def scenario() -> None:
        for url in (
            "https://github.com/someone/else",
            "https://mirror.example/docs/widget/install",
        ):
            observation = await fetch_research_source(
                _entry(),
                url,
                [_developer_scope()],
                resolve=resolver,
            )
            assert observation.status == ToolObservationStatus.ERROR
            assert observation.retrieval_outcome == "refused"
            assert observation.extraction_completeness == "unsuccessful"
            assert observation.fresh is False
            assert observation.passages == []
            assert observation.final_url is None
            assert observation.retrieved_at is None
            assert observation.evidence_id
            assert observation.summary.strip()

    asyncio.run(scenario())
    assert resolved == []


def test_unsafe_resolution_is_refused_before_any_connection() -> None:
    from ai_news_agent.research_fetch import fetch_research_source

    answers = {
        "loopback.example": ["127.0.0.1"],
        "lan.example": ["10.1.2.3"],
        "linklocal.example": ["169.254.169.254"],
        "multicast.example": ["224.0.0.1"],
        "mixed.example": ["1.1.1.1", "192.168.0.9"],
        "mapped.example": ["::ffff:127.0.0.1"],
        "scoped.example": ["fe80::1%12"],
        "empty.example": [],
    }
    backend = _PinnedBackend()

    async def resolver(host: str, port: int) -> list[str]:
        return answers[host]

    async def scenario() -> None:
        for host in answers:
            observation = await fetch_research_source(
                _entry(source_url=f"https://{host}/acme/widget"),
                f"https://{host}/acme/widget",
                [],
                resolve=resolver,
                network_backend=backend,
            )
            assert observation.retrieval_outcome == "refused", host
            assert observation.extraction_completeness == "unsuccessful", host
            assert observation.fresh is False, host
            assert observation.passages == [], host

    asyncio.run(scenario())
    assert backend.dialed == []


class _PinnedStream(AsyncNetworkStream):
    """One fake TLS connection that records how it was opened."""

    body = b"HTTP/1.1 200 OK\r\ncontent-type: text/plain\r\n\r\nRuns on 8 GB."

    def __init__(self, dialed: list[tuple[str, int]]) -> None:
        self._dialed = dialed
        self._body = self.body

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        chunk, self._body = self._body[:max_bytes], self._body[max_bytes:]
        return chunk

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        return None

    async def aclose(self) -> None:
        return None

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> AsyncNetworkStream:
        assert ssl_context.verify_mode == ssl.CERT_REQUIRED
        assert ssl_context.check_hostname is True
        self._dialed.append(("tls", server_hostname))  # type: ignore[arg-type]
        return self

    def get_extra_info(self, info: str) -> object:
        return None


class _PinnedBackend(AsyncNetworkBackend):
    """Records the address HTTPX actually dials, then serves one response."""

    def __init__(self) -> None:
        self.dialed: list[tuple[object, ...]] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object = None,
    ) -> AsyncNetworkStream:
        self.dialed.append(("tcp", host, port))
        return _PinnedStream(self.dialed)

    async def sleep(self, seconds: float) -> None:  # pragma: no cover - retries are off
        raise AssertionError("the pinned request must not retry")


def test_authorized_plain_text_dials_only_the_vetted_address() -> None:
    from ai_news_agent.research_fetch import fetch_research_source

    backend = _PinnedBackend()

    async def resolver(host: str, port: int) -> list[str]:
        assert (host, port) == ("github.com", 443)
        return ["8.8.8.8", "1.1.1.1"]

    async def scenario() -> None:
        observation = await fetch_research_source(
            _entry(),
            "https://github.com/acme/widget#readme",
            [],
            resolve=resolver,
            network_backend=backend,
        )
        assert observation.status == ToolObservationStatus.OK
        assert observation.retrieval_outcome == "retrieved"
        assert observation.extraction_completeness == "complete"
        assert observation.fresh is True
        assert observation.requested_url == "https://github.com/acme/widget#readme"
        assert observation.final_url == "https://github.com/acme/widget"
        assert observation.publisher == "github.com"
        assert observation.relationship == "original_source"
        assert observation.approved_scope is None
        assert observation.retrieved_at is not None
        assert [passage.text for passage in observation.passages] == ["Runs on 8 GB."]

    asyncio.run(scenario())
    assert backend.dialed == [("tcp", "8.8.8.8", 443), ("tls", "github.com")]


class _RedirectBackend(_PinnedBackend):
    """Serves a redirect from the first connection and a document from the next."""

    def __init__(self, location: str) -> None:
        super().__init__()
        self._location = location
        self._responses = [
            (
                b"HTTP/1.1 302 Found\r\nlocation: "
                + location.encode()
                + b"\r\ncontent-length: 0\r\n\r\n"
            ),
            b"HTTP/1.1 200 OK\r\ncontent-type: text/plain\r\n\r\nInstall with 4-bit loading.",
        ]

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object = None,
    ) -> AsyncNetworkStream:
        stream = await super().connect_tcp(host, port, timeout, local_address, socket_options)
        stream._body = self._responses.pop(0)  # type: ignore[attr-defined]
        return stream


def test_redirect_is_reauthorized_and_an_unapproved_target_is_not_contacted() -> None:
    from ai_news_agent.research_fetch import fetch_research_source

    answers = {
        "acme.example": ["1.1.1.1"],
        "mirror.example": ["8.8.8.8"],
        "lan.example": ["10.0.0.5"],
    }

    async def resolver(host: str, port: int) -> list[str]:
        return answers[host]

    async def scenario() -> None:
        entry = _entry(source_url="https://github.com/acme/widget")
        approved = await fetch_research_source(
            entry,
            "https://acme.example/docs/widget/install",
            [_developer_scope()],
            resolve=resolver,
            network_backend=_RedirectBackend("install/gpu"),
        )
        assert approved.retrieval_outcome == "retrieved"
        assert approved.final_url == "https://acme.example/docs/widget/install/gpu"
        assert approved.publisher == "Acme developer docs"
        assert approved.relationship == "original_developer"
        assert approved.approved_scope == _developer_scope()
        assert [passage.text for passage in approved.passages] == [
            "Install with 4-bit loading."
        ]

        for location in ("https://mirror.example/docs/widget/gpu", "https://lan.example/secret"):
            backend = _RedirectBackend(location)
            refused = await fetch_research_source(
                entry,
                "https://acme.example/docs/widget/install",
                [_developer_scope()],
                resolve=resolver,
                network_backend=backend,
            )
            assert refused.retrieval_outcome == "refused", location
            assert refused.final_url is None, location
            assert refused.passages == [], location
            assert [hop[1] for hop in backend.dialed if hop[0] == "tcp"] == ["1.1.1.1"], (
                location
            )

    asyncio.run(scenario())


def _redirect_chain(locations: list[str | None]) -> list[bytes]:
    """One redirect response per location, then a document that must not be read."""
    responses = []
    for location in locations:
        header = b"" if location is None else b"location: " + location.encode() + b"\r\n"
        responses.append(b"HTTP/1.1 302 Found\r\n" + header + b"content-length: 0\r\n\r\n")
    responses.append(b"HTTP/1.1 200 OK\r\ncontent-type: text/plain\r\n\r\nShould not be read.")
    return responses


def test_a_broken_or_too_long_redirect_chain_fails_without_another_request() -> None:
    from ai_news_agent.research_fetch import fetch_research_source

    async def resolver(host: str, port: int) -> list[str]:
        assert host == "acme.example"
        return ["1.1.1.1"]

    chains = {
        "missing location": _redirect_chain([None]),
        "empty location": _redirect_chain([""]),
        "unsupported scheme": _redirect_chain(["javascript:alert(1)"]),
        "too many hops": _redirect_chain(["install"] * 4),
    }

    async def scenario() -> None:
        entry = _entry(source_url="https://github.com/acme/widget")
        for name, responses in chains.items():
            backend = _RedirectBackend("unused")
            backend._responses = responses
            observation = await fetch_research_source(
                entry,
                "https://acme.example/docs/widget/install",
                [_developer_scope()],
                resolve=resolver,
                network_backend=backend,
            )
            assert observation.status == ToolObservationStatus.ERROR, name
            assert observation.retrieval_outcome == "failed", name
            assert observation.extraction_completeness == "unsuccessful", name
            assert observation.passages == [], name
            assert observation.fresh is False, name
            assert len(backend._responses) == 1, name

    asyncio.run(scenario())


class _ChunkedStream(_PinnedStream):
    """Serves one body as several reads, with no Content-Length to trust."""

    chunk_size = 100_000

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        size = min(self.chunk_size, max_bytes, len(self._body))
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk


class _ChunkedBackend(_PinnedBackend):
    def __init__(self, body: bytes) -> None:
        super().__init__()
        self._body = body

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object = None,
    ) -> AsyncNetworkStream:
        self.dialed.append(("tcp", host, port))
        stream = _ChunkedStream(self.dialed)
        stream._body = self._body
        return stream


def _chunked_body(size: int) -> bytes:
    """A chunked response whose decoded body is exactly ``size`` bytes.

    Chunked framing carries its own end, so the reader cannot stop on a
    connection close, and no content length is declared for it to trust.
    """
    header = b"HTTP/1.1 200 OK\r\ncontent-type: text/plain\r\ntransfer-encoding: chunked\r\n\r\n"
    return header + format(size, "x").encode() + b"\r\n" + b"a" * size + b"\r\n0\r\n\r\n"


def test_a_body_past_the_cap_is_dropped_and_the_exact_cap_is_kept() -> None:
    from ai_news_agent.research_fetch import (
        _MAX_RESPONSE_BYTES,
        _MAX_TOTAL_TEXT,
        fetch_research_source,
    )

    async def resolver(host: str, port: int) -> list[str]:
        return ["8.8.8.8"]

    async def scenario() -> None:
        over_cap = await fetch_research_source(
            _entry(),
            "https://github.com/acme/widget",
            [],
            resolve=resolver,
            network_backend=_ChunkedBackend(_chunked_body(_MAX_RESPONSE_BYTES + 1)),
        )
        assert over_cap.retrieval_outcome == "retrieved"
        assert over_cap.extraction_completeness == "unsuccessful"
        assert over_cap.status == ToolObservationStatus.ERROR
        assert over_cap.passages == []
        assert over_cap.caveats

        at_cap = await fetch_research_source(
            _entry(),
            "https://github.com/acme/widget",
            [],
            resolve=resolver,
            network_backend=_ChunkedBackend(_chunked_body(_MAX_RESPONSE_BYTES)),
        )
        assert at_cap.retrieval_outcome == "retrieved"
        assert at_cap.status == ToolObservationStatus.OK
        assert at_cap.passages
        assert at_cap.extraction_completeness == "truncated"
        assert sum(len(passage.text) for passage in at_cap.passages) == _MAX_TOTAL_TEXT

    asyncio.run(scenario())


class _StallingBackend(_PinnedBackend):
    """A connection that records when it closes and never returns data."""

    def __init__(self) -> None:
        super().__init__()
        self.closed = asyncio.Event()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object = None,
    ) -> AsyncNetworkStream:
        stream = _PinnedStream(self.dialed)

        async def read(max_bytes: int, timeout: float | None = None) -> bytes:
            await asyncio.sleep(60)
            return b""

        async def aclose() -> None:
            self.closed.set()

        stream.read = read  # type: ignore[method-assign]
        stream.aclose = aclose  # type: ignore[method-assign]
        return stream


def test_the_deadline_bounds_a_stalled_read_and_cancellation_closes_it() -> None:
    from ai_news_agent.research_fetch import fetch_research_source

    async def resolver(host: str, port: int) -> list[str]:
        return ["8.8.8.8"]

    async def scenario() -> None:
        backend = _StallingBackend()
        started = asyncio.get_running_loop().time()
        observation = await fetch_research_source(
            _entry(),
            "https://github.com/acme/widget",
            [],
            timeout_seconds=0.2,
            resolve=resolver,
            network_backend=backend,
        )
        elapsed = asyncio.get_running_loop().time() - started
        assert observation.retrieval_outcome == "failed"
        assert observation.passages == []
        assert elapsed < 2
        assert backend.closed.is_set()

        cancelling = _StallingBackend()
        task = asyncio.create_task(
            fetch_research_source(
                _entry(),
                "https://github.com/acme/widget",
                [],
                resolve=resolver,
                network_backend=cancelling,
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.wait([task])
        assert task.cancelled()
        assert cancelling.closed.is_set()

    asyncio.run(scenario())


def _typed_body(content_type: str, payload: bytes) -> bytes:
    header = (
        b"HTTP/1.1 200 OK\r\ncontent-type: "
        + content_type.encode()
        + b"\r\ncontent-length: "
        + str(len(payload)).encode()
        + b"\r\n\r\n"
    )
    return header + payload


def test_unsupported_content_and_undecodable_text_are_limitations() -> None:
    from ai_news_agent.research_fetch import fetch_research_source

    async def resolver(host: str, port: int) -> list[str]:
        return ["8.8.8.8"]

    cases = {
        "binary type": (_typed_body("application/pdf", b"%PDF"), "unsupported"),
        "gzip encoding": (
            _typed_body("text/plain", b"hello").replace(
                b"content-length", b"content-encoding: gzip\r\ncontent-length"
            ),
            "unsupported",
        ),
        "declared shift-jis": (
            _typed_body("text/plain; charset=shift_jis", b"hello"),
            "unsupported",
        ),
        "not valid utf-8": (_typed_body("text/plain", b"\xff\xfe"), "unsuccessful"),
    }

    async def scenario() -> None:
        for name, (body, completeness) in cases.items():
            observation = await fetch_research_source(
                _entry(),
                "https://github.com/acme/widget",
                [],
                resolve=resolver,
                network_backend=_ChunkedBackend(body),
            )
            assert observation.retrieval_outcome == "retrieved", name
            assert observation.extraction_completeness == completeness, name
            assert observation.status == ToolObservationStatus.ERROR, name
            assert observation.passages == [], name
            assert observation.caveats, name

    asyncio.run(scenario())


def test_html_and_markdown_yield_readable_passages_and_unfetched_candidates() -> None:
    from ai_news_agent.research_fetch import fetch_research_source

    html = b"""<html><head><title>Install</title><style>.x{}</style>
    <script>ignore()</script><base href="https://evil.example/"></head>
    <body><h1>Install</h1><p>Use <strong>4-bit</strong> loading.</p>
    <ul><li>Step one</li></ul>
    <a href="/docs/widget/gpu">GPU guide</a>
    <a href="https://other.example/x#frag">Other</a>
    <a href="javascript:alert(1)">bad</a>
    <a href="/docs/widget/gpu">duplicate</a>
    <a href="mailto:docs@acme.example">mail</a>
    </body></html>"""

    async def resolver(host: str, port: int) -> list[str]:
        return ["8.8.8.8"]

    async def scenario() -> None:
        backend = _ChunkedBackend(_typed_body("text/html", html))
        observation = await fetch_research_source(
            _entry(),
            "https://github.com/acme/widget",
            [],
            resolve=resolver,
            network_backend=backend,
        )
        readable = " ".join(passage.text for passage in observation.passages)
        assert "Install" in readable
        assert "Use 4-bit loading." in readable
        assert "Step one" in readable
        assert "ignore()" not in readable
        assert ".x{}" not in readable
        assert observation.candidate_links == [
            "https://github.com/docs/widget/gpu",
            "https://other.example/x",
        ]
        assert [hop for hop in backend.dialed if hop[0] == "tcp"] == [
            ("tcp", "8.8.8.8", 443)
        ]

        markdown = b"""# Install

Use **4-bit** loading. See the [GPU guide](/docs/widget/gpu).

    pip install acme
"""
        markdown_backend = _ChunkedBackend(_typed_body("text/markdown", markdown))
        markdown_observation = await fetch_research_source(
            _entry(),
            "https://github.com/acme/widget",
            [],
            resolve=resolver,
            network_backend=markdown_backend,
        )
        markdown_text = " ".join(
            passage.text for passage in markdown_observation.passages
        )
        assert "Use **4-bit** loading." in markdown_text
        assert "pip install acme" in markdown_text
        assert "See the [GPU guide](/docs/widget/gpu)." in markdown_text
        assert markdown_observation.candidate_links == [
            "https://github.com/docs/widget/gpu"
        ]
        assert [hop for hop in markdown_backend.dialed if hop[0] == "tcp"] == [
            ("tcp", "8.8.8.8", 443)
        ]

    asyncio.run(scenario())


def test_long_documents_and_link_lists_are_bounded_and_say_so() -> None:
    from ai_news_agent.research_fetch import (
        _MAX_CANDIDATES,
        _MAX_PASSAGE_CHARS,
        _MAX_TOTAL_TEXT,
        fetch_research_source,
    )

    async def resolver(host: str, port: int) -> list[str]:
        return ["8.8.8.8"]

    async def fetch(body: bytes) -> object:
        return await fetch_research_source(
            _entry(),
            "https://github.com/acme/widget",
            [],
            resolve=resolver,
            network_backend=_ChunkedBackend(_typed_body("text/html", body)),
        )

    async def scenario() -> None:
        one_long_block = await fetch(b"<p>" + b"a" * 4000 + b"</p>")
        assert all(
            len(passage.text) <= _MAX_PASSAGE_CHARS
            for passage in one_long_block.passages
        )
        assert sum(len(passage.text) for passage in one_long_block.passages) == 4000
        assert one_long_block.extraction_completeness == "complete"

        many_blocks = await fetch(
            b"".join(b"<p>word " * 400 + b"</p>" for _ in range(20))
        )
        assert sum(len(passage.text) for passage in many_blocks.passages) <= (
            _MAX_TOTAL_TEXT
        )
        assert many_blocks.passages
        assert many_blocks.extraction_completeness == "truncated"
        assert many_blocks.status == ToolObservationStatus.OK
        assert many_blocks.caveats

        many_links = await fetch(
            b"".join(b'<a href="/docs/widget/page%d">p</a>' % i for i in range(25))
        )
        assert len(many_links.candidate_links) == _MAX_CANDIDATES
        assert many_links.extraction_completeness == "complete"
        assert many_links.caveats

    asyncio.run(scenario())


def test_evidence_and_passage_ids_depend_only_on_content_and_final_url() -> None:
    from ai_news_agent.research_fetch import fetch_research_source

    async def resolver(host: str, port: int) -> list[str]:
        return ["8.8.8.8"]

    async def fetch(url: str, payload: bytes) -> object:
        return await fetch_research_source(
            _entry(source_url=url),
            url,
            [],
            resolve=resolver,
            network_backend=_ChunkedBackend(_typed_body("text/plain", payload)),
        )

    async def scenario() -> None:
        first = b"First paragraph.\n\nSecond paragraph."
        again = await fetch("https://github.com/acme/widget", first)
        repeat = await fetch("https://github.com/acme/widget", first)
        changed = await fetch(
            "https://github.com/acme/widget",
            b"First paragraph.\n\nThird paragraph.",
        )
        moved = await fetch("https://github.com/acme/other", first)

        assert again.evidence_id == repeat.evidence_id
        assert [p.passage_id for p in again.passages] == [
            p.passage_id for p in repeat.passages
        ]
        assert again.evidence_id.startswith("ev1-")

        assert changed.evidence_id != again.evidence_id
        assert [p.passage_id for p in changed.passages] != [
            p.passage_id for p in again.passages
        ]

        assert moved.evidence_id != again.evidence_id

    asyncio.run(scenario())


def test_default_resolver_uses_the_system_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    from ai_news_agent.research_fetch import fetch_research_source

    def fake_getaddrinfo(host: str, port: int, *args: object, **kwargs: object):
        assert host == "github.com"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    backend = _PinnedBackend()

    async def scenario() -> None:
        observation = await fetch_research_source(
            _entry(),
            "https://github.com/acme/widget",
            [],
            network_backend=backend,
        )
        assert observation.retrieval_outcome == "retrieved"
        assert observation.passages

    asyncio.run(scenario())
    assert backend.dialed == [("tcp", "1.1.1.1", 443), ("tls", "github.com")]


class _ExplodingBackend(_PinnedBackend):
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object = None,
    ) -> AsyncNetworkStream:
        raise httpcore.ConnectError("connection refused")


def _status_body(status: str) -> bytes:
    return (
        b"HTTP/1.1 "
        + status.encode()
        + b"\r\ncontent-type: text/plain\r\ncontent-length: 0\r\n\r\n"
    )


def test_http_and_transport_failures_map_to_distinct_limitations() -> None:
    from ai_news_agent.research_fetch import fetch_research_source

    async def resolver(host: str, port: int) -> list[str]:
        return ["8.8.8.8"]

    async def failing_resolver(host: str, port: int) -> list[str]:
        raise OSError("lookup failed")

    async def scenario() -> None:
        url = "https://github.com/acme/widget"
        for status in ("401 Unauthorized", "403 Forbidden", "404 Not Found"):
            observation = await fetch_research_source(
                _entry(),
                url,
                [],
                resolve=resolver,
                network_backend=_ChunkedBackend(_status_body(status)),
            )
            assert observation.retrieval_outcome == "inaccessible", status
            assert observation.extraction_completeness == "unsuccessful", status
            assert observation.status == ToolObservationStatus.ERROR, status
            assert observation.passages == [], status
            assert observation.final_url == url, status
            assert status.split()[0] in observation.caveats[0], status

        for status in ("500 Internal Server Error", "503 Service Unavailable", "206 Partial Content"):
            observation = await fetch_research_source(
                _entry(),
                url,
                [],
                resolve=resolver,
                network_backend=_ChunkedBackend(_status_body(status)),
            )
            assert observation.retrieval_outcome == "failed", status
            assert observation.passages == [], status

        for backend, lookup in (
            (_ExplodingBackend(), resolver),
            (_PinnedBackend(), failing_resolver),
        ):
            observation = await fetch_research_source(
                _entry(),
                url,
                [],
                resolve=lookup,
                network_backend=backend,
            )
            assert observation.retrieval_outcome == "failed"
            assert observation.extraction_completeness == "unsuccessful"
            assert observation.fresh is False
            assert observation.passages == []
            assert observation.final_url is None
            assert observation.caveats

    asyncio.run(scenario())
