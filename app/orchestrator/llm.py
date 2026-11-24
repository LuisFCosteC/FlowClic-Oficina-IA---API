"""Cliente de modelos del orquestador (Fase 2): Gemini y Claude con herramientas.

Sin SDKs: solo HTTPS a URLs fijas de los proveedores. La clave sale de la bolsa global (KeyPool) y
NUNCA aparece en logs, errores ni mensajes: los errores son genéricos y no copian el cuerpo del
proveedor. La salida del modelo es entrada NO confiable (la valida quien la usa).
"""

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.models_catalog import MODELS_CATALOG
from app.errors import AppError
from app.services.key_pool import KeyPool

_TIMEOUT = 120.0
_MAX_KEYS_PER_CALL = 12


class LlmError(Exception):
    """Fallo del proveedor (red, 5xx, respuesta rara). El texto es genérico."""


class LlmRateLimited(LlmError):
    def __init__(self, retry_after: float | None = None) -> None:
        super().__init__("El proveedor limitó la petición (429)")
        self.retry_after = retry_after


class LlmModelNotFound(LlmError):
    """El proveedor no conoce ese modelo (404) con esta clave."""

    def __init__(self, api_model: str) -> None:
        super().__init__(f"El modelo «{api_model}» no está disponible con tu clave")
        self.api_model = api_model


class LlmInvalidKey(LlmError):
    def __init__(self, status: int) -> None:
        super().__init__(f"El proveedor rechazó la clave (HTTP {status})")
        self.status = status


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema simple: type/properties/required/items/enum


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class Turn:
    """Un mensaje de la conversación en formato neutro."""

    role: str  # "user" | "assistant"
    text: str = ""
    calls: list[ToolCall] = field(default_factory=list)  # solo assistant
    results: list[tuple[ToolCall, str]] = field(default_factory=list)  # solo user (tras tools)


@dataclass(frozen=True)
class LlmReply:
    text: str
    calls: list[ToolCall]
    input_tokens: int = 0
    output_tokens: int = 0


class LlmClient(Protocol):
    def complete(
        self,
        *,
        provider: str,
        api_model: str,
        secret: str,
        system: str,
        turns: list[Turn],
        tools: list[ToolDef],
    ) -> LlmReply: ...

    def discover(self, provider: str, secret: str, logical_id: str, bad_model: str) -> str | None:
        """Nombre real de un modelo equivalente que SÍ ofrezca la clave (o None)."""
        ...


Post = Callable[[str, dict[str, str], dict[str, Any]], tuple[int, dict[str, Any], float | None]]


def default_post(
    url: str, headers: dict[str, str], body: dict[str, Any]
) -> tuple[int, dict[str, Any], float | None]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 - URLs fijas https de los proveedores
        url, data=data, headers={"content-type": "application/json", **headers}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        retry = exc.headers.get("Retry-After") if exc.headers else None
        try:
            wait = float(retry) if retry is not None else None
        except ValueError:
            wait = None
        return exc.code, {}, wait
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise LlmError("No se pudo contactar con el proveedor") from None


def _check_status(status: int, retry: float | None, api_model: str = "") -> None:
    if status == 404 and api_model:
        raise LlmModelNotFound(api_model)
    if status == 429:
        raise LlmRateLimited(retry)
    if status in (401, 403):
        raise LlmInvalidKey(status)
    if status >= 400:
        # Google responde 400 tanto a una clave mala como a una petición mala: se distingue
        # por el cuerpo en `_google`; aquí es un error genérico.
        raise LlmError(f"El proveedor respondió HTTP {status}")


def _schema(params: dict[str, Any]) -> dict[str, Any]:
    """Gemini no admite `additionalProperties`; se quita en todo el árbol."""
    out: dict[str, Any] = {}
    for k, v in params.items():
        if k == "additionalProperties":
            continue
        if isinstance(v, dict):
            out[k] = _schema(v)
        else:
            out[k] = v
    return out


