"""Turn Hugging Face model-card README text into a readable Markdown excerpt."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

__all__ = ["normalize_model_card_snippet"]

_SKIP_TAGS = frozenset({"script", "style", "svg", "iframe", "video", "noscript", "canvas"})
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class _CardHtmlParser(HTMLParser):
    """Unwrap model-card layout HTML into Markdown, including specification tables."""

    def __init__(self, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._source_url = source_url
        self._out: list[str] = []
        self._skip_depth = 0
        self._literal_depth = 0
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._link_href: str | None = None
        self._link_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self._literal_depth:
            self._write(self.get_starttag_text() or f"<{tag}>")
            if tag in {"code", "pre"}:
                self._literal_depth += 1
            return
        if self._skip_depth:
            self._skip_depth += 1
            return
        if tag in _SKIP_TAGS:
            self._skip_depth = 1
            return
        if tag in {"code", "pre"}:
            self._literal_depth = 1
            self._write(f"<{tag}>")
            return
        if tag == "img":
            return
        if tag == "a":
            self._link_href = _attr(attrs, "href") or ""
            self._link_parts = []
            return
        if tag == "br":
            self._write("\n")
            return
        if tag in {"strong", "b"}:
            self._write("**")
            return
        if tag in {"em", "i"}:
            self._write("*")
            return
        if tag == "table":
            self._table = []
            return
        if tag == "tr" and self._table is not None:
            self._row = []
            return
        if tag in {"td", "th"} and self._row is not None:
            self._cell = []
            return
        if tag in _HEADINGS:
            self._write("\n\n" + ("#" * _HEADINGS[tag]) + " ")
            return
        if tag == "p":
            self._write("\n\n")
            return
        if tag == "li":
            self._write("\n- ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._literal_depth:
            self._write(f"</{tag}>")
            if tag in {"code", "pre"}:
                self._literal_depth -= 1
            return
        if self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "a" and self._link_href is not None:
            self._finish_link()
            return
        if tag in {"strong", "b"}:
            self._write("**")
            return
        if tag in {"em", "i"}:
            self._write("*")
            return
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(_clean_cell("".join(self._cell)))
            self._cell = None
            return
        if tag == "tr" and self._row is not None and self._table is not None:
            if any(cell for cell in self._row):
                self._table.append(self._row)
            self._row = None
            return
        if tag == "table" and self._table is not None:
            rendered = _render_table(self._table)
            self._table = None
            if rendered:
                self._out.append(f"\n\n{rendered}\n\n")
            return
        if tag in _HEADINGS or tag == "p":
            self._write("\n\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not data:
            return
        self._write(data)

    def _write(self, text: str) -> None:
        if self._link_href is not None:
            self._link_parts.append(text)
            return
        if self._cell is not None:
            self._cell.append(text)
        else:
            self._out.append(text)

    def _finish_link(self) -> None:
        label = re.sub(r"\s+", " ", "".join(self._link_parts)).strip()
        href = self._link_href or ""
        self._link_href = None
        self._link_parts = []
        if not label:
            return
        destination = _safe_http_url(href, self._source_url)
        rendered = f"[{label}]({destination})" if destination else label
        self._write(rendered)

    def markdown(self) -> str:
        return "".join(self._out)


def normalize_model_card_snippet(
    text: str,
    *,
    source_url: str,
    max_chars: int = 4000,
) -> str:
    """Return readable Markdown for a model-card README."""
    body = _strip_yaml_frontmatter(text)
    body = _drop_unfinished_trailing_tag(body)
    if not body:
        return ""
    masked, literals = _mask_markdown_code(body)
    parser = _CardHtmlParser(source_url)
    parser.feed(masked)
    parser.close()
    rendered = _restore_markdown_code(parser.markdown(), literals)
    cleaned = re.sub(r"[ \t]+\n", "\n", rendered)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return _bound_excerpt(cleaned, source_url=source_url, max_chars=max_chars)


_NOTICE = "Excerpt shortened. Read the full model card."


def _bound_excerpt(text: str, *, source_url: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    card_target = "README.md" if "huggingface.co/" in source_url else ""
    link = _safe_http_url(card_target, source_url)
    notice = f"[{_NOTICE}]({link})" if link else _NOTICE
    budget = max_chars - len(notice) - 2
    if budget < 1:
        return notice[:max_chars]
    blocks = re.split(r"\n\n+", text)
    kept: list[str] = []
    used = 0
    for block in blocks:
        separator = 2 if kept else 0
        if used + separator + len(block) <= budget:
            kept.append(block)
            used += separator + len(block)
            continue
        if not kept:
            kept.append(_shorten_block(block, budget))
        break
    body = "\n\n".join(part for part in kept if part).strip()
    if not body:
        return notice[:max_chars]
    return f"{body}\n\n{notice}"


def _shorten_block(block: str, budget: int) -> str:
    if block.startswith("```") or block.startswith("|"):
        return ""
    words = block.split()
    if len(words) == 1 and len(words[0]) > budget:
        return words[0][:budget]
    kept: list[str] = []
    used = 0
    for word in words:
        extra = len(word) + (1 if kept else 0)
        if used + extra > budget:
            break
        kept.append(word)
        used += extra
    return " ".join(kept)


def _drop_unfinished_trailing_tag(text: str) -> str:
    start = text.rfind("<")
    if start == -1 or ">" in text[start:]:
        return text
    return text[:start].rstrip()


def _strip_yaml_frontmatter(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("---"):
        return stripped
    match = re.match(r"---\r?\n.*?\r?\n---(?:\r?\n)?", stripped, flags=re.DOTALL)
    if match is None:
        return stripped
    return stripped[match.end() :].strip()


def _mask_markdown_code(text: str) -> tuple[str, list[str]]:
    literals: list[str] = []

    def _store(match: re.Match[str]) -> str:
        literals.append(match.group(0))
        return f"\x00CODE{len(literals) - 1}\x00"

    masked = re.sub(r"```.*?```", _store, text, flags=re.DOTALL)
    masked = re.sub(r"`[^`\n]+`", _store, masked)
    return masked, literals


def _restore_markdown_code(text: str, literals: list[str]) -> str:
    restored = text
    for index, literal in enumerate(literals):
        restored = restored.replace(f"\x00CODE{index}\x00", literal)
    return restored


def _attr(attrs: list[tuple[str, str | None]], wanted: str) -> str | None:
    for name, value in attrs:
        if name == wanted:
            return value
    return None


def _safe_http_url(href: str, source_url: str) -> str | None:
    base = source_url
    if "huggingface.co/" in source_url and "/blob/" not in source_url:
        base = source_url.rstrip("/") + "/blob/main/"
    elif not source_url.endswith("/"):
        base = f"{source_url}/"
    resolved = urljoin(base, href.strip())
    parsed = urlparse(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if "img.shields.io" in parsed.netloc.lower():
        return None
    return resolved


def _clean_cell(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().replace("|", r"\|")


def _render_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]

    def _line(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    lines = [
        _line(padded[0]),
        "| " + " | ".join("---" for _ in range(width)) + " |",
    ]
    lines.extend(_line(row) for row in padded[1:])
    return "\n".join(lines)
