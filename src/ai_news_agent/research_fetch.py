"""Bounded fetch and extraction of one authorized research source (R4).

Every hop is authorized by ``authorize_research_url`` before DNS, and a
connection is only ever made to an address this module has validated as
public. Candidate links are reported, never fetched.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

from ai_news_agent.research_evidence import ResearchObservation, ResearchPassage
from ai_news_agent.research_scope import (
    ApprovedResearchScope,
    ResearchAuthorization,
    ResearchScopeEntry,
    authorize_research_url,
)
from ai_news_agent.tools.schemas import ToolObservationStatus

Resolver = Callable[[str, int], Awaitable[list[str]]]

_MAX_REDIRECTS = 3
_MAX_RESPONSE_BYTES = 512_000
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_SUPPORTED_MEDIA_TYPES = frozenset({"text/html", "text/markdown", "text/plain"})
_SUPPORTED_CHARSETS = frozenset(
    {"", "utf-8", "utf8", "ascii", "us-ascii", "latin-1", "iso-8859-1"}
)

_SKIP_TAGS = frozenset(
    {"script", "style", "template", "head", "title", "noscript", "svg"}
)
_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
)
_MAX_CANDIDATES = 16
_MAX_CANDIDATE_LENGTH = 1024
_MAX_PASSAGE_CHARS = 1_500
_MAX_TOTAL_TEXT = 12_000
_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)")


class _RedirectRejected(Exception):
    """A redirect target that cannot be turned into a URL."""


async def fetch_research_source(
    entry: ResearchScopeEntry,
    url: str,
    approved_scopes: list[ApprovedResearchScope],
    *,
    timeout_seconds: float = 5.0,
    resolve: Resolver | None = None,
    network_backend: httpcore.AsyncNetworkBackend | None = None,
) -> ResearchObservation:
    """Fetch one URL and return a research observation, or a limitation."""
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    try:
        async with asyncio.timeout(timeout_seconds):
            return await _fetch(entry, url, approved_scopes, resolve, network_backend)
    except TimeoutError:
        return _failed(url)


async def _fetch(
    entry: ResearchScopeEntry,
    url: str,
    approved_scopes: list[ApprovedResearchScope],
    resolve: Resolver | None,
    network_backend: httpcore.AsyncNetworkBackend | None,
) -> ResearchObservation:
    """The fetch itself, bounded by the caller's deadline."""
    authorization = authorize_research_url(entry, url, approved_scopes)
    response: httpx.Response | None = None
    client: httpx.AsyncClient | None = None
    for _ in range(_MAX_REDIRECTS + 1):
        if authorization.decision != "allow" or authorization.url is None:
            return _refused(url)
        try:
            addresses = await _resolve(authorization, resolve)
        except OSError:
            return _failed(url)
        if addresses is None:
            return _refused(url)
        try:
            response, client = await _pinned_get(
                authorization.url, addresses[0], network_backend
            )
        except (httpx.HTTPError, _RedirectRejected):
            return _failed(url)
        if response.status_code not in _REDIRECT_STATUSES:
            break
        redirect = _redirect_target(response, authorization.url)
        await _close_hop(response, client)
        if redirect is None:
            return _failed(url)
        authorization = authorize_research_url(entry, redirect, approved_scopes)
    else:
        return _failed(url)
    assert response is not None and client is not None
    if response.status_code != 200:
        await _close_hop(response, client)
        if response.is_client_error:
            return _limited(
                url,
                "inaccessible",
                "The source refused access.",
                final_url=authorization.url,
                caveat=f"The source returned HTTP {response.status_code}.",
            )
        return _limited(
            url,
            "failed",
            "The source returned no usable response.",
            final_url=authorization.url,
            caveat=f"Unexpected HTTP {response.status_code}.",
        )
    media_type, charset = _content_type(response.headers.get("content-type", ""))
    body = await _capped_body(response, client)
    if body is None:
        return _limited(
            url,
            "retrieved",
            "The source is larger than the response cap.",
            final_url=authorization.url,
            caveat="The response exceeded the size cap and was not kept.",
        )
    text, completeness, caveat = _decode_supported(response, body, media_type, charset)
    if text is None:
        return _limited(
            url,
            "retrieved",
            "The source could not be extracted as text.",
            final_url=authorization.url,
            caveat=caveat,
            completeness=completeness,
        )
    blocks, candidates, truncated, clipped = _extract(
        media_type, text, authorization.url or url
    )
    caveats: list[str] = []
    if truncated:
        caveats.append("Text was clipped to the per-document limit.")
    if clipped:
        caveats.append("Only the first candidate links are listed.")
    return _retrieved(
        url,
        authorization,
        blocks,
        candidates,
        "truncated" if truncated else "complete",
        caveats,
    )


