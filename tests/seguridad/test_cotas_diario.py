"""Cotas de longitud de los textos libres del diario.

Cada test comprueba el control seguro de una huella; ver `HUELLAS`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tests.api.conftest import actor_headers
from vigia.app.main import create_app
from vigia.app.schemas.alerts import (
    AlertActionBody,
    AlertDecisionAction,
    AlertInvestigateBody,
    AlertsBulkBody,
    ProtocolBody,
)
from vigia.app.schemas.common import ActorBody
from vigia.app.schemas.projects import ProjectCreate, ProjectPatch, VersionCreate
from vigia.app.schemas.settings import SettingsPatchBody
from vigia.app.settings import Settings

HUELLA = "resource/free-text-unbounded-persisted-append-only-and-amplified-per-class"
HUELLAS = {
    "test_los_campos_libres_de_los_cuerpos_tienen_tope": HUELLA,
    "test_el_nombre_de_clase_del_alta_tiene_tope": HUELLA,
    "test_las_clases_de_la_plantilla_de_mapeo_tienen_tope": HUELLA,
    "test_el_motivo_de_una_anotacion_tiene_tope": HUELLA,
    "test_el_actor_de_la_cabecera_tiene_tope": HUELLA,
}

BASE = "http://127.0.0.1:8765"
AA = {"actor": "a", "motivo": "m"}

# (modelo, campos mínimos, campo con tope, tope esperado)
CASOS = [
    (ActorBody, AA, "motivo", 2000),
    (ActorBody, AA, "actor", 200),
    (AlertActionBody, {"action": "x", **AA}, "motivo", 2000),
    (AlertActionBody, {"action": "x", **AA}, "actor", 200),
    (AlertsBulkBody, {"alert_ids": [1], "action": "x", **AA}, "motivo", 2000),
    (AlertsBulkBody, {"alert_ids": [1], "action": "x", **AA}, "actor", 200),
    (ProtocolBody, {"protocolo_md": "p", **AA}, "motivo", 2000),
    (ProtocolBody, {"protocolo_md": "p", **AA}, "actor", 200),
    (ProtocolBody, AA | {"protocolo_md": "p"}, "protocolo_md", 20000),
    (AlertInvestigateBody, {"hallazgos": "h", **AA}, "hallazgos", 20000),
    (AlertDecisionAction, {"key": "k"}, "notes", 2000),
    (SettingsPatchBody, {"values": {"tema": "miguel"}, **AA}, "motivo", 2000),
    (SettingsPatchBody, {"values": {"tema": "miguel"}, **AA}, "actor", 200),
    (ProjectCreate, {"name": "p"}, "name", 200),
    (ProjectCreate, {"name": "p"}, "target_unit", 100),
    (ProjectPatch, AA, "name", 200),
    (ProjectPatch, AA, "description", 2000),
    (ProjectPatch, AA, "motivo", 2000),
    (VersionCreate, {"label": "v", **AA}, "label", 200),
]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    datos = tmp_path / "vigia-datos"
    datos.mkdir(parents=True, exist_ok=True)
    ajustes = Settings(data_dir=datos, port_start=8904, open_browser=False, jobs_inline=True)
    app: FastAPI = create_app(ajustes)
    app.state.port = 8904
    app.state.shutdown_token = "test-token"
    with TestClient(app, base_url=BASE) as c:
        yield c


@pytest.mark.parametrize(("modelo", "base", "campo", "tope"), CASOS)
def test_los_campos_libres_de_los_cuerpos_tienen_tope(modelo, base, campo, tope):
    """Un texto libre que va al diario tiene longitud máxima; el tope exacto pasa."""
    modelo(**{**base, campo: "x" * tope})
    with pytest.raises(ValidationError):
        modelo(**{**base, campo: "x" * (tope + 1)})


def test_el_nombre_de_clase_del_alta_tiene_tope():
    """El nombre de cada clase de un proyecto multiclase tiene como mucho 100 caracteres."""
    ProjectCreate(name="p", task_type="multiclass", classes=["a" * 100, "b", "c"])
    with pytest.raises(ValidationError):
        ProjectCreate(name="p", task_type="multiclass", classes=["a", "b" * 101, "c"])
    ProjectCreate(name="p", task_type="multiclass", classes=[1, 2, 3])


def test_las_clases_de_la_plantilla_de_mapeo_tienen_tope():
    """La plantilla de mapeo del alta y del parche admite nombres de clase de 100 caracteres, no de 101."""
    def plantilla(nombre: str) -> dict:
        return {"classes": [nombre, "b"], "probability_cols": ["p0", "p1"]}

    ProjectCreate(name="p", mapping_template=plantilla("a" * 100))
    ProjectPatch(**AA, mapping_template=plantilla("a" * 100))
    with pytest.raises(ValidationError):
        ProjectCreate(name="p", mapping_template=plantilla("a" * 101))
    with pytest.raises(ValidationError):
        ProjectPatch(**AA, mapping_template=plantilla("a" * 101))


def test_el_motivo_de_una_anotacion_tiene_tope(client):
    """La API rechaza con 422 un motivo de más de 2 000 caracteres y admite el tope exacto."""
    ok = client.post(
        "/api/events", json={"actor": "miguel", "motivo": "m" * 2000}, headers=actor_headers("miguel")
    )
    assert ok.status_code == 200, ok.text
    largo = client.post(
        "/api/events", json={"actor": "miguel", "motivo": "m" * 2001}, headers=actor_headers("miguel")
    )
    assert largo.status_code == 422, largo.text
    assert len(largo.text) < 5000


def test_el_actor_de_la_cabecera_tiene_tope(client):
    """`X-Vigia-Actor` de más de 200 caracteres da 422 en español; el tope exacto pasa."""
    cuerpo = {"actor": "miguel", "motivo": "nota"}
    ok = client.post("/api/events", json=cuerpo, headers=actor_headers("a" * 200))
    assert ok.status_code == 200, ok.text
    largo = client.post("/api/events", json=cuerpo, headers=actor_headers("a" * 201))
    assert largo.status_code == 422, largo.text
    assert "200" in largo.json()["detail"]
