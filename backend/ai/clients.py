"""HTTP clients for the two API styles: OpenAI-compatible and Anthropic."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Optional

import httpx

from ai.providers import KIND_ANTHROPIC, Provider
from mail.retry import send_with_retry

ANTHROPIC_VERSION = "2026-10-21"


class AIError(Exception):
    """A failure with a short code and a message that is safe to show the user."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class BatchRequest:
    custom_id: str
    system: str
    messages: list[dict]
    max_tokens: int
    schema: Optional[dict] = None


@dataclass
class BatchState:
    # "pending", "ended" or "failed"
    status: str
    detail: str = ""
    extra: dict = field(default_factory=dict)


def _check(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    if response.status_code in (401, 403):
        raise AIError("auth", "The provider rejected the API key.")
    if response.status_code == 404:
        raise AIError("not_found", "The model or endpoint wasn't found. Check the model and the base URL.")
    if response.status_code == 429 or response.status_code >= 500:
        raise AIError("unavailable", f"The AI provider isn't responding right now (HTTP {response.status_code}).")
    raise AIError("provider_error", f"The AI provider returned HTTP {response.status_code}.")


class AIClient:
    def __init__(self, provider: Provider, model: str, api_key: Optional[str], base_url: Optional[str],
                 http: httpx.AsyncClient):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = (base_url or provider.default_base_url).rstrip("/")
        self.http = http

    @property
    def supports_batch(self) -> bool:
        return self.provider.supports_batch

    @property
    def supports_pdf(self) -> bool:
        return self.provider.supports_pdf

    async def aclose(self) -> None:
        await self.http.aclose()

    async def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return await send_with_retry(self.http, method, f"{self.base_url}{path}", headers=self._headers(), **kwargs)
        except httpx.TransportError as exc:
            raise AIError("network", f"Couldn't reach {self.base_url}.") from exc

    def _headers(self) -> dict:
        raise NotImplementedError

    async def list_models(self) -> list[dict]:
        raise NotImplementedError

    async def complete(self, system: str, messages: list[dict], max_tokens: int,
                       schema: Optional[dict] = None, pdf: Optional[bytes] = None) -> Completion:
        raise NotImplementedError

    async def submit_batch(self, requests: list[BatchRequest]) -> str:
        raise AIError("no_batch", f"{self.provider.name} batches aren't supported.")

    async def batch_state(self, batch_id: str) -> BatchState:
        raise AIError("no_batch", f"{self.provider.name} batches aren't supported.")

    async def batch_results(self, batch_id: str) -> dict[str, Optional[str]]:
        raise AIError("no_batch", f"{self.provider.name} batches aren't supported.")


class OpenAICompatibleClient(AIClient):
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _body(self, system: str, messages: list[dict], max_tokens: int, schema: Optional[dict], json_mode: bool) -> dict:
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, *messages]}
        # OpenAI's newer models only accept max_completion_tokens; other compatible APIs use max_tokens.
        body["max_completion_tokens" if self.provider.id == "openai" else "max_tokens"] = max_tokens
        if schema is not None:
            body["response_format"] = (
                {"type": "json_object"} if json_mode
                else {"type": "json_schema", "json_schema": {"name": "result", "schema": schema, "strict": True}}
            )
        return body

    async def list_models(self) -> list[dict]:
        response = await self._send("GET", "/models")
        _check(response)
        return [{"id": m["id"], "name": m.get("name") or m["id"]} for m in response.json().get("data", []) if m.get("id")]

    async def complete(self, system, messages, max_tokens, schema=None, pdf=None) -> Completion:
        response = await self._send("POST", "/chat/completions", json=self._body(system, messages, max_tokens, schema, False))
        # Some compatible servers don't support JSON schemas; plain JSON mode is the fallback.
        if response.status_code == 400 and schema is not None:
            response = await self._send("POST", "/chat/completions", json=self._body(system, messages, max_tokens, schema, True))
        _check(response)
        data = response.json()
        usage = data.get("usage") or {}
        return Completion(
            text=(data["choices"][0]["message"].get("content") or "") if data.get("choices") else "",
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )

    async def submit_batch(self, requests: list[BatchRequest]) -> str:
        if not self.supports_batch:
            return await super().submit_batch(requests)
        lines = [
            json.dumps({
                "custom_id": r.custom_id, "method": "POST", "url": "/v1/chat/completions",
                "body": self._body(r.system, r.messages, r.max_tokens, r.schema, False),
            })
            for r in requests
        ]
        upload = await self._send(
            "POST", "/files", data={"purpose": "batch"},
            files={"file": ("batch.jsonl", "\n".join(lines).encode(), "application/jsonl")},
        )
        _check(upload)
        created = await self._send("POST", "/batches", json={
            "input_file_id": upload.json()["id"], "endpoint": "/v1/chat/completions", "completion_window": "24h",
        })
        _check(created)
        return created.json()["id"]

    async def batch_state(self, batch_id: str) -> BatchState:
        response = await self._send("GET", f"/batches/{batch_id}")
        _check(response)
        data = response.json()
        status = data.get("status")
        if status == "completed":
            return BatchState("ended", extra={"output_file_id": data.get("output_file_id")})
        if status in ("failed", "expired", "cancelled"):
            return BatchState("failed", detail=f"batch {status}")
        return BatchState("pending")

    async def batch_results(self, batch_id: str) -> dict[str, Optional[str]]:
        state = await self.batch_state(batch_id)
        file_id = state.extra.get("output_file_id")
        if not file_id:
            return {}
        response = await self._send("GET", f"/files/{file_id}/content")
        _check(response)
        results: dict[str, Optional[str]] = {}
        for line in response.text.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            reply = item.get("response") or {}
            body = reply.get("body") or {}
            ok = reply.get("status_code") == 200 and body.get("choices")
            results[item["custom_id"]] = body["choices"][0]["message"].get("content") if ok else None
        return results


