"""
青果网络 (qg.net) short-term elastic-extraction proxy client.

Refs #963 production evidence: the worker's static egress IP has been
fingerprinted by Doubao's risk control. Even with the full self-healing
chain (#1016/#1017/#1027/#1030/#1032/#1037) deployed and a fresh
account registered via service_id=666056 fallback, Doubao now serves a
3D image-selection captcha with the image itself failing to load
(error code 5202). 5202 denial is by-IP — the captcha is unsolvable
because the challenge image never arrives. Rotating to a fresh
residential / mobile IP per Doubao query bypasses the IP-level block.

This module wraps the 青果 弹性提取 (elastic extraction) API:
- A user-supplied ``QG_PROXY_EXTRACT_URL`` returns a fresh batch of
  short-term IPs (ip:port format).
- Each request is authenticated by ``QG_PROXY_AUTH_KEY`` +
  ``QG_PROXY_AUTH_PASSWORD`` baked into the per-IP proxy URL as
  ``http://AUTH_KEY:PASSWORD@IP:PORT``.
- IPs are short-lived (typically 1-10 minutes); we cache the batch and
  refresh when exhausted or when an IP is reported as failed.

The client deliberately accepts multiple known qg.net response shapes
so the caller doesn't have to match an exact JSON schema:
- ``{"code":0,"data":[{"server":"ip:port"},...]}`` (standard)
- ``{"code":0,"data":["ip:port","ip:port",...]}``
- ``{"data":[{"ip":"...","port":...}, ...]}``
- Plain text body ``ip:port\nip:port\n...``
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


_IP_PORT_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}:\d{1,5}$")


@dataclass
class QGProxyLease:
    """An IP:Port lease handed out by the QG extraction API."""

    ip_port: str
    auth_key: str
    auth_password: str

    @property
    def proxy_url(self) -> str:
        """``http://AUTH_KEY:PASSWORD@IP:PORT`` for httpx / Playwright."""
        return f"http://{self.auth_key}:{self.auth_password}@{self.ip_port}"

    @property
    def server_url(self) -> str:
        """``http://IP:PORT`` — Playwright wants server / username / password
        as separate fields rather than embedded in the URL."""
        return f"http://{self.ip_port}"


@dataclass
class QGProxyClient:
    """Async client for 青果 short-term elastic-extraction proxy."""

    extract_url: str
    auth_key: str
    auth_password: str
    pool: list[str] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _http: httpx.AsyncClient = field(default_factory=lambda: httpx.AsyncClient(timeout=15))

    @classmethod
    def from_env(cls) -> Optional["QGProxyClient"]:
        extract_url = os.getenv("QG_PROXY_EXTRACT_URL", "").strip()
        auth_key = os.getenv("QG_PROXY_AUTH_KEY", "").strip()
        auth_password = os.getenv("QG_PROXY_AUTH_PASSWORD", "").strip()
        if not (extract_url and auth_key and auth_password):
            return None
        return cls(
            extract_url=extract_url,
            auth_key=auth_key,
            auth_password=auth_password,
        )

    async def reserve(self) -> QGProxyLease:
        """Return a fresh ``ip:port`` lease, refilling the pool when empty."""
        async with self._lock:
            if not self.pool:
                self.pool = await self._fetch_pool()
            if not self.pool:
                raise RuntimeError(
                    "qg extract returned 0 usable IPs; check extract_url, "
                    "balance, and whether the worker IP is whitelisted"
                )
            # Randomise selection within the batch so consecutive queries
            # on the same worker don't all hit the same IP — qg's batch
            # is small (1-100) and Doubao's risk control aggregates by
            # specific IP, not by ASN.
            ip_port = self.pool.pop(random.randrange(len(self.pool)))
        return QGProxyLease(
            ip_port=ip_port,
            auth_key=self.auth_key,
            auth_password=self.auth_password,
        )

    async def report_failure(self, ip_port: str) -> None:
        """Drop a known-bad IP from the cache.

        We do not actively release IPs back to qg — short-term IPs expire
        on their own. We just stop using one that triggered a 5202 / auth
        failure / etc.
        """
        async with self._lock:
            self.pool = [p for p in self.pool if p != ip_port]

    async def _fetch_pool(self) -> list[str]:
        """Call the extract API and parse the IP list."""
        try:
            resp = await self._http.get(self.extract_url)
        except Exception as exc:
            logger.warning("qg extract HTTP failed: %s", exc)
            return []
        status = resp.status_code
        body = resp.text or ""
        if status != 200:
            logger.warning(
                "qg extract HTTP %s body=%s",
                status,
                _redact_for_log(body)[:300],
            )
            return []
        return _parse_qg_response(body)

    async def close(self) -> None:
        await self._http.aclose()


def _parse_qg_response(body: str) -> list[str]:
    """Tolerate multiple qg.net response shapes.

    Returns a list of ``"ip:port"`` strings, possibly empty.

    Documented qg.net success envelope (per doc 1839 / 1865):
      {"code": "SUCCESS",
       "data": [{"proxy_ip":"1.2.3.4","server":"1.2.3.4:18080",
                 "area":"...", "deadline":"..."}, ...],
       "request_id": "..."}
    Also accepts ``code`` as ``0`` / ``"0"`` for compatibility with
    legacy / non-overseas qg endpoints.
    """
    body = (body or "").strip()
    if not body:
        return []
    # JSON envelope first.
    try:
        data = json.loads(body)
    except Exception:
        data = None
    if isinstance(data, dict):
        # qg.net uses string codes ("SUCCESS") on overseas endpoints and
        # numeric 0 on some legacy endpoints — accept both.
        code_val = data.get("code")
        if code_val is not None:
            code_str = str(code_val).strip().upper()
            if code_str not in ("0", "SUCCESS"):
                logger.warning(
                    "qg extract API returned non-success code=%s msg=%s",
                    code_str,
                    _redact_for_log(
                        str(data.get("msg") or data.get("message") or "")
                    )[:200],
                )
                return []
        items = data.get("data") or data.get("list") or data.get("ips") or []
    elif isinstance(data, list):
        items = data
    else:
        items = None
    parsed: list[str] = []
    if isinstance(items, list):
        for item in items:
            ip_port = _extract_ip_port(item)
            if ip_port and _IP_PORT_RE.fullmatch(ip_port):
                parsed.append(ip_port)
    if parsed:
        return parsed
    # Fallback: plain text, one ip:port per line.
    for line in body.splitlines():
        line = line.strip().strip(",")
        if _IP_PORT_RE.fullmatch(line):
            parsed.append(line)
    return parsed


def _extract_ip_port(item) -> Optional[str]:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return None
    # Common keys: server="ip:port", ip="..." + port=...
    server = item.get("server") or item.get("proxy") or item.get("addr")
    if isinstance(server, str) and ":" in server:
        return server.strip()
    ip = item.get("ip")
    port = item.get("port")
    if ip and port:
        return f"{ip}:{port}"
    return None


def _redact_for_log(text: str) -> str:
    # Drop anything that looks like the apikey query string param.
    return re.sub(r"(key|apikey|token|password)=[^&\s]+", r"\1=[redacted]", text, flags=re.IGNORECASE)