class HttpLlmClient:
    def __init__(self, post: Post = default_post) -> None:
        self._post = post

    def complete(
        self,
        *,
        provider: str,
        api_model: str,
        secret: str,
        system: str,
        turns: list[Turn],
        tools: list[ToolDef],
    ) -> LlmReply:
        if provider == "google":
            return self._google(api_model, secret, system, turns, tools)
        if provider == "anthropic":
            return self._anthropic(api_model, secret, system, turns, tools)
        raise LlmError(f"Proveedor sin soporte en el orquestador: {provider}")

    def discover(self, provider: str, secret: str, logical_id: str, bad_model: str) -> str | None:
        try:
            if provider == "google":
                return self._discover_google(secret, logical_id, bad_model)
            if provider == "anthropic":
                return self._discover_anthropic(secret, logical_id, bad_model)
        except (LlmError, OSError, ValueError):
            return None
        return None

    def _get(self, url: str, headers: dict[str, str]) -> dict[str, Any]:
        req = urllib.request.Request(url, headers=headers)  # noqa: S310 - URLs fijas https
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
                data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                return data
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            raise LlmError("No se pudo consultar los modelos del proveedor") from None

    def _discover_google(self, secret: str, logical_id: str, bad_model: str) -> str | None:
        data = self._get(
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
            {"x-goog-api-key": secret},
        )
        names = [
            str(m.get("name", "")).removeprefix("models/")
            for m in data.get("models", [])
            if "generateContent" in (m.get("supportedGenerationMethods") or [])
        ]
        return pick_model(names, "pro" if "pro" in logical_id else "flash", bad_model)

    def _discover_anthropic(self, secret: str, logical_id: str, bad_model: str) -> str | None:
        data = self._get(
            "https://api.anthropic.com/v1/models?limit=100",
            {"x-api-key": secret, "anthropic-version": "2023-06-01"},
        )
        names = [str(m.get("id", "")) for m in data.get("data", [])]
        family = next((f for f in ("opus", "sonnet", "haiku") if f in logical_id), "sonnet")
        return pick_model(names, family, bad_model)

    # ── Gemini ───────────────────────────────────────────────────────────────────────────────
    def _google(
        self, model: str, secret: str, system: str, turns: list[Turn], tools: list[ToolDef]
    ) -> LlmReply:
        contents: list[dict[str, Any]] = []
        for t in turns:
            if t.role == "assistant":
                parts: list[dict[str, Any]] = []
                if t.text:
                    parts.append({"text": t.text})
                parts += [{"functionCall": {"name": c.name, "args": c.args}} for c in t.calls]
                contents.append({"role": "model", "parts": parts or [{"text": "."}]})
            elif t.results:
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {"functionResponse": {"name": c.name, "response": {"result": out}}}
                            for c, out in t.results
                        ],
                    }
                )
            else:
                contents.append({"role": "user", "parts": [{"text": t.text}]})
        body: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
        }
        if tools:
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": d.name,
                            "description": d.description,
                            "parameters": _schema(d.parameters),
                        }
                        for d in tools
                    ]
                }
            ]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        status, data, retry = self._post(url, {"x-goog-api-key": secret}, body)
        if status == 400 and not data:
            raise LlmInvalidKey(400)  # el proveedor responde 400 a una clave inválida
        _check_status(status, retry, model)
        cands = data.get("candidates") or []
        parts_out = (cands[0].get("content", {}).get("parts") if cands else None) or []
        text = "".join(str(p["text"]) for p in parts_out if "text" in p)
        calls = [
            ToolCall(
                f"c{i}", str(p["functionCall"]["name"]), dict(p["functionCall"].get("args") or {})
            )
            for i, p in enumerate(parts_out)
            if "functionCall" in p
        ]
        usage = data.get("usageMetadata") or {}
        return LlmReply(
            text.strip(),
            calls,
            int(usage.get("promptTokenCount") or 0),
            int(usage.get("candidatesTokenCount") or 0),
        )

    # ── Claude ───────────────────────────────────────────────────────────────────────────────
    def _anthropic(
        self, model: str, secret: str, system: str, turns: list[Turn], tools: list[ToolDef]
    ) -> LlmReply:
        messages: list[dict[str, Any]] = []
        for t in turns:
            if t.role == "assistant":
                blocks: list[dict[str, Any]] = []
                if t.text:
                    blocks.append({"type": "text", "text": t.text})
                blocks += [
                    {"type": "tool_use", "id": c.id, "name": c.name, "input": c.args}
                    for c in t.calls
                ]
                messages.append(
                    {"role": "assistant", "content": blocks or [{"type": "text", "text": "."}]}
                )
            elif t.results:
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": c.id, "content": out}
                            for c, out in t.results
                        ],
                    }
                )
            else:
                messages.append({"role": "user", "content": t.text})
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
        }
        if tools:
            body["tools"] = [
                {"name": d.name, "description": d.description, "input_schema": d.parameters}
                for d in tools
            ]
        status, data, retry = self._post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": secret, "anthropic-version": "2023-06-01"},
            body,
        )
        _check_status(status, retry, model)
        blocks_out = data.get("content") or []
        text = "".join(str(b["text"]) for b in blocks_out if b.get("type") == "text")
        calls = [
            ToolCall(str(b["id"]), str(b["name"]), dict(b.get("input") or {}))
            for b in blocks_out
            if b.get("type") == "tool_use"
        ]
        usage = data.get("usage") or {}
        return LlmReply(
            text.strip(),
            calls,
            int(usage.get("input_tokens") or 0),
            int(usage.get("output_tokens") or 0),
        )


