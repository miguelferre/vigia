"""Cruzadas con un diario de 5 clases.

CX-2, CX-3, CX-5 y CX-6 comparan clases: una discrepancia entre dos clases no
favorables también es un override. CX-1 usa el 0/1 del conjunto favorable
(`truth_fav` y `model_fav` del diario): positivos son la verdad dentro del
conjunto y fallo es la salida fuera de él. Sin conjunto favorable, CX-1
da `sin_datos` con su motivo.
"""

from __future__ import annotations

import pandas as pd

from vigia.human.cross_alerts import (
    MOTIVO_SIN_CONJUNTO_FAVORABLE,
    build_reference,
    evaluate_cross,
)

FAVORABLES = {"A", "B"}
NO_FAVORABLES = ["C", "D", "E"]


def _otra_no_favorable(clase: str) -> str:
    return NO_FAVORABLES[(NO_FAVORABLES.index(clase) + 1) % 3]


def _grupo(
    nombre: str,
    *,
    n: int,
    overrides: int,
    positivos: int,
    fn: int,
    offset: int,
    entre_no_favorables: bool = False,
    clinicos: int = 3,
    conjunto: bool = True,
) -> pd.DataFrame:
    """`n` decisiones con 5 clases. Los primeros `positivos` casos tienen la verdad
    en el conjunto favorable (A o B) y el modelo falla en los primeros `fn`
    (dice C). Las últimas `overrides` filas corrigen al modelo: con
    `entre_no_favorables`, cambian una clase no favorable por otra."""
    verdad, modelo, humano = [], [], []
    for i in range(n):
        if i < positivos:
            v = "AB"[i % 2]
            m = "C" if i < fn else v
        else:
            v = NO_FAVORABLES[i % 3]
            m = v
        h = m
        if i >= n - overrides:
            h = _otra_no_favorable(m) if (m in NO_FAVORABLES and entre_no_favorables) else (
                "E" if m in FAVORABLES else "A"
            )
        verdad.append(v)
        modelo.append(m)
        humano.append(h)
    return pd.DataFrame(
        {
            "date": ["2026-01-05"] * n,
            "clinician_pseudonym": [f"clin-{nombre}-{i % clinicos}" for i in range(n)],
            "subgroup": [nombre] * n,
            "human_decision": humano,
            "model_output": modelo,
            "ground_truth": verdad,
            "record_seq": list(range(offset, offset + n)),
            "model_version": ["v1"] * n,
            "truth_fav": [int(v in FAVORABLES) if conjunto else None for v in verdad],
            "model_fav": [int(m in FAVORABLES) if conjunto else None for m in modelo],
            "conjunto_favorable": [conjunto] * n,
        }
    )


def _usage(*grupos: tuple, **kw) -> pd.DataFrame:
    """Cada grupo: (nombre, overrides, fn) con 300 filas y 100 positivos."""
    frames = [
        _grupo(nombre, n=300, overrides=ov, positivos=100, fn=fn, offset=i * 300, **kw)
        for i, (nombre, ov, fn) in enumerate(grupos)
    ]
    return pd.concat(frames, ignore_index=True)


def _vigilar(df: pd.DataFrame, **kw):
    return evaluate_cross(df, reference=build_reference(df), mode="vigilancia", **kw)


def _alertas(r, regla: str) -> set[str]:
    return {a.group for a in r.alerts if a.rule == regla}


def _medida(r, clave: str):
    return next(m for m in r.measurements if m.metric_key == clave)


def test_cx1_usa_la_pertenencia_al_conjunto_favorable():
    """A converge con el modelo (override bajo) y el modelo deja fuera del conjunto
    favorable a 80 de sus 100 positivos; B corrige mucho y el modelo falla poco."""
    r = _vigilar(_usage(("A", 15, 80), ("B", 150, 10)))
    assert _alertas(r, "CX-1") == {"A"}
    fnr = _medida(r, "cx1_model_fnr_z:A")
    assert fnr.extra["positives_group"] == 100
    assert fnr.extra["fnr_group"] == 0.8
    assert fnr.extra["fnr_complement"] == 0.1


def test_cx1_un_cambio_entre_dos_favorables_no_es_un_fallo_del_modelo():
    """La salida del modelo cuenta como fallo solo si sale del conjunto: acertar con
    la otra clase favorable (el modelo dice B y la verdad es A) no es fallo."""
    df = _usage(("A", 15, 0), ("B", 150, 0))
    df.loc[df["truth_fav"] == 1, "model_output"] = "B"
    df.loc[df["truth_fav"] == 1, "human_decision"] = "B"
    r = _vigilar(df)
    assert _alertas(r, "CX-1") == set()
    assert _medida(r, "cx1_model_fnr_z:A").extra["fnr_group"] == 0.0