def _limited(
    url: str,
    outcome: str,
    summary: str,
    *,
    final_url: str | None = None,
    caveat: str | None = None,
    completeness: str = "unsuccessful",
) -> ResearchObservation:
    return ResearchObservation(
        status=ToolObservationStatus.ERROR,
        summary=summary,
        requested_url=url,
        final_url=final_url,
        evidence_id=f"{outcome}:{final_url or url}",
        retrieval_outcome=outcome,
        extraction_completeness=completeness,
        fresh=False,
        caveats=[caveat] if caveat else [],
    )


def _retrieved(
    url: str,
    authorization: ResearchAuthorization,
    blocks: list[str],
    candidates: list[str],
    completeness: str,
    caveats: list[str],
) -> ResearchObservation:
    evidence_id = _evidence_id(authorization.url or url, blocks)
    return ResearchObservation(
        status=ToolObservationStatus.OK,
        summary="Read the source.",
        requested_url=url,
        final_url=authorization.url,
        evidence_id=evidence_id,
        retrieval_outcome="retrieved",
        extraction_completeness=completeness,
        publisher=authorization.publisher,
        relationship=authorization.relationship,
        approved_scope=authorization.scope,
        retrieved_at=datetime.now(UTC),
        fresh=True,
        passages=[
            ResearchPassage(passage_id=f"{evidence_id}:p{index}", text=text)
            for index, text in enumerate(blocks, start=1)
        ],
        candidate_links=candidates,
        caveats=caveats,
    )


def _evidence_id(final_url: str, blocks: list[str]) -> str:
    """Versioned content identity: final URL plus the emitted passages.

    The clock is deliberately excluded, so the same source text at the same
    final URL keeps the same ids, while changed text or a different final URL
    does not.
    """
    digest = hashlib.sha256(final_url.encode("utf-8"))
    for block in blocks:
        digest.update(b"\x00")
        digest.update(block.encode("utf-8"))
    return f"ev1-{digest.hexdigest()}"


def _extract(
    media_type: str,
    text: str,
    base_url: str,
) -> tuple[list[str], list[str], bool, bool]:
    """Return bounded blocks, candidates, text truncation, and link clipping."""
    if media_type == "text/html":
        parser = _TextExtractor()
        parser.feed(text)
        parser.close()
        raw_blocks = parser.blocks
        links = parser.links
    else:
        raw_blocks = [_normalize(block) for block in re.split(r"\n\s*\n", text)]
        raw_blocks = [block for block in raw_blocks if block]
        links = _MARKDOWN_LINK.findall(text)
    candidates, clipped = _candidates(links, base_url)
    blocks, truncated = _bounded_blocks(raw_blocks)
    return blocks, candidates, truncated, clipped


def _bounded_blocks(blocks: list[str]) -> tuple[list[str], bool]:
    """Split long blocks and stop at the per-document text limit."""
    bounded: list[str] = []
    used = 0
    for block in blocks:
        for piece in _split_block(block):
            if used + len(piece) > _MAX_TOTAL_TEXT:
                return bounded, True
            bounded.append(piece)
            used += len(piece)
    return bounded, False


def _split_block(text: str) -> list[str]:
    """Break one block into passages of at most the passage limit."""
    pieces: list[str] = []
    remaining = text
    while len(remaining) > _MAX_PASSAGE_CHARS:
        cut = remaining.rfind(" ", 0, _MAX_PASSAGE_CHARS + 1)
        if cut <= 0:
            cut = _MAX_PASSAGE_CHARS
        pieces.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        pieces.append(remaining)
    return [piece for piece in pieces if piece]