_UNSTABLE = ("preview", "exp", "latest", "tts", "image", "live", "thinking", "audio", "embed")
# id lógico del catálogo → nombre real descubierto cuando el configurado no existe
_OVERRIDES: dict[str, str] = {}


def _version(name: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+(?:\.\d+)?", name)
    out: list[int] = []
    for n in nums[:2]:
        out += [int(x) for x in n.split(".")]
    return tuple(out)


def pick_model(names: list[str], family: str, bad: str) -> str | None:
    """El modelo más reciente y estable de una familia (pro/flash/opus/sonnet/haiku)."""
    pool = [n for n in names if family in n and n != bad]
    stable = [n for n in pool if not any(u in n for u in _UNSTABLE)]
    ranked = sorted(stable or pool, key=lambda n: (_version(n), n), reverse=True)
    return ranked[0] if ranked else None


def provider_of(model_id: str) -> tuple[str, str] | None:
    """(proveedor, nombre exacto de API) de un id lógico del catálogo."""
    for m in MODELS_CATALOG:
        if m.id == model_id:
            return m.provider, m.api_model
    return None


def complete_with_pool(
    pool: KeyPool,
    client: LlmClient,
    *,
    model_ids: list[str],
    system: str,
    turns: list[Turn],
    tools: list[ToolDef],
    agent_id: str | None = None,
) -> LlmReply:
    """Llama al primer modelo con clave usable. 429 → siguiente clave; clave mala → INVALID.

    Prueba `model_ids` en orden (principal y respaldo). Sin clave para ninguno →
    `NO_KEY_AVAILABLE` (y el agente pasa a SLEEP_QUOTA).
    """
    last: AppError | None = None
    for model_id in model_ids:
        found = provider_of(model_id)
        if found is None:
            continue
        provider, api_model = found
        api_model = _OVERRIDES.get(model_id, api_model)
        for _ in range(_MAX_KEYS_PER_CALL):
            try:
                key = (
                    pool.acquire_for_agent(agent_id, provider, model_id)
                    if agent_id
                    else pool.acquire(provider, model_id)
                )
            except AppError as exc:
                last = exc
                break
            try:
                reply = client.complete(
                    provider=provider,
                    api_model=api_model,
                    secret=key.secret,
                    system=system,
                    turns=turns,
                    tools=tools,
                )
            except LlmRateLimited as exc:
                pool.report_exhausted(
                    key.key_id, model_id, retry_after_seconds=exc.retry_after, error_code="429"
                )
                continue
            except LlmInvalidKey as exc:
                pool.report_invalid(key.key_id, str(exc.status))
                continue
            except LlmModelNotFound as exc:
                alt = client.discover(provider, key.secret, model_id, api_model)
                if alt is None:
                    raise
                print(
                    f"[ORQUESTADOR] El modelo «{exc.api_model}» no existe para tu clave: "
                    f"uso «{alt}» para {model_id}.",
                    flush=True,
                )
                _OVERRIDES[model_id] = alt
                api_model = alt
                continue
            pool.report_usage(key.key_id, model_id, reply.input_tokens, reply.output_tokens, 0.0)
            return reply
    if last is not None:
        raise last
    raise AppError("NO_KEY_AVAILABLE", "Ningún modelo del agente tiene una clave disponible")
