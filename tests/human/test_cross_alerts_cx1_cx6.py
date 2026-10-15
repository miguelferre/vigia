"""CX-6 no se emite donde hay CX-1.

La supresion va en `evaluate_cross` DESPUES de la reduccion por pareja: con dos
grupos, CX-1 dispara en el grupo con menos override, que es justo el ancla de
`_cx6_una_por_pareja`. Si se suprimiera antes, quedaria una sola alerta CX-6 en el
grupo de mas override y la reduccion no actuaria (alerta espejo en el grupo
equivocado).
"""
from __future__ import annotations

import pandas as pd

from vigia.human.cross_alerts import (
    MOTIVO_CX6_CUBIERTA_POR_CX1,
    build_reference,
    evaluate_cross,
)


def _grupo(
    nombre: str, *, n: int, overrides: int, positivos: int, fn: int, offset: int
) -> pd.DataFrame:
    """`n` decisiones; `positivos` con verdad `refer` de las que el modelo falla `fn`;
    las ultimas `overrides` filas corrigen al modelo."""
    gt, modelo, humano = [], [], []
    for i in range(n):
        positivo = i < positivos
        gt.append("refer" if positivo else "no-refer")
        m = "no-refer" if (not positivo or i < fn) else "refer"
        modelo.append(m)
        invertir = i >= n - overrides
        humano.append(("refer" if m == "no-refer" else "no-refer") if invertir else m)
    return pd.DataFrame(
        {
            "date": ["2026-01-05"] * n,
            "clinician_pseudonym": [f"clin-{nombre}-{i % 3}" for i in range(n)],
            "subgroup": [nombre] * n,
            "human_decision": humano,
            "model_output": modelo,
            "ground_truth": gt,
            "record_seq": list(range(offset, offset + n)),
            "model_version": ["v1"] * n,
        }
    )


def _usage(*grupos: tuple[str, int, int]) -> pd.DataFrame:
    """Cada grupo: (nombre, overrides, fn) con 300 filas y 100 positivos."""
    frames = [
        _grupo(nombre, n=300, overrides=ov, positivos=100, fn=fn, offset=i * 300)
        for i, (nombre, ov, fn) in enumerate(grupos)
    ]
    return pd.concat(frames, ignore_index=True)


def _cx6(r, grupo: str):
    return next(m for m in r.measurements if m.metric_key == f"cx6_override_z:{grupo}")


def _alertas(r, regla: str) -> set[str]:
    return {a.group for a in r.alerts if a.rule == regla}


def _vigilar(df: pd.DataFrame, **kw):
    return evaluate_cross(df, reference=build_reference(df), mode="vigilancia", **kw)


def test_dos_grupos_cx1_dispara_en_el_ancla_no_hay_cx6_en_ningun_grupo():
    """(a) A converge con el modelo (override bajo, FNR alta): CX-1 en A y ninguna CX-6."""
    df = _usage(("A", 15, 80), ("B", 150, 10))
    r = _vigilar(df)
    assert _alertas(r, "CX-1") == {"A"}
    assert _alertas(r, "CX-6") == set()
    ancla = _cx6(r, "A")
    assert ancla.state.value == "ok"
    assert ancla.motivo == MOTIVO_CX6_CUBIERTA_POR_CX1
    assert "CX-1" in ancla.motivo
    assert ancla.extra["cubierta_por"] == "CX-1"
    assert ancla.value is not None and abs(ancla.value) >= 3.0  # conserva el z
    otra = _cx6(r, "B")
    assert otra.state.value == "ok"
    assert otra.extra["pareja_de"] == "A"
    assert "cubierta_por" not in otra.extra
    # El motivo de la pareja ya no dice que la alerta va en A: A no tiene CX-6.
    assert "CX-1" in otra.motivo
    assert "la alerta de la pareja va en ese grupo" not in otra.motivo


def test_dos_grupos_sin_cx1_el_control_si_emite_cx6_en_el_ancla():
    df = _usage(("A", 15, 10), ("B", 150, 10))
    r = _vigilar(df)
    assert _alertas(r, "CX-1") == set()
    assert _alertas(r, "CX-6") == {"A"}
    assert "cubierta_por" not in _cx6(r, "A").extra


def test_cx1_alert_groups_sin_cx1_en_la_evaluacion_suprime_cx6_en_ese_grupo():
    """(b) CX-1 viva de una evaluacion anterior (la resuelve el llamador)."""
    df = _usage(("A", 15, 10), ("B", 150, 10))
    r = _vigilar(df, cx1_alert_groups={"A"})
    assert _alertas(r, "CX-1") == set()
    assert _alertas(r, "CX-6") == set()
    ancla = _cx6(r, "A")
    assert ancla.state.value == "ok"
    assert ancla.motivo == MOTIVO_CX6_CUBIERTA_POR_CX1
    assert ancla.extra["cubierta_por"] == "CX-1"


def test_cx1_alert_groups_de_un_grupo_que_no_es_el_ancla_no_toca_la_alerta_de_la_pareja():
    df = _usage(("A", 15, 10), ("B", 150, 10))
    r = _vigilar(df, cx1_alert_groups={"B"})
    assert _alertas(r, "CX-6") == {"A"}


def test_tres_grupos_cx1_en_uno_cx6_sigue_pudiendo_disparar_en_otro():
    """(c) Sin pareja: la supresion es por grupo."""
    df = _usage(("A", 15, 80), ("B", 150, 10), ("C", 150, 10))
    r = _vigilar(df)
    assert _alertas(r, "CX-1") == {"A"}
    assert _alertas(r, "CX-6") == {"B", "C"}
    assert _cx6(r, "A").extra["cubierta_por"] == "CX-1"
    assert _cx6(r, "A").state.value == "ok"


def test_tres_grupos_cx1_alert_groups_viva_suprime_solo_ese_grupo():
    df = _usage(("A", 15, 10), ("B", 150, 10), ("C", 150, 10))
    sin = _vigilar(df)
    con = _vigilar(df, cx1_alert_groups={"A"})
    assert _alertas(sin, "CX-6") == {"A", "B", "C"}
    assert _alertas(con, "CX-6") == {"B", "C"}


def test_sin_cx1_alert_groups_el_comportamiento_es_el_de_siempre():
    df = _usage(("A", 15, 10), ("B", 150, 10))
    assert _alertas(_vigilar(df, cx1_alert_groups=None), "CX-6") == {"A"}
    assert _alertas(_vigilar(df, cx1_alert_groups=set()), "CX-6") == {"A"}
