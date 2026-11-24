"""Orquestador (Fase 2): Sheldon reparte, los agentes trabajan, se revisa y se avisa al CEO."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.database import Database
from app.errors import AppError
from app.orchestrator.llm import LlmError, LlmReply, ToolCall, ToolDef, Turn
from app.orchestrator.runner import Orchestrator
from app.services.key_pool import AcquiredKey


class FakePool:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.usage = 0

    def acquire(self, provider: str, model: str) -> AcquiredKey:
        if self.fail:
            raise AppError("NO_KEY_AVAILABLE", "sin clave")
        return AcquiredKey("k1", provider, "k", model, "secreto-de-prueba")

    def acquire_for_agent(self, agent_id: str, provider: str, model: str) -> AcquiredKey:
        return self.acquire(provider, model)

    def report_usage(self, *a: Any, **k: Any) -> None:
        self.usage += 1

    def report_exhausted(self, *a: Any, **k: Any) -> None: ...

    def report_invalid(self, *a: Any, **k: Any) -> None: ...


class FakeLlm:
    """Responde según las herramientas ofrecidas; `worker_id` es a quien Sheldon reparte."""

    def __init__(self, worker_id: str = "", reject_first: bool = False) -> None:
        self.worker_id = worker_id
        self.reject_first = reject_first
        self.rejected = False

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
        assert secret == "secreto-de-prueba"
        names = {t.name for t in tools}
        step = sum(1 for t in turns if t.role == "assistant")

        def call(name: str, **args: Any) -> LlmReply:
            return LlmReply("", [ToolCall(f"c{step}", name, args)], 10, 5)

        if "create_subtask" in names:
            if step == 0:
                return call(
                    "create_subtask",
                    title="Analizar el proyecto",
                    objective="Revisar el código",
                    acceptance_criteria=["Informe claro"],
                    assigned_agent_id=self.worker_id,
                    priority="HIGH",
                )
            return call("finish_planning")
        if "submit_report" in names:
            return call("submit_report", report="Informe: todo analizado")
        if "approve" in names:
            if self.reject_first and not self.rejected:
                self.rejected = True
                return call("reject", reason="Falta detalle")
            return call("approve", comment="Cumple")
        if "deliver" in names:
            return call("deliver", summary="Resumen para el CEO")
        if "reply" in names:
            return call("reply", text="Entendido, me ocupo")
        return LlmReply("sin herramienta", [], 1, 1)


class BoomLlm:
    def complete(self, **k: Any) -> LlmReply:
        raise LlmError("caído")


def mk(c: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    r = c.post("/api/agents", json={"name": name, "role": "R", **extra})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


@pytest.fixture
def team(client: TestClient) -> dict[str, Any]:
    assert client.post("/api/admin/projects", json={"id": "web", "name": "Web"}).status_code == 201
    cto = mk(client, "Sheldon", roleType="CTO")
    senior = mk(
        client,
        "Leonard",
        roleType="DEV_BACKEND",
        reportsTo=cto["id"],
        permissions={
            "ticketTransitions": [["IN_SENIOR_REVIEW", "IN_QA"], ["IN_SENIOR_REVIEW", "RETURNED"]]
        },
    )
    worker = mk(client, "Howard", roleType="CUSTOM", reportsTo=senior["id"])
    return {"cto": cto, "senior": senior, "worker": worker}


def make_request(c: TestClient) -> dict[str, Any]:
    r = c.post(
        "/api/tickets",
        json={"title": "Análisis", "requirement": "Analiza el proyecto", "projectId": "web"},
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def run(db: Database, llm: Any, pool: FakePool | None = None, ticks: int = 8) -> Orchestrator:
    orch = Orchestrator(db, None, pool or FakePool(), llm, retry_seconds=0)  # type: ignore[arg-type]
    for _ in range(ticks):
        orch.tick()
    return orch


def statuses(c: TestClient) -> dict[str, str]:
    return {t["title"]: t["status"] for t in c.get("/api/tickets").json()}


def test_flujo_completo_termina_en_revision_cto_y_nunca_en_hecho(
    client: TestClient, migrated_db: Database, team: dict[str, Any]
) -> None:
    req = make_request(client)
    run(migrated_db, FakeLlm(team["worker"]["id"]))
    st = statuses(client)
    assert st["Análisis"] == "IN_REVIEW"  # Revisión CTO: solo el CEO lo pasa a HECHO
    assert st["Analizar el proyecto"] == "IN_REVIEW"
    assert "DONE" not in st.values()
    # terminado y aprobado: nadie queda trabajando, todos vuelven a la zona de descanso
    assert {a["status"] for a in client.get("/api/agents").json()} == {"IDLE"}
    thread = client.get("/api/messages", params={"scope": "GLOBAL"}).json()
    assert any("Resumen para el CEO" in e["body"] for e in thread)
    kids = [t for t in client.get("/api/tickets").json() if t["parentTicketId"] == req["id"]]
    assert len(kids) == 1 and kids[0]["assignedAgentId"] == team["worker"]["id"]
    w_thread = client.get("/api/messages", params={"agentId": team["worker"]["id"]}).json()
    assert any("IN_SENIOR_REVIEW" in e["body"] for e in w_thread)  # pasó por revisión senior


def test_el_revisor_puede_devolver_y_el_agente_corrige(
    client: TestClient, migrated_db: Database, team: dict[str, Any]
) -> None:
    make_request(client)
    run(migrated_db, FakeLlm(team["worker"]["id"], reject_first=True), ticks=14)
    st = statuses(client)
    assert st["Análisis"] == "IN_REVIEW" and st["Analizar el proyecto"] == "IN_REVIEW"
    w_thread = client.get("/api/messages", params={"agentId": team["worker"]["id"]}).json()
    assert any("RETURNED" in e["body"] for e in w_thread)


def test_orden_del_ceo_recibe_respuesta(
    client: TestClient, migrated_db: Database, team: dict[str, Any]
) -> None:
    r = client.post(
        "/api/messages", json={"scope": "GLOBAL", "body": "¿cómo vamos?", "kind": "QUESTION"}
    )
    assert r.status_code == 201
    run(migrated_db, FakeLlm(), ticks=2)
    thread = client.get("/api/messages", params={"scope": "GLOBAL"}).json()
    assert any(e["authorType"] == "AGENT" and "Entendido" in e["body"] for e in thread)
    assert next(e for e in thread if e["id"] == r.json()["id"])["status"] == "DONE"


def test_sin_clave_no_avanza_y_avisa_una_sola_vez(
    client: TestClient, migrated_db: Database, team: dict[str, Any]
) -> None:
    make_request(client)
    run(migrated_db, FakeLlm(team["worker"]["id"]), FakePool(fail=True), ticks=10)
    thread = client.get("/api/messages", params={"scope": "GLOBAL"}).json()
    avisos = [e for e in thread if e["authorType"] == "SYSTEM"]
    assert len(avisos) == 1 and "no pudo avanzar" in avisos[0]["body"]
    assert "DONE" not in statuses(client).values()


def test_los_agentes_no_leen_env_ni_salen_del_espacio(
    client: TestClient, migrated_db: Database, team: dict[str, Any], tmp_path: Path
) -> None:
    from app.orchestrator import fs_tools
    from app.repositories import agents_repo

    (tmp_path / "ok.txt").write_text("hola", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRETO=1", encoding="utf-8")
    r = client.put(
        "/api/admin/workspaces/w1",
        json={"name": "W", "path": str(tmp_path), "projectId": "web", "kind": "other"},
    )
    assert r.status_code in (200, 201), r.text
    howard = agents_repo.get_agent(migrated_db, team["worker"]["id"])
    assert howard is not None
    assert fs_tools.visible_workspaces(migrated_db, howard) == []  # sin permisos no ve nada
    p = client.patch(
        f"/api/agents/{howard.id}",
        json={"permissions": {"folderAccess": {"other": "read"}, "projectScope": "ALL"}},
    )
    assert p.status_code == 200, p.text
    howard = agents_repo.get_agent(migrated_db, howard.id)
    assert howard is not None
    assert fs_tools.read_file(migrated_db, howard, "w1", "ok.txt") == "hola"
    with pytest.raises(AppError):
        fs_tools.read_file(migrated_db, howard, "w1", ".env")
    with pytest.raises(AppError):
        fs_tools.read_file(migrated_db, howard, "w1", "../fuera.txt")
    assert ".env" not in fs_tools.list_dir(migrated_db, howard, "w1")
    # Windows: flujos alternativos, nombres cortos 8.3 y punto/espacio final no esquivan la lista
    for sneaky in ("ok.txt:secreto", "ENV~1", ".env.", ".env ", "a/../.env", "x<y"):
        with pytest.raises(AppError):
            fs_tools.read_file(migrated_db, howard, "w1", sneaky)


def test_error_del_modelo_no_rompe_el_tick(
    client: TestClient, migrated_db: Database, team: dict[str, Any]
) -> None:
    make_request(client)
    run(migrated_db, BoomLlm(), ticks=3)
    assert statuses(client)["Análisis"] == "IN_PROGRESS"  # Sheldon lo tomó; sigue reintentando


def test_endpoint_de_estado_explica_el_motivo(client: TestClient) -> None:
    body = client.get("/api/admin/orchestrator").json()
    assert {"mode", "running", "reason", "pendingMessages", "tickets"} <= set(body)
