"""Comparación de versiones: servicio, ruta y errores."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.api.comparacion_util import (
    comparar,
    congelar_base,
    escenario_dos_versiones,
    fila,
    lote,
    medida,
    proyecto,
    version_nueva,
)
from vigia.app.models import Event, Project


def test_mejora_empeora_igual_y_sin_datos(client: TestClient, session: Session):
    e = escenario_dos_versiones(client, session)
    d = comparar(client, e["pid"], a=e["v1"], b=e["v2"])
    assert d["version_a"]["label"] == "v1" and d["version_b"]["label"] == "v2"
    assert d["version_b"]["n_lotes_evaluados"] == 1
    auc = fila(d, "auc")
    assert auc["direccion"] == "mejora" and round(auc["diferencia"], 6) == 0.1
    assert auc["a"]["valor_linea_base"] == 0.75 and auc["b"]["n"] == 200
    eq = fila(d, "fairness_value")
    assert eq["direccion"] == "empeora"
    assert eq["a"]["estado"] == "ok" and eq["b"]["estado"] == "ok"
    assert auc["a"]["interval_low"] is None and auc["b"]["interval_high"] is None
    assert fila(d, "f1")["direccion"] == "igual"
    rec = fila(d, "recall")
    assert rec["direccion"] == "sin_datos" and rec["diferencia"] is None
    assert rec["b"]["estado"] == "sin_datos" and "sin etiquetas" in rec["motivo"]
    assert d["nota_alertas"] == "las alertas son del modelo, no de la versión"


def test_version_sin_lotes_evaluados_da_sin_datos(client: TestClient, session: Session):
    pid, v1 = proyecto(client, session)
    v2 = version_nueva(session, pid)
    prod = lote(session, pid, v1, 0)
    medida(session, pid, v1, prod, "quality", "auc", 0.7, low=0.65)
    d = comparar(client, pid, a=v1, b=v2)
    f = fila(d, "auc")
    assert f["direccion"] == "sin_datos"
    assert d["version_b"]["n_lotes_evaluados"] == 0
    assert "v2" in f["b"]["motivo"] and "no tiene lotes" in f["b"]["motivo"]


def test_ventana_todos_hace_la_media(client: TestClient, session: Session):
    pid, v1 = proyecto(client, session)
    v2 = version_nueva(session, pid)
    for seq, valor in ((0, 0.6), (1, 0.8)):
        medida(session, pid, v1, lote(session, pid, v1, seq), "quality", "auc", valor,
               low=0.65, n=100)
    medida(session, pid, v2, lote(session, pid, v2, 2), "quality", "auc", 0.9, low=0.65)
    ultimo = fila(comparar(client, pid, a=v1, b=v2), "auc")
    todos = fila(comparar(client, pid, a=v1, b=v2, ventana="todos"), "auc")
    assert ultimo["a"]["valor"] == 0.8 and len(ultimo["a"]["batch_ids"]) == 1
    assert round(todos["a"]["valor"], 6) == 0.7 and len(todos["a"]["batch_ids"]) == 2
    assert todos["a"]["n"] == 200 and "media de 2 lotes" in todos["a"]["motivo"]


def test_solo_minimo_solo_maximo_y_los_dos(client: TestClient, session: Session):
    pid, v1 = proyecto(client, session)
    v2 = version_nueva(session, pid)
    casos = [
        ("minimo", {"low": 0.5}, 0.6, 0.7, "mejora"),
        ("maximo", {"high": 0.1}, 0.05, 0.08, "empeora"),
        ("maximo_baja", {"high": 0.1}, 0.08, 0.05, "mejora"),
        ("ambos_centro", {"low": 0.8, "high": 1.2}, 0.85, 1.0, "mejora"),
        ("ambos_lejos", {"low": 0.8, "high": 1.2}, 1.0, 1.15, "empeora"),
    ]
    b1, b2 = lote(session, pid, v1, 0), lote(session, pid, v2, 1)
    for clave, umbral, va, vb, _ in casos:
        medida(session, pid, v1, b1, "quality", clave, va, **umbral)
        medida(session, pid, v2, b2, "quality", clave, vb, **umbral)
    d = comparar(client, pid, a=v1, b=v2)
    for clave, _, _, _, esperado in casos:
        assert fila(d, clave)["direccion"] == esperado, clave
    assert "más alto" in fila(d, "minimo")["motivo"]
    assert "más bajo" in fila(d, "maximo")["motivo"]
    assert "centro" in fila(d, "ambos_centro")["motivo"]


def test_igual_por_intervalos_solapados_y_por_diferencia_pequena(
    client: TestClient, session: Session
):
    pid, v1 = proyecto(client, session)
    v2 = version_nueva(session, pid)
    b1, b2 = lote(session, pid, v1, 0), lote(session, pid, v2, 1)
    medida(session, pid, v1, b1, "quality", "con_int", 0.60, low=0.5, interval=(0.5, 0.7))
    medida(session, pid, v2, b2, "quality", "con_int", 0.75, low=0.5, interval=(0.65, 0.85))
    medida(session, pid, v1, b1, "quality", "sin_int", 0.600, low=0.5)
    medida(session, pid, v2, b2, "quality", "sin_int", 0.605, low=0.5)
    medida(session, pid, v1, b1, "quality", "disjuntos", 0.50, low=0.4, interval=(0.45, 0.55))
    medida(session, pid, v2, b2, "quality", "disjuntos", 0.80, low=0.4, interval=(0.75, 0.85))
    d = comparar(client, pid, a=v1, b=v2)
    assert fila(d, "con_int")["direccion"] == "igual"
    assert fila(d, "con_int")["motivo"] == "intervalos solapados"
    assert fila(d, "sin_int")["direccion"] == "igual"
    assert fila(d, "disjuntos")["direccion"] == "mejora"


def test_deriva_con_dos_lineas_base_distintas(client: TestClient, session: Session):
    pid, v1 = proyecto(client, session)
    v2 = version_nueva(session, pid)
    base1, prod1 = lote(session, pid, v1, 0), lote(session, pid, v1, 1)
    base2, prod2 = lote(session, pid, v2, 2), lote(session, pid, v2, 3)
    congelar_base(session, v1, base1)
    congelar_base(session, v2, base2)
    medida(session, pid, v1, prod1, "drift", "feature_drift_score", 0.30, high=0.15, state="alerta")
    medida(session, pid, v2, prod2, "drift", "feature_drift_score", 0.05, high=0.15)
    f = fila(comparar(client, pid, a=v1, b=v2), "feature_drift_score")
    assert f["direccion"] == "mejora"
    assert "propia línea base" in f["motivo"]
    assert f"lote {base1}" in f["motivo"] and f"lote {base2}" in f["motivo"]
    assert f"lote {base1}" in f["a"]["motivo"] and f"lote {base2}" in f["b"]["motivo"]
    assert f["a"]["estado"] == "alerta"


def test_por_defecto_a_es_la_activa_anterior(client: TestClient, session: Session):
    e = escenario_dos_versiones(client, session)
    pid, v1, v2 = e["pid"], e["v1"], e["v2"]
    # Sin evento de activación: a es la versión con evaluaciones distinta de b.
    p = session.get(Project, pid)
    p.active_version_id = v2
    session.add(p)
    session.commit()
    d = comparar(client, pid)
    assert d["version_a"]["id"] == v1 and d["version_b"]["id"] == v2
    # Con evento: manda el `before` de la última activación de b.
    v3 = version_nueva(session, pid, "v3")
    session.add(
        Event(action="version.activada", object_type="model_version", object_id=v3,
              project_id=pid, before_json={"active_version_id": v2},
              after_json={"active_version_id": v3})
    )
    p.active_version_id = v3
    session.add(p)
    session.commit()
    d = comparar(client, pid)
    assert d["version_a"]["id"] == v2 and d["version_b"]["id"] == v3


def test_errores_404_y_409(client: TestClient, session: Session):
    pid, v1 = proyecto(client, session)
    url = f"/api/projects/{pid}/versions/compare"
    r = client.get(url)
    assert r.status_code == 409 and "una sola versión" in r.json()["detail"]
    r_modelo = client.get("/api/projects/99999/versions/compare")
    assert r_modelo.status_code == 404 and "modelo 99999 no existe" in r_modelo.json()["detail"]
    r404 = client.get(url, params={"a": v1, "b": 99999})
    assert r404.status_code == 404 and "versión 99999 no existe" in r404.json()["detail"]
    otro, otra_v = proyecto(client, session, "otro")
    version_nueva(session, otro)
    assert client.get(url, params={"a": otra_v, "b": v1}).status_code == 404
    v2 = version_nueva(session, pid)
    r409 = client.get(url, params={"a": v1, "b": v1})
    assert r409.status_code == 409 and "distintas" in r409.json()["detail"]
    assert client.get(url, params={"a": v1, "b": v2}).status_code == 200
    assert client.get(url, params={"ventana": "mal"}).status_code == 422


def test_intervalo_en_el_lado_y_ultimo_lote_sin_la_metrica(
    client: TestClient, session: Session
):
    pid, v1 = proyecto(client, session)
    v2 = version_nueva(session, pid)
    b1a, b1b = lote(session, pid, v1, 0), lote(session, pid, v1, 1)
    b2 = lote(session, pid, v2, 2)
    medida(session, pid, v1, b1a, "quality", "auc", 0.60, low=0.5, interval=(0.55, 0.65), n=90)
    medida(session, pid, v1, b1b, "quality", "f1", 0.7, low=0.5)  # el último lote no trae auc
    medida(session, pid, v2, b2, "quality", "auc", 0.80, low=0.5, interval=(0.75, 0.85))
    medida(session, pid, v2, b2, "quality", "f1", 0.7, low=0.5)
    d = comparar(client, pid, a=v1, b=v2)
    auc = fila(d, "auc")
    assert auc["b"]["interval_low"] == 0.75 and auc["b"]["interval_high"] == 0.85
    # v1: el último lote evaluado (b1b) no tiene auc: sin_datos, sin usar el lote viejo.
    assert auc["a"]["valor"] is None and auc["direccion"] == "sin_datos"
    assert f"lote {b1b}" in auc["a"]["motivo"]
    # Con ventana todos sí cuenta el lote que tiene valor.
    todos = fila(comparar(client, pid, a=v1, b=v2, ventana="todos"), "auc")
    assert todos["a"]["valor"] == 0.60 and todos["a"]["batch_ids"] == [b1a]


def test_deriva_igual_con_dos_lineas_base(client: TestClient, session: Session):
    pid, v1 = proyecto(client, session)
    v2 = version_nueva(session, pid)
    base1, prod1 = lote(session, pid, v1, 0), lote(session, pid, v1, 1)
    base2, prod2 = lote(session, pid, v2, 2), lote(session, pid, v2, 3)
    congelar_base(session, v1, base1)
    congelar_base(session, v2, base2)
    medida(session, pid, v1, prod1, "drift", "feature_drift_score", 0.100, high=0.15)
    medida(session, pid, v2, prod2, "drift", "feature_drift_score", 0.104, high=0.15)
    f = fila(comparar(client, pid, a=v1, b=v2), "feature_drift_score")
    assert f["direccion"] == "igual"
    assert "propia línea base" in f["motivo"]


def test_explicabilidad_y_reglas_cruzadas_no_entran_en_la_tabla(
    client: TestClient, session: Session
):
    e = escenario_dos_versiones(client, session)
    for v, (_, prod) in ((e["v1"], e["b1"]), (e["v2"], e["b2"])):
        medida(session, e["pid"], v, prod, "explain", "explanation_stability", 0.9, low=0.5)
        medida(session, e["pid"], v, prod, "cross", "cx1_override_z", 1.0, high=2.0, group="g1")
    d = comparar(client, e["pid"], a=e["v1"], b=e["v2"])
    assert {f["monitor_type"] for f in d["filas"]} == {"fairness", "quality"}
