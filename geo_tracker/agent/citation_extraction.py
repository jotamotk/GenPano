from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import urlparse


SKIP_DOMAIN_PARTS: tuple[str, ...] = (
    "chatgpt.com",
    "gemini.google.com",
    "accounts.google.com",
    "cdn.oaistatic.com",
    "oaiusercontent.com",
    "cdn-cgi",
    "gstatic.com",
    "googleapis.com",
    "google.com/gsi",
    "statsig",
    "sentry",
    "intercom",
    "cdn.openai.com",
    "openaiassets.blob.core.windows.net",
    "persistent.oaistatic.com",
)

_SOURCE_UI_RE = re.compile(
    r"(?:data-testid|aria-label|title)=['\"][^'\"]*(?:source|sources|citation|citations)[^'\"]*['\"]"
    r"|>\s*(?:Sources|Citations)\s*<",
    re.IGNORECASE,
)
_CHATGPT_ASSISTANT_RE = re.compile(
    r"data-message-author-role=['\"]assistant['\"]",
    re.IGNORECASE,
)


class _CitationHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._anchors: list[dict[str, Any]] = []
        self._stack: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name.lower(): value or "" for name, value in attrs}
        url = _first_attr_url(attrs_dict)
        frame: dict[str, Any] = {"tag": tag.lower(), "url": url, "text": []}
        self._stack.append(frame)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self._stack:
            return
        frame = self._stack.pop()
        text = " ".join("".join(frame["text"]).split())
        if frame.get("url"):
            self._anchors.append({"url": frame["url"], "title": text})
        if self._stack and text:
            self._stack[-1]["text"].append(text)
        if frame.get("tag") != tag:
            return

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1]["text"].append(data)


def _first_attr_url(attrs: dict[str, str]) -> str | None:
    for key in ("href", "data-url", "data-href", "cite"):
        value = attrs.get(key)
        if value and value.startswith(("http://", "https://")):
            return unescape(value)
    return None


def _skip_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return True
    try:
        parsed = urlparse(url)
    except Exception:
        return True
    host = (parsed.netloc or "").lower().split("@")[-1].split(":")[0]
    if not host:
        return True
    normalized = url.lower()
    return any(part in host or part in normalized for part in SKIP_DOMAIN_PARTS)


def _normalize_url(url: str) -> str:
    return unescape(url).rstrip(".,;:!?)]}")


def _citation_dict(url: str, title: str, index: int) -> dict[str, Any]:
    return {"url": url, "title": title[:200], "index": index}


def extract_citations_from_html(
    html: str | None,
    *,
    llm_name: str | None = None,
) -> list[dict[str, Any]]:
    if not html:
        return []

    chunks = [html]
    if (llm_name or "").lower() == "chatgpt":
        assistant_starts = [match.start() for match in _CHATGPT_ASSISTANT_RE.finditer(html)]
        if assistant_starts:
            chunks = []
            for index, start in enumerate(assistant_starts):
                end = assistant_starts[index + 1] if index + 1 < len(assistant_starts) else len(html)
                chunks.append(html[start:end])

    parser = _CitationHTMLParser()
    for chunk in chunks:
        try:
            parser.feed(chunk)
        except Exception:
            continue

    candidates: list[dict[str, str]] = list(parser._anchors)
    seen: set[str] = set()
    citations: list[dict[str, Any]] = []
    for candidate in candidates:
        url = _normalize_url(candidate.get("url", ""))
        if not url or url in seen or _skip_url(url):
            continue
        seen.add(url)
        citations.append(_citation_dict(url, candidate.get("title", ""), len(citations) + 1))
    return citations


def merge_citations(
    existing: list[dict[str, Any]] | None,
    extra: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for citation in [*(existing or []), *(extra or [])]:
        url = _normalize_url(str(citation.get("url") or ""))
        if not url or url in seen or _skip_url(url):
            continue
        seen.add(url)
        merged.append(
            _citation_dict(url, str(citation.get("title") or ""), len(merged) + 1)
        )
    return merged


def classify_citation_extraction(
    llm_name: str,
    *,
    raw_text: str | None,
    response_html: str | None,
    citations: list[dict[str, Any]] | None,
    source_ui_seen: bool = False,
    source_ui_clicked: bool = False,
) -> dict[str, Any]:
    llm = (llm_name or "").lower()
    citation_count = len(citations or [])
    html_candidates = extract_citations_from_html(response_html, llm_name=llm)
    source_marker_count = len(_SOURCE_UI_RE.findall(response_html or ""))
    saw_source_ui = bool(source_ui_seen or source_ui_clicked or source_marker_count > 0)

    if citation_count > 0:
        status = "citations_present"
        reason = "persisted_citations"
    elif html_candidates:
        status = "citation_extractor_gap"
        reason = "external_urls_in_html_not_persisted"
    elif llm == "chatgpt" and saw_source_ui:
        status = "citation_extractor_gap"
        reason = "source_markers_without_extractable_urls"
    elif llm == "chatgpt":
        status = "citation_not_applicable"
        reason = "no_source_markers_or_external_links"
    else:
        status = "not_checked"
        reason = "non_chatgpt_without_citations"

    return {
        "status": status,
        "reason": reason,
        "citation_count": citation_count,
        "html_candidate_count": len(html_candidates),
        "source_marker_count": source_marker_count,
        "source_ui_seen": saw_source_ui,
        "source_ui_clicked": bool(source_ui_clicked),
        "response_len": len(raw_text or ""),
    }
