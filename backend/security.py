"""Request checks for an API that has no login and only listens on this machine.

- Host must be this machine (localhost, 127.0.0.1 or [::1] with the configured port) or one of
  the configured addresses. That blocks DNS rebinding, where a web page renames its own domain
  to 127.0.0.1 and reads the API as if it were same-origin.
- Requests that change something (POST, PUT, PATCH, DELETE) need the X-Requested-With header.
  A page on another site can't add that header without a CORS preflight, which CORS refuses.
  When the browser sends Origin (or Referer), it has to be one of ours too.
"""

import logging
import re
from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from config import settings

logger = logging.getLogger(__name__)

CSRF_HEADER = "X-Requested-With"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOOPBACK_NAMES = ("localhost", "127.0.0.1", "[::1]")


def _netloc(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"{host.lower()}:{port}"


def allowed_hosts() -> set[str]:
    hosts = {f"{name}:{settings.PORT}" for name in LOOPBACK_NAMES}
    for url in (settings.BACKEND_URL, settings.WEB_SETUP_URL, *settings.CORS_ORIGINS):
        netloc = _netloc(url)
        if netloc:
            hosts.add(netloc)
    return hosts


def _host_header(value: str) -> str | None:
    """The Host header as host:port (port 80 when it has none), or None when it's malformed."""
    match = re.fullmatch(r"(\[[0-9a-fA-F:.]+\]|[A-Za-z0-9.-]+)(?::(\d{1,5}))?", value.strip())
    if not match:
        return None
    return f"{match.group(1).lower()}:{int(match.group(2) or 80)}"


def _same_site(url: str, hosts: set[str]) -> bool:
    netloc = _netloc(url)
    return netloc is not None and netloc in hosts


class LocalRequestGuard:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        hosts = allowed_hosts()
        host = _host_header(headers.get("host", ""))
        if host not in hosts:
            logger.warning("Refused a request with an unexpected Host header")
            await PlainTextResponse("Unknown host", status_code=421)(scope, receive, send)
            return
        method = scope.get("method", "GET").upper()
        if scope["type"] == "http" and method not in SAFE_METHODS:
            reason = self._cross_site_reason(headers, hosts)
            if reason:
                logger.warning("Refused %s %s: %s", method, scope.get("path", ""), reason)
                await PlainTextResponse(reason, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)

    @staticmethod
    def _cross_site_reason(headers: dict[str, str], hosts: set[str]) -> str | None:
        if not headers.get(CSRF_HEADER.lower()):
            return f"Missing {CSRF_HEADER} header"
        origin = headers.get("origin")
        if origin is not None:
            return None if _same_site(origin, hosts) else "Cross-site request"
        referer = headers.get("referer")
        if referer is not None and not _same_site(referer, hosts):
            return "Cross-site request"
        return None


class RedactQueryParams(logging.Filter):
    """Keeps OAuth codes and state out of the access log (they arrive in the callback's query)."""

    _SECRET = re.compile(r"\b(code|state)=[^&\s\"]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = tuple(
                self._SECRET.sub(r"\1=[redacted]", a) if isinstance(a, str) else a for a in record.args
            )
        return True
