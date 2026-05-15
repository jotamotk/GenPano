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


# Doubao 2026 reference-drawer DOM. See guest_executor._extract_doubao_citations
# for the live page.evaluate version that this helper mirrors for HTML-only
# (post-mortem / fallback) extraction.
#
# - Panel root:     <div class="container-outer-XXXX" data-visible="true">
# - Panel header:   [class*="page-search"] containing "参考资料"
# - Card container: <div class="search-item-XXXX"> (suffix differs from inner
#                   class prefixes search-item-title / search-item-footer /
#                   search-item-summary / search-item-transition)
# - Card title:     [class*="search-item-title"]
# - Card source:    [class*="footer-title"]
# - Card index:     [class*="footer-citation"]
# - Card link:      first <a href> inside the card
_DOUBAO_PANEL_INNER_CLASS_PREFIXES: tuple[str, ...] = (
    "search-item-title",
    "search-item-footer",
    "search-item-summary",
    "search-item-transition",
)
_DOUBAO_SELF_DOMAINS: tuple[str, ...] = ("doubao.com", "bytedance.com")

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


def _classes_from_attrs(attrs: dict[str, str]) -> list[str]:
    raw = attrs.get("class") or ""
    return raw.split()


def _has_panel_marker_class(classes: list[str], marker: str) -> bool:
    return any(marker in cls for cls in classes)


def _is_doubao_card_container(classes: list[str]) -> bool:
    for cls in classes:
        if not cls.startswith("search-item-"):
            continue
        if any(cls.startswith(prefix) for prefix in _DOUBAO_PANEL_INNER_CLASS_PREFIXES):
            continue
        return True
    return False


def _is_doubao_panel_open(attrs: dict[str, str]) -> bool:
    classes = _classes_from_attrs(attrs)
    if not any("container-outer" in cls for cls in classes):
        return False
    visible = (attrs.get("data-visible") or "").strip().lower()
    if visible == "false":
        return False
    # data-visible absent OR data-visible="true" → treat as open. The live
    # JS counterpart in guest_executor uses the same fallback so that pages
    # rendered without the attribute still extract.
    return True


