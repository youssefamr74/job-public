"""Fake AI provider servers for tests, served through httpx.MockTransport. No real API is called."""

from __future__ import annotations

import json
from typing import Callable, Optional, Union

import httpx

from ai.providers import PROVIDERS
from ai.service import ActiveAI

Reply = Union[str, Callable[[dict], str], httpx.Response]


def answer(**fields) -> str:
    base = {"is_job_related": True, "company": None, "role": None, "status": "Applied",
            "interview_date": None, "job_id": None, "location": None}
    return json.dumps({**base, **fields})


def user_text(body: dict) -> str:
    """The text of the last user message in a chat or messages request body."""
    content = body["messages"][-1]["content"]
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if part.get("type") == "text")
    return content


class FakeServer:
    """Hands out replies in order (the last one repeats) and records every request."""

    models: list[str] = ["model-small", "model-large"]

    def __init__(self, replies: Optional[list[Reply]] = None, batch_polls_pending: int = 0):
        self.replies = list(replies or [answer()])
        self.requests: list[httpx.Request] = []
        self.completions: list[dict] = []
        self.batches: dict[str, dict] = {}
        self.batch_polls_pending = batch_polls_pending
        self._next_batch = 0

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport())

    def reply_for(self, body: dict) -> Union[str, httpx.Response]:
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return reply(body) if callable(reply) else reply

    def new_batch(self, entries: list[tuple[str, dict]]) -> str:
        self._next_batch += 1
        batch_id = f"batch_{self._next_batch}"
        self.batches[batch_id] = {"entries": entries, "polls": 0}
        return batch_id

    def batch_done(self, batch_id: str) -> bool:
        batch = self.batches[batch_id]
        batch["polls"] += 1
        return batch["polls"] > self.batch_polls_pending

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.route(request)

    def route(self, request: httpx.Request) -> httpx.Response:
        raise NotImplementedError


class FakeOpenAI(FakeServer):
    def route(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/v1")
        if request.method == "GET" and path == "/models":
            return httpx.Response(200, json={"object": "list", "data": [{"id": m, "object": "model"} for m in self.models]})
        if request.method == "POST" and path == "/chat/completions":
            body = json.loads(request.content)
            self.completions.append(body)
            reply = self.reply_for(body)
            if isinstance(reply, httpx.Response):
                return reply
            return httpx.Response(200, json={
                "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            })
        if request.method == "POST" and path == "/files":
            text = request.content.decode(errors="ignore")
            lines = [json.loads(line) for line in text.splitlines() if line.startswith("{")]
            batch_id = self.new_batch([(line["custom_id"], line["body"]) for line in lines])
            return httpx.Response(200, json={"id": f"file_{batch_id}"})
        if request.method == "POST" and path == "/batches":
            return httpx.Response(200, json={"id": json.loads(request.content)["input_file_id"].removeprefix("file_")})
        if request.method == "GET" and path.startswith("/batches/"):
            batch_id = path.split("/")[2]
            if not self.batch_done(batch_id):
                return httpx.Response(200, json={"id": batch_id, "status": "in_progress"})
            return httpx.Response(200, json={"id": batch_id, "status": "completed", "output_file_id": f"out_{batch_id}"})
        if request.method == "GET" and path.startswith("/files/out_"):
            batch_id = path.split("/")[2].removeprefix("out_")
            lines = []
            for custom_id, body in self.batches[batch_id]["entries"]:
                self.completions.append(body)
                content = self.reply_for(body)
                lines.append(json.dumps({"custom_id": custom_id, "response": {"status_code": 200, "body": {
                    "choices": [{"message": {"role": "assistant", "content": content}}]}}}))
            return httpx.Response(200, text="\n".join(lines))
        return httpx.Response(404, json={"error": {"message": "not found"}})


class FakeAnthropic(FakeServer):
    def route(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/v1")
        if request.method == "GET" and path == "/models":
            return httpx.Response(200, json={
                "data": [{"id": m, "display_name": m.title(), "type": "model"} for m in self.models],
                "has_more": False, "last_id": self.models[-1],
            })
        if request.method == "POST" and path == "/messages":
            body = json.loads(request.content)
            self.completions.append(body)
            reply = self.reply_for(body)
            if isinstance(reply, httpx.Response):
                return reply
            return httpx.Response(200, json={
                "type": "message", "role": "assistant", "content": [{"type": "text", "text": reply}],
                "usage": {"input_tokens": 50, "output_tokens": 20},
            })
        if request.method == "POST" and path == "/messages/batches":
            body = json.loads(request.content)
            batch_id = self.new_batch([(r["custom_id"], r["params"]) for r in body["requests"]])
            return httpx.Response(200, json={"id": batch_id, "processing_status": "in_progress"})
        if request.method == "GET" and path.startswith("/messages/batches/") and path.endswith("/results"):
            batch_id = path.split("/")[3]
            lines = []
            for custom_id, params in self.batches[batch_id]["entries"]:
                self.completions.append(params)
                text = self.reply_for(params)
                lines.append(json.dumps({"custom_id": custom_id, "result": {
                    "type": "succeeded", "message": {"content": [{"type": "text", "text": text}]}}}))
            return httpx.Response(200, text="\n".join(lines))
        if request.method == "GET" and path.startswith("/messages/batches/"):
            batch_id = path.split("/")[3]
            status = "ended" if self.batch_done(batch_id) else "in_progress"
            return httpx.Response(200, json={"id": batch_id, "processing_status": status})
        return httpx.Response(404, json={"error": {"message": "not found"}})


def fake_settings(provider_id: str = "openai", **overrides) -> ActiveAI:
    values = dict(
        provider=PROVIDERS[provider_id], model="model-small",
        api_key=None if provider_id == "ollama" else "sk-test-fake", base_url=None,
        privacy_mode="subject_sender", body_chars=500, use_batch=False, batch_threshold=50,
    )
    values.update(overrides)
    return ActiveAI(**values)