def test_cx6_cuenta_como_override_un_cambio_entre_clases_no_favorables():
    """Los 150 overrides de B van de una clase no favorable a otra: con el diario
    colapsado a favorable o no, B no tendría ninguno y CX-6 no vería nada."""
    r = _vigilar(_usage(("A", 15, 10), ("B", 150, 10), entre_no_favorables=True))
    assert _alertas(r, "CX-1") == set()
    assert _alertas(r, "CX-6") == {"A"}
    cx6 = _medida(r, "cx6_override_z:A")
    assert cx6.value is not None and abs(cx6.value) >= 3.0


def test_cx6_dos_clases_iguales_no_son_un_override():
    """Mismo diario sin ningún cambio: ni override ni CX-6."""
    r = _vigilar(_usage(("A", 0, 10), ("B", 0, 10)))
    assert _alertas(r, "CX-6") == set()
    assert _medida(r, "cx6_override_z:A").state.value in {"sin_datos", "ok"}


def test_cx5_compara_el_override_por_clinico_con_clases():
    """Tres profesionales con 5, 30 y 60 % de override entre clases no favorables."""
    partes = []
    for i, (nombre, ov) in enumerate((("x", 10), ("y", 60), ("z", 120))):
        parte = _grupo(
            "G", n=200, overrides=ov, positivos=50, fn=5, offset=i * 200, entre_no_favorables=True
        )
        parte["clinician_pseudonym"] = f"clin-{nombre}"
        partes.append(parte)
    r = _vigilar(pd.concat(partes, ignore_index=True))
    cx5 = _medida(r, "cx5_chi2_p")
    assert cx5.state.value == "alerta"
    assert cx5.value is not None and cx5.value < 1e-3
    assert _alertas(r, "CX-5") == {None}


def test_cx2_la_calidad_en_alerta_con_mas_override_que_la_referencia():
    referencia = _usage(("A", 10, 10), ("B", 10, 10), entre_no_favorables=True)
    ventana = _usage(("A", 120, 10), ("B", 120, 10), entre_no_favorables=True)
    r = evaluate_cross(
        ventana,
        reference=build_reference(referencia),
        quality_state="alerta",
        mode="vigilancia",
    )
    assert _medida(r, "cx2_override_z").state.value == "alerta"
    assert {a.rule for a in r.alerts} >= {"CX-2"}
    # Con la calidad en ok, el mismo diario no abre CX-2.
    r_ok = evaluate_cross(
        ventana, reference=build_reference(referencia), quality_state="ok", mode="vigilancia"
    )
    assert _medida(r_ok, "cx2_override_z").state.value == "ok"


def _con_rescate(*, n: int, errores: int, rescatados: int, extra_overrides: int) -> pd.DataFrame:
    """`errores` filas donde el modelo falla (dice C y la verdad es D); en
    `rescatados` el profesional pone la verdad, en el resto otra clase que no
    es la verdad. `extra_overrides` filas acertadas del modelo que el profesional cambia."""
    verdad, modelo, humano = [], [], []
    for i in range(n):
        if i < errores:
            v, m = "D", "C"
            h = v if i < rescatados else "E"
        else:
            v = m = NO_FAVORABLES[i % 3]
            h = _otra_no_favorable(m) if i < errores + extra_overrides else m
        verdad.append(v)
        modelo.append(m)
        humano.append(h)
    return pd.DataFrame(
        {
            "date": ["2026-01-05"] * n,
            "clinician_pseudonym": [f"clin-{i % 3}" for i in range(n)],
            "subgroup": ["G"] * n,
            "human_decision": humano,
            "model_output": modelo,
            "ground_truth": verdad,
            "record_seq": list(range(n)),
            "model_version": ["v1"] * n,
            "truth_fav": [0] * n,
            "model_fav": [0] * n,
            "conjunto_favorable": [True] * n,
        }
    )


def test_cx3_el_rescate_compara_con_la_clase_real():
    """Referencia: el profesional rescata 80 de 100 errores. Ventana: el profesional
    cambia más, pero ya no pone la clase real: rescate 10 de 100."""
    referencia = _con_rescate(n=400, errores=100, rescatados=80, extra_overrides=0)
    ventana = _con_rescate(n=400, errores=100, rescatados=10, extra_overrides=120)
    r = evaluate_cross(
        ventana, reference=build_reference(referencia), quality_state="ok", mode="vigilancia"
    )
    rescate = _medida(r, "cx3_rescue_z")
    assert rescate.state.value == "aviso"
    assert rescate.value is not None and rescate.value <= -3.0
    assert _medida(r, "cx3_override_z").value >= 3.0


def test_sin_conjunto_favorable_cx1_da_sin_datos_con_su_motivo():
    df = _usage(("A", 15, 80), ("B", 150, 10), conjunto=False)
    r = _vigilar(df)
    assert _alertas(r, "CX-1") == set()
    for g in ("A", "B"):
        for clave in (f"cx1_override_z:{g}", f"cx1_model_fnr_z:{g}"):
            m = _medida(r, clave)
            assert m.state.value == "sin_datos"
            assert m.motivo == MOTIVO_SIN_CONJUNTO_FAVORABLE
            assert m.value is None
    # CX-6 no lee la pertenencia: sigue calculándose con las clases.
    assert _medida(r, "cx6_override_z:A").value is not None
