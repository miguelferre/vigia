"""Endurecimiento de la ingesta, las subidas, los artefactos y los outcomes."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.api.conftest import actor_headers
from tests.api.test_model_artifacts import (
    _entrenar_pipeline,
    _onnx_bytes,
    _preparar_proyecto_con_baseline,
    _subir_artefacto,
)
from tests.seguridad.test_ciclo_b import VALOR_EXTRA, _ingerir_csv
from vigia.app.main import create_app
from vigia.app.models import Project, Record
from vigia.app.services import ingest, subidas
from vigia.app.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    d = tmp_path / "vigia-datos"
    d.mkdir(parents=True, exist_ok=True)
    return Settings(
        data_dir=d, host="127.0.0.1", port_start=8971, open_browser=False,
        jobs_inline=True, sse_heartbeat_s=0.2,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    application.state.port = 8971
    application.state.shutdown_token = "test-token"
    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _crear_proyecto(client: TestClient, name: str) -> int:
    resp = client.post(
        "/api/projects", json={"name": name, "domain": "reuma"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _ficheros(settings: Settings) -> list[Path]:
    carpeta = settings.data_dir / "uploads"
    return [p for p in carpeta.rglob("*") if p.is_file()] if carpeta.exists() else []


def test_paginacion_de_datasets_rechaza_limite_y_desplazamiento_invalidos(client: TestClient):
    """`limit` menor que 1 y `offset` negativo dan 422 en las tres listas."""
    pid = _crear_proyecto(client, "pag-datasets")
    for url in (f"/api/projects/{pid}/datasets", f"/api/projects/{pid}/batches"):
        for params in ({"limit": 0}, {"limit": -1}, {"offset": -1}):
            assert client.get(url, params=params).status_code == 422, (url, params)
        assert client.get(url, params={"limit": 1, "offset": 0}).status_code == 200
    resp = client.get("/api/batches/1/records", params={"limit": -1})
    assert resp.status_code == 422


@pytest.mark.parametrize("valor", ["nan", "inf", "-inf", "Infinity"])
def test_outcomes_rechaza_valores_no_finitos(client: TestClient, valor: str):
    """`nan` e `inf` en `value` dan 422 y no se guarda nada."""
    pid = _crear_proyecto(client, "outcomes-no-finito")
    csv = f"period,metric_key,value,source\n2026-01,m,{valor},manual\n".encode()
    resp = client.post(
        f"/api/projects/{pid}/outcomes",
        files={"file": ("o.csv", csv, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 422, resp.text
    assert client.get(f"/api/projects/{pid}/outcomes").json()["rows"] == []


def test_subida_por_encima_del_tope_da_413_sin_escribir(
    client: TestClient, settings: Settings, monkeypatch
):
    """Una subida mayor que el tope da 413 en datasets y outcomes y no deja ficheros."""
    pid = _crear_proyecto(client, "tope-subidas")
    monkeypatch.setattr(subidas, "LIMITE_BYTES_SUBIDA", 64)
    grande = b"a,b\n" + b"1,2\n" * 100
    resp = client.post(
        f"/api/projects/{pid}/datasets/upload",
        files={"file": ("g.csv", grande, "text/csv")},
        data={"kind": "combined", "role": "baseline"},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 413, resp.text
    assert "máximo" in resp.json()["detail"]
    resp = client.post(
        f"/api/projects/{pid}/outcomes",
        files={"file": ("o.csv", grande, "text/csv")},
        headers=actor_headers("miguel"),
    )
    assert resp.status_code == 413, resp.text
    assert _ficheros(settings) == []


def test_artefacto_por_encima_del_tope_da_413(client: TestClient, monkeypatch):
    """El artefacto del modelo también respeta el tope de subida."""
    _, version_id, _ = _preparar_proyecto_con_baseline(client, "tope-artefacto")
    monkeypatch.setattr(subidas, "LIMITE_BYTES_SUBIDA", 64)
    resp = _subir_artefacto(client, version_id, contenido=b"x" * 200)
    assert resp.status_code == 413, resp.text


def test_artefacto_nuevo_con_otro_nombre_sustituye_al_anterior(
    client: TestClient, settings: Settings
):
    """Una subida válida con otro nombre deja un solo fichero en `artifacts/` y ningún temporal."""
    _, version_id, _ = _preparar_proyecto_con_baseline(client, "artefacto-renombrado")
    contenido = _onnx_bytes(_entrenar_pipeline())
    assert _subir_artefacto(client, version_id, contenido=contenido, filename="a.onnx").status_code == 200
    assert _subir_artefacto(client, version_id, contenido=contenido, filename="b.onnx").status_code == 200
    ficheros = sorted(p.name for p in (settings.data_dir / "artifacts").rglob("*") if p.is_file())
    assert len(ficheros) == 1 and ficheros[0].endswith("_b.onnx"), ficheros


def test_retirar_variables_guardadas_vacia_registros_y_privado(
    client: TestClient, settings: Settings
):
    """Retirar las variables deja `features_json` nulo y el `.privado.csv` sin columnas no mapeadas."""
    proyecto, _batch_id = _ingerir_csv(client, "retirar-variables", store_features=True)
    privados = list((settings.data_dir / "uploads").rglob("*.privado.csv"))
    assert len(privados) == 1
    assert VALOR_EXTRA.encode() in privados[0].read_bytes()  # control positivo
    with Session(client.app.state.engine) as s:
        project = s.get(Project, proyecto["id"])
        n = ingest.retirar_variables_guardadas(s, project)
        s.commit()
        assert n == 2
        assert all(r.features_json is None for r in s.exec(select(Record)).all())
    assert VALOR_EXTRA.encode() not in privados[0].read_bytes()
    assert b"Age" not in privados[0].read_bytes().splitlines()[0]
