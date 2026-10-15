"""Registro de uso.

Cada test comprueba el control seguro de un apunte; ver `HUELLAS`.
"""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api import conftest as _api
from tests.api.conftest import actor_headers
from tests.api.test_human_multiclase import CABECERA
from vigia.app.models import ModelVersion, Project
from vigia.app.services import human_layer
from vigia.human import cross_alerts

# Fixtures de tests/api/conftest.py: app, client, data_dir y settings.
app, client, data_dir, settings = _api.app, _api.client, _api.data_dir, _api.settings

HUELLAS = {
    "test_filas_con_celdas_en_blanco_no_entran_al_motor_de_cruzadas": (
        "human-layer/cross-alerts-blank-cells-counted-as-override-and-model-error"
    ),
    "test_fecha_fuera_de_intervalo_da_422_con_la_fila": (
        "human-layer/usage-log-outlier-date-collapses-deskilling-windows"
    ),
    "test_fechas_dentro_del_intervalo_se_aceptan": (
        "human-layer/usage-log-outlier-date-collapses-deskilling-windows"
    ),
    "test_export_neutraliza_las_clases_que_empiezan_como_formula": (
        "csv-formula-injection:usage-log-export-class-names"
    ),
    "test_export_deja_las_clases_numericas_tal_cual": "csv-formula-injection:usage-log-export-class-names",
    "test_registro_de_uso_por_encima_del_tope_de_filas_da_422": (
        "usage-log-upload-sync-work-in-async-handler"
    ),
}

CABECERA_BIN = "date,human_decision,model_output,ground_truth\n"


def _proyecto(client: TestClient, nombre: str) -> dict:
    resp = client.post(
        "/api/projects", json={"name": nombre, "domain": "reuma"}, headers=actor_headers("miguel")
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _subir(client: TestClient, proyecto_id: int, cuerpo: str):
    return client.post(
        f"/api/projects/{proyecto_id}/usage-logs/upload",
        files={"file": ("uso.csv", cuerpo.encode("utf-8"), "text/csv")},
        headers=actor_headers("miguel"),
    )


# --- Filas sin verdad en las cruzadas ----------------------------------------


def test_filas_con_celdas_en_blanco_no_entran_al_motor_de_cruzadas(client: TestClient):
    """El marco que recibe el motor de cruzadas solo trae filas con decision y
    salida; una celda en blanco no cuenta como override. Una fila sin verdad
    entra (la verdad llega tarde) y no cuenta como error del modelo."""
    proyecto = _proyecto(client, "n04-blancos")
    filas = [
        "2026-01-05,refer,refer,refer",
        "2026-01-06,no-refer,refer,refer",
        "2026-01-07,refer,refer,refer",
        "2026-01-08,,refer,refer",
        "2026-01-09,refer,,refer",
        "2026-01-10,refer,refer,",
    ]
    resp = _subir(client, proyecto["id"], CABECERA_BIN + "\n".join(filas) + "\n")
    assert resp.status_code == 200, resp.text
    with Session(client.app.state.engine) as s:
        p = s.get(Project, proyecto["id"])
        v = s.get(ModelVersion, proyecto["active_version_id"])
        df = human_layer.usage_frame(s, p, v)
    assert len(df) == 4
    assert df[["human_decision", "model_output"]].notna().all().all()
    assert int((df["human_decision"] != df["model_output"]).sum()) == 1
    bloque = cross_alerts._block(df)
    assert bloque["model_error_rate"] == 0.0
    assert bloque["override_rate"] == 0.25


# --- Registro de uso: validación ---------------------------------------------


@pytest.mark.parametrize("fecha", ["2099-12-31", "0001-01-01", "01/01/1900", "31-12-2100"])
def test_fecha_fuera_de_intervalo_da_422_con_la_fila(client: TestClient, fecha: str):
    """La subida rechaza una fecha fuera del intervalo plausible y dice la fila."""
    proyecto = _proyecto(client, "n05-fuera")
    cuerpo = CABECERA_BIN + "2026-01-05,refer,refer,refer\n" + f"{fecha},refer,refer,refer\n"
    resp = _subir(client, proyecto["id"], cuerpo)
    assert resp.status_code == 422, resp.text
    assert "fila 2" in resp.json()["detail"]
    assert "intervalo" in resp.json()["detail"]


def test_fechas_dentro_del_intervalo_se_aceptan(client: TestClient):
    proyecto = _proyecto(client, "n05-dentro")
    cuerpo = CABECERA_BIN + "".join(
        f"{f},refer,refer,refer\n" for f in ("2000-01-01", "2026-06-30", "15/03/2026", "2049-12-31")
    )
    assert _subir(client, proyecto["id"], cuerpo).status_code == 200


# --- Registro de uso: límites ------------------------------------------------


def _exportar_clases(client: TestClient, clases: list[str]) -> list[dict[str, str]]:
    cuerpo_proyecto = {
        "name": "n12-export",
        "domain": "libre",
        "task_type": "multiclass",
        "classes": clases,
        "mapping_template": {"favorable_label": [clases[1]]},
    }
    resp = client.post("/api/projects", json=cuerpo_proyecto, headers=actor_headers("miguel"))
    assert resp.status_code == 200, resp.text
    pid = resp.json()["id"]
    a, b, c = clases
    diario = f"{CABECERA}\n2026-01-05,{a},{b},{c},clin-1,x\n2026-01-06,{b},{b},{b},clin-1,x\n"
    assert _subir(client, pid, diario).status_code == 200
    exp = client.get(f"/api/projects/{pid}/usage-logs/export.csv")
    assert exp.status_code == 200, exp.text
    return list(csv.DictReader(io.StringIO(exp.text)))


def test_export_neutraliza_las_clases_que_empiezan_como_formula(client: TestClient):
    """El CSV exportado prefija con comilla los nombres de clase que una hoja de
    calculo leeria como formula, en las tres columnas de decision."""
    filas = _exportar_clases(client, ["=1+1", "b", "@c"])
    primera = filas[0]
    assert primera["human_decision"] == "'=1+1"
    assert primera["ground_truth"] == "'@c"
    assert primera["model_output"] == "b"


def test_export_deja_las_clases_numericas_tal_cual(client: TestClient):
    """Control positivo: una clase que es un numero simple (`-1`) no se altera."""
    filas = _exportar_clases(client, ["-1", "2", "otra"])
    assert filas[0]["human_decision"] == "-1"
    assert filas[0]["model_output"] == "2"


# --- Registro de uso: cierre -------------------------------------------------


def test_registro_de_uso_por_encima_del_tope_de_filas_da_422(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """La subida cuenta las filas antes de procesarlas y rechaza las que pasan
    del tope por lote, sin crear dataset ni filas."""
    monkeypatch.setattr(human_layer, "LIMITE_FILAS_LOTE", 5, raising=False)
    proyecto = _proyecto(client, "n24-tope")
    cuerpo = CABECERA_BIN + "".join(f"2026-01-{d:02d},refer,refer,refer\n" for d in range(1, 8))
    resp = _subir(client, proyecto["id"], cuerpo)
    assert resp.status_code == 422, resp.text
    assert "filas" in resp.json()["detail"]
    lista = client.get(f"/api/projects/{proyecto['id']}/datasets").json()
    assert lista["items"] == []
    ok = CABECERA_BIN + "".join(f"2026-01-{d:02d},refer,refer,refer\n" for d in range(1, 6))
    assert _subir(client, proyecto["id"], ok).status_code == 200
