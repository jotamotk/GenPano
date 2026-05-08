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
        stack_matches = _CHATGPT_ASSET_STACK_RE.findall(text)
        if "application error" in lower and stack_matches:
            return "chatgpt_application_error"
        if len(stack_matches) >= 3:
            return "chatgpt_application_error"

    return None
