"""Layer classifier for Topic / Prompt / Query boundaries.

This module enforces the three-layer concept boundary defined in Module 0
of the GenPano admin redesign plan:

  Topic  = research subject area (noun-phrase, no user intent, no personal anchors)
  Prompt = a complete user input — request, question, or exploration — that a
           real user could paste into ChatGPT and get a useful answer back from.
           No personal anchors (no name / city / age / numeric budget).
  Query  = a Prompt instantiated for one specific Profile, with personal
           anchors injected (我 / 我家 / [city] / [number]+岁 / etc.).

The intent classifier is mechanical (regex over Chinese surface features), so
it stays cheap and runs after every LLM batch. Generators use it as a final
"boundary firewall" — anything the LLM produces in the wrong layer gets
rejected with reason ``looks_like_<actual_layer>``.

Both ``topic_plan.py`` and ``prompt_matrix.py`` import from here, so the
boundary stays consistent across generators.
"""

from __future__ import annotations

import re

# Verb-shaped intent (request / question / exploration) — anything here marks
# the text as a *complete user input*, not a topic label.
PROMPT_INTENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[?？]"),  # English/CJK question mark
    re.compile(r"(吗|呢)$"),  # sentence-final particles
    re.compile(r"(怎么|如何|哪个|哪款|哪种|是什么|为什么|什么样)"),
    re.compile(r"(帮我|告诉我|给我|介绍下?|说一下|讲讲)"),
    re.compile(r"(推荐|对比|比较|列出|列举|分析|评测|总结|评价)"),
    re.compile(r"(优缺点|差异|区别|与.*相比|和.*相比|VS|vs)"),
)

# First-person + personal facts — these mark the text as *individualized*,
# i.e. a Query rather than a Prompt template.
#
# Note: bare demographic descriptors like "二胎" / "三胎" / "单身" are NOT
# personal anchors on their own — "二胎家庭奶粉选择策略" is a Topic, not a
# Query. These only become personal when combined with self-claims (我是二胎
# 宝妈) or specific child references like 老大/老二/老三 + age.
PERSONAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:^|[，,。 ])(我|我家|我们|本人|咱|咱家)"),
    re.compile(r"\d{1,3}\s*(岁|个月|周岁|周|天)"),  # ages
    re.compile(r"(预算|月入|工资|月薪).{0,4}?\d"),  # budget anchors
    re.compile(r"(老大|老二|老三)"),  # specific child reference
    re.compile(r"(二胎|三胎)\s*(宝妈|妈妈|爸爸|家长|奶爸|宝爸|爹妈)"),  # self-claim
    re.compile(r"(在|住在|来自)\s*[一-鿿]{2,4}市?(?![一-鿿])"),
)

LAYERS: tuple[str, ...] = ("topic", "prompt", "query")


def has_intent(text: str) -> bool:
    """True if ``text`` contains any verb-shaped user-input cue."""
    if not text:
        return False
    return any(p.search(text) for p in PROMPT_INTENT_PATTERNS)


def has_personal_anchor(text: str) -> bool:
    """True if ``text`` contains first-person + an individualizing fact."""
    if not text:
        return False
    return any(p.search(text) for p in PERSONAL_PATTERNS)


def classify_text(text: str) -> str:
    """Mechanically classify ``text`` into one of LAYERS.

    Order matters: personal anchors trump intent (a personalized question
    is still a Query, not a Prompt).
    """
    if not text:
        return "topic"
    if has_personal_anchor(text):
        return "query"
    if has_intent(text):
        return "prompt"
    return "topic"


def reject_reason(text: str, expected_layer: str) -> str | None:
    """Return ``None`` if ``text`` matches ``expected_layer``, else the
    structured reason ``"looks_like_<actual>"`` for the API response.
    """
    if expected_layer not in LAYERS:
        return None
    actual = classify_text(text)
    if actual == expected_layer:
        return None
    return f"looks_like_{actual}"


# Reusable system-prompt header that defines the boundaries to the LLM.
# Both topic_plan.py and prompt_matrix.py prepend this (with their own
# {LAYER} substituted) so the LLM knows what it's expected to produce.
LAYER_BOUNDARY_PROMPT = """## 三层概念边界（必须遵守，越界的输出会被自动拒收）

Topic = 研究主题 / 话题标签。
  - 不是用户会发出的句子，而是一片话题领域，类似一篇文章的标题。
  - 5–20 字，名词性短语为主。
  - 禁止：动词性祈使（帮我/推荐/介绍/告诉我）、问号、个人化字眼。
  - 例：「奶粉冲调温度争议」「直邮代购真伪辨别」「二胎家庭奶粉选择策略」

Prompt = 用户会自然发出的、完整的提问或请求。
  - 测试：复制粘贴进 ChatGPT，应该能直接给出有用回答（不会反问"你想知道什么"）。
  - 8–60 字。可以是问句、祈使句（帮我推荐 / 介绍下 / 对比一下 / 列出）、或探索句（…的优缺点 / …和…的差异）。
  - 禁止：纯名词短语；禁止个性化锚点（我/我家/我们/城市名/年龄数字/预算数字/老大老二）。
  - 例：「帮我推荐一款适合二胎家庭的奶粉」「奶粉冲调用多少度水合适？」「对比一下雀巢和惠氏」

Query = 某个 Profile 的一次个性化执行文本。
  - = Prompt 模板 + 该 Profile 的角色上下文。
  - 20–200 字。必须包含至少一个个性化锚点（第一人称 + 个人事实）。
  - 例：「我在杭州，娃刚 4 个月，看代购说澳洲 a2 比国内便宜很多但又怕假，怎么验？」

你当前在生成的层级是：{LAYER}。只输出该层级的内容。"""
