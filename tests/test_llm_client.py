"""Cliente de modelos del orquestador: formato de cada proveedor y rotación de claves."""

from typing import Any

import pytest

from app.orchestrator.llm import (
    HttpLlmClient,
    LlmInvalidKey,
    LlmRateLimited,
    ToolCall,
    ToolDef,
    Turn,
)

TOOL = ToolDef(
    "read_file", "Lee", {"type": "object", "properties": {}, "additionalProperties": False}
)


def test_gemini_envia_herramientas_sin_additional_properties_y_lee_function_call() -> None:
    seen: dict[str, Any] = {}

    def post(url: str, headers: dict[str, str], body: dict[str, Any]) -> Any:
        seen.update(url=url, headers=headers, body=body)
        return (
            200,
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"functionCall": {"name": "read_file", "args": {"a": 1}}}]
                        }
                    }
                ],
                "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 3},
            },
            None,
        )

    reply = HttpLlmClient(post).complete(
        provider="google",
        api_model="gemini-2.5-pro",
        secret="k",
        system="sys",
        turns=[Turn("user", "hola")],
        tools=[TOOL],
    )
    assert reply.calls[0].name == "read_file" and reply.calls[0].args == {"a": 1}
    assert (reply.input_tokens, reply.output_tokens) == (7, 3)
    assert "gemini-2.5-pro:generateContent" in seen["url"]
    assert seen["headers"] == {"x-goog-api-key": "k"}
    decl = seen["body"]["tools"][0]["functionDeclarations"][0]
    assert "additionalProperties" not in decl["parameters"]


def test_claude_formato_de_mensajes_y_resultados_de_herramienta() -> None:
    seen: dict[str, Any] = {}

    def post(url: str, headers: dict[str, str], body: dict[str, Any]) -> Any:
        seen.update(body=body, headers=headers)
        return (
            200,
            {"content": [{"type": "text", "text": "listo"}], "usage": {"input_tokens": 4}},
            None,
        )

    call = ToolCall("tu1", "read_file", {"path": "x"})
    reply = HttpLlmClient(post).complete(
        provider="anthropic",
        api_model="claude-sonnet-5-5",
        secret="k",
        system="sys",
        turns=[
            Turn("user", "hola"),
            Turn("assistant", "", [call]),
            Turn("user", "", results=[(call, "ok")]),
        ],
        tools=[TOOL],
    )
    assert reply.text == "listo" and reply.input_tokens == 4
    msgs = seen["body"]["messages"]
    assert msgs[1]["content"][0]["type"] == "tool_use"
    assert msgs[2]["content"][0] == {"type": "tool_result", "tool_use_id": "tu1", "content": "ok"}
    assert seen["headers"]["x-api-key"] == "k"


@pytest.mark.parametrize(
    ("status", "exc"), [(429, LlmRateLimited), (401, LlmInvalidKey), (403, LlmInvalidKey)]
)
def test_errores_del_proveedor_son_genericos_y_sin_la_clave(
    status: int, exc: type[Exception]
) -> None:
    client = HttpLlmClient(lambda *_: (status, {}, 5.0))
    with pytest.raises(exc) as info:
        client.complete(
            provider="anthropic",
            api_model="m",
            secret="clave-super-secreta",
            system="s",
            turns=[Turn("user", "x")],
            tools=[],
        )
    assert "clave-super-secreta" not in str(info.value)


def test_pick_model_elige_el_mas_reciente_y_estable_de_la_familia() -> None:
    from app.orchestrator.llm import pick_model

    names = [
        "gemini-1.5-pro",
        "gemini-2.5-pro",
        "gemini-3-pro-preview",
        "gemini-2.5-flash",
        "gemini-2.5-pro-exp",
    ]
    assert pick_model(names, "pro", "gemini-9-pro") == "gemini-2.5-pro"
    assert pick_model(names, "flash", "x") == "gemini-2.5-flash"
    assert pick_model(names, "pro", "gemini-2.5-pro") == "gemini-1.5-pro"
    assert pick_model(["otra"], "pro", "x") is None


def test_si_el_modelo_no_existe_se_descubre_uno_equivalente_y_se_recuerda() -> None:
    from app.orchestrator import llm as llm_mod
    from app.orchestrator.llm import LlmModelNotFound, LlmReply, complete_with_pool
    from app.services.key_pool import AcquiredKey

    class Pool:
        def acquire(self, provider: str, model: str) -> AcquiredKey:
            return AcquiredKey("k", provider, "k", model, "secreto")

        def report_usage(self, *a: Any, **k: Any) -> None: ...

    class Client:
        def __init__(self) -> None:
            self.seen: list[str] = []

        def complete(self, **kw: Any) -> LlmReply:
            self.seen.append(kw["api_model"])
            if kw["api_model"] == "gemini-2.5-pro":
                raise LlmModelNotFound(kw["api_model"])
            return LlmReply("ok", [], 1, 1)

        def discover(self, provider: str, secret: str, logical_id: str, bad: str) -> str:
            return "gemini-3-pro"

    llm_mod._OVERRIDES.clear()
    c = Client()
    r = complete_with_pool(
        Pool(),  # type: ignore[arg-type]
        c,  # type: ignore[arg-type]
        model_ids=["gemini-pro"],
        system="s",
        turns=[Turn("user", "x")],
        tools=[],
    )
    assert r.text == "ok" and c.seen == ["gemini-2.5-pro", "gemini-3-pro"]
    complete_with_pool(
        Pool(),  # type: ignore[arg-type]
        c,  # type: ignore[arg-type]
        model_ids=["gemini-pro"],
        system="s",
        turns=[Turn("user", "x")],
        tools=[],
    )
    assert c.seen[-1] == "gemini-3-pro"  # recordado: no vuelve a probar el que no existe
    llm_mod._OVERRIDES.clear()
