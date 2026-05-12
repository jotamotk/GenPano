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

_DOUBAO_UNAUTH_TEXT_MARKERS = (
    "\u0037\u5929\u514d\u767b\u5f55",  # 7天免登录
    "\u514d\u767b\u5f55",  # 免登录
)

_DOUBAO_LOGIN_BUTTON_RE = re.compile(
    r"<(?:button|a|div|span)[^>]*(?:login|passport|signin|sign-in|data-testid=[\"'][^\"']*login)[^>]*>"
    r"[^<]{0,80}\u767b\u5f55"
    r"|<(?:button|a)[^>]{0,500}>\s*(?:<[^>]+>\s*)*\u767b\u5f55\s*(?:</[^>]+>\s*)*</(?:button|a)>"
    r"|<[^>]+role=[\"']button[\"'][^>]{0,500}>\s*(?:<[^>]+>\s*)*\u767b\u5f55"
    r"|(?:aria-label|title)=[\"']\u767b\u5f55[\"']",
    re.IGNORECASE | re.DOTALL,
)

_DOUBAO_AUTHENTICATED_RE = re.compile(
    r"(?:user-avatar|account-menu|profile-menu|user-account|"
    r"\u7528\u6237\u5934\u50cf|\u8d26\u53f7\u83dc\u5355|\u6211\u7684\u8d26\u53f7)",
    re.IGNORECASE,
)


def doubao_auth_state_reason(text: str | None, html: str | None = None) -> str | None:
    """Return a Doubao auth-state failure reason, or None when auth is proven."""
    combined = "\n".join(part for part in (text or "", html or "") if part)
    if not combined.strip():
        return "doubao_auth_state_missing"

    if any(marker in combined for marker in _DOUBAO_UNAUTH_TEXT_MARKERS):
        return "doubao_not_logged_in"
    if "\u767b\u5f55" in combined and _DOUBAO_LOGIN_BUTTON_RE.search(combined):
        return "doubao_not_logged_in"

    if _DOUBAO_AUTHENTICATED_RE.search(combined):
        return None

    return "doubao_auth_state_missing"


def invalid_response_reason(llm_name: str, text: str | None) -> str | None:
    """Return a reason when extracted page text is not an LLM answer."""
    if not text:
        return None

    lower = text.lower()
    for marker, reason in _GENERIC_INVALID_MARKERS.items():
        if marker in lower:
            return reason

    llm = (llm_name or "").lower()
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