def _is_doubao_self_link(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = (parsed.netloc or "").lower().split("@")[-1].split(":")[0]
    if not host:
        return False
    return any(host == d or host.endswith(f".{d}") for d in _DOUBAO_SELF_DOMAINS)


class _DoubaoPanelParser(HTMLParser):
    """Stack-based parser that extracts opened-drawer citation cards.

    Mirrors guest_executor._extract_doubao_citations' page.evaluate strategy
    so that HTML-only post-mortem extraction (e.g. ``response_html`` saved by
    the worker AFTER opening the drawer) yields the same citation rows the
    live extractor would.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[dict[str, Any]] = []
        self._open_panels = 0  # depth count of currently-open visible panels
        self._cards: list[dict[str, Any]] = []

    # Stack frame helpers -------------------------------------------------
    def _current_card(self) -> dict[str, Any] | None:
        for frame in reversed(self._stack):
            if frame.get("role") == "card":
                return frame
        return None

    def _push_text(self, key: str, text: str) -> None:
        card = self._current_card()
        if not card:
            return
        existing = card.get(key)
        if existing:
            return  # first occurrence wins (mirrors querySelector behavior)
        if text.strip():
            card[key] = text.strip()

    # Parser callbacks ----------------------------------------------------
    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs: dict[str, str] = {
            name.lower(): (value or "") for name, value in attrs_list
        }
        classes = _classes_from_attrs(attrs)
        frame: dict[str, Any] = {
            "tag": tag.lower(),
            "classes": classes,
            "attrs": attrs,
            "role": None,
            "text_buf": [],
        }

        if tag.lower() == "div" and _is_doubao_panel_open(attrs):
            frame["role"] = "panel"
            self._open_panels += 1
        elif (
            self._open_panels > 0
            and _is_doubao_card_container(classes)
            and self._current_card() is None
        ):
            frame["role"] = "card"
            frame["card"] = {
                "url": "",
                "title": "",
                "source": "",
                "index": 0,
            }
        elif self._current_card() is not None:
            if tag.lower() == "a" and not self._current_card().get("card", {}).get("url"):
                href = attrs.get("href", "")
                if href.startswith(("http://", "https://")):
                    self._current_card()["card"]["url"] = unescape(href)
            if _has_panel_marker_class(classes, "search-item-title"):
                frame["role"] = "card-title"
            elif _has_panel_marker_class(classes, "footer-title"):
                frame["role"] = "card-source"
            elif _has_panel_marker_class(classes, "footer-citation"):
                frame["role"] = "card-index"

        self._stack.append(frame)

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        # Find the most recent matching tag to tolerate malformed HTML.
        idx = len(self._stack) - 1
        while idx >= 0 and self._stack[idx]["tag"] != tag.lower():
            idx -= 1
        if idx < 0:
            return
        # Pop everything above the matched tag (defensive — drawer DOM is
        # well-formed in practice).
        while len(self._stack) - 1 > idx:
            self._stack.pop()
        frame = self._stack.pop()

        text = "".join(frame.get("text_buf") or []).strip()

        role = frame.get("role")
        if role == "panel":
            self._open_panels = max(0, self._open_panels - 1)
        elif role == "card":
            card = frame.get("card") or {}
            if card.get("url"):
                self._cards.append(card)
        elif role in ("card-title", "card-source", "card-index"):
            card_frame = self._current_card()
            if card_frame:
                card = card_frame.setdefault("card", {})
                if role == "card-title" and not card.get("title"):
                    if text:
                        card["title"] = text
                elif role == "card-source" and not card.get("source"):
                    if text:
                        card["source"] = text
                elif role == "card-index" and not card.get("index"):
                    match = re.search(r"\d+", text)
                    if match:
                        try:
                            card["index"] = int(match.group(0))
                        except ValueError:
                            pass

        # Bubble text up so wrappers (e.g. <a><div class="search-item-title">)
        # surface the inner text into the parent frame when the inner div has
        # no class match (defensive fallback for slightly different markups).
        if text and self._stack:
            self._stack[-1].setdefault("text_buf", []).append(text)

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1].setdefault("text_buf", []).append(data)


def extract_doubao_panel_citations_from_html(html: str | None) -> list[dict[str, Any]]:
    """Extract citation cards from an opened Doubao reference drawer's HTML.

    Returns one dict per ``search-item-XXXX`` card found inside an open
    ``container-outer-XXXX`` panel (``data-visible="true"`` or attribute
    absent). Each dict contains ``url``, ``title``, ``source``, ``index``.
    Self-doubao/bytedance links and duplicate URLs are dropped. Cards
    inside a closed panel (``data-visible="false"``) are ignored so that
    pre-open snapshots do not silently surface as citations.
    """
    if not html:
        return []

    parser = _DoubaoPanelParser()
    try:
        parser.feed(html)
    except Exception:
        # Parser is best-effort; corrupted markup yields whatever it
        # managed to collect rather than raising into the scraper hot path.
        pass

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for card in parser._cards:
        url = _normalize_url(str(card.get("url") or ""))
        if not url or url in seen:
            continue
        if _is_doubao_self_link(url):
            continue
        seen.add(url)
        out.append(
            {
                "url": url,
                "title": str(card.get("title") or "")[:200],
                "source": str(card.get("source") or "")[:120],
                "index": int(card.get("index") or len(out) + 1),
            }
        )
    return out


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

    doubao_panel_candidates: list[dict[str, Any]] = []
    if llm == "doubao":
        doubao_panel_candidates = extract_doubao_panel_citations_from_html(response_html)

    if citation_count > 0:
        status = "citations_present"
        reason = "persisted_citations"
    elif html_candidates or doubao_panel_candidates:
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
        "doubao_panel_candidate_count": len(doubao_panel_candidates),
        "source_marker_count": source_marker_count,
        "source_ui_seen": saw_source_ui,
        "source_ui_clicked": bool(source_ui_clicked),
        "response_len": len(raw_text or ""),
    }