class AnthropicClient(AIClient):
    def _headers(self) -> dict:
        return {"x-api-key": self.api_key or "", "anthropic-version": ANTHROPIC_VERSION}

    def _body(self, system: str, messages: list[dict], max_tokens: int, schema: Optional[dict],
              pdf: Optional[bytes] = None, native_schema: bool = True) -> dict:
        messages = [dict(m) for m in messages]
        # Document blocks are only valid in user messages, never assistant ones.
        user_indexes = [i for i, m in enumerate(messages) if m.get("role") == "user"]
        if pdf is not None and user_indexes:
            target = messages[user_indexes[-1]]
            text = target["content"]
            if isinstance(text, str):
                text = [{"type": "text", "text": text}]
            target["content"] = [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                "data": base64.b64encode(pdf).decode()}},
                *text,
            ]
        # No temperature/top_p/top_k: they return 400 on this API version.
        body = {"model": self.model, "max_tokens": max_tokens, "system": system, "messages": messages}
        if schema is not None and native_schema:
            body["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        return body

    async def list_models(self) -> list[dict]:
        models: list[dict] = []
        params = {"limit": 1000}
        for _ in range(10):
            response = await self._send("GET", "/models", params=params)
            _check(response)
            data = response.json()
            models += [{"id": m["id"], "name": m.get("display_name") or m["id"]} for m in data.get("data", [])]
            if not data.get("has_more"):
                break
            params = {"limit": 1000, "after_id": data.get("last_id")}
        return models

    @staticmethod
    def _text(message: dict) -> str:
        return "".join(block.get("text", "") for block in message.get("content", []) if block.get("type") == "text")

    async def complete(self, system, messages, max_tokens, schema=None, pdf=None) -> Completion:
        response = await self._send("POST", "/messages", json=self._body(system, messages, max_tokens, schema, pdf))
        # Models without native structured output still get the schema through the instructions.
        if response.status_code == 400 and schema is not None:
            response = await self._send("POST", "/messages", json=self._body(system, messages, max_tokens, schema, pdf, False))
        _check(response)
        data = response.json()
        usage = data.get("usage") or {}
        return Completion(self._text(data), usage.get("input_tokens", 0), usage.get("output_tokens", 0))

    async def submit_batch(self, requests: list[BatchRequest]) -> str:
        response = await self._send("POST", "/messages/batches", json={"requests": [
            {"custom_id": r.custom_id, "params": self._body(r.system, r.messages, r.max_tokens, r.schema)}
            for r in requests
        ]})
        _check(response)
        return response.json()["id"]

    async def batch_state(self, batch_id: str) -> BatchState:
        response = await self._send("GET", f"/messages/batches/{batch_id}")
        _check(response)
        status = response.json().get("processing_status")
        return BatchState("ended") if status == "ended" else BatchState("pending")

    async def batch_results(self, batch_id: str) -> dict[str, Optional[str]]:
        response = await self._send("GET", f"/messages/batches/{batch_id}/results")
        _check(response)
        results: dict[str, Optional[str]] = {}
        for line in response.text.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            result = item.get("result") or {}
            results[item["custom_id"]] = self._text(result.get("message") or {}) if result.get("type") == "succeeded" else None
        return results


def make_client(provider: Provider, model: str, api_key: Optional[str], base_url: Optional[str],
                http: httpx.AsyncClient) -> AIClient:
    cls = AnthropicClient if provider.kind == KIND_ANTHROPIC else OpenAICompatibleClient
    return cls(provider, model, api_key, base_url, http)
