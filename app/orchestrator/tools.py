"""Herramientas que el orquestador ofrece a los agentes (GM01).

`gemini_models`: lista los modelos Gemini que el proveedor ofrece de verdad (models.list). Usa la
bolsa global de claves (KeyPool): toma la primera clave usable y, ante 429 o clave rechazada, pasa
a la siguiente. NUNCA devuelve, registra ni incluye en errores el valor de la clave.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.domain.models_catalog import MODELS_CATALOG
from app.domain.schemas import CamelModel
from app.errors import AppError
from app.services.key_pool import KeyPool

# Pseudo-modelo con el que se contabiliza la llamada: no gasta ni agota la cuota de ningún
# modelo real del catálogo.
LIST_MODEL = "models.list"
_MAX_ATTEMPTS = 20
_PAGE_SIZE = 200
_MAX_PAGES = 5
_TIMEOUT = 10.0
_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


GEMINI_MODELS_SPEC = ToolSpec(
    name="gemini_models",
    description=(
        "Lista los modelos Gemini disponibles (nombre de API, límites de tokens y si admiten "
        "generateContent) con una clave de la bolsa global. No consume tokens."
    ),
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
)
TOOLS: dict[str, ToolSpec] = {GEMINI_MODELS_SPEC.name: GEMINI_MODELS_SPEC}


class GeminiModelInfo(CamelModel):
    name: str  # "models/gemini-2.5-pro"
    api_model: str  # "gemini-2.5-pro" (lo que va en el campo apiModel del catálogo)
    display_name: str
    input_token_limit: int | None
    output_token_limit: int | None
    supports_generate_content: bool
    catalog_id: str | None  # id lógico del catálogo que lo usa hoy (None = sin usar)


@dataclass(frozen=True)
class HttpResult:
    status: int
    body: dict[str, Any]
    retry_after: float | None = None


HttpGet = Callable[[str, str], HttpResult]  # (url, api_key) -> resultado


def default_http_get(url: str, api_key: str) -> HttpResult:
    req = urllib.request.Request(url, headers={"x-goog-api-key": api_key})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
            return HttpResult(resp.status, json.loads(resp.read().decode("utf-8")))
    except urllib.error.HTTPError as exc:
        retry = exc.headers.get("Retry-After") if exc.headers else None
        try:
            wait = float(retry) if retry is not None else None
        except ValueError:
            wait = None
        return HttpResult(exc.code, {}, wait)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise AppError("UPSTREAM_ERROR", "No se pudo contactar con Gemini") from None


def _parse(items: list[dict[str, Any]]) -> list[GeminiModelInfo]:
    in_use = {m.api_model: m.id for m in MODELS_CATALOG if m.provider == "google"}
    out: list[GeminiModelInfo] = []
    for item in items:
        name = str(item.get("name", ""))
        short = name.removeprefix("models/")
        if not short.startswith("gemini"):
            continue
        methods = item.get("supportedGenerationMethods") or []
        out.append(
            GeminiModelInfo(
                name=name,
                api_model=short,
                display_name=str(item.get("displayName", short)),
                input_token_limit=item.get("inputTokenLimit"),
                output_token_limit=item.get("outputTokenLimit"),
                supports_generate_content="generateContent" in methods,
                catalog_id=in_use.get(short),
            )
        )
    return sorted(out, key=lambda m: m.api_model)


def _fetch_all(api_key: str, http_get: HttpGet) -> HttpResult | list[dict[str, Any]]:
    """Todas las páginas de models.list; si una falla devuelve ese resultado (no 200)."""
    items: list[dict[str, Any]] = []
    token = ""
    for _ in range(_MAX_PAGES):
        url = f"{_BASE}?pageSize={_PAGE_SIZE}" + (f"&pageToken={token}" if token else "")
        res = http_get(url, api_key)
        if res.status != 200:
            return res
        items += list(res.body.get("models", []))
        token = str(res.body.get("nextPageToken") or "")
        if not token:
            break
    return items


def gemini_models(pool: KeyPool, http_get: HttpGet = default_http_get) -> list[GeminiModelInfo]:
    """Herramienta `gemini_models`. Rota por la bolsa: 429 → siguiente; 400/401/403 → INVALID."""
    for _ in range(_MAX_ATTEMPTS):
        key = pool.acquire("google", LIST_MODEL)  # NO_KEY_AVAILABLE si no queda ninguna
        result = _fetch_all(key.secret, http_get)
        if isinstance(result, list):
            pool.report_usage(key.key_id, LIST_MODEL, 0, 0, 0.0)
            return _parse(result)
        if result.status == 429:
            pool.report_exhausted(
                key.key_id, LIST_MODEL, retry_after_seconds=result.retry_after, error_code="429"
            )
        elif result.status in (400, 401, 403):  # Google responde 400 a una clave inválida
            pool.report_invalid(key.key_id, str(result.status))
        else:
            raise AppError("UPSTREAM_ERROR", f"Gemini respondió HTTP {result.status}")
    raise AppError("UPSTREAM_ERROR", "No se pudo listar los modelos con ninguna clave")
