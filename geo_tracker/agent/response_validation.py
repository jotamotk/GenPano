from __future__ import annotations

import re


_CHATGPT_ASSET_STACK_RE = re.compile(
    r"https://chatgpt\.com/cdn/assets/[^ \n]+\.js:\d+:\d+",
    re.IGNORECASE,
)

_GENERIC_INVALID_MARKERS = {
    "your session has expired": "cookies_expired",
    "please log in again to continue using the app": "cookies_expired",
}

_CHATGPT_TOKEN_INVALIDATED_MARKERS = (
    "token_invalidated",
    "your authentication token has been invalidated",
)

_DOUBAO_UNAUTH_TEXT_MARKERS = (
    "\u0037\u5929\u514d\u767b\u5f55",  # 7天免登录
    "\u514d\u767b\u5f55",  # 免登录
)

_DOUBAO_LOGIN_BUTTON_RE = re.compile(
    r"<(?:button|a|div|span)[^>]*(?:login|passport|signin|sign-in|data-testid=[\"'][^\"']*login)[^>]*>"
    r"[^<]{0,80}\u767b\u5f55"
    r"|(?:aria-label|title)=[\"']\u767b\u5f55[\"']",
    re.IGNORECASE | re.DOTALL,
)

_DOUBAO_LOGIN_CHROME_RE = re.compile(
    r"<(?:button|a|div|span)[^>]{0,240}>[\s\n\r]*\u767b\u5f55[\s\n\r]*</(?:button|a|div|span)>",
    re.IGNORECASE | re.DOTALL,
)

_DOUBAO_TEMPLATE_RE = re.compile(
    r"<template\b[^>]*>.*?</template>",
    re.IGNORECASE | re.DOTALL,
)

_DOUBAO_ELEMENT_WITH_ATTRS_RE = re.compile(
    r"<(?P<tag>button|a|div|span)\b(?P<attrs>[^>]*)>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)

_DOUBAO_HIDDEN_ATTR_RE = re.compile(
    r"(?:\bhidden\b|aria-hidden\s*=\s*['\"]?true['\"]?|"
    r"style\s*=\s*['\"][^'\"]*(?:display\s*:\s*none|visibility\s*:\s*hidden)|"
    r"class\s*=\s*['\"][^'\"]*(?:^|\s)(?:hidden|is-hidden|sr-only)(?:\s|$))",
    re.IGNORECASE,
)

_DOUBAO_AUTHENTICATED_RE = re.compile(
    r"(?:user-avatar|account-menu|profile-menu|user-info|"
    r"\u7528\u6237\u5934\u50cf|\u8d26\u53f7\u83dc\u5355|\u6211\u7684\u8d26\u53f7)",
    re.IGNORECASE,
)

DOUBAO_AUTH_OK_MARKER = "doubao-auth-state:ok"


def _strip_hidden_doubao_auth_chrome(html: str | None) -> str:
    if not html:
        return ""

    visible_html = _DOUBAO_TEMPLATE_RE.sub("\n", html)
    previous = None
    while previous != visible_html:
        previous = visible_html
        visible_html = _DOUBAO_ELEMENT_WITH_ATTRS_RE.sub(
            lambda match: "\n"
            if _DOUBAO_HIDDEN_ATTR_RE.search(match.group("attrs") or "")
            else match.group(0),
            visible_html,
        )
    return visible_html


def doubao_auth_state_reason(text: str | None, html: str | None = None) -> str | None:
    """Return a Doubao auth-state failure reason, or None when auth is proven."""
    visible_html = _strip_hidden_doubao_auth_chrome(html)
    combined = "\n".join(part for part in (text or "", visible_html) if part)
    if not combined.strip():
        return "doubao_auth_state_missing"

    if any(marker in combined for marker in _DOUBAO_UNAUTH_TEXT_MARKERS):
        return "doubao_not_logged_in"
    if "\u767b\u5f55" in combined and _DOUBAO_LOGIN_BUTTON_RE.search(combined):
        return "doubao_not_logged_in"
    if "\u767b\u5f55" in visible_html and _DOUBAO_LOGIN_CHROME_RE.search(visible_html):
        return "doubao_not_logged_in"

    if _DOUBAO_AUTHENTICATED_RE.search(combined):
        return None

    return "doubao_auth_state_missing"


def chatgpt_auth_state_reason(
    text: str | None,
    *,
    runtime_events: list[dict] | None = None,
) -> str | None:
    """Return a ChatGPT auth/session failure reason, if page/runtime proves one."""
    parts = [text or ""]
    for event in runtime_events or []:
        if isinstance(event, dict):
            parts.append(str(event.get("text") or ""))
        else:
            parts.append(str(event))
    lower = "\n".join(parts).lower()

    if any(marker in lower for marker in _CHATGPT_TOKEN_INVALIDATED_MARKERS):
        return "token_invalidated"
    for marker, reason in _GENERIC_INVALID_MARKERS.items():
        if marker in lower:
            return reason
    return None


def doubao_persistence_auth_reason(
    llm_name: str,
    raw_text: str | None,
    response_html: str | None = None,
) -> str | None:
    """Return a Doubao auth failure that must block DONE persistence."""
    if (llm_name or "").lower() != "doubao":
        return None
    if response_html and DOUBAO_AUTH_OK_MARKER in response_html:
        return None
    return doubao_auth_state_reason(raw_text, response_html)


def invalid_response_reason(llm_name: str, text: str | None) -> str | None:
    """Return a reason when extracted page text is not an LLM answer."""
    if not text:
        return None

    lower = text.lower()
    llm = (llm_name or "").lower()
    if llm == "chatgpt":
        auth_reason = chatgpt_auth_state_reason(text)
        if auth_reason:
            return auth_reason

    for marker, reason in _GENERIC_INVALID_MARKERS.items():
        if marker in lower:
            return reason

    if llm == "chatgpt":
        if _looks_like_chatgpt_login_page(lower):
            return "chatgpt_login_page"
        if _looks_like_chatgpt_home_shell(lower):
            return "chatgpt_home_shell"

        stack_matches = _CHATGPT_ASSET_STACK_RE.findall(text)
        if "application error" in lower and stack_matches:
            return "chatgpt_application_error"
        if len(stack_matches) >= 3:
            return "chatgpt_application_error"

    return None


def _looks_like_chatgpt_home_shell(lower: str) -> bool:
    nav_markers = sum(
        marker in lower
        for marker in (
            "skip to content",
            "new chat",
            "search chats",
            "chat history",
            "recents",
            "free chatgpt",
        )
    )
    prompt_markers = (
        "what are you working on" in lower
        or "what's on your mind today" in lower
        or "what\u2019s on your mind today" in lower
        or "what?s on your mind today" in lower
        or "what\u9225\u6a9as on your mind today" in lower
    )
    return prompt_markers and nav_markers >= 2


def _looks_like_chatgpt_login_page(lower: str) -> bool:
    apple_markers = sum(
        marker in lower
        for marker in (
            "apple account",
            "use your apple account to sign in to chatgpt",
            "email or phone number",
        )
    )
    if apple_markers >= 2:
        return True

    login_markers = sum(
        marker in lower
        for marker in (
            "sign in to chatgpt",
            "log in to chatgpt",
            "continue with google",
            "continue with microsoft",
            "continue with apple",
        )
    )
    return login_markers >= 2