class _TextExtractor(HTMLParser):
    """Collect visible text blocks and anchors; never honor ``base``."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.links: list[str] = []
        self._buffer: list[str] = []
        self._skip_depth = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.lower()
        if self._skip_depth:
            if tag in _SKIP_TAGS:
                self._skip_depth += 1
            return
        if tag in _SKIP_TAGS:
            self._skip_depth = 1
            return
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href.strip())
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        if not self._skip_depth and tag.lower() in _BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip_depth:
            if tag in _SKIP_TAGS:
                self._skip_depth -= 1
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._buffer.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        text = _normalize("".join(self._buffer))
        self._buffer = []
        if text:
            self.blocks.append(text)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _candidates(links: list[str], base_url: str) -> tuple[list[str], bool]:
    """Resolve and bound unfetched HTTPS candidates, in document order."""
    seen: list[str] = []
    clipped = False
    for link in links:
        try:
            resolved = urljoin(base_url, link)
            parts = urlsplit(resolved)
        except ValueError:
            continue
        if parts.scheme != "https" or not parts.hostname:
            continue
        if parts.username is not None or parts.password is not None:
            continue
        canonical = resolved.split("#", 1)[0]
        if canonical in seen:
            continue
        if len(canonical) > _MAX_CANDIDATE_LENGTH:
            clipped = True
            continue
        if len(seen) >= _MAX_CANDIDATES:
            clipped = True
            continue
        seen.append(canonical)
    return seen, clipped


def _content_type(header: str) -> tuple[str, str]:
    """Split a ``Content-Type`` header into media type and normalized charset."""
    media_type, *params = header.split(";")
    charset = ""
    for param in params:
        name, _, value = param.partition("=")
        if name.strip().lower() == "charset":
            charset = value.strip().strip('"').lower()
    return media_type.strip().lower(), charset


def _decode_supported(
    response: httpx.Response,
    body: bytes,
    media_type: str,
    charset: str,
) -> tuple[str | None, str, str | None]:
    """Admit only supported text documents; never sniff binary as text."""
    encoding = response.headers.get("content-encoding", "").strip().lower()
    if encoding not in ("", "identity"):
        return None, "unsupported", "The response used an unsupported content encoding."
    if media_type not in _SUPPORTED_MEDIA_TYPES:
        return None, "unsupported", "The response is not a supported text document."
    if charset not in _SUPPORTED_CHARSETS:
        return None, "unsupported", "The response declared an unsupported charset."
    try:
        return body.decode(charset or "utf-8"), "complete", None
    except UnicodeDecodeError:
        return None, "unsuccessful", "The response body was not valid text."


def _refused(url: str) -> ResearchObservation:
    return _limited(url, "refused", "The source was refused before any request.")


def _failed(url: str) -> ResearchObservation:
    return _limited(
        url,
        "failed",
        "The source could not be retrieved.",
        caveat="The source could not be reached or did not answer usefully.",
    )


async def _resolve(
    authorization: ResearchAuthorization,
    resolve: Resolver | None,
) -> list[str] | None:
    """Resolve one authorized URL, refusing unless every answer is public."""
    parts = urlsplit(authorization.url or "")
    port = parts.port or 443
    host = parts.hostname or ""
    answers = (
        await _default_resolve(host, port)
        if resolve is None
        else await resolve(host, port)
    )
    validated: list[str] = []
    for answer in answers:
        address = _public_address(answer)
        if address is None:
            return None
        validated.append(address)
    return validated or None


async def _close_hop(response: httpx.Response, client: httpx.AsyncClient) -> None:
    """Release one hop's connection and the client that opened it."""
    await response.aclose()
    await client.aclose()


async def _capped_body(
    response: httpx.Response,
    client: httpx.AsyncClient,
) -> bytes | None:
    """Read the raw body, keeping it only while it stays within the cap.

    The read stops as soon as one more byte would overflow, and the connection
    is closed without decoding. A declared content length is never trusted.
    """
    body = bytearray()
    try:
        async for chunk in response.aiter_raw():
            if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
                return None
            body.extend(chunk)
        return bytes(body)
    finally:
        await _close_hop(response, client)


def _redirect_target(response: httpx.Response, current_url: str) -> str | None:
    """Resolve a redirect against the authorized URL, never the dialed address.

    The request is sent to a numeric IP, so HTTPX's own resolution of a relative
    ``Location`` would point the next hop at that IP and drop the real hostname.
    """
    if not response.has_redirect_location:
        return None
    location = response.headers.get("location")
    if not location:
        return None
    return urljoin(current_url, location)


async def _pinned_get(
    canonical_url: str,
    address: str,
    network_backend: httpcore.AsyncNetworkBackend | None,
) -> tuple[httpx.Response, httpx.AsyncClient]:
    """GET one authorized URL through a connection to its vetted address.

    The request URL carries the numeric address, so that is what the transport
    dials. The original hostname stays in the ``Host`` header and in the TLS
    handshake, which is what the certificate is checked against.
    """
    parts = urlsplit(canonical_url)
    port = parts.port or 443
    dial_host = f"[{address}]" if ":" in address else address
    query = f"?{parts.query}" if parts.query else ""
    dial_url = f"https://{dial_host}:{port}{parts.path}{query}"
    authority = parts.netloc
    transport = httpx.AsyncHTTPTransport(
        verify=True,
        trust_env=False,
        retries=0,
        http2=False,
    )
    if network_backend is not None:
        transport._pool._network_backend = network_backend  # type: ignore[attr-defined]
    client = httpx.AsyncClient(transport=transport, trust_env=False)
    try:
        response = await client.send(
            client.build_request(
                "GET",
                dial_url,
                headers={"host": authority, "accept-encoding": "identity"},
                extensions={"sni_hostname": parts.hostname},
            ),
            stream=True,
        )
    except httpx.InvalidURL as exc:
        await client.aclose()
        raise _RedirectRejected() from exc
    except BaseException:
        await client.aclose()
        raise
    return response, client


async def _default_resolve(host: str, port: int) -> list[str]:
    """Resolve through the platform resolver without blocking the loop."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def _public_address(answer: str) -> str | None:
    """Return the canonical text of one globally routable address, else ``None``.

    Scoped IPv6 and IPv4-mapped forms are refused outright: a mapped address can
    hide a private IPv4 destination inside an address that looks global.
    """
    if "%" in answer:
        return None
    try:
        address = ipaddress.ip_address(answer)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return None
    if not address.is_global or address.is_multicast:
        return None
    return str(address)


__all__ = ["fetch_research_source"]
