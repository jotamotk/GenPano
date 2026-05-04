"""Hotspot collectors for Module D.

Each collector pulls a list of HotspotCandidate objects from a public hot-list
source (微博热搜 / 百度热点 / 抖音热点榜 / 小红书热点 / 知乎热榜 / 豆包联网搜)
and the pipeline normalizes, dedupes, classifies by industry, and persists
them as ``status='draft'`` rows for admin review.

D-A (this PR): public-API collectors (baidu / zhihu) + LLM-search fallback.
D-B (next PR): browser-use collectors for closed/half-closed platforms
              (weibo / douyin / xiaohongshu) using the existing AccountPool.
"""
from .base import HotspotCandidate, HotspotCollector  # noqa: F401
