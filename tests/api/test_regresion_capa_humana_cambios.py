"""Tabla de cambios entre la salida del modelo y la decisión del
profesional, en los tres tipos de tarea.

El diario se inserta directamente en `usage_log` (lo que guarda la ingesta) para fijar los recuentos
sin depender del generador.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api import _datos_regresion as r
from tests.api.conftest import actor_headers
from vigia.app.models import UsageLog
from vigia.core.schema import MOTIVO_CAPA_HUMANA_SIN_RANGO

HUMANO = actor_headers("miguel")
CLASES = ["ok", "spam", "odio"]


def _cambios(client: TestClient, proyecto_id: int, **params):
    resp = client.get(f"/api/projects/{proyecto_id}/overrides/cambios", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _insertar(
    session: Session, proyecto: dict, filas: Sequence[dict], *, version_id: int | None = None
) -> None:
    for i, datos in enumerate(filas):
        session.add(
            UsageLog(
                project_id=proyecto["id"],
                model_version_id=version_id or proyecto["active_version_id"],
                date=f"2026-01-{1 + i % 28:02d}",
                **datos,
            )
        )
    session.commit()


def _repetir(n: int, **datos) -> list[dict]:
    return [dict(datos) for _ in range(n)]


def _celdas(fila: dict) -> dict[str, int]:
    return {c["decision_profesional"]: c["n"] for c in fila["celdas"]}


# -- Binario -------------------------------------------------------------------------------------


def test_binario(client: TestClient, session: Session):
    p = client.post("/api/projects", json={"name": "r5-cambios-binario"}, headers=HUMANO).json()
    _insertar(
        session,
        p,
        # Modelo refer (1): 40 filas, el profesional lo mantiene en 30 y lo cambia en 10.
        _repetir(30, model_output=1, human_decision=1)
        + _repetir(10, model_output=1, human_decision=0)
        # Modelo no-refer (0): 5 filas (por debajo de min_n), 2 cambiadas.
        + _repetir(3, model_output=0, human_decision=0)
        + _repetir(2, model_output=0, human_decision=1)
        # Sin decisión del profesional o sin salida del modelo: no entran en la tabla.
        + _repetir(4, model_output=1, human_decision=None)
        + _repetir(3, model_output=None, human_decision=0),
    )
    c = _cambios(client, p["id"])
    assert c["task_type"] == "binary" and c["categorias"] == ["refer", "no-refer"]
    assert c["n_total"] == 52 and c["n_sin_decision"] == 7 and c["min_n"] == 30
    assert c["unidad"] is None and c["rangos_favorables"] is None and c["motivo"] is None
    refer, no_refer = c["filas"]
    assert refer["salida_modelo"] == "refer" and refer["n"] == 40
    assert _celdas(refer) == {"refer": 30, "no-refer": 10}
    assert refer["tasa_cambio"] == pytest.approx(0.25)
    assert [x["tasa"] for x in refer["celdas"]] == pytest.approx([0.75, 0.25])
    # La fila de 5 decisiones queda por debajo de la celda mínima: tasas nulas, `n` conservado.
    assert no_refer["n"] == 5 and _celdas(no_refer) == {"refer": 2, "no-refer": 3}
    assert no_refer["tasa_cambio"] is None and all(x["tasa"] is None for x in no_refer["celdas"])
    # Con `min_n` más bajo la misma fila ya da tasa.
    baja = _cambios(client, p["id"], min_n=5)["filas"][1]
    assert baja["tasa_cambio"] == pytest.approx(0.4)


# -- Multiclase ----------------------------------------------------------------------------------


def _multiclase(client: TestClient, nombre: str) -> dict:
    resp = client.post(
        "/api/projects",
        json={"name": nombre, "domain": "libre", "task_type": "multiclass", "classes": CLASES,
              "mapping_template": {"favorable_label": ["spam"]}},
        headers=HUMANO,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_multiclase_en_el_orden_declarado_y_con_una_clase_a_cero(client: TestClient, session: Session):
    p = _multiclase(client, "r5-cambios-multiclase")
    _insertar(
        session,
        p,
        _repetir(20, model_class="ok", human_class="ok")
        + _repetir(10, model_class="ok", human_class="spam")
        + _repetir(5, model_class="ok", human_class="odio")
        + _repetir(30, model_class="spam", human_class="spam")
        # «odio» nunca sale del modelo: su fila va a cero pero existe.
        + _repetir(2, model_class="otra", human_class="ok")  # clase fuera de las declaradas
        + _repetir(3, model_class="ok", human_class=None),
    )
    c = _cambios(client, p["id"])
    assert c["task_type"] == "multiclass" and c["categorias"] == CLASES
    assert [f["salida_modelo"] for f in c["filas"]] == CLASES
    assert all([x["decision_profesional"] for x in f["celdas"]] == CLASES for f in c["filas"])
    ok, spam, odio = c["filas"]
    assert ok["n"] == 35 and _celdas(ok) == {"ok": 20, "spam": 10, "odio": 5}
    assert ok["tasa_cambio"] == pytest.approx(15 / 35)
    assert spam["n"] == 30 and spam["tasa_cambio"] == pytest.approx(0.0)
    assert odio["n"] == 0 and odio["tasa_cambio"] is None and _celdas(odio) == {"ok": 0, "spam": 0, "odio": 0}
    assert c["n_total"] == 70 and c["n_sin_decision"] == 5  # 2 de clase desconocida y 3 sin decisión


def test_multiclase_sin_clases_fijadas_dice_que_hacer(client: TestClient):
    resp = client.post(
        "/api/projects", json={"name": "r5-cambios-sin-clases", "task_type": "multiclass"}, headers=HUMANO
    )
    assert resp.status_code == 200, resp.text
    c = _cambios(client, resp.json()["id"])
    assert c["categorias"] == [] and c["filas"] == [] and "Congela la línea base" in c["motivo"]


# -- Regresión -----------------------------------------------------------------------------------


def test_regresion_con_rango(client: TestClient, session: Session):
    p = r.crear_proyecto_regresion(client, "r5-cambios-regresion")
    _insertar(
        session,
        p,
        # model_output y human_decision guardan la pertenencia al rango: 1 = dentro.
        _repetir(50, model_output=1, human_decision=1, human_value=14.0, model_value=13.0)
        + _repetir(10, model_output=1, human_decision=0, human_value=8.0, model_value=13.0)
        + _repetir(40, model_output=0, human_decision=0, human_value=5.0, model_value=6.0)
        + _repetir(4, model_output=0, human_decision=1, human_value=15.0, model_value=9.0),
    )
    c = _cambios(client, p["id"])
    assert c["task_type"] == "regression" and c["categorias"] == ["dentro del rango", "fuera del rango"]
    assert c["unidad"] == r.UNIDAD and c["rangos_favorables"] == [[12.0, None]]
    dentro, fuera = c["filas"]
    assert dentro["salida_modelo"] == "dentro del rango" and dentro["n"] == 60
    assert _celdas(dentro) == {"dentro del rango": 50, "fuera del rango": 10}
    assert dentro["tasa_cambio"] == pytest.approx(10 / 60)
    assert fuera["n"] == 44 and fuera["tasa_cambio"] == pytest.approx(4 / 44)
    assert c["n_total"] == 104 and c["n_sin_decision"] == 0


def test_regresion_con_rango_min_n_y_n_sin_decision(client: TestClient, session: Session):
    p = r.crear_proyecto_regresion(client, "r5-cambios-regresion-minn")
    _insertar(
        session,
        p,
        # Modelo dentro del rango: 35 filas (celda mínima superada).
        _repetir(30, model_output=1, human_decision=1, human_value=14.0, model_value=13.0)
        + _repetir(5, model_output=1, human_decision=0, human_value=8.0, model_value=13.0)
        # Modelo fuera: 6 filas, por debajo de min_n.
        + _repetir(4, model_output=0, human_decision=0, human_value=5.0, model_value=6.0)
        + _repetir(2, model_output=0, human_decision=1, human_value=15.0, model_value=9.0)
        # Cifra del profesional en blanco o cifra del modelo en blanco: sin decisión.
        + _repetir(3, model_output=1, human_decision=None, human_value=None, model_value=13.0)
        + _repetir(2, model_output=None, human_decision=1, human_value=15.0, model_value=None),
    )
    c = _cambios(client, p["id"])
    assert c["n_total"] == 46 and c["n_sin_decision"] == 5 and c["min_n"] == 30
    dentro, fuera = c["filas"]
    assert dentro["n"] == 35 and dentro["tasa_cambio"] == pytest.approx(5 / 35)
    assert fuera["n"] == 6 and fuera["tasa_cambio"] is None
    assert _celdas(fuera) == {"dentro del rango": 2, "fuera del rango": 4}
    assert all(x["tasa"] is None for x in fuera["celdas"])
    assert _cambios(client, p["id"], min_n=5)["filas"][1]["tasa_cambio"] == pytest.approx(2 / 6)


def test_regresion_con_extremo_inferior_abierto(client: TestClient, session: Session):
    p = r.crear_proyecto_regresion(client, "r5-cambios-regresion-abierto", rangos=[[None, 5]])
    _insertar(
        session,
        p,
        _repetir(31, model_output=1, human_decision=1, human_value=3.0, model_value=4.0)
        + _repetir(2, model_output=1, human_decision=0, human_value=9.0, model_value=4.0),
    )
    c = _cambios(client, p["id"])
    assert c["rangos_favorables"] == [[None, 5.0]]
    assert c["filas"][0]["n"] == 33 and c["filas"][0]["tasa_cambio"] == pytest.approx(2 / 33)
    assert c["filas"][1]["n"] == 0 and c["filas"][1]["tasa_cambio"] is None


def test_regresion_sin_rango(client: TestClient):
    p = r.crear_proyecto_regresion(client, "r5-cambios-sin-rango", rangos=None)
    c = _cambios(client, p["id"])
    assert c["task_type"] == "regression" and c["categorias"] == [] and c["filas"] == []
    assert c["motivo"] == MOTIVO_CAPA_HUMANA_SIN_RANGO and c["rangos_favorables"] == []


# -- Diario vacío y parámetros -------------------------------------------------------------------


@pytest.mark.parametrize("tipo", ["binary", "multiclass", "regression"])
def test_diario_vacio_da_todas_las_categorias_a_cero_con_el_motivo(client: TestClient, tipo: str):
    match tipo:
        case "binary":
            p = client.post("/api/projects", json={"name": "r5-cambios-vacio-b"}, headers=HUMANO).json()
            esperadas = 2
        case "multiclass":
            p = _multiclase(client, "r5-cambios-vacio-m")
            esperadas = 3
        case _:
            p = r.crear_proyecto_regresion(client, "r5-cambios-vacio-r")
            esperadas = 2
    c = _cambios(client, p["id"])
    assert c["motivo"] == "sin filas de diario para esta versión"
    assert c["n_total"] == 0 and c["n_sin_decision"] == 0 and len(c["filas"]) == esperadas
    assert all(f["n"] == 0 and f["tasa_cambio"] is None for f in c["filas"])
    assert all(x["n"] == 0 and x["tasa"] is None for f in c["filas"] for x in f["celdas"])


def test_parametros_y_versiones(client: TestClient, session: Session):
    p = client.post("/api/projects", json={"name": "r5-cambios-params"}, headers=HUMANO).json()
    _insertar(session, p, _repetir(31, model_output=1, human_decision=1))
    # `min_n` fuera de rango, versión de otro modelo y sin versión activa.
    assert client.get(f"/api/projects/{p['id']}/overrides/cambios", params={"min_n": 0}).status_code == 422
    otro = client.post("/api/projects", json={"name": "r5-cambios-params-otro"}, headers=HUMANO).json()
    resp = client.get(f"/api/projects/{p['id']}/overrides/cambios", params={"model_version_id": otro["active_version_id"]})
    assert resp.status_code == 422
    assert client.get("/api/projects/9999/overrides/cambios").status_code == 404
    # La versión pedida manda sobre la activa.
    pedida = _cambios(client, p["id"], model_version_id=p["active_version_id"])
    assert pedida["model_version_id"] == p["active_version_id"] and pedida["n_total"] == 31
    # Lectura sin evento: pedirla no deja nada en el diario.
    antes = client.get(f"/api/projects/{p['id']}/events").json()
    _cambios(client, p["id"])
    assert client.get(f"/api/projects/{p['id']}/events").json() == antes
