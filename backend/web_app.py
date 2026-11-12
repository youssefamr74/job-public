"""Serves the built web app next to the API, so Jōb runs as one app on one port.

API paths and page paths overlap (/applications is both), so a GET that asks for HTML
gets the web app and everything else reaches the API.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

API_PAGES = ("/docs", "/redoc", "/openapi.json", "/mail/oauth/", "/data/export/")


def wants_web_page(request: Request) -> bool:
    if request.method not in ("GET", "HEAD"):
        return False
    path = request.url.path
    if any(path == page or path.startswith(page) for page in API_PAGES):
        return False
    return "text/html" in request.headers.get("accept", "")


def mount_web_app(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if not index.is_file():
        return
    root = dist.resolve()

    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="web-assets")

    @app.middleware("http")
    async def web_app_pages(request: Request, call_next):
        path = request.url.path
        if request.method in ("GET", "HEAD") and path != "/" and "." in path.rsplit("/", 1)[-1]:
            candidate = (dist / path.lstrip("/")).resolve()
            if candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
        if path == "/" or wants_web_page(request):
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return await call_next(request)
