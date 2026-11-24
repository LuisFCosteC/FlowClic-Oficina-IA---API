"""Catálogo de modelos registrables en un agente (PLAN §19.1).

Editable sin migración. `id` es el identificador LÓGICO que ven agentes y tickets; `api_model` es
el nombre exacto que se envía al proveedor. Los de Gemini son un valor inicial: la herramienta
`gemini_models` (app/orchestrator/tools.py) lista los que ofrece de verdad cada clave.
"""

from dataclasses import dataclass

from app.errors import validation_error


@dataclass(frozen=True)
class CatalogModel:
    id: str
    label: str
    provider: str
    api_model: str


MODELS_CATALOG: tuple[CatalogModel, ...] = (
    CatalogModel("claude-opus-5-5", "Claude Opus 5.5", "anthropic", "claude-opus-5-5"),
    CatalogModel("claude-sonnet-5-5", "Claude Sonnet 5.5", "anthropic", "claude-sonnet-5-5"),
    CatalogModel("claude-haiku-5-5", "Claude Haiku 5.5", "anthropic", "claude-haiku-5-5"),
    CatalogModel("gemini-pro", "Gemini Pro", "google", "gemini-2.5-pro"),
    CatalogModel("gemini-flash", "Gemini Flash", "google", "gemini-2.5-flash"),
)

MODEL_IDS = frozenset(m.id for m in MODELS_CATALOG)


def validate_model_ids(primary: str, fallback: str | None) -> None:
    """400 si el modelo principal o el de respaldo no están en el catálogo."""
    details = []
    if primary not in MODEL_IDS:
        details.append({"path": "model.primary", "message": f"modelo desconocido: {primary}"})
    if fallback is not None and fallback not in MODEL_IDS:
        details.append({"path": "model.fallback", "message": f"modelo desconocido: {fallback}"})
    if details:
        raise validation_error(f"{details[0]['path']}: {details[0]['message']}", details)
