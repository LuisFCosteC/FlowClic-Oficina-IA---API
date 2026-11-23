import threading

import pytest

from app.events.bus import DomainEvent, EventBus


def test_un_suscriptor_recibe_el_evento_con_su_payload() -> None:
    bus = EventBus()
    seen: list[DomainEvent] = []
    bus.subscribe(seen.append)
    bus.emit("agent.updated", {"id": "a1", "status": "WORKING"})
    assert seen == [DomainEvent("agent.updated", {"id": "a1", "status": "WORKING"})]


def test_dar_de_baja_deja_de_recibir_y_es_idempotente() -> None:
    bus = EventBus()
    seen: list[DomainEvent] = []
    off = bus.subscribe(seen.append)
    bus.emit("ticket.deleted", {"id": "t1"})
    off()
    off()
    bus.emit("ticket.deleted", {"id": "t2"})
    assert [e.payload["id"] for e in seen] == ["t1"]
    assert bus.subscriber_count == 0


def test_un_suscriptor_que_falla_no_rompe_al_emisor_ni_a_los_demas(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()
    seen: list[DomainEvent] = []

    def malo(_e: DomainEvent) -> None:
        raise RuntimeError("fallo del suscriptor")

    bus.subscribe(malo)
    bus.subscribe(seen.append)
    bus.emit("approval.created", {"id": "x"})  # no lanza
    assert len(seen) == 1
    assert "fallo en un suscriptor" in caplog.text


def test_se_puede_darse_de_baja_durante_la_emision() -> None:
    bus = EventBus()
    calls: list[str] = []
    offs: list[object] = []

    def uno(_e: DomainEvent) -> None:
        calls.append("uno")
        off_dos()

    def dos(_e: DomainEvent) -> None:
        calls.append("dos")

    bus.subscribe(uno)
    off_dos = bus.subscribe(dos)
    bus.emit("memory.created", {})
    assert calls == ["uno", "dos"]  # la copia de la lista se emite completa
    bus.emit("memory.created", {})
    assert calls == ["uno", "dos", "uno"]
    assert offs == []


def test_emitir_desde_varios_hilos() -> None:
    bus = EventBus()
    seen: list[DomainEvent] = []
    lock = threading.Lock()

    def collect(e: DomainEvent) -> None:
        with lock:
            seen.append(e)

    bus.subscribe(collect)
    threads = [
        threading.Thread(target=lambda i=i: bus.emit("ticket.created", {"n": i})) for i in range(20)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(e.payload["n"] for e in seen) == list(range(20))
