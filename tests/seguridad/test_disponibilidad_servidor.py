"""Disponibilidad del servidor.

Cada test comprueba el control seguro de una huella o de un apunte; ver `HUELLAS`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from vigia.app.main import create_app
from vigia.app.models import Dossier, DossierReview, Event, Job
from vigia.app.schemas.demo import CreateRunBody, LabRunBody
from vigia.app.settings import Settings
from vigia.core.schema import DatosNoValidos
from vigia.sim import generators

HUELLAS = {
    "test_las_lecturas_del_stream_de_un_trabajo_no_corren_en_el_bucle": (
        "db.async-stream-job-blocks-event-loop-on-sqlalchemy-pool"
    ),
    "test_el_laboratorio_rechaza_edad_fuera_de_rango": (
        "demo.generator-age-params-nonterminating-rejection-loop"
    ),
    "test_el_laboratorio_admite_el_rango_de_la_interfaz": (
        "demo.generator-age-params-nonterminating-rejection-loop"
    ),
    "test_el_muestreo_de_edad_tiene_tope_de_intentos": (
        "demo.generator-age-params-nonterminating-rejection-loop"
    ),
    "test_el_generador_por_defecto_no_cambia": "demo.generator-age-params-nonterminating-rejection-loop",
    "test_al_arrancar_los_trabajos_vivos_pasan_a_un_estado_final": "live-jobs-after-restart",
    "test_el_tope_de_proyectos_de_demo_da_409": "demo-quota",
    "test_el_tope_de_proyectos_de_demo_por_defecto": "demo-quota",
}

ACTOR = actor_headers("miguel")
BASE = "http://127.0.0.1:8765"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    datos = tmp_path / "vigia-datos"
    datos.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=datos, host="127.0.0.1", port_start=8904, open_browser=False,
        jobs_inline=True, sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    aplicacion = create_app(settings)
    aplicacion.state.port = 8904
    aplicacion.state.shutdown_token = "test-token"
    return aplicacion


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url=BASE) as c:
        yield c


def test_las_lecturas_del_stream_de_un_trabajo_no_corren_en_el_bucle(client, monkeypatch):
    """El stream de un trabajo lee la base fuera del bucle de eventos (hilo aparte)."""
    from vigia.app.routers import jobs as rutas

    with Session(client.app.state.engine) as s:
        trabajo = Job(kind="prueba", queue="rapida", status="pendiente")
        s.add(trabajo)
        s.commit()
        job_id = trabajo.id
    original = rutas._get_job
    en_bucle: list[bool] = []

    def espia(session, jid):
        try:
            asyncio.get_running_loop()
            en_bucle.append(True)
        except RuntimeError:
            en_bucle.append(False)
        trabajo = original(session, jid)
        if len(en_bucle) == 1:  # tras la primera lectura el trabajo termina, y el flujo con él
            with Session(client.app.state.engine) as otra:
                fila = otra.get(Job, jid)
                fila.status = "terminado"
                otra.add(fila)
                otra.commit()
        return trabajo

    monkeypatch.setattr(rutas, "_get_job", espia)
    resp = client.get(f"/api/jobs/{job_id}/stream")
    assert resp.status_code == 200, resp.text
    assert len(en_bucle) == 2
    assert not any(en_bucle), "una lectura de SQLite corrió en el hilo de ejecución del bucle de eventos"


@pytest.mark.parametrize(
    ("clave", "valor"),
    [("age_mean", 0), ("age_mean", 17), ("age_mean", 101), ("age_std", 0), ("age_std", 0.5), ("age_std", 51)],
)
def test_el_laboratorio_rechaza_edad_fuera_de_rango(client, clave, valor):
    """La edad media y su dispersión llevan rango en el esquema: fuera de él, 422."""
    cuerpo = {"actor": "miguel", "motivo": "m", "phase_key": "b1", "params": {clave: valor}}
    resp = client.post("/api/demo/runs/1/lab", json=cuerpo, headers=ACTOR)
    assert resp.status_code == 422, resp.text
    resp = client.post(
        "/api/demo/runs", json={"scenario_key": "timeline_completo", "params": {clave: valor}}, headers=ACTOR
    )
    assert resp.status_code == 422, resp.text


def test_el_laboratorio_admite_el_rango_de_la_interfaz():
    """Todo valor que ofrece el laboratorio (edad media 30 a 80, dispersión 5 a 30) pasa."""
    for media, desv in [(30, 5), (80, 30), (62.4, 15.4), (18, 1), (100, 50)]:
        LabRunBody(actor="m", motivo="m", phase_key="b1", params={"age_mean": media, "age_std": desv})
        CreateRunBody(scenario_key="x", params={"age_mean": media, "age_std": desv})


def test_el_muestreo_de_edad_tiene_tope_de_intentos(monkeypatch):
    """Una combinación de edad que nunca llega a 36 años acaba con un error claro."""
    llamadas = {"n": 0}
    original = generators.sample_age

    def contada(*args, **kwargs):
        llamadas["n"] += 1
        assert llamadas["n"] < 200_000, "el bucle de rechazo no tiene tope"
        return original(*args, **kwargs)

    monkeypatch.setattr(generators, "sample_age", contada)
    with pytest.raises(DatosNoValidos, match="age_mean"):
        generators.generate_age_split_batch(
            n_total=10, frac_young=0.0, seed=1, age_mean=34.0, age_std=0.1
        )
    llamadas["n"] = 0
    with pytest.raises(DatosNoValidos, match="age_std"):
        generators.generate_e1_event(n_total=10, frac_young=0.0, age_mean=18.0, age_std=1.0)


def test_el_generador_por_defecto_no_cambia():
    """El tope no consume números del generador: mismo lote que antes del cambio (valores de HEAD)."""
    a = generators.generate_age_split_batch(n_total=30, frac_young=0.2, seed=3)
    assert len(a) == 30
    assert a["Age"].tolist()[:8] == [65, 25, 46, 64, 74, 33, 57, 70]
    assert float(a["Age"].sum()) == 1766.0
    assert int((a["Age"] < 36).sum()) == 6


def test_al_arrancar_los_trabajos_vivos_pasan_a_un_estado_final(settings):
    """Tras un cierre, un trabajo en curso o pendiente queda cancelado, con su evento."""
    app1 = create_app(settings)
    with TestClient(app1, base_url=BASE) as c1:
        pid = c1.post("/api/projects", json={"name": "p", "domain": "reuma"}, headers=ACTOR).json()["id"]
        with Session(app1.state.engine) as s:
            vivos = [Job(kind="k", queue="rapida", status=e, project_id=pid) for e in ("en_curso", "pendiente")]
            listo = Job(kind="k", queue="rapida", status="terminado", project_id=pid)
            s.add_all([*vivos, listo])
            dossier = Dossier(project_id=pid, system_name="s")
            s.add(dossier)
            s.commit()
            s.add_all([
                DossierReview(dossier_id=dossier.id, status="en_curso", job_id=vivos[0].id),
                DossierReview(dossier_id=dossier.id, status="pendiente"),
                DossierReview(dossier_id=dossier.id, status="terminada"),
            ])
            s.commit()
            ids_vivos, id_listo = [j.id for j in vivos], listo.id
    app2 = create_app(settings)
    with TestClient(app2, base_url=BASE), Session(app2.state.engine) as s:
        for jid in ids_vivos:
            fila = s.get(Job, jid)
            assert fila.status == "cancelado"
            assert fila.finished_at
            assert "cerr" in fila.message
        assert s.get(Job, id_listo).status == "terminado"
        estados = sorted(r.status for r in s.exec(select(DossierReview)).all())
        assert estados == ["cancelada", "cancelada", "terminada"]
        cancelados = s.exec(select(Event).where(Event.action == "job.cancelado")).all()
        assert sorted(e.object_id for e in cancelados) == sorted(ids_vivos)
        assert all(e.actor_kind == "sistema" for e in cancelados)


def test_el_tope_de_proyectos_de_demo_da_409(tmp_path):
    """Pasado el tope de proyectos de demo vivos, crear otro da 409 en español."""
    datos = tmp_path / "datos-tope"
    datos.mkdir()
    ajustes = Settings(
        data_dir=datos, port_start=8904, open_browser=False, jobs_inline=True, max_proyectos_demo=2
    )
    with TestClient(create_app(ajustes), base_url=BASE) as c:
        cuerpo = {"scenario_key": "timeline_completo"}
        for _ in range(2):
            assert c.post("/api/demo/runs", json=cuerpo, headers=ACTOR).status_code == 200
        resp = c.post("/api/demo/runs", json=cuerpo, headers=ACTOR)
        assert resp.status_code == 409, resp.text
        assert "2" in resp.json()["detail"]
        assert c.get("/api/demo/runs").json()["total"] == 2


def test_el_tope_de_proyectos_de_demo_por_defecto():
    """El tope de fábrica es de 50 proyectos de demo vivos."""
    assert Settings().max_proyectos_demo == 50
