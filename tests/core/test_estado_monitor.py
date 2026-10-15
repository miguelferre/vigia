"""Estado del monitor."""
from __future__ import annotations

import json

from vigia.core import CORE_VERSION
from vigia.core.schema import (
    EvaluationResult,
    Measurement,
    MonitorType,
    State,
    WindowInfo,
    estado_monitor,
    worst,
)


def _m(clave: str, estado: State, *, umbral: bool = True, motivo: str | None = None):
    return Measurement(
        metric_key=clave,
        value=None if estado == State.sin_datos else 0.5,
        threshold_low=0.1 if umbral else None,
        state=estado,
        motivo=motivo,
    )


def _res(medidas: list[Measurement], **kw) -> EvaluationResult:
    return EvaluationResult(
        monitor=MonitorType.quality,
        window=WindowInfo(kind="batch", n=10),
        measurements=medidas,
        config_snapshot={},
        core_version=CORE_VERSION,
        **kw,
    )


def test_una_evaluada_ok_con_otra_sin_datos_es_ok():
    r = _res([_m("accuracy", State.ok), _m("label_skew", State.sin_datos)])
    assert r.worst_state == State.ok


def test_manda_la_peor_de_las_evaluadas():
    r = _res(
        [
            _m("accuracy", State.aviso),
            _m("recall", State.alerta),
            _m("label_skew", State.sin_datos),
        ]
    )
    assert r.worst_state == State.alerta


def test_todas_sin_datos_sigue_sin_datos():
    r = _res([_m("accuracy", State.sin_datos), _m("label_skew", State.sin_datos)])
    assert r.worst_state == State.sin_datos


def test_auxiliares_sin_umbral_no_deciden():
    r = _res(
        [
            _m("accuracy", State.sin_datos),
            _m("n", State.ok, umbral=False),
            _m("tp", State.ok, umbral=False),
        ]
    )
    assert r.worst_state == State.sin_datos


def test_sin_ninguna_con_umbral_se_aplica_worst():
    medidas = [_m("a", State.ok, umbral=False), _m("b", State.sin_datos, umbral=False)]
    assert estado_monitor(medidas) == worst(m.state for m in medidas) == State.sin_datos
    assert estado_monitor([]) == State.sin_datos


def test_worst_no_cambia():
    assert worst([State.sin_datos, State.ok]) == State.sin_datos


def test_details_enumera_las_metricas_sin_datos_con_su_motivo():
    r = _res(
        [
            _m("accuracy", State.ok),
            _m("label_skew", State.sin_datos, motivo="sin línea base congelada para esta versión"),
            _m("n", State.sin_datos, umbral=False),
        ]
    )
    d = r.to_dict()
    json.dumps(d)
    assert d["details"]["metricas_sin_datos"] == [
        {
            "metric_key": "label_skew",
            "group_code": None,
            "motivo": "sin línea base congelada para esta versión",
        }
    ]
    assert "metricas_sin_datos" not in r.details  # no muta el modelo


def test_details_sin_faltantes_no_añade_clave():
    d = _res([_m("accuracy", State.ok)]).to_dict()
    assert "metricas_sin_datos" not in d["details"]


def test_motivo_por_defecto_sale_de_details_o_de_la_ventana():
    r = _res([_m("accuracy", State.sin_datos)], details={"motivo": "batch sin filas"})
    assert r.to_dict()["details"]["metricas_sin_datos"][0]["motivo"] == "batch sin filas"
