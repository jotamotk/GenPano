from __future__ import annotations

import re
from urllib.parse import urlparse


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

_CHATGPT_AUTH_REDIRECT_HOST_MARKERS = (
    "appleid.apple.com",
    "auth0.openai.com",
    "auth.openai.com",
    "login.openai.com",
)

_CHATGPT_AUTH_REDIRECT_TEXT_MARKERS = (
    "use your apple account to sign in to chatgpt",
    "sign in to apple account",
    "sign in to chatgpt",
    "log in to chatgpt",
    "continue with apple",
    "continue with google",
    "continue with microsoft",
)

_CHATGPT_LOGGED_OUT_SHELL_MARKERS = (
    "log in to get answers based on saved chats",
    "sign up for free",
    "stay logged out",
    "log in to try chatgpt",
)

_DOUBAO_UNAUTH_TEXT_MARKERS = (
    "\u0037\u5929\u514d\u767b\u5f55",  # 7天免登录
    "\u514d\u767b\u5f55",  # 免登录
    "\u767b\u5f55\u4ee5\u89e3\u9501\u66f4\u591a\u529f\u80fd",
    "\u4f1a\u8bdd\u8fc7\u671f\uff0c\u8bf7\u91cd\u65b0\u767b\u5f55",
    "from_logout=1",
    "login-btn-header",
    "error_code=13",
    '"error_code":13',
    '"is_login":false',
    '"user_id":0',
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

_DOUBAO_FLOW_MARKDOWN_BODY_RE = re.compile(
    r"<div\b[^>]*class\s*=\s*['\"][^'\"]*\bflow-markdown-body\b[^'\"]*['\"][^>]*>"
    r"(?P<body>.*?)</div>",
    re.IGNORECASE | re.DOTALL,
)

# Refs #963 Q-184971 (raw_text=1255 chars `非常适合 ，bestCoffer 企业级 AI 数据
# 脱敏工具…`) and Q-184988 (raw_text=1191 chars `非结构化数据 AI 脱敏准确率测评
# 核心指标…`) verify-readonly evidence (issue #963 comment 4469617051,
# 2026-05-17). Both queries landed in production as
# ``queries.status=failed`` with ``retry_reason`` in
# ``{no_response, doubao_homepage_content, doubao_auth_state_missing}``
# while their ``llm_responses`` row carried a real, >100-char answer.
# When the Doubao scraper extraction uses the JS body fallback (because
# ``.flow-markdown-body`` partly hydrated then the SPA reflowed), the
# captured ``raw_text`` is the real answer prefix concatenated with
# the page chrome that persists in the logged-in shell — including
# ``login-btn-header`` className, ``7天免登录`` promo text, and the
# ``登录以解锁更多功能`` overlay. Those chrome strings sit in the SOFT
# bucket because Doubao keeps them in DOM regardless of login state.
# The existing 20-char ``.flow-markdown-body`` whitelist only bypasses
# HARD markers; STRONG (SOFT+HARD) and the ``doubao_auth_state_reason``
# fallback still fired and rejected real answers. Production
# evidence: a 1255-char answer cannot coexist with an actual
# logged-out session — the chat would have redirected to /login or
# the page would have an actively-rendered login dialog (which is
# still treated as an absolute block above). A long-form answer is
# unforgeable evidence the SPA produced model output for the user.
# Use a tighter 100-char threshold than the HARD-bypass whitelist
# so this stronger override is robust: short hint strings that
# coincidentally exceed 20 chars do not flip the gate, but real
# answers that exceed 100 chars in any of the known Doubao response
# selectors do.
_DOUBAO_PERSISTENCE_RESPONSE_WHITELIST_MIN_LEN = 100

_DOUBAO_RESPONSE_CONTAINER_RES = (
    _DOUBAO_FLOW_MARKDOWN_BODY_RE,
    # ``data-testid='receive_message'`` is the second Doubao response
    # selector used by ``DOUBAO_SCRAPER_CONFIG['response_selector']``
    # in ``guest_executor.py:487``. When the SPA re-renders mid-stream
    # the .flow-markdown-body inner div can detach while the parent
    # receive_message container keeps the answer text — match either.
    re.compile(
        r"<[^>]*data-testid\s*=\s*['\"]receive_message['\"][^>]*>"
        r"(?P<body>.*?)</",
        re.IGNORECASE | re.DOTALL,
    ),
    # ``[class*='message-content']`` / ``[class*='chat-message-content']``
    # are the third/fourth selectors in the same config. Match elements
    # whose class attribute contains the substring as a class token.
    re.compile(
        r"<[^>]*class\s*=\s*['\"][^'\"]*\b(?:chat-)?message-content\b[^'\"]*['\"][^>]*>"
        r"(?P<body>.*?)</",
        re.IGNORECASE | re.DOTALL,
    ),
)

# Refs #963 production evidence (run 25951168887, query 184406 at
# 2026-05-16 03:04:24): Doubao overlays a "登录以解锁更多功能" /
# "7天免登录" promo on successful answers as a tier-up push -
# the page still carries the promo while ``.flow-markdown-body`` holds the
# real 1866-char response. Treating these visible promo strings as hard
# logout evidence rejected real answers. Split the strong-unauth set so
# substantive answers can override promo overlays while hard logout
# signals (session expired, from_logout=1) still block persistence
# regardless of any incidental answer-like text on the page.
_DOUBAO_PERSISTENCE_SOFT_UNAUTH_MARKERS = (
    "\u0037\u5929\u514d\u767b\u5f55",  # 7天免登录 (promo banner)
    "\u767b\u5f55\u4ee5\u89e3\u9501\u66f4\u591a\u529f\u80fd",  # promo banner
    # Refs #963 Q-184988 (post-#1042 deploy 2026-05-16 ~09:1x): a fully
    # authenticated Doubao chat \u2014 user 527070 in the sidebar, real
    # \u8131\u654f\u6307\u6807 answer in .flow-markdown-body, conversation history
    # populated \u2014 was still rejected as doubao_not_logged_in. Root
    # cause: ``login-btn-header`` was in the HARD bucket on the
    # assumption that the className only persists in logged-out shells,
    # but Doubao's SPA carries it through hydration into the logged-in
    # shell too. Moving it to SOFT lets a substantive answer override
    # the false-positive while keeping truly definitive signals
    # (\u4f1a\u8bdd\u8fc7\u671f / from_logout=1 / JS state / visible dialog) hard.
    "login-btn-header",
)
_DOUBAO_PERSISTENCE_HARD_UNAUTH_MARKERS = (
    "\u4f1a\u8bdd\u8fc7\u671f\uff0c\u8bf7\u91cd\u65b0\u767b\u5f55",  # 会话过期
    "from_logout=1",
)
_DOUBAO_PERSISTENCE_STRONG_UNAUTH_MARKERS = (
    _DOUBAO_PERSISTENCE_SOFT_UNAUTH_MARKERS
    + _DOUBAO_PERSISTENCE_HARD_UNAUTH_MARKERS
)

_DOUBAO_PERSISTENCE_STATE_LOGOUT_RE = re.compile(
    r"(?:[\"']?error_code[\"']?\s*[:=]\s*13|"
    r"[\"']?is_login[\"']?\s*[:=]\s*false|"
    r"[\"']?user_id[\"']?\s*[:=]\s*0)",
    re.IGNORECASE,
)

_DOUBAO_SUBSTANTIVE_ANSWER_MIN_LEN = 20

DOUBAO_AUTH_OK_MARKER = "doubao-auth-state:ok"


def _strip_hidden_doubao_auth_chrome(html: str | None) -> str:
    if not html:
        return ""

    visible_html = _DOUBAO_TEMPLATE_RE.sub("\n", html)
    previous = None
    while previous != visible_html:
        previous = visible_html
        visible_html = _DOUBAO_ELEMENT_WITH_ATTRS_RE.sub(
            lambda match: (
                "\n"
                if _DOUBAO_HIDDEN_ATTR_RE.search(match.group("attrs") or "")
                else match.group(0)
            ),
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
    url: str | None = None,
    title: str | None = None,
    runtime_events: list[dict] | None = None,
) -> str | None:
    """Return a ChatGPT auth/session failure reason, if page/runtime proves one."""
    page_parts = [text or "", url or "", title or ""]
    runtime_parts = []
    for event in runtime_events or []:
        if isinstance(event, dict):
            runtime_parts.append(str(event.get("text") or ""))
        else:
            runtime_parts.append(str(event))
    page_lower = "\n".join(page_parts).lower()
    runtime_lower = "\n".join(runtime_parts).lower()
    combined_lower = "\n".join((page_lower, runtime_lower))

    if any(marker in combined_lower for marker in _CHATGPT_TOKEN_INVALIDATED_MARKERS):
        return "token_invalidated"
    for marker, reason in _GENERIC_INVALID_MARKERS.items():
        if marker in combined_lower:
            return reason
    if _chatgpt_url_is_auth_redirect(url):
        return "chatgpt_auth_redirect"
    redirect_markers = sum(
        marker in page_lower for marker in _CHATGPT_AUTH_REDIRECT_TEXT_MARKERS
    )
    if redirect_markers >= 2:
        return "chatgpt_auth_redirect"
    logged_out_markers = sum(
        marker in page_lower for marker in _CHATGPT_LOGGED_OUT_SHELL_MARKERS
    )
    if logged_out_markers >= 2:
        return "chatgpt_not_logged_in"
    if _looks_like_chatgpt_logged_out_shell(page_lower):
        return "chatgpt_not_logged_in"
    return None


def _chatgpt_url_is_auth_redirect(url: str | None) -> bool:
    if not url:
        return False
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    host = host.split("@")[-1].split(":")[0]
    return any(
        host == marker or host.endswith(f".{marker}")
        for marker in _CHATGPT_AUTH_REDIRECT_HOST_MARKERS
    )


def doubao_persistence_auth_reason(
    llm_name: str,
    raw_text: str | None,
    response_html: str | None = None,
) -> str | None:
    """Return a Doubao auth failure that must block DONE persistence."""
    if (llm_name or "").lower() != "doubao":
        return None
    # Refs #963 production evidence (run 25951168887, query 184406 retry at
    # 2026-05-16 03:04:24): after a successful auto_login + requeue, Doubao
    # streamed a real 1866-char answer into ``.flow-markdown-body``, the
    # scraper extracted it cleanly, and then this function rejected the
    # result because the page also carried the promo banner string
    # "登录以解锁更多功能". The previous gate let strong-unauth markers win
    # before either the AUTH_OK marker or the substantive-answer probe
    # could, throwing away the valid response and re-marking the account
    # expired. That cycle is what production tagged as
    # ``doubao_post_reauth_doubao_not_logged_in``.
    #
    # Refs #963 follow-up evidence (Q-184971 retry 2026-05-16 13:20:33,
    # worker SHA 847cd9e): even with the timezone/WebRTC/qg fixes shipped,
    # an authenticated chat page that streamed a real 1727-char bestCoffer
    # answer into ``.flow-markdown-body`` STILL got rejected as
    # ``doubao_not_logged_in``. The page was on
    # ``/chat/38426272185416450`` with user 527070 visible in the
    # sidebar; the responseSelectors snapshot confirmed
    # ``.flow-markdown-body`` matched count=1, visibleCount=1 with the
    # real answer text. Root cause: one of the HARD markers (most likely
    # a JS state object remnant like ``is_login:false`` for a logged-out
    # template panel, or the literal string ``会话过期`` baked into an
    # i18n string bundle) appears in the page HTML even on the
    # logged-in shell. The previous gate ran HARD before substantive
    # answer, so the JS-state remnant won.
    #
    # New gate order:
    #   1. Actively-visible login dialog: absolute block (user can't
    #      interact with the chat anyway).
    #   2. AUTH_OK explicit marker: pass.
    #   3. Substantive ``.flow-markdown-body`` answer: pass — overrides
    #      JS-state remnants and i18n string matches because the page
    #      already rendered a real, streamed answer.
    #   4. HARD markers (``是会话过期``/``from_logout=1``/JS state):
    #      block only when no substantive answer is present.
    #   5. Strong markers (SOFT + HARD via STRONG): block in the
    #      remaining no-answer case.
    #   6. Generic auth_state_reason fallback.
    #
    # Visible login dialog stays absolute because it's the only HARD
    # signal that an actively-rendered login UI is interrupting the
    # session right now — at that point the answer below is stale and
    # the user is logged out for the purposes of any future call.
    if _doubao_has_visible_login_dialog(
        "\n".join(part for part in (raw_text or "", _strip_hidden_doubao_auth_chrome(response_html)) if part)
    ):
        return "doubao_not_logged_in"
    if response_html and DOUBAO_AUTH_OK_MARKER in response_html:
        return None
    # Refs Codex P1 on PR #1076: the override that lets a substantive
    # answer bypass HARD logout markers must be tied to the proven
    # ``.flow-markdown-body`` selector match, NOT raw_text length.
    # ``raw_text`` can come from the JS ``document.body.innerText``
    # fallback when the response selector misses, in which case >= 20
    # visible chars can include logout chrome text like
    # ``会话过期，请重新登录...`` — and bypassing HARD on THAT would
    # persist a logged-out page as a successful response. The
    # ``.flow-markdown-body`` HTML match is unforgeable: Doubao only
    # populates that node when a real model answer has streamed in.
    if _doubao_has_substantive_answer_html(response_html):
        return None
    # Refs #963 Q-184971 (raw_text=1255, `非常适合 ，bestCoffer 企业级 AI…`)
    # and Q-184988 (raw_text=1191, `非结构化数据 AI 脱敏准确率测评核心指标`)
    # verify-readonly evidence (issue #963 comment 4469617051): when the
    # response contains >=100 chars of real answer text in any of
    # Doubao's documented response selectors, even SOFT-bucket chrome
    # (``login-btn-header`` className, ``7天免登录`` promo, ``登录以解锁
    # 更多功能`` overlay) and the ``doubao_auth_state_reason`` fallback
    # must NOT veto persistence — the SPA would not produce a 100+
    # char answer for a session that is actually logged out. This
    # whitelist sits below the absolute visible-login-dialog block
    # (which still wins, because an interrupting dialog actively
    # ends the session) and below the HARD-bypass at 20 chars; it
    # exists to additionally bypass STRONG (SOFT+HARD) and the
    # auth_state fallback when the answer is long enough to be
    # unmistakably real.
    if _doubao_has_persistence_whitelist_answer(raw_text, response_html):
        return None
    hard_auth_reason = _doubao_hard_persistence_auth_reason(
        raw_text, response_html
    )
    if hard_auth_reason:
        return hard_auth_reason
    strong_auth_reason = _doubao_strong_persistence_auth_reason(
        raw_text, response_html
    )
    if strong_auth_reason:
        return strong_auth_reason
    return doubao_auth_state_reason(raw_text, response_html)


def _doubao_hard_persistence_auth_reason(
    text: str | None,
    html: str | None = None,
) -> str | None:
    """Hard logout evidence that overrides even substantive answers.

    Hard signals prove the session is in a logged-out state regardless of
    any answer-like text on the page: JS state markers (``is_login:false``,
    ``error_code:13``, ``user_id:0``), explicit error chrome
    (``from_logout=1`` URL artifact, ``会话过期，请重新登录`` text), and
    an actually-visible login dialog. Soft chrome (promo banners
    ``7天免登录`` / ``登录以解锁更多功能`` and the SPA className
    ``login-btn-header``) is intentionally NOT in this set — these
    coexist with real answers on the logged-in shell and would
    otherwise reject legitimate responses.
    """
    visible_html = _strip_hidden_doubao_auth_chrome(html)
    combined = "\n".join(part for part in (text or "", visible_html) if part)
    if not combined.strip():
        return "doubao_auth_state_missing"
    if any(
        marker in combined
        for marker in _DOUBAO_PERSISTENCE_HARD_UNAUTH_MARKERS
    ):
        return "doubao_not_logged_in"
    if _DOUBAO_PERSISTENCE_STATE_LOGOUT_RE.search(combined):
        return "doubao_not_logged_in"
    if _doubao_has_visible_login_dialog(combined):
        return "doubao_not_logged_in"
    return None


def _doubao_has_substantive_answer(
    raw_text: str | None,
    html: str | None,
) -> bool:
    if raw_text and len(raw_text.strip()) >= _DOUBAO_SUBSTANTIVE_ANSWER_MIN_LEN:
        return True
    return _doubao_has_substantive_answer_html(html)


def _doubao_has_substantive_answer_html(html: str | None) -> bool:
    visible_html = _strip_hidden_doubao_auth_chrome(html)
    for match in _DOUBAO_FLOW_MARKDOWN_BODY_RE.finditer(visible_html):
        body = re.sub(r"<[^>]+>", " ", match.group("body"))
        if len(body.strip()) >= _DOUBAO_SUBSTANTIVE_ANSWER_MIN_LEN:
            return True
    return False


def _doubao_max_response_container_text_len(html: str | None) -> int:
    """Return the longest stripped text length found in any Doubao response container.

    Inspects the union of Doubao's response selectors
    (``.flow-markdown-body``, ``[data-testid='receive_message']``,
    ``[class*='message-content']``) so the whitelist still fires
    when the SPA re-renders the inner ``.flow-markdown-body`` away
    but keeps the answer text in the parent ``receive_message``
    container.
    """
    visible_html = _strip_hidden_doubao_auth_chrome(html)
    longest = 0
    for container_re in _DOUBAO_RESPONSE_CONTAINER_RES:
        for match in container_re.finditer(visible_html):
            body = re.sub(r"<[^>]+>", " ", match.group("body"))
            stripped_len = len(body.strip())
            if stripped_len > longest:
                longest = stripped_len
    return longest


def _doubao_has_persistence_whitelist_answer(
    raw_text: str | None,
    html: str | None,
) -> bool:
    """Return True when the response carries >=100 chars of real answer text.

    Refs #963 Q-184971 / Q-184988 (issue #963 comment 4469617051):
    a long-form answer in any of the documented Doubao response
    containers is unforgeable evidence that the SPA produced
    model output for the user; SOFT chrome (``login-btn-header`` /
    ``7天免登录`` / ``登录以解锁更多功能``) coexists with such
    answers on the logged-in shell, so it must NOT veto persistence.
    The threshold is intentionally higher than the 20-char HARD-
    bypass whitelist so a brief hint that crosses 20 chars does not
    flip the gate. Visible login dialog chrome is still allowed to
    override above this gate because an interrupting dialog is the
    only signal that the user cannot continue interacting with the
    page.
    """
    container_len = _doubao_max_response_container_text_len(html)
    if container_len >= _DOUBAO_PERSISTENCE_RESPONSE_WHITELIST_MIN_LEN:
        return True
    return False


def _doubao_strong_persistence_auth_reason(
    text: str | None,
    html: str | None = None,
) -> str | None:
    visible_html = _strip_hidden_doubao_auth_chrome(html)
    combined = "\n".join(part for part in (text or "", visible_html) if part)
    if not combined.strip():
        return "doubao_auth_state_missing"

    if any(marker in combined for marker in _DOUBAO_PERSISTENCE_STRONG_UNAUTH_MARKERS):
        return "doubao_not_logged_in"
    if _DOUBAO_PERSISTENCE_STATE_LOGOUT_RE.search(combined):
        return "doubao_not_logged_in"
    if (
        "\u767b\u5f55\u4ee5\u89e3\u9501\u66f4\u591a\u529f\u80fd" in combined
        or _doubao_has_visible_login_dialog(combined)
    ):
        return "doubao_not_logged_in"
    return None


# Refs #963 production evidence (Q-184971 retry on worker SHA ``9e9b1e0``,
# 2026-05-16 16:15-16:18 UTC, GitHub Actions verify-readonly run
# 25967204514 \u2192
# https://github.com/jotamotk/trash_test/issues/963#issuecomment-4467456937).
# Worker log: ``[doubao] \u901a\u8fc7 selector \u63d0\u53d6\u54cd\u5e94: .flow-markdown-body
# (1023 chars)`` followed 21ms later by ``[doubao] \u672a\u80fd\u83b7\u53d6\u54cd\u5e94`` +
# account 45 marked ``expired`` + ``Query 184971 failed
# (doubao_post_reauth_doubao_not_logged_in: 0 chars)``. The Phase 1
# diagnostic ran every gate stage against the saved HTML
# ``query_184971_doubao_not_logged_in_1778948280.html`` (455785 bytes)
# and produced:
#   visible_login_dialog          = True
#   substantive_answer_html       = True
#   hard_persistence_auth_reason  = doubao_not_logged_in
#   strong_persistence_auth_reason= doubao_not_logged_in
#   HARD markers found            = (none)
#   STATE_LOGOUT_RE matches       = (none)
# i.e. neither the hard string markers (``\u4f1a\u8bdd\u8fc7\u671f``,
# ``from_logout=1``) nor the JS-state RE (``is_login:false`` /
# ``error_code:13`` / ``user_id:0``) fired; the dialog probe alone
# returned True. The literal triggering substrings captured were:
#   DIALOG-CANDIDATE 'passport' at offset 428251: ...,"app_user_info":{},
#     "avatar_url":"https:\\u002F\\u002Fp9-passport.byteacctimg.com
#     \\u002Fimg\\u002Fuser-avatar\\u002Fassets\\u002Fe7b19241fb224c
#     ea967dfaea35448102_1080_10..."
#   DIALOG-CANDIDATE '\u624b\u673a\u53f7' at offset 365248:
#     ...\u5ba2\u6237\u8d44\u6599\uff1a\u8eab\u4efd\u8bc1\u3001
#     \u624b\u673a\u53f7\u3001\u94f6\u884c\u5361\u53f7\u8bc6\u522b
#     \u51c6\u786e\u738799.7%\uff0c\u652f\u630115/18 \u4f4d\u8eab
#     \u4efd\u8bc1\u533a\u5206...
# i.e. ``passport`` matched the Bytedance SSO asset host
# (``p9-passport.byteacctimg.com``) inside the logged-in user's
# ``accountInfo.app_user_info.avatar_url`` JSON state \u2014 that JSON only
# exists when the account IS authenticated, so the substring proves
# the opposite of what the gate inferred \u2014 and ``\u624b\u673a\u53f7``
# matched the bullet ``\u5ba2\u6237\u8d44\u6599\uff1a\u8eab\u4efd\u8bc1
# \u3001\u624b\u673a\u53f7\u3001\u94f6\u884c\u5361\u53f7\u8bc6\u522b
# \u51c6\u786e\u738799.7%`` inside the LLM-generated answer about
# data masking. None of ``role="dialog"`` / ``login-dialog`` /
# ``login-button`` / ``\u626b\u7801\u767b\u5f55`` /
# ``\u624b\u673a\u53f7\u767b\u5f55`` / ``\u77ed\u4fe1\u9a8c\u8bc1\u7801``
# / ``\u8bf7\u8f93\u5165\u624b\u673a\u53f7`` existed in the visible
# HTML \u2014 the real login dialog was not present.
#
# This is the 3rd iteration on persistence_auth_reason after #1047 and
# #1076 + Codex P1 on #1076. AGENTS.md rule 5 (SECOND FAILED ITERATION
# -> step-back redesign) applies: stop adding more markers to the
# disjunction and instead require the dialog probe to bind on chrome
# that actually proves a dialog is on screen. Bare substrings that
# ride along on every Bytedance SPA page (``passport`` matches any
# ``*passport*.byteacctimg.com`` / ``passport.bytedance.com`` /
# ``passport.douyin.com`` asset URL) and bare substrings that ride
# along on any Chinese answer about personal data (``\u624b\u673a\u53f7``
# for phone-number) cannot trip the gate by themselves. A real Doubao
# login dialog carries explicit chrome \u2014 ``role="dialog"`` /
# ``login-dialog`` paired with ``login-button`` / ``\u626b\u7801\u767b
# \u5f55``, or one of the explicit login-context phrases
# (``\u624b\u673a\u53f7\u767b\u5f55`` / ``\u77ed\u4fe1\u9a8c\u8bc1\u7801``
# / ``\u8bf7\u8f93\u5165\u624b\u673a\u53f7``).
_DOUBAO_LOGIN_DIALOG_CHROME_MARKERS = (
    "role=\"dialog\"",
    "role='dialog'",
    "login-dialog",
)
_DOUBAO_LOGIN_DIALOG_ACTION_MARKERS = (
    "login-button",
    "\u626b\u7801\u767b\u5f55",  # \u626b\u7801\u767b\u5f55 (QR-code login)
)
_DOUBAO_LOGIN_DIALOG_TEXT_MARKERS = (
    "\u624b\u673a\u53f7\u767b\u5f55",      # \u624b\u673a\u53f7\u767b\u5f55 (phone-number login)
    "\u77ed\u4fe1\u9a8c\u8bc1\u7801",          # \u77ed\u4fe1\u9a8c\u8bc1\u7801 (SMS code)
    "\u8bf7\u8f93\u5165\u624b\u673a\u53f7",  # \u8bf7\u8f93\u5165\u624b\u673a\u53f7 (enter phone)
)


def _doubao_has_visible_login_dialog(combined: str) -> bool:
    """Decide whether the visible HTML contains a real Doubao login dialog.

    Refs #963 Q-184971 evidence (run 25967204514). Bare ``passport``
    and bare ``\u624b\u673a\u53f7`` (phone-number Chinese, without a
    login qualifier) are not enough: the logged-in shell embeds
    ``p9-passport.byteacctimg.com`` avatar URLs in ``accountInfo``,
    and an LLM answer about data masking can spell out
    ``\u624b\u673a\u53f7`` as a bullet point. A real login dialog
    always carries one of the explicit chrome markers
    (``role="dialog"`` / ``login-dialog``) combined with a login
    action marker (``login-button`` / ``\u626b\u7801\u767b\u5f55``),
    or one of the explicit login-context Chinese phrases
    (``\u624b\u673a\u53f7\u767b\u5f55`` / ``\u77ed\u4fe1\u9a8c\u8bc1
    \u7801`` / ``\u8bf7\u8f93\u5165\u624b\u673a\u53f7``). Require
    those combinations.
    """
    has_dialog = any(
        marker in combined
        for marker in _DOUBAO_LOGIN_DIALOG_CHROME_MARKERS
    )
    has_login_action = any(
        marker in combined
        for marker in _DOUBAO_LOGIN_DIALOG_ACTION_MARKERS
    )
    if has_dialog and has_login_action:
        return True
    return any(
        marker in combined
        for marker in _DOUBAO_LOGIN_DIALOG_TEXT_MARKERS
    )


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


def _looks_like_chatgpt_logged_out_shell(lower: str) -> bool:
    login_markers = sum(
        marker in lower
        for marker in (
            "log in",
            "sign up",
            "sign up for free",
            "saved chats",
            "uploaded files",
            "accept all cookies",
        )
    )
    prompt_markers = (
        "#prompt-textarea" in lower
        or "message chatgpt" in lower
        or "what are you working on" in lower
        or "what's on your mind today" in lower
        or "what\u2019s on your mind today" in lower
    )
    return prompt_markers and login_markers >= 3


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
