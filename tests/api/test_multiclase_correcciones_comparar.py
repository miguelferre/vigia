"""Arreglos del backend: Comparar en multiclase."""

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


def test_label_rate_y_prediction_rate_por_clase_no_mejoran_ni_empeoran(
    client: TestClient, session: Session
):
    pid, v1 = proyecto(client, session, "a-224-dir")
    v2 = version_nueva(session, pid)
    b1, p1 = lote(session, pid, v1, 0), lote(session, pid, v1, 1)
    b2, p2 = lote(session, pid, v2, 2), lote(session, pid, v2, 3)
    congelar_base(session, v1, b1)
    congelar_base(session, v2, b2)
    valores = {
        v1: {
            ("label_rate", "clase:spam"): 0.20,
            ("label_rate", "clase:odio"): 0.20,
            ("prediction_rate", "clase:spam"): 0.30,
            ("recall", "clase:spam"): 0.60,
        },
        v2: {
            ("label_rate", "clase:spam"): 0.35,
            ("label_rate", "clase:odio"): 0.205,
            ("prediction_rate", "clase:spam"): 0.10,
            ("recall", "clase:spam"): 0.75,
        },
    }
    for v, base, prod in ((v1, b1, p1), (v2, b2, p2)):
        for lote_id in (base, prod):
            for (clave, grupo), valor in valores[v].items():
                medida(session, pid, v, lote_id, "quality", clave, valor, group=grupo, n=100)
    datos = comparar(client, pid, a=v1, b=v2)
    sube = fila(datos, "label_rate", "clase:spam")
    assert sube["direccion"] == "cambia"
    assert sube["motivo"] == "una proporción de clase no mejora ni empeora"
    assert fila(datos, "prediction_rate", "clase:spam")["direccion"] == "cambia"  # bajar tampoco empeora
    assert fila(datos, "label_rate", "clase:odio")["direccion"] == "igual"  # 0,005 < 0,01
    # Ninguna otra medida cambia de dirección: el recall por clase sigue siendo «más alto es mejor».
    assert fila(datos, "recall", "clase:spam")["direccion"] == "mejora"


def test_binario_nunca_da_cambia(client: TestClient, session: Session):
    e = escenario_dos_versiones(client, session)
    datos = comparar(client, e["pid"], a=e["v1"], b=e["v2"])
    assert {f["direccion"] for f in datos["filas"]} <= {"mejora", "empeora", "igual", "sin_datos"}


def test_metricas_sin_datos_enumera_las_medidas_de_la_clase_rara():
    from tests.core._datos_multiclase import canonico, historia, tarea
    from vigia.core.quality import evaluate_quality
    from vigia.core.schema import MonitorThresholds, QualityConfig

    # La clase `baja` pesa un 2 %: con 300 filas salen unas 6 y se piden al menos 20.
    frame = canonico(300, seed=2, pesos=[0.5, 0.48, 0.02])
    res = evaluate_quality(
        historia(frame),
        batch_seq=0,
        config=QualityConfig(),
        thresholds=MonitorThresholds(thresholds=[]),
        task=tarea(),
    )
    faltan = res.metricas_sin_datos()
    de_la_clase = [f for f in faltan if f["group_code"] == "clase:baja"]
    claves = {f["metric_key"] for f in de_la_clase}
    assert claves >= {"precision", "recall", "f1_measure", "label_rate", "prediction_rate"}
    assert all("clase con" in f["motivo"] and "al menos 20" in f["motivo"] for f in de_la_clase)
    # Las clases con datos no salen, y el volcado de `details` lo lleva.
    assert not [f for f in faltan if f["group_code"] in ("clase:alta", "clase:media")]
    assert res.to_dict()["details"]["metricas_sin_datos"] == faltan


def test_false_positive_rate_por_clase_mejora_al_bajar(client: TestClient, session: Session):
    """Hilo, nota de A: una tasa de falsos positivos por clase mejora al bajar."""
    pid, v1 = proyecto(client, session, "a-224-fpr")
    v2 = version_nueva(session, pid)
    b1, p1 = lote(session, pid, v1, 0), lote(session, pid, v1, 1)
    b2, p2 = lote(session, pid, v2, 2), lote(session, pid, v2, 3)
    congelar_base(session, v1, b1)
    congelar_base(session, v2, b2)
    valores = {v1: 0.20, v2: 0.05}
    for v, base, prod in ((v1, b1, p1), (v2, b2, p2)):
        for lote_id in (base, prod):
            medida(session, pid, v, lote_id, "quality", "false_positive_rate", valores[v],
                   group="clase:spam", n=100)
    datos = comparar(client, pid, a=v1, b=v2)
    assert fila(datos, "false_positive_rate", "clase:spam")["direccion"] == "mejora"
