"""`job.error` sin código de estado ni texto de librería."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session

from vigia.app.errores import texto_error_trabajo
from vigia.app.jobs import JobContext
from vigia.core.schema import DatosNoValidos


def _lanzar(client: TestClient, excepcion: Exception, kind: str = "prueba"):
    def _falla(ctx: JobContext, session: Session) -> None:
        raise excepcion

    return client.app.state.jobs.enqueue(kind, "rapida", _falla, params={})


def test_httpexception_guarda_el_detalle_sin_el_codigo(client: TestClient):
    job = _lanzar(client, HTTPException(422, "los datos no tienen mapeo: guarda el mapeo antes"))
    assert job.status == "error"
    assert job.error == "los datos no tienen mapeo: guarda el mapeo antes"
    assert "422" not in job.error


def test_datos_no_validos_guarda_su_texto_tal_cual(client: TestClient):
    job = _lanzar(client, DatosNoValidos("el fichero ya no tiene la columna 'edad'"))
    assert job.error == "el fichero ya no tiene la columna 'edad'"


def test_otra_excepcion_da_el_texto_generico_sin_texto_de_libreria(client: TestClient):
    job = _lanzar(client, KeyError("columna_secreta"), kind="ingesta")
    assert job.status == "error"
    assert job.error == "error interno al ingerir el fichero: el registro del servidor tiene el detalle"
    assert "KeyError" not in job.error and "columna_secreta" not in job.error


@pytest.mark.parametrize(
    ("kind", "accion"),
    [
        ("evaluacion", "evaluar el lote"),
        ("explicacion", "calcular la explicación"),
        ("cruzadas", "evaluar las reglas cruzadas"),
        ("revision_dossier", "revisar el dossier"),
        ("desconocido", "ejecutar el trabajo"),
    ],
)
def test_texto_generico_por_tipo_de_trabajo(kind, accion):
    texto = texto_error_trabajo(ValueError("x"), kind)
    assert texto == f"error interno al {accion}: el registro del servidor tiene el detalle"


def test_el_trabajo_de_la_api_enseña_el_mensaje_limpio(client: TestClient):
    """Una ingesta sin mapeo ya no sale como «422: ... PUT /datasets/{id}/mapping»."""
    resp = client.post("/api/projects", json={"name": "sin-mapeo", "domain": "reuma"})
    proyecto = resp.json()
    resp = client.post(
        f"/api/projects/{proyecto['id']}/datasets/upload",
        files={"file": ("a.csv", b"id,pred\n1,1\n2,0\n", "text/csv")},
        data={"kind": "combined", "role": "production"},
    )
    assert resp.status_code == 200, resp.text
    dataset_id = resp.json()["dataset"]["id"]
    resp = client.post(
        f"/api/datasets/{dataset_id}/ingest",
        json={"model_version_id": proyecto["active_version_id"], "evaluate": False},
    )
    # sin mapeo la ingesta se rechaza al encolar o termina en error: en los dos casos sin jerga
    texto = resp.json().get("error") or resp.json().get("detail") or ""
    assert texto == "los datos no tienen mapeo: guarda el mapeo en el paso Mapeo antes de ingerir"
