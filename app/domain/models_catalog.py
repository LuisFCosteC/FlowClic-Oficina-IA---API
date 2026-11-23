"""Catálogo de modelos registrables en un agente (PLAN §19.1).

Editable sin migración. En la Fase 1 los modelos solo se REGISTRAN: nadie los llama.
Los ids exactos de Gemini se fijarán en la Fase 2.
"""

from dataclasses import dataclass

from app.errors import validation_error


@dataclass(frozen=True)
class CatalogModel:
    id: str
    label: str
    provider: str


MODELS_CATALOG: tuple[CatalogModel, ...] = (
    CatalogModel("claude-opus-5-5", "Claude Opus 5.5", "anthropic"),
    CatalogModel("claude-sonnet-5-5", "Claude Sonnet 5.5", "anthropic"),
    CatalogModel("claude-haiku-5-5", "Claude Haiku 5.5", "anthropic"),
    CatalogModel("gemini-pro", "Gemini Pro", "google"),
    CatalogModel("gemini-flash", "Gemini Flash", "google"),
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
